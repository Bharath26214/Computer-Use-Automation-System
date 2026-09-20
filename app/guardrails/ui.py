from __future__ import annotations

from urllib.parse import urlparse


def _path(url: str) -> str:
    try:
        return (urlparse(url).path or "/").rstrip("/") or "/"
    except Exception:
        return "/"


def expected_page_for_action(action: dict | None) -> str | None:
    """
    Return a route fragment the browser should already be on for this action,
    or None when any authenticated/app page is acceptable.
    """
    action = action or {}
    name = str(action.get("action") or "").strip().lower()
    target = str(action.get("target") or "").strip().lower()

    if name == "navigate":
        return None
    if name == "fill":
        if "user" in target or "member" in target:
            return "/login"
        if any(token in target for token in ("from account", "to account", "amount", "memo")):
            return "/transfer"
        if "account name" in target or target == "use":
            return "/dashboard"
        return None
    if name == "click":
        if "sign in" in target or "log in" in target:
            return "/login"
        if "confirm transfer" in target or "review transfer" in target:
            return "/transfer"
        if "transfer money" in target:
            return None  # usually from dashboard/nav
        if ("open" in target and "account" in target) or (
            "delete" in target and "account" in target
        ):
            return "/dashboard"
        if "transaction" in target:
            return None
        return None
    if name == "read":
        if "transaction" in target:
            return "/transactions"
        if "account" in target or "open-account" in target:
            return "/dashboard"
        return None
    return None


def page_matches(url: str, expected: str | None) -> bool:
    if not expected:
        return True
    path = _path(url).lower()
    want = expected.lower().rstrip("/") or "/"
    return path == want or path.endswith(want)


def ui_page_check(url: str, action: dict | None) -> tuple[bool, str | None, str]:
    """
    Returns (ok, expected_page, message).
    """
    action = action or {}
    name = str(action.get("action") or "").strip().lower()
    target = str(action.get("target") or "").strip()
    expected = expected_page_for_action(action)
    actual = _path(url)
    if page_matches(url, expected):
        return True, expected, f"UI page ok ({actual})"
    return (
        False,
        expected,
        f"UI changed: expected page {expected}, browser is on {actual} "
        f"(route mismatch for {name or 'action'}"
        + (f" → {target}" if target else "")
        + ")",
    )
