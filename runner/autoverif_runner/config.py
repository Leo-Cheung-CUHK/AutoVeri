"""
config.py — Local runner configuration stored in ~/.autoverif/config.json.

Fields:
    server_url      Base URL of the AutoVerif cloud API (e.g. https://app.autoverif.ai)
    runner_token    Bearer token issued at registration time
    runner_id       UUID of this runner in the cloud database
    runner_name     Human-readable name chosen at registration
    project_id      UUID of the project this runner is associated with
    repo_path       Absolute path to the local git repository to simulate
    poll_interval   How often (in seconds) to poll for new jobs  (default: 10)
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".autoverif"
CONFIG_FILE = CONFIG_DIR / "config.json"

_REQUIRED_KEYS = {"server_url", "runner_token", "runner_id", "project_id"}


def _ensure_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def config_exists() -> bool:
    """Return True if a config file is present and has the minimum required keys."""
    if not CONFIG_FILE.exists():
        return False
    try:
        data = json.loads(CONFIG_FILE.read_text())
        return _REQUIRED_KEYS.issubset(data.keys())
    except (json.JSONDecodeError, OSError):
        return False


def load_config() -> dict:
    """
    Load and return the config dict.

    Raises:
        FileNotFoundError: if the config file does not exist.
        KeyError: if required keys are missing.
        ValueError: if the file is not valid JSON.
    """
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"Config file not found at {CONFIG_FILE}. "
            "Run 'autoverif-runner register' first."
        )

    try:
        data = json.loads(CONFIG_FILE.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Config file is corrupt ({CONFIG_FILE}): {exc}") from exc

    missing = _REQUIRED_KEYS - data.keys()
    if missing:
        raise KeyError(
            f"Config is missing required keys: {missing}. "
            "Run 'autoverif-runner register' again."
        )

    return data


def save_config(data: dict) -> None:
    """
    Merge *data* into the existing config (if any) and write it to disk.
    File mode is restricted to owner read/write only (0o600).
    """
    _ensure_dir()

    existing: dict = {}
    if CONFIG_FILE.exists():
        try:
            existing = json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    existing.update(data)

    CONFIG_FILE.write_text(json.dumps(existing, indent=2))
    # Restrict to owner-only so the runner token is not world-readable.
    try:
        CONFIG_FILE.chmod(0o600)
    except OSError:
        # chmod may not be supported on all platforms (e.g. Windows)
        pass


def get(key: str, default=None):
    """Convenience: load config and return a single key."""
    try:
        return load_config().get(key, default)
    except (FileNotFoundError, KeyError, ValueError):
        return default
