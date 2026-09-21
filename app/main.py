from __future__ import annotations

import argparse
import asyncio
import os
import re

from dotenv import load_dotenv

from app.agent.discover import run_discovery
from app.artifact.recorder import (
    current_member_id,
    find_artifact_by_id,
    force_discovery,
    force_discovery_for,
    force_replay,
    allow_discovery_fallback,
)
from app.artifact.replay import run_replay_with_fallbacks
from app.browser.manager import BrowserManager
from app.delete_account import run_delete_account
from app.lookup_balance import run_lookup_balance
from app.open_account import run_open_account
from app.plan import plan_query
from app.run.logger import RunLogger
from app.run.outcome import (
    TERMINAL_PASS_CODES,
    code_from_label,
    resolve_outcome,
    summarize_task_results,
)
from app.transfer_funds import run_transfer_funds


def task_succeeded(task, answer: str) -> bool:
    """Return True when the step reached a valid business conclusion (pass)."""
    result = resolve_outcome(task_kind=task.kind, answer=answer)
    return result.status == "pass"


def should_stop_workflow(task, result: dict) -> bool:
    """
    Stop the chain after failures, or after transfer business stops
    (missing account / insufficient funds). Open 'already exists' continues.
    """
    if result.get("status") != "pass":
        return True
    code = result.get("outcome_code") or code_from_label(result.get("outcome"))
    if task.kind == "transfer" and code in TERMINAL_PASS_CODES:
        return True
    return False


def void_remaining(task, reason: str = "previous step did not complete") -> str:
    return f"Skipped {task.artifact_id}: {reason}, so this step was voided."


def workflow_run_kind(tasks) -> str:
    """Prefer replay only when every planned operator already covers this member."""
    from app.artifact.recorder import expected_error_kind_for_member, force_discovery_for

    member_id = current_member_id()
    expected = expected_error_kind_for_member(member_id)
    for task in tasks:
        if force_discovery_for(task.artifact_id):
            return "discovery"
        if task.kind == "delete_account":
            from app.delete_account.runner import _operators_ready

            if not _operators_ready(member_id, need_transfer=False):
                return "discovery"
            continue
        artifact = find_artifact_by_id(task.artifact_id, member_id)
        if artifact is None:
            if expected:
                print(
                    f"[discovery] {task.artifact_id} lacks {expected} for {member_id} "
                    f"— treating as new capability"
                )
            return "discovery"
        if task.kind == "open_account":
            from app.open_account.runner import _artifact_has_open_click

            if not _artifact_has_open_click(artifact):
                return "discovery"
    return "replay"


async def run_task(
    task,
    browser_manager: BrowserManager,
    skip_auth: bool,
    fallback_discovery: bool | None = None,
    run_logger: RunLogger | None = None,
    own_run: bool = True,
) -> str:
    if fallback_discovery is None:
        fallback_discovery = allow_discovery_fallback()
    if task.kind == "delete_account":
        return await run_delete_account(
            task,
            browser_manager,
            skip_auth,
            run_task,
            run_logger=run_logger,
            own_run=own_run,
        )
    if task.kind == "open_account":
        return await run_open_account(
            task,
            browser_manager,
            skip_auth,
            run_logger=run_logger,
            own_run=own_run,
        )
    if task.kind == "transfer":
        return await run_transfer_funds(
            task,
            browser_manager,
            skip_auth,
            run_logger=run_logger,
            own_run=own_run,
        )

    if task.kind == "get_balance":
        return await run_lookup_balance(
            task,
            browser_manager,
            skip_auth,
            run_logger=run_logger,
            own_run=own_run,
        )

    member_id = current_member_id()
    artifact = find_artifact_by_id(task.artifact_id, member_id)
    if artifact is not None and not force_discovery_for(task.artifact_id):
        artifact_ref = f"{artifact.get('artifact_id')}/v{artifact.get('version')}"
        path = artifact.get("_path") or artifact.get("artifact_id")
        print(f"[replay] {artifact_ref} for {member_id} from {path} — LLM skipped")
        logger = run_logger
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
                skip_auth=skip_auth,
            )
        except Exception as exc:
            if own_run:
                logger.finish(error=str(exc), answer=str(exc), task_kind=task.kind)
            raise
        if result.get("status") == "replayed":
            answer = result.get("answer") or "No answer."
            if own_run:
                logger.finish(answer=answer, task_kind=task.kind)
            if result.get("artifact_path"):
                print(f"Operator: {result['artifact_path']}")
            return answer
        error = str(result.get("error") or result.get("status") or "UI changed")
        if own_run:
            logger.finish(error=error, answer=error, task_kind=task.kind)
        print(
            f"[replay] failed: {result.get('error')}; falling back to discovery"
            if fallback_discovery
            else f"[replay] failed: {result.get('error')}"
        )
        if not fallback_discovery:
            return error
    elif not fallback_discovery:
        print(f"[discovery] skipped for {task.artifact_id}")
        return f"No {task.params.get('account') or 'requested'} account was visible."
    else:
        print(f"[discovery] no matching operator for {task.artifact_id}; routing to LLM")

    if force_replay():
        msg = f"No replayable {task.artifact_id} operator; discovery disabled."
        print(f"[replay] {msg}")
        return msg

    logger = run_logger
    if own_run or logger is None:
        logger = RunLogger("discovery", task.goal)
    else:
        logger.event(type="operator", operator=task.artifact_id, mode="discovery")
    return await run_discovery(
        task.goal,
        browser_manager,
        logger,
        finish_run=own_run,
        task_kind=task.kind,
    )


