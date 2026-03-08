# AutoVerif AI — Feasibility Test Projects

Clone any RTL repo here to test AutoVerif AI against a real project.
Each subfolder is git-ignored so cloned repos don't pollute the AutoVeri repo.

---

## Recommended Example Repos

These are well-known open-source RTL projects that work with Verilator and are good test candidates:

### 1. PicoRV32 — Compact RISC-V CPU (Beginner-friendly)
```bash
git clone https://github.com/YosysHQ/picorv32.git
```
- **Sim command:** `make test_verilator`
- **What it tests:** Full RISC-V core, rich testbench, many edge cases
- **TB prefix:** `testbench` / **RTL prefix:** `picorv32`

### 2. SERV — Bit-serial RISC-V CPU (Minimal)
```bash
git clone https://github.com/olofk/serv.git
```
- **Sim command:** `fusesoc run --target sim servant`
- **What it tests:** Ultra-minimal core, good for quick iteration

### 3. OpenCores UART16550 — Classic UART controller
```bash
git clone https://github.com/freecores/uart16550.git
```
- **Sim command:** `make`  (inside `bench/verilog/`)
- **What it tests:** Interface-level bugs, protocol errors

### 4. ZipCPU Blinky / Basic DSP — Beginner modules
```bash
git clone https://github.com/ZipCPU/wb2axip.git
```
- **Sim command:** `make`
- **What it tests:** AXI/Wishbone bus bridges, width mismatches

### 5. Tiny Tapeout Starter Template — Simple custom logic
```bash
git clone https://github.com/TinyTapeout/tt-verilog-template.git
```
- **Sim command:** `make -C sim`
- **What it tests:** Small combinational/sequential modules — easy to introduce bugs

---

## How to Test a Cloned Repo with AutoVerif AI

### Step 1 — Clone the repo here
```bash
cd test_projects/
git clone <repo-url>
cd <repo-name>
```

### Step 2 — Verify the sim command works manually
```bash
# Run the sim command once to confirm it works (or fails with known errors)
make sim        # or whatever the project uses
```

### Step 3 — Create a project in AutoVerif AI dashboard
Open `http://localhost:5173` → New Project:

| Field | Value |
|---|---|
| Repo URL | `https://github.com/<owner>/<repo>` |
| Sim command | e.g. `make test_verilator` |
| TB folder pattern | e.g. `testbench`, `tb_`, `bench` |
| RTL folder pattern | e.g. `rtl_`, `src/`, the repo's src prefix |

Copy the **webhook secret**.

### Step 4 — Register the runner pointing at the cloned repo
```bash
autoverif-runner register \
  --server http://localhost:8000 \
  --token <webhook-secret> \
  --name test-runner

autoverif-runner start --repo /path/to/test_projects/<repo-name>
```

### Step 5 — Introduce a bug and push
```bash
cd test_projects/<repo-name>

# Example: introduce a width mismatch
# Edit an RTL file to add a bug, then commit and push to trigger the webhook
git checkout -b test/autoverif-bug
# ... edit a file ...
git commit -am "introduce bug for AutoVerif test"
git push origin test/autoverif-bug
```

> **No remote to push to?** Use `trigger_test_job.py` from `tests/` to fire a fake webhook instead:
> ```bash
> python tests/trigger_test_job.py \
>   --api http://localhost:8000 \
>   --token <runner-token> \
>   --project-id <project-uuid>
> ```

### Step 6 — Watch the pipeline in the dashboard
Open `http://localhost:5173` → Jobs → watch the job move through:
`queued → running → analyzing → (approve/reject)`

---

## Tips for Good Test Cases

| Type | How to introduce | What to expect from AI |
|---|---|---|
| Width mismatch | Change port width in module declaration | `RTL_ERROR`, high confidence patch |
| Missing signal | Remove a wire declaration | `RTL_ERROR`, high confidence patch |
| Off-by-one | Change `<` to `<=` in a loop bound | `RTL_ERROR`, medium confidence |
| Wrong operator | `+` instead of `\|` in a bitwise op | `RTL_ERROR`, high confidence |
| Assertion failure | Change a constant in the testbench | `TB_ERROR`, AI explains mismatch |
| $fatal trigger | Add `if (x == 0) $fatal(...)` to RTL | `FATAL`, AI traces the condition |

---

## Folder Structure (after cloning)

```
test_projects/
├── README.md              ← this file
├── picorv32/              ← git-ignored
├── serv/                  ← git-ignored
└── <your-repo>/           ← git-ignored
```
