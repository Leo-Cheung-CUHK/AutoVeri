"""
main.py — CLI entry point for the AutoVerif Runner.

Commands
--------
autoverif-runner register   Register this machine as a runner for a project.
autoverif-runner start      Start the polling loop and process jobs.
autoverif-runner status     Show current config and cloud connectivity.
"""

from __future__ import annotations

import platform
import sys
from typing import Optional

import click
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import autoverif_runner.config as cfg
from autoverif_runner import __version__

console = Console()
err_console = Console(stderr=True)

_HTTP_TIMEOUT = 20


# ──────────────────────────────────────────────────────────────────────────────
# CLI group
# ──────────────────────────────────────────────────────────────────────────────

@click.group()
@click.version_option(version=__version__, prog_name="autoverif-runner")
def cli():
    """AutoVerif Runner — local simulation agent for the AutoVerif AI platform."""


# ──────────────────────────────────────────────────────────────────────────────
# register
# ──────────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option(
    "--server",
    required=True,
    help="Base URL of the AutoVerif cloud (e.g. https://app.autoverif.ai).",
)
@click.option(
    "--token",
    required=True,
    help="Project token (webhook_secret) shown in the project settings.",
)
@click.option(
    "--name",
    default=None,
    help="Human-readable name for this runner (defaults to hostname).",
)
def register(server: str, token: str, name: Optional[str]):
    """Register this machine as a runner for an AutoVerif project."""
    import socket

    runner_name = name or socket.gethostname()
    server = server.rstrip("/")

    # Detect platform
    sys_platform = platform.system().lower()
    if "linux" in sys_platform:
        detected_platform = "linux"
    elif "darwin" in sys_platform:
        detected_platform = "mac"
    else:
        console.print(
            f"[yellow]Warning: platform '{platform.system()}' is not officially supported "
            "(linux/mac only). Registering as 'linux'.[/yellow]"
        )
        detected_platform = "linux"

    console.print(
        Panel(
            f"Registering runner [bold]{runner_name}[/bold] "
            f"([dim]{detected_platform}[/dim]) with\n{server}",
            title="[cyan]AutoVerif Runner — Register[/cyan]",
        )
    )

    payload = {
        "project_token": token,
        "name": runner_name,
        "platform": detected_platform,
    }

    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            response = client.post(f"{server}/runners/register", json=payload)
    except httpx.ConnectError:
        err_console.print(f"[red]Cannot connect to {server}[/red]")
        sys.exit(1)
    except httpx.RequestError as exc:
        err_console.print(f"[red]Network error:[/red] {exc}")
        sys.exit(1)

    if response.status_code == 201:
        data = response.json()
        cfg.save_config(
            {
                "server_url": server,
                "runner_token": data["token"],
                "runner_id": data["id"],
                "runner_name": data["name"],
                "project_id": data["project_id"],
            }
        )
        console.print(
            Panel(
                f"[green]Registration successful![/green]\n\n"
                f"Runner ID:   [bold]{data['id']}[/bold]\n"
                f"Runner name: {data['name']}\n"
                f"Project ID:  {data['project_id']}\n\n"
                f"Config saved to [cyan]{cfg.CONFIG_FILE}[/cyan]\n\n"
                "Run [bold]autoverif-runner start --repo /path/to/repo[/bold] to begin.",
                title="[green]Registered[/green]",
            )
        )
    elif response.status_code == 403:
        err_console.print(
            "[red]Invalid project token.[/red] "
            "Check the token in your project settings."
        )
        sys.exit(1)
    elif response.status_code == 422:
        err_console.print(f"[red]Validation error:[/red] {response.text}")
        sys.exit(1)
    else:
        err_console.print(
            f"[red]Registration failed:[/red] HTTP {response.status_code}\n"
            f"{response.text[:400]}"
        )
        sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# start
# ──────────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option(
    "--repo",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    help="Absolute path to the local HDL repository.",
)
@click.option(
    "--interval",
    default=10,
    show_default=True,
    help="Polling interval in seconds.",
)
def start(repo: str, interval: int):
    """Start the polling loop and process simulation jobs."""
    if not cfg.config_exists():
        err_console.print(
            "[red]Runner is not registered.[/red] "
            "Run [bold]autoverif-runner register[/bold] first."
        )
        sys.exit(1)

    try:
        config = cfg.load_config()
    except (FileNotFoundError, KeyError, ValueError) as exc:
        err_console.print(f"[red]Config error:[/red] {exc}")
        sys.exit(1)

    from autoverif_runner.poller import Poller

    poller = Poller(config=config, repo_path=repo, poll_interval=interval)
    poller.run()


# ──────────────────────────────────────────────────────────────────────────────
# status
# ──────────────────────────────────────────────────────────────────────────────

@cli.command()
def status():
    """Show current runner config and cloud connectivity."""
    console.print(
        Panel(
            f"[bold cyan]AutoVerif Runner[/bold cyan] v{__version__}",
            subtitle=f"[dim]{platform.system()} {platform.release()}[/dim]",
        )
    )

    if not cfg.config_exists():
        console.print(
            "[yellow]Runner is not registered.[/yellow]\n"
            "Run [bold]autoverif-runner register --server <url> --token <token>[/bold]"
        )
        return

    try:
        config = cfg.load_config()
    except (FileNotFoundError, KeyError, ValueError) as exc:
        err_console.print(f"[red]Config error:[/red] {exc}")
        sys.exit(1)

    # Config table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="dim")
    table.add_column("Value")
    table.add_row("Config file", str(cfg.CONFIG_FILE))
    table.add_row("Server", config.get("server_url", "—"))
    table.add_row("Runner ID", config.get("runner_id", "—"))
    table.add_row("Runner name", config.get("runner_name", "—"))
    table.add_row("Project ID", config.get("project_id", "—"))
    console.print(table)
    console.print()

    # Cloud connectivity
    server = config["server_url"]
    runner_token = config["runner_token"]

    console.print("[dim]Checking cloud connectivity…[/dim]")
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            resp = client.get(
                f"{server}/runners/jobs",
                headers={"Authorization": f"Bearer {runner_token}"},
            )

        if resp.status_code == 200:
            jobs = resp.json()
            queued = [j for j in jobs if j.get("status") == "queued"]
            console.print(f"[green]Cloud reachable[/green] — {len(queued)} job(s) queued")

            if queued:
                jt = Table(title="Queued Jobs", show_lines=True)
                jt.add_column("ID", style="dim", no_wrap=True)
                jt.add_column("Branch")
                jt.add_column("Commit SHA", no_wrap=True)
                jt.add_column("Status")
                for j in queued:
                    jt.add_row(
                        j["id"][:8] + "…",
                        j.get("branch", "—"),
                        j.get("commit_sha", "—")[:12],
                        j.get("status", "—"),
                    )
                console.print(jt)

        elif resp.status_code == 401:
            console.print(
                "[red]Authentication failed[/red] — runner token may be invalid."
            )
        else:
            console.print(
                f"[yellow]Cloud returned HTTP {resp.status_code}[/yellow]: {resp.text[:200]}"
            )

    except httpx.ConnectError:
        console.print(f"[red]Cannot connect to {server}[/red]")
    except httpx.RequestError as exc:
        console.print(f"[red]Network error:[/red] {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
