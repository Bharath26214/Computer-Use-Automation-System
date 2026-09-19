from __future__ import annotations

import os
import re
from datetime import datetime

from app.agent.act import act as run_act
from app.agent.safety import safety_check
from app.artifact.recorder import current_member_id, find_artifact_by_id, persist_artifact
from app.artifact.replay import _is_signed_in, run_replay
from app.browser.manager import BrowserManager
from app.plan import CREATE_STATEMENT, PlannedTask, account_params, parse_month, parse_statement_fields
from app.run.logger import RunLogger, utc_now

SCRAPE_ROWS = """
() => {
  const table = document.querySelector('[data-testid="transaction-table"]');
  if (!table) {
    return [];
  }
  return [...table.querySelectorAll('tbody tr')].map((row) => {
    const cells = [...row.querySelectorAll('td')].map((td) => td.textContent.trim());
    if (cells.length < 6 || cells[0] === 'No matching transactions.') {
      return null;
    }
    return {
      date: row.getAttribute('data-date') || cells[0],
      description: cells[1],
      account: row.getAttribute('data-account') || cells[2],
      amountText: cells[3],
      type: cells[4],
      status: cells[5],
    };
  }).filter(Boolean);
}
"""


CREATE_STATEMENT_STEPS = [
    {
        "id": "step_1",
        "type": "navigate",
        "target": {"strategy": "url", "value": "{{bank_url}}"},
    },
    {
        "id": "step_2",
        "type": "fill",
        "target": {"strategy": "label", "value": "Username"},
        "value": "{{member_id}}",
    },
    {
        "id": "step_3",
        "type": "fill",
        "target": {"strategy": "label", "value": "Password"},
        "value": "{{password}}",
    },
    {
        "id": "step_4",
        "type": "click",
        "target": {"strategy": "role", "role": "button", "name": "Sign In"},
    },
    {
        "id": "step_5",
        "type": "click",
        "target": {"strategy": "role", "role": "button", "name": "Transactions"},
    },
    {
        "id": "step_6",
        "type": "read",
        "target": {"strategy": "testid", "value": "transaction-table"},
    },
]


def statement_task(account: str = "", month: str = "", query: str = "") -> PlannedTask:
    params = parse_statement_fields(query)
    if month:
        params["month"] = month
    if account:
        params.update(account_params(account))
    label = params.get("account") or "all accounts"
    period = params.get("month") or parse_month(query)
    params["month"] = period
    return PlannedTask(
        "create_statement",
        CREATE_STATEMENT,
        f"Create a {period} statement for {label}",
        params,
    )


def parse_signed_amount(text: str) -> float:
    raw = (text or "").replace(",", "").replace("−", "-").strip()
    match = re.search(r"[\d]+(?:\.\d{1,2})?", raw)
    if not match:
        return 0.0
    amount = float(match.group(0))
    if raw.startswith("-"):
        return round(-abs(amount), 2)
    return round(amount, 2)


def month_title(month: str) -> str:
    try:
        return datetime.strptime(month, "%Y-%m").strftime("%B %Y")
    except ValueError:
        return month


def _format_amount(amount: float) -> str:
    if amount > 0:
        return f"+${amount:,.2f}"
    if amount < 0:
        return f"-${abs(amount):,.2f}"
    return f"${amount:,.2f}"


def render_statement_markdown(
    *,
    member_id: str,
    account: str,
    month: str,
    rows: list[dict],
) -> str:
    title = month_title(month)
    scope = account or "All accounts"
    credits = sum(row["amount"] for row in rows if row["amount"] > 0)
    debits = sum(row["amount"] for row in rows if row["amount"] < 0)
    lines = [
        f"# Atlas Bank Statement",
        "",
        f"- Member: `{member_id}`",
        f"- Account: {scope}",
        f"- Period: {title}",
        f"- Generated: {utc_now()}",
        f"- Transactions: {len(rows)}",
        f"- Credits: {_format_amount(credits)}",
        f"- Debits: {_format_amount(debits)}",
        f"- Net: {_format_amount(round(credits + debits, 2))}",
        "",
        "| Date | Description | Account | Amount | Type | Status |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    if not rows:
        lines.append("| | No transactions in this period. | | | | |")
    else:
        for row in rows:
            description = str(row.get("description") or "").replace("|", "\\|")
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("date") or ""),
                        description,
                        str(row.get("account") or ""),
                        _format_amount(float(row.get("amount") or 0)),
                        str(row.get("type") or ""),
                        str(row.get("status") or ""),
                    ]
                )
                + " |"
            )
    lines.append("")
    return "\n".join(lines)


def _filter_rows(rows: list[dict], month: str, account: str) -> list[dict]:
    wanted = account.strip().lower()
    filtered: list[dict] = []
    for row in rows:
        row_date = str(row.get("date") or "")
        if not row_date.startswith(month):
            continue
        row_account = str(row.get("account") or "")
        if wanted and wanted not in row_account.lower() and row_account.lower() not in wanted:
            continue
        amount = parse_signed_amount(str(row.get("amountText") or row.get("amount") or "0"))
        filtered.append(
            {
                "date": row_date,
                "description": row.get("description") or "",
                "account": row_account,
                "amount": amount,
                "type": row.get("type") or "",
                "status": row.get("status") or "",
            }
        )
    filtered.sort(key=lambda item: str(item.get("date") or ""), reverse=True)
    return filtered


