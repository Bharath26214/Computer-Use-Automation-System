# Versioning

Operators are versioned files under `operators/{capability}/vN.json`. Older versions are kept so replay can roll back when a preferred version fails or when a member needs a different error-handling path.

## When a new version is created

Discovery calls `save_artifact` with these rules:

1. **Same steps + same error set** → update the existing `vN.json` in place (merge query signatures and `viewports_validated`). No version bump.
2. **Different steps or different handled-error kinds** → write the next free `v{N+1}.json` and leave older files in place.

Members are **not** versions. Running as `alex123` versus `casey404` alone does not create a new file; a new version appears only when the durable step list or the recorded `error_handling` set differs.

## Typical Atlas Bank split

| Version | `error_handling` | Usually discovered with |
| --- | --- | --- |
| v1 | `{}` | `alex123` (normal login) |
| v2 | `page_not_found` | `casey404` |
| v3 | `reloading` | `taylor321` |

`blake000` (`hard_failure`) is expected to fail discovery and does not produce a reusable operator.

## Scenario matching at replay

- Happy-path members only use versions with blank `error_handling`.
- Scenario members only use a version that already recorded their error kind.
- If no match exists, discovery creates a new version for that error set.

## Preference and rollback

`metadata.json` pins:

- `most_frequent` — try-first version (highest `usage_counts`; ties break to higher `N`)
- `latest` — kept aligned with the preferred pin after usage updates

Replay order for a capability: scenario-compatible version preferred by `most_frequent`, then other matching versions by usage, then higher version number. If the preferred version fails on this viewport or checkpoint, older compatible operators are tried before falling back to discovery (unless discovery is disabled).

## Composition

Higher-level flows may nest other operators. For example `delete_account` prefers an existing `lookup_balance` and, when needed, `transfer_funds` before rediscovering those steps. Each nested replay updates counters on **that** version.
