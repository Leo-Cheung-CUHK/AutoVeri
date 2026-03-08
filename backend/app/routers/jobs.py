"""
Jobs router — job listing, detail view, approve/reject debug results.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.models import DebugResult, Job, JobIteration, ParsedError, Project, User
from app.routers.auth import get_current_user

router = APIRouter(prefix="/jobs", tags=["jobs"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ParsedErrorOut(BaseModel):
    id: str
    error_type: str
    file_path: str
    line_number: Optional[int]
    message: str
    sim_time: Optional[str]
    test_name: Optional[str]

    class Config:
        from_attributes = True


class JobIterationOut(BaseModel):
    id: str
    iteration_number: int
    patch: Optional[str]
    errors_before: Optional[list]
    errors_after: Optional[list]
    new_errors_introduced: bool
    outcome: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class DebugResultOut(BaseModel):
    id: str
    root_cause: str
    fix_target: Optional[str]
    confidence: str
    explanation: str
    patch: Optional[str]
    approved_at: Optional[datetime]
    rejected_at: Optional[datetime]
    approval_expires_at: datetime

    class Config:
        from_attributes = True


class JobSummaryOut(BaseModel):
    id: str
    project_id: str
    runner_id: Optional[str]
    commit_sha: str
    branch: str
    status: str
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class JobDetailOut(JobSummaryOut):
    git_diff: Optional[str]
    timeout_at: Optional[datetime]
    iterations: list[JobIterationOut]
    parsed_errors: list[ParsedErrorOut]
    debug_result: Optional[DebugResultOut]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=list[JobSummaryOut], summary="List jobs for user's projects")
async def list_jobs(
    project_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List jobs across all of the current user's projects (or filtered by project_id).
    """
    # Get IDs of projects owned by user
    proj_result = await db.execute(
        select(Project.id).where(Project.user_id == current_user.id)
    )
    owned_project_ids = [row[0] for row in proj_result.all()]

    if not owned_project_ids:
        return []

    query = select(Job).where(Job.project_id.in_(owned_project_ids))

    if project_id:
        if project_id not in owned_project_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        query = query.where(Job.project_id == project_id)

    query = query.order_by(Job.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobDetailOut, summary="Get full job details")
async def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return full job details including iterations, parsed errors, and debug result."""
    job = await _get_user_job(job_id, current_user.id, db, load_relations=True)
    return _job_to_detail(job)


@router.post("/{job_id}/approve", response_model=DebugResultOut, summary="Approve debug result")
async def approve_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Approve the debug result for a job.
    Sets approved_at and transitions the job to 'analyzing' so the runner
    will pick up the patch via GET /runners/jobs.
    """
    job = await _get_user_job(job_id, current_user.id, db)

    if job.status not in ("analyzing", "logs_uploaded"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is not in an approvable state (status: {job.status})",
        )

    dr_result = await db.execute(select(DebugResult).where(DebugResult.job_id == job_id))
    debug_result = dr_result.scalar_one_or_none()
    if not debug_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No debug result found for this job",
        )

    now = datetime.now(timezone.utc)

    if now > debug_result.approval_expires_at:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Approval window has expired. Please re-trigger the job.",
        )

    if debug_result.rejected_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Debug result has already been rejected",
        )

    debug_result.approved_at = now
    job.status = "analyzing"  # Runner will poll and see patch ready
    await db.commit()
    await db.refresh(debug_result)
    return DebugResultOut.model_validate(debug_result)


@router.post("/{job_id}/reject", response_model=DebugResultOut, summary="Reject debug result")
async def reject_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Reject the debug result for a job. Transitions job to 'failed'.
    """
    job = await _get_user_job(job_id, current_user.id, db)

    if job.status not in ("analyzing", "logs_uploaded"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is not in a rejectable state (status: {job.status})",
        )

    dr_result = await db.execute(select(DebugResult).where(DebugResult.job_id == job_id))
    debug_result = dr_result.scalar_one_or_none()
    if not debug_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No debug result found for this job",
        )

    if debug_result.approved_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Debug result has already been approved",
        )

    debug_result.rejected_at = datetime.now(timezone.utc)
    job.status = "failed"
    await db.commit()
    await db.refresh(debug_result)
    return DebugResultOut.model_validate(debug_result)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_user_job(
    job_id: str,
    user_id: str,
    db: AsyncSession,
    load_relations: bool = False,
) -> Job:
    """Load a job, verifying it belongs to a project owned by user_id."""
    # Check ownership via project join
    proj_result = await db.execute(
        select(Project.id).where(Project.user_id == user_id)
    )
    owned_project_ids = [row[0] for row in proj_result.all()]

    if load_relations:
        query = (
            select(Job)
            .options(
                selectinload(Job.iterations),
                selectinload(Job.parsed_errors),
                selectinload(Job.debug_result),
            )
            .where(Job.id == job_id, Job.project_id.in_(owned_project_ids))
        )
    else:
        query = select(Job).where(Job.id == job_id, Job.project_id.in_(owned_project_ids))

    result = await db.execute(query)
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


def _job_to_detail(job: Job) -> JobDetailOut:
    return JobDetailOut(
        id=job.id,
        project_id=job.project_id,
        runner_id=job.runner_id,
        commit_sha=job.commit_sha,
        branch=job.branch,
        status=job.status,
        git_diff=job.git_diff,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        timeout_at=job.timeout_at,
        iterations=[JobIterationOut.model_validate(i) for i in job.iterations],
        parsed_errors=[ParsedErrorOut.model_validate(e) for e in job.parsed_errors],
        debug_result=DebugResultOut.model_validate(job.debug_result) if job.debug_result else None,
    )
