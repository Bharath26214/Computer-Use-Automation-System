# Atlas Discovery Field Guide

How discovery runs are planned, executed, and recorded under `evidence/discovery/`.

## Purpose

Discovery teaches the agent a bank workflow **once**, captures a reusable DOM-only operator under `operators/`, and writes a full evidence pack for that run (`run.json`, `events.jsonl`, `summary.json`, plus `transfer.md` when money moves).

Run discovery **before** replay. Replay depends on the operators saved here.

## Process

1. Start the demo bank (`atlas-demo-bank`) and ensure members are seeded.
2. Force discovery for the capability under test:
   ```bash
   python3 -m tests.discovery list
   python3 -m tests.discovery test1
   python3 -m tests.discovery all
   ```
3. The harness sets `ATLAS_FORCE_DISCOVERY=1` and scopes rediscovery with `ATLAS_FORCE_DISCOVERY_ARTIFACT`.
4. Nested helpers (e.g. lookup inside delete) may still **replay** an already-saved operator.
5. Each successful discovery writes:
   - `evidence/discovery/run_NNN/` — run evidence
   - `operators/{capability}/vN.json` — new version only when steps or handled-error kinds differ
6. Scenario users stamp `error_handling` on the operator (blank `{}` for happy-path alex123).
7. Operator layout and versioning rules: `operators/README.md`.

## Sequence rule

Per scenario user, keep this order so account state stays consistent:

```text
lookup_balance  →  transfer (< $5000)  →  delete savings  →  open savings
```

## Cases (13)

| ID | User | Scenario | Capability | Query | Status |
| --- | --- | --- | --- | --- | --- |
| test1 | alex123 | normal | lookup_balance | What is my checking account balance? | success |
| test2 | alex123 | normal | transfer_funds | Transfer 100 from checking to savings | success |
| test3 | alex123 | normal | delete_account | Delete my savings account | success |
| test4 | alex123 | normal | open_account | Open a savings account named Travel Fund for personal use | success |
| test5 | casey404 | page_not_found | lookup_balance | What is my checking account balance? | success |
| test6 | casey404 | page_not_found | transfer_funds | Transfer 100 from checking to savings | success |
| test7 | casey404 | page_not_found | delete_account | Delete my savings account | success |
| test8 | casey404 | page_not_found | open_account | Open a savings account named Travel Fund for personal use | success |
| test9 | taylor321 | reloading | lookup_balance | What is my checking account balance? | success |
| test10 | taylor321 | reloading | transfer_funds | Transfer 100 from checking to savings | success |
| test11 | taylor321 | reloading | delete_account | Delete my savings account | success |
| test12 | taylor321 | reloading | open_account | Open a savings account named Travel Fund for personal use | success |
| test13 | blake000 | hard_failure | lookup_balance | What is my checking account balance? | failure |

## Members

| Username | Login scenario |
| --- | --- |
| alex123 | normal |
| casey404 | page_not_found (recover after reload) |
| taylor321 | reloading |
| blake000 | hard_failure (cannot recover) |

## Evidence layout

```text
evidence/discovery/
  atlas-discovery-field-guide.md   ← this file
  run_001/
    run.json
    events.jsonl
    summary.json
    transfer.md                    ← only when a transfer occurred
  run_002/
  …
```

`transfer.md` starts with run **Status** (`success` / `failure`) and **Outcome** (from `run.json`), then the debit/credit ledger table.

Viewport for all discovery cases: **desktop**.

Source of truth for case definitions: `tests/discovery/cases.py`.
