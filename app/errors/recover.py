from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from app.errors.detect import (
    classify_exception,
    page_signals,
    ui_mismatch_message,
)
from app.errors.types import (
    ERROR_POLICIES,
    ErrorKind,
    RecoveryStatus,
    RuntimeErrorEvent,
)
from app.guardrails.ui import expected_page_for_action
from app.run.confirm import (
    ConfirmationTimeout,
    ask_browser_handoff,
    confirmation_label,
)
from app.run.logger import RunLogger
from app.run.screenshots import capture_run_screenshot

ExecuteFn = Callable[[], Awaitable[str]]


async def _log_event(run_logger: RunLogger | None, event: RuntimeErrorEvent) -> None:
    print(
        f"[error] {event.kind.value} status={event.status.value} "
        f"attempt={event.attempt} {event.message[:180]}"
    )
    if run_logger is not None:
        run_logger.log_error_event(event)


async def save_mid_run_checkpoint(
    run_logger: RunLogger | None,
    *,
    checkpoints: dict[str, Any] | None,
    event: RuntimeErrorEvent,
) -> None:
    """Persist whatever checkpoints we have when an error interrupts the flow."""
    if run_logger is None:
        return
    run_logger.save_checkpoint_snapshot(
        checkpoints=checkpoints or {},
        error=event.to_dict(),
    )


async def handle_human_intervention(
    *,
    prompt: str,
    action: dict | None = None,
    run_logger: RunLogger | None = None,
    checkpoints: dict[str, Any] | None = None,
) -> RuntimeErrorEvent:
    """
    Browser handoff on the app confirmation page.

    Human clicks Yes, Confirm / Confirm Transfer in the browser, then types resume.
    With --yes the agent clicks instead. With --no / abort the action is blocked.
    """
    action = action or {}
    target = str(action.get("target") or action.get("action") or "Yes, Confirm")
    label = confirmation_label(target)
    instruction = (
        prompt
        if prompt and ("browser" in prompt.lower() or "resume" in prompt.lower())
        else (
            f"Confirmation page open: click “{label}” in the browser, then type resume."
        )
    )
    event = RuntimeErrorEvent(
        kind=ErrorKind.HUMAN_INTERVENTION,
        message=instruction,
        status=RecoveryStatus.RETRYING,
        action=action.get("action"),
        target=action.get("target"),
    )
    await _log_event(run_logger, event)
    try:
        approved = ask_browser_handoff(label)
    except ConfirmationTimeout as exc:
        event.status = RecoveryStatus.TERMINAL
        event.message = str(exc)
        event.kind = ErrorKind.HARD_FAILURE
        event.details = {"reason": "hitl_timeout"}
        await _log_event(run_logger, event)
        await save_mid_run_checkpoint(run_logger, checkpoints=checkpoints, event=event)
        return event

    if approved:
        auto = None
        try:
            from app.run.confirm import auto_confirm_reply

            auto = auto_confirm_reply()
        except Exception:
            auto = None
        if auto is True:
            # --yes: agent will click the confirmation control.
            event.status = RecoveryStatus.APPROVED
            event.message = f"Auto-yes: agent will click “{label}”"
            event.details = {"confirmation": "auto_yes", "handoff": "agent_clicks"}
            await _log_event(run_logger, event)
            return event
        # Human already clicked in the browser — caller must not re-click.
        event.status = RecoveryStatus.APPROVED
        event.message = f"Human completed “{label}” in the browser"
        event.details = {"confirmation": "resume", "handoff": "human_clicked"}
        await _log_event(run_logger, event)
        return event

    event.status = RecoveryStatus.REJECTED
    event.message = f"Human declined: “{label}” was not confirmed"
    event.details = {"confirmation": "abort"}
    await _log_event(run_logger, event)
    await save_mid_run_checkpoint(run_logger, checkpoints=checkpoints, event=event)
    return event


def _signals_reloading(signals: dict[str, Any]) -> bool:
    from app.errors.detect import RELOADING_HINTS

    title_text = f"{signals.get('title') or ''} {signals.get('text') or ''}"
    ready = str(signals.get("ready_state") or "").lower()
    body = str(signals.get("text") or "")
    return bool(RELOADING_HINTS.search(title_text)) or (
        ready in {"loading", "uninitialized"} and len(body.strip()) < 20
    )


