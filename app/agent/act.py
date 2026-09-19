from __future__ import annotations

from app.browser.manager import BrowserManager

BOTH_ACCOUNTS_EXIST = (
    "You already have Checking and Savings accounts. Additional accounts are not allowed."
)


async def _both_products_open(page) -> bool:
    try:
        checking = await page.get_by_test_id("checking-account").count()
        savings = await page.get_by_test_id("savings-account").count()
    except Exception:
        return False
    return checking > 0 and savings > 0


async def _product_from_goal(goal: str) -> str | None:
    text = (goal or "").lower()
    if "checking" in text:
        return "checking"
    if "saving" in text:
        return "savings"
    return None


async def _open_fields_already_open(page, target: str, goal: str) -> str | None:
    lower = (target or "").strip().lower()
    if lower not in {"account name", "use"}:
        return None
    try:
        if await page.get_by_label(target).count() > 0:
            return None
    except Exception:
        pass
    if await _both_products_open(page):
        return BOTH_ACCOUNTS_EXIST
    kind = await _product_from_goal(goal)
    kinds = [kind] if kind else ["checking", "savings"]
    for item in kinds:
        try:
            if await page.get_by_test_id(f"{item}-account").count() > 0:
                return f"{item.title()} account already exists"
        except Exception:
            continue
    return None


async def _account_already_open(page, target: str) -> str | None:
    lower = (target or "").lower()
    if "open" not in lower or "account" not in lower:
        return None
    if "checking" in lower:
        kind = "checking"
    elif "saving" in lower:
        kind = "savings"
    else:
        return None
    if await _both_products_open(page):
        return BOTH_ACCOUNTS_EXIST
    try:
        if await page.get_by_test_id(f"{kind}-account").count() > 0:
            return f"{kind.title()} account already exists"
    except Exception:
        return None
    return None


async def act(state: dict, browser_manager: BrowserManager) -> dict:
    action = state.get("action") or {}
    page = browser_manager.page
    if page is None:
        page = await browser_manager.open()

    name = action.get("action")
    target = action.get("target")
    value = action.get("value") or ""
    outputs = dict(state.get("outputs") or {})
    result = ""

    try:
        if name == "navigate":
            if not target:
                raise ValueError("navigate requires a target URL")
            await page.goto(target, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle")
            result = f"Navigated to {page.url}"

        elif name == "fill":
            if not target:
                raise ValueError("fill requires a target field")
            skipped = await _open_fields_already_open(
                page,
                target,
                str(state.get("goal") or ""),
            )
            if skipped:
                result = skipped
            else:
                try:
                    locator = page.get_by_label(target)
                except Exception:
                    locator = await browser_manager.locate_fillable(target)
                tag = ""
                try:
                    tag = await locator.first.evaluate("el => el.tagName")
                except Exception:
                    locator = await browser_manager.locate_fillable(target)
                    tag = await locator.first.evaluate("el => el.tagName")
                if str(tag).upper() == "SELECT":
                    try:
                        await locator.first.select_option(label=value)
                    except Exception:
                        await locator.first.select_option(value=value)
                else:
                    try:
                        await locator.first.fill(value)
                    except Exception:
                        fillable = await browser_manager.locate_fillable(target)
                        await fillable.fill(value)
                result = f"Filled {target}"

        elif name == "click":
            if not target:
                raise ValueError("click requires a target")
            clicked = False
            aliases = {
                "transactions": "nav-transactions",
                "dashboard": "nav-dashboard",
                "transfer money": "transfer-money",
                "review transfer": "review-transfer",
                "confirm transfer": "confirm-transfer",
                "open checking account": "open-checking-account",
                "open savings account": "open-savings-account",
                "delete checking account": "delete-checking-account",
                "delete savings account": "delete-savings-account",
            }
            test_id = aliases.get(target.lower())
            for locator in [
                page.get_by_test_id(test_id) if test_id else None,
                page.get_by_test_id("nav-transfer") if target.lower() == "transfer money" else None,
                page.get_by_role("button", name=target),
                page.get_by_role("link", name=target),
            ]:
                if locator is None:
                    continue
                try:
                    await locator.first.click(timeout=2500)
                    clicked = True
                    break
                except Exception:
                    continue
            if not clicked:
                already = await _account_already_open(page, target)
                if already:
                    result = already
                else:
                    locator = await browser_manager.locate_clickable(target)
                    await locator.click(timeout=2500)
                    result = f"Clicked {target}"
            else:
                result = f"Clicked {target}"
            if result.startswith("Clicked"):
                await page.wait_for_load_state("networkidle")
                if "confirm transfer" in target.lower():
                    try:
                        await page.get_by_test_id("transfer-success").wait_for(
                            state="visible",
                            timeout=8000,
                        )
                    except Exception:
                        pass
                if "open" in target.lower() and "account" in target.lower():
                    try:
                        await page.get_by_test_id("open-account-message").wait_for(
                            state="visible",
                            timeout=4000,
                        )
                    except Exception:
                        pass
                if "delete" in target.lower() and "account" in target.lower():
                    try:
                        await page.get_by_test_id("open-account-message").wait_for(
                            state="visible",
                            timeout=4000,
                        )
                    except Exception:
                        pass

        elif name == "read":
            if not target:
                text = await page.locator("body").inner_text()
                outputs["page"] = text
            else:
                try:
                    text = await page.get_by_test_id(target).inner_text()
                except Exception:
                    try:
                        text = await page.get_by_text(target, exact=False).first.inner_text()
                    except Exception:
                        if "open-account" in str(target).lower():
                            text = ""
                            for test_id in ("open-account-message", "checking-account", "savings-account"):
                                try:
                                    if await page.get_by_test_id(test_id).count() > 0:
                                        text = await page.get_by_test_id(test_id).inner_text()
                                        if text:
                                            break
                                except Exception:
                                    continue
                            if not text:
                                locator = await browser_manager.locate(target)
                                text = await locator.inner_text()
                        else:
                            locator = await browser_manager.locate(target)
                            text = await locator.inner_text()
                outputs[target] = text
            result = (text or "").strip()

        else:
            result = f"No browser step for {name}"
    except Exception as exc:
        already = None
        if page is not None:
            if name == "click":
                already = await _account_already_open(page, target or "")
            elif name == "fill":
                already = await _open_fields_already_open(
                    page,
                    target or "",
                    str(state.get("goal") or ""),
                )
        result = already or f"Action failed: {exc}"

    log = list(state.get("action_log") or [])
    log.append(" ".join(part for part in [name, target or "", value] if part))
    print(f"[act] {result[:200]}")
    return {
        "outputs": outputs,
        "last_result": result,
        "action_log": log,
        "status": "acting",
    }
