from __future__ import annotations

import re

from app.agent.act import act as run_act
from app.agent.safety import safety_check
from app.artifact.recorder import current_member_id, find_artifact_by_id
from app.artifact.replay import run_replay_with_fallbacks
from app.browser.manager import BrowserManager
from app.plan import (
    DELETE_ACCOUNT,
    LOOKUP_BALANCE,
    TRANSFER_FUNDS,
    PlannedTask,
    account_params,
)
from app.run.confirm import ConfirmationTimeout, ask_yes_no
from app.run.logger import RunLogger

DELETE_ACCOUNT_STEPS = [
    {
        "id": "step_1",
        "type": "navigate",
        "description": "navigate \u2192 {{bank_url}}",
        "target": {
            "strategy": "url",
            "value": "{{bank_url}}",
            "robustness": "Navigate by absolute/templated URL so replay starts from a known route."
        }
    },
    {
        "id": "step_2",
        "type": "fill",
        "description": "fill \u2192 Username",
        "target": {
            "strategy": "label",
            "value": "Username",
            "robustness": "Use the Username field label; login is username-only (member_id = name + three digits)."
        },
        "value": "{{member_id}}"
    },
    {
        "id": "step_3",
        "type": "click",
        "description": "click \u2192 Sign In",
        "target": {
            "strategy": "role",
            "role": "button",
            "name": "Sign In",
            "robustness": "Locate by ARIA role + accessible name so the control remains findable if layout shifts but semantics stay the same."
        }
    },
    {
        "id": "step_4",
        "type": "click",
        "description": "click \u2192 Dashboard",
        "target": {
            "strategy": "role",
            "role": "button",
            "name": "Dashboard",
            "robustness": "Locate by ARIA role + accessible name so the control remains findable if layout shifts but semantics stay the same."
        }
    },
    {
        "id": "step_5",
        "type": "click",
        "description": "click \u2192 Delete {{account}} Account",
        "target": {
            "strategy": "role",
            "role": "button",
            "name": "Delete {{account}} Account",
            "robustness": "Locate by ARIA role + accessible name so the control remains findable if layout shifts but semantics stay the same."
        }
    },
    {
        "id": "step_6",
        "type": "read",
        "description": "read \u2192 open-account-message",
        "target": {
            "strategy": "testid",
            "value": "open-account-message",
            "robustness": "Prefer data-testid attributes; they are stable across copy changes and less brittle than visible text."
        }
    }
]

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
            # Delete flow already got human approval; do not re-ask for >$5000.
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


