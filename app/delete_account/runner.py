from __future__ import annotations

import re

from app.agent.act import act as run_act
from app.agent.safety import safety_check
from app.artifact.recorder import current_member_id, find_artifact_by_id, persist_artifact
from app.artifact.replay import run_replay
from app.browser.manager import BrowserManager
from app.create_statement import statement_task
from app.plan import (
    DELETE_ACCOUNT,
    CREATE_STATEMENT,
    LOOKUP_BALANCE,
    TRANSFER_FUNDS,
    PlannedTask,
    account_params,
)
from app.run.confirm import ask_yes_no
from app.run.logger import RunLogger

DELETE_ACCOUNT_STEPS = [
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
        "target": {"strategy": "role", "role": "button", "name": "Dashboard"},
    },
    {
        "id": "step_6",
        "type": "click",
        "target": {"strategy": "role", "role": "button", "name": "Delete {{account}} Account"},
    },
    {
        "id": "step_7",
        "type": "read",
        "target": {"strategy": "testid", "value": "open-account-message"},
    },
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
    required = [LOOKUP_BALANCE, CREATE_STATEMENT, DELETE_ACCOUNT]
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
    delete_goal = goal or f"Delete the {account} account"
    member_id = current_member_id()
    artifact = find_artifact_by_id(DELETE_ACCOUNT, member_id)
    if artifact is not None:
        artifact_ref = f"{artifact.get('artifact_id')}/v{artifact.get('version')}"
        run_logger.note_operator(artifact_ref, created=False)
        run_logger.event(type="operator", operator=artifact_ref, mode="replay")
        result = await run_replay(
            delete_goal,
            artifact,
            browser_manager,
            run_logger,
            skip_auth=True,
        )
        if result.get("status") == "replayed":
            return result.get("answer") or f"{account} account deleted."
        print(f"[replay] failed: {result.get('error')}; falling back to discovery")

    run_logger.event(type="operator", operator=DELETE_ACCOUNT, mode="discovery")
    deleted = await delete_account_in_ui(browser_manager, account)
    path = persist_artifact(
        {
            "goal": delete_goal,
            "recorded_steps": DELETE_ACCOUNT_STEPS,
            "checkpoints": {
                "member_details_displayed": True,
                "account_deleted": True,
            },
        }
    )
    if path is not None:
        run_logger.set_artifact_created(f"{DELETE_ACCOUNT}/v1")
        print(f"Operator: {path}")
    return deleted


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
    # Prefer one shared parent run for multi-step queries. Standalone delete
    # still owns a single composite run for lookup → transfer → statement → delete.
    finish_self = own_run or run_logger is None
    if finish_self:
        kind = "replay" if _operators_ready(member_id, need_transfer=False) else "discovery"
        run_logger = RunLogger(kind, task.goal)
    assert run_logger is not None
    answers: list[str] = []

    def _finish(status: str, error: str | None = None) -> None:
        if finish_self:
            run_logger.finish(status=status, error=error)

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
        if not source_visible and balance is None:
            _finish("failed", f"no {account} account")
            return f"There is no {account} account to delete."
        if balance is None:
            _finish("failed", "balance unread")
            return (
                f"I could not read the {account} balance, so the account was not deleted."
            )

        if balance > 0:
            destination_visible = await _account_visible(browser_manager, other)
            print(
                f"The {account} account cannot be deleted with a nonzero balance "
                f"({format_currency(balance)})."
            )
            if not destination_visible:
                _finish("failed", f"no {other} account")
                return (
                    f"There is no {other} account to receive the funds. "
                    f"Open a {other} account first. {account} was not deleted."
                )
            print(
                f"Transfer all {account} funds to {other}, then delete {account}? "
                "(yes/no)"
            )
            if not ask_yes_no("> "):
                _finish("cancelled")
                return f"{account} account was not deleted."
            print(
                f"This will transfer {format_currency(balance)} from {account} to {other} "
                f"and permanently delete the {account} account. This process is irreversible. "
                "Do you want to continue? (yes/no)"
            )
            if not ask_yes_no("> "):
                _finish("cancelled")
                return f"{account} account was not deleted."
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
                _finish("failed", "transfer amount missing")
                return f"Transfer failed, so {account} was not deleted."
            if "transfer to" not in transfer_answer.lower() and "transfer from" not in transfer_answer.lower():
                _finish("failed", "transfer failed")
                return f"Transfer failed, so {account} was not deleted. {transfer_answer}"
        else:
            print(
                f"The {account} balance is {format_currency(0)}. "
                f"Delete the {account} account? This process is irreversible. (yes/no)"
            )
            if not ask_yes_no("> "):
                _finish("cancelled")
                return f"{account} account was not deleted."

        print(f"[delete_account] creating {account} monthly statement")
        statement_answer = await run_task(
            statement_task(account=account),
            browser_manager,
            True,
            run_logger=run_logger,
            own_run=False,
        )
        print(statement_answer)
        answers.append(statement_answer)
        if "saved" not in statement_answer.lower():
            _finish("failed", "statement failed")
            return f"Could not create a statement, so {account} was not deleted."

        print(f"[delete_account] deleting {account}")
        deleted = await _finish_delete(task.goal, account, browser_manager, run_logger)
        answers.append(deleted)
        _finish("success")
        return "\n".join(part for part in answers if part)
    except Exception as exc:
        _finish("failed", str(exc))
        raise
