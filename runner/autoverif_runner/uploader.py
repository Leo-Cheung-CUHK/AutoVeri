"""
uploader.py — Uploads simulation logs + git diff to the AutoVerif cloud.

The backend endpoint is:
    POST /runners/jobs/{job_id}/logs
    Content-Type: multipart/form-data
    Authorization: Bearer <runner_token>

Fields:
    sim_log   — UploadFile (sim.log content)
    git_diff  — Form field (optional, plain text)
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import httpx
from rich.console import Console

from autoverif_runner.simulator import SimulationResult

console = Console(stderr=True)

# Maximum time to wait for a log upload response (seconds).
_UPLOAD_TIMEOUT = 120


@dataclass
class UploadResult:
    success: bool
    errors_found: int = 0
    job_id: str = ""
    detail: str = ""
    http_status: int = 0


class Uploader:
    """
    Uploads a :class:`~autoverif_runner.simulator.SimulationResult` to the
    AutoVerif cloud for a specific job.
    """

    def __init__(
        self,
        cloud_url: str,
        runner_token: str,
        job_id: str,
        simulation_result: SimulationResult,
    ) -> None:
        # Strip trailing slash so URL joins are consistent.
        self.cloud_url = cloud_url.rstrip("/")
        self.runner_token = runner_token
        self.job_id = job_id
        self.result = simulation_result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upload(self) -> UploadResult:
        """
        POST the simulation log and git diff to the cloud.

        Returns an :class:`UploadResult` indicating success or failure.
        """
        url = f"{self.cloud_url}/runners/jobs/{self.job_id}/logs"
        headers = {"Authorization": f"Bearer {self.runner_token}"}

        # Build the log content — include exit code, duration, and optional
        # file snippets so the AI has full context.
        log_content = self._build_log_payload()

        console.log(
            f"[cyan]Uploading logs[/cyan] to {url} "
            f"({len(log_content):,} chars)"
        )

        try:
            with httpx.Client(timeout=_UPLOAD_TIMEOUT) as client:
                response = client.post(
                    url,
                    headers=headers,
                    files={
                        "sim_log": (
                            "sim.log",
                            io.BytesIO(log_content.encode("utf-8")),
                            "text/plain",
                        )
                    },
                    data={
                        "git_diff": self.result.git_diff or "",
                    },
                )

        except httpx.TimeoutException:
            console.log("[red]Upload timed out[/red]")
            return UploadResult(success=False, detail="Upload request timed out")

        except httpx.RequestError as exc:
            console.log(f"[red]Upload network error:[/red] {exc}")
            return UploadResult(success=False, detail=str(exc))

        if response.status_code in (200, 202):
            body = response.json()
            errors_found = body.get("errors_found", 0)
            console.log(
                f"[green]Logs uploaded successfully[/green] — "
                f"{errors_found} error(s) parsed by cloud"
            )
            return UploadResult(
                success=True,
                errors_found=errors_found,
                job_id=body.get("job_id", self.job_id),
                detail=body.get("detail", "ok"),
                http_status=response.status_code,
            )

        console.log(
            f"[red]Log upload failed[/red] — "
            f"HTTP {response.status_code}: {response.text[:300]}"
        )
        return UploadResult(
            success=False,
            detail=response.text[:500],
            http_status=response.status_code,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_log_payload(self) -> str:
        """
        Assemble the full log payload, including metadata and optional
        source-file snippets so the AI has maximum context.
        """
        parts: list[str] = []

        parts.append(
            f"=== AutoVerif Simulation Log ===\n"
            f"exit_code:        {self.result.exit_code}\n"
            f"duration_seconds: {self.result.duration_seconds:.2f}\n"
            f"timed_out:        {self.result.timed_out}\n"
        )
        if self.result.error:
            parts.append(f"runner_error:     {self.result.error}\n")

        parts.append("\n=== Simulation Output ===\n")
        parts.append(self.result.sim_log or "(no output)\n")

        if self.result.file_snippets:
            parts.append("\n=== Source File Snippets ===\n")
            for snippet in self.result.file_snippets:
                parts.append(
                    f"\n--- {snippet['file']} (around line {snippet['around_line']}) ---\n"
                )
                parts.append(snippet["content"])
                parts.append("\n")

        return "".join(parts)