def format_balance_answer(task, answer: str) -> str:
    """Normalize a bare currency finish into a full balance sentence."""
    if task.kind != "get_balance":
        return answer
    text = (answer or "").strip()
    if not text:
        return text
    if "do not have a" in text.lower() and "account" in text.lower():
        account = str(task.params.get("account") or "requested").strip() or "requested"
        return f"Account not found: you do not have a {account} account."
    if "balance" in text.lower():
        return text
    match = re.search(r"(\$\s*[\d,]+(?:\.\d{1,2})?)", text)
    if not match:
        return text
    account = str(task.params.get("account") or "account").lower()
    return f"Your {account} account balance is {match.group(1).replace(' ', '')}."


def task_outcome(task, answer: str, run_logger: RunLogger | None = None) -> dict:
    """Map a step answer to structured outcome for run.json."""
    resolved = resolve_outcome(
        task_kind=task.kind,
        answer=answer,
        outcome_code=(run_logger._outcome_code if run_logger else None),
        guardrail_audit=(
            list(run_logger.meta.get("guardrail_audit") or []) if run_logger else None
        ),
        error_events=(
            list(run_logger.meta.get("error_events") or []) if run_logger else None
        ),
        dom_signals=(
            dict(run_logger._dom_signals or run_logger.meta.get("dom_signals") or {})
            if run_logger
            else None
        ),
    )
    return {
        "status": resolved.status,
        "outcome": resolved.label,
        "outcome_code": resolved.code,
        "outcome_source": resolved.source,
        "outcome_evidence": resolved.evidence,
        "artifact": task.artifact_id,
    }


async def run_query(query: str) -> str:
    print(f"[query] {query}")
    tasks = plan_query(query)
    print("[plan] " + " → ".join(task.artifact_id for task in tasks))
    from app.browser.viewport import current_viewport

    viewport = current_viewport()
    browser_manager = BrowserManager(viewport=viewport)
    answers: list[str] = []
    task_results: list[dict] = []
    kind = workflow_run_kind(tasks)
    run_logger = RunLogger(kind, query)
    run_logger.meta["viewport"] = {
        "profile": viewport.get("profile"),
        "width": viewport.get("width"),
        "height": viewport.get("height"),
        "locator_policy": "dom_only",
    }
    run_logger._write_meta()
    try:
        for index, task in enumerate(tasks):
            print(f"[plan] step {index + 1}/{len(tasks)} {task.artifact_id}: {task.goal}")
            skip_auth = index > 0 and browser_manager.page is not None
            try:
                answer = await run_task(
                    task,
                    browser_manager,
                    skip_auth,
                    run_logger=run_logger,
                    own_run=False,
                )
            except Exception as exc:
                message = str(exc)
                answers.append(message)
                result = task_outcome(task, message, run_logger)
                result["status"] = result.get("status") or "failed"
                task_results.append(result)
                run_logger.event(
                    type="task_result",
                    operator=task.artifact_id,
                    status=result["status"],
                    outcome=result["outcome"],
                    outcome_code=result.get("outcome_code"),
                    outcome_source=result.get("outcome_source"),
                )
                break
            answer = format_balance_answer(task, answer)
            # Prefer page facts over answer prose when the browser is still open.
            try:
                await run_logger.capture_dom_outcome(
                    browser_manager.page,
                    task_kind=task.kind,
                    account=str((task.params or {}).get("account") or "") or None,
                )
            except Exception:
                pass
            answers.append(answer)
            result = task_outcome(task, answer, run_logger)
            task_results.append(result)
            run_logger.event(
                type="task_result",
                operator=task.artifact_id,
                status=result["status"],
                outcome=result["outcome"],
                outcome_code=result.get("outcome_code"),
                outcome_source=result.get("outcome_source"),
            )
            if should_stop_workflow(task, result):
                if index < len(tasks) - 1:
                    reason = (
                        f"previous step stopped ({result['outcome']})"
                        if result.get("status") == "pass"
                        else "previous step did not complete"
                    )
                    print(
                        f"[plan] step {index + 1} stopped ({result['status']}/"
                        f"{result['outcome']}); voiding remaining steps"
                    )
                    for later in tasks[index + 1 :]:
                        voided = void_remaining(later, reason=reason)
                        print(f"[plan] void {later.artifact_id}: {voided}")
                        run_logger.event(
                            type="void",
                            operator=later.artifact_id,
                            reason=reason,
                        )
                        answers.append(voided)
                break
        summary = summarize_task_results(task_results)
        run_logger.meta["task_results"] = task_results
        run_logger.finish(
            status=summary.status,
            outcome=summary.label,
            outcome_code=summary.code,
            answer="\n".join(answers),
            task_kind=tasks[0].kind if tasks else None,
        )
        return "\n".join(part for part in answers if part)
    except Exception as exc:
        resolved = resolve_outcome(error=str(exc))
        run_logger.finish(
            status=resolved.status,
            outcome=resolved.label,
            outcome_code=resolved.code,
            error=str(exc),
        )
        raise
    finally:
        await browser_manager.close()


