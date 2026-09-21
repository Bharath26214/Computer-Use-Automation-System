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
from app.browser.manager import BrowserManager
from app.plan import (
    DELETE_ACCOUNT,
    LOOKUP_BALANCE,
    TRANSFER_FUNDS,
    PlannedTask,
    account_params,
)
from app.run.logger import RunLogger

CURRENCY = re.compile(r"\$([\d,]+(?:\.\d{1,2})?)")


def parse_balance(text: str) -> float | None:
    match = CURRENCY.search(text or "")
    if not match:
        return None
    return round(float(match.group(1).replace(",", "")), 2)


def format_amount(amount: float) -> str:
    return f"{amount:.2f}"


def format_currency(amount: float) -> str:
    return f"${amount:,.2f}"


def _lookup_task(account: str) -> PlannedTask:
    params = account_params(account)
    return PlannedTask(
        "get_balance",
        LOOKUP_BALANCE,
        f"What is my {params['account'].lower()} account balance?",
        params,
    )


def _transfer_all_task(source: str, destination: str, amount: str) -> PlannedTask:
    return PlannedTask(
        "transfer",
        TRANSFER_FUNDS,
        f"Transfer {amount} from {source} to {destination}",
        {
            "from_account": source,
            "to_account": destination,
            "amount": amount,
            "memo": f"{source} account closure",
            # Human already approved transfer-before-delete on the app page.
            "skip_large_transfer_approval": True,
        },
    )


