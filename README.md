# Computer-Use Automation System (Atlas)

Backend-style computer use for legacy bank UIs: an LLM **discovers** a workflow once, saves a typed **operator** artifact, then **replays** it deterministically without the model. Human confirmation is required for irreversible steps on the live browser session.

write-up: [REPORT.md](./REPORT.md).

## Documentation map


| Document                                                                                                 | Contents                                                                         |
| -------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| [REPORT.md](./REPORT.md)                                                                                 | Design write-up (architecture, schema, errors, multi-tenant, HITL, safety, cuts) |
| [atlas-demo-bank/setup.md](./atlas-demo-bank/setup.md)                                                   | How to launch the demo bank and seeded members                                   |
| [operators/README.md](./operators/README.md)                                                             | Operator overview (schema, versioning, approval)                                 |
| [operators/schema.md](./operators/schema.md)                                                             | Artifact schema detail                                                           |
| [operators/versioning.md](./operators/versioning.md)                                                     | Version bump and rollback rules                                                  |
| [operators/confidence-and-approval.md](./operators/confidence-and-approval.md)                           | Usage counts, attempts, draft → approved                                         |
| [evidence/discovery/README.md](./evidence/discovery/README.md)                                           | Discovery flow                                                                   |
| [evidence/discovery/atlas-discovery-field-guide.md](./evidence/discovery/atlas-discovery-field-guide.md) | Discovery tests, descriptions, and run durations                                 |
| [evidence/replay/README.md](./evidence/replay/README.md)                                                 | Replay flow                                                                      |
| [evidence/replay/atlas-replay-playbook.md](./evidence/replay/atlas-replay-playbook.md)                   | Replay tests, descriptions, and run durations                                    |


## Prerequisites

- Python 3.11+ recommended
- Node.js 18+ (demo bank)
- A Groq API key (discovery only; replay does not call the LLM)

## Setup

### 1. Demo bank

See [atlas-demo-bank/setup.md](./atlas-demo-bank/setup.md).

```bash
cd atlas-demo-bank
npm install
npm run dev
```

Leave the Vite server running (default `http://127.0.0.1:5173`).

### 2. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Set `GROQ_API_KEY` in `.env`. Bank URL, member, model, and headless mode use built-in defaults (override via CLI when needed, e.g. `-u alex123`).

## Demo path

With the bank running and `.env` configured:

**Discovery (LLM once → save operator):**

```bash
python3 -m app.main -u alex123 "What is my checking account balance?"
```

**Replay (no LLM decisions, uses `operators/`):**

```bash
# After operators exist; harness forces replay-only
python3 -m tests.replay test1
```

**Full suites:**

```bash
python3 -m tests.discovery list
python3 -m tests.discovery test1          # interactive HITL for delete/open
python3 -m tests.discovery all --yes      # unattended confirms

python3 -m tests.replay list
python3 -m tests.replay all --yes         # test7 stays --no (reject)
```

Interactive HITL: agent clicks Delete/Open/Confirm → you confirm in the browser → type `resume`.

### Exceptional-state replay (assignment evidence)

```bash
python3 -m tests.replay test8   # insufficient funds — structured business outcome
```

See [evidence/replay/run_008/](./evidence/replay/run_008/) and the duration table in [evidence/replay/atlas-replay-playbook.md](./evidence/replay/atlas-replay-playbook.md).

## Repository layout

```text
app/                 Agent, artifacts, guardrails, errors, runners, CLI
atlas-demo-bank/     Local bank UI (setup.md)
operators/           Versioned DOM operators + metadata
evidence/            Discovery & replay run packs + timings
tests/               Discovery and replay harnesses
REPORT.md            Design write-up
requirements.txt     Python dependencies
.env.example         Config template
```

## Configuration


| Variable       | Role                   |
| -------------- | ---------------------- |
| `GROQ_API_KEY` | Required for discovery |


CLI supports `-u` username, `--viewport desktop|laptop|tablet|mobile`, and `--yes` / `--no` for confirmation auto-responses.

## Evidence already in the repo

- Discovery: 13 runs under `evidence/discovery/run_*` (total **5m 29s**)
- Replay: 16 runs under `evidence/replay/run_*` (total **4m 00s**, `model_turns: 0`)
- Operators: `lookup_balance`, `transfer_funds`, `open_account`, `delete_account` with per-version draft/approved metadata

Per-test workflow: [discovery field guide](./evidence/discovery/atlas-discovery-field-guide.md) and [replay playbook](./evidence/replay/atlas-replay-playbook.md).