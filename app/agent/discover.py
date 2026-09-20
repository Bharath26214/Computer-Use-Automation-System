from __future__ import annotations

import json
import os

from app.artifact.recorder import persist_artifact
from app.browser.manager import BrowserManager
from app.run.logger import RunLogger


async def run_discovery(
    query: str,
    browser_manager: BrowserManager,
    run_logger: RunLogger,
    *,
    finish_run: bool = True,
    task_kind: str | None = None,
    allow_delete: bool = False,
    allow_open: bool = False,
) -> str:
    """
    First-time capability learning: LLM chooses Playwright actions each turn.
    Successful runs persist operators/{id}/vN.json from recorded steps.
    """
    from app.agent.graph import build_agent

    print(f"[discovery] LLM + Playwright for: {query}")
    agent = build_agent(
        browser_manager,
        run_logger,
        allow_delete=allow_delete,
        allow_open=allow_open,
    )
    last_answer = ""
    recorded_steps: list = []
    checkpoints: dict = {}
    error_events: list = []
    artifact_path = None
    blocked = False
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
                "allow_delete": allow_delete,
                "allow_open": allow_open,
                "error_events": [],
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
                if payload.get("error_events"):
                    for event in payload["error_events"]:
                        if event not in error_events:
                            error_events.append(event)
                if payload.get("artifact_path"):
                    artifact_path = payload["artifact_path"]
                    print(f"Operator: {artifact_path}")
                if payload.get("answer"):
                    last_answer = payload["answer"]
                if node_status == "blocked":
                    blocked = True
        # Include logger-captured recovery events (HITL / UI) as well.
        for event in list(run_logger.meta.get("error_events") or []):
            if event not in error_events:
                error_events.append(event)
        if not artifact_path and recorded_steps and not blocked:
            should_persist = True
            lowered = last_answer.lower()
            opened_this_run = any(
                "open" in str(step.get("description") or step.get("type") or "").lower()
                and "account" in str(step.get("description") or "").lower()
                for step in recorded_steps
            )
            if "additional accounts are not allowed" in lowered:
                should_persist = False
            elif "already exists" in lowered and "open" in query.lower() and not opened_this_run:
                should_persist = False
            if should_persist:
                if opened_this_run and "already exists" in lowered:
                    last_answer = last_answer.replace(
                        "already exists", "created"
                    ).replace("Already exists", "created")
                    if "created" not in last_answer.lower():
                        last_answer = "Savings account created." if "saving" in query.lower() else "Checking account created."
                path = persist_artifact(
                    {
                        "goal": query,
                        "recorded_steps": recorded_steps,
                        "checkpoints": checkpoints,
                        "viewport": getattr(browser_manager, "viewport", None),
                        "error_events": error_events,
                    }
                )
                if path is not None:
                    artifact_path = str(path)
                    print(f"Operator: {artifact_path}")
                    artifact = json.loads(path.read_text(encoding="utf-8"))
                    run_logger.set_artifact_created(
                        f"{artifact.get('artifact_id')}/v{artifact.get('version')}"
                    )
        answer = last_answer or ("UI changed" if blocked else "No answer.")
        if finish_run:
            run_logger.finish(answer=answer, task_kind=task_kind)
        return answer
    except Exception as exc:
        if not artifact_path and recorded_steps:
            path = persist_artifact(
                {
                    "goal": query,
                    "recorded_steps": recorded_steps,
                    "checkpoints": checkpoints,
                    "viewport": getattr(browser_manager, "viewport", None),
                    "error_events": error_events
                    or list(run_logger.meta.get("error_events") or []),
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
            run_logger.finish(error=str(exc), task_kind=task_kind)
        raise
