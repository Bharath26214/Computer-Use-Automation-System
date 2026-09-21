from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.run.outcome import resolve_outcome

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "evidence"

SECRET_TARGETS = ("password", "pass", "member", "user")

_SCREENSHOT_SAFE = re.compile(r"[^a-zA-Z0-9_-]+")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_numbers_for(kind: str) -> list[int]:
    """Collect run_NNN indices for one kind (discovery or replay) independently."""
    numbers: list[int] = []
    folder = RUNS_DIR / kind
    if not folder.is_dir():
        return numbers
    for path in folder.iterdir():
        if path.is_dir() and path.name.startswith("run_"):
            suffix = path.name.split("_", 1)[-1]
            if suffix.isdigit():
                numbers.append(int(suffix))
    return numbers


def _next_run_id(kind: str) -> tuple[str, Path]:
    """
    Allocate the next run folder for this kind only.

    discovery/run_001, discovery/run_002, …
    replay/run_001, replay/run_002, …
    Each mode starts at run_001 and increments on its own.
    """
    folder = RUNS_DIR / kind
    folder.mkdir(parents=True, exist_ok=True)
    run_id = f"run_{max(_run_numbers_for(kind), default=0) + 1:03d}"
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
        self.summary_path = self.run_dir / "summary.json"
        self._step = 0
        self._llm_used = False
        self._model_turns = 0
        self._retries = 0
        self._final_response: str | None = None
        self._transfer_body: str | None = None
        self._outcome_code: str | None = None
        self._outcome_source: str | None = None
        self._outcome_evidence: dict[str, Any] = {}
        self._dom_signals: dict[str, Any] = {}
        used = list(operators_used or [])
        if artifact_used and artifact_used not in used:
            used.append(artifact_used)
        sequence = [
            {
                "order": index + 1,
                "artifact": ref,
                "mode": kind,
                "created": False,
            }
            for index, ref in enumerate(used)
        ]
        self.meta: dict[str, Any] = {
            "run_id": self.run_id,
            "type": kind,
            "goal": goal,
            "target_url": os.getenv("BANK_URL", "http://localhost:5173/login"),
            "started_at": utc_now(),
            "ended_at": None,
            "status": "running",
            "outcome": None,
            "outcome_code": None,
            "outcome_source": None,
            "outcome_evidence": None,
            "llm_used": False,
            "llm_model": None,
            "model_turns": 0,
            "retries": 0,
            "artifact_sequence": sequence,
            "operators_created": [],
            "operators_used": used,
            # legacy single-operator fields
            "artifact_created": None,
            "artifact_used": used[0] if len(used) == 1 else None,
            "guardrail_audit": [],
            "error_events": [],
            "checkpoints": None,
        }
        self._write_meta()
        self.events_path.touch()
        print(f"[run] {kind} {self.run_id} → {self.run_dir}")

    def _write_meta(self) -> None:
        self.meta_path.write_text(json.dumps(self.meta, indent=2) + "\n", encoding="utf-8")

    def event(self, **fields: Any) -> None:
        self._step += 1
        payload = {"step": self._step, **{key: value for key, value in fields.items() if value is not None}}
        if payload.get("type") == "llm_decision":
            self._llm_used = True
            self.meta["llm_used"] = True
            if not self.meta.get("llm_model"):
                self.meta["llm_model"] = os.getenv("GROQ_MODEL")
            self._write_meta()
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")

    def log_observe(self, url: str, title: str | None = None) -> None:
        self.event(type="observe", url=url, **({"title": title} if title else {}))

    def log_llm_decision(self, action: dict) -> None:
        self._model_turns += 1
        self.meta["model_turns"] = self._model_turns
        self.event(
            type="llm_decision",
            action=action.get("action"),
            target=action.get("target"),
            turn=self._model_turns,
        )

    def log_llm_retry(self, reason: str | None = None) -> None:
        """Record a model retry (e.g. structured-output failure → JSON fallback)."""
        self._retries += 1
        self.meta["retries"] = self._retries
        self._llm_used = True
        self.meta["llm_used"] = True
        if not self.meta.get("llm_model"):
            self.meta["llm_model"] = os.getenv("GROQ_MODEL")
        self._write_meta()
        self.event(type="llm_retry", reason=reason or "model_fallback", retry=self._retries)

    def log_act(self, action: dict) -> None:
        name = action.get("action")
        target = action.get("target")
        payload: dict[str, Any] = {"type": name, "target": target}
        if name == "fill":
            payload["value"] = _redact(name, target, action.get("value"))
        if name == "navigate" and target:
            payload["url"] = target
        from app.guardrails.risk import classify_action_risk

        payload["risk"] = classify_action_risk(action).value
        self.event(**payload)

    def note_outcome(
        self,
        code: str,
        *,
        source: str,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        """Record a structured outcome from guardrail / DOM / HITL evidence."""
        self._outcome_code = code
        self._outcome_source = source
        self._outcome_evidence = dict(evidence or {})
        self.meta["outcome_code"] = code
        self.meta["outcome_source"] = source
        self.meta["outcome_evidence"] = self._outcome_evidence
        self.event(
            type="outcome",
            outcome_code=code,
            outcome_source=source,
            evidence=self._outcome_evidence or None,
        )
        self._write_meta()

    def note_dom_signals(self, signals: dict[str, Any] | None) -> None:
        if not signals:
            return
        self._dom_signals = dict(signals)
        self.meta["dom_signals"] = self._dom_signals
        self._write_meta()

    async def capture_dom_outcome(
        self,
        page,
        *,
        task_kind: str | None = None,
        account: str | None = None,
    ) -> dict[str, Any]:
        """Probe the bank UI and store signals for resolve_outcome."""
        from app.run.evidence import observe_dom_signals

        signals = await observe_dom_signals(
            page, task_kind=task_kind, account=account
        )
        self.note_dom_signals(signals)
        return signals

    def log_guardrail(self, decision) -> None:
        """Persist guardrail evaluation into events.jsonl + run.json (no separate jsonl)."""
        audit = decision.to_audit() if hasattr(decision, "to_audit") else dict(decision)
        self.event(
            type="guardrail",
            action=audit.get("action"),
            target=audit.get("target"),
            status=audit.get("status"),
            risk=audit.get("risk"),
            guardrail_decision=audit.get("decision") or audit.get("guardrail_decision"),
            rule=audit.get("rule"),
            message=audit.get("message"),
            expected_page=audit.get("expected_page"),
            actual_page=audit.get("actual_page"),
        )
        trail = list(self.meta.get("guardrail_audit") or [])
        trail.append(
            {
                "step": len(trail) + 1,
                "action": audit.get("action"),
                "target": audit.get("target"),
                "status": audit.get("status"),
                "risk": audit.get("risk"),
                "guardrail_decision": audit.get("decision") or audit.get("guardrail_decision"),
                "rule": audit.get("rule"),
                "message": audit.get("message"),
            }
        )
        self.meta["guardrail_audit"] = trail

        # Blocking / denied rules are outcome facts — not answer text.
        from app.run.outcome import code_from_rule

        decision_value = str(
            audit.get("decision") or audit.get("guardrail_decision") or ""
        ).lower()
        status_value = str(audit.get("status") or "").lower()
        rule = audit.get("rule")
        if (
            decision_value in {"block", "blocked"}
            or status_value in {"blocked", "block"}
            or str(rule or "") in {
                "hitl_denied",
                "hitl_timeout",
                "insufficient_funds",
                "transfer_account_not_found",
                "create_account_exists",
                "delete_account_not_exist",
            }
        ):
            details = dict(audit.get("details") or {})
            details.setdefault("message", audit.get("message"))
            code = code_from_rule(str(rule) if rule else None, details=details)
            if code:
                self.note_outcome(
                    code,
                    source="guardrail",
                    evidence={"rule": rule, **details},
                )
        self._write_meta()

    def log_error_event(self, event) -> None:
        """Append a recovery / runtime error event to events.jsonl + run.json."""
        payload = event.to_dict() if hasattr(event, "to_dict") else dict(event)
        self.event(type="error", **{key: value for key, value in payload.items() if value is not None})
        trail = list(self.meta.get("error_events") or [])
        trail.append(payload)
        self.meta["error_events"] = trail

        status = str(payload.get("status") or "").lower()
        details = payload.get("details") or {}
        reason = str(details.get("reason") or "").lower()
        if status in {"rejected", "terminal"} or reason == "hitl_timeout":
            from app.run.outcome import code_from_rule

            rule = "hitl_timeout" if reason == "hitl_timeout" else "hitl_denied"
            code = code_from_rule(rule) or "human_did_not_confirm"
            self.note_outcome(
                code,
                source="hitl",
                evidence={"status": status, "reason": reason or status},
            )
        self._write_meta()
    def save_checkpoint_snapshot(
        self,
        *,
        checkpoints: dict[str, Any] | None,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Freeze mid-run checkpoints into run.json when an error interrupts the flow.

        Later resume-from-checkpoint is out of scope; this is durable evidence only.
        """
        snapshot = {
            "saved_at": utc_now(),
            "run_id": self.run_id,
            "checkpoints": dict(checkpoints or {}),
            "error": error,
        }
        self.meta["checkpoints"] = snapshot
        self._write_meta()
        print(f"[run] checkpoints saved → {self.meta_path}")
        return snapshot

    def log_verify(self, action: dict, passed: bool) -> None:
        self.event(
            type="verify",
            checkpoint=checkpoint_for_action(action),
            status="passed" if passed else "failed",
        )

    def note_operator(self, operator_ref: str, *, created: bool = False, mode: str | None = None) -> None:
        key = "operators_created" if created else "operators_used"
        refs = list(self.meta.get(key) or [])
        is_new = operator_ref not in refs
        if is_new:
            refs.append(operator_ref)
            self.meta[key] = refs
        # Ordered sequence: append once per first use, or again when mode changes (replay→discovery).
        sequence = list(self.meta.get("artifact_sequence") or [])
        last = sequence[-1] if sequence else None
        same_as_last = (
            last is not None
            and last.get("artifact") == operator_ref
            and last.get("mode") == (mode or ("discovery" if created else self.kind))
            and bool(last.get("created")) == bool(created)
        )
        if not same_as_last:
            sequence.append(
                {
                    "order": len(sequence) + 1,
                    "artifact": operator_ref,
                    "mode": mode or ("discovery" if created else self.kind),
                    "created": bool(created),
                }
            )
            self.meta["artifact_sequence"] = sequence
        if created:
            self.meta["artifact_created"] = operator_ref
        else:
            used = list(self.meta.get("operators_used") or [])
            self.meta["artifact_used"] = used[0] if len(used) == 1 else self.meta.get("artifact_used")
        self._write_meta()

    def set_artifact_created(self, artifact_ref: str) -> None:
        self.note_operator(artifact_ref, created=True, mode="discovery")

    def write_statement(self, markdown: str) -> Path:
        path = self.run_dir / "statement.md"
        path.write_text(markdown, encoding="utf-8")
        self.meta["statement"] = "statement.md"
        self._write_meta()
        print(f"[run] statement {path}")
        return path

    def screenshots_dir(self) -> Path:
        path = self.run_dir / "screenshots"
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def capture_screenshot(self, page: Any, name: str) -> Path | None:
        """
        Capture a full-page Playwright screenshot into this run folder.

        Files land under evidence/{discovery|replay}/run_NNN/screenshots/{name}.png
        and are listed on run.json as meta["screenshots"].
        """
        if page is None:
            return None
        safe = _SCREENSHOT_SAFE.sub("_", (name or "shot").strip()).strip("_") or "shot"
        path = self.screenshots_dir() / f"{safe}.png"
        try:
            await page.screenshot(path=str(path), full_page=True)
        except Exception as exc:
            print(f"[run] screenshot failed ({safe}): {exc}")
            return None
        rel = f"screenshots/{path.name}"
        shots = list(self.meta.get("screenshots") or [])
        if rel not in shots:
            shots.append(rel)
        self.meta["screenshots"] = shots
        self._write_meta()
        print(f"[run] screenshot {path}")
        return path

    @staticmethod
    def _transfer_table_body(markdown: str) -> str:
        """Keep the ledger table; drop any prior Status/Outcome header."""
        lines = (markdown or "").splitlines()
        start = 0
        while start < len(lines) and not lines[start].startswith("|"):
            start += 1
        body = "\n".join(lines[start:]).strip()
        return f"{body}\n" if body else ""

    @staticmethod
    def _status_label(status: str | None) -> str:
        value = (status or "").strip().lower()
        if value in {"pass", "success"}:
            return "success"
        if value in {"failed", "fail", "failure", "blocked", "cancelled"}:
            return "failure"
        return "success" if not value else value

    def _compose_transfer_markdown(
        self,
        body: str,
        *,
        status: str | None = "success",
        outcome: str | None = None,
    ) -> str:
        lines = [f"**Status:** {self._status_label(status)}"]
        if outcome:
            lines.append(f"**Outcome:** {outcome}")
        lines.append("")
        table = self._transfer_table_body(body).rstrip()
        if table:
            lines.append(table)
        lines.append("")
        return "\n".join(lines)

    def write_transfer(
        self,
        markdown: str,
        *,
        status: str | None = "success",
        outcome: str | None = None,
    ) -> Path:
        body = self._transfer_table_body(markdown)
        self._transfer_body = body
        path = self.run_dir / "transfer.md"
        path.write_text(
            self._compose_transfer_markdown(body, status=status, outcome=outcome),
            encoding="utf-8",
        )
        self.meta["transfer"] = "transfer.md"
        self._write_meta()
        print(f"[run] transfer {path}")
        return path

    def _refresh_transfer_status(
        self,
        status: str,
        outcome: str | None = None,
    ) -> None:
        """Stamp final run success/failure onto transfer.md when present."""
        path = self.run_dir / "transfer.md"
        body = getattr(self, "_transfer_body", None)
        if not body and path.is_file():
            body = self._transfer_table_body(path.read_text(encoding="utf-8"))
        if not body:
            return
        self._transfer_body = body
        path.write_text(
            self._compose_transfer_markdown(body, status=status, outcome=outcome),
            encoding="utf-8",
        )
        self.meta["transfer"] = "transfer.md"

    def finish(
        self,
        status: str | None = None,
        artifact_created: str | None = None,
        error: str | None = None,
        *,
        outcome: str | None = None,
        outcome_code: str | None = None,
        answer: str | None = None,
        task_kind: str | None = None,
    ) -> None:
        if artifact_created:
            self.note_operator(artifact_created, created=True, mode="discovery")

        resolved = resolve_outcome(
            task_kind=task_kind,
            answer=answer,
            error=error,
            outcome_code=outcome_code or self._outcome_code,
            guardrail_audit=list(self.meta.get("guardrail_audit") or []),
            error_events=list(self.meta.get("error_events") or []),
            dom_signals=dict(self._dom_signals or self.meta.get("dom_signals") or {}),
        )

        from app.run.outcome import label_for, status_for

        # Evidence-backed resolution is primary. Caller status/outcome are overrides
        # only when they do not fight structured codes.
        final_code = outcome_code or self._outcome_code or resolved.code
        final_source = (
            "explicit"
            if outcome_code
            else (self._outcome_source or resolved.source)
        )
        final_evidence = dict(resolved.evidence or self._outcome_evidence or {})
        final_outcome = label_for(final_code) if final_code else (outcome or resolved.label)
        final_status = status_for(final_code) if final_code else resolved.status

        if status in {"cancelled"}:
            final_status = "failed"
            final_code = final_code or "human_did_not_confirm"
            final_outcome = outcome or label_for("human_did_not_confirm")
            final_source = final_source or "explicit"
        elif status == "failed" and resolved.source == "answer_heuristic" and not self._outcome_code:
            # Caller forced failure without structured evidence.
            final_status = "failed"
            if outcome:
                final_outcome = outcome
        elif status in {"success", "pass"} and resolved.source == "answer_heuristic" and not (
            outcome_code or self._outcome_code
        ):
            # Keep pass when caller says success and we only have heuristic.
            final_status = "pass" if not error else final_status
            if outcome:
                final_outcome = outcome

        if final_status == "success":
            final_status = "pass"

        self.meta["ended_at"] = utc_now()
        self.meta["status"] = final_status
        self.meta["outcome"] = final_outcome
        self.meta["outcome_code"] = final_code
        self.meta["outcome_source"] = final_source
        self.meta["outcome_evidence"] = final_evidence
        self.meta["llm_used"] = bool(self.meta.get("llm_used") or self._llm_used)
        self.meta["model_turns"] = self._model_turns
        self.meta["retries"] = self._retries
        if answer is not None:
            self._final_response = str(answer)
            self.meta["final_response"] = self._final_response
        elif error is not None and self._final_response is None:
            self._final_response = str(error)
            self.meta["final_response"] = self._final_response
        if error:
            self.meta["error"] = error
        self._refresh_transfer_status(final_status, final_outcome)
        self._write_meta()
        self._write_summary()
        print(
            f"[run] {self.kind} {self.run_id} {final_status} "
            f"({final_outcome}; code={final_code}; source={final_source})"
        )
    def _write_summary(self) -> None:
        """Compact per-run summary for operators and evaluation."""
        summary = {
            "run_id": self.run_id,
            "model": self.meta.get("llm_model") if self.meta.get("llm_used") else None,
            "model_turns": self._model_turns,
            "retries": self._retries,
            "started_at": self.meta.get("started_at"),
            "ended_at": self.meta.get("ended_at"),
            "status": self.meta.get("status"),
            "outcome": self.meta.get("outcome"),
            "outcome_code": self.meta.get("outcome_code"),
            "outcome_source": self.meta.get("outcome_source"),
            "final_response": self._final_response
            or self.meta.get("final_response")
            or self.meta.get("error"),
        }
        self.summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"[run] summary {self.summary_path}")
