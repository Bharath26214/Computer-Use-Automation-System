"""DOM probes that turn page state into outcome evidence signals."""

from __future__ import annotations

from typing import Any


async def _count(page, test_id: str) -> int:
    try:
        return int(await page.get_by_test_id(test_id).count())
    except Exception:
        return 0


async def _visible(page, test_id: str) -> bool:
    try:
        loc = page.get_by_test_id(test_id)
        if await loc.count() == 0:
            return False
        return bool(await loc.first.is_visible())
    except Exception:
        return False


async def _alert_text(page) -> str:
    try:
        alerts = page.locator("[role='alert']")
        n = await alerts.count()
        parts: list[str] = []
        for i in range(min(n, 5)):
            parts.append(await alerts.nth(i).inner_text())
        return "\n".join(parts).lower()
    except Exception:
        return ""


async def observe_dom_signals(
    page,
    *,
    task_kind: str | None = None,
    account: str | None = None,
) -> dict[str, Any]:
    """
    Read bank UI facts for outcome resolution.

    Returns a dict of boolean (and a few string) signals — never an outcome label.
    """
    if page is None:
        return {}

    kind = (task_kind or "").strip().lower()
    signals: dict[str, Any] = {}

    signals["hard_failure"] = await _visible(page, "hard-failure")
    signals["page_not_found"] = await _visible(page, "page-not-found")
    signals["reloading"] = await _visible(page, "reloading")

    alert = await _alert_text(page)
    if alert:
        signals["alert_text"] = alert[:500]
    if "insufficient funds" in alert:
        signals["insufficient_funds_alert"] = True

    signals["transfer_success"] = await _visible(page, "transfer-success")
    signals["transfer_form"] = await _visible(page, "transfer") or await _visible(
        page, "transfer-form"
    )
    signals["transfer_review"] = await _visible(page, "transfer-review")

    checking = await _count(page, "checking-account")
    savings = await _count(page, "savings-account")
    signals["checking_present"] = checking > 0
    signals["savings_present"] = savings > 0
    signals["both_accounts_present"] = checking > 0 and savings > 0
    open_checking = await _count(page, "open-checking-account")
    open_savings = await _count(page, "open-savings-account")
    signals["open_button_present"] = open_checking > 0 or open_savings > 0

    message = ""
    try:
        if await _count(page, "open-account-message") > 0:
            message = (await page.get_by_test_id("open-account-message").inner_text()).lower()
            signals["open_account_message"] = True
            signals["message_text"] = message[:300]
    except Exception:
        pass

    if "deleted" in message:
        signals["account_deleted_message"] = True
    if "opened" in message:
        signals["account_opened_message"] = True
    if "already" in message and "exist" in message:
        signals["account_already_exists_message"] = True
    if "transfer funds approved" in message:
        signals["transfer_before_delete_approved"] = True

    product = (account or "").strip().lower()
    if kind in {"get_balance", "lookup_balance"} and product:
        test_id = "checking-account" if product.startswith("check") else "savings-account"
        if await _count(page, test_id) == 0:
            signals["account_card_missing"] = True
        else:
            signals["balance_visible"] = True
            signals["account_card_present"] = True
    elif kind in {"get_balance", "lookup_balance"}:
        if checking > 0 or savings > 0:
            signals["balance_visible"] = True
            signals["account_card_present"] = True

    if kind == "delete_account" and product:
        test_id = "checking-account" if product.startswith("check") else "savings-account"
        if await _count(page, test_id) == 0:
            signals["account_missing_after_delete"] = True

    if kind == "open_account" and product:
        test_id = "checking-account" if product.startswith("check") else "savings-account"
        if await _count(page, test_id) > 0:
            signals["account_card_present"] = True

    # Drop falsey bools except keep informative strings.
    cleaned: dict[str, Any] = {}
    for key, value in signals.items():
        if isinstance(value, bool):
            if value:
                cleaned[key] = True
        elif value not in (None, "", {}, []):
            cleaned[key] = value
    return cleaned
