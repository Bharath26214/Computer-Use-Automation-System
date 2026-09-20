from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.browser.viewport import current_viewport
from app.guardrails.risk import classify_action_risk
from app.plan import (
    is_delete_account_goal,
    is_open_account_goal,
    is_transfer_goal,
    plan_query,
)

ROOT = Path(__file__).resolve().parents[2]
OPERATORS_DIR = ROOT / "operators"
ARTIFACTS_DIR = OPERATORS_DIR  # backward-compatible alias

# Member IDs are opaque tokens: letters then exactly three digits (e.g. alex123).
MEMBER_ID_PATTERN = r"^[A-Za-z]+\d{3}$"
MEMBER_ID_RE = re.compile(MEMBER_ID_PATTERN)

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

CHECKPOINT_DESCRIPTIONS = {
    "member_details_visible": "Signed-in member chrome is visible on the page.",
    "checking_balance_visible": "Checking account balance card/text is present.",
    "savings_balance_visible": "Savings account balance card/text is present.",
    "transfer_form_visible": "Transfer form controls are visible.",
    "transfer_review_visible": "Transfer review panel is visible before confirm.",
    "transfer_success_visible": "Transfer success confirmation is visible.",
    "transfer_id_visible": "A transfer id or matching ledger rows are available.",
    "transactions_visible": "Transactions table is visible.",
    "account_opened": "The requested product account card is visible after open.",
    "account_deleted": "The account is gone or a delete confirmation message is shown.",
}

ARTIFACT_META: dict[str, dict[str, str]] = {
    "lookup_balance": {
        "title": "Lookup account balance",
        "description": (
            "Sign in with a member ID, open the dashboard, and read the Checking "
            "or Savings balance from a stable test id."
        ),
    },
    "transfer_funds": {
        "title": "Transfer funds",
        "description": (
            "Sign in, move a typed currency amount between Checking and Savings, "
            "confirm the transfer, then extract the matching debit and credit rows."
        ),
    },
    "open_account": {
        "title": "Open account",
        "description": (
            "Sign in and open a Checking or Savings product with a nickname and use. "
            "Fails when both products already exist for the member."
        ),
    },
    "delete_account": {
        "title": "Delete account",
        "description": (
            "Sign in and delete a Checking or Savings product from the dashboard. "
            "Nonzero balances must be transferred first by the calling workflow."
        ),
    },
}


def _parameterize_target(action: dict) -> str:
    target = action.get("target") or ""
    name = action.get("action")
    lower = target.strip().lower()
    if name == "click" and re.search(r"(open|add)\s+(checking|savings)\s+account", lower):
        verb = "Add" if re.search(r"\badd\b", lower) else "Open"
        return f"{verb} {{{{account}}}} Account"
    if name == "click" and re.search(r"(delete|close)\s+(checking|savings)\s+account", lower):
        verb = "Close" if re.search(r"\bclose\b", lower) else "Delete"
        return f"{verb} {{{{account}}}} Account"
    if name == "click" and re.search(r"view\s+(checking|savings)\s+balance", lower):
        return "View {{account}} Balance"
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
        # Password is not part of the login contract; drop the step value.
        return None
    if "from account" in target:
        return "{{from_account}}"
    if "to account" in target:
        return "{{to_account}}"
    if "account name" in target or "nickname" in target:
        return "{{account_name}}"
    if target.strip() in {"use", "account use", "purpose"}:
        return "{{account_use}}"
    if "amount" in target:
        return "{{amount}}"
    if "memo" in target or target.strip() == "note":
        return "{{memo}}"
    return action.get("value")


def _robustness_for(strategy: str, target: str) -> str:
    lower = (target or "").lower()
    if strategy == "testid":
        return (
            "Prefer data-testid attributes; they are stable across copy changes "
            "and less brittle than visible text."
        )
    if strategy == "url":
        return "Navigate by absolute/templated URL so replay starts from a known route."
    if strategy == "label":
        if "user" in lower:
            return (
                "Use the Username field label; login is username-only "
                "(member_id = name + three digits)."
            )
        return "Locate the control by accessible label text shown beside the field."
    if strategy == "role":
        return (
            "Locate by ARIA role + accessible name so the control remains findable "
            "if layout shifts but semantics stay the same."
        )
    return "Fall back to visible text matching when no stronger locator exists."


