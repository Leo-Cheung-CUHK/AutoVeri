"""
poller.py — Polls the AutoVerif cloud for queued jobs and orchestrates the
            simulation → upload → patch workflow.

Job lifecycle (from the runner's perspective)
---------------------------------------------
1. Poll  GET /runners/jobs          → list of jobs with status="queued"
2. Claim POST /runners/jobs/{id}/claim  → status transitions to "running"
3. Run simulation locally (simulator.py)
4. Upload logs POST /runners/jobs/{id}/logs → status becomes "logs_uploaded"
5. Poll job status (via GET /runners/jobs) until status = "analyzing"
   (meaning the user approved the AI patch in the cloud dashboard)
6. Fetch patch via GET /runners/jobs/{id}/patch
   NOTE: The backend exposes the patch through the job detail endpoint
   (GET /jobs/{id}), but runners must use the runner-auth poll endpoint.
   We store the patch from the jobs list and re-fetch with the runner token.
7. Apply patch + push branch (patcher.py)
8. Confirm POST /runners/jobs/{id}/apply → cloud re-queues job for re-sim
"""

from __future__ import annotations

import signal
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from rich.console import Console

from autoverif_runner.patcher import Patcher, PatchError
from autoverif_runner.simulator import Simulator
from autoverif_runner.uploader import Uploader

console = Console()

# Seconds to wait between full job-list polls.
_DEFAULT_POLL_INTERVAL = 10
# How long to wait for the user to approve/reject the AI patch (seconds).
_APPROVAL_POLL_INTERVAL = 15
_APPROVAL_TIMEOUT = 60 * 60  # 1 hour
# HTTP client timeout for individual API calls.
_HTTP_TIMEOUT = 30


