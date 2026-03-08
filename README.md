# AutoVerif AI

AI-powered CI/CD framework for RTL regression testing. AutoVerif monitors your HDL repository for push events, runs simulations locally via a lightweight agent, parses error logs, calls GPT-4o to diagnose root causes and generate patches, and presents the fix for human review in a web dashboard.

---

## How It Works

```
Git push
   │
   ▼
Webhook ──► Cloud Backend (FastAPI)
                │  creates Job (queued)
                ▼
         Runner polls cloud
                │  claims Job
                ▼
         Runs simulation locally
         (verilator / make sim)
                │  uploads sim.log + git diff
                ▼
         Backend parses errors
         Background task calls GPT-4o
                │  stores DebugResult
                ▼
         Job status → analyzing
                │
                ▼
         Developer reviews in Web UI
         (root cause · explanation · diff)
                │
         ┌──────┴──────┐
       Approve        Reject
         │
         ▼
       Runner applies patch
       pushes branch autoverif/fix-*
         │
         ▼
       Backend re-queues for re-simulation
       (up to 3 iterations)
```

---

## Repository Structure

```
AutoVeri/
├── backend/                    # FastAPI cloud service
│   ├── app/
│   │   ├── main.py             # App entry point, CORS, router wiring
│   │   ├── core/
│   │   │   ├── config.py       # Pydantic-settings (env vars)
│   │   │   └── database.py     # SQLAlchemy async engine + session factory
│   │   ├── models/
│   │   │   └── models.py       # SQLAlchemy ORM models (6 tables)
│   │   ├── routers/
│   │   │   ├── auth.py         # GitHub + GitLab OAuth2, JWT issuance
│   │   │   ├── projects.py     # Project CRUD + git webhook receiver
│   │   │   ├── runners.py      # Runner registration, job polling, log upload,
│   │   │   │                   #   AI analysis background task, patch delivery
│   │   │   └── jobs.py         # Job listing, detail view, approve/reject
│   │   └── services/
│   │       ├── log_parser.py   # Regex parser for Verilator/UVM/SV error patterns
│   │       ├── debug_agent.py  # GPT-4o client; produces root_cause + unified diff patch
│   │       └── refinement_loop.py  # Multi-iteration loop skeleton (v2)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── runner/                     # Local simulation agent (pip-installable CLI)
│   ├── autoverif_runner/
│   │   ├── main.py             # CLI commands: register · start · status
│   │   ├── config.py           # Read/write ~/.autoverif/config.json
│   │   ├── poller.py           # Polling loop: claim → simulate → upload → patch → apply
│   │   ├── simulator.py        # Runs sim command, collects log + git diff + file snippets
│   │   ├── uploader.py         # POSTs sim.log + git diff to cloud
│   │   └── patcher.py          # Applies unified diff, commits, pushes new branch
│   ├── requirements.txt
│   └── setup.py
│
├── frontend/                   # React + Tailwind web dashboard
│   ├── src/
│   │   ├── App.jsx             # Router setup
│   │   ├── api/client.js       # Axios wrapper for all API calls
│   │   ├── pages/
│   │   │   ├── Login.jsx       # GitHub / GitLab OAuth entry
│   │   │   ├── Dashboard.jsx   # Project list + recent jobs overview
│   │   │   ├── JobList.jsx     # Filterable job table for a project
│   │   │   ├── JobDetail.jsx   # Full job view: errors · AI result · diff · approve/reject
│   │   │   ├── ProjectNew.jsx  # Create project form
│   │   │   └── ProjectSettings.jsx  # Edit project + runner setup instructions
│   │   └── components/
│   │       ├── Layout.jsx      # Nav shell
│   │       ├── JobStatusBadge.jsx   # Coloured status pill
│   │       ├── DiffViewer.jsx  # Syntax-highlighted unified diff
│   │       └── RunnerSetup.jsx # Copy-paste runner install instructions
│   └── package.json
│
├── docker-compose.yml          # Postgres + Redis + Backend + Frontend
└── README.md
```

---

## Database Schema

| Table | Purpose |
|---|---|
| `users` | OAuth-authenticated users (GitHub or GitLab) |
| `projects` | HDL repos with sim command, patterns, webhook secret |
| `runners` | Registered runner agents per project |
| `jobs` | One job per push event; tracks status through the pipeline |
| `job_iterations` | One record per AI fix attempt (max 3) |
| `parsed_errors` | Structured errors extracted from each sim log |
| `debug_results` | GPT-4o output: root cause, patch, confidence, approval state |

**Job status lifecycle:**
```
queued → running → logs_uploaded → analyzing → completed
                                              → failed
                                              → timeout
```

---

## Prerequisites

| Component | Requirement |
|---|---|
| Backend | Python 3.10+, PostgreSQL 15, Redis 7 |
| Frontend | Node.js 20+ |
| Runner | Python 3.10+, git, Verilator (or other simulator) |
| AI | OpenAI API key (GPT-4o) |
| Auth | GitHub OAuth App and/or GitLab OAuth App |

---

## Local Development Setup

### 1. Clone and configure environment

```bash
git clone <repo-url>
cd AutoVeri

cp backend/.env.example backend/.env
# Edit backend/.env — fill in SECRET_KEY, OAuth credentials, OPENAI_API_KEY
```

Generate a secret key:
```bash
openssl rand -hex 32
```

### 2. Start infrastructure with Docker Compose

```bash
docker-compose up -d db redis
```

This starts PostgreSQL on port `5432` and Redis on port `6379`.

### 3. Start the backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The API is available at `http://localhost:8000`.
Interactive docs: `http://localhost:8000/docs`