def _target_schema(action: dict) -> dict[str, Any]:
    name = action.get("action")
    target = _parameterize_target(action)
    if name == "fill":
        strategy = "label"
        schema = {"strategy": strategy, "value": target}
    elif name == "click":
        strategy = "role"
        schema = {"strategy": strategy, "role": "button", "name": target}
    elif name == "read":
        if "{{" in target or "-" in target or str(target).endswith("account"):
            strategy = "testid"
            schema = {"strategy": strategy, "value": target}
        else:
            strategy = "text"
            schema = {"strategy": strategy, "value": target}
    elif name == "navigate":
        strategy = "url"
        if "login" in str(target).lower() or not target:
            schema = {"strategy": strategy, "value": "{{bank_url}}"}
        else:
            schema = {"strategy": strategy, "value": target}
    else:
        strategy = "text"
        schema = {"strategy": strategy, "value": target}
    schema["robustness"] = _robustness_for(strategy, str(target))
    # Explicit contract: Playwright uses DOM objects, never screen coordinates.
    schema["interaction"] = "dom"
    return schema


def _step_label(action: dict) -> str:
    """Human-readable intent for a step (open application, enter amount, …)."""
    name = str(action.get("action") or "").strip().lower()
    raw_target = str(action.get("target") or "").strip()
    target = _parameterize_target(action)
    lower = raw_target.lower()
    value = str(action.get("value") or "").strip()

    if name == "navigate":
        if "login" in lower or not raw_target or "{{bank_url}}" in str(target):
            return "Open application — navigate to login"
        if "dashboard" in lower:
            return "Navigate to dashboard"
        if "transfer" in lower:
            return "Navigate to transfer page"
        if "transaction" in lower:
            return "Navigate to transactions"
        return f"Navigate to {target or raw_target or 'page'}"

    if name == "fill":
        if "user" in lower or "member" in lower:
            return "Enter member ID — fill Username"
        if "from account" in lower:
            return "Select from account — fill From Account"
        if "to account" in lower:
            return "Select to account — fill To Account"
        if "amount" in lower:
            return "Enter amount — fill Amount"
        if "memo" in lower or lower in {"note"}:
            return "Enter memo — fill Memo"
        if "account name" in lower or "nickname" in lower:
            return "Enter account name — fill Account name"
        if lower in {"use", "account use", "purpose"}:
            return "Select account use — fill Use"
        label = target or raw_target or "field"
        return f"Fill {label}" + (f" with {value}" if value and "{{" not in value else "")

    if name == "click":
        if "sign in" in lower or "log in" in lower:
            return "Sign in — click Sign In"
        if re.search(r"(open|add)\s+(checking|savings|\{\{account\}\})\s+account", lower):
            return f"Open account — click {target or raw_target}"
        if re.search(r"(delete|close)\s+(checking|savings|\{\{account\}\})\s+account", lower):
            return f"Delete account — click {target or raw_target}"
        if "transfer money" in lower:
            return "Open transfer form — click Transfer Money"
        if "review transfer" in lower:
            return "Review transfer — click Review Transfer"
        if "confirm transfer" in lower:
            return "Confirm transfer — click Confirm Transfer"
        if "transaction" in lower:
            return "Open transactions — click Transactions"
        if "dashboard" in lower:
            return "Return to dashboard — click Dashboard"
        return f"Click {target or raw_target or 'control'}"

    if name == "read":
        if "checking" in lower or "savings" in lower or "account_testid" in str(target):
            return f"Read account balance — read {target or raw_target}"
        if "transaction" in lower:
            return f"Read transaction table — read {target or raw_target}"
        if "transfer" in lower and "id" in lower:
            return f"Read transfer id — read {target or raw_target}"
        if "open-account" in lower or "message" in lower:
            return f"Read status message — read {target or raw_target}"
        return f"Read {target or raw_target or 'page text'}"

    if name == "finish":
        return "Finish — return final response"
    if name == "request_human":
        return "Request human approval"
    return f"{name} {target or raw_target}".strip()


def _step_risk(action: dict) -> str:
    return classify_action_risk(action).value


def action_to_step(action: dict, index: int) -> dict[str, Any]:
    """Turn a verified AgentAction into a replayable artifact step."""
    name = str(action.get("action") or "act")
    target = _parameterize_target(action)
    # Skip password fills — Atlas login is username-only.
    if name == "fill" and "pass" in str(action.get("target") or "").lower():
        return {}
    # Never persist coordinate-based steps.
    if isinstance(action.get("target"), dict) and (
        "x" in action["target"] or "y" in action["target"]
    ):
        return {}
    step: dict[str, Any] = {
        "id": f"step_{index}",
        "type": name,
        "description": _step_label(action),
        "risk": _step_risk(action),
        "target": _target_schema(action),
    }
    value = _parameterize_value(action)
    if value is not None:
        step["value"] = value
    return step


def current_member_id() -> str:
    return (os.getenv("BANK_USERNAME") or "alex123").strip()


# Demo members whose post-login gate is a distinct error capability.
MEMBER_ERROR_SCENARIOS: dict[str, str] = {
    "casey404": "page_not_found",
    "morgan789": "human_intervention",
    "taylor321": "reloading",
    "blake000": "hard_failure",
}


