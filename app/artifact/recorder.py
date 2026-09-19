from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.plan import (
    is_create_statement_goal,
    is_delete_account_goal,
    is_open_account_goal,
    is_transfer_goal,
    plan_query,
)

ROOT = Path(__file__).resolve().parents[2]
OPERATORS_DIR = ROOT / "operators"
ARTIFACTS_DIR = OPERATORS_DIR  # backward-compatible alias

CHECKPOINT_NAMES = {
    "member_details_displayed": "member_details_visible",
    "savings_account_displayed": "savings_balance_visible",
    "balance_extracted": "savings_balance_visible",
    "checking_account_displayed": "checking_balance_visible",
    "transfer_form_visible": "transfer_form_visible",
    "transfer_review_visible": "transfer_review_visible",
    "transfer_success_visible": "transfer_success_visible",
    "transfer_id_extracted": "transfer_id_visible",
    "transactions_visible": "transactions_visible",
    "account_opened": "account_opened",
    "account_deleted": "account_deleted",
}


def _parameterize_target(action: dict) -> str:
    target = action.get("target") or ""
    name = action.get("action")
    lower = target.strip().lower()
    if name == "click" and re.search(r"open\s+(checking|savings)\s+account", lower):
        return "Open {{account}} Account"
    if name == "click" and re.search(r"delete\s+(checking|savings)\s+account", lower):
        return "Delete {{account}} Account"
    if name == "read" and re.search(r"(savings|checking)[- ]account", lower):
        return "{{account_testid}}"
    return target


def _parameterize_value(action: dict) -> str | None:
    if action.get("action") != "fill":
        return None
    target = (action.get("target") or "").strip().lower()
    if "user" in target or "member" in target:
        return "{{member_id}}"
    if "pass" in target:
        return "{{password}}"
    if "from account" in target:
        return "{{from_account}}"
    if "to account" in target:
        return "{{to_account}}"
    if "account name" in target:
        return "{{account_name}}"
    if target.strip() == "use" or target.strip() == "account use":
        return "{{account_use}}"
    if "amount" in target:
        return "{{amount}}"
    if "memo" in target:
        return "{{memo}}"
    return action.get("value")


def _target_schema(action: dict) -> dict[str, Any]:
    name = action.get("action")
    target = _parameterize_target(action)
    if name == "fill":
        return {"strategy": "label", "value": target}
    if name == "click":
        return {"strategy": "role", "role": "button", "name": target}
    if name == "read":
        if "{{" in target or "-" in target or str(target).endswith("account"):
            return {"strategy": "testid", "value": target}
        return {"strategy": "text", "value": target}
    if name == "navigate":
        if "login" in str(target).lower() or not target:
            return {"strategy": "url", "value": "{{bank_url}}"}
        return {"strategy": "url", "value": target}
    return {"strategy": "text", "value": target}


def action_to_step(action: dict, index: int) -> dict[str, Any]:
    """Turn a verified AgentAction into a replayable artifact step."""
    step: dict[str, Any] = {
        "id": f"step_{index}",
        "type": action.get("action"),
        "target": _target_schema(action),
    }
    value = _parameterize_value(action)
    if value is not None:
        step["value"] = value
    return step


def current_member_id() -> str:
    return os.getenv("BANK_USERNAME", "alex")


def query_signature(goal: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (goal or "").lower()).strip()


def artifact_id_for(goal: str) -> str:
    tasks = plan_query(goal)
    if tasks:
        return tasks[0].artifact_id
    if is_transfer_goal(goal):
        return "transfer_funds"
    if is_open_account_goal(goal):
        return "open_account"
    if is_delete_account_goal(goal):
        return "delete_account"
    if is_create_statement_goal(goal):
        return "create_statement"
    return "lookup_balance"


