# Atlas Replay Playbook

How replay runs are planned, executed, and recorded under `evidence/replay/`.

## Purpose

Replay reuses operators saved during discovery. It must **not** fall back to discovery. Each case is one CLI invocation; there is no silent account prep.

Run **after** discovery has produced matching operators (including page_not_found / reloading versions for casey404 and taylor321).

## Process

1. Confirm operators exist under `operators/` for the capabilities you will replay (see `operators/README.md` for versioning).
2. Force replay-only mode:
   ```bash
   python3 -m tests.replay list
   python3 -m tests.replay test1
   python3 -m tests.replay all
   ```
3. The harness sets `ATLAS_FORCE_REPLAY=1` and clears discovery force flags.
4. Artifact selection prefers the member’s scenario-compatible version (then most-frequent among matches), with rollbacks if replay fails.
5. Each run writes `evidence/replay/run_NNN/` (`run.json`, `events.jsonl`, `summary.json`, optional `transfer.md`).
6. Successful replays update `operators/*/metadata.json` usage / most_frequent.

## HITL notes

- **test6** pipes `yes` for large-transfer accept.
- **test7** pipes `no` for large-transfer reject (expect fail / Human did not confirm).
- **test11** (mobile delete) waits for a **real** human yes/no in the terminal — do not auto-answer.

## Cases (16)

### Group A — discovery mirror (alex123, desktop)

| ID | Capability | Query | Expected outcome | Status |
| --- | --- | --- | --- | --- |
| test1 | lookup_balance | What is my checking account balance? | Balance retrieved | success |
| test2 | transfer_funds | Transfer 100 from checking to savings | Transfer completed | success |
| test3 | delete_account | Delete my savings account | Account deleted | success |
| test4 | open_account | Open a savings account named Travel Fund for personal use | Account opened | success |

### Group B — business edges (alex123, desktop)

| ID | Capability | Query | Expected outcome | Status |
| --- | --- | --- | --- | --- |
| test5 | open_account | Open a checking account named Extra Checking for personal use | Account already exists | success |
| test6 | transfer_funds | Transfer 6000 from checking to savings | Transfer completed (HITL yes) | success |
| test7 | transfer_funds | Transfer 6000 from checking to savings | Human did not confirm (HITL no) | failure |
| test8 | transfer_funds | Transfer 99999 from checking to savings | Insufficient funds | success |

### Group C — viewport uniqueness

| ID | Viewport | Capability | Query | Expected outcome | Status |
| --- | --- | --- | --- | --- | --- |
| test9 | tablet | lookup_balance | What is my checking account balance? | Balance retrieved | success |
| test10 | tablet | transfer_funds | Transfer 100 from checking to savings | Transfer completed | success |
| test11 | mobile | delete_account | Delete my savings account | Account deleted | success |
| test12 | mobile | open_account | Open a savings account named Travel Fund for personal use | Account opened | success |

### Group D — error-handling replay

| ID | User | Scenario | Capability | Query | Expected outcome | Status |
| --- | --- | --- | --- | --- | --- | --- |
| test13 | casey404 | page_not_found | lookup_balance | What is my checking account balance? | Balance retrieved | success |
| test14 | casey404 | page_not_found | transfer_funds | Transfer 100 from checking to savings | Transfer completed | success |
| test15 | taylor321 | reloading | lookup_balance | What is my checking account balance? | Balance retrieved | success |
| test16 | taylor321 | reloading | transfer_funds | Transfer 100 from checking to savings | Transfer completed | success |

## Recommended order

```text
discovery all  →  replay all
```

Keep Group A order (lookup → transfer → delete → open) so savings state lines up for test4 / mobile open.

## Evidence layout

```text
evidence/replay/
  atlas-replay-playbook.md   ← this file
  run_001/
    run.json
    events.jsonl
    summary.json
    transfer.md              ← only when a transfer occurred
  run_002/
  …
```

`transfer.md` starts with run **Status** (`success` / `failure`) and **Outcome** (from `run.json`), then the debit/credit ledger table.

Source of truth for case definitions: `tests/replay/cases.py`.
