from __future__ import annotations

import json

from app.artifact.recorder import (
    current_member_id,
    find_artifact_by_id,
    force_discovery_for,
    force_replay,
    allow_discovery_fallback,
)
from app.artifact.replay import run_replay_with_fallbacks
from app.browser.accounts import (
    account_is_open,
    ensure_dashboard,
    ensure_signed_in,
)
from app.browser.manager import BrowserManager
from app.plan import OPEN_ACCOUNT, PlannedTask
from app.run.logger import RunLogger


def _artifact_has_open_click(artifact: dict | None) -> bool:
    if not artifact:
        return False
    blob = json.dumps(artifact.get("steps") or []).lower()
    has_open = any(
        token in blob
        for token in (
            "open {{account}} account",
            "add {{account}} account",
            "create {{account}} account",
            "create account",
            "open-checking-account",
            "open-savings-account",
        )
    )
    has_fields = any(
        token in blob
        for token in (
            "account name",
            "account_name",
            "nickname",
            "{{account_name}}",
            "account type",
            "{{account}}",
        )
    )
    return has_open and (has_fields or "create account" in blob)


def _success_message(account: str, name: str, use: str) -> str:
    extras = ", ".join(part for part in (name, use) if part)
    if extras:
        return f"{account} account created successfully ({extras})."
    return f"{account} account created successfully."


def _normalize_answer(account: str, name: str, use: str, answer: str) -> str:
    text = (answer or "").strip()
    lowered = text.lower()
    if "additional accounts are not allowed" in lowered:
        return text
    if ("already exists" in lowered or "already have a" in lowered) and "created" not in lowered:
        return text
    if any(
        marker in lowered
        for marker in ("opened", "created", "ready", "clicked open")
    ):
        return _success_message(account, name, use)
    if text and text.lower() not in {"no answer.", "no answer"}:
        return text
    return _success_message(account, name, use)


async def run_open_account(
    task: PlannedTask,
    browser_manager: BrowserManager,
    skip_auth: bool,
    run_logger: RunLogger | None = None,
    own_run: bool = True,
) -> str:
    from app.agent.discover import run_discovery

    account = str(task.params.get("account") or "Checking").strip() or "Checking"
    name = str(task.params.get("account_name") or account).strip() or account
    use = str(task.params.get("account_use") or "Personal").strip() or "Personal"

    await ensure_signed_in(browser_manager, skip_auth=skip_auth, run_logger=run_logger)
    await ensure_dashboard(browser_manager)
    if await account_is_open(browser_manager, account):
        return f"You already have a {account} account."
    checking_open = await account_is_open(browser_manager, "Checking")
    savings_open = await account_is_open(browser_manager, "Savings")
    if checking_open and savings_open:
        return (
            "You already have Checking and Savings accounts. "
            "Additional accounts are not allowed."
        )

    # Agent clicks Open Account → app confirmation page → human clicks Yes, Confirm.

    print(f"[open_account] creating {account} named {name} ({use})")
    member_id = current_member_id()
    artifact = find_artifact_by_id(OPEN_ACCOUNT, member_id)
    use_stored = (not force_discovery_for(OPEN_ACCOUNT)) and _artifact_has_open_click(artifact)

    async def _finish(logger: RunLogger, answer: str, error: str | None = None) -> None:
        if own_run:
            try:
                await logger.capture_dom_outcome(
                    browser_manager.page,
                    task_kind="open_account",
                    account=account,
                )
            except Exception:
                pass
            logger.finish(
                answer=answer,
                error=error,
                task_kind="open_account",
            )

    logger = run_logger
    if artifact is not None and use_stored:
        artifact_ref = f"{artifact.get('artifact_id')}/v{artifact.get('version')}"
        if own_run or logger is None:
            logger = RunLogger("replay", task.goal, artifact_used=artifact_ref)
        else:
            logger.note_operator(artifact_ref, created=False)
            logger.event(type="operator", operator=artifact_ref, mode="replay")
        try:
            result = await run_replay_with_fallbacks(
                task.goal,
                artifact,
                browser_manager,
                logger,
                skip_auth=True,
                context={},
            )
        except Exception as exc:
            await _finish(logger, str(exc), error=str(exc))
            raise
        if result.get("status") == "replayed":
            answer = _normalize_answer(
                account, name, use, str(result.get("answer") or "")
            )
            await _finish(logger, answer)
            return answer
        if result.get("status") == "guardrail_blocked":
            answer = str(result.get("answer") or result.get("error") or "")
            await _finish(logger, answer)
            return answer
        error = str(result.get("error") or result.get("status") or "UI changed")
        if not allow_discovery_fallback():
            print(f"[replay] failed: {error}; discovery fallback disabled")
            await _finish(logger, error, error=error)
            return error
        print(f"[replay] failed: {error}; falling back to LLM discovery")

    if force_replay():
        msg = f"No replayable {OPEN_ACCOUNT} operator for {member_id}."
        print(f"[replay] {msg}")
        await _finish(
            logger if logger is not None else RunLogger("replay", task.goal),
            msg,
            error=msg,
        )
        return msg

    if own_run or logger is None:
        logger = RunLogger("discovery", task.goal)
    else:
        logger.event(type="operator", operator=OPEN_ACCOUNT, mode="discovery")
    try:
        answer = await run_discovery(
            task.goal,
            browser_manager,
            logger,
            finish_run=False,
            task_kind="open_account",
            allow_open=False,
        )
        answer = _normalize_answer(account, name, use, answer)
        await _finish(logger, answer)
        return answer
    except Exception as exc:
        await _finish(logger, str(exc), error=str(exc))
        raise
