# Atlas Replay Playbook

Catalog of replay tests: HITL, groups, case descriptions, and wall-clock duration from each run’s `summary.json`. For how to run the suite, see [README.md](./README.md).

Sixteen cases in four groups. No silent prep — each case is one CLI invocation. All runs report `model_turns: 0`. **Suite total: 4m 00s.**

## HITL

| Capability | Confirmation |
| --- | --- |
| `lookup_balance` | None |
| `transfer_funds` under $5000 | None — agent confirms the transfer |
| `transfer_funds` over $5000 | App handoff: Confirm Transfer on review (accept or reject) |
| `delete_account` | App handoff: Transfer funds Yes/No if balance &gt; 0, then Yes, Confirm on delete |
| `open_account` | App handoff: Yes, Confirm after Open (skipped when account already exists) |

## Group A — discovery mirror (alex123, desktop)

| ID | Run | Capability | Description | Expected | Duration |
| --- | --- | --- | --- | --- | ---: |
| test1 | run_001 | lookup_balance | Replay checking balance lookup | Balance retrieved | 4s |
| test2 | run_002 | transfer_funds | Replay $100 checking → savings (under $5000) | Transfer completed | 18s |
| test3 | run_003 | delete_account | Replay delete savings (funds move first if needed) | Account deleted | 31s |
| test4 | run_004 | open_account | Replay re-open savings named Travel Fund | Account opened | 10s |

## Group B — business edges (alex123, desktop)

| ID | Run | Capability | Description | Expected | Duration |
| --- | --- | --- | --- | --- | ---: |
| test5 | run_005 | open_account | Open checking when checking already exists — no Open click | Account already exists | 3s |
| test6 | run_006 | transfer_funds | Transfer $6000 checking → savings with HITL accept | Transfer completed | 19s |
| test7 | run_007 | transfer_funds | Same large transfer with HITL reject (`--no`) | Human did not confirm | 14s |
| test8 | run_008 | transfer_funds | Transfer $99999 — blocked for insufficient funds | Insufficient funds | 5s |

## Group C — viewport uniqueness

| ID | Run | Viewport | Capability | Description | Expected | Duration |
| --- | --- | --- | --- | --- | --- | ---: |
| test9 | run_009 | tablet | lookup_balance | Replay lookup on tablet | Balance retrieved | 4s |
| test10 | run_010 | tablet | transfer_funds | Replay small transfer on tablet | Transfer completed | 19s |
| test11 | run_011 | mobile | delete_account | Replay delete savings on mobile | Account deleted | 36s |
| test12 | run_012 | mobile | open_account | Replay open savings on mobile (after mobile delete) | Account opened | 15s |

## Group D — error-handling replay

| ID | Run | User | Scenario | Capability | Description | Expected | Duration |
| --- | --- | --- | --- | --- | --- | --- | ---: |
| test13 | run_013 | casey404 | page_not_found | lookup_balance | Replay lookup after 404 recovery operator | Balance retrieved | 4s |
| test14 | run_014 | casey404 | page_not_found | transfer_funds | Replay small transfer after 404 recovery operator | Transfer completed | 20s |
| test15 | run_015 | taylor321 | reloading | lookup_balance | Replay lookup after reloading operator | Balance retrieved | 11s |
| test16 | run_016 | taylor321 | reloading | transfer_funds | Replay small transfer after reloading operator | Transfer completed | 27s |

Durations are `ended_at − started_at` from `summary.json` (includes HITL wait time). Exceptional-state examples: run_005 (already exists), run_007 (HITL reject), run_008 (insufficient funds).

Source of truth: `tests/replay/cases.py`.
