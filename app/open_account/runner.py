from __future__ import annotations

import json

from app.artifact.recorder import current_member_id, find_artifact_by_id, persist_artifact
from app.artifact.replay import run_replay
from app.browser.manager import BrowserManager
from app.plan import OPEN_ACCOUNT, PlannedTask
from app.run.confirm import ask_yes_no
from app.run.logger import RunLogger

OPEN_ACCOUNT_STEPS = [
    {
        "id": "step_1",
        "type": "navigate",
        "target": {"strategy": "url", "value": "{{bank_url}}"},
    },
    {
        "id": "step_2",
        "type": "fill",
        "target": {"strategy": "label", "value": "Username"},
        "value": "{{member_id}}",
    },
    {
        "id": "step_3",
        "type": "fill",
        "target": {"strategy": "label", "value": "Password"},
        "value": "{{password}}",
    },
    {
        "id": "step_4",
        "type": "click",
        "target": {"strategy": "role", "role": "button", "name": "Sign In"},
    },
    {
        "id": "step_5",
        "type": "fill",
        "target": {"strategy": "label", "value": "Account name"},
        "value": "{{account_name}}",
    },
    {
        "id": "step_6",
        "type": "fill",
        "target": {"strategy": "label", "value": "Use"},
        "value": "{{account_use}}",
    },
    {
        "id": "step_7",
        "type": "click",
        "target": {
            "strategy": "role",
            "role": "button",
            "name": "Open {{account}} Account",
        },
    },
]


def _artifact_has_open_click(artifact: dict | None) -> bool:
    if not artifact:
        return False
    blob = json.dumps(artifact.get("steps") or []).lower()
    return "open" in blob and ("account name" in blob or "account_name" in blob)


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
    if "already exists" in lowered or "already have a" in lowered:
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
    account = str(task.params.get("account") or "Checking").strip() or "Checking"
    name = str(task.params.get("account_name") or account).strip() or account
    use = str(task.params.get("account_use") or "Personal").strip() or "Personal"

    print(
        f"Create a {account} account named {name} ({use})? "
        "This will open the account in Atlas Bank. (yes/no)"
    )
    if not ask_yes_no("> "):
        return f"{account} account was not created."

    print(f"[open_account] creating {account} named {name} ({use})")
    member_id = current_member_id()
    artifact = find_artifact_by_id(OPEN_ACCOUNT, member_id)
    use_stored = _artifact_has_open_click(artifact)

    if artifact is not None and use_stored:
        artifact_ref = f"{artifact.get('artifact_id')}/v{artifact.get('version')}"
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
            answer = _normalize_answer(
                account, name, use, str(result.get("answer") or "")
            )
            if own_run:
                logger.finish(status="success")
            return answer
        if own_run:
            logger.finish(
                status="failed",
                error=str(result.get("error") or result.get("status")),
            )
        print(f"[replay] failed: {result.get('error')}; falling back to discovery")

    logger = run_logger
    if own_run or logger is None:
        logger = RunLogger("discovery", task.goal)
    else:
        logger.event(type="operator", operator=OPEN_ACCOUNT, mode="discovery")
    try:
        result = await run_replay(
            task.goal,
            {
                "artifact_id": OPEN_ACCOUNT,
                "steps": OPEN_ACCOUNT_STEPS,
                "_path": None,
            },
            browser_manager,
            logger,
            skip_auth=skip_auth,
        )
        if result.get("status") != "replayed":
            if own_run:
                logger.finish(
                    status="failed",
                    error=str(result.get("error") or result.get("status")),
                )
            return str(result.get("error") or f"{account} account was not created.")
        path = persist_artifact(
            {
                "goal": task.goal,
                "recorded_steps": OPEN_ACCOUNT_STEPS,
                "checkpoints": {
                    "member_details_displayed": True,
                    "account_form_filled": True,
                    "account_opened": True,
                },
            }
        )
        if path is not None:
            logger.set_artifact_created(f"{OPEN_ACCOUNT}/v1")
            print(f"Operator: {path}")
        answer = _normalize_answer(
            account,
            name,
            use,
            str(result.get("answer") or result.get("last_result") or ""),
        )
        if own_run:
            logger.finish(status="success")
        return answer
    except Exception as exc:
        if own_run:
            logger.finish(status="failed", error=str(exc))
        raise
