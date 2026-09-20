from __future__ import annotations

from typing import Any

from app.browser.manager import BrowserManager
from app.guardrails.business import evaluate_business_rules
from app.guardrails.risk import classify_action_risk
from app.guardrails.types import GuardrailDecision, HITLState, RiskLevel
from app.guardrails.ui import ui_page_check
from app.run.logger import RunLogger


def _path_safe(url: str) -> str:
    from app.guardrails.ui import _path

    return _path(url)

ALLOWED_ACTIONS = {
    "click",
    "fill",
    "read",
    "navigate",
    "finish",
    "request_human",
}

# Actions that always require human approval unless already granted in state.
HITL_TARGETS = (
    "confirm transfer",
    "delete checking account",
    "delete savings account",
    "open checking account",
    "open savings account",
)

LARGE_TRANSFER_THRESHOLD = 5000.0


def _amount_from_state(state: dict[str, Any]) -> float | None:
    params = state.get("params") or {}
    raw = params.get("amount")
    if raw in (None, ""):
        from app.plan import parse_transfer_goal

        raw = parse_transfer_goal(state.get("goal") or "").get("amount")
    text = str(raw or "").replace(",", "").replace("$", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _requires_hitl(action: dict, state: dict[str, Any], risk: RiskLevel) -> bool:
    if state.get("guardrail_approved") or state.get("hitl_approved"):
        return False
    name = str(action.get("action") or "").lower()
    target = str(action.get("target") or "").lower()
    if name != "click":
        return False
    if "delete" in target and "account" in target:
        return not bool(state.get("allow_delete"))
    if "open" in target and "account" in target:
        return not bool(state.get("allow_open"))
    if "confirm transfer" in target:
        if state.get("skip_large_transfer_approval"):
            return False
        amount = _amount_from_state(state)
        # Large transfers always need HITL at confirm; small ones are allow + high risk audit.
        return amount is not None and amount > LARGE_TRANSFER_THRESHOLD
    return False


def _approval_prompt(action: dict, risk: RiskLevel, message: str | None = None) -> str:
    target = action.get("target") or action.get("action") or "this action"
    base = message or f"Guardrail requires approval for {target} (risk={risk.value}). Continue? (yes/no)"
    return base if base.endswith("(yes/no)") or base.endswith("(yes/no) ") else f"{base} (yes/no)"


async def evaluate_guardrails(
    *,
    action: dict,
    browser_manager: BrowserManager | None = None,
    state: dict[str, Any] | None = None,
    run_logger: RunLogger | None = None,
    ask_hitl: bool = True,
) -> GuardrailDecision:
    """
    Single enforcement point for risk, UI page, business rules, and HITL.

    Returns allow / block / require_approval (resolved to allow/block when ask_hitl).
    """
    state = dict(state or {})
    action = dict(action or {})
    name = str(action.get("action") or "").strip().lower()
    target = action.get("target")
    risk = classify_action_risk(action)

    if name and name not in ALLOWED_ACTIONS:
        decision = GuardrailDecision(
            decision=HITLState.BLOCK,
            risk=RiskLevel.HIGH,
            rule="action_not_allowed",
            message=f"Action not allowed: {name}",
            status="blocked",
            action=name,
            target=target,
        )
        _audit(run_logger, decision)
        return decision

    if name in {"finish", "request_human"}:
        decision = GuardrailDecision(
            decision=HITLState.ALLOW,
            risk=risk,
            rule="terminal_action",
            message="Terminal action allowed",
            status="allowed",
            action=name,
            target=target,
        )
        _audit(run_logger, decision)
        return decision

    page = None
    url = ""
    if browser_manager is not None:
        page = browser_manager.page
        if page is None:
            page = await browser_manager.open()
        url = page.url or ""

    ok, expected, ui_message = ui_page_check(url, action)
    if not ok and name != "navigate":
        from app.errors.recover import handle_ui_changed

        event = await handle_ui_changed(
            action=action,
            expected_page=expected,
            actual_page=_path_safe(url),
            run_logger=run_logger,
            checkpoints=state.get("checkpoints"),
        )
        decision = GuardrailDecision(
            decision=HITLState.BLOCK,
            risk=risk,
            rule="ui_page_mismatch",
            message=event.message,
            status="blocked",
            action=name,
            target=target,
            expected_page=expected,
            actual_page=url,
            details={"error_kind": "hard_failure"},
        )
        _audit(run_logger, decision)
        return decision

    if browser_manager is not None:
        business = await evaluate_business_rules(
            browser_manager=browser_manager,
            goal=str(state.get("goal") or ""),
            state=state,
            action=action,
            risk=risk,
        )
        if business is not None:
            business.status = "blocked"
            business.expected_page = expected
            business.actual_page = url
            _audit(run_logger, business)
            return business

    if _requires_hitl(action, state, risk):
        from app.errors.recover import handle_human_intervention

        pending = GuardrailDecision(
            decision=HITLState.REQUIRE_APPROVAL,
            risk=risk,
            rule="hitl_required",
            message=_approval_prompt(action, risk),
            status="require_approval",
            action=name,
            target=target,
            expected_page=expected,
            actual_page=url,
        )
        _audit(run_logger, pending)
        if not ask_hitl:
            return pending
        hitl = await handle_human_intervention(
            prompt=pending.message,
            action=action,
            run_logger=run_logger,
            checkpoints=state.get("checkpoints"),
        )
        if hitl.status.value == "approved":
            decision = GuardrailDecision(
                decision=HITLState.ALLOW,
                risk=risk,
                rule="hitl_approved",
                message="Human intervention: approved",
                status="allowed",
                action=name,
                target=target,
                expected_page=expected,
                actual_page=url,
            )
            _audit(run_logger, decision)
            return decision
        if hitl.status.value == "rejected":
            decision = GuardrailDecision(
                decision=HITLState.BLOCK,
                risk=risk,
                rule="hitl_denied",
                message="Human intervention: rejected",
                status="blocked",
                action=name,
                target=target,
                expected_page=expected,
                actual_page=url,
            )
            _audit(run_logger, decision)
            return decision
        decision = GuardrailDecision(
            decision=HITLState.BLOCK,
            risk=risk,
            rule="hitl_timeout",
            message=hitl.message,
            status="blocked",
            action=name,
            target=target,
            expected_page=expected,
            actual_page=url,
        )
        _audit(run_logger, decision)
        return decision

    decision = GuardrailDecision(
        decision=HITLState.ALLOW,
        risk=risk,
        rule="pass",
        message=ui_message,
        status="allowed",
        action=name,
        target=target,
        expected_page=expected,
        actual_page=url,
    )
    _audit(run_logger, decision)
    return decision


def _audit(run_logger: RunLogger | None, decision: GuardrailDecision) -> None:
    print(
        f"[guardrail] {decision.decision.value} risk={decision.risk.value} "
        f"rule={decision.rule} action={decision.action} target={decision.target}"
    )
    if run_logger is not None:
        run_logger.log_guardrail(decision)


async def enforce_or_raise(
    *,
    action: dict,
    browser_manager: BrowserManager | None = None,
    state: dict[str, Any] | None = None,
    run_logger: RunLogger | None = None,
) -> GuardrailDecision:
    """Enforce guardrails; raise RuntimeError on block so callers cannot ignore."""
    decision = await evaluate_guardrails(
        action=action,
        browser_manager=browser_manager,
        state=state,
        run_logger=run_logger,
        ask_hitl=True,
    )
    if decision.blocked():
        raise RuntimeError(decision.message)
    return decision
