# AutoVerif Runner

The AutoVerif Runner is a lightweight Python CLI that runs **locally on your Linux or macOS machine**. It polls the AutoVerif AI cloud for queued simulation jobs, runs your HDL simulation command locally (e.g. via Verilator / `make sim`), uploads the logs, and — when you approve the AI-generated patch in the web dashboard — applies that patch and pushes a new branch to your repository.

---

## Architecture overview

```
AutoVerif Cloud  ←──── HTTPS ────→  autoverif-runner (your machine)
                                          │
                                          ├── polls for queued jobs
                                          ├── runs sim_command in your repo
                                          ├── uploads logs + git diff
                                          ├── waits for patch approval
                                          └── git apply + push branch
```

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | ≥ 3.10 |
| git | any recent version |
| Verilator / simulator | installed and on `PATH` |

---

## Installation

```bash
pip install autoverif-runner
```

Or install from source:

```bash
git clone https://github.com/autoverif-ai/runner.git
cd runner
pip install -e .
```

---

## Quick start

### 1. Register the runner

Grab your **project token** from the project settings page in the AutoVerif dashboard, then run:

```bash
autoverif-runner register \
  --server https://app.autoverif.ai \
  --token  <your-project-token> \
  --name   my-workstation          # optional; defaults to hostname
```

This stores credentials in `~/.autoverif/config.json` (owner-read-only, mode 0600).

### 2. Start polling

Point the runner at the local clone of your HDL repository:

```bash
autoverif-runner start --repo /path/to/your/hdl-repo
```

The runner will print a live log as it polls, claims jobs, and runs simulations.

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--repo` | *(required)* | Absolute path to the git repository |
| `--interval` | `10` | Poll interval in seconds |

### 3. Check status

```bash
autoverif-runner status
```

Prints the current config and shows any queued jobs in the cloud.

---

## Workflow

1. A webhook from GitHub/GitLab triggers AutoVerif when you push a commit.
2. AutoVerif creates a **Job** (status `queued`).
3. Your runner polls every `--interval` seconds and **claims** the job.
4. The runner runs `sim_command` (configured in the project settings) inside your repo.
5. Logs + git diff are **uploaded** to the cloud.
6. AutoVerif AI analyses the logs and proposes a patch.
7. You **review and approve** (or reject) the patch in the web dashboard.
8. The runner detects the approval, applies the patch with `git apply`, commits, and pushes a new branch (`autoverif/fix-<sha>-<ts>`).
9. The job is re-queued for a verification re-simulation run.

---

## Configuration file

`~/.autoverif/config.json` is created automatically by `register`. You can also edit it manually:

```json
{
  "server_url":    "https://app.autoverif.ai",
  "runner_token":  "<runner-bearer-token>",
  "runner_id":     "<uuid>",
  "runner_name":   "my-workstation",
  "project_id":    "<uuid>",
  "poll_interval": 10
}
```

---

## Troubleshooting

### "Runner is not registered"
Run `autoverif-runner register` first.

### "Invalid project token"
The `--token` value must be the **webhook_secret** shown in your project settings, not your personal API key.

### Simulation times out
Increase the `timeout_minutes` in the project settings on the cloud dashboard.

### `git apply` fails
The AI patch may not apply cleanly if your local working tree has uncommitted changes. Ensure your repo is clean before starting the runner:
```bash
git status   # should show nothing modified
```

### Logs
All runner activity is printed to stdout with UTC timestamps. Redirect to a file for persistence:
```bash
autoverif-runner start --repo /path/to/repo 2>&1 | tee runner.log
```

---

## Security

- Runner tokens are stored with file permissions `0600` (owner read/write only).
- The runner never exposes your runner token in log output.
- All communication with the cloud uses HTTPS.
- Patches are applied only after explicit human approval in the web UI.

---

## License

MIT © AutoVerif AI
