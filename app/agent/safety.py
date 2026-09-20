from __future__ import annotations

from app.guardrails.engine import evaluate_guardrails
from app.guardrails.risk import classify_action_risk
from app.guardrails.types import HITLState


# Back-compat exports used by older call sites.
ALLOWED_ACTIONS = {
    "click",
    "fill",
    "read",
    "navigate",
    "finish",
    "request_human",
}


def classify_risk(action: dict) -> str:
    """Legacy string risk labels for older printers."""
    level = classify_action_risk(action)
    return {
        "low": "SAFE",
        "medium": "REVIEW",
        "high": "HIGH RISK",
    }.get(level.value, "SAFE")


def safety_check(state: dict) -> dict:
    """
    Sync shim. Prefer async evaluate_guardrails at the execution layer.
    Unknown actions are blocked immediately; other checks run in act/replay.
    """
    action = state.get("action") or {}
    name = action.get("action")
    if name not in ALLOWED_ACTIONS:
        print("[safety] blocked unknown action")
        return {
            "status": "blocked",
            "error": "Action not allowed",
            "risk_level": "blocked",
            "answer": "Action not allowed.",
            "guardrail_decision": HITLState.BLOCK.value,
        }
    risk = classify_risk(action)
    print(f"[safety] {name} classified as {risk}")
    return {
        "status": "safety_passed",
        "error": None,
        "risk_level": risk,
        "guardrail_decision": HITLState.ALLOW.value,
    }


async def async_safety_check(state: dict, browser_manager=None, run_logger=None) -> dict:
    """Execution-layer guardrail enforcement used by the agent graph."""
    action = state.get("action") or {}
    decision = await evaluate_guardrails(
        action=action,
        browser_manager=browser_manager,
        state=state,
        run_logger=run_logger,
        ask_hitl=True,
    )
    if decision.blocked():
        return {
            "status": "blocked",
            "error": decision.message,
            "risk_level": decision.risk.value,
            "answer": decision.message,
            "guardrail_decision": decision.decision.value,
            "guardrail_rule": decision.rule,
        }
    return {
        "status": "safety_passed",
        "error": None,
        "risk_level": decision.risk.value,
        "guardrail_decision": decision.decision.value,
        "guardrail_rule": decision.rule,
    }
