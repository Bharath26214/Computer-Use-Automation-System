from __future__ import annotations

from app.artifact.recorder import current_member_id, find_artifact_by_id, persist_artifact
from app.artifact.replay import run_replay
from app.browser.manager import BrowserManager
from app.create_statement.runner import (
    _format_amount,
    _open_transactions,
    parse_signed_amount,
    scrape_transactions,
)
from app.plan import TRANSFER_FUNDS, PlannedTask, parse_transfer_goal
from app.run.logger import RunLogger

TRANSFER_FUNDS_STEPS = [
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
        "target": {"strategy": "role", "role": "button", "name": "Transfer Money"},
    },
    {
        "id": "step_6",
        "type": "fill",
        "target": {"strategy": "label", "value": "From Account"},
        "value": "{{from_account}}",
    },
    {
        "id": "step_7",
        "type": "fill",
        "target": {"strategy": "label", "value": "To Account"},
        "value": "{{to_account}}",
    },
    {
        "id": "step_8",
        "type": "fill",
        "target": {"strategy": "label", "value": "Amount"},
        "value": "{{amount}}",
    },
    {
        "id": "step_9",
        "type": "click",
        "target": {"strategy": "role", "role": "button", "name": "Review Transfer"},
    },
    {
        "id": "step_10",
        "type": "click",
        "target": {"strategy": "role", "role": "button", "name": "Confirm Transfer"},
    },
    {
        "id": "step_11",
        "type": "click",
        "target": {"strategy": "role", "role": "button", "name": "Transactions"},
    },
    {
        "id": "step_12",
        "type": "read",
        "target": {"strategy": "testid", "value": "transaction-table"},
    },
]


def render_transfer_markdown(rows: list[dict]) -> str:
    lines = [
        "| Date | Description | Account | Amount | Type | Status |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for row in rows:
        description = str(row.get("description") or "").replace("|", "\\|")
        amount = row.get("amount")
        if amount is None:
            amount_text = str(row.get("amountText") or "")
        else:
            amount_text = _format_amount(float(amount))
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("date") or ""),
                    description,
                    str(row.get("account") or ""),
                    amount_text,
                    str(row.get("type") or ""),
                    str(row.get("status") or ""),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _match_transfer_rows(
    rows: list[dict],
    source: str,
    destination: str,
    amount: str,
) -> list[dict]:
    source_l = source.lower()
    dest_l = destination.lower()
    wanted = None
    try:
        wanted = round(float(str(amount).replace(",", "").replace("$", "")), 2)
    except ValueError:
        wanted = None

    debit_desc = f"transfer to {dest_l}"
    credit_desc = f"transfer from {source_l}"
    matched: list[dict] = []
    for row in rows:
        description = str(row.get("description") or "").lower()
        account = str(row.get("account") or "").lower()
        amount_value = parse_signed_amount(str(row.get("amountText") or row.get("amount") or "0"))
        if wanted is not None and round(abs(amount_value), 2) != wanted:
            continue
        if debit_desc in description and source_l in account and amount_value < 0:
            matched.append(
                {
                    "date": row.get("date") or "",
                    "description": row.get("description") or "",
                    "account": row.get("account") or "",
                    "amount": amount_value,
                    "type": row.get("type") or "Debit",
                    "status": row.get("status") or "Completed",
                }
            )
        elif credit_desc in description and dest_l in account and amount_value > 0:
            matched.append(
                {
                    "date": row.get("date") or "",
                    "description": row.get("description") or "",
                    "account": row.get("account") or "",
                    "amount": amount_value,
                    "type": row.get("type") or "Credit",
                    "status": row.get("status") or "Completed",
                }
            )
        if len(matched) >= 2:
            break
    return matched[:2]


async def finalize_transfer(
    goal: str,
    browser_manager: BrowserManager,
    run_logger: RunLogger,
) -> str:
    parsed = parse_transfer_goal(goal)
    source = parsed.get("from_account") or "Savings"
    destination = parsed.get("to_account") or "Checking"
    amount = parsed.get("amount") or ""
    await _open_transactions(browser_manager)
    rows = _match_transfer_rows(
        await scrape_transactions(browser_manager),
        source,
        destination,
        amount,
    )
    if not rows:
        return "Transfer completed, but the debit and credit rows were not found."
    markdown = render_transfer_markdown(rows)
    path = run_logger.write_transfer(markdown)
    print(markdown)
    print(f"[transfer_funds] saved {path}")
    return markdown


async def run_transfer_funds(
    task: PlannedTask,
    browser_manager: BrowserManager,
    skip_auth: bool,
    run_logger: RunLogger | None = None,
    own_run: bool = True,
) -> str:
    if not task.params.get("amount"):
        return (
            "I could not find a transfer amount in that request. "
            "If you used a dollar sign, the shell may have removed it. "
            "Try: python3 -m app.main 'Transfer 20 from savings to checking'"
        )

    print(
        f"[transfer_funds] {task.params.get('amount')} "
        f"from {task.params.get('from_account')} to {task.params.get('to_account')}"
    )
    member_id = current_member_id()
    artifact = find_artifact_by_id(TRANSFER_FUNDS, member_id)
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
            answer = await finalize_transfer(task.goal, browser_manager, logger)
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
        logger.event(type="operator", operator=TRANSFER_FUNDS, mode="discovery")
    try:
        result = await run_replay(
            task.goal,
            {
                "artifact_id": TRANSFER_FUNDS,
                "steps": TRANSFER_FUNDS_STEPS,
                "_path": None,
            },
            browser_manager,
            logger,
            skip_auth=skip_auth,
        )
        if result.get("status") != "replayed":
            if own_run:
                logger.finish(
                    status="failed",
                    error=str(result.get("error") or result.get("status")),
                )
            return str(result.get("error") or "Transfer failed.")
        path = persist_artifact(
            {
                "goal": task.goal,
                "recorded_steps": TRANSFER_FUNDS_STEPS,
                "checkpoints": {
                    "member_details_displayed": True,
                    "transfer_form_visible": True,
                    "transfer_review_visible": True,
                    "transfer_success_visible": True,
                    "transactions_visible": True,
                },
            }
        )
        if path is not None:
            logger.set_artifact_created(f"{TRANSFER_FUNDS}/v1")
            print(f"Operator: {path}")
        answer = await finalize_transfer(task.goal, browser_manager, logger)
        if own_run:
            logger.finish(status="success")
        return answer
    except Exception as exc:
        if own_run:
            logger.finish(status="failed", error=str(exc))
        raise
