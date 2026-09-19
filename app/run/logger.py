from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "runs"

SECRET_TARGETS = ("password", "pass", "member", "user")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_run_id(kind: str) -> tuple[str, Path]:
    folder = RUNS_DIR / kind
    folder.mkdir(parents=True, exist_ok=True)
    numbers = []
    for path in folder.iterdir():
        if path.is_dir() and path.name.startswith("run_"):
            suffix = path.name.split("_", 1)[-1]
            if suffix.isdigit():
                numbers.append(int(suffix))
    run_id = f"run_{max(numbers, default=0) + 1:03d}"
    run_dir = folder / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_id, run_dir


def allocate_run_dir(kind: str) -> tuple[str, Path]:
    return _next_run_id(kind)


def _redact(action_name: str | None, target: str | None, value: Any) -> Any:
    if action_name != "fill" or value in (None, ""):
        return value
    text = (target or "").lower()
    if any(token in text for token in SECRET_TARGETS):
        return "[REDACTED]"
    return value


def checkpoint_for_action(action: dict) -> str:
    name = (action.get("action") or "").lower()
    target = (action.get("target") or "").lower()
    if name == "fill" and ("user" in target or "member" in target):
        return "member_id_filled"
    if name == "fill" and "pass" in target:
        return "password_filled"
    if name == "click" and ("sign in" in target or "search" in target):
        return "member_details_visible"
    if name == "click" and "transfer money" in target:
        return "transfer_form_visible"
    if name == "click" and "review transfer" in target:
        return "transfer_review_visible"
    if name == "click" and "confirm transfer" in target:
        return "transfer_success_visible"
    if name == "click" and "transaction" in target:
        return "transactions_visible"
    if name == "fill" and "from account" in target:
        return "from_account_filled"
    if name == "fill" and "to account" in target:
        return "to_account_filled"
    if name == "fill" and "amount" in target:
        return "amount_filled"
    if name == "read" and "transfer" in target:
        return "transfer_id_visible"
    if name == "read":
        return "balance_visible"
    if name == "navigate":
        return "page_loaded"
    return "step_completed"


class RunLogger:
    def __init__(
        self,
        kind: str,
        goal: str,
        artifact_used: str | None = None,
        operators_used: list[str] | None = None,
    ) -> None:
        if kind not in {"discovery", "replay"}:
            raise ValueError("kind must be discovery or replay")
        self.kind = kind
        self.run_id, self.run_dir = _next_run_id(kind)
        self.events_path = self.run_dir / "events.jsonl"
        self.meta_path = self.run_dir / "run.json"
        self._step = 0
        used = list(operators_used or [])
        if artifact_used and artifact_used not in used:
            used.append(artifact_used)
        self.meta: dict[str, Any] = {
            "run_id": self.run_id,
            "type": kind,
            "goal": goal,
            "target_url": os.getenv("BANK_URL", "http://127.0.0.1:5173/login"),
            "started_at": utc_now(),
            "ended_at": None,
            "status": "running",
            "llm_model": os.getenv("GROQ_MODEL") if kind == "discovery" else None,
            "operators_created": [],
            "operators_used": used,
            # legacy single-operator fields
            "artifact_created": None,
            "artifact_used": used[0] if len(used) == 1 else None,
        }
        self._write_meta()
        self.events_path.touch()
        print(f"[run] {kind} {self.run_id} → {self.run_dir}")

    def _write_meta(self) -> None:
        self.meta_path.write_text(json.dumps(self.meta, indent=2) + "\n", encoding="utf-8")

    def event(self, **fields: Any) -> None:
        self._step += 1
        payload = {"step": self._step, **{key: value for key, value in fields.items() if value is not None}}
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")

    def log_observe(self, url: str, title: str | None = None) -> None:
        self.event(type="observe", url=url, **({"title": title} if title else {}))

    def log_llm_decision(self, action: dict) -> None:
        self.event(
            type="llm_decision",
            action=action.get("action"),
            target=action.get("target"),
        )

    def log_act(self, action: dict) -> None:
        name = action.get("action")
        target = action.get("target")
        payload: dict[str, Any] = {"type": name, "target": target}
        if name == "fill":
            payload["value"] = _redact(name, target, action.get("value"))
        if name == "navigate" and target:
            payload["url"] = target
        self.event(**payload)

    def log_verify(self, action: dict, passed: bool) -> None:
        self.event(
            type="verify",
            checkpoint=checkpoint_for_action(action),
            status="passed" if passed else "failed",
        )

    def note_operator(self, operator_ref: str, *, created: bool = False) -> None:
        key = "operators_created" if created else "operators_used"
        refs = list(self.meta.get(key) or [])
        if operator_ref not in refs:
            refs.append(operator_ref)
            self.meta[key] = refs
        if created:
            self.meta["artifact_created"] = operator_ref
        else:
            used = list(self.meta.get("operators_used") or [])
            self.meta["artifact_used"] = used[0] if len(used) == 1 else self.meta.get("artifact_used")
        self._write_meta()

    def set_artifact_created(self, artifact_ref: str) -> None:
        self.note_operator(artifact_ref, created=True)

    def write_statement(self, markdown: str) -> Path:
        path = self.run_dir / "statement.md"
        path.write_text(markdown, encoding="utf-8")
        self.meta["statement"] = "statement.md"
        self._write_meta()
        print(f"[run] statement {path}")
        return path

    def write_transfer(self, markdown: str) -> Path:
        path = self.run_dir / "transfer.md"
        path.write_text(markdown, encoding="utf-8")
        self.meta["transfer"] = "transfer.md"
        self._write_meta()
        print(f"[run] transfer {path}")
        return path

    def finish(self, status: str, artifact_created: str | None = None, error: str | None = None) -> None:
        if artifact_created:
            self.note_operator(artifact_created, created=True)
        self.meta["ended_at"] = utc_now()
        self.meta["status"] = status
        if error:
            self.meta["error"] = error
        self._write_meta()
        print(f"[run] {self.kind} {self.run_id} {status}")
