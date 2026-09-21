# Operators

Reusable DOM-only browser workflows discovered by Atlas and replayed without the LLM.

Each capability lives under `operators/{capability}/`. Discovery writes them; replay reads them.

## Layout

```text
operators/
  README.md                      ← this overview
  schema.md                      ← artifact field reference
  versioning.md                  ← when and how versions bump
  confidence-and-approval.md     ← usage / attempts / draft → approved
  lookup_balance/
    metadata.json
    v1.json …
  transfer_funds/
  delete_account/
  open_account/
```

Capabilities today: `lookup_balance`, `transfer_funds`, `delete_account`, `open_account`.

## **Artifact schema.**
 Each `vN.json` is a typed capability: inputs, outputs, ordered DOM steps with locator strategies, success conditions, viewport hints, and optional `error_handling`. Parameters use `{{placeholders}}`; secrets are never stored. See [schema.md](./schema.md) for more detail.

## **Versioning.**
 Same steps and error set update an existing file in place; different steps or error kinds create `vN+1`. Scenario members select versions by `error_handling`. Replay prefers `most_frequent` and can roll back to older files. See [versioning.md](./versioning.md) for more detail.

## **Confidence and approval.**
 Confidence is tracked per version via `usage_counts`, `attempt_counts`, `failure_counts`, and `approval`. New versions start as `draft`; at least three successes at a ≥75% rate promote to `approved` (required for production `--yes`). Nested replays update the version that actually ran. See [confidence-and-approval.md](./confidence-and-approval.md) for more detail.

## Evidence

Successful discovery and replay runs are stored under `evidence/{discovery|replay}/run_NNN/`. Transfer evidence (`transfer.md`) includes **Status** and **Outcome** aligned with `run.json`.