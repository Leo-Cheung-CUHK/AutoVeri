"""
trigger_test_job.py — Manually fires a fake webhook to create a test job,
then acts as a minimal runner: claims the job, uploads the sample sim log,
and polls until the AI analysis completes.

Usage:
    python tests/trigger_test_job.py \
        --api   http://localhost:8000 \
        --token <runner-token>        \
        --project-id <project-uuid>

Requires:
    pip install httpx rich

You can get the runner token from ~/.autoverif/config.json after running:
    autoverif-runner register --server http://localhost:8000 --token <webhook-secret>
"""

import argparse
import json
import time
from pathlib import Path

import httpx
from rich.console import Console
from rich.table import Table

console = Console()
SAMPLE_LOG = Path(__file__).parent / "sample_sim.log"
POLL_INTERVAL = 5   # seconds between status polls
MAX_WAIT = 120      # seconds to wait for AI analysis


def main():
    parser = argparse.ArgumentParser(description="AutoVerif AI end-to-end smoke test")
    parser.add_argument("--api",        required=True, help="Backend URL, e.g. http://localhost:8000")
    parser.add_argument("--token",      required=True, help="Runner token from ~/.autoverif/config.json")
    parser.add_argument("--project-id", required=True, dest="project_id", help="Project UUID")
    parser.add_argument("--jwt",        default=None,  help="User JWT (needed to fire webhook via API; "
                                                             "skip if you fire it manually via curl)")
    args = parser.parse_args()

    api  = args.api.rstrip("/")
    hdrs = {"Authorization": f"Bearer {args.token}"}

    # ── 1. Fire a fake webhook ────────────────────────────────────────────────
    if args.jwt:
        console.rule("[cyan]Step 1 — Create test job via webhook[/cyan]")
        webhook_payload = {
            "ref": "refs/heads/main",
            "after": "deadbeef1234567890abcdef1234567890abcdef",
            "commits": [{"id": "deadbeef1234567890abcdef1234567890abcdef"}],
        }
        # Note: webhook HMAC verification is skipped here — for a real test use
        # the project's webhook_secret as described in the README.
        console.print("[dim]Posting fake webhook payload to create a queued job…[/dim]")
        with httpx.Client() as c:
            r = c.post(
                f"{api}/projects/{args.project_id}/webhook",
                json=webhook_payload,
                headers={
                    # GitLab-style token header (no HMAC needed for testing if you
                    # pass the webhook_secret as x-gitlab-token)
                    "X-Gitlab-Token": args.token,
                },
            )
        if r.status_code in (200, 202):
            job_id = r.json().get("job_id")
            console.print(f"[green]Job created:[/green] {job_id}")
        else:
            console.print(f"[yellow]Webhook returned {r.status_code}: {r.text[:200]}[/yellow]")
            console.print("[dim]Continuing — will pick up any existing queued job…[/dim]")
            job_id = None
    else:
        console.rule("[cyan]Step 1 — Using existing queued job[/cyan]")
        job_id = None

    # ── 2. Poll for queued jobs ───────────────────────────────────────────────
    console.rule("[cyan]Step 2 — Claim a queued job[/cyan]")
    with httpx.Client() as c:
        r = c.get(f"{api}/runners/jobs", headers=hdrs)
    if r.status_code != 200:
        console.print(f"[red]Failed to poll jobs: {r.status_code} {r.text[:200]}[/red]")
        return

    jobs = r.json()
    if not jobs:
        console.print("[red]No queued jobs found. Create one first (push to repo or fire webhook).[/red]")
        return

    # Use the specific job from webhook, or the first queued one
    target = next((j for j in jobs if j["id"] == job_id), None) if job_id else jobs[0]
    if target is None:
        target = jobs[0]

    job_id = target["id"]
    console.print(f"[green]Found job:[/green] {job_id[:8]}…  branch={target.get('branch')}  "
                  f"commit={target.get('commit_sha', '')[:8]}")

    # ── 3. Claim the job ──────────────────────────────────────────────────────
    with httpx.Client() as c:
        r = c.post(f"{api}/runners/jobs/{job_id}/claim", headers=hdrs)
    if r.status_code not in (200, 201):
        console.print(f"[red]Claim failed: {r.status_code} {r.text[:200]}[/red]")
        return
    console.print(f"[green]Job claimed.[/green]")

    # ── 4. Upload sample sim log ──────────────────────────────────────────────
    console.rule("[cyan]Step 3 — Upload sample simulation log[/cyan]")
    if not SAMPLE_LOG.exists():
        console.print(f"[red]Sample log not found at {SAMPLE_LOG}[/red]")
        return

    log_content = SAMPLE_LOG.read_text()
    fake_git_diff = """\
diff --git a/rtl_adder.sv b/rtl_adder.sv
index abc1234..def5678 100644
--- a/rtl_adder.sv
+++ b/rtl_adder.sv
@@ -22,7 +22,7 @@ module rtl_adder(
-    assign sum = a + b;          // bug: b is 16-bit, a is 8-bit
+    assign sum = a + b[7:0];     // truncated b to match width
"""

    with httpx.Client(timeout=30) as c:
        r = c.post(
            f"{api}/runners/jobs/{job_id}/logs",
            headers=hdrs,
            files={"sim_log": ("sim.log", log_content.encode(), "text/plain")},
            data={"git_diff": fake_git_diff},
        )
    if r.status_code not in (200, 202):
        console.print(f"[red]Log upload failed: {r.status_code} {r.text[:300]}[/red]")
        return

    body = r.json()
    console.print(f"[green]Logs uploaded.[/green] Errors parsed by cloud: {body.get('errors_found', '?')}")
    console.print("[yellow]AI analysis triggered in background — polling for result…[/yellow]")

    # ── 5. Poll for AI result ─────────────────────────────────────────────────
    console.rule("[cyan]Step 4 — Wait for AI analysis[/cyan]")
    deadline = time.monotonic() + MAX_WAIT

    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL)
        with httpx.Client() as c:
            r = c.get(f"{api}/runners/jobs/{job_id}/status", headers=hdrs)
        if r.status_code != 200:
            console.print(f"[yellow]Status poll: {r.status_code}[/yellow]")
            continue

        job_status = r.json().get("status")
        console.print(f"[dim]  status: {job_status}[/dim]")

        if job_status == "analyzing":
            console.print("[green]AI analysis complete! Job is waiting for approval.[/green]")
            break
        if job_status in ("failed", "timeout", "completed"):
            console.print(f"[yellow]Job ended with status: {job_status}[/yellow]")
            break
    else:
        console.print(f"[red]Timed out after {MAX_WAIT}s waiting for AI analysis.[/red]")
        return

    # ── 6. Fetch and display the AI result ───────────────────────────────────
    console.rule("[cyan]Step 5 — AI Debug Result[/cyan]")
    with httpx.Client() as c:
        r = c.get(f"{api}/runners/jobs/{job_id}/patch", headers=hdrs)

    if r.status_code == 404:
        console.print("[yellow]No patch available (either no errors found, "
                      "or awaiting human approval in the web dashboard).[/yellow]")
        console.print(f"\nOpen the dashboard and go to:\n  Jobs → {job_id[:8]}…\n"
                      "to see the AI explanation and approve the fix.")
        return

    if r.status_code != 200:
        console.print(f"[yellow]Patch endpoint returned {r.status_code}: {r.text[:200]}[/yellow]")
        return

    result = r.json()

    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column("Key",   style="dim", min_width=14)
    t.add_column("Value")
    t.add_row("confidence",  result.get("confidence", "—"))
    t.add_row("explanation", (result.get("explanation") or "—")[:200])
    console.print(t)

    if result.get("patch"):
        console.print("\n[bold]Proposed patch:[/bold]")
        console.print(result["patch"])
    else:
        console.print("[yellow]No automated patch generated.[/yellow]")

    console.print(
        f"\n[green]Test complete.[/green] Open the web dashboard → Jobs → {job_id[:8]}… "
        "to approve or reject the fix."
    )


if __name__ == "__main__":
    main()
