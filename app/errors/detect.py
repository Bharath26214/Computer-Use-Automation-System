from __future__ import annotations

import re
from typing import Any

from app.errors.types import ErrorKind
from app.guardrails.ui import _path

RELOADING_HINTS = re.compile(
    r"(reloading|please wait|loading\.\.\.|spinner|still loading|page is loading)",
    re.IGNORECASE,
)
NOT_FOUND_HINTS = re.compile(
    r"(404|page not found|not found|this page doesn.?t exist|cannot (get|find)|err_name_not_resolved)",
    re.IGNORECASE,
)
HARD_FAILURE_HINTS = re.compile(
    r"(cannot be recovered|services are unavailable|hard failure)",
    re.IGNORECASE,
)


async def page_signals(page) -> dict[str, Any]:
    """Collect lightweight URL/title/body hints for classification."""
    url = ""
    title = ""
    text = ""
    ready = ""
    try:
        url = page.url or ""
    except Exception:
        pass
    try:
        title = await page.title()
    except Exception:
        pass
    try:
        ready = await page.evaluate("() => document.readyState")
    except Exception:
        ready = ""
    try:
        text = await page.locator("body").inner_text(timeout=1500)
    except Exception:
        text = ""
    return {
        "url": url,
        "title": title or "",
        "text": (text or "")[:4000],
        "ready_state": ready or "",
        "path": _path(url),
    }


def classify_page_state(signals: dict[str, Any], action: dict | None = None) -> ErrorKind | None:
    """
    Map live page signals to a handled error kind, or None when the page looks usable.

    Handled: reloading | page_not_found | hard_failure
    """
    del action
    path = str(signals.get("path") or "")
    url = str(signals.get("url") or "").lower()
    title = str(signals.get("title") or "")
    text = str(signals.get("text") or "")
    ready = str(signals.get("ready_state") or "").lower()
    title_text = f"{title} {text}"

    if path == "/unavailable" or HARD_FAILURE_HINTS.search(title_text):
        return ErrorKind.HARD_FAILURE
    if NOT_FOUND_HINTS.search(f"{url} {title_text}") or path in {"/404", "/not-found"}:
        return ErrorKind.PAGE_NOT_FOUND
    if "chrome-error://" in url or "about:neterror" in url:
        return ErrorKind.PAGE_NOT_FOUND
    if path == "/reloading" or RELOADING_HINTS.search(title_text):
        return ErrorKind.RELOADING
    if ready in {"loading", "uninitialized"} and len(text.strip()) < 20:
        return ErrorKind.RELOADING
    return None


def classify_exception(exc: BaseException, signals: dict[str, Any] | None = None) -> ErrorKind:
    """Map a Playwright / runtime exception to the closest error kind."""
    text = f"{type(exc).__name__}: {exc}".lower()
    signals = signals or {}
    page_kind = classify_page_state(signals) if signals else None
    if page_kind is not None:
        return page_kind
    if any(token in text for token in ("404", "not found", "err_name_not_resolved", "net::err")):
        return ErrorKind.PAGE_NOT_FOUND
    if any(token in text for token in ("target closed", "browser has been closed", "crashed")):
        return ErrorKind.HARD_FAILURE
    if any(
        token in text
        for token in (
            "timeout",
            "no matching element",
            "strict mode violation",
            "locator.",
            "waiting for",
        )
    ):
        return ErrorKind.HARD_FAILURE
    return ErrorKind.HARD_FAILURE


def ui_mismatch_message(expected: str | None, actual: str | None, detail: str | None = None) -> str:
    expected = expected or "(any page)"
    actual = actual or "(unknown)"
    base = f"UI changed: expected page {expected}, browser is on {actual}"
    if detail:
        return f"{base}. {detail}"
    return base
