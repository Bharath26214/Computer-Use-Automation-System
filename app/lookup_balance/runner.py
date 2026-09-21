from __future__ import annotations

import re

from app.artifact.recorder import (
    current_member_id,
    expected_error_kind_for_member,
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
    missing_account_message,
)
from app.browser.manager import BrowserManager
from app.plan import LOOKUP_BALANCE, PlannedTask
from app.run.logger import RunLogger

CURRENCY = re.compile(r"(\$\s*[\d,]+(?:\.\d{1,2})?)")


def _account_key(account: str) -> str:
    text = (account or "").strip().lower()
    if text.startswith("sav"):
        return "savings"
    return "checking"


def _format_balance_answer(account: str, account_key: str, answer: str, outputs: dict | None = None) -> str:
    text = answer or "No answer."
    match = CURRENCY.search(str(text))
    if match:
        return (
            f"Your {account.lower()} account balance is "
            f"{match.group(1).replace(' ', '')}."
        )
    for key in (f"{account_key}-account", "last_result"):
        blob = str((outputs or {}).get(key) or "")
        match = CURRENCY.search(blob)
        if match:
            return (
                f"Your {account.lower()} account balance is "
                f"{match.group(1).replace(' ', '')}."
            )
    return text


async def run_lookup_balance(
    task: PlannedTask,
    browser_manager: BrowserManager,
    skip_auth: bool,
    run_logger: RunLogger | None = None,
    own_run: bool = True,
) -> str:
    from app.agent.discover import run_discovery

    account = str(task.params.get("account") or "Checking").strip() or "Checking"
    account_key = _account_key(account)
    member_id = current_member_id()
    artifact = find_artifact_by_id(LOOKUP_BALANCE, member_id)
    expected = expected_error_kind_for_member(member_id)
    logger = run_logger

    # Scenario error not on any version → new capability via discovery (e.g. v2).
    if artifact is None and expected:
        print(
            f"[discovery] {LOOKUP_BALANCE} has no version for {expected} "
            f"({member_id}) — new capability, skipping replay"
        )

    use_replay = (
        not force_discovery_for(LOOKUP_BALANCE)
        and bool(artifact is not None and artifact.get("steps"))
    )
    if use_replay:
        artifact_ref = f"{artifact.get('artifact_id')}/v{artifact.get('version')}"
        if own_run or logger is None:
            logger = RunLogger("replay", task.goal, artifact_used=artifact_ref)
        else:
            logger.note_operator(artifact_ref, created=False)
            logger.event(type="operator", operator=artifact_ref, mode="replay")
    elif own_run or logger is None:
        logger = RunLogger("discovery", task.goal)
    else:
        logger.event(type="operator", operator=LOOKUP_BALANCE, mode="discovery")

    await ensure_signed_in(browser_manager, skip_auth=skip_auth, run_logger=logger)
    await ensure_dashboard(browser_manager)

    if not await account_is_open(browser_manager, account):
        if own_run:
            msg = missing_account_message(account)
            logger.finish(answer=msg, task_kind="get_balance")
            return msg
        return missing_account_message(account)

    if use_replay:
        print(f"[replay] {artifact.get('artifact_id')}/v{artifact.get('version')} "
              f"for {member_id} — Playwright lookup")
        try:
            result = await run_replay_with_fallbacks(
                task.goal,
                artifact,
                browser_manager,
                logger,
                skip_auth=True,
            )
        except Exception as exc:
            if own_run:
                logger.finish(error=str(exc), answer=str(exc), task_kind="get_balance")
            raise
        if result.get("status") == "replayed":
            answer = _format_balance_answer(
                account,
                account_key,
                str(result.get("answer") or ""),
                result.get("outputs") or {},
            )
            if own_run:
                try:
                    await logger.capture_dom_outcome(
                        browser_manager.page,
                        task_kind="get_balance",
                        account=account,
                    )
                except Exception:
                    pass
                logger.finish(answer=answer, task_kind="get_balance")
            path = artifact.get("_path")
            if path:
                print(f"Operator: {path}")
            return answer
        error = str(result.get("error") or result.get("status") or "UI changed")
        if not allow_discovery_fallback():
            print(f"[replay] failed: {error}; discovery fallback disabled")
            if own_run:
                try:
                    await logger.capture_dom_outcome(
                        browser_manager.page,
                        task_kind="get_balance",
                        account=account,
                    )
                except Exception:
                    pass
                logger.finish(error=error, answer=error, task_kind="get_balance")
            return error
        print(f"[replay] failed: {error}; falling back to LLM discovery")
        if own_run:
            logger = RunLogger("discovery", task.goal)
            await ensure_signed_in(browser_manager, skip_auth=False, run_logger=logger)
            await ensure_dashboard(browser_manager)

    if force_replay():
        msg = f"No replayable {LOOKUP_BALANCE} operator for {member_id}."
        print(f"[replay] {msg}")
        if own_run and logger is not None:
            logger.finish(error=msg, answer=msg, task_kind="get_balance")
        return msg

    try:
        answer = await run_discovery(
            task.goal,
            browser_manager,
            logger,
            finish_run=False,
            task_kind="get_balance",
        )
        answer = _format_balance_answer(account, account_key, answer)
        if own_run:
            try:
                await logger.capture_dom_outcome(
                    browser_manager.page,
                    task_kind="get_balance",
                    account=account,
                )
            except Exception:
                pass
            logger.finish(answer=answer, task_kind="get_balance")
        return answer
    except Exception as exc:
        if own_run:
            logger.finish(error=str(exc), answer=str(exc), task_kind="get_balance")
        raise
