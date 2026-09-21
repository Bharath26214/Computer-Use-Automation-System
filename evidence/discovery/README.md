# Discovery runs

Evidence packs from Atlas discovery tests live here (`run_NNN/`). Discovery teaches each bank workflow once, writes a reusable operator under `operators/`, and records the full run for audit.

## Flow

1. Start the demo bank (`atlas-demo-bank`) so members are available.
2. From the repo root, run the discovery harness:

```bash
python3 -m tests.discovery list
python3 -m tests.discovery test1
python3 -m tests.discovery all --yes
```

3. Interactive HITL (default for delete/open): agent clicks the control → you click **Yes** / **Yes, Confirm** in the browser → type `resume`. Pass `--yes` only for unattended auto-confirm.
4. Per scenario user, keep this order so account state stays consistent:

```text
lookup_balance  →  transfer (< $5000)  →  delete savings  →  open savings
```

5. The harness forces discovery for the case capability; nested helpers (lookup/transfer inside delete) may still replay an existing operator.
6. New operator versions are created only when steps or handled-error sets differ. See `operators/README.md` for versioning, approval, and usage chains.
7. Each successful case writes `evidence/discovery/run_NNN/` and updates `operators/{capability}/`.

Case definitions: `tests/discovery/cases.py`.  
Test catalog and descriptions: [atlas-discovery-field-guide.md](./atlas-discovery-field-guide.md).

## Evidence layout

```text
evidence/discovery/
  README.md                          ← this file (flow)
  atlas-discovery-field-guide.md     ← tests and descriptions
  run_001/
    run.json
    events.jsonl
    summary.json
    transfer.md                      ← when a transfer occurred
    screenshots/
  …
```

Transfer evidence includes **Status** and **Outcome** aligned with `run.json`.

Per-test durations: [atlas-discovery-field-guide.md](./atlas-discovery-field-guide.md).
