# REPORT.md — Computer-Use Automation System

Atlas turns a natural-language banking goal into a reusable capability: an LLM discovers the workflow once against a live UI, the successful path is saved as a typed operator, and later invocations replay that operator without the model. The target is a local demo bank. Run evidence lives under [`evidence/`](evidence/); per-test durations are in the [discovery field guide](evidence/discovery/atlas-discovery-field-guide.md) and [replay playbook](evidence/replay/atlas-replay-playbook.md).

## 1. Architecture

A goal enters as natural language and is planned into one or more capabilities (lookup balance, transfer funds, open account, delete account) with typed parameters. If no suitable operator exists—or discovery is forced—the system runs an observe → decide → act loop on a live browser session: it reads the page, asks the model for the next action, checks safety policy, executes the action, verifies progress, and records durable steps. When an operator already covers the member and scenario, the same session path is taken without the model: parameters are substituted into stored steps, locators are resolved, checkpoints are checked, and a structured outcome is returned. Irreversible steps pause so a human can confirm on the same session. Every run writes an evidence pack; successful discovery publishes or updates a versioned operator for later replay.

```text
                    ┌─────────────┐
   natural-language │   Planner   │  capability + params
        goal ──────►│             │──────────────┐
                    └─────────────┘              │
                                                 ▼
                    ┌────────────────────────────────────────┐
                    │         Operator catalog               │
                    │   (versioned, parameterized flows)     │
                    └───────────────┬────────────────────────┘
                         miss │              │ hit
                              ▼              ▼
                    ┌──────────────┐  ┌──────────────┐
                    │  Discovery   │  │    Replay    │
                    │  LLM loop    │  │  no LLM      │
                    │ observe →    │  │ substitute → │
                    │ decide → act │  │ locate → act │
                    └──────┬───────┘  └──────┬───────┘
                           │                 │
                           └────────┬────────┘
                                    ▼
                    ┌──────────────────────────────┐
                    │  Guardrails + error recovery │
                    │  (allowlist, risk, business, │
                    │   reloading / 404 / hard)    │
                    └──────────────┬───────────────┘
                                   ▼
                    ┌──────────────────────────────┐
                    │  HITL handoff (if needed)    │
                    │  same live browser session   │
                    └──────────────┬───────────────┘
                                   ▼
                    ┌──────────────────────────────┐
                    │  Evidence + structured       │
                    │  outcome; save / bump        │
                    │  operator on discovery       │
                    └──────────────────────────────┘
```

Trade-offs favored a DOM-driven browser surface (stable locators, reviewable artifacts, viewport portability) over screenshot coordinates; a synchronous CLI over queues; and capability-specific orchestration where delete composes lookup and transfer rather than forcing one generic executor. The production path is always replay of a saved operator; discovery exists to create and refresh that catalog.

## 2. Artifact schema

Each operator is a reviewable capability contract: identity (`artifact_id`, integer version, title, description), typed inputs (opaque member id, account product, amounts, nicknames), typed outputs (balance shape, transfer ledger rows, status messages), ordered steps with locator strategy and a short robustness note, success conditions, viewport hints, optional `error_handling` stamps, and query signatures for matching. Values that vary per call use `{{param}}` placeholders; credentials and raw PII are not stored.

Versioning keeps history: identical steps and error sets update in place; a new error path or different step sequence allocates `vN+1`. Metadata tracks per-version usage, attempts, failures, and approval (`draft` until at least three successes at ≥75% success rate, then `approved`). Replay prefers the most frequently successful compatible version and can roll back to older versions before failing closed.

Checkpoints are intentionally minimal: boolean success conditions derived from visible product state (balance present, transfer success, account opened or deleted) rather than a full assertion language or multi-page state machines. That is enough to refuse a silent false success; richer predicates, soft asserts, and partial-progress resume markers are natural extensions of the same field.

## 3. Determinism & error handling

Replay never asks the model what to do next. It binds inputs, resolves controls by strategy (prefer test id, then role and accessible name, then label), brings elements into view, executes, and checks success conditions. Nested capabilities reuse stored operators when they match the member’s scenario.

