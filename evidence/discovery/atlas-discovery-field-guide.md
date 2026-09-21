# Atlas Discovery Field Guide

Catalog of discovery tests: members, HITL, case descriptions, and wall-clock duration from each run’s `summary.json`. For how to run the suite, see [README.md](./README.md).

Thirteen desktop cases: four users × lookup → transfer → delete → open, plus one hard-failure lookup. **Suite total: 5m 29s.**

## Members

| Username | Login scenario |
| --- | --- |
| alex123 | Normal dashboard after sign-in |
| casey404 | Page not found, then recover after reload |
| taylor321 | Reloading gate, then dashboard |
| blake000 | Hard failure (cannot recover) |

## HITL

| Capability | Confirmation |
| --- | --- |
| `lookup_balance` | None |
| `transfer_funds` under $5000 | None — agent confirms the transfer |
| `delete_account` | App handoff: Transfer funds Yes/No if balance &gt; 0, then Yes, Confirm on delete (two resumes when funds must move first) |
| `open_account` | App handoff: Yes, Confirm after Open |
| Hard failure | None |

## Cases

| ID | Run | User | Scenario | Capability | Description | Expected | Duration |
| --- | --- | --- | --- | --- | --- | --- | ---: |
| test1 | run_001 | alex123 | normal | lookup_balance | Read checking balance on a clean login | Balance retrieved | 13s |
| test2 | run_002 | alex123 | normal | transfer_funds | Transfer $100 checking → savings (under $5000) | Transfer completed | 35s |
| test3 | run_003 | alex123 | normal | delete_account | Delete savings (transfer remaining funds if needed, then confirm delete) | Account deleted | 46s |
| test4 | run_004 | alex123 | normal | open_account | Re-open savings named Travel Fund (personal use) | Account opened | 15s |
| test5 | run_005 | casey404 | page_not_found | lookup_balance | Same lookup after 404 recovery | Balance retrieved | 7s |
| test6 | run_006 | casey404 | page_not_found | transfer_funds | Same small transfer after 404 recovery | Transfer completed | 32s |
| test7 | run_007 | casey404 | page_not_found | delete_account | Same delete after 404 recovery | Account deleted | 41s |
| test8 | run_008 | casey404 | page_not_found | open_account | Same open after 404 recovery | Account opened | 14s |
| test9 | run_009 | taylor321 | reloading | lookup_balance | Same lookup after reloading gate | Balance retrieved | 15s |
| test10 | run_010 | taylor321 | reloading | transfer_funds | Same small transfer after reloading gate | Transfer completed | 27s |
| test11 | run_011 | taylor321 | reloading | delete_account | Same delete after reloading gate | Account deleted | 1m 01s |
| test12 | run_012 | taylor321 | reloading | open_account | Same open after reloading gate | Account opened | 17s |
| test13 | run_013 | blake000 | hard_failure | lookup_balance | Lookup against an unrecoverable login failure | Fail (hard failure) | 6s |

Scenario users stamp `error_handling` on the operator they create (`{}` for alex123; `page_not_found` / `reloading` for the others). blake000 does not produce a reusable operator. Durations are `ended_at − started_at` from `summary.json` (includes HITL wait time).

Source of truth: [tests/discovery/cases.py](../../tests/discovery/cases.py).
