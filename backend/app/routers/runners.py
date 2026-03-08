"""
Runners router — Runner registration, job polling, log upload, patch confirmation.
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.models.models import DebugResult, Job, JobIteration, ParsedError, Project, Runner
from app.services.debug_agent import DebugAgent
from app.services.log_parser import LogParser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runners", tags=["runners"])
bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Runner authentication dependency
# ---------------------------------------------------------------------------

async def get_current_runner(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Runner:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing runner token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials:
        raise exc

    result = await db.execute(
        select(Runner).where(Runner.token == credentials.credentials, Runner.is_active == True)
    )
    runner = result.scalar_one_or_none()
    if not runner:
        raise exc

    # Update last-seen timestamp
    runner.last_seen_at = datetime.now(timezone.utc)
    await db.commit()
    return runner


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class RunnerRegisterRequest(BaseModel):
    project_token: str  # The project's webhook_secret used as a shared registration secret
    name: str
    platform: str  # linux | mac


class RunnerOut(BaseModel):
    id: str
    name: str
    token: str
    platform: str
    project_id: str
    registered_at: datetime

    class Config:
        from_attributes = True


class JobPollOut(BaseModel):
    id: str
    project_id: str
    commit_sha: str
    branch: str
    status: str
    sim_command: str
    tb_folder_pattern: str
    rtl_folder_pattern: str
    timeout_minutes: int
    created_at: datetime


class JobClaimOut(BaseModel):
    id: str
    status: str
    started_at: Optional[datetime]


class ApplyConfirmOut(BaseModel):
    id: str
    status: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/register",
    response_model=RunnerOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new runner",
)
async def register_runner(
    body: RunnerRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a runner for a project. Authentication uses the project's webhook_secret
    as a shared registration secret.
    """
    result = await db.execute(
        select(Project).where(Project.webhook_secret == body.project_token)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid project token",
        )

    if body.platform not in ("linux", "mac"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="platform must be 'linux' or 'mac'",
        )

    runner = Runner(
        id=str(uuid.uuid4()),
        project_id=project.id,
        name=body.name,
        token=secrets.token_hex(32),
        platform=body.platform,
        is_active=True,
    )
    db.add(runner)
    await db.commit()
    await db.refresh(runner)
    return runner


@router.get("/jobs", response_model=list[JobPollOut], summary="Poll for queued jobs")
async def poll_jobs(
    runner: Runner = Depends(get_current_runner),
    db: AsyncSession = Depends(get_db),
):
    """
    Return jobs that are queued for this runner's project and not yet claimed.
    The runner polls this endpoint at RUNNER_POLL_INTERVAL_SECONDS.
    """
    result = await db.execute(
        select(Job, Project)
        .join(Project, Job.project_id == Project.id)
        .where(
            Job.project_id == runner.project_id,
            Job.status == "queued",
        )
        .order_by(Job.created_at.asc())
    )
    rows = result.all()

    jobs_out = []
    for job, project in rows:
        jobs_out.append(
            JobPollOut(
                id=job.id,
                project_id=job.project_id,
                commit_sha=job.commit_sha,
                branch=job.branch,
                status=job.status,
                sim_command=project.sim_command,
                tb_folder_pattern=project.tb_folder_pattern,
                rtl_folder_pattern=project.rtl_folder_pattern,
                timeout_minutes=project.timeout_minutes,
                created_at=job.created_at,
            )
        )
    return jobs_out


@router.post("/jobs/{job_id}/claim", response_model=JobClaimOut, summary="Claim a job")
async def claim_job(
    job_id: str,
    runner: Runner = Depends(get_current_runner),
    db: AsyncSession = Depends(get_db),
):
    """
    Claim a queued job — transitions it to 'running' and associates this runner.
    Only the runner for the job's project may claim it.
    """
    job = await _get_runner_job(job_id, runner, db)

    if job.status != "queued":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is not queued (current status: {job.status})",
        )

    now = datetime.now(timezone.utc)
    job.status = "running"
    job.runner_id = runner.id
    job.started_at = now

    await db.commit()
    await db.refresh(job)
    return JobClaimOut(id=job.id, status=job.status, started_at=job.started_at)


