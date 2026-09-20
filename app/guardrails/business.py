from __future__ import annotations

from typing import Any

from app.browser.accounts import (
    account_is_open,
    missing_account_message,
    product_key,
    read_account_balance,
)
from app.browser.manager import BrowserManager
from app.guardrails.types import GuardrailDecision, HITLState, RiskLevel


def _parse_amount(value: object) -> float | None:
    raw = str(value or "").replace(",", "").replace("$", "").strip()
    if not raw:
        return None
    try:
        return round(float(raw), 2)
    except ValueError:
        return None


def _task_params(goal: str, state: dict[str, Any]) -> dict[str, Any]:
    params = dict(state.get("params") or {})
    if params.get("from_account") or params.get("amount"):
        return params
    # Lazy import to avoid circular deps with runners.
    from app.plan import parse_transfer_goal, plan_query

    tasks = plan_query(goal)
    if tasks and tasks[0].params:
        return dict(tasks[0].params)
    parsed = parse_transfer_goal(goal)
    return {key: value for key, value in parsed.items() if value not in (None, "")}


async def check_open_account_exists(
    browser_manager: BrowserManager,
    goal: str,
    action: dict,
    risk: RiskLevel,
) -> GuardrailDecision | None:
    target = str(action.get("target") or "")
    name = str(action.get("action") or "").lower()
    lower = target.lower()
    opening = name == "click" and "open" in lower and "account" in lower
    filling = name == "fill" and (
        "account name" in lower or lower.strip() == "use"
    )
    if not (opening or filling):
        return None

    account = "Checking"
    if "saving" in lower:
        account = "Savings"
    else:
        text = (goal or "").lower()
        if "saving" in text:
            account = "Savings"
        elif "checking" in text:
            account = "Checking"

    if await account_is_open(browser_manager, account):
        return GuardrailDecision(
            decision=HITLState.BLOCK,
            risk=risk,
            rule="create_account_exists",
            message=f"You already have a {account} account.",
            action=name,
            target=target,
            details={"account": account},
        )
    checking = await account_is_open(browser_manager, "Checking")
    savings = await account_is_open(browser_manager, "Savings")
    if checking and savings:
        return GuardrailDecision(
            decision=HITLState.BLOCK,
            risk=risk,
            rule="create_account_exists",
            message=(
                "You already have Checking and Savings accounts. "
                "Additional accounts are not allowed."
            ),
            action=name,
            target=target,
            details={"account": account},
        )
    return None


async def check_delete_account_missing(
    browser_manager: BrowserManager,
    goal: str,
    action: dict,
    risk: RiskLevel,
) -> GuardrailDecision | None:
    target = str(action.get("target") or "")
    name = str(action.get("action") or "").lower()
    lower = target.lower()
    if not (name == "click" and "delete" in lower and "account" in lower):
        return None

    if "saving" in lower:
        account = "Savings"
    elif "checking" in lower:
        account = "Checking"
    else:
        text = (goal or "").lower()
        account = "Savings" if "saving" in text else "Checking"

    if not await account_is_open(browser_manager, account):
        return GuardrailDecision(
            decision=HITLState.BLOCK,
            risk=risk,
            rule="delete_account_not_exist",
            message=f"There is no {account} account to delete.",
            action=name,
            target=target,
            details={"account": account},
        )
    return None


async def check_transfer_accounts_and_funds(
    browser_manager: BrowserManager,
    goal: str,
    state: dict[str, Any],
    action: dict,
    risk: RiskLevel,
) -> GuardrailDecision | None:
    name = str(action.get("action") or "").lower()
    target = str(action.get("target") or "").lower()
    relevant = (
        (name == "click" and "confirm transfer" in target)
        or (name == "click" and "review transfer" in target)
        or (name == "fill" and "amount" in target)
    )
    if not relevant:
        return None

    params = _task_params(goal, state)
    source = str(params.get("from_account") or "Savings")
    destination = str(params.get("to_account") or "Checking")
    amount = _parse_amount(params.get("amount") or action.get("value"))

    if not await account_is_open(browser_manager, source):
        key = product_key(source)
        label = "Checking" if key == "checking" else "Savings"
        return GuardrailDecision(
            decision=HITLState.BLOCK,
            risk=risk,
            rule="transfer_account_not_found",
            message=(
                f"{label} account not found. {missing_account_message(label)} "
                "Transfer was not completed."
            ),
            action=name,
            target=action.get("target"),
            details={"from_account": source, "to_account": destination},
        )
    if not await account_is_open(browser_manager, destination):
        key = product_key(destination)
        label = "Checking" if key == "checking" else "Savings"
        return GuardrailDecision(
            decision=HITLState.BLOCK,
            risk=risk,
            rule="transfer_account_not_found",
            message=(
                f"{label} account not found. {missing_account_message(label)} "
                "Transfer was not completed."
            ),
            action=name,
            target=action.get("target"),
            details={"from_account": source, "to_account": destination},
        )

    if amount is not None:
        balance = await read_account_balance(browser_manager, source)
        if balance is not None and amount > balance + 1e-9:
            return GuardrailDecision(
                decision=HITLState.BLOCK,
                risk=risk,
                rule="insufficient_funds",
                message=(
                    f"Insufficient funds in {source} account "
                    f"(available ${balance:,.2f}, requested ${amount:,.2f}). "
                    "Transfer was not completed."
                ),
                action=name,
                target=action.get("target"),
                details={
                    "from_account": source,
                    "amount": amount,
                    "available": balance,
                },
            )
    return None


async def evaluate_business_rules(
    *,
    browser_manager: BrowserManager,
    goal: str,
    state: dict[str, Any],
    action: dict,
    risk: RiskLevel,
) -> GuardrailDecision | None:
    """Run domain checks; first blocking rule wins."""
    result = await check_open_account_exists(browser_manager, goal, action, risk)
    if result is not None:
        return result
    result = await check_delete_account_missing(browser_manager, goal, action, risk)
    if result is not None:
        return result
    return await check_transfer_accounts_and_funds(
        browser_manager, goal, state, action, risk
    )


async def preflight_transfer_business(
    browser_manager: BrowserManager,
    *,
    from_account: str,
    to_account: str,
    amount: float | None,
) -> GuardrailDecision | None:
    """Standalone transfer preflight used by the transfer runner."""
    fake_action = {"action": "click", "target": "Review Transfer"}
    state = {
        "params": {
            "from_account": from_account,
            "to_account": to_account,
            "amount": amount,
        }
    }
    return await check_transfer_accounts_and_funds(
        browser_manager,
        goal=f"Transfer {amount} from {from_account} to {to_account}",
        state=state,
        action=fake_action,
        risk=RiskLevel.HIGH,
    )
