# Computer-Use Automation System

A LangGraph agent takes a natural-language banking request, then uses Playwright to operate Atlas Bank.

Supported tasks:

- Open a Checking or Savings account (asks for yes/no confirmation first; on yes, opens the account and reports that it was created successfully)
- Account balance lookup
- Transfer funds between Savings and Checking. The matching debit and credit rows are returned and saved as `runs/.../transfer.md`.
- Delete a Checking or Savings account (looks up the balance first; nonzero balances require a confirmed transfer to the other account). After that transfer, a monthly statement is created and shown before the account is deleted.
- Create a monthly transaction statement. The Markdown file is saved next to the run trace as `runs/discovery/run_XXX/statement.md` or `runs/replay/run_XXX/statement.md`.
- Multiple tasks in one request, chained with `then` / `and then`

Transfers, account opens, and deletes are completed in the Atlas Bank UI and stored in `localStorage`. The automation browser reuses `.atlas-browser/` so those changes survive reloads and later `python3 -m app.main` runs (for example, after deleting Savings, creating Savings again is allowed; if both products already exist, create/open is refused). Replayable flows are stored as parameterized operators:

- `operators/lookup_balance/` — Checking or Savings, with `{{account}}`
- `operators/transfer_funds/` — either direction, with `{{from_account}}`, `{{to_account}}`, and `{{amount}}`
- `operators/create_statement/` — monthly statement, with `{{month}}` and optional `{{account}}`
- `operators/delete_account/` — delete Checking or Savings after confirmation, with `{{account}}`
- `operators/open_account/` — Checking or Savings, with `{{account}}`, `{{account_name}}`, and `{{account_use}}`. Invalid when the member already holds both products; chained steps after a failed open are voided.

If a matching operator exists, that flow is **replayed**. If it does not, **discovery** records it. `create_statement` writes `statement.md` into the active run folder, alongside `run.json` and `events.jsonl`.

`delete_account` is one composite run. It reuses `lookup_balance`, optional `transfer_funds`, `create_statement`, and `delete_account`, logs every step into a single `runs/discovery|replay/run_XXX/`, and still stores each operator under `operators/`.

Any chained request (for example open account then transfer funds) is also **one** discovery or replay run for the full query. Individual operators are still stored separately under `operators/`. The run is replay when every needed operator already exists; otherwise it is discovery.

`sam` has Savings only (use to open Checking). `jordan` has Checking only (use to open Savings). `alex` already has both.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Put your Groq API key in `.env`. Default bank login is `alex` / `atlas123`.

Start Atlas Bank:

```bash
cd atlas-demo-bank
npm install
npm run dev
```

## Ask the bank

```bash
python3 -m app.main "What is my savings account balance?"
python3 -m app.main "Look up the checking balance for jordan"
python3 -m app.main 'Transfer 20 from savings to checking'
python3 -m app.main 'Move 10 from checking to savings'
python3 -m app.main "Open a checking account"
python3 -m app.main "Create a savings account"
python3 -m app.main "Open a checking account named Everyday Checking use business"
python3 -m app.main 'Open a checking account then transfer 20 from savings to checking then display savings balance'
python3 -m app.main "Delete my savings account"
python3 -m app.main "Create a statement"
python3 -m app.main "Create a savings statement for September"
```

Or run an interactive prompt:

```bash
python3 -m app.main
```

The first time a user asks a lookup, discovery runs and writes a trace under `runs/discovery/run_001/`:

observe → decide → safety → act → record → observe

`run.json` describes the run. `events.jsonl` records observe, LLM decisions, browser actions, and verify checkpoints. Every successful discovery is saved for replay under `operators/{operator_id}/v1.json`. If the same browser steps are discovered again, that version is reused and the new query is added as an alias instead of writing `v2.json`. A later discovery only creates `v2.json` when the steps actually changed.

If the **same user** asks the **same kind of query** again, that operator is replayed in Playwright with a trace under `runs/replay/run_001/`. The LLM is not called. Fill values such as `{{member_id}}`, `{{account}}`, `{{from_account}}`, `{{to_account}}`, and `{{amount}}` are substituted from the current request and `.env`. If replay fails, the agent falls back to discovery and records a new operator.

The LLM never writes Playwright code. **Confirm Transfer** and **Transfer Money** are classified as REVIEW and allowed for this demo bank. **Delete** stays HIGH RISK unless the user confirmed the `delete_account` flow.
