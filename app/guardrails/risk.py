from __future__ import annotations

from app.guardrails.types import RiskLevel


def classify_action_risk(action: dict | None) -> RiskLevel:
    """
    Risk factor for every browser interaction.

    navigation / read → low
    form fills, review → medium
    confirm transfer / delete / open account → high
    """
    action = action or {}
    name = str(action.get("action") or "").strip().lower()
    target = str(action.get("target") or "").strip().lower()

    if name in {"finish", "request_human"}:
        return RiskLevel.LOW
    if name in {"navigate", "read"}:
        return RiskLevel.LOW
    if name == "fill":
        if "amount" in target:
            return RiskLevel.MEDIUM
        if "user" in target or "member" in target:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
    if name == "click":
        if "confirm transfer" in target:
            return RiskLevel.HIGH
        if "delete" in target and "account" in target:
            return RiskLevel.HIGH
        if "open" in target and "account" in target:
            return RiskLevel.HIGH
        if "review transfer" in target:
            return RiskLevel.MEDIUM
        if "transfer money" in target:
            return RiskLevel.MEDIUM
        if "sign in" in target or "log in" in target:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
    return RiskLevel.MEDIUM