def artifact_id_from_state(state: dict) -> str:
    goal = state.get("goal") or ""
    tasks = plan_query(goal)
    if tasks:
        return tasks[0].artifact_id
    blob = str(state.get("recorded_steps") or []).lower()
    if "open {{account}}" in blob or "open checking" in blob or "open savings" in blob:
        return "open_account"
    if "confirm transfer" in blob or "review transfer" in blob:
        return "transfer_funds"
    if "delete {{account}}" in blob or "delete checking" in blob or "delete savings" in blob:
        return "delete_account"
    if "transaction-table" in blob:
        return "create_statement"
    for step in reversed(list(state.get("recorded_steps") or [])):
        if step.get("type") != "read":
            continue
        target = ((step.get("target") or {}).get("value") or "").lower()
        if "transfer-id" in target or "transaction" in target:
            return "transfer_funds"
        if "account_testid" in target or "checking" in target or "saving" in target:
            return "lookup_balance"
    return artifact_id_for(goal)


def matching_artifact_id(goal: str) -> str | None:
    """Reuse an artifact when the query is a single known task."""
    tasks = plan_query(goal)
    if len(tasks) == 1:
        return tasks[0].artifact_id
    return None


def artifact_dir(artifact_id: str) -> Path:
    return ARTIFACTS_DIR / artifact_id


def artifact_path_for(artifact_id: str, version: int) -> Path:
    return artifact_dir(artifact_id) / f"v{version}.json"


def _version_from_name(name: str) -> int | None:
    if not name.startswith("v") or not name.endswith(".json"):
        return None
    suffix = name[1:-5]
    return int(suffix) if suffix.isdigit() else None


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("steps"):
        return None
    return data


def _latest_version_number(artifact_id: str) -> int:
    folder = artifact_dir(artifact_id)
    if not folder.is_dir():
        return 0
    versions = [
        version
        for path in folder.glob("v*.json")
        if (version := _version_from_name(path.name)) is not None
    ]
    return max(versions, default=0)


def _iter_artifacts(member_id: str | None = None):
    if not ARTIFACTS_DIR.is_dir():
        return
    for folder in ARTIFACTS_DIR.iterdir():
        if not folder.is_dir():
            continue
        for path in folder.glob("v*.json"):
            version = _version_from_name(path.name)
            data = _load_json(path)
            if version is None or data is None:
                continue
            recorded_for = data.get("recorded_for")
            if member_id and recorded_for not in (None, "", member_id):
                continue
            data["_path"] = str(path)
            data["version"] = version
            yield version, path, data


def find_artifact_by_id(artifact_id: str, member_id: str | None = None) -> dict[str, Any] | None:
    member_id = member_id or current_member_id()
    return _latest_for(artifact_id, member_id)


def find_artifact_for_query(goal: str, member_id: str | None = None) -> dict[str, Any] | None:
    member_id = member_id or current_member_id()
    wanted_id = matching_artifact_id(goal)
    signature = query_signature(goal)
    matches: list[tuple[int, int, dict[str, Any]]] = []
    for version, _path, data in _iter_artifacts(member_id):
        artifact_id = data.get("artifact_id") or Path(data["_path"]).parent.name
        signatures = {
            query_signature(data.get("source_query") or ""),
            *(query_signature(item) for item in data.get("query_signatures") or []),
        }
        signatures.discard("")
        rank = 0
        if signature and signature in signatures:
            rank += 3
        if wanted_id and artifact_id == wanted_id:
            rank += 2
        if rank == 0:
            continue
        matches.append((rank, version, data))
    if not matches:
        return None
    _rank, _version, data = max(matches, key=lambda item: (item[0], item[1]))
    return data


def _checkpoint_list(state: dict) -> list[str]:
    seen: list[str] = []
    for name, passed in (state.get("checkpoints") or {}).items():
        if not passed:
            continue
        mapped = CHECKPOINT_NAMES.get(name)
        if mapped and mapped not in seen:
            seen.append(mapped)
    return seen


