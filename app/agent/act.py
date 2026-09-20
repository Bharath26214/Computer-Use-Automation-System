from __future__ import annotations

from app.browser.manager import BrowserManager

BOTH_ACCOUNTS_EXIST = (
    "You already have Checking and Savings accounts. Additional accounts are not allowed."
)


def _reject_coordinates(action: dict) -> None:
    """Hard rule: Playwright must drive the DOM, never x/y click points."""
    target = action.get("target")
    if isinstance(target, dict) and ("x" in target or "y" in target or "coordinates" in target):
        raise ValueError(
            "Coordinate clicks are not supported; artifacts must use DOM locators "
            "(testid, role, label)."
        )
    for key in ("x", "y", "coordinates", "position"):
        if key in action and action.get(key) not in (None, ""):
            raise ValueError(
                "Coordinate clicks are not supported; artifacts must use DOM locators "
                "(testid, role, label)."
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


async def _click_dom(locator, timeout: int = 2500) -> None:
    await BrowserManager.ensure_in_view(locator)
    await locator.click(timeout=timeout)


async def act(state: dict, browser_manager: BrowserManager) -> dict:
    action = state.get("action") or {}
    page = browser_manager.page
    if page is None:
        page = await browser_manager.open()

    name = action.get("action")
    target = action.get("target")
    value = action.get("value") or ""
    strategy = str(action.get("strategy") or "").strip().lower() or None
    role = action.get("role")
    outputs = dict(state.get("outputs") or {})
    result = ""

    # Hard enforcement at act: always run unless safety already cleared this action.
    from app.guardrails.engine import evaluate_guardrails
    from app.guardrails.risk import classify_action_risk
    from app.guardrails.types import GuardrailDecision, HITLState

    if state.get("guardrails_already_checked"):
        decision = GuardrailDecision(
            decision=HITLState.ALLOW,
            risk=classify_action_risk(action),
            rule="prechecked",
            message="Already cleared by safety node",
            status="allowed",
            action=name,
            target=target,
        )
    else:
        decision = await evaluate_guardrails(
            action=action,
            browser_manager=browser_manager,
            state=state,
            run_logger=state.get("run_logger"),
            ask_hitl=True,
        )
    if decision.blocked():
        log = list(state.get("action_log") or [])
        log.append(" ".join(part for part in [name, target or "", "BLOCKED"] if part))
        print(f"[act] blocked by guardrail: {decision.message[:200]}")
        return {
            "outputs": outputs,
            "last_result": decision.message,
            "action_log": log,
            "status": "blocked",
            "risk_level": decision.risk.value,
            "guardrail_decision": decision.decision.value,
            "answer": decision.message,
        }

    error_events = list(state.get("error_events") or [])

    async def _execute_once() -> str:
        nonlocal outputs
        _reject_coordinates(action)
        local_result = ""

        if name == "navigate":
            if not target:
                raise ValueError("navigate requires a target URL")
            await page.goto(target, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle")
            return f"Navigated to {page.url}"

        if name == "fill":
            if not target:
                raise ValueError("fill requires a target field")
            skipped = await _open_fields_already_open(
                page,
                target,
                str(state.get("goal") or ""),
            )
            if skipped:
                return skipped
            if strategy in {"label", "testid", "placeholder", "role"}:
                locator = await browser_manager.locate_by_strategy(
                    strategy=strategy,
                    value=str(target),
                    role=role or "textbox",
                )
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
            target_locator = locator.first
            await BrowserManager.ensure_in_view(target_locator)
            if str(tag).upper() == "SELECT":
                try:
                    await target_locator.select_option(label=value)
                except Exception:
                    await target_locator.select_option(value=value)
            else:
                try:
                    await target_locator.fill(value)
                except Exception:
                    fillable = await browser_manager.locate_fillable(target)
                    await BrowserManager.ensure_in_view(fillable)
                    await fillable.fill(value)
            return f"Filled {target}"

        if name == "click":
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
            test_id = aliases.get(str(target).lower())
            candidates = []
            if strategy:
                try:
                    candidates.append(
                        await browser_manager.locate_by_strategy(
                            strategy=strategy,
                            value=str(target),
                            role=role or "button",
                        )
                    )
                except Exception:
                    pass
            candidates.extend(
                [
                    page.get_by_test_id(test_id) if test_id else None,
                    page.get_by_test_id("nav-transfer")
                    if str(target).lower() == "transfer money"
                    else None,
                    page.get_by_role("button", name=target),
                    page.get_by_role("link", name=target),
                ]
            )
            for locator in candidates:
                if locator is None:
                    continue
                try:
                    await _click_dom(locator.first)
                    clicked = True
                    break
                except Exception:
                    continue
            if not clicked:
                already = await _account_already_open(page, target)
                if already:
                    return already
                locator = await browser_manager.locate_clickable(target)
                await _click_dom(locator)
                local_result = f"Clicked {target}"
            else:
                local_result = f"Clicked {target}"
            if local_result.startswith("Clicked"):
                await page.wait_for_load_state("networkidle")
                if "confirm transfer" in str(target).lower():
                    try:
                        await page.get_by_test_id("transfer-success").wait_for(
                            state="visible",
                            timeout=8000,
                        )
                    except Exception:
                        pass
                if "open" in str(target).lower() and "account" in str(target).lower():
                    try:
                        await page.get_by_test_id("open-account-message").wait_for(
                            state="visible",
                            timeout=4000,
                        )
                    except Exception:
                        pass
                if "delete" in str(target).lower() and "account" in str(target).lower():
                    try:
                        await page.get_by_test_id("open-account-message").wait_for(
                            state="visible",
                            timeout=4000,
                        )
                    except Exception:
                        pass
            return local_result

        if name == "read":
            if not target:
                text = await page.locator("body").inner_text()
                outputs["page"] = text
            else:
                text = ""
                if strategy in {"testid", "label", "role", "text"}:
                    try:
                        locator = await browser_manager.locate_by_strategy(
                            strategy=strategy,
                            value=str(target),
                            role=role,
                        )
                        await BrowserManager.ensure_in_view(locator)
                        text = await locator.inner_text()
                    except Exception:
                        text = ""
                if not text:
                    try:
                        locator = page.get_by_test_id(target)
                        await BrowserManager.ensure_in_view(locator.first)
                        text = await locator.inner_text()
                    except Exception:
                        try:
                            locator = page.get_by_text(target, exact=False).first
                            await BrowserManager.ensure_in_view(locator)
                            text = await locator.inner_text()
                        except Exception:
                            if "open-account" in str(target).lower():
                                text = ""
                                for test_id in (
                                    "open-account-message",
                                    "checking-account",
                                    "savings-account",
                                ):
                                    try:
                                        if await page.get_by_test_id(test_id).count() > 0:
                                            loc = page.get_by_test_id(test_id)
                                            await BrowserManager.ensure_in_view(loc.first)
                                            text = await loc.inner_text()
                                            if text:
                                                break
                                    except Exception:
                                        continue
                                if not text:
                                    locator = await browser_manager.locate(target)
                                    await BrowserManager.ensure_in_view(locator)
                                    text = await locator.inner_text()
                            else:
                                locator = await browser_manager.locate(target)
                                await BrowserManager.ensure_in_view(locator)
                                text = await locator.inner_text()
                outputs[target] = text
            return (text or "").strip()

        return f"No browser step for {name}"

    from app.errors.recover import execute_with_recovery

    result, recovered_events, fatal = await execute_with_recovery(
        page=page,
        action=action,
        execute=_execute_once,
        run_logger=state.get("run_logger"),
        checkpoints=state.get("checkpoints"),
    )
    error_events.extend(recovered_events)

    # Business soft-fails (already exists) should not be treated as fatal UI errors.
    if fatal and result and not any(
        token in result.lower()
        for token in ("already exist", "additional accounts", "human intervention")
    ):
        # Keep Action-failed style for classify_run / verify when recovery exhausted.
        if not result.lower().startswith("ui changed") and "cannot be recovered" not in result.lower():
            if not result.startswith("Action failed"):
                pass

    log = list(state.get("action_log") or [])
    log.append(" ".join(part for part in [name, target or "", value] if part))
    print(f"[act] {result[:200]}")
    status = "blocked" if fatal else "acting"
    payload = {
        "outputs": outputs,
        "last_result": result,
        "action_log": log,
        "status": status,
        "risk_level": decision.risk.value,
        "guardrail_decision": decision.decision.value,
        "error_events": error_events,
    }
    if fatal:
        payload["answer"] = result
        payload["error"] = result
    return payload