def apply_cli_credentials(username: str | None, password: str | None = None) -> None:
    """Override bank login env vars for this process when CLI flags are set."""
    del password  # Login is username-only.
    if username:
        from app.artifact.recorder import validate_member_id

        error = validate_member_id(username)
        if error:
            raise SystemExit(error)
        os.environ["BANK_USERNAME"] = username.strip()


def main() -> None:
    load_dotenv(override=True)
    parser = argparse.ArgumentParser(
        description="Ask Atlas Bank to open an account, look up a balance, transfer funds, or delete an account.",
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="Example: Delete my savings account",
    )
    parser.add_argument(
        "-u",
        "--username",
        default=None,
        help="Member ID (letters + 3 digits). Overrides BANK_USERNAME. Examples: alex123, jordan456, sam789",
    )
    parser.add_argument(
        "--viewport",
        default=None,
        choices=["desktop", "laptop", "tablet", "mobile"],
        help=(
            "Device profile for Playwright (DOM locators + scroll). "
            "Same desktop artifact replays on tablet/mobile without discovery when possible. "
            "Overrides VIEWPORT / DEVICE_PROFILE."
        ),
    )
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        help="Custom viewport width in pixels (with --height).",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=None,
        help="Custom viewport height in pixels (with --width).",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help=(
            "Auto-confirm app handoffs: agent clicks Yes, Confirm / Confirm Transfer "
            "for you (no browser click / resume). Production requires approved "
            "operators (≥3 successes at ≥75%%); draft versions need interactive "
            "replay or ATLAS_ALLOW_DRAFT_YES=1 (test harness)."
        ),
    )
    parser.add_argument(
        "-n",
        "--no",
        action="store_true",
        help="Auto-abort confirmation handoffs (cancel protected confirms).",
    )
    args = parser.parse_args()
    apply_cli_credentials(args.username)
    if args.yes and args.no:
        raise SystemExit("Use only one of --yes / --no.")
    if args.yes:
        os.environ["ATLAS_AUTO_CONFIRM"] = "yes"
    elif args.no:
        os.environ["ATLAS_AUTO_CONFIRM"] = "no"
    if args.viewport:
        os.environ["VIEWPORT"] = args.viewport
    if args.width:
        os.environ["VIEWPORT_WIDTH"] = str(args.width)
    if args.height:
        os.environ["VIEWPORT_HEIGHT"] = str(args.height)

    if args.query:
        print(asyncio.run(run_query(" ".join(args.query))))
        return

    print(
        "Atlas Bank assistant. Ask to open Checking/Savings, look up a balance, "
        "transfer funds, or delete an account. "
        "Chain steps with then. Type quit to exit."
    )
    member = os.getenv("BANK_USERNAME", "alex123")
    print(f"Signed-in member for this session: {member}")
    while True:
        try:
            query = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not query:
            continue
        if query.lower() in {"quit", "exit"}:
            return
        print(asyncio.run(run_query(query)))


if __name__ == "__main__":
    main()