def _ts() -> str:
    """Current UTC time as a compact string for log prefixes."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


class Poller:
    """
    Main polling loop.  Instantiate once and call :meth:`run` to start.

    Args:
        config:         The loaded runner config dict (from config.py).
        repo_path:      Absolute path to the local HDL repository.
        poll_interval:  Seconds between polling calls (default 10).
    """

    def __init__(
        self,
        config: dict,
        repo_path: str,
        poll_interval: int = _DEFAULT_POLL_INTERVAL,
    ) -> None:
        self.config = config
        self.repo_path = repo_path
        self.poll_interval = poll_interval

        self.server_url: str = config["server_url"].rstrip("/")
        self.runner_token: str = config["runner_token"]
        self.runner_id: str = config["runner_id"]
        self.project_id: str = config["project_id"]

        self._stop = False
        self._current_job_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the blocking polling loop.  Handles SIGINT gracefully."""
        self._install_signal_handler()

        console.rule("[bold cyan]AutoVerif Runner[/bold cyan]")
        console.print(
            f"[dim]Server:[/dim]   {self.server_url}\n"
            f"[dim]Runner:[/dim]   {self.runner_id}\n"
            f"[dim]Project:[/dim]  {self.project_id}\n"
            f"[dim]Repo:[/dim]     {self.repo_path}\n"
            f"[dim]Interval:[/dim] {self.poll_interval}s\n"
        )
        console.print("[green]Runner started — waiting for jobs…[/green]\n")

        while not self._stop:
            try:
                self._poll_cycle()
            except KeyboardInterrupt:
                break
            except Exception as exc:  # noqa: BLE001
                console.print(f"[red][{_ts()}] Unhandled error in poll cycle:[/red] {exc}")

            if not self._stop:
                self._sleep_with_interrupt(self.poll_interval)

        console.print("\n[yellow]Runner stopped.[/yellow]")

    def stop(self) -> None:
        """Signal the loop to stop after the current cycle completes."""
        self._stop = True

    # ------------------------------------------------------------------
    # Internal — polling cycle
    # ------------------------------------------------------------------

    def _poll_cycle(self) -> None:
        jobs = self._fetch_queued_jobs()
        if not jobs:
            return  # Nothing to do; spinner will tick on next wake-up.

        for job in jobs:
            if self._stop:
                break
            self._handle_job(job)

    def _handle_job(self, job: dict) -> None:
        job_id = job["id"]
        commit_sha = job.get("commit_sha", "unknown")
        branch = job.get("branch", "unknown")
        sim_command = job.get("sim_command", "make sim")
        timeout_minutes = int(job.get("timeout_minutes", 30))

        console.rule(f"[bold]Job {job_id[:8]}…[/bold]")
        console.print(
            f"[cyan]Branch:[/cyan]  {branch}\n"
            f"[cyan]Commit:[/cyan]  {commit_sha}\n"
            f"[cyan]Command:[/cyan] {sim_command}\n"
        )

        # ── 1. Claim ──────────────────────────────────────────────────
        if not self._claim_job(job_id):
            return

        # ── 2. Simulate ───────────────────────────────────────────────
        sim = Simulator(
            repo_path=self.repo_path,
            sim_command=sim_command,
            timeout_minutes=timeout_minutes,
        )
        try:
            result = sim.run(last_passing_sha=None)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Simulation error:[/red] {exc}")
            self._report_failure(job_id, str(exc))
            return

        # ── 3. Upload logs ────────────────────────────────────────────
        uploader = Uploader(
            cloud_url=self.server_url,
            runner_token=self.runner_token,
            job_id=job_id,
            simulation_result=result,
        )
        upload_result = uploader.upload()
        if not upload_result.success:
            console.print(f"[red]Log upload failed:[/red] {upload_result.detail}")
            return  # Cloud will eventually time-out the job.

        # ── 4. Wait for user approval (patch ready) ───────────────────
        console.print(
            "\n[yellow]Waiting for patch approval in the cloud dashboard…[/yellow]"
        )
        patch_content = self._wait_for_patch(job_id, timeout_minutes=60)
        if patch_content is None:
            console.print("[yellow]No patch approved within timeout — moving on.[/yellow]")
            return

        # ── 5. Apply patch + push branch ──────────────────────────────
        patcher = Patcher(
            repo_path=self.repo_path,
            patch_content=patch_content,
            commit_sha=commit_sha,
        )
        try:
            branch_name = patcher.apply()
        except PatchError as exc:
            console.print(f"[red]Patch could not be applied:[/red] {exc}")
            self._report_failure(job_id, f"Patch apply failed: {exc}")
            return
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Unexpected patcher error:[/red] {exc}")
            return

        console.print(f"[green]Patch applied and pushed on branch:[/green] {branch_name}")

        # ── 6. Confirm apply to cloud ─────────────────────────────────
        self._confirm_apply(job_id)
        console.print(f"[green]Job {job_id[:8]} complete — cloud will re-queue for re-sim.[/green]")
        console.rule()

    # ------------------------------------------------------------------
    # Internal — API calls
    # ------------------------------------------------------------------

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.runner_token}"}

    def _fetch_queued_jobs(self) -> list[dict]:
        """GET /runners/jobs → list of queued jobs for this runner's project."""
        url = f"{self.server_url}/runners/jobs"
        try:
            with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
                resp = client.get(url, headers=self._headers())
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 401:
                console.print(
                    f"[red][{_ts()}] Authentication failed — check runner token.[/red]"
                )
                self._stop = True
            else:
                console.print(
                    f"[yellow][{_ts()}] Poll returned HTTP {resp.status_code}[/yellow]"
                )
        except httpx.RequestError as exc:
            console.print(f"[yellow][{_ts()}] Network error polling jobs:[/yellow] {exc}")
        return []

    def _claim_job(self, job_id: str) -> bool:
        """POST /runners/jobs/{job_id}/claim → True if successfully claimed."""
        url = f"{self.server_url}/runners/jobs/{job_id}/claim"
        try:
            with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
                resp = client.post(url, headers=self._headers())
            if resp.status_code in (200, 201):
                console.print(f"[green]Claimed job {job_id[:8]}[/green]")
                return True
            if resp.status_code == 409:
                console.print(
                    f"[yellow]Job {job_id[:8]} already claimed (conflict) — skipping.[/yellow]"
                )
            else:
                console.print(
                    f"[red]Failed to claim job {job_id[:8]}:[/red] "
                    f"HTTP {resp.status_code} — {resp.text[:200]}"
                )
        except httpx.RequestError as exc:
            console.print(f"[red]Network error claiming job:[/red] {exc}")
        return False

    def _wait_for_patch(
        self, job_id: str, timeout_minutes: int = 60
    ) -> Optional[str]:
        """
        Poll until the job status becomes "analyzing" (AI analysis complete)
        and the user approves the patch, then return the patch content.

        Flow:
          1. Poll GET /runners/jobs/{id}/status until status = "analyzing"
             (means the debug agent finished and a DebugResult is ready).
          2. Then poll GET /runners/jobs/{id}/patch until it returns 200
             (means the user approved the patch in the web UI).
          3. Return the patch string, or None on timeout/failure/no patch.
        """
        deadline = time.monotonic() + timeout_minutes * 60
        status_url = f"{self.server_url}/runners/jobs/{job_id}/status"
        patch_url = f"{self.server_url}/runners/jobs/{job_id}/patch"

        while time.monotonic() < deadline and not self._stop:
            try:
                with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
                    resp = client.get(status_url, headers=self._headers())

                if resp.status_code != 200:
                    console.print(
                        f"[yellow]Status poll returned {resp.status_code}[/yellow]"
                    )
                    self._sleep_with_interrupt(_APPROVAL_POLL_INTERVAL)
                    continue

                job_data = resp.json()
                job_status = job_data.get("status", "")

                if job_status in ("failed", "timeout"):
                    console.print(
                        f"[yellow]Job {job_id[:8]} moved to '{job_status}' — no patch.[/yellow]"
                    )
                    return None

                if job_status == "completed":
                    console.print(
                        f"[green]Job {job_id[:8]} completed with no errors — no patch needed.[/green]"
                    )
                    return None

                if job_status == "analyzing":
                    # AI has produced a result. Try to fetch the approved patch.
                    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
                        patch_resp = client.get(patch_url, headers=self._headers())

                    if patch_resp.status_code == 200:
                        patch_data = patch_resp.json()
                        patch_content = patch_data.get("patch")
                        if patch_content:
                            console.print(
                                f"[green]Patch approved and fetched for job {job_id[:8]}[/green]"
                            )
                            return patch_content
                        # Approved but no patch generated (AI couldn't produce one)
                        console.print(
                            f"[yellow]Job {job_id[:8]} approved but no patch in result.[/yellow]"
                        )
                        return None
                    elif patch_resp.status_code == 404:
                        # Not yet approved — keep polling
                        console.print(
                            f"[dim][{_ts()}] Job {job_id[:8]}: AI result ready, "
                            "waiting for approval in dashboard…[/dim]"
                        )
                    else:
                        console.print(
                            f"[yellow]Patch fetch returned {patch_resp.status_code}[/yellow]"
                        )
                else:
                    # logs_uploaded or similar — AI not done yet
                    console.print(
                        f"[dim][{_ts()}] Job {job_id[:8]} status: {job_status} — "
                        "waiting for AI analysis…[/dim]"
                    )

            except httpx.RequestError as exc:
                console.print(f"[yellow]Network error waiting for patch:[/yellow] {exc}")

            self._sleep_with_interrupt(_APPROVAL_POLL_INTERVAL)

        return None  # Timed out

    def _confirm_apply(self, job_id: str) -> bool:
        """POST /runners/jobs/{job_id}/apply → True on success."""
        url = f"{self.server_url}/runners/jobs/{job_id}/apply"
        try:
            with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
                resp = client.post(url, headers=self._headers())
            if resp.status_code in (200, 201, 202):
                return True
            console.print(
                f"[red]Apply confirm failed:[/red] HTTP {resp.status_code} — {resp.text[:200]}"
            )
        except httpx.RequestError as exc:
            console.print(f"[red]Network error confirming apply:[/red] {exc}")
        return False

    def _report_failure(self, job_id: str, reason: str) -> None:
        """
        Best-effort: upload a failure log so the cloud knows the job failed
        locally rather than timing out silently.
        """
        from autoverif_runner.simulator import SimulationResult

        failure_log = f"[AutoVerif Runner] Job failed on runner.\nReason: {reason}\n"
        fake_result = SimulationResult(
            sim_log=failure_log,
            git_diff="",
            exit_code=-1,
            duration_seconds=0.0,
            error=reason,
        )
        uploader = Uploader(
            cloud_url=self.server_url,
            runner_token=self.runner_token,
            job_id=job_id,
            simulation_result=fake_result,
        )
        uploader.upload()

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _sleep_with_interrupt(self, seconds: int) -> None:
        """Sleep in 1-second chunks so SIGINT is handled promptly."""
        for _ in range(seconds):
            if self._stop:
                return
            time.sleep(1)

    def _install_signal_handler(self) -> None:
        def _handler(sig, frame):  # noqa: ANN001
            console.print("\n[yellow]Interrupt received — stopping after current job…[/yellow]")
            self._stop = True

        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)
