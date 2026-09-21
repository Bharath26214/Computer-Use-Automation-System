# Artifact schema

Each operator file `operators/{capability}/vN.json` is a typed, reviewable capability an agent can invoke. It describes what the flow needs, what it returns, how controls are found, and how success is judged—not a raw model transcript.

## Top-level fields


| Field                   | Type     | Purpose                                                                     |
| ----------------------- | -------- | --------------------------------------------------------------------------- |
| `artifact_id`           | string   | Capability name; matches the folder (`lookup_balance`, `transfer_funds`, …) |
| `version`               | integer  | `N` in `vN.json`                                                            |
| `title` / `description` | string   | Human-readable contract summary                                             |
| `locator_policy`        | string   | Perception/action backend; always `dom_only` in this project                |
| `viewport`              | object   | Profile and size used when the operator was captured                        |
| `viewports_validated`   | string[] | Profiles where this DOM flow has succeeded (e.g. desktop, tablet, mobile)   |
| `error_handling`        | object   | `{}` for happy path; otherwise keys such as `page_not_found` or `reloading` |
| `inputs`                | object   | Typed parameters supplied per invocation                                    |
| `outputs`               | object   | Typed results the caller receives                                           |
| `steps`                 | array    | Ordered actions with locators                                               |
| `success_conditions`    | array    | Checkpoints that must hold for success                                      |
| `query_signatures`      | string[] | Normalized goals that map to this operator                                  |


Members and amounts are **inputs**, not separate versions. Secrets (passwords, tokens, raw PII) must not appear in the file.

## Inputs

Each input is a small schema object, for example:

```json
"member_id": {
  "type": "string",
  "required": true,
  "description": "Opaque member login id…",
  "pattern": "^[A-Za-z]+\\d{3}$",
  "example": "alex123"
}
```

Common inputs by capability:


| Capability       | Typical inputs                                                       |
| ---------------- | -------------------------------------------------------------------- |
| `lookup_balance` | `member_id`, `account` (Checking                                     |
| `transfer_funds` | `member_id`, `from_account`, `to_account`, `amount`, optional `memo` |
| `open_account`   | `member_id`, `account`, optional `account_name`, `account_use`       |
| `delete_account` | `member_id`, `account`                                               |


At replay, values are substituted into steps via `{{param}}` placeholders (e.g. `{{account_testid}}`, `{{amount}}`).

## Outputs

Declare what the caller gets back and its shape—for example a currency string for balance, or a list of ledger rows for a transfer—so a calling agent can type-check results without reading step logs.

## Steps

Each step is one durable action:


| Field         | Purpose                                                                        |
| ------------- | ------------------------------------------------------------------------------ |
| `id`          | Stable id (`step_1`, …)                                                        |
| `type`        | Action: `click`, `fill`, `read`, …                                             |
| `description` | Reviewer-facing intent                                                         |
| `risk`        | `low` / `medium` / `high` (informational; guardrails also classify at runtime) |
| `target`      | How to find the control                                                        |
| `value`       | Optional fill value (may contain `{{params}}`)                                 |




### Target object


| Field                     | Purpose                                     |
| ------------------------- | ------------------------------------------- |
| `strategy`                | `testid`, `role`, `label`, `text`, …        |
| `value` / `name` / `role` | Locator details for that strategy           |
| `robustness`              | Short note on why this locator is preferred |
| `interaction`             | `dom` for this project                      |


Replay resolves targets in a stable preference order (test id, then role + name, then label) and scrolls the control into view before acting.

## Success conditions

Minimal checkpoints: boolean conditions such as “checking balance visible” or “transfer success visible.” They refuse a silent false success; they are not a full assertion language. Each entry has `id`, `description`, and `required`.

## Error handling stamp

```json
"error_handling": {}
```

or a map of recovered error kinds recorded during discovery. Scenario members only replay a version whose stamp matches their login path; happy-path members use blank `{}`.