from __future__ import annotations

import argparse
import asyncio
import json
import os

from dotenv import load_dotenv

from app.artifact.recorder import current_member_id, find_artifact_by_id, persist_artifact
from app.artifact.replay import run_replay
from app.browser.manager import BrowserManager
from app.create_statement import run_create_statement
from app.delete_account import run_delete_account
from app.open_account import run_open_account
from app.plan import plan_query
from app.run.logger import RunLogger
from app.transfer_funds import run_transfer_funds


def task_succeeded(task, answer: str) -> bool:
    """Return True only when the step completed its intended outcome."""
    text = (answer or "").strip()
    lowered = text.lower()
    if not text or lowered in {"no answer.", "no answer"}:
        return False
    if "stopped after the maximum" in lowered:
        return False
    if "action not allowed" in lowered or "blocked" in lowered:
        return False
    if "was not created" in lowered or "was not deleted" in lowered:
        return False

    if task.kind == "open_account":
        if "additional accounts are not allowed" in lowered:
            return False
        if "already exists" in lowered or "already have a" in lowered:
            return False
        return "created successfully" in lowered or "opened" in lowered or "ready" in lowered

    if task.kind == "transfer":
        return "transfer to" in lowered and "transfer from" in lowered

    if task.kind == "create_statement":
        return "saved" in lowered and "statement" in lowered

    if task.kind == "delete_account":
        return "deleted" in lowered and "was not deleted" not in lowered

    if task.kind == "get_balance":
        return "$" in text and "balance" in lowered

    if any(
        marker in lowered
        for marker in (
            "failed",
            "could not",
            "was not deleted",
            "not allowed",
            "no matching",
        )
    ):
        return False
    return True


def void_remaining(task) -> str:
    return (
        f"Skipped {task.artifact_id}: previous step did not complete, "
        "so this step was voided."
    )


def workflow_run_kind(tasks) -> str:
    """Prefer replay only when every planned operator already exists."""
    member_id = current_member_id()
    for task in tasks:
        if task.kind == "delete_account":
            from app.delete_account.runner import _operators_ready

            if not _operators_ready(member_id, need_transfer=False):
                return "discovery"
            continue
        artifact = find_artifact_by_id(task.artifact_id, member_id)
        if artifact is None:
            return "discovery"
        if task.kind == "open_account":
            from app.open_account.runner import _artifact_has_open_click

            if not _artifact_has_open_click(artifact):
                return "discovery"
    return "replay"


async def run_discovery(
    query: str,
    browser_manager: BrowserManager,
    run_logger: RunLogger,
    *,
    finish_run: bool = True,
) -> str:
    from app.agent.graph import build_agent

    agent = build_agent(browser_manager, run_logger)
    last_answer = ""
    status = "success"
    recorded_steps: list = []
    checkpoints: dict = {}
    artifact_path = None
    try:
        async for update in agent.astream(
            {
                "goal": query,
                "messages": [],
                "iteration": 0,
                "max_iterations": int(os.getenv("MAX_ITERATIONS", "18")),
                "status": "start",
                "action_log": [],
                "recorded_steps": [],
                "artifact_path": None,
                "outputs": {},
                "checkpoints": {},
                "checkpoint_passed": False,
                "error": None,
                "risk_level": None,
            },
            stream_mode="updates",
        ):
            for node, payload in update.items():
                node_status = payload.get("status")
                if node_status:
                    print(f"[agent:{node}] {node_status}")
                if payload.get("recorded_steps"):
                    recorded_steps = payload["recorded_steps"]
                if payload.get("checkpoints"):
                    checkpoints = payload["checkpoints"]
                if payload.get("artifact_path"):
                    artifact_path = payload["artifact_path"]
                    print(f"Operator: {artifact_path}")
                if payload.get("answer"):
                    last_answer = payload["answer"]
                if node_status == "blocked":
                    status = "blocked"
        if not artifact_path and recorded_steps and status != "blocked":
            should_persist = True
            if "additional accounts are not allowed" in last_answer.lower():
                should_persist = False
                status = "failed"
            elif "already exists" in last_answer.lower() and "open" in query.lower():
                should_persist = False
                status = "failed"
            if should_persist:
                path = persist_artifact(
                    {
                        "goal": query,
                        "recorded_steps": recorded_steps,
                        "checkpoints": checkpoints,
                    }
                )
                if path is not None:
                    artifact_path = str(path)
                    print(f"Operator: {artifact_path}")
                    artifact = json.loads(path.read_text(encoding="utf-8"))
                    run_logger.set_artifact_created(
                        f"{artifact.get('artifact_id')}/v{artifact.get('version')}"
                    )
        if last_answer and (
            "additional accounts are not allowed" in last_answer.lower()
            or (
                "already exists" in last_answer.lower()
                and ("open" in query.lower() or "creat" in query.lower())
            )
        ):
            status = "failed"
        if not last_answer and status == "success":
            status = "failed"
        if finish_run:
            run_logger.finish(status=status)
        return last_answer or "No answer."
    except Exception as exc:
        if not artifact_path and recorded_steps:
            path = persist_artifact(
                {
                    "goal": query,
                    "recorded_steps": recorded_steps,
                    "checkpoints": checkpoints,
                }
            )
            if path is not None:
                artifact_path = str(path)
                print(f"Operator: {artifact_path}")
                artifact = json.loads(path.read_text(encoding="utf-8"))
                run_logger.set_artifact_created(
                    f"{artifact.get('artifact_id')}/v{artifact.get('version')}"
                )
        if finish_run:
            run_logger.finish(status="failed", error=str(exc))
        raise


