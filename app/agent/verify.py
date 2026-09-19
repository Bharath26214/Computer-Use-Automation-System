from __future__ import annotations

import re

from app.browser.manager import BrowserManager


async def _is_visible(page, text: str) -> bool:
    try:
        locator = page.get_by_text(text, exact=False)
        if await locator.count() == 0:
            return False
        return await locator.first.is_visible()
    except Exception:
        return False


async def verify(state: dict, browser_manager: BrowserManager) -> dict:
    page = browser_manager.page
    if page is None:
        return {
            "checkpoint_passed": False,
            "status": "verify_failed",
        }

    checkpoints = dict(state.get("checkpoints") or {})
    outputs = state.get("outputs") or {}
    action = state.get("action") or {}
    url = page.url

    if await _is_visible(page, "Sign In") or "/login" in url:
        checkpoints["member_search_page_loaded"] = await _is_visible(page, "Sign In") or await _is_visible(
            page, "Username"
        )

    if "/dashboard" in url or await _is_visible(page, "Welcome back") or await _is_visible(page, "Dashboard"):
        checkpoints["member_details_displayed"] = True

    visible_output = " ".join(str(value) for value in outputs.values())
    if await _is_visible(page, "Savings Account") or "Savings" in visible_output:
        checkpoints["savings_account_displayed"] = True
    if await _is_visible(page, "Checking Account") or "Checking" in visible_output:
        checkpoints["checking_account_displayed"] = True

    if re.search(r"\$[\d,]+(?:\.\d{2})?", visible_output) or re.search(
        r"\$[\d,]+(?:\.\d{2})?",
        str(state.get("last_result") or ""),
    ):
        checkpoints["balance_extracted"] = True

    if "/transfer" in url or await _is_visible(page, "From Account"):
        checkpoints["transfer_form_visible"] = True
    if await _is_visible(page, "Transfer Review"):
        checkpoints["transfer_review_visible"] = True
    if await _is_visible(page, "Transfer Successful") or await _is_visible(page, "Transfer ID"):
        checkpoints["transfer_success_visible"] = True
    if "transfer-id" in outputs or re.search(r"TXN|TRF|transfer", visible_output, re.IGNORECASE):
        checkpoints["transfer_id_extracted"] = True
    if "/transactions" in url or await _is_visible(page, "Search transactions"):
        checkpoints["transactions_visible"] = True

    last_result = str(state.get("last_result") or "")
    if (
        await _is_visible(page, "account opened")
        or "already exists" in last_result.lower()
        or "account opened" in last_result.lower()
        or "open-account-message" in outputs
    ):
        checkpoints["account_opened"] = True
    if (
        "account deleted" in last_result.lower()
        or await _is_visible(page, "account deleted")
    ):
        checkpoints["account_deleted"] = True

    if action.get("action") == "finish" and (
        checkpoints.get("balance_extracted")
        or checkpoints.get("transfer_success_visible")
        or checkpoints.get("account_opened")
    ):
        checkpoints["task_completed"] = True

    expected = True
    name = action.get("action")
    target = (action.get("target") or "").lower()
    if str(state.get("last_result") or "").startswith("Action failed"):
        expected = False
    elif name == "navigate":
        expected = "about:blank" not in url
    elif name == "click" and "sign in" in target:
        expected = bool(checkpoints.get("member_details_displayed"))
    elif name == "click" and "delete" in target and "account" in target:
        expected = bool(
            checkpoints.get("account_deleted")
            or "deleted" in last_result.lower()
            or "cannot be deleted" in last_result.lower()
        )
    elif name == "click" and "open" in target and "account" in target:
        expected = bool(
            checkpoints.get("account_opened")
            or ("checking" in target and checkpoints.get("checking_account_displayed"))
            or ("saving" in target and checkpoints.get("savings_account_displayed"))
            or "already" in last_result.lower()
            or "opened" in last_result.lower()
        )
    elif name == "click" and "transfer money" in target:
        expected = bool(checkpoints.get("transfer_form_visible")) or "/transfer" in url
    elif name == "click" and "review transfer" in target:
        expected = bool(checkpoints.get("transfer_review_visible"))
    elif name == "click" and "confirm transfer" in target:
        expected = bool(checkpoints.get("transfer_success_visible"))
    elif name == "click" and "transaction" in target:
        expected = bool(checkpoints.get("transactions_visible"))
    elif name == "click" and "dashboard" in target:
        expected = bool(checkpoints.get("member_details_displayed")) or "/dashboard" in url
    elif name == "read" and "open-account" in target:
        expected = bool(last_result.strip())
    elif name == "read" and "saving" in target:
        expected = bool(checkpoints.get("savings_account_displayed") and checkpoints.get("balance_extracted"))
    elif name == "read" and "checking" in target:
        expected = bool(checkpoints.get("checking_account_displayed") and checkpoints.get("balance_extracted"))
    elif name == "read" and ("transfer" in target or "transaction" in target):
        expected = True
    elif name == "fill":
        expected = True

    print(f"[verify] passed={expected} checkpoints={checkpoints}")
    return {
        "checkpoints": checkpoints,
        "checkpoint_passed": expected,
        "status": "verified" if expected else "verify_failed",
    }
