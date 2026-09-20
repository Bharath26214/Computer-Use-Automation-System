from __future__ import annotations

import json

from app.agent.verify import verify as run_verify
from app.artifact.recorder import action_to_step, persist_artifact
from app.browser.manager import BrowserManager
from app.run.logger import RunLogger


async def record(
    state: dict,
    browser_manager: BrowserManager,
    run_logger: RunLogger | None = None,
) -> dict:
    action = state.get("action") or {}
    name = action.get("action")
    steps = list(state.get("recorded_steps") or [])
    updates: dict = {}

    if name not in {None, "finish", "request_human"}:
        verified = await run_verify(state, browser_manager)
        updates.update(verified)
        checkpoint_passed = bool(verified.get("checkpoint_passed"))
        if run_logger is not None:
            run_logger.log_verify(action, checkpoint_passed)
    else:
        checkpoint_passed = True

    failed = str(state.get("last_result") or "").startswith("Action failed")
    skipped = name in {None, "finish", "request_human"} or not checkpoint_passed or failed

    if not skipped:
        steps.append(action_to_step(action, len(steps) + 1))
        last = steps[-1]
        print(f"[record] {last['id']} {last['type']} risk={last.get('risk')} — {last.get('description')}")

    updates["recorded_steps"] = steps
    updates["status"] = "recording_skipped" if skipped else "recorded"

    should_save = name == "finish" or state.get("iteration", 0) >= state.get("max_iterations", 18)
    if should_save:
        finish_text = " ".join(
            part
            for part in (
                str(action.get("value") or ""),
                str(state.get("answer") or ""),
                str(state.get("last_result") or ""),
                str(state.get("goal") or ""),
            )
            if part
        ).lower()
        open_failed = (
            "additional accounts are not allowed" in finish_text
            or (
                "already exists" in finish_text
                and ("open" in str(state.get("goal") or "").lower() or "creat" in str(state.get("goal") or "").lower())
            )
        )
        opened_this_run = any(
            "open" in str(step.get("description") or "").lower()
            and "account" in str(step.get("description") or "").lower()
            for step in steps
        )
        if open_failed and not opened_this_run:
            updates["status"] = "open_account_rejected"
            print("[operator] skipped save: open account is not valid for this member")
        else:
            if opened_this_run and "already exists" in finish_text:
                # Successful open click then mistaken "already exists" finish — still save.
                updates["answer"] = updates.get("answer") or (
                    str(action.get("value") or "").replace(
                        "already exists", "created"
                    )
                    if action.get("value")
                    else None
                )
            path = persist_artifact(
                {
                    **state,
                    **updates,
                    "recorded_steps": steps,
                    "error_events": list(state.get("error_events") or [])
                    + list(
                        (run_logger.meta.get("error_events") if run_logger else None) or []
                    ),
                }
            )
            if path is not None:
                print(f"[operator] saved {path}")
                updates["artifact_path"] = str(path)
                updates["status"] = "artifact_saved"
                if run_logger is not None:
                    artifact = json.loads(path.read_text(encoding="utf-8"))
                    run_logger.set_artifact_created(
                        f"{artifact.get('artifact_id')}/v{artifact.get('version')}"
                    )

    return updates