def _signals_not_found(signals: dict[str, Any]) -> bool:
    from app.errors.detect import NOT_FOUND_HINTS

    title_text = f"{signals.get('title') or ''} {signals.get('text') or ''}"
    url = str(signals.get("url") or "").lower()
    path = str(signals.get("path") or "")
    return bool(
        NOT_FOUND_HINTS.search(title_text)
        or path in {"/404", "/not-found"}
        or "chrome-error://" in url
        or "about:neterror" in url
    )


async def recover_reloading(
    page,
    *,
    action: dict | None = None,
    run_logger: RunLogger | None = None,
    checkpoints: dict[str, Any] | None = None,
) -> RuntimeErrorEvent:
    """Wait 2s, re-check; wait 5s, re-check; otherwise cannot recover."""
    action = action or {}
    await capture_run_screenshot(run_logger, page, "error_reloading")
    delays = list(ERROR_POLICIES[ErrorKind.RELOADING.value]["delays_sec"])
    last = RuntimeErrorEvent(
        kind=ErrorKind.RELOADING,
        message="Page appears to be reloading",
        status=RecoveryStatus.RETRYING,
        action=action.get("action"),
        target=action.get("target"),
    )
    for index, delay in enumerate(delays, start=1):
        last.attempt = index
        last.delay_sec = float(delay)
        last.status = RecoveryStatus.RETRYING
        last.message = f"Reloading detected — waiting {delay}s before retry {index}/{len(delays)}"
        await _log_event(run_logger, last)
        await asyncio.sleep(delay)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        signals = await page_signals(page)
        if not _signals_reloading(signals):
            last.status = RecoveryStatus.RECOVERED
            last.message = f"Recovered after reload wait ({delay}s)"
            last.actual_page = signals.get("path")
            await _log_event(run_logger, last)
            return last

    last.kind = ErrorKind.HARD_FAILURE
    last.status = RecoveryStatus.TERMINAL
    last.message = "Cannot be recovered: page still reloading after 2s and 5s retries"
    await _log_event(run_logger, last)
    await save_mid_run_checkpoint(run_logger, checkpoints=checkpoints, event=last)
    return last


