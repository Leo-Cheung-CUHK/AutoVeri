"""
RefinementLoop: Orchestrates the parse → debug → apply → re-simulate cycle.

The loop:
  1. Parse current sim log → extract errors
  2. Call DebugAgent → produce fix (patch + explanation)
  3. Persist DebugResult and JobIteration in DB
  4. Signal via DB status that runner should apply the patch
  5. Wait for runner to upload new logs (status = logs_uploaded)
  6. Repeat up to max_iterations
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import DebugResult, Job, JobIteration, ParsedError
from app.services.debug_agent import DebugAgent
from app.services.log_parser import LogParser

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5
APPROVAL_WINDOW_HOURS = 24


class RefinementLoop:
    """
    Drives the automated verification–fix loop for a single Job.

    The caller is responsible for providing the initial sim_log content.
    Subsequent iterations are triggered by the Runner uploading new logs.
    """

    def __init__(
        self,
        db: AsyncSession,
        job_id: str,
        max_iterations: int = 3,
        timeout_minutes: int = 30,
    ):
        self.db = db
        self.job_id = job_id
        self.max_iterations = max_iterations
        self.timeout_minutes = timeout_minutes
        self._parser = LogParser()
        self._agent = DebugAgent()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self, sim_log: str, git_diff: str) -> str:
        """
        Execute the refinement loop.

        Returns the final job status string:
          "completed" | "failed" | "timeout"
        """
        job = await self._get_job()
        if not job:
            logger.error("Job %s not found", self.job_id)
            return "failed"

        timeout_at = job.timeout_at or (
            datetime.now(timezone.utc)
            if self.timeout_minutes == 0
            else None
        )

        current_log = sim_log
        current_diff = git_diff

        for iteration_num in range(1, self.max_iterations + 1):
            # Check wall-clock timeout
            if job.timeout_at and datetime.now(timezone.utc) > job.timeout_at:
                await self._set_job_status("timeout")
                logger.warning("Job %s timed out at iteration %d", self.job_id, iteration_num)
                return "timeout"

            logger.info("Job %s — iteration %d starting", self.job_id, iteration_num)

            # Step 1: Parse log
            await self._set_job_status("analyzing")
            errors = self._parser.parse(current_log)
            await self._persist_parsed_errors(errors, iteration_id=None)

            if not errors:
                logger.info("Job %s — no errors found; marking completed", self.job_id)
                await self._set_job_status("completed")
                return "completed"

            # Step 2: AI analysis
            debug_dict = await self._agent.analyse(
                errors=errors,
                git_diff=current_diff,
                error_contexts=[],  # caller may enrich this later
            )

            # Step 3: Persist iteration record
            errors_before_json = errors
            iteration = await self._persist_iteration(
                iteration_num=iteration_num,
                patch=debug_dict.get("patch"),
                errors_before=errors_before_json,
            )

            # Step 4: Persist DebugResult (upsert: one per job)
            await self._persist_debug_result(debug_dict, iteration)

            # Step 5: If no patch, we cannot proceed automatically
            if not debug_dict.get("patch"):
                logger.info(
                    "Job %s — no patch generated at iteration %d; "
                    "marking failed (manual review needed)",
                    self.job_id,
                    iteration_num,
                )
                await self._finalise_iteration(iteration, errors_after=errors, outcome="errors_remain")
                await self._set_job_status("failed")
                return "failed"

            # Step 6: Signal runner to apply patch (status → analyzing keeps the
            # DebugResult visible; the runner polls GET /runners/jobs and will
            # see the approved patch once the user approves, or we set it directly
            # for automated confidence=high cases)
            if debug_dict.get("confidence") == "high":
                logger.info(
                    "Job %s — high-confidence fix; auto-signalling runner", self.job_id
                )
                await self._set_job_status("analyzing")
            else:
                # Pause and wait for human approval (handled by POST /jobs/{id}/approve)
                logger.info(
                    "Job %s — confidence=%s; awaiting human approval",
                    self.job_id,
                    debug_dict.get("confidence"),
                )
                await self._set_job_status("analyzing")
                # In a real deployment, execution stops here and resumes when
                # the approval webhook fires. For the loop skeleton we return.
                return "analyzing"  # caller should await external event

            # Step 7: Wait for runner to upload new logs
            new_log = await self._wait_for_new_logs(timeout_seconds=self.timeout_minutes * 60)
            if new_log is None:
                await self._finalise_iteration(iteration, errors_after=errors, outcome="timeout")
                await self._set_job_status("timeout")
                return "timeout"

            # Step 8: Re-parse new logs for the next iteration
            new_errors = self._parser.parse(new_log)
            new_errors_introduced = self._detect_new_errors(errors, new_errors)

            await self._finalise_iteration(
                iteration,
                errors_after=new_errors,
                outcome="success" if not new_errors else "errors_remain",
                new_errors_introduced=new_errors_introduced,
            )

            if not new_errors:
                logger.info("Job %s — all errors resolved at iteration %d", self.job_id, iteration_num)
                await self._set_job_status("completed")
                return "completed"

            if new_errors_introduced:
                logger.warning(
                    "Job %s — patch introduced new errors at iteration %d; stopping",
                    self.job_id,
                    iteration_num,
                )
                await self._set_job_status("failed")
                return "failed"

            # Prepare next iteration
            current_log = new_log
            # git_diff stays the same (the patch is additive on top of original diff)

        # Exhausted iterations
        logger.warning("Job %s — max iterations (%d) reached", self.job_id, self.max_iterations)
        await self._set_job_status("failed")
        return "failed"

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    async def _get_job(self) -> Optional[Job]:
        result = await self.db.execute(select(Job).where(Job.id == self.job_id))
        return result.scalar_one_or_none()

    async def _set_job_status(self, status: str) -> None:
        await self.db.execute(
            update(Job).where(Job.id == self.job_id).values(status=status)
        )
        await self.db.commit()

    async def _persist_parsed_errors(
        self, errors: list[dict], iteration_id: Optional[str]
    ) -> None:
        for err in errors:
            pe = ParsedError(
                id=str(uuid.uuid4()),
                job_id=self.job_id,
                iteration_id=iteration_id,
                error_type=err["error_type"],
                file_path=err["file_path"],
                line_number=err.get("line_number"),
                message=err["message"],
                sim_time=err.get("sim_time"),
                test_name=err.get("test_name"),
            )
            self.db.add(pe)
        await self.db.commit()

    async def _persist_iteration(
        self,
        iteration_num: int,
        patch: Optional[str],
        errors_before: list[dict],
    ) -> JobIteration:
        iteration = JobIteration(
            id=str(uuid.uuid4()),
            job_id=self.job_id,
            iteration_number=iteration_num,
            patch=patch,
            errors_before=errors_before,
            errors_after=None,
            new_errors_introduced=False,
            outcome=None,
        )
        self.db.add(iteration)
        await self.db.commit()
        await self.db.refresh(iteration)
        return iteration

    async def _finalise_iteration(
        self,
        iteration: JobIteration,
        errors_after: list[dict],
        outcome: str,
        new_errors_introduced: bool = False,
    ) -> None:
        iteration.errors_after = errors_after
        iteration.outcome = outcome
        iteration.new_errors_introduced = new_errors_introduced
        await self.db.commit()

    async def _persist_debug_result(self, debug_dict: dict, iteration: JobIteration) -> None:
        # Check if a DebugResult already exists for this job
        existing = await self.db.execute(
            select(DebugResult).where(DebugResult.job_id == self.job_id)
        )
        dr = existing.scalar_one_or_none()

        approval_expires = datetime.now(timezone.utc)
        approval_expires += timedelta(hours=APPROVAL_WINDOW_HOURS)

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
                job_id=self.job_id,
                root_cause=debug_dict["root_cause"],
                fix_target=debug_dict["fix_target"],
                confidence=debug_dict["confidence"],
                explanation=debug_dict["explanation"],
                patch=debug_dict.get("patch"),
                approval_expires_at=approval_expires,
            )
            self.db.add(dr)

        await self.db.commit()

    # ------------------------------------------------------------------
    # Runner coordination
    # ------------------------------------------------------------------

    async def _wait_for_new_logs(self, timeout_seconds: int) -> Optional[str]:
        """
        Poll the DB until the runner uploads new logs (job status = logs_uploaded).

        Returns the sim_log text if found, or None on timeout.
        Note: In production, you'd use Redis pub/sub or a task queue instead of polling.
        """
        elapsed = 0
        while elapsed < timeout_seconds:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            elapsed += POLL_INTERVAL_SECONDS

            job = await self._get_job()
            if not job:
                return None

            if job.status == "logs_uploaded":
                # The runner has posted new logs; they are stored in job.git_diff
                # (or a dedicated log field — here we re-read from the upload endpoint)
                # Return a sentinel; real implementation fetches from blob storage / field.
                return job.git_diff  # placeholder; real impl fetches stored log

            if job.status in ("failed", "timeout", "completed"):
                return None

        return None

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_new_errors(
        errors_before: list[dict], errors_after: list[dict]
    ) -> bool:
        """Return True if errors_after contains error messages not in errors_before."""
        before_msgs = {e["message"] for e in errors_before}
        for err in errors_after:
            if err["message"] not in before_msgs:
                return True
        return False