async def _run_action(browser_manager: BrowserManager, action: dict) -> str:
    state = {
        "action": action,
        "goal": "",
        "outputs": {},
        "action_log": [],
    }
    safety = safety_check(state)
    if safety.get("status") == "blocked":
        return str(safety.get("answer") or safety.get("error") or "Action blocked.")
    acted = await run_act(state, browser_manager)
    return str(acted.get("last_result") or "")


async def _ensure_signed_in(browser_manager: BrowserManager, skip_auth: bool) -> None:
    page = await browser_manager.open()
    if skip_auth and await _is_signed_in(browser_manager):
        return
    if await _is_signed_in(browser_manager):
        return
    bank_url = os.getenv("BANK_URL", "http://127.0.0.1:5173/login")
    await _run_action(browser_manager, {"action": "navigate", "target": bank_url})
    await _run_action(
        browser_manager,
        {
            "action": "fill",
            "target": "Username",
            "value": os.getenv("BANK_USERNAME", "alex"),
        },
    )
    await _run_action(
        browser_manager,
        {
            "action": "fill",
            "target": "Password",
            "value": os.getenv("BANK_PASSWORD", "atlas123"),
        },
    )
    await _run_action(browser_manager, {"action": "click", "target": "Sign In"})


async def _open_transactions(browser_manager: BrowserManager) -> None:
    page = await browser_manager.open()
    if "/transactions" not in (page.url or ""):
        await _run_action(browser_manager, {"action": "click", "target": "Transactions"})
    await page.get_by_test_id("transaction-table").wait_for(state="visible", timeout=8000)


async def scrape_transactions(browser_manager: BrowserManager) -> list[dict]:
    page = await browser_manager.open()
    rows = await page.evaluate(SCRAPE_ROWS)
    return list(rows or [])


async def finalize_statement(
    task: PlannedTask,
    browser_manager: BrowserManager,
    run_logger: RunLogger,
) -> str:
    month = str(task.params.get("month") or parse_month(task.goal))
    account = str(task.params.get("account") or "").strip()
    rows = _filter_rows(await scrape_transactions(browser_manager), month, account)
    markdown = render_statement_markdown(
        member_id=current_member_id(),
        account=account,
        month=month,
        rows=rows,
    )
    path = run_logger.write_statement(markdown)
    print(markdown)
    print(f"[create_statement] saved {path}")
    label = account or "all accounts"
    count = len(rows)
    noun = "transaction" if count == 1 else "transactions"
    return (
        f"{month_title(month)} statement for {label} "
        f"({count} {noun}) saved to {path}."
    )


async def run_create_statement(
    task: PlannedTask,
    browser_manager: BrowserManager,
    skip_auth: bool,
    run_logger: RunLogger | None = None,
    own_run: bool = True,
) -> str:
    month = str(task.params.get("month") or parse_month(task.goal))
    account = str(task.params.get("account") or "").strip()
    print(f"[create_statement] {month} account={account or 'all'}")
    member_id = current_member_id()
    artifact = find_artifact_by_id(CREATE_STATEMENT, member_id)
    if artifact is not None:
        artifact_ref = f"{artifact.get('artifact_id')}/v{artifact.get('version')}"
        logger = run_logger
        if own_run or logger is None:
            logger = RunLogger("replay", task.goal, artifact_used=artifact_ref)
        else:
            logger.note_operator(artifact_ref, created=False)
            logger.event(type="operator", operator=artifact_ref, mode="replay")
        try:
            result = await run_replay(
                task.goal,
                artifact,
                browser_manager,
                logger,
                skip_auth=skip_auth,
            )
        except Exception as exc:
            if own_run:
                logger.finish(status="failed", error=str(exc))
            raise
        if result.get("status") == "replayed":
            answer = await finalize_statement(task, browser_manager, logger)
            if own_run:
                logger.finish(status="success")
            return answer
        if own_run:
            logger.finish(
                status="failed",
                error=str(result.get("error") or result.get("status")),
            )
        print(f"[replay] failed: {result.get('error')}; falling back to discovery")

    logger = run_logger
    if own_run or logger is None:
        logger = RunLogger("discovery", task.goal)
    else:
        logger.event(type="operator", operator=CREATE_STATEMENT, mode="discovery")
    try:
        await _ensure_signed_in(browser_manager, skip_auth)
        await _open_transactions(browser_manager)
        path = persist_artifact(
            {
                "goal": task.goal,
                "recorded_steps": CREATE_STATEMENT_STEPS,
                "checkpoints": {
                    "member_details_displayed": True,
                    "transactions_visible": True,
                },
            }
        )
        if path is not None:
            logger.set_artifact_created(f"{CREATE_STATEMENT}/v1")
            print(f"Operator: {path}")
        answer = await finalize_statement(task, browser_manager, logger)
        if own_run:
            logger.finish(status="success")
        return answer
    except Exception as exc:
        if own_run:
            logger.finish(status="failed", error=str(exc))
        raise
