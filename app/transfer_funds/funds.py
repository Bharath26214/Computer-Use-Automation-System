from __future__ import annotations

import re

from app.agent.act import act as run_act
from app.agent.safety import safety_check
from app.artifact.recorder import (
    current_member_id,
    find_artifact_by_id,
    force_discovery_for,
    force_replay,
    allow_discovery_fallback,
)
from app.artifact.replay import run_replay_with_fallbacks
from app.browser.accounts import (
    ensure_dashboard,
    ensure_signed_in,
)
from app.browser.manager import BrowserManager
from app.guardrails.business import preflight_transfer_business
from app.plan import TRANSFER_FUNDS, PlannedTask, parse_transfer_goal
from app.run.logger import RunLogger

LARGE_TRANSFER_THRESHOLD = 5000.0

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


def parse_transfer_amount(value: object) -> float | None:
    raw = str(value or "").replace(",", "").replace("$", "").strip()
    if not raw:
        return None
    try:
        return round(float(raw), 2)
    except ValueError:
        return None


def parse_signed_amount(text: str) -> float:
    raw = (text or "").replace(",", "").replace("−", "-").strip()
    match = re.search(r"[\d]+(?:\.\d{1,2})?", raw)
    if not match:
        return 0.0
    amount = float(match.group(0))
    if raw.startswith("-"):
        return round(-abs(amount), 2)
    return round(amount, 2)


def _format_amount(amount: float) -> str:
    if amount > 0:
        return f"+${amount:,.2f}"
    if amount < 0:
        return f"-${abs(amount):,.2f}"
    return f"${amount:,.2f}"


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


async def _open_transactions(browser_manager: BrowserManager) -> None:
    page = await browser_manager.open()
    if "/transactions" not in (page.url or ""):
        await _run_action(browser_manager, {"action": "click", "target": "Transactions"})
    await page.get_by_test_id("transaction-table").wait_for(state="visible", timeout=8000)


async def scrape_transactions(browser_manager: BrowserManager) -> list[dict]:
    page = await browser_manager.open()
    rows = await page.evaluate(SCRAPE_ROWS)
    return list(rows or [])


def _status_label(status: str | None) -> str:
    value = (status or "").strip().lower()
    if value in {"pass", "success"}:
        return "success"
    if value in {"failed", "fail", "failure", "blocked", "cancelled"}:
        return "failure"
    return "success" if not value else value


def render_transfer_markdown(
    rows: list[dict],
    *,
    status: str | None = "success",
    outcome: str | None = None,
) -> str:
    lines: list[str] = [
        f"**Status:** {_status_label(status)}",
    ]
    if outcome:
        lines.append(f"**Outcome:** {outcome}")
    lines.extend(
        [
            "",
            "| Date | Description | Account | Amount | Type | Status |",
            "| --- | --- | --- | ---: | --- | --- |",
        ]
    )
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
    wanted = parse_transfer_amount(amount)

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


def _approve_large_transfer(task: PlannedTask) -> str | None:
    """
    Large transfers (> $5000): agent opens Transfer Review, then you click
    Confirm Transfer on the app confirmation page (type resume after).
    """
    if task.params.get("skip_large_transfer_approval"):
        return None
    amount = parse_transfer_amount(task.params.get("amount"))
    if amount is None or amount <= LARGE_TRANSFER_THRESHOLD:
        return None
    source = task.params.get("from_account") or "Savings"
    destination = task.params.get("to_account") or "Checking"
    print(
        f"[transfer_funds] ${amount:,.2f} from {source} to {destination} exceeds "
        f"${LARGE_TRANSFER_THRESHOLD:,.0f} — after Review Transfer, click "
        f"Confirm Transfer on the app page, then type resume."
    )
    return None


