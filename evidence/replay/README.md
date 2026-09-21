# Replay runs

Evidence packs from Atlas replay tests live here (`run_NNN/`). Replay reuses operators saved during discovery — it does **not** fall back to discovery. Run after matching operators exist under `operators/` (including `page_not_found` / `reloading` versions for casey404 and taylor321).

## Flow

1. Start the demo bank (`atlas-demo-bank`) and ensure discovery has already produced the operators you need.
2. From the repo root, run the replay harness:

```bash
python3 -m tests.replay list
python3 -m tests.replay test1
python3 -m tests.replay all --yes
```

3. Interactive HITL (default for delete/open): agent clicks the control → you click **Yes** / **Yes, Confirm** (or **Confirm Transfer** for large transfers) in the browser → type `resume`. Pass `--yes` for unattended auto-confirm; test7 stays `--no` (reject).
4. Recommended order:

```text
discovery all  →  replay all
```

   Keep Group A order (lookup → transfer → delete → open) so savings state lines up for test4 and the mobile open case.
5. The harness sets `ATLAS_FORCE_REPLAY=1`. Artifact selection prefers a scenario-compatible version, then most-frequent among matches, with rollbacks if replay fails.
6. Successful replays update per-version usage, attempts, and approval in `operators/*/metadata.json`. See `operators/README.md`.
7. Each run writes `evidence/replay/run_NNN/`.

Case definitions: `tests/replay/cases.py`.  
Test catalog and descriptions: [atlas-replay-playbook.md](./atlas-replay-playbook.md).

## Evidence layout

```text
evidence/replay/
  README.md                     ← this file (flow)
  atlas-replay-playbook.md      ← tests and descriptions
  run_001/
    run.json
    events.jsonl
    summary.json
    transfer.md                 ← when a transfer occurred
    screenshots/
  …
```

Transfer evidence includes **Status** and **Outcome** aligned with `run.json`.

Per-test durations: [atlas-replay-playbook.md](./atlas-replay-playbook.md).