async def run_task(
    task,
    browser_manager: BrowserManager,
    skip_auth: bool,
    fallback_discovery: bool = True,
    run_logger: RunLogger | None = None,
    own_run: bool = True,
) -> str:
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
    if task.kind == "create_statement":
        return await run_create_statement(
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

    member_id = current_member_id()
    artifact = find_artifact_by_id(task.artifact_id, member_id)
    if artifact is not None:
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
            result = await run_replay(
                task.goal,
                artifact,
                browser_manager,
                logger,
                skip_auth=skip_auth,
            )
        except Exception as exc:
            if own_run:
                logger.finish(status="failed", error=str(exc))
            raise
        if result.get("status") == "replayed":
            if own_run:
                logger.finish(status="success")
            if result.get("artifact_path"):
                print(f"Operator: {result['artifact_path']}")
            return result.get("answer") or "No answer."
        if own_run:
            logger.finish(
                status="failed",
                error=str(result.get("error") or result.get("status")),
            )
        print(
            f"[replay] failed: {result.get('error')}; falling back to discovery"
            if fallback_discovery
            else f"[replay] failed: {result.get('error')}"
        )
        if not fallback_discovery:
            return str(result.get("error") or "Lookup failed.")
    elif not fallback_discovery:
        print(f"[discovery] skipped for {task.artifact_id}")
        return f"No {task.params.get('account') or 'requested'} account was visible."
    else:
        print(f"[discovery] no matching operator for {task.artifact_id}; routing to LLM")

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
    )


def task_outcome(task, answer: str) -> str:
    """Map a step answer to run status: success, failed, or cancelled."""
    text = (answer or "").strip().lower()
    if task.kind == "delete_account" and "was not deleted" in text:
        return "cancelled"
    if task.kind == "open_account" and "was not created" in text:
        return "cancelled"
    if task_succeeded(task, answer):
        return "success"
    return "failed"


async def run_query(query: str) -> str:
    print(f"[query] {query}")
    tasks = plan_query(query)
    print("[plan] " + " → ".join(task.artifact_id for task in tasks))
    browser_manager = BrowserManager()
    answers: list[str] = []
    kind = workflow_run_kind(tasks)
    run_logger = RunLogger(kind, query)
    status = "success"
    try:
        for index, task in enumerate(tasks):
            print(f"[plan] step {index + 1}/{len(tasks)} {task.artifact_id}: {task.goal}")
            skip_auth = index > 0 and browser_manager.page is not None
            answer = await run_task(
                task,
                browser_manager,
                skip_auth,
                run_logger=run_logger,
                own_run=False,
            )
            answers.append(answer)
            outcome = task_outcome(task, answer)
            if outcome != "success":
                status = outcome
                if index < len(tasks) - 1:
                    print(
                        f"[plan] step {index + 1} did not complete; "
                        "voiding remaining steps"
                    )
                    for later in tasks[index + 1 :]:
                        voided = void_remaining(later)
                        print(f"[plan] void {later.artifact_id}: {voided}")
                        run_logger.event(
                            type="void",
                            operator=later.artifact_id,
                            reason="previous step did not complete",
                        )
                        answers.append(voided)
                break
        run_logger.finish(status=status)
        return "\n".join(part for part in answers if part)
    except Exception as exc:
        run_logger.finish(status="failed", error=str(exc))
        raise
    finally:
        await browser_manager.close()


def main() -> None:
    load_dotenv(override=True)
    parser = argparse.ArgumentParser(
        description="Ask Atlas Bank to open an account, look up a balance, transfer funds, create a statement, or delete an account.",
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="Example: Delete my savings account",
    )
    args = parser.parse_args()

    if args.query:
        print(asyncio.run(run_query(" ".join(args.query))))
        return

    print(
        "Atlas Bank assistant. Ask to open Checking/Savings, look up a balance, "
        "transfer funds, create a monthly statement, or delete an account. "
        "Chain steps with then. Type quit to exit."
    )
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