Tables are created automatically on first startup via SQLAlchemy.

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

The dashboard is available at `http://localhost:5173`.

### 5. Run all services via Docker Compose (optional)

```bash
docker-compose up --build
```

Services: backend on `8000`, frontend on `5173`, Postgres on `5432`, Redis on `6379`.

---

## Runner Setup (on the machine with Verilator)

### Install

```bash
cd runner
pip install -e .
```

Or directly from the repo root:
```bash
pip install -r runner/requirements.txt
```

### Register

Get your **project token** from the project settings page in the web UI (it is the `webhook_secret`).

```bash
autoverif-runner register \
  --server https://your-autoverif-instance.com \
  --token <project-token> \
  --name my-workstation
```

Config is saved to `~/.autoverif/config.json`.

### Start

```bash
autoverif-runner start --repo /path/to/your/hdl/repo
```

The runner polls the cloud every 10 seconds for new jobs.

### Status check

```bash
autoverif-runner status
```

---

## Git Webhook Configuration

After creating a project in the web UI, configure your repo to send push events:

**GitHub:**
- Settings → Webhooks → Add webhook
- Payload URL: `https://your-backend/projects/<project-id>/webhook`
- Content type: `application/json`
- Secret: the project token from project settings
- Events: `Just the push event`

**GitLab:**
- Settings → Webhooks
- URL: `https://your-backend/projects/<project-id>/webhook`
- Secret token: the project token from project settings
- Trigger: Push events

---

## End-to-End Flow

1. Developer pushes a commit with an RTL bug
2. Webhook fires → backend creates a `queued` job
3. Runner picks up the job, runs `make sim` (or configured command)
4. Runner uploads `sim.log` + `git diff` to the cloud
5. Backend parses errors (Verilator `%Error`, UVM `UVM_ERROR`, `$fatal`, etc.)
6. Background task calls GPT-4o → produces root cause, explanation, unified diff patch
7. Job status transitions to `analyzing`; developer gets an email notification
8. Developer opens the web UI → sees the AI's explanation and syntax-highlighted diff
9. **Approve** → runner applies the patch, creates branch `autoverif/fix-<sha>-<ts>`, pushes, opens PR
10. **Reject** → job closed, no changes made
11. On approval, backend re-queues the job for re-simulation (up to 3 iterations)

---

## API Overview

All routes are documented at `/docs` (Swagger UI) or `/redoc`.

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | — | Service health check |
| `GET` | `/auth/github` | — | Redirect to GitHub OAuth |
| `GET` | `/auth/github/callback` | — | GitHub OAuth callback, returns JWT |
| `GET` | `/auth/gitlab` | — | Redirect to GitLab OAuth |
| `GET` | `/auth/gitlab/callback` | — | GitLab OAuth callback, returns JWT |
| `GET` | `/auth/me` | JWT | Current user info |
| `GET` | `/projects` | JWT | List user's projects |
| `POST` | `/projects` | JWT | Create project |
| `GET` | `/projects/{id}` | JWT | Project detail |
| `PUT` | `/projects/{id}` | JWT | Update project |
| `DELETE` | `/projects/{id}` | JWT | Delete project |
| `POST` | `/projects/{id}/webhook` | HMAC | Receive git push event |
| `POST` | `/runners/register` | project token | Register a new runner |
| `GET` | `/runners/jobs` | runner token | Poll for queued jobs |
| `POST` | `/runners/jobs/{id}/claim` | runner token | Claim a job |
| `POST` | `/runners/jobs/{id}/logs` | runner token | Upload sim log (triggers AI) |
| `GET` | `/runners/jobs/{id}/status` | runner token | Poll job status |
| `GET` | `/runners/jobs/{id}/patch` | runner token | Fetch approved patch |
| `POST` | `/runners/jobs/{id}/apply` | runner token | Confirm patch applied |
| `GET` | `/jobs` | JWT | List jobs |
| `GET` | `/jobs/{id}` | JWT | Full job detail |
| `POST` | `/jobs/{id}/approve` | JWT | Approve AI fix |
| `POST` | `/jobs/{id}/reject` | JWT | Reject AI fix |

---

## Error Classification

The log parser classifies each error by filename prefix (configurable per project):

| Type | Rule | Example |
|---|---|---|
| `TB_ERROR` | File starts with `tb_` | `tb_alu_top.sv:42` |
| `RTL_ERROR` | File starts with `rtl_` or `src_` | `rtl_adder.sv:17` |
| `FATAL` | `%Fatal`, `$fatal`, `UVM_FATAL` | simulation abort |

Supported simulators: **Verilator** (`%Error`, `%Fatal`), **ModelSim/Questa** (`** Error`, `** Fatal`), **UVM** (`UVM_ERROR`, `UVM_FATAL`), and generic SystemVerilog (`$error`, `$fatal`).

---

## v1 Scope and Limitations

- Triggers on **git push** only (no manual or scheduled runs)
- Simulation runs **locally** on the registered runner machine; only logs are sent to the cloud
- **Max 3 refinement iterations** per job
- Human approval is required in the web UI before any patch is applied
- No coverage reporting in v1
- Billing is manual for the first pilot customers

Features planned for v2: test generation agent, coverage reporter, RAG knowledge base, multi-simulator support, executive dashboard.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.10+, FastAPI, SQLAlchemy (async), asyncpg |
| AI | OpenAI GPT-4o |
| Database | PostgreSQL 15 |
| Cache / Queue | Redis 7 |
| Runner CLI | Python, Click, httpx, Rich |
| Frontend | React 18, Vite, Tailwind CSS, React Router |
| Deployment | Docker / Docker Compose |