async def delete_account_in_ui(browser_manager: BrowserManager, account: str) -> str:
    kind = "checking" if account.lower().startswith("check") else "savings"
    page = await browser_manager.open()
    if "/dashboard" not in (page.url or ""):
        await _run_action(
            browser_manager,
            {"action": "click", "target": "Dashboard"},
        )
    try:
        button = page.get_by_test_id(f"delete-{kind}-account")
        await button.wait_for(state="visible", timeout=5000)
        await page.wait_for_function(
            "(sel) => { const el = document.querySelector(sel); return !!el && !el.disabled; }",
            arg=f"[data-testid='delete-{kind}-account']",
            timeout=8000,
        )
    except Exception:
        if not await _account_visible(browser_manager, account):
            return f"There is no {account} account to delete."
        return f"{account} still has a balance, so it was not deleted."
    clicked = await _run_action(
        browser_manager,
        {"action": "click", "target": f"Delete {account} Account"},
        allow_delete=True,
    )
    if str(clicked).startswith("Action failed"):
        return clicked
    message = await _run_action(
        browser_manager,
        {"action": "read", "target": "open-account-message"},
        allow_delete=True,
    )
    if "deleted" in message.lower():
        return f"{account} account deleted."
    if message and not str(message).startswith("Action failed"):
        return message
    if not await _account_visible(browser_manager, account):
        return f"{account} account deleted."
    return clicked or f"{account} account was not deleted."


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
    if artifact is not None:
        artifact_ref = f"{artifact.get('artifact_id')}/v{artifact.get('version')}"
        run_logger.note_operator(artifact_ref, created=False)
        run_logger.event(type="operator", operator=artifact_ref, mode="replay")
        result = await run_replay_with_fallbacks(
            delete_goal,
            artifact,
            browser_manager,
            run_logger,
            skip_auth=True,
            context={"allow_delete": True},
        )
        if result.get("status") == "replayed":
            return result.get("answer") or f"{account} account deleted."
        print(f"[replay] failed: {result.get('error')}; falling back to LLM discovery")

    run_logger.event(type="operator", operator=DELETE_ACCOUNT, mode="discovery")
    return await run_discovery(
        delete_goal,
        browser_manager,
        run_logger,
        finish_run=False,
        task_kind="delete_account",
        allow_delete=True,
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

    def _finish(answer: str, error: str | None = None) -> None:
        if finish_self:
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
            fallback_discovery=True,
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
            _finish(message)
            return message
        if balance is None:
            message = (
                f"I could not read the {account} balance, so the account was not deleted."
            )
            _finish(message, error="UI changed: balance unread")
            return message

        if balance > 0:
            destination_visible = await _account_visible(browser_manager, other)
            print(
                f"The {account} account cannot be deleted with a nonzero balance "
                f"({format_currency(balance)})."
            )
            if not destination_visible:
                message = (
                    f"There is no {other} account to receive the funds. "
                    f"Open a {other} account first. {account} was not deleted."
                )
                _finish(message)
                return message
            # One human confirmation covers transfer (including amounts > $5000) and delete.
            print(
                f"Transfer all {format_currency(balance)} from {account} to {other}, "
                f"then permanently delete the {account} account? (yes/no)"
            )
            try:
                confirmed = ask_yes_no("> ")
            except ConfirmationTimeout as exc:
                message = str(exc)
                answers.append(message)
                _finish(message, error=message)
                return message
            if not confirmed:
                message = (
                    f"{account} account was not deleted: transfer of remaining funds "
                    f"to {other} was declined."
                )
                _finish(message)
                return message
            amount = format_amount(balance)
            print(f"[delete_account] transferring {amount} from {account} to {other}")
            transfer_answer = await run_task(
                _transfer_all_task(account, other, amount),
                browser_manager,
                skip_auth=True,
                run_logger=run_logger,
                own_run=False,
            )
            print(transfer_answer)
            answers.append(transfer_answer)
            if "could not find a transfer amount" in transfer_answer.lower():
                message = f"Transfer failed, so {account} was not deleted."
                _finish(message, error="UI changed")
                return message
            if "human approval was not given" in transfer_answer.lower() or (
                "human did not confirm" in transfer_answer.lower()
            ):
                message = (
                    f"{account} account was not deleted: transfer of remaining funds "
                    f"was declined."
                )
                _finish(message)
                return message
            if "insufficient funds" in transfer_answer.lower():
                message = (
                    f"Transfer failed (insufficient funds), so {account} was not deleted."
                )
                _finish(message, error="UI changed")
                return message
            if "account not found" in transfer_answer.lower() or "do not have a" in transfer_answer.lower():
                message = (
                    f"Transfer failed (account missing), so {account} was not deleted."
                )
                _finish(message)
                return message
            if "transfer to" not in transfer_answer.lower() and "transfer from" not in transfer_answer.lower():
                message = (
                    f"Transfer failed, so {account} was not deleted. {transfer_answer}"
                )
                _finish(message, error="UI changed")
                return message
        else:
            print(
                f"The {account} balance is {format_currency(0)}. "
                f"Delete the {account} account? This process is irreversible. (yes/no)"
            )
            try:
                confirmed = ask_yes_no("> ")
            except ConfirmationTimeout as exc:
                message = str(exc)
                answers.append(message)
                _finish(message, error=message)
                return message
            if not confirmed:
                message = f"{account} account was not deleted."
                _finish(message)
                return message

        print(f"[delete_account] deleting {account}")
        deleted = await _finish_delete(task.goal, account, browser_manager, run_logger)
        answers.append(deleted)
        combined = "\n".join(part for part in answers if part)
        _finish(combined)
        return combined
    except Exception as exc:
        _finish(str(exc), error=str(exc))
        raise
