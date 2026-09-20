from __future__ import annotations

import json
import os
import re
from typing import Any

from app.agent.act import act as run_act
from app.agent.safety import async_safety_check
from app.plan import account_params, is_transfer_goal, parse_transfer_goal, plan_query
from app.agent.verify import verify as run_verify
from app.browser.manager import BrowserManager
from app.run.logger import RunLogger

TEMPLATE = re.compile(r"\{\{\s*(\w+)\s*\}\}")
CURRENCY = re.compile(r"\$[\d,]+(?:\.\d{2})?")


def current_inputs(goal: str = "") -> dict[str, str]:
    member_id = os.getenv("BANK_USERNAME", "alex123")
    inputs = {
        "member_id": member_id,
        "username": member_id,
        "bank_url": os.getenv("BANK_URL", "http://localhost:5173/login"),
    }
    tasks = plan_query(goal)
    if tasks:
        params = dict(tasks[0].params or {})
        if params.get("account"):
            merged = account_params(params["account"])
            merged.update({key: value for key, value in params.items() if value not in (None, "")})
            params = merged
        for key, value in params.items():
            if value not in (None, ""):
                inputs[key] = str(value)
    if is_transfer_goal(goal):
        parsed = parse_transfer_goal(goal)
        for key, value in parsed.items():
            if value not in (None, ""):
                inputs[key] = value
    return inputs


def substitute(value: Any, inputs: dict[str, str]) -> Any:
    if not isinstance(value, str):
        return value
    return TEMPLATE.sub(lambda match: inputs.get(match.group(1), match.group(0)), value)


def step_to_action(step: dict[str, Any], inputs: dict[str, str]) -> dict[str, Any]:
    target = step.get("target") or {}
    strategy = target.get("strategy")
    if strategy == "role":
        target_str = substitute(target.get("name") or target.get("value") or "", inputs)
    else:
        target_str = substitute(target.get("value") or "", inputs)
    action: dict[str, Any] = {
        "action": step.get("type"),
        "target": target_str,
        "value": substitute(step.get("value"), inputs),
        "reason": f"replay {step.get('id') or 'step'}",
        "locator_policy": "dom_only",
    }
    if strategy:
        action["strategy"] = strategy
    if target.get("role"):
        action["role"] = target.get("role")
    return action


def _dashboard_url() -> str:
    bank = os.getenv("BANK_URL", "http://localhost:5173/login")
    lowered = bank.rstrip("/")
    if lowered.lower().endswith("/login"):
        return lowered[: -len("/login")] + "/dashboard"
    return lowered + "/dashboard"


def _is_auth_step(step: dict[str, Any]) -> bool:
    target = step.get("target") or {}
    value = str(target.get("value") or target.get("name") or "").lower()
    step_type = step.get("type")
    if step_type == "navigate" and (
        "login" in value or "bank_url" in value or "{{bank_url}}" in value
    ):
        return True
    if step_type == "fill" and any(token in value for token in ("user", "pass", "member")):
        return True
    if step_type == "click" and "sign in" in value:
        return True
    return False


async def _is_signed_in(browser_manager: BrowserManager) -> bool:
    page = browser_manager.page
    if page is None:
        return False
    url = page.url or ""
    if not any(part in url for part in ("/dashboard", "/transfer", "/transactions")):
        return False
    wanted = (os.getenv("BANK_USERNAME", "alex123") or "alex123").strip().lower()
    try:
        from app.browser.accounts import _session_username

        current = await _session_username(page)
    except Exception:
        current = None
    if current is not None:
        return current.lower() == wanted
    # Fallback when session parse fails: signed-in chrome is visible.
    try:
        return await page.get_by_test_id("signed-in-member").count() > 0
    except Exception:
        return False