async def _analyse_job(job_id: str) -> None:
    """
    Background task: run one AI analysis pass after logs are uploaded.
    Creates a JobIteration and DebugResult, then sets job status to 'analyzing'.
    """
    async with AsyncSessionLocal() as db:
        try:
            # Load job
            result = await db.execute(select(Job).where(Job.id == job_id))
            job = result.scalar_one_or_none()
            if not job or job.status != "logs_uploaded":
                return

            # Count existing iterations to enforce max-3 limit
            iter_count_result = await db.execute(
                select(func.count(JobIteration.id)).where(JobIteration.job_id == job_id)
            )
            iteration_count = iter_count_result.scalar() or 0
            iteration_num = iteration_count + 1

            if iteration_count >= 3:
                job.status = "failed"
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()
                logger.warning("Job %s reached max iterations; marked failed", job_id)
                return

            # Load parsed errors for this job
            errors_result = await db.execute(
                select(ParsedError).where(ParsedError.job_id == job_id, ParsedError.iteration_id.is_(None))
            )
            errors = errors_result.scalars().all()
            errors_list = [
                {
                    "error_type": e.error_type,
                    "file_path": e.file_path,
                    "line_number": e.line_number,
                    "message": e.message,
                    "sim_time": e.sim_time,
                    "test_name": e.test_name,
                }
                for e in errors
            ]

            if not errors_list:
                # No errors → simulation passed
                job.status = "completed"
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()
                logger.info("Job %s has no errors; marked completed", job_id)
                return

            # Signal analysis in progress
            job.status = "analyzing"
            await db.commit()

            # Call the AI debug agent
            agent = DebugAgent()
            debug_dict = await agent.analyse(
                errors=errors_list,
                git_diff=job.git_diff or "",
                error_contexts=[],
            )

            # Persist JobIteration record
            iteration = JobIteration(
                id=str(uuid.uuid4()),
                job_id=job_id,
                iteration_number=iteration_num,
                patch=debug_dict.get("patch"),
                errors_before=errors_list,
                errors_after=None,
                new_errors_introduced=False,
                outcome=None,
            )
            db.add(iteration)
            await db.commit()

            # Upsert DebugResult (one per job)
            existing = await db.execute(select(DebugResult).where(DebugResult.job_id == job_id))
            dr = existing.scalar_one_or_none()
            approval_expires = datetime.now(timezone.utc) + timedelta(hours=24)

            if dr:
                dr.root_cause = debug_dict["root_cause"]
                dr.fix_target = debug_dict["fix_target"]
                dr.confidence = debug_dict["confidence"]
                dr.explanation = debug_dict["explanation"]
                dr.patch = debug_dict.get("patch")
                dr.approved_at = None
                dr.rejected_at = None
                dr.approval_expires_at = approval_expires
            else:
                dr = DebugResult(
                    id=str(uuid.uuid4()),
                    job_id=job_id,
                    root_cause=debug_dict["root_cause"],
                    fix_target=debug_dict["fix_target"],
                    confidence=debug_dict["confidence"],
                    explanation=debug_dict["explanation"],
                    patch=debug_dict.get("patch"),
                    approval_expires_at=approval_expires,
                )
                db.add(dr)

            await db.commit()
            logger.info(
                "Job %s analysis complete — iteration %d, confidence=%s, patch=%s",
                job_id, iteration_num, debug_dict["confidence"],
                "yes" if debug_dict.get("patch") else "no",
            )

        except Exception as exc:
            logger.exception("_analyse_job failed for job %s: %s", job_id, exc)
            # Best-effort: mark job failed so UI doesn't spin forever
            try:
                async with AsyncSessionLocal() as err_db:
                    await err_db.execute(
                        update(Job).where(Job.id == job_id).values(status="failed")
                    )
                    await err_db.commit()
            except Exception:
                pass


