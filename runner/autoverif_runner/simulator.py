"""
simulator.py — Runs the user-defined sim command and collects artefacts.

Usage::

    from autoverif_runner.simulator import Simulator, SimulationResult

    sim = Simulator(repo_path="/path/to/repo", sim_command="make sim", timeout_minutes=30)
    result = sim.run(last_passing_sha=None)
    print(result.exit_code, result.duration_seconds)
"""

from __future__ import annotations

import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console(stderr=True)

# How many lines of context to collect around an error mention in a source file.
_CONTEXT_LINES = 20

# Regex to find "file.sv:123" style references in log output.
_FILE_REF_RE = re.compile(
    r'(?P<path>[\w./\\-]+\.(?:sv|v|vh|svh|vhd|vhdl|c|cpp|h))'
    r':(?P<line>\d+)',
    re.IGNORECASE,
)


@dataclass
class SimulationResult:
    sim_log: str
    git_diff: str
    exit_code: int
    duration_seconds: float
    timed_out: bool = False
    error: Optional[str] = None
    # Snippets: list of {"file": str, "around_line": int, "content": str}
    file_snippets: list[dict] = field(default_factory=list)


class Simulator:
    """
    Runs the configured sim command inside *repo_path* and collects:
    - Combined stdout + stderr log
    - `git diff` relative to *last_passing_sha* (or HEAD~1 as fallback)
    - File snippets around any source-file line references found in the log
    """

    def __init__(
        self,
        repo_path: str,
        sim_command: str,
        timeout_minutes: int = 30,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.sim_command = sim_command
        self.timeout_minutes = timeout_minutes

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, last_passing_sha: Optional[str] = None) -> SimulationResult:
        """
        Execute the simulation and return a :class:`SimulationResult`.

        Args:
            last_passing_sha: If provided, `git diff <sha> HEAD` is used.
                              Otherwise falls back to `git diff HEAD~1 HEAD`.
        """
        self._validate_repo()

        console.log(f"[cyan]Starting simulation:[/cyan] {self.sim_command}")
        console.log(f"[cyan]Working directory:[/cyan]  {self.repo_path}")
        console.log(f"[cyan]Timeout:[/cyan]            {self.timeout_minutes} min")

        sim_log, exit_code, duration, timed_out = self._run_command()
        git_diff = self._collect_git_diff(last_passing_sha)
        snippets = self._collect_file_snippets(sim_log)

        status_label = "[green]passed[/green]" if exit_code == 0 else "[red]failed[/red]"
        console.log(
            f"[cyan]Simulation finished[/cyan] — exit_code={exit_code} "
            f"({status_label}), duration={duration:.1f}s"
        )

        return SimulationResult(
            sim_log=sim_log,
            git_diff=git_diff,
            exit_code=exit_code,
            duration_seconds=duration,
            timed_out=timed_out,
            file_snippets=snippets,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_repo(self) -> None:
        if not self.repo_path.is_dir():
            raise NotADirectoryError(f"repo_path does not exist: {self.repo_path}")
        git_dir = self.repo_path / ".git"
        if not git_dir.exists():
            raise ValueError(
                f"{self.repo_path} is not a git repository (no .git directory found)."
            )

    def _run_command(self) -> tuple[str, int, float, bool]:
        """
        Run self.sim_command with a timeout.

        Returns (combined_log, exit_code, duration_seconds, timed_out).
        """
        try:
            args = shlex.split(self.sim_command)
        except ValueError:
            # Fall back to shell=True for complex commands
            args = self.sim_command

        use_shell = isinstance(args, str)
        timeout_secs = self.timeout_minutes * 60
        start = time.monotonic()
        timed_out = False

        try:
            proc = subprocess.run(
                args,
                cwd=str(self.repo_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout_secs,
                shell=use_shell,
            )
            exit_code = proc.returncode
            raw_output = proc.stdout

        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = -1
            raw_output = (exc.output or b"") + (
                f"\n\n[AutoVerif] Simulation timed out after {self.timeout_minutes} minutes.\n"
            ).encode()

        except FileNotFoundError:
            elapsed = time.monotonic() - start
            cmd_name = args[0] if isinstance(args, list) else self.sim_command.split()[0]
            return (
                f"[AutoVerif] Command not found: '{cmd_name}'. "
                "Is it installed and on PATH?\n",
                127,
                elapsed,
                False,
            )

        except PermissionError:
            elapsed = time.monotonic() - start
            return (
                f"[AutoVerif] Permission denied running: {self.sim_command}\n",
                126,
                elapsed,
                False,
            )

        duration = time.monotonic() - start
        combined_log = raw_output.decode("utf-8", errors="replace")
        return combined_log, exit_code, duration, timed_out

    def _collect_git_diff(self, last_passing_sha: Optional[str]) -> str:
        """Return git diff output as a string; returns empty string on failure."""
        if last_passing_sha:
            diff_range = [last_passing_sha, "HEAD"]
        else:
            diff_range = ["HEAD~1", "HEAD"]

        try:
            result = subprocess.run(
                ["git", "diff", *diff_range],
                cwd=str(self.repo_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
            diff = result.stdout.decode("utf-8", errors="replace")
            if result.returncode != 0 and not diff:
                # HEAD~1 may fail on a repo with a single commit; try staged/unstaged diff.
                result2 = subprocess.run(
                    ["git", "diff"],
                    cwd=str(self.repo_path),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=30,
                )
                diff = result2.stdout.decode("utf-8", errors="replace")
            return diff
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            console.log(f"[yellow]Warning: could not collect git diff: {exc}[/yellow]")
            return ""

    def _collect_file_snippets(self, log: str) -> list[dict]:
        """
        Scan the log for file:line references and collect ±CONTEXT_LINES lines
        of source context. Skips files outside the repo root or that don't exist.
        """
        seen: set[tuple[str, int]] = set()
        snippets: list[dict] = []

        for match in _FILE_REF_RE.finditer(log):
            raw_path = match.group("path")
            line_no = int(match.group("line"))
            key = (raw_path, line_no)
            if key in seen:
                continue
            seen.add(key)

            # Resolve relative to repo root
            candidate = (self.repo_path / raw_path).resolve()
            if not str(candidate).startswith(str(self.repo_path)):
                continue  # Security: do not read outside repo
            if not candidate.is_file():
                continue

            try:
                lines = candidate.read_text(errors="replace").splitlines()
            except OSError:
                continue

            start_idx = max(0, line_no - 1 - _CONTEXT_LINES)
            end_idx = min(len(lines), line_no + _CONTEXT_LINES)
            snippet_lines = lines[start_idx:end_idx]
            numbered = "\n".join(
                f"{start_idx + i + 1:5d}  {ln}"
                for i, ln in enumerate(snippet_lines)
            )
            snippets.append(
                {
                    "file": str(candidate.relative_to(self.repo_path)),
                    "around_line": line_no,
                    "content": numbered,
                }
            )

            if len(snippets) >= 20:
                break  # Avoid flooding the log payload

        return snippets