def build_artifact(state: dict) -> dict[str, Any]:
    artifact_id = artifact_id_from_state(state)
    goal = state.get("goal") or ""
    signatures = [query_signature(goal)] if query_signature(goal) else []
    if artifact_id == "transfer_funds" or artifact_id.startswith("transfer_"):
        inputs = {
            "member_id": {"type": "string", "required": True},
            "password": {"type": "string", "required": True},
            "from_account": {"type": "string", "required": True},
            "to_account": {"type": "string", "required": True},
            "amount": {"type": "currency", "required": True},
            "memo": {"type": "string", "required": False},
            "bank_url": {"type": "string", "required": False},
        }
        outputs = {
            "transfer_id": {"type": "string"},
            "transactions": {"type": "list"},
        }
    elif artifact_id == "open_account" or artifact_id.startswith("open_"):
        inputs = {
            "member_id": {"type": "string", "required": True},
            "password": {"type": "string", "required": True},
            "account": {"type": "string", "required": True},
            "account_name": {"type": "string", "required": True},
            "account_use": {"type": "string", "required": True},
            "bank_url": {"type": "string", "required": False},
        }
        outputs = {
            "account_status": {"type": "string"},
        }
    elif artifact_id == "create_statement":
        inputs = {
            "member_id": {"type": "string", "required": True},
            "password": {"type": "string", "required": True},
            "account": {"type": "string", "required": False},
            "month": {"type": "string", "required": True},
            "bank_url": {"type": "string", "required": False},
        }
        outputs = {
            "statement_path": {"type": "string"},
            "transactions": {"type": "list"},
        }
    elif artifact_id == "delete_account" or artifact_id.startswith("delete_"):
        inputs = {
            "member_id": {"type": "string", "required": True},
            "password": {"type": "string", "required": True},
            "account": {"type": "string", "required": True},
            "bank_url": {"type": "string", "required": False},
        }
        outputs = {
            "account_status": {"type": "string"},
        }
    else:
        inputs = {
            "member_id": {"type": "string", "required": True},
            "password": {"type": "string", "required": True},
            "account": {"type": "string", "required": True},
            "bank_url": {"type": "string", "required": False},
        }
        outputs = {
            "balance": {"type": "currency"},
        }
    return {
        "artifact_id": artifact_id,
        "version": 1,
        "inputs": inputs,
        "outputs": outputs,
        "steps": list(state.get("recorded_steps") or []),
        "checkpoints": _checkpoint_list(state),
        "recorded_for": current_member_id(),
        "source_query": goal,
        "query_signatures": signatures,
    }


def _latest_for(artifact_id: str, member_id: str) -> dict[str, Any] | None:
    matches = [
        (version, data)
        for version, _path, data in _iter_artifacts(member_id)
        if (data.get("artifact_id") or Path(data["_path"]).parent.name) == artifact_id
    ]
    if not matches:
        return None
    _version, data = max(matches, key=lambda item: item[0])
    return data


def save_artifact(artifact: dict[str, Any]) -> Path:
    artifact_id = str(artifact["artifact_id"])
    member_id = str(artifact.get("recorded_for") or current_member_id())
    existing = _latest_for(artifact_id, member_id)
    if existing is not None and existing.get("steps") == artifact.get("steps"):
        signatures = []
        for collection in (
            existing.get("query_signatures"),
            artifact.get("query_signatures"),
            [existing.get("source_query"), artifact.get("source_query")],
        ):
            for item in collection or []:
                signature = query_signature(str(item))
                if signature and signature not in signatures:
                    signatures.append(signature)
        existing["query_signatures"] = signatures
        path = Path(existing["_path"])
        payload = {key: value for key, value in existing.items() if not str(key).startswith("_")}
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    folder = artifact_dir(artifact_id)
    folder.mkdir(parents=True, exist_ok=True)
    version = _latest_version_number(artifact_id) + 1
    artifact["version"] = version
    path = artifact_path_for(artifact_id, version)
    payload = {key: value for key, value in artifact.items() if not str(key).startswith("_")}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def persist_artifact(state: dict) -> Path | None:
    artifact = build_artifact(state)
    if not artifact.get("steps"):
        return None
    return save_artifact(artifact)