Runtime conditions are classified deliberately. Expected business outcomes—insufficient funds, account already exists, missing product, human declined confirmation—are returned as structured codes the caller can handle, not as crashes. Recoverable conditions—login 404 and transient reloading—are retried on the live session and, on discovery, stamped onto the operator so the correct variant is chosen later. Hard failures—unrecoverable gates, exhausted retries, missing critical controls—stop the run with a clear message and a richer signal (screenshot). Detection prefers guardrail decisions, DOM probes, and recovery events over scraping the agent’s own prose.

UI drift is secondary: scenario-compatible version selection and rollback absorb moderate change; non-DOM locators fail closed toward rediscovery. Visual regression and bounded single-step model repair on failure were left for later.

## 4. Heterogeneity & multi-tenant

The recorded flow is a sequence of intents, parameters, and success conditions; how the machine perceives and acts on a surface is a separate concern. Today perception and action use a browser DOM. The same envelope can target a legacy web app or a desktop surface by swapping the act/locate backend—accessibility tree, screenshot plus coordinates, or OS automation—selected by a locator policy on the artifact, without re-authoring the business steps. Replay would dispatch to that backend rather than re-discovering the workflow.

Institutions often share a vendor product with different branding and configuration. Operators are therefore parameterized by opaque member identifiers and product fields, not by institution chrome. Reuse across tenants would layer a base artifact with per-tenant overrides (locator or route canonicalization), a compatibility fingerprint (app version and known error set), and promotion or demotion from replay statistics when drift rises. Rising failure counts already demote approval; failed preferred versions roll back before rediscovery. A second branded tenant was not built; forked operators for recoverable login scenarios stand in for “same product, different runtime path.”

## 5. Escalation & handoff

When the agent initiates delete, open, or a large-transfer confirm, the bank shows a confirmation page. Automation pauses on that live session: a human clicks Yes, Yes Confirm, Confirm Transfer, or No in the browser, then signals resume or abort in the CLI. Unattended runs may auto-accept or auto-reject via flags. A nonzero-balance delete requires two handoffs—approve moving remaining funds, then confirm deletion. Context preserved across the handoff includes the open page, the run log, and screenshots. There is no separate co-browsing console; the operator surface is the application UI plus the resume prompt. Discovery also stops on max steps, policy blocks, and hard failures instead of open-ended thrashing.

## 6. Safety

Only an allowlisted set of action types may run; unknown actions are blocked. Page expectations gate sensitive flows. Risk is ranked so reads stay low, ordinary form fills medium, and delete, open, and transfer confirmation high—those high-risk confirms require human approval unless an explicit auto-confirm path is armed and, for production auto-confirm, the operator version is approved. Business rules catch insufficient funds and missing or duplicate accounts before irreversible progress. Artifacts omit passwords; member ids are opaque tokens; logs avoid credentials. Limits of the model: policy is action- and page-scoped rather than a full multi-tenant entitlement engine, and there is no separate secrets vault.

## 7. Cuts

Several pieces were kept deliberately thin so every core requirement stays real end-to-end.

Checkpoints assert only coarse success conditions after steps, not a rich assertion DSL or mid-flow branch tables. Evidence is structured logs plus failure screenshots and transfer ledgers, not full DOM snapshots or video. HITL uses the bank’s own confirmation page and a CLI resume signal rather than a dedicated operator console. Locators are DOM strategies only; accessibility and screenshot backends are designed for but not implemented. Approval scoring is per-version counters and a draft/approved gate, not a multi-run flakiness dashboard. Multi-tenant support is parameterization and error-set forks, not live overlays across branded institutions. Invocation is a CLI and test harness, not an agent-facing capability API. There are no job queues, browser farms, or code generation from artifacts.

Natural extensions follow those seams: richer checkpoint languages and partial-progress resume; an invoke API returning the same outcome contract; accessibility or coordinate act adapters behind locator policy; tenant overlays with canonicalized routes; bounded, policy-checked single-step model recovery on replay failure; and tighter hard-failure outcome labeling when multiple classifiers compete. With more time, those deepen existing seams rather than replacing the discover → artifact → replay spine.