async def _preflight_transfer(
    task: PlannedTask,
    browser_manager: BrowserManager,
    skip_auth: bool,
    run_logger: RunLogger | None = None,
):
    """Business edge cases via the guardrail engine before Transfer UI."""
    from app.guardrails.types import GuardrailDecision

    await ensure_signed_in(browser_manager, skip_auth=skip_auth, run_logger=run_logger)
    await ensure_dashboard(browser_manager)

    source = str(task.params.get("from_account") or "Savings").strip() or "Savings"
    destination = str(task.params.get("to_account") or "Checking").strip() or "Checking"
    amount = parse_transfer_amount(task.params.get("amount"))
    decision = await preflight_transfer_business(
        browser_manager,
        from_account=source,
        to_account=destination,
        amount=amount,
    )
    if decision is not None and decision.blocked():
        return decision
    return None


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

    # Resolve accounts/funds before asking about large-transfer approval.
    # Create logger early so preflight guardrail decisions are audited.
    logger = run_logger
    if own_run or logger is None:
        # Tentative kind; may still discovery-fallback later.
        kind = (
            "discovery"
            if force_discovery_for(TRANSFER_FUNDS) or not find_artifact_by_id(TRANSFER_FUNDS)
            else "replay"
        )
        logger = RunLogger(kind, task.goal)
        own_finish = True
    else:
        own_finish = False

    decision = await _preflight_transfer(task, browser_manager, skip_auth, run_logger=logger)
    if decision is not None:
        logger.log_guardrail(decision)
        # Capture DOM corroboration when the form already shows the alert.
        try:
            await logger.capture_dom_outcome(
                browser_manager.page,
                task_kind="transfer",
            )
        except Exception:
            pass
        if own_run or own_finish:
            logger.finish(
                answer=decision.message,
                task_kind="transfer",
                outcome_code=None,  # already noted from guardrail rule
            )
        return decision.message

    denied = _approve_large_transfer(task)
    if denied:
        from app.guardrails.types import GuardrailDecision, HITLState, RiskLevel

        hitl_decision = GuardrailDecision(
            decision=HITLState.BLOCK,
            risk=RiskLevel.HIGH,
            rule="hitl_denied",
            message=denied,
            status="blocked",
            action="preflight",
            target="large_transfer",
        )
        logger.log_guardrail(hitl_decision)
        if own_run or own_finish:
            logger.finish(answer=denied, error=denied, task_kind="transfer")
        return denied

    # Confirm-transfer HITL still applies unless this was a delete-driven transfer.
    transfer_context = {
        "skip_large_transfer_approval": bool(
            task.params.get("skip_large_transfer_approval")
        ),
        "guardrail_approved": bool(task.params.get("skip_large_transfer_approval")),
    }

    print(
        f"[transfer_funds] {task.params.get('amount')} "
        f"from {task.params.get('from_account')} to {task.params.get('to_account')}"
    )
    member_id = current_member_id()
    artifact = find_artifact_by_id(TRANSFER_FUNDS, member_id)

    async def _finish(log: RunLogger, answer: str, error: str | None = None) -> None:
        if own_run or own_finish:
            try:
                await log.capture_dom_outcome(
                    browser_manager.page, task_kind="transfer"
                )
            except Exception:
                pass
            log.finish(
                answer=answer,
                error=error,
                task_kind="transfer",
            )

    # Reuse the logger created for preflight audit.
    if artifact is not None and not force_discovery_for(TRANSFER_FUNDS):
        artifact_ref = f"{artifact.get('artifact_id')}/v{artifact.get('version')}"
        logger.note_operator(artifact_ref, created=False)
        logger.event(type="operator", operator=artifact_ref, mode="replay")
        try:
            result = await run_replay_with_fallbacks(
                task.goal,
                artifact,
                browser_manager,
                logger,
                skip_auth=True,
                context=transfer_context,
            )
        except Exception as exc:
            await _finish(logger, str(exc), error=str(exc))
            raise
        if result.get("status") == "replayed":
            answer = await finalize_transfer(task.goal, browser_manager, logger)
            await _finish(logger, answer)
            return answer
        if result.get("status") == "guardrail_blocked":
            answer = str(result.get("answer") or result.get("error") or "")
            await _finish(logger, answer)
            return answer
        error = str(result.get("error") or result.get("status") or "UI changed")
        if "insufficient funds" in error.lower():
            await _finish(logger, error)
            return error
        if not allow_discovery_fallback():
            print(f"[replay] failed: {error}; discovery fallback disabled")
            await _finish(logger, error, error=error)
            return error
        print(f"[replay] failed: {error}; falling back to LLM discovery")

    if force_replay():
        msg = f"No replayable {TRANSFER_FUNDS} operator for {member_id}."
        print(f"[replay] {msg}")
        await _finish(logger, msg, error=msg)
        return msg

    from app.agent.discover import run_discovery

    logger.event(type="operator", operator=TRANSFER_FUNDS, mode="discovery")
    try:
        answer = await run_discovery(
            task.goal,
            browser_manager,
            logger,
            finish_run=False,
            task_kind="transfer",
        )
        lowered = answer.lower()
        if "insufficient funds" in lowered or "transfer to" in lowered or "transfer from" in lowered:
            if "transfer to" in lowered or "transfer from" in lowered:
                try:
                    answer = await finalize_transfer(task.goal, browser_manager, logger)
                except Exception:
                    pass
            await _finish(logger, answer)
            return answer
        await _finish(logger, answer)
        return answer
    except Exception as exc:
        await _finish(logger, str(exc), error=str(exc))
        raise
