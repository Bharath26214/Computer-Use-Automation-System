from __future__ import annotations

ALLOWED_ACTIONS = {
    "click",
    "fill",
    "read",
    "navigate",
    "finish",
    "request_human",
}

SAFE_ACTIONS = {"read", "fill", "navigate", "finish", "request_human"}
REVIEW_CLICKS = {
    "sign in",
    "submit",
    "review transfer",
    "create account",
    "transfer money",
    "confirm transfer",
}
HIGH_RISK_CLICKS = {
    "delete",
    "delete account",
}


def classify_risk(action: dict) -> str:
    name = (action.get("action") or "").strip().lower()
    target = (action.get("target") or "").strip().lower()

    if name in SAFE_ACTIONS:
        return "SAFE"
    if name == "click":
        if any(token in target for token in HIGH_RISK_CLICKS):
            return "HIGH RISK"
        if "open" in target and "account" in target:
            return "REVIEW"
        if any(token in target for token in REVIEW_CLICKS):
            return "REVIEW"
        if "search" in target:
            return "SAFE"
        return "SAFE"
    return "SAFE"


def safety_check(state: dict) -> dict:
    action = state.get("action") or {}
    name = action.get("action")

    if name not in ALLOWED_ACTIONS:
        print("[safety] blocked unknown action")
        return {
            "status": "blocked",
            "error": "Action not allowed",
            "risk_level": "blocked",
            "answer": "Action not allowed.",
        }

    risk = classify_risk(action)
    print(f"[safety] {name} classified as {risk}")
    target = (action.get("target") or "").strip().lower()
    if risk == "HIGH RISK":
        if state.get("allow_delete") and "delete" in target:
            print("[safety] delete allowed after user confirmation")
            return {
                "status": "safety_passed",
                "error": None,
                "risk_level": "REVIEW",
            }
        return {
            "status": "blocked",
            "error": f"High-risk action blocked: {name} {action.get('target') or ''}".strip(),
            "risk_level": risk,
            "answer": (
                "I blocked a high-risk banking action "
                f"({action.get('target') or name}). "
                "Account deletions require an explicit delete_account confirmation."
            ),
        }

    return {
        "status": "safety_passed",
        "error": None,
        "risk_level": risk,
    }