@router.post("/jobs/{job_id}/logs", status_code=status.HTTP_202_ACCEPTED, summary="Upload simulation logs")
async def upload_logs(
    job_id: str,
    background_tasks: BackgroundTasks,
    sim_log: UploadFile = File(..., description="The simulation log file (sim.log)"),
    git_diff: Optional[str] = Form(None, description="The git diff for this run"),
    runner: Runner = Depends(get_current_runner),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload sim.log (and optionally git_diff) for a running job.
    Parses the log immediately and stores ParsedErrors.
    Transitions status to 'logs_uploaded'.
    """
    job = await _get_runner_job(job_id, runner, db)

    if job.status not in ("running", "logs_uploaded"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot upload logs for job with status '{job.status}'",
        )

    log_content = (await sim_log.read()).decode("utf-8", errors="replace")

    # Determine tb/rtl patterns from project
    proj_result = await db.execute(select(Project).where(Project.id == job.project_id))
    project = proj_result.scalar_one()

    # Parse errors immediately
    parser = LogParser(
        tb_prefix=project.tb_folder_pattern,
        rtl_prefix=project.rtl_folder_pattern,
    )
    errors = parser.parse(log_content)

    # Persist parsed errors
    for err in errors:
        pe = ParsedError(
            id=str(uuid.uuid4()),
            job_id=job.id,
            iteration_id=None,
            **err,
        )
        db.add(pe)

    # Update job fields
    job.git_diff = git_diff or job.git_diff
    job.status = "logs_uploaded"

    await db.commit()

    # Trigger AI analysis as a background task
    background_tasks.add_task(_analyse_job, job.id)

    return {
        "detail": "Logs uploaded and parsed",
        "errors_found": len(errors),
        "job_id": job.id,
    }


class JobStatusOut(BaseModel):
    id: str
    status: str
    completed_at: Optional[datetime]
    timeout_at: Optional[datetime]


@router.get("/jobs/{job_id}/status", response_model=JobStatusOut, summary="Check job status")
async def get_job_status(
    job_id: str,
    runner: Runner = Depends(get_current_runner),
    db: AsyncSession = Depends(get_db),
):
    """
    Lightweight status check polled by the Runner while waiting for
    human approval (analyzing) or for re-simulation (queued).
    """
    job = await _get_runner_job(job_id, runner, db)
    return JobStatusOut(
        id=job.id,
        status=job.status,
        completed_at=job.completed_at,
        timeout_at=job.timeout_at,
    )


class PatchOut(BaseModel):
    job_id: str
    patch: Optional[str]
    confidence: Optional[str]
    explanation: Optional[str]


@router.get("/jobs/{job_id}/patch", response_model=PatchOut, summary="Fetch approved patch for a job")
async def get_job_patch(
    job_id: str,
    runner: Runner = Depends(get_current_runner),
    db: AsyncSession = Depends(get_db),
):
    """
    Called by the Runner after it detects job status is 'approved'.
    Returns the patch content from the DebugResult so the Runner can apply it.
    Only returns a patch if the DebugResult has been approved.
    """
    job = await _get_runner_job(job_id, runner, db)

    result = await db.execute(
        select(DebugResult).where(
            DebugResult.job_id == job_id,
            DebugResult.approved_at.isnot(None),
        )
    )
    debug_result = result.scalar_one_or_none()
    if not debug_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No approved patch found for this job",
        )

    return PatchOut(
        job_id=job.id,
        patch=debug_result.patch,
        confidence=debug_result.confidence,
        explanation=debug_result.explanation,
    )


@router.post("/jobs/{job_id}/apply", response_model=ApplyConfirmOut, summary="Confirm patch applied")
async def confirm_patch_applied(
    job_id: str,
    runner: Runner = Depends(get_current_runner),
    db: AsyncSession = Depends(get_db),
):
    """
    Runner calls this after it has applied the approved patch and pushed to the repo.
    Transitions job status back to 'queued' so the re-simulation run can be claimed.
    """
    job = await _get_runner_job(job_id, runner, db)

    if job.status != "analyzing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Expected job status 'analyzing', got '{job.status}'",
        )

    job.status = "queued"
    job.runner_id = None  # release so any runner can pick it up
    await db.commit()
    await db.refresh(job)
    return ApplyConfirmOut(id=job.id, status=job.status)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_runner_job(job_id: str, runner: Runner, db: AsyncSession) -> Job:
    """Load a job and verify it belongs to the runner's project."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.project_id == runner.project_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job