async def _ensure_replay_location(
    browser_manager: BrowserManager,
    steps: list[dict[str, Any]],
    skip_auth: bool,
) -> None:
    if not skip_auth:
        return
    page = await browser_manager.open()
    blob = json.dumps(steps).lower()
    needs_dashboard = any(
        token in blob
        for token in (
            "savings-account",
            "checking-account",
            "account_testid",
            "open checking",
            "open savings",
            "open {{account}}",
            "open-checking",
            "open-savings",
            "transaction-table",
            "transactions",
            "delete {{account}}",
            "delete checking",
            "delete savings",
        )
    )
    if needs_dashboard and "/dashboard" not in (page.url or ""):
        await page.goto(_dashboard_url(), wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")


def _answer_from_outputs(
    artifact: dict[str, Any],
    outputs: dict[str, Any],
    last_result: str | None,
    inputs: dict[str, str] | None = None,
) -> str:
    blob = " ".join([str(last_result or ""), *[str(value) for value in outputs.values()]])
    artifact_id = str(artifact.get("artifact_id") or "")
    parsed = inputs or {}
    if artifact_id in {"open_account"} or artifact_id.startswith("open_"):
        account = parsed.get("account") or "Checking"
        lowered = blob.lower()
        if "additional accounts" in lowered:
            return "You already have Checking and Savings accounts. Additional accounts are not allowed."
        if "already" in lowered:
            return f"{account} account already exists."
        extras = ", ".join(
            part
            for part in (
                parsed.get("account_name"),
                parsed.get("account_use"),
            )
            if part
        )
        if "opened" in lowered or "clicked open" in lowered or "created" in lowered:
            if extras:
                return f"{account} account created successfully ({extras})."
            return f"{account} account created successfully."
        if extras:
            return f"{account} account created successfully ({extras})."
        return f"{account} account created successfully."
    if artifact_id in {"delete_account"} or artifact_id.startswith("delete_"):
        account = parsed.get("account") or "Checking"
        if "deleted" in blob.lower():
            return f"{account} account deleted."
        return f"Replayed {artifact_id}."
    if artifact_id in {"transfer_funds"} or artifact_id.startswith("transfer_"):
        table = str(outputs.get("transaction-table") or last_result or "").strip()
        if "Transfer to" in table or "Transfer from" in table:
            return table
        amount = parsed.get("amount") or ""
        source = parsed.get("from_account") or "Savings"
        destination = parsed.get("to_account") or "Checking"
        return f"Transferred ${amount} from {source} to {destination}."
    match = CURRENCY.search(blob)
    amount = match.group(0) if match else (last_result or "").strip()
    account = (parsed.get("account") or "Savings").lower()
    if amount:
        return f"Your {account} account balance is {amount}."
    return f"Replayed {artifact.get('artifact_id')} but no balance was visible."


async def run_replay(
    goal: str,
    artifact: dict[str, Any],
    browser_manager: BrowserManager,
    run_logger: RunLogger | None = None,
    skip_auth: bool = False,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.browser.viewport import current_viewport, viewport_compatible
    from app.artifact.recorder import mark_viewport_validated

    inputs = current_inputs(goal)
    context = dict(context or {})
    for key, value in context.items():
        if value is not None:
            inputs[key] = value

    active_viewport = getattr(browser_manager, "viewport", None) or current_viewport()
    if not viewport_compatible(artifact, active_viewport):
        return {
            "status": "replay_failed",
            "error": (
                "Artifact is not DOM-portable (coordinate/screenshot locators). "
                "Run discovery to create a DOM version for this viewport."
            ),
            "mode": "replay",
        }

    if is_transfer_goal(goal) and not inputs.get("amount"):
        return {
            "status": "replay_failed",
            "error": (
                "No transfer amount found in the request. "
                "The shell may have removed $20; use single quotes or omit the dollar sign, "
                "for example: python3 -m app.main 'Transfer 20 from savings to checking'"
            ),
            "mode": "replay",
        }
    print(
        f"[replay] flow={artifact.get('artifact_id')} "
        f"v{artifact.get('version')} "
        f"viewport={active_viewport.get('profile')} "
        f"{active_viewport.get('width')}x{active_viewport.get('height')} "
        f"locator=dom "
        f"account={inputs.get('account') or '-'} "
        f"account_name={inputs.get('account_name') or '-'} "
        f"account_use={inputs.get('account_use') or '-'} "
        f"amount={inputs.get('amount') or '-'} "
        f"from={inputs.get('from_account') or '-'} "
        f"to={inputs.get('to_account') or '-'}"
    )
    steps = list(artifact.get("steps") or [])
    if not steps:
        return {"status": "replay_failed", "error": "Artifact has no steps."}

    signed_in = skip_auth and await _is_signed_in(browser_manager)
    if signed_in:
        steps = [step for step in steps if not _is_auth_step(step)]
    elif not steps or steps[0].get("type") != "navigate":
        steps = [
            {
                "id": "step_0",
                "type": "navigate",
                "target": {
                    "strategy": "url",
                    "value": "{{bank_url}}",
                    "interaction": "dom",
                },
            },
            *steps,
        ]

    await _ensure_replay_location(browser_manager, steps, signed_in)

    state: dict[str, Any] = {
        "goal": goal,
        "outputs": {},
        "action_log": [],
        "checkpoints": {},
        "last_result": None,
        "mode": "replay",
    }

    for step in steps:
        action = step_to_action(step, inputs)
        print(
            f"[replay] {step.get('id')} {action['action']} "
            f"strategy={action.get('strategy') or 'auto'} "
            f"target={action.get('target')} value={action.get('value')}"
        )
        safety = await async_safety_check(
            {
                "action": action,
                "goal": goal,
                "params": inputs,
                "allow_delete": bool(context.get("allow_delete"))
                or str(artifact.get("artifact_id") or "") == "delete_account",
                "allow_open": bool(context.get("allow_open"))
                or str(artifact.get("artifact_id") or "") == "open_account",
                "skip_large_transfer_approval": bool(
                    context.get("skip_large_transfer_approval")
                    or inputs.get("skip_large_transfer_approval")
                ),
                "guardrail_approved": bool(context.get("guardrail_approved")),
            },
            browser_manager=browser_manager,
            run_logger=run_logger,
        )
        if safety.get("status") == "blocked":
            message = str(safety.get("answer") or safety.get("error") or "Blocked by guardrail")
            return {
                "status": "guardrail_blocked",
                "answer": message,
                "error": message,
                "mode": "replay",
                "guardrail_decision": safety.get("guardrail_decision"),
            }

        step_state = {
            **state,
            "action": action,
            "params": inputs,
            "allow_delete": bool(context.get("allow_delete"))
            or str(artifact.get("artifact_id") or "") == "delete_account",
            "allow_open": bool(context.get("allow_open"))
            or str(artifact.get("artifact_id") or "") == "open_account",
            "skip_large_transfer_approval": bool(
                context.get("skip_large_transfer_approval")
                or inputs.get("skip_large_transfer_approval")
            ),
            "guardrail_approved": bool(context.get("guardrail_approved")),
            "guardrails_already_checked": True,
            "run_logger": run_logger,
        }
        acted = await run_act(step_state, browser_manager)
        state.update(acted)
        if run_logger is not None:
            run_logger.log_act(action)
        if acted.get("status") == "blocked":
            message = str(acted.get("last_result") or acted.get("answer") or "Blocked by guardrail")
            return {
                "status": "guardrail_blocked",
                "answer": message,
                "error": message,
                "mode": "replay",
                "guardrail_decision": acted.get("guardrail_decision"),
            }
        if str(acted.get("last_result") or "").startswith("Action failed"):
            if run_logger is not None:
                run_logger.log_verify(action, False)
            return {
                "status": "replay_failed",
                "error": acted.get("last_result"),
                "mode": "replay",
                "viewport": active_viewport,
            }
        last = str(acted.get("last_result") or "").lower()
        if (
            "already exists" in last or "additional accounts" in last
        ) and str(artifact.get("artifact_id") or "").startswith("open"):
            verified = await run_verify({**state, "action": action}, browser_manager)
            state.update(verified)
            if run_logger is not None:
                run_logger.log_verify(action, bool(verified.get("checkpoint_passed")))
            break

        verified = await run_verify({**state, "action": action}, browser_manager)
        state.update(verified)
        if run_logger is not None:
            run_logger.log_verify(action, bool(verified.get("checkpoint_passed")))
        if not verified.get("checkpoint_passed"):
            return {
                "status": "replay_failed",
                "error": f"Checkpoint failed on {step.get('id')}",
                "mode": "replay",
                "viewport": active_viewport,
            }

    answer = _answer_from_outputs(artifact, state.get("outputs") or {}, state.get("last_result"), inputs)
    # Same DOM artifact worked on this screen — record without rediscovery.
    try:
        mark_viewport_validated(artifact, active_viewport)
    except Exception:
        pass
    try:
        from app.artifact.recorder import record_artifact_usage

        artifact_id = str(artifact.get("artifact_id") or "")
        version = int(artifact.get("version") or 0)
        if artifact_id and version > 0:
            record_artifact_usage(artifact_id, version)
    except Exception:
        pass
    print(
        f"[replay] done without LLM "
        f"(viewport={active_viewport.get('profile')}, locator=dom)"
    )
    return {
        "answer": answer,
        "outputs": state.get("outputs") or {},
        "last_result": state.get("last_result"),
        "action_log": state.get("action_log") or [],
        "checkpoints": state.get("checkpoints") or {},
        "artifact_path": artifact.get("_path"),
        "status": "replayed",
        "mode": "replay",
        "viewport": active_viewport,
    }


async def run_replay_with_fallbacks(
    goal: str,
    artifact: dict[str, Any] | None,
    browser_manager: BrowserManager,
    run_logger: RunLogger | None = None,
    skip_auth: bool = False,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Try the preferred DOM artifact, then older versions, before callers start discovery.

    Desktop-captured operators replay on tablet/mobile via DOM + scroll-into-view.
    Only when no version works do runners create a new discovery version.
    """
    from app.artifact.recorder import iter_artifact_rollbacks

    if artifact is None:
        return {"status": "replay_failed", "error": "No artifact", "mode": "replay"}

    candidates = [artifact]
    artifact_id = str(artifact.get("artifact_id") or "")
    seen_versions = {int(artifact.get("version") or 0)}
    for older in iter_artifact_rollbacks(artifact_id):
        version = int(older.get("version") or 0)
        if version in seen_versions:
            continue
        seen_versions.add(version)
        candidates.append(older)

    last_error: dict[str, Any] = {
        "status": "replay_failed",
        "error": "UI changed",
        "mode": "replay",
    }
    for candidate in candidates:
        result = await run_replay(
            goal,
            candidate,
            browser_manager,
            run_logger,
            skip_auth=skip_auth,
            context=context,
        )
        if result.get("status") in {"replayed", "guardrail_blocked"}:
            return result
        last_error = result
        print(
            f"[replay] v{candidate.get('version')} failed on this viewport; "
            f"trying older DOM artifact or discovery"
        )
    return last_error