def expected_error_kind_for_member(member_id: str | None = None) -> str | None:
    """Error kind this member is expected to exercise, or None for the happy path."""
    mid = (member_id or current_member_id() or "").strip().lower()
    return MEMBER_ERROR_SCENARIOS.get(mid)


def artifact_matches_member_scenario(
    artifact: dict[str, Any] | None,
    member_id: str | None = None,
) -> bool:
    """
    Happy-path members only replay blank error_handling versions.
    Scenario members only replay a version that already recorded their error —
    otherwise discovery creates a new capability (vN) for that error.
    """
    if not artifact:
        return False
    expected = expected_error_kind_for_member(member_id)
    kinds = _error_kinds(artifact.get("error_handling"))
    if not expected:
        return not kinds
    return expected in kinds


def validate_member_id(member_id: str) -> str | None:
    """Return an error string if member_id is not name+3digits."""
    value = (member_id or "").strip()
    if not value:
        return "Member ID is required (letters followed by exactly three digits)."
    if not MEMBER_ID_RE.fullmatch(value):
        return (
            "Member ID must be a name followed by exactly three digits "
            "(example: alex123)."
        )
    return None


def query_signature(goal: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", (goal or "").lower()).strip()
    # Strip opaque member tokens so signatures stay capability-focused, not PII.
    text = re.sub(r"\b[a-z]+\d{3}\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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
    return "lookup_balance"


def artifact_id_from_state(state: dict) -> str:
    goal = state.get("goal") or ""
    blob = str(state.get("recorded_steps") or []).lower()
    # Prefer step shape over a vague goal (e.g. seed scripts / discovery leftovers).
    if (
        "open {{account}}" in blob
        or "open checking" in blob
        or "open savings" in blob
        or ("account name" in blob and "open" in blob)
    ):
        return "open_account"
    if "confirm transfer" in blob or "review transfer" in blob:
        return "transfer_funds"
    if (
        "delete {{account}}" in blob
        or "delete checking" in blob
        or "delete savings" in blob
    ):
        return "delete_account"
    for step in reversed(list(state.get("recorded_steps") or [])):
        if step.get("type") != "read":
            continue
        target = ((step.get("target") or {}).get("value") or "").lower()
        if "transfer-id" in target or "transaction" in target:
            return "transfer_funds"
        if "account_testid" in target or "checking" in target or "saving" in target:
            return "lookup_balance"

    tasks = plan_query(goal)
    if tasks:
        return tasks[0].artifact_id
    if is_transfer_goal(goal):
        return "transfer_funds"
    if is_open_account_goal(goal):
        return "open_account"
    if is_delete_account_goal(goal):
        return "delete_account"
    return artifact_id_for(goal)


def matching_artifact_id(goal: str) -> str | None:
    tasks = plan_query(goal)
    if len(tasks) == 1:
        return tasks[0].artifact_id
    return None


def artifact_dir(artifact_id: str) -> Path:
    return OPERATORS_DIR / artifact_id


def artifact_path_for(artifact_id: str, version: int) -> Path:
    return artifact_dir(artifact_id) / f"v{version}.json"


def metadata_path(artifact_id: str) -> Path:
    """operators/{artifact_id}/metadata.json — pins which version to try first."""
    return artifact_dir(artifact_id) / "metadata.json"


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


def _on_disk_versions(artifact_id: str) -> list[int]:
    folder = artifact_dir(artifact_id)
    if not folder.is_dir():
        return []
    versions = [
        version
        for path in folder.glob("v*.json")
        if (version := _version_from_name(path.name)) is not None
    ]
    return sorted(versions, reverse=True)


def read_metadata(artifact_id: str) -> dict[str, Any]:
    """
    Version pointer + usage so the most frequently used operator is preferred.

      {
        "artifact_id": "lookup_balance",
        "latest": 2,
        "most_frequent": 2,
        "usage_counts": {"1": 3, "2": 10}
      }
    """
    path = metadata_path(artifact_id)
    on_disk = _on_disk_versions(artifact_id)
    fallback = on_disk[0] if on_disk else 0
    empty = {
        "artifact_id": artifact_id,
        "latest": fallback,
        "most_frequent": fallback,
        "usage_counts": {},
    }
    if not path.is_file():
        return empty
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return empty
    if not isinstance(data, dict):
        return empty
    usage_raw = data.get("usage_counts") or {}
    usage_counts: dict[str, int] = {}
    if isinstance(usage_raw, dict):
        for key, value in usage_raw.items():
            try:
                usage_counts[str(int(key))] = int(value)
            except (TypeError, ValueError):
                continue
    most = data.get("most_frequent")
    latest = data.get("latest")
    if not isinstance(most, int) or most < 1:
        most = _most_frequent_version(usage_counts, on_disk) or fallback
    if not isinstance(latest, int) or latest < 1:
        latest = most or fallback
    return {
        "artifact_id": artifact_id,
        "latest": latest,
        "most_frequent": most,
        "usage_counts": usage_counts,
    }


def _most_frequent_version(
    usage_counts: dict[str, int],
    on_disk: list[int] | None = None,
) -> int | None:
    """Highest usage wins; ties break to higher version number."""
    candidates = on_disk or [int(key) for key in usage_counts]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda version: (int(usage_counts.get(str(version)) or 0), version),
    )


def write_metadata(
    artifact_id: str,
    latest: int | None = None,
    *,
    usage_counts: dict[str, int] | None = None,
) -> Path:
    """
    Persist metadata with usage_counts and pin latest/most_frequent to the
    most frequently used on-disk version (ties → higher version; all-zero → latest).
    """
    path = metadata_path(artifact_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    current = read_metadata(artifact_id)
    counts = dict(current.get("usage_counts") or {})
    if usage_counts is not None:
        for key, value in usage_counts.items():
            counts[str(int(key))] = int(value)
    on_disk = _on_disk_versions(artifact_id)
    counts = {key: value for key, value in counts.items() if int(key) in set(on_disk)}
    for version in on_disk:
        counts.setdefault(str(version), 0)

    all_zero = all(int(counts.get(str(v)) or 0) == 0 for v in on_disk) if on_disk else True
    if all_zero and latest is not None:
        preferred = int(latest)
    else:
        preferred = _most_frequent_version(counts, on_disk)
        if preferred is None:
            preferred = int(latest) if latest is not None else 0

    payload = {
        "artifact_id": artifact_id,
        "latest": int(preferred),
        "most_frequent": int(preferred),
        "usage_counts": {str(v): int(counts.get(str(v)) or 0) for v in sorted(on_disk)},
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def record_artifact_usage(artifact_id: str, version: int) -> dict[str, Any]:
    """Increment use count for a version and re-pin metadata to most frequent."""
    meta = read_metadata(artifact_id)
    counts = dict(meta.get("usage_counts") or {})
    key = str(int(version))
    counts[key] = int(counts.get(key) or 0) + 1
    write_metadata(artifact_id, usage_counts=counts)
    return read_metadata(artifact_id)


def version_candidates(artifact_id: str) -> list[int]:
    """
    Preferred try order: most frequently used first, then other versions by usage/version.
    """
    on_disk = _on_disk_versions(artifact_id)
    if not on_disk:
        return []
    meta = read_metadata(artifact_id)
    counts = dict(meta.get("usage_counts") or {})
    preferred = meta.get("most_frequent") or meta.get("latest") or on_disk[0]
    ordered = sorted(
        on_disk,
        key=lambda version: (
            0 if version == preferred else 1,
            -int(counts.get(str(version)) or 0),
            -version,
        ),
    )
    return ordered


def _latest_version_number(artifact_id: str) -> int:
    return max(_on_disk_versions(artifact_id), default=0)


def _load_version(artifact_id: str, version: int) -> dict[str, Any] | None:
    path = artifact_path_for(artifact_id, version)
    data = _load_json(path)
    if data is None:
        return None
    data["_path"] = str(path)
    data["version"] = int(data.get("version") or version)
    data.setdefault("artifact_id", artifact_id)
    return data


def _iter_artifacts(member_id: str | None = None):
    del member_id
    if not OPERATORS_DIR.is_dir():
        return
    for folder in sorted(OPERATORS_DIR.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        for path in sorted(folder.glob("v*.json")):
            version = _version_from_name(path.name)
            data = _load_json(path)
            if version is None or data is None:
                continue
            data["_path"] = str(path)
            data["version"] = int(data.get("version") or version)
            data.setdefault("artifact_id", folder.name)
            yield version, path, data


def find_artifact_by_id(artifact_id: str, member_id: str | None = None) -> dict[str, Any] | None:
    """
    Prefer the metadata-pinned version that matches this member's error scenario.

    Scenario users (e.g. casey404 → page_not_found) do not reuse a blank happy-path
    operator; callers fall through to discovery and store a new version.
    """
    member_id = (member_id or current_member_id()).strip()
    from app.browser.viewport import current_viewport, viewport_preference_score

    active = current_viewport()
    preferred = _latest_for(artifact_id)
    candidates: list[dict[str, Any]] = []
    for version, _path, data in _iter_artifacts():
        aid = data.get("artifact_id") or Path(data["_path"]).parent.name
        if aid != artifact_id:
            continue
        data = dict(data)
        data.setdefault("version", version)
        data.setdefault("locator_policy", "dom_only")
        if not artifact_matches_member_scenario(data, member_id):
            continue
        candidates.append(data)
    if not candidates:
        return None
    if preferred is not None and artifact_matches_member_scenario(preferred, member_id):
        preferred.setdefault("locator_policy", "dom_only")
        pref_score = viewport_preference_score(preferred, active)
        best = max(
            candidates,
            key=lambda item: (
                viewport_preference_score(item, active),
                int(item.get("version") or 0),
            ),
        )
        if pref_score >= viewport_preference_score(best, active):
            return preferred
        return best
    return max(
        candidates,
        key=lambda item: (
            viewport_preference_score(item, active),
            int(item.get("version") or 0),
        ),
    )


def find_artifact_for_query(goal: str, member_id: str | None = None) -> dict[str, Any] | None:
    member_id = (member_id or current_member_id()).strip()
    wanted_id = matching_artifact_id(goal)
    signature = query_signature(goal)
    matches: list[tuple[int, int, dict[str, Any]]] = []
    for version, _path, data in _iter_artifacts():
        if not artifact_matches_member_scenario(data, member_id):
            continue
        artifact_id = data.get("artifact_id") or Path(data["_path"]).parent.name
        signatures = {
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


def _success_conditions(checkpoint_ids: list[str]) -> list[dict[str, Any]]:
    conditions: list[dict[str, Any]] = []
    for item in checkpoint_ids:
        conditions.append(
            {
                "id": item,
                "description": CHECKPOINT_DESCRIPTIONS.get(
                    item, f"Checkpoint `{item}` must pass."
                ),
                "required": True,
            }
        )
    if not conditions:
        conditions.append(
            {
                "id": "flow_completed",
                "description": "All ordered steps executed without a failed checkpoint.",
                "required": True,
            }
        )
    return conditions


def _inputs_for(artifact_id: str) -> dict[str, Any]:
    member = {
        "type": "string",
        "required": True,
        "description": (
            "Opaque member login id: letters followed by exactly three digits. "
            "Do not store real personal names in artifacts; supply this at invoke time."
        ),
        "pattern": MEMBER_ID_PATTERN,
        "example": "alex123",
    }
    bank_url = {
        "type": "string",
        "required": False,
        "description": "Atlas Bank login URL for this environment.",
        "example": "http://localhost:5173/login",
    }
    if artifact_id == "transfer_funds" or artifact_id.startswith("transfer_"):
        return {
            "member_id": member,
            "from_account": {
                "type": "string",
                "required": True,
                "description": "Source product.",
                "enum": ["Checking", "Savings"],
                "example": "Savings",
            },
            "to_account": {
                "type": "string",
                "required": True,
                "description": "Destination product.",
                "enum": ["Checking", "Savings"],
                "example": "Checking",
            },
            "amount": {
                "type": "currency",
                "required": True,
                "description": "Transfer amount. Values over 5000 require human approval.",
                "example": "20.00",
            },
            "memo": {
                "type": "string",
                "required": False,
                "description": "Optional transfer memo.",
            },
            "bank_url": bank_url,
        }
    if artifact_id == "open_account" or artifact_id.startswith("open_"):
        return {
            "member_id": member,
            "account": {
                "type": "string",
                "required": True,
                "description": "Product to open.",
                "enum": ["Checking", "Savings"],
                "example": "Checking",
            },
            "account_name": {
                "type": "string",
                "required": False,
                "description": (
                    "Nickname for the new account. Defaults to the product type "
                    "(Checking or Savings) when omitted."
                ),
                "example": "Savings",
            },
            "account_use": {
                "type": "string",
                "required": False,
                "description": "Personal or Business use. Defaults to Personal.",
                "enum": ["Personal", "Business"],
                "example": "Personal",
            },
            "bank_url": bank_url,
        }
    if artifact_id == "delete_account" or artifact_id.startswith("delete_"):
        return {
            "member_id": member,
            "account": {
                "type": "string",
                "required": True,
                "description": "Product to delete.",
                "enum": ["Checking", "Savings"],
                "example": "Savings",
            },
            "bank_url": bank_url,
        }
    return {
        "member_id": member,
        "account": {
            "type": "string",
            "required": True,
            "description": "Which product balance to read.",
            "enum": ["Checking", "Savings"],
            "example": "Checking",
        },
        "bank_url": bank_url,
    }


def _outputs_for(artifact_id: str) -> dict[str, Any]:
    if artifact_id == "transfer_funds" or artifact_id.startswith("transfer_"):
        return {
            "transactions": {
                "type": "list",
                "description": "Matching debit and credit ledger rows for the transfer.",
                "shape": "[{date, description, account, amount, type, status}]",
            }
        }
    if artifact_id == "open_account" or artifact_id.startswith("open_"):
        return {
            "account_status": {
                "type": "string",
                "description": "Opened / already-exists / refused message.",
                "example": "Checking account created successfully.",
            }
        }
    if artifact_id == "delete_account" or artifact_id.startswith("delete_"):
        return {
            "account_status": {
                "type": "string",
                "description": "Delete result message.",
                "example": "Savings account deleted.",
            }
        }
    return {
        "balance": {
            "type": "currency",
            "description": "Available balance string extracted from the account card.",
            "shape": "$X,XXX.XX",
            "example": "$2,180.40",
        }
    }


def _action_from_step(step: dict[str, Any]) -> dict[str, Any]:
    """Rebuild a minimal AgentAction-shaped dict from a stored step."""
    target = step.get("target") or {}
    if isinstance(target, dict):
        label = (
            target.get("name")
            or target.get("value")
            or target.get("role")
            or ""
        )
    else:
        label = str(target)
    return {
        "action": step.get("type") or step.get("action") or "act",
        "target": label,
        "value": step.get("value"),
    }


def _normalize_recorded_steps(raw_steps: list[Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for index, step in enumerate(raw_steps or [], start=1):
        if not isinstance(step, dict) or not step:
            continue
        # Drop password fills if an older discovery recorded them.
        target = step.get("target") or {}
        blob = json.dumps(target).lower()
        if step.get("type") == "fill" and "pass" in blob:
            continue
        item = dict(step)
        item.setdefault("id", f"step_{index}")
        action_like = _action_from_step(item)
        # Prefer detailed intent labels over terse "fill → Amount" strings.
        legacy = str(item.get("description") or "")
        if (
            not legacy
            or " → " in legacy
            or legacy.endswith(" step")
            or legacy == str(item.get("type") or "")
        ):
            item["description"] = _step_label(action_like)
        item["risk"] = item.get("risk") or _step_risk(action_like)
        if isinstance(item.get("target"), dict):
            target_dict = dict(item["target"])
            strategy = str(target_dict.get("strategy") or "text")
            label = str(
                target_dict.get("value")
                or target_dict.get("name")
                or target_dict.get("role")
                or ""
            )
            target_dict.setdefault("robustness", _robustness_for(strategy, label))
            target_dict["interaction"] = "dom"
            # Strip any legacy coordinate fields if present.
            for key in ("x", "y", "coordinates", "position"):
                target_dict.pop(key, None)
            item["target"] = target_dict
        steps.append(item)
    # Re-number ids for a clean ordered contract.
    for index, step in enumerate(steps, start=1):
        step["id"] = f"step_{index}"
    return steps


def _error_policy_template(kind: str) -> dict[str, Any]:
    from app.errors.types import ERROR_POLICIES

    base = dict(ERROR_POLICIES.get(kind) or {"description": kind, "policy": "handled"})
    base["recorded_occurrences"] = 0
    base["last_message"] = None
    return base


def _error_handling_from_events(error_events: list[Any] | None) -> dict[str, Any]:
    """
    Only errors actually handled in this run are stored.
    No events → blank {} (not the full five-key catalog).
    """
    from app.errors.types import catalog_kind

    handled: dict[str, Any] = {}
    for event in error_events or []:
        if not isinstance(event, dict):
            continue
        mapped = catalog_kind(str(event.get("kind") or ""))
        if not mapped or mapped == "normal":
            continue
        entry = handled.get(mapped) or _error_policy_template(mapped)
        entry["recorded_occurrences"] = int(entry.get("recorded_occurrences") or 0) + 1
        if event.get("message"):
            entry["last_message"] = event.get("message")
        if event.get("status"):
            entry["last_status"] = event.get("status")
        handled[mapped] = entry
    return handled


def _error_kinds(error_handling: Any) -> set[str]:
    if not isinstance(error_handling, dict):
        return set()
    from app.errors.types import catalog_kind

    kinds: set[str] = set()
    for key in error_handling:
        mapped = catalog_kind(str(key))
        if mapped and mapped != "normal":
            kinds.add(mapped)
    return kinds


def _merge_error_handling(
    catalog: dict[str, Any] | None,
    error_events: list[Any] | None,
) -> dict[str, Any]:
    """Union of previously stored handled errors + newly observed events (no blank fillers)."""
    from app.errors.types import catalog_kind

    merged: dict[str, Any] = {}
    if isinstance(catalog, dict):
        for key, value in catalog.items():
            mapped = catalog_kind(key)
            if not mapped or mapped == "normal" or not isinstance(value, dict):
                continue
            if int(value.get("recorded_occurrences") or 0) <= 0 and not value.get("last_message"):
                # Skip empty placeholders from older full catalogs.
                continue
            entry = _error_policy_template(mapped)
            entry.update(
                {
                    k: v
                    for k, v in value.items()
                    if k not in {"ui_changed", "cannot_recover"}
                }
            )
            merged[mapped] = entry
    observed = _error_handling_from_events(error_events)
    for key, value in observed.items():
        if key not in merged:
            merged[key] = value
            continue
        cur = merged[key]
        cur["recorded_occurrences"] = int(cur.get("recorded_occurrences") or 0) + int(
            value.get("recorded_occurrences") or 0
        )
        if value.get("last_message"):
            cur["last_message"] = value["last_message"]
        if value.get("last_status"):
            cur["last_status"] = value["last_status"]
    return merged


def build_artifact(state: dict) -> dict[str, Any]:
    artifact_id = artifact_id_from_state(state)
    goal = state.get("goal") or ""
    signatures = [query_signature(goal)] if query_signature(goal) else []
    meta = ARTIFACT_META.get(
        artifact_id,
        {
            "title": artifact_id.replace("_", " ").title(),
            "description": f"Reusable capability for {artifact_id}.",
        },
    )
    checkpoints = _checkpoint_list(state)
    steps = _normalize_recorded_steps(list(state.get("recorded_steps") or []))
    viewport = dict(state.get("viewport") or current_viewport())
    profile = str(viewport.get("profile") or "desktop")
    error_handling = _error_handling_from_events(state.get("error_events"))
    # Stamp the member's expected scenario error so discovery for casey404 etc.
    # always forks a distinct capability even if the gate was skipped upstream.
    expected = expected_error_kind_for_member()
    if expected and expected not in error_handling:
        entry = _error_policy_template(expected)
        entry["recorded_occurrences"] = 1
        entry["last_message"] = (
            f"Handled {expected} for member {current_member_id()}"
        )
        entry["last_status"] = "recovered"
        error_handling[expected] = entry
    return {
        "artifact_id": artifact_id,
        "version": 1,
        "title": meta["title"],
        "description": meta["description"],
        "locator_policy": "dom_only",
        "viewport": {
            "profile": profile,
            "width": int(viewport.get("width") or 1280),
            "height": int(viewport.get("height") or 900),
        },
        "viewports_validated": [profile],
        # Only errors handled in this run (plus expected member scenario); blank {} otherwise.
        "error_handling": error_handling,
        "inputs": _inputs_for(artifact_id),
        "outputs": _outputs_for(artifact_id),
        "steps": steps,
        "success_conditions": _success_conditions(checkpoints),
        "query_signatures": signatures,
    }


def _latest_for(artifact_id: str) -> dict[str, Any] | None:
    """Load the metadata-pinned version; callers may roll back via version_candidates()."""
    for version in version_candidates(artifact_id):
        data = _load_version(artifact_id, version)
        if data is not None:
            return data
    return None


def iter_artifact_rollbacks(artifact_id: str):
    """Yield versions after the preferred one (for replay failure → older operator)."""
    candidates = version_candidates(artifact_id)
    for version in candidates[1:]:
        data = _load_version(artifact_id, version)
        if data is not None:
            yield data


def _find_same_steps(artifact_id: str, steps: Any) -> dict[str, Any] | None:
    matches = [
        (version, data)
        for version, _path, data in _iter_artifacts()
        if (data.get("artifact_id") or Path(data["_path"]).parent.name) == artifact_id
        and data.get("steps") == steps
    ]
    if not matches:
        return None
    _version, data = max(matches, key=lambda item: item[0])
    return data


def _find_same_capability(
    artifact_id: str,
    steps: Any,
    error_handling: Any,
) -> dict[str, Any] | None:
    """Same DOM steps and the same set of handled error kinds."""
    wanted = _error_kinds(error_handling)
    matches = [
        (version, data)
        for version, _path, data in _iter_artifacts()
        if (data.get("artifact_id") or Path(data["_path"]).parent.name) == artifact_id
        and data.get("steps") == steps
        and _error_kinds(data.get("error_handling")) == wanted
    ]
    if not matches:
        return None
    _version, data = max(matches, key=lambda item: item[0])
    return data


def _merge_signatures(*collections: Any) -> list[str]:
    signatures: list[str] = []
    for collection in collections:
        for item in collection or []:
            signature = query_signature(str(item))
            if signature and signature not in signatures:
                signatures.append(signature)
    return signatures


def mark_viewport_validated(artifact: dict[str, Any], viewport: dict[str, Any] | None = None) -> Path | None:
    """Record that this DOM artifact replayed successfully on another screen size."""
    path_str = artifact.get("_path")
    if not path_str:
        return None
    path = Path(path_str)
    if not path.is_file():
        return None
    data = _load_json(path)
    if data is None:
        return None
    viewport = viewport or current_viewport()
    profile = str(viewport.get("profile") or "")
    validated = [str(item) for item in (data.get("viewports_validated") or [])]
    if profile and profile not in validated:
        validated.append(profile)
    data["viewports_validated"] = validated
    data.setdefault("locator_policy", "dom_only")
    data.pop("recorded_for", None)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def _artifact_error_events(error_handling: Any) -> list[dict[str, Any]] | None:
    events: list[dict[str, Any]] = []
    if not isinstance(error_handling, dict):
        return None
    for key, value in error_handling.items():
        if not isinstance(value, dict):
            continue
        if int(value.get("recorded_occurrences") or 0) <= 0 and not value.get("last_message"):
            continue
        events.append(
            {
                "kind": key,
                "message": value.get("last_message"),
                "status": value.get("last_status"),
            }
        )
    return events or None


def save_artifact(artifact: dict[str, Any]) -> Path:
    """Write operators/{artifact_id}/vN.json (versioned; no personal names stored).

    Same DOM steps + same handled-error set reuse a version. A different
    error set (including blank vs non-blank) is a new capability → new vN.
    error_handling stays blank {} until at least one handled error is observed.
    """
    artifact_id = str(artifact["artifact_id"])
    incoming_errors = artifact.get("error_handling") or {}
    if not isinstance(incoming_errors, dict):
        incoming_errors = {}
    artifact = dict(artifact)
    artifact["error_handling"] = _merge_error_handling(incoming_errors, None)

    same_capability = _find_same_capability(
        artifact_id, artifact.get("steps"), artifact.get("error_handling")
    )
    same_steps = _find_same_steps(artifact_id, artifact.get("steps"))

    if same_capability is not None:
        existing = same_capability
        existing["query_signatures"] = _merge_signatures(
            existing.get("query_signatures"),
            artifact.get("query_signatures"),
        )
        validated = [str(item) for item in (existing.get("viewports_validated") or [])]
        for item in artifact.get("viewports_validated") or []:
            if str(item) not in validated:
                validated.append(str(item))
        profile = (artifact.get("viewport") or {}).get("profile")
        if profile and str(profile) not in validated:
            validated.append(str(profile))
        existing["viewports_validated"] = validated
        existing.setdefault("locator_policy", artifact.get("locator_policy") or "dom_only")
        if artifact.get("viewport") and not existing.get("viewport"):
            existing["viewport"] = artifact["viewport"]
        existing["error_handling"] = _merge_error_handling(
            existing.get("error_handling"),
            _artifact_error_events(artifact.get("error_handling")),
        )
        existing.pop("recorded_for", None)
        existing.pop("source_query", None)
        existing.pop("password", None)
        path = Path(existing["_path"])
        payload = {key: value for key, value in existing.items() if not str(key).startswith("_")}
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        write_metadata(artifact_id, int(existing.get("version") or 1))
        return path

    if same_steps is not None:
        # Same steps, different error capability → fork a version.
        new_kinds = _error_kinds(artifact.get("error_handling"))
        old_kinds = _error_kinds(same_steps.get("error_handling"))
        if new_kinds - old_kinds:
            artifact["error_handling"] = _merge_error_handling(
                same_steps.get("error_handling"),
                _artifact_error_events(artifact.get("error_handling")),
            )
        artifact["query_signatures"] = _merge_signatures(
            same_steps.get("query_signatures"),
            artifact.get("query_signatures"),
        )
        validated = [str(item) for item in (same_steps.get("viewports_validated") or [])]
        for item in artifact.get("viewports_validated") or []:
            if str(item) not in validated:
                validated.append(str(item))
        profile = (artifact.get("viewport") or {}).get("profile")
        if profile and str(profile) not in validated:
            validated.append(str(profile))
        artifact["viewports_validated"] = validated
        if not artifact.get("viewport") and same_steps.get("viewport"):
            artifact["viewport"] = same_steps["viewport"]

    folder = artifact_dir(artifact_id)
    folder.mkdir(parents=True, exist_ok=True)
    version = _latest_version_number(artifact_id) + 1
    artifact["version"] = version
    artifact.setdefault("locator_policy", "dom_only")
    artifact.setdefault("error_handling", {})
    artifact.pop("recorded_for", None)
    artifact.pop("source_query", None)
    path = artifact_path_for(artifact_id, version)
    payload = {key: value for key, value in artifact.items() if not str(key).startswith("_")}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_metadata(artifact_id, version)
    return path


def persist_artifact(state: dict) -> Path | None:
    # Rebuild steps from raw actions when callers pass AgentAction-shaped rows.
    recorded = list(state.get("recorded_steps") or [])
    if recorded and recorded[0].get("action") and not recorded[0].get("type"):
        steps = []
        for index, action in enumerate(recorded, start=1):
            step = action_to_step(action, index)
            if step:
                steps.append(step)
        state = {**state, "recorded_steps": steps}
    if "viewport" not in state:
        state = {**state, "viewport": current_viewport()}
    artifact = build_artifact(state)
    if not artifact.get("steps"):
        return None
    return save_artifact(artifact)
