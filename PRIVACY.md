# AutoVerif AI — Privacy & Data Handling

---

## What Leaves Your Machine

The AutoVerif runner executes your simulation locally. The following data is sent to the AutoVerif cloud backend for AI analysis:

| Data | Contains source code? | Sensitivity |
|---|---|---|
| `sim.log` (stdout + stderr from your sim command) | Sometimes — error messages may echo signal names and file paths | Medium |
| `git diff` (changed lines since last commit) | **Yes** — actual RTL source lines | High |
| `±20 lines of context` around each error location | **Yes** — raw RTL source | High |

> **Note:** The current v1 README states "your source code never leaves your machine." This is inaccurate. The git diff and surrounding context do contain source code. This document supersedes that claim and will be corrected in a future README update.

Your source code is **never cloned, pulled, or stored in full** by AutoVerif. Only the diff of the most recent push and the simulation log are transmitted.

---

## Known Privacy Risks

### 1. Git diff contains proprietary RTL
The git diff sent to the backend includes the actual changed lines of your Verilog/SystemVerilog. For teams working on proprietary chip designs, this may constitute disclosure of trade secrets.

### 2. Log files may leak signal and module names
Verilator and other simulators echo file paths, module names, and signal names in error output. These appear in `sim.log` even in log-only mode.

### 3. No contractual data protection in v1
The current v1 release has no formal Data Processing Agreement (DPA). Enterprise customers — particularly in semiconductor, defence, and automotive — will require one before signing.

---

## Planned Privacy Improvements

### v1.1 — Immediate Fixes

| # | Action | Detail |
|---|--------|--------|
| 1 | Fix inaccurate README claim | Remove "source code never leaves your machine"; replace with accurate description |
| 2 | Add data retention policy | Simulation logs and diffs deleted from AutoVerif servers after job completion (target: 24 hours) |
| 3 | Add Log-Only mode (default ON) | Send `sim.log` only; do not send git diff or source context. Opt-in "Enhanced mode" sends diff with explicit user consent and warning |
| 4 | Add privacy policy page | Hosted at `autoverif.ai/privacy`; covers data collected, retention, third-party sharing (OpenAI API) |

**Log-Only mode behaviour:**
- AI receives: error type, file name, line number, error message text
- AI does NOT receive: changed source lines, surrounding RTL context
- Patch quality is reduced — AI produces best-effort suggestions rather than precise unified diffs
- Recommended default for all teams handling proprietary IP

**Enhanced mode behaviour (opt-in):**
- AI receives: full git diff + ±20 lines context per error
- Produces higher-quality, directly applicable patches
- Requires user to acknowledge that changed source lines will be transmitted
- Subject to AutoVerif zero-retention DPA

### v2 — On-Premise Backend Option

Package the full AutoVerif backend (API, database, job queue) as a self-hosted Docker Compose bundle. The customer runs everything inside their own network.

- Customer brings their own OpenAI API key (or uses a private Azure OpenAI endpoint)
- Zero data leaves the customer's infrastructure
- AutoVerif provides updates as versioned Docker images
- Target: enterprise accounts at semiconductor companies ($10K+/yr tier)

### v3 — Local AI Mode

Run inference entirely on the user's machine using a locally hosted model (e.g., Ollama + a fine-tuned RTL-specific model).

- No external API calls of any kind
- Works fully air-gapped
- Requires capable local hardware (GPU recommended)
- Model quality dependent on fine-tuning investment

---

## Third-Party Data Exposure

| Third Party | What they receive | Mitigation |
|---|---|---|
| OpenAI (GPT-4o API) | Parsed errors + git diff (Enhanced mode) | OpenAI API data is not used for training by default under the API terms. Zero-retention DPA available. |
| AutoVerif cloud (Railway / Render) | Sim logs, diffs, job metadata | Covered by AutoVerif data retention policy. Not shared with any other party. |

---

## Recommended Approach by Team Type

| Team Type | Recommended Mode | Notes |
|---|---|---|
| Open-source project | Enhanced mode (opt-in) | No proprietary IP concern |
| Startup (pre-tapeout) | Log-Only mode | Protects unreleased design |
| SME semiconductor | Log-Only + DPA | Require signed DPA before enabling Enhanced mode |
| Large enterprise / defence | On-premise backend (v2) | Data never leaves their network |

---

## Sales Guidance

The privacy posture is a **competitive advantage**, not a liability — if communicated correctly.

**Recommended pitch:**

> "AutoVerif is designed for hardware IP. By default, your source code never leaves your network — we analyse the simulation error log only, the same text you'd paste into a Slack message. For teams that want higher patch precision, Enhanced mode sends only the changed lines under a zero-retention agreement. For large enterprises, we offer a fully on-premise deployment."

This framing passes legal review at semiconductor companies. Avoid the v1 claim that "source code never leaves your machine" until Log-Only mode is the enforced default.

---

## Open Questions (to resolve before v2 launch)

- [ ] Engage a lawyer to draft the DPA template
- [ ] Confirm OpenAI API zero-retention terms apply to our usage tier
- [ ] Decide default retention window (24h vs 7 days vs job-expiry)
- [ ] Determine whether `sim.log` alone is sufficient for SOC2 compliance scope
- [ ] Evaluate Azure OpenAI as an alternative API endpoint (stronger enterprise data residency guarantees)
