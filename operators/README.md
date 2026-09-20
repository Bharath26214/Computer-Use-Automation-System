# Operators

Reusable DOM-only browser workflows discovered by Atlas and replayed without the LLM.

Each capability lives under `operators/{capability}/`. Discovery writes them; replay reads them.

## Layout

```text
operators/
  README.md                 ← this file
  lookup_balance/
    metadata.json           ← which version to prefer
    v1.json                 ← happy-path (blank error_handling)
    v2.json                 ← page_not_found recovery
    v3.json                 ← reloading recovery
  transfer_funds/
  delete_account/
  open_account/
```

Capabilities today: `lookup_balance`, `transfer_funds`, `delete_account`, `open_account`.

## Version files (`vN.json`)

A version is a frozen operator: ordered DOM steps, inputs/outputs, viewport hints, and optional `error_handling`.

| Field | Meaning |
| --- | --- |
| `artifact_id` | Capability name (folder name) |
| `version` | Integer `N` matching `vN.json` |
| `locator_policy` | Always `dom_only` for replay |
| `viewport` / `viewports_validated` | Screen sizes this operator has run on |
| `error_handling` | `{}` for normal; otherwise recorded recoveries (`page_not_found`, `reloading`, …) |
| `steps` | Ordered click / fill / read actions with role/label/test-id locators |
| `inputs` | Dynamic params (`member_id`, amounts, account names) — not baked into the file |
| `query_signatures` | Normalized goals that map to this operator |

Members are inputs, not versions. Running as `alex123` vs `casey404` does not create a new file by itself.

## When a new version is created

Discovery calls `save_artifact`. Rules:

1. **Same steps + same error set** → update the existing `vN.json` in place (merge query signatures / viewports). No bump.
2. **Different steps or different handled-error kinds** → write the next free `v{N+1}.json` and keep older files.

Typical Atlas Bank split:

| Version | `error_handling` | Discovered with |
| --- | --- | --- |
| v1 | `{}` | `alex123` (normal) |
| v2 | `page_not_found` | `casey404` |
| v3 | `reloading` | `taylor321` |

`blake000` (`hard_failure`) is expected to fail discovery and does not produce a reusable operator.

## Metadata (`metadata.json`)

```json
{
  "artifact_id": "lookup_balance",
  "latest": 1,
  "most_frequent": 1,
  "usage_counts": { "1": 10, "2": 3, "3": 2 }
}
```

| Field | Meaning |
| --- | --- |
| `usage_counts` | Successful replay hits per version |
| `most_frequent` | Preferred try-first version (highest usage; ties → higher `N`) |
| `latest` | Kept in sync with the preferred pin after usage updates |

Replay order: scenario-compatible version preferred by `most_frequent`, then other matching versions; roll back to older operators if replay fails.

## Scenario matching

- Happy-path members (`alex123`, …) only replay versions with blank `error_handling`.
- Scenario members only replay a version that already recorded their error kind.
- If no match exists, discovery creates a new version for that error set.

## Evidence link

Successful discovery/replay runs land under `evidence/{discovery|replay}/run_NNN/`. Transfer evidence (`transfer.md`) includes a top-level **Status** (`success` / `failure`) and **Outcome** aligned with `run.json`.