async def recover_page_not_found(
    page,
    *,
    action: dict | None = None,
    run_logger: RunLogger | None = None,
    checkpoints: dict[str, Any] | None = None,
    retry_url: str | None = None,
) -> RuntimeErrorEvent:
    """One retry: reload current URL or re-navigate to the intended target."""
    action = action or {}
    await capture_run_screenshot(run_logger, page, "error_page_not_found")
    event = RuntimeErrorEvent(
        kind=ErrorKind.PAGE_NOT_FOUND,
        message="Page not found — retrying once",
        status=RecoveryStatus.RETRYING,
        action=action.get("action"),
        target=action.get("target"),
        attempt=1,
        delay_sec=1.0,
    )
    await _log_event(run_logger, event)
    await asyncio.sleep(1.0)
    try:
        if retry_url:
            await page.goto(retry_url, wait_until="domcontentloaded")
        else:
            await page.reload(wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
    except Exception as exc:
        event.kind = ErrorKind.HARD_FAILURE
        event.status = RecoveryStatus.TERMINAL
        event.message = f"Cannot be recovered: page-not-found retry failed ({exc})"
        await _log_event(run_logger, event)
        await save_mid_run_checkpoint(run_logger, checkpoints=checkpoints, event=event)
        return event

    signals = await page_signals(page)
    if _signals_not_found(signals):
        event.kind = ErrorKind.HARD_FAILURE
        event.status = RecoveryStatus.TERMINAL
        event.message = "Cannot be recovered: page still not found after one retry"
        event.actual_page = signals.get("path")
        await _log_event(run_logger, event)
        await save_mid_run_checkpoint(run_logger, checkpoints=checkpoints, event=event)
        return event

    event.status = RecoveryStatus.RECOVERED
    event.message = "Recovered after page-not-found retry"
    event.actual_page = signals.get("path")
    await _log_event(run_logger, event)
    return event


async def handle_ui_changed(
    *,
    action: dict | None = None,
    expected_page: str | None = None,
    actual_page: str | None = None,
    detail: str | None = None,
    run_logger: RunLogger | None = None,
    checkpoints: dict[str, Any] | None = None,
) -> RuntimeErrorEvent:
    """Report UI mismatch and freeze checkpoints — no automatic recovery."""
    action = action or {}
    expected = expected_page or expected_page_for_action(action)
    message = ui_mismatch_message(expected, actual_page, detail)
    event = RuntimeErrorEvent(
        kind=ErrorKind.HARD_FAILURE,
        message=message,
        status=RecoveryStatus.FAILED,
        action=action.get("action"),
        target=action.get("target"),
        expected_page=expected,
        actual_page=actual_page,
    )
    await _log_event(run_logger, event)
    await save_mid_run_checkpoint(run_logger, checkpoints=checkpoints, event=event)
    return event


async def recover_hard_failure(
    page,
    *,
    action: dict | None = None,
    run_logger: RunLogger | None = None,
    checkpoints: dict[str, Any] | None = None,
) -> RuntimeErrorEvent:
    """
    blake000: one reload attempt, then terminal cannot-recover.
    No other error kinds are mixed in for this user.
    """
    action = action or {}
    await capture_run_screenshot(run_logger, page, "error_hard_failure")
    event = RuntimeErrorEvent(
        kind=ErrorKind.HARD_FAILURE,
        message="Hard failure — retrying once, then cannot recover",
        status=RecoveryStatus.RETRYING,
        action=action.get("action"),
        target=action.get("target"),
        attempt=1,
        delay_sec=1.0,
        details={"scenario": "hard_failure"},
    )
    await _log_event(run_logger, event)
    await asyncio.sleep(1.0)
    try:
        await page.reload(wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
    except Exception:
        pass
    signals = await page_signals(page)
    from app.errors.detect import HARD_FAILURE_HINTS

    path = str(signals.get("path") or "")
    title_text = f"{signals.get('title') or ''} {signals.get('text') or ''}"
    still_hard = path == "/unavailable" or bool(HARD_FAILURE_HINTS.search(title_text))
    if still_hard:
        event.status = RecoveryStatus.TERMINAL
        event.message = (
            "Cannot be recovered: hard failure remains after retry "
            "(no other error paths for this member)"
        )
        event.actual_page = path
        await _log_event(run_logger, event)
        await save_mid_run_checkpoint(run_logger, checkpoints=checkpoints, event=event)
        return event
    event.status = RecoveryStatus.RECOVERED
    event.message = "Recovered unexpectedly after hard-failure retry"
    event.kind = ErrorKind.HARD_FAILURE
    event.actual_page = path
    await _log_event(run_logger, event)
    return event


async def prepare_page_for_action(
    page,
    action: dict,
    *,
    run_logger: RunLogger | None = None,
    checkpoints: dict[str, Any] | None = None,
) -> RuntimeErrorEvent | None:
    """
    Pre-flight for scenario pages + reload / 404 / hard failure.

    UI route mismatch for normal actions remains a guardrail concern.
    """
    from app.errors.detect import (
        HARD_FAILURE_HINTS,
        NOT_FOUND_HINTS,
        RELOADING_HINTS,
    )

    signals = await page_signals(page)
    title_text = f"{signals.get('title') or ''} {signals.get('text') or ''}"
    url = str(signals.get("url") or "").lower()
    path = str(signals.get("path") or "")
    ready = str(signals.get("ready_state") or "").lower()
    body = str(signals.get("text") or "")

    if path == "/unavailable" or HARD_FAILURE_HINTS.search(title_text):
        return await recover_hard_failure(
            page, action=action, run_logger=run_logger, checkpoints=checkpoints
        )
    if path in {"/404", "/not-found"} or NOT_FOUND_HINTS.search(title_text):
        return await recover_page_not_found(
            page, action=action, run_logger=run_logger, checkpoints=checkpoints
        )
    if "chrome-error://" in url or "about:neterror" in url:
        return await recover_page_not_found(
            page, action=action, run_logger=run_logger, checkpoints=checkpoints
        )
    if path == "/reloading" or RELOADING_HINTS.search(title_text) or (
        ready in {"loading", "uninitialized"} and len(body.strip()) < 20
    ):
        return await recover_reloading(
            page, action=action, run_logger=run_logger, checkpoints=checkpoints
        )
    return None


async def resolve_login_scenario_gates(
    page,
    *,
    run_logger: RunLogger | None = None,
    checkpoints: dict[str, Any] | None = None,
) -> RuntimeErrorEvent | None:
    """After Sign In, clear scenario gates until dashboard is reachable."""
    action = {"action": "navigate", "target": "post-login"}
    for _ in range(4):
        event = await prepare_page_for_action(
            page, action, run_logger=run_logger, checkpoints=checkpoints
        )
        if event is None:
            return None
        if event.status in {RecoveryStatus.FAILED, RecoveryStatus.TERMINAL, RecoveryStatus.REJECTED}:
            return event
        # recovered — loop in case another gate appears
        await asyncio.sleep(0.3)
    signals = await page_signals(page)
    if "/dashboard" in str(signals.get("url") or ""):
        return None
    fail = RuntimeErrorEvent(
        kind=ErrorKind.HARD_FAILURE,
        message="Cannot be recovered: post-login scenario gate did not clear",
        status=RecoveryStatus.TERMINAL,
        actual_page=signals.get("path"),
    )
    await _log_event(run_logger, fail)
    await save_mid_run_checkpoint(run_logger, checkpoints=checkpoints, event=fail)
    return fail


async def execute_with_recovery(
    *,
    page,
    action: dict,
    execute: ExecuteFn,
    run_logger: RunLogger | None = None,
    checkpoints: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]], bool]:
    """
    Run an action with pre-flight + exception recovery.

    Returns (result_text, error_events, fatal).
    """
    events: list[dict[str, Any]] = []
    pre = await prepare_page_for_action(
        page, action, run_logger=run_logger, checkpoints=checkpoints
    )
    if pre is not None:
        events.append(pre.to_dict())
        if pre.status in {RecoveryStatus.FAILED, RecoveryStatus.TERMINAL, RecoveryStatus.REJECTED}:
            return pre.message, events, True
        # recovered → fall through and execute

    try:
        result = await execute()
        return result, events, False
    except Exception as exc:
        signals = await page_signals(page)
        kind = classify_exception(exc, signals)

        if kind == ErrorKind.RELOADING:
            event = await recover_reloading(
                page, action=action, run_logger=run_logger, checkpoints=checkpoints
            )
            events.append(event.to_dict())
            if event.status != RecoveryStatus.RECOVERED:
                return event.message, events, True
            try:
                return await execute(), events, False
            except Exception as retry_exc:
                fail = await handle_ui_changed(
                    action=action,
                    expected_page=expected_page_for_action(action),
                    actual_page=signals.get("path"),
                    detail=str(retry_exc),
                    run_logger=run_logger,
                    checkpoints=checkpoints,
                )
                events.append(fail.to_dict())
                return fail.message, events, True

        if kind == ErrorKind.PAGE_NOT_FOUND:
            retry_url = str(action.get("target")) if action.get("action") == "navigate" else None
            event = await recover_page_not_found(
                page,
                action=action,
                run_logger=run_logger,
                checkpoints=checkpoints,
                retry_url=retry_url,
            )
            events.append(event.to_dict())
            if event.status != RecoveryStatus.RECOVERED:
                return event.message, events, True
            try:
                return await execute(), events, False
            except Exception as retry_exc:
                fail = RuntimeErrorEvent(
                    kind=ErrorKind.HARD_FAILURE,
                    message=f"Cannot be recovered after page-not-found retry: {retry_exc}",
                    status=RecoveryStatus.TERMINAL,
                    action=action.get("action"),
                    target=action.get("target"),
                )
                await _log_event(run_logger, fail)
                await save_mid_run_checkpoint(run_logger, checkpoints=checkpoints, event=fail)
                events.append(fail.to_dict())
                return fail.message, events, True

        fail = await handle_ui_changed(
            action=action,
            expected_page=expected_page_for_action(action),
            actual_page=signals.get("path"),
            detail=str(exc),
            run_logger=run_logger,
            checkpoints=checkpoints,
        )
        events.append(fail.to_dict())
        return fail.message, events, True
