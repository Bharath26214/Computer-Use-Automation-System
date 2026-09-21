# Confidence and approval

Confidence is tracked **per version**, not for the capability as a whole. Counters and approval live in `operators/{capability}/metadata.json` alongside the preference pins (`most_frequent`, `latest`).

## Metadata fields

| Field | Meaning |
| --- | --- |
| `usage_counts` | Successful replays of that version |
| `attempt_counts` | Total replay tries (success + failure) |
| `failure_counts` | Failed replay tries |
| `approval` | `draft` or `approved` for that version |
| `most_frequent` | Preferred try-first version (highest usage; ties → higher `N`) |
| `latest` | Kept in sync with the preferred pin after usage updates |

Example:

```json
{
  "artifact_id": "lookup_balance",
  "latest": 1,
  "most_frequent": 1,
  "usage_counts": { "1": 10, "2": 3 },
  "attempt_counts": { "1": 12, "2": 4 },
  "failure_counts": { "1": 2, "2": 1 },
  "approval": { "1": "approved", "2": "draft" }
}
```

Success rate for a version is `usage_counts[v] / attempt_counts[v]` when attempts &gt; 0.

## Lifecycle

| Stage | Meaning |
| --- | --- |
| `draft` | Newly written or not yet proven. Replay for validation is allowed. Production auto-confirm (`--yes`) is blocked. |
| `approved` | At least **3** successes and **≥ 75%** success rate. Eligible for production invocation with `--yes`. |

New versions always start as `draft` with zero counters. After each replay of a specific version:

- success → increment `usage_counts` and `attempt_counts`
- failure → increment `failure_counts` and `attempt_counts`

Approval is recomputed from those counters. If the rate later falls below 75%, the version returns to `draft`. Interactive replay (human confirms in the browser) remains available for drafts while they accumulate confidence. The discovery/replay test harness may set `ATLAS_ALLOW_DRAFT_YES=1` so unattended validation can still auto-confirm drafts.

## Usage chain

When one operator invokes another (e.g. delete → lookup → transfer), counters update on the **version that actually replayed**, so confidence stays accurate along the chain.

| Capability | Depends on | Role |
| --- | --- | --- |
| `lookup_balance` | — | Leaf: read a product balance |
| `transfer_funds` | — | Leaf: move funds between products |
| `open_account` | — | Leaf: open Checking or Savings |
| `delete_account` | `lookup_balance`, often `transfer_funds` | Orchestrator: balance → optional transfer → delete |