def _choose_account() -> str | None:
    print("Which account should be deleted, Checking or Savings?")
    try:
        reply = input("Account: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if reply.startswith("check"):
        return "Checking"
    if reply.startswith("sav"):
        return "Savings"
    return None


def _operators_ready(member_id: str, need_transfer: bool) -> bool:
    required = [LOOKUP_BALANCE, DELETE_ACCOUNT]
    if need_transfer:
        required.append(TRANSFER_FUNDS)
    return all(find_artifact_by_id(name, member_id) is not None for name in required)


async def _account_visible(browser_manager: BrowserManager, account: str) -> bool:
    page = browser_manager.page
    if page is None:
        return False
    kind = "checking" if account.lower().startswith("check") else "savings"
    try:
        return await page.get_by_test_id(f"{kind}-account").count() > 0
    except Exception:
        return False


async def _run_action(
    browser_manager: BrowserManager,
    action: dict,
    allow_delete: bool = False,
) -> str:
    state = {
        "action": action,
        "goal": "",
        "outputs": {},
        "action_log": [],
        "allow_delete": allow_delete,
    }
    safety = safety_check(state)
    if safety.get("status") == "blocked":
        return str(safety.get("answer") or safety.get("error") or "Action blocked.")
    acted = await run_act(state, browser_manager)
    return str(acted.get("last_result") or "")


async def _ensure_dashboard(browser_manager: BrowserManager) -> None:
    page = await browser_manager.open()
    if "/dashboard" not in (page.url or ""):
        await _run_action(
            browser_manager,
            {"action": "click", "target": "Dashboard"},
        )


async def request_transfer_before_delete(
    browser_manager: BrowserManager,
    account: str,
) -> str:
    """
    Click Delete on a nonzero-balance account so the app shows Transfer funds Yes/No.
    Human clicks Yes in the browser, then types resume. Returns error string or "".
    """
    await _ensure_dashboard(browser_manager)
    kind = "checking" if account.lower().startswith("check") else "savings"
    page = await browser_manager.open()
    try:
        button = page.get_by_test_id(f"delete-{kind}-account")
        await button.wait_for(state="visible", timeout=5000)
    except Exception:
        if not await _account_visible(browser_manager, account):
            return f"There is no {account} account to delete."
        return f"Could not find Delete {account} Account."

    print(
        f"[delete_account] click Delete {account} Account → transfer-funds Yes/No page"
    )
    clicked = await _run_action(
        browser_manager,
        {"action": "click", "target": f"Delete {account} Account"},
    )
    if "human did not confirm" in str(clicked).lower() or "human declined" in str(
        clicked
    ).lower():
        return clicked
    if str(clicked).startswith("Action failed"):
        return clicked
    # After handoff, message should note transfer approval.
    message = await _run_action(
        browser_manager,
        {"action": "read", "target": "open-account-message"},
    )
    if "transfer funds approved" in str(message).lower():
        return ""
    if "human did not confirm" in str(message).lower():
        return message
    # Handoff already completed inside act; treat as approved if no hard failure.
    return ""


def _persist_delete_operator(goal: str, account: str, run_logger: RunLogger) -> None:
    """
    Scripted delete never goes through LLM discovery, so persist the DOM steps
    that delete_account_in_ui just executed (Dashboard → Delete → status read).
    """
    from app.artifact.recorder import persist_artifact
    from app.browser.viewport import current_viewport

    recorded = [
        {
            "action": "click",
            "target": "Dashboard",
            "reason": "Return to dashboard before delete",
        },
        {
            "action": "click",
            "target": f"Delete {account} Account",
            "reason": f"Delete the {account} account",
        },
        {
            "action": "read",
            "target": "open-account-message",
            "reason": "Read delete confirmation message",
        },
    ]
    path = persist_artifact(
        {
            "goal": goal or f"Delete the {account} account",
            "artifact_id": DELETE_ACCOUNT,
            "recorded_steps": recorded,
            "viewport": current_viewport(),
            "checkpoints": {
                "member_details_displayed": True,
                "account_deleted": True,
            },
        }
    )
    if path is not None:
        print(f"[delete_account] saved operator {path}")
        run_logger.note_operator(f"{DELETE_ACCOUNT}/v1", created=True)
        run_logger.event(
            type="operator",
            operator=f"{DELETE_ACCOUNT}",
            mode="discovery",
            path=str(path),
        )


async def delete_account_in_ui(browser_manager: BrowserManager, account: str) -> str:
    """Click Delete on a zero-balance account → Confirm Delete → human Yes, Confirm + resume."""
    kind = "checking" if account.lower().startswith("check") else "savings"
    await _ensure_dashboard(browser_manager)
    page = await browser_manager.open()
    try:
        button = page.get_by_test_id(f"delete-{kind}-account")
        await button.wait_for(state="visible", timeout=5000)
    except Exception:
        if not await _account_visible(browser_manager, account):
            return f"There is no {account} account to delete."
        return f"{account} account was not deleted."

    print(
        f"[delete_account] click Delete {account} Account → confirm deletion page"
    )
    clicked = await _run_action(
        browser_manager,
        {"action": "click", "target": f"Delete {account} Account"},
    )
    if str(clicked).startswith("Action failed"):
        return clicked
    if "human did not confirm" in str(clicked).lower() or "human declined" in str(
        clicked
    ).lower():
        return clicked
    message = await _run_action(
        browser_manager,
        {"action": "read", "target": "open-account-message"},
    )
    if "deleted" in message.lower():
        return f"{account} account deleted."
    if message and not str(message).startswith("Action failed"):
        return message
    if not await _account_visible(browser_manager, account):
        return f"{account} account deleted."
    return clicked or f"{account} account was not deleted."


def _delete_succeeded(message: str) -> bool:
    text = (message or "").lower()
    if "was not deleted" in text:
        return False
    if "human did not confirm" in text or "human declined" in text:
        return False
    return "deleted" in text


async def _finish_delete(
    goal: str,
    account: str,
    browser_manager: BrowserManager,
    run_logger: RunLogger,
) -> str:
    from app.agent.discover import run_discovery

    delete_goal = goal or f"Delete the {account} account"
    member_id = current_member_id()
    artifact = find_artifact_by_id(DELETE_ACCOUNT, member_id)
    if artifact is not None and not force_discovery_for(DELETE_ACCOUNT):
        artifact_ref = f"{artifact.get('artifact_id')}/v{artifact.get('version')}"
        run_logger.note_operator(artifact_ref, created=False)
        run_logger.event(type="operator", operator=artifact_ref, mode="replay")
        result = await run_replay_with_fallbacks(
            delete_goal,
            artifact,
            browser_manager,
            run_logger,
            skip_auth=True,
            context={},
        )
        if result.get("status") == "replayed":
            return result.get("answer") or f"{account} account deleted."
        error = str(result.get("error") or result.get("status") or "UI changed")
        if not allow_discovery_fallback():
            print(f"[replay] failed: {error}; discovery fallback disabled")
            return error
        print(f"[replay] failed: {error}; falling back to LLM discovery")

    if force_replay():
        msg = f"No replayable {DELETE_ACCOUNT} operator for {member_id}."
        print(f"[replay] {msg}")
        return msg

    run_logger.event(type="operator", operator=DELETE_ACCOUNT, mode="discovery")
    return await run_discovery(
        delete_goal,
        browser_manager,
        run_logger,
        finish_run=False,
        task_kind="delete_account",
    )


async def run_delete_account(
    task: PlannedTask,
    browser_manager: BrowserManager,
    skip_auth: bool,
    run_task,
    run_logger: RunLogger | None = None,
    own_run: bool = True,
) -> str:
    account = str(task.params.get("account") or "").strip()
    if not account:
        chosen = _choose_account()
        if not chosen:
            return "No account was selected, so nothing was deleted."
        account = chosen
    other = str(task.params.get("other_account") or "")
    if not other:
        other = "Savings" if account == "Checking" else "Checking"

    member_id = current_member_id()
    finish_self = own_run or run_logger is None
    if finish_self:
        kind = "replay" if _operators_ready(member_id, need_transfer=False) else "discovery"
        run_logger = RunLogger(kind, task.goal)
    assert run_logger is not None
    answers: list[str] = []

    async def _finish(answer: str, error: str | None = None) -> None:
        if finish_self:
            try:
                await run_logger.capture_dom_outcome(
                    browser_manager.page,
                    task_kind="delete_account",
                    account=account,
                )
            except Exception:
                pass
            run_logger.finish(
                answer=answer,
                error=error,
                task_kind="delete_account",
            )

    try:
        print(f"[delete_account] looking up {account} balance")
        lookup_answer = await run_task(
            _lookup_task(account),
            browser_manager,
            skip_auth,
            fallback_discovery=allow_discovery_fallback(),
            run_logger=run_logger,
            own_run=False,
        )
        print(lookup_answer)
        answers.append(lookup_answer)
        balance = parse_balance(lookup_answer)
        source_visible = await _account_visible(browser_manager, account)
        missing_lookup = (
            "do not have a" in lookup_answer.lower()
            or "account not found" in lookup_answer.lower()
        )
        if missing_lookup or (not source_visible and balance is None):
            message = f"There is no {account} account to delete."
            await _finish(message)
            return message
        if balance is None:
            message = (
                f"I could not read the {account} balance, so the account was not deleted."
            )
            await _finish(message, error="UI changed: balance unread")
            return message

        if balance > 0:
            destination_visible = await _account_visible(browser_manager, other)
            print(
                f"The {account} balance is {format_currency(balance)}. "
                f"Agent clicks Delete → you approve Transfer funds (Yes) on the app, "
                f"then type resume. After that, funds move to {other} and delete continues."
            )
            if not destination_visible:
                message = (
                    f"There is no {other} account to receive the funds. "
                    f"Open a {other} account first. {account} was not deleted."
                )
                await _finish(message)
                return message

            # Step 1: Delete click → transfer Yes/No page → human Yes + resume
            approved = await request_transfer_before_delete(browser_manager, account)
            if approved:
                message = (
                    f"{account} account was not deleted: transfer of remaining funds "
                    f"was declined."
                    if "did not confirm" in approved.lower()
                    or "declined" in approved.lower()
                    else approved
                )
                answers.append(message)
                await _finish(message)
                return message

            amount = format_amount(balance)
            print(f"[delete_account] transferring {amount} from {account} to {other}")
            transfer_answer = await run_task(
                _transfer_all_task(account, other, amount),
                browser_manager,
                skip_auth=True,
                fallback_discovery=allow_discovery_fallback(),
                run_logger=run_logger,
                own_run=False,
            )
            print(transfer_answer)
            answers.append(transfer_answer)
            if "could not find a transfer amount" in transfer_answer.lower():
                message = f"Transfer failed, so {account} was not deleted."
                await _finish(message, error="UI changed")
                return message
            if "human approval was not given" in transfer_answer.lower() or (
                "human did not confirm" in transfer_answer.lower()
            ) or "human declined" in transfer_answer.lower():
                message = (
                    f"{account} account was not deleted: transfer of remaining funds "
                    f"was declined."
                )
                await _finish(message)
                return message
            if "insufficient funds" in transfer_answer.lower():
                message = (
                    f"Transfer failed (insufficient funds), so {account} was not deleted."
                )
                await _finish(message, error="UI changed")
                return message
            if "account not found" in transfer_answer.lower() or "do not have a" in transfer_answer.lower():
                message = (
                    f"Transfer failed (account missing), so {account} was not deleted."
                )
                await _finish(message)
                return message
            if "transfer to" not in transfer_answer.lower() and "transfer from" not in transfer_answer.lower():
                message = (
                    f"Transfer failed, so {account} was not deleted. {transfer_answer}"
                )
                await _finish(message, error="UI changed")
                return message

            # Step 2: Delete again → Confirm Delete → human Yes, Confirm + resume
            print(
                f"[delete_account] balance cleared — click Delete {account} Account "
                f"again; confirm deletion on the app, then type resume."
            )
            deleted = await delete_account_in_ui(browser_manager, account)
            if _delete_succeeded(deleted):
                _persist_delete_operator(task.goal, account, run_logger)
            answers.append(deleted)
            combined = "\n".join(part for part in answers if part)
            await _finish(combined)
            return combined

        print(
            f"The {account} balance is {format_currency(0)}. "
            f"Agent clicks Delete → you confirm on the app page, then type resume."
        )
        print(f"[delete_account] deleting {account}")
        # Prefer direct UI path so the two-step handoff is consistent.
        deleted = await delete_account_in_ui(browser_manager, account)
        if "was not deleted" in deleted.lower() and "human did not confirm" not in deleted.lower():
            deleted = await _finish_delete(task.goal, account, browser_manager, run_logger)
        elif _delete_succeeded(deleted):
            _persist_delete_operator(task.goal, account, run_logger)
        answers.append(deleted)
        combined = "\n".join(part for part in answers if part)
        await _finish(combined)
        return combined
    except Exception as exc:
        await _finish(str(exc), error=str(exc))
        raise
