"""
Run outcome resolution.

Outcome comes from evidence, not from grepping the bot's own answer prose:

1. Explicit outcome_code (caller already knows)
2. Blocking guardrail rule / HITL error event (facts recorded at decision time)
3. DOM signals (page testids / alerts)
4. Legacy answer-text heuristics — last resort, marked source=answer_heuristic

`outcome` in run.json stays a human label; `outcome_code` is the stable id.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


# Stable codes → labels used in run.json / test expect_outcome.
OUTCOME_LABELS: dict[str, str] = {
    "balance_retrieved": "Balance retrieved",
    "transfer_completed": "Transfer completed",
    "account_opened": "Account opened",
    "account_deleted": "Account deleted",
    "account_already_exists": "Account already exists",
    "account_not_found": "Account not found",
    "checking_account_not_found": "Checking account not found",
    "savings_account_not_found": "Savings account not found",
    "insufficient_funds": "Insufficient funds",
    "human_did_not_confirm": "Human did not confirm",
    "human_rejected": "Human intervention: rejected",
    "username_not_found": "Username not found",
    "page_not_found": "Page not found",
    "reloading": "Reloading failed",
    "hard_failure": "Hard failure",
    "completed": "Completed",
}

# pass vs failed for each code
OUTCOME_STATUS: dict[str, str] = {
    "balance_retrieved": "pass",
    "transfer_completed": "pass",
    "account_opened": "pass",
    "account_deleted": "pass",
    "account_already_exists": "pass",
    "account_not_found": "pass",
    "checking_account_not_found": "pass",
    "savings_account_not_found": "pass",
    "insufficient_funds": "pass",
    "human_did_not_confirm": "failed",
    "human_rejected": "failed",
    "username_not_found": "failed",
    "page_not_found": "failed",
    "reloading": "failed",
    "hard_failure": "failed",
    "completed": "pass",
}

# Guardrail / recovery rule → outcome code
RULE_TO_CODE: dict[str, str] = {
    "insufficient_funds": "insufficient_funds",
    "transfer_account_not_found": "account_not_found",
    "create_account_exists": "account_already_exists",
    "delete_account_not_exist": "account_not_found",
    "hitl_denied": "human_did_not_confirm",
    "hitl_timeout": "human_did_not_confirm",
    "hitl_required": "human_did_not_confirm",
    "ui_page_mismatch": "hard_failure",
    "action_not_allowed": "hard_failure",
    "username_not_found": "username_not_found",
}

# Labels still accepted as expect_outcome in tests (backward compatible).
LABEL_TO_CODE: dict[str, str] = {label.lower(): code for code, label in OUTCOME_LABELS.items()}

# Legacy name used by older callers
FAILURE_OUTCOMES = {
    "username_not_found": OUTCOME_LABELS["username_not_found"],
    "human_did_not_confirm": OUTCOME_LABELS["human_did_not_confirm"],
    "human_rejected": OUTCOME_LABELS["human_rejected"],
    "page_not_found": OUTCOME_LABELS["page_not_found"],
    "reloading": OUTCOME_LABELS["reloading"],
    "hard_failure": OUTCOME_LABELS["hard_failure"],
    "cannot_recover": OUTCOME_LABELS["hard_failure"],
    "ui_changed": OUTCOME_LABELS["hard_failure"],
}

TERMINAL_PASS_CODES = frozenset(
    {
        "insufficient_funds",
        "account_not_found",
        "checking_account_not_found",
        "savings_account_not_found",
    }
)


@dataclass
class OutcomeResult:
    status: str
    code: str
    label: str
    source: str = "unknown"
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_tuple(self) -> tuple[str, str]:
        """Back-compat (status, label) for older call sites."""
        return self.status, self.label

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def label_for(code: str) -> str:
    return OUTCOME_LABELS.get(code, code.replace("_", " ").title())


def status_for(code: str) -> str:
    return OUTCOME_STATUS.get(code, "failed")


def code_from_label(label: str | None) -> str | None:
    if not label:
        return None
    return LABEL_TO_CODE.get(str(label).strip().lower())


def code_from_rule(rule: str | None, *, details: dict[str, Any] | None = None) -> str | None:
    if not rule:
        return None
    key = str(rule).strip().lower()
    if key == "transfer_account_not_found" and details:
        account = str(
            details.get("missing_account")
            or details.get("account")
            or details.get("from_account")
            or ""
        ).lower()
        # Prefer destination/source specificity from message context if present.
        msg = str(details.get("message") or "").lower()
        if "checking" in msg and "not found" in msg:
            return "checking_account_not_found"
        if "savings" in msg and "not found" in msg:
            return "savings_account_not_found"
        if account.startswith("check"):
            return "checking_account_not_found"
        if account.startswith("sav"):
            return "savings_account_not_found"
    return RULE_TO_CODE.get(key)


def outcome_from_code(
    code: str,
    *,
    source: str,
    evidence: dict[str, Any] | None = None,
) -> OutcomeResult:
    return OutcomeResult(
        status=status_for(code),
        code=code,
        label=label_for(code),
        source=source,
        evidence=dict(evidence or {}),
    )


def _from_guardrail_audit(trail: list[dict[str, Any]] | None) -> OutcomeResult | None:
    if not trail:
        return None
    blocking_rules = {
        "hitl_denied",
        "hitl_timeout",
        "insufficient_funds",
        "transfer_account_not_found",
        "create_account_exists",
        "delete_account_not_exist",
        "ui_page_mismatch",
        "action_not_allowed",
        "username_not_found",
    }
    for item in reversed(trail):
        decision = str(item.get("guardrail_decision") or item.get("decision") or "").lower()
        status = str(item.get("status") or "").lower()
        rule = str(item.get("rule") or "")
        is_block = decision in {"block", "blocked"} or status in {"blocked", "block"}
        if not is_block and rule not in blocking_rules:
            continue
        details = {
            "message": item.get("message"),
            "action": item.get("action"),
            "target": item.get("target"),
        }
        code = code_from_rule(rule or None, details=details)
        if code:
            return outcome_from_code(
                code,
                source="guardrail",
                evidence={"rule": rule, **details},
            )
    return None


def _from_error_events(events: list[dict[str, Any]] | None) -> OutcomeResult | None:
    if not events:
        return None
    for item in reversed(events):
        kind = str(item.get("kind") or "").lower()
        status = str(item.get("status") or "").lower()
        details = item.get("details") or {}
        reason = str(details.get("reason") or "").lower()
        message = str(item.get("message") or "").lower()
        if status in {"rejected", "terminal"} or kind == "human_intervention":
            if reason == "hitl_timeout" or "timed out" in message:
                return outcome_from_code(
                    "human_did_not_confirm",
                    source="hitl",
                    evidence={"kind": kind, "status": status, "reason": reason},
                )
            if status == "rejected" or "declined" in message or "abort" in message:
                return outcome_from_code(
                    "human_did_not_confirm",
                    source="hitl",
                    evidence={"kind": kind, "status": status},
                )
        if "page_not_found" in kind or "page not found" in message:
            return outcome_from_code(
                "page_not_found",
                source="error_event",
                evidence={"kind": kind},
            )
        if "reload" in kind and ("cannot" in message or status == "terminal"):
            return outcome_from_code(
                "reloading",
                source="error_event",
                evidence={"kind": kind},
            )
        if "hard_failure" in kind or "cannot be recovered" in message:
            return outcome_from_code(
                "hard_failure",
                source="error_event",
                evidence={"kind": kind},
            )
    return None


def _from_dom_signals(
    signals: dict[str, Any] | None,
    *,
    task_kind: str | None,
) -> OutcomeResult | None:
    if not signals:
        return None
    kind = (task_kind or "").strip().lower()
    true = {key for key, value in signals.items() if value}

    if "hard_failure" in true:
        return outcome_from_code("hard_failure", source="dom", evidence=signals)
    if "page_not_found" in true:
        return outcome_from_code("page_not_found", source="dom", evidence=signals)
    if "reloading" in true and "reloading_recovered" not in true:
        return outcome_from_code("reloading", source="dom", evidence=signals)

    if "insufficient_funds_alert" in true:
        return outcome_from_code("insufficient_funds", source="dom", evidence=signals)
    if "transfer_success" in true:
        return outcome_from_code("transfer_completed", source="dom", evidence=signals)

    if "account_deleted_message" in true or (
        "account_missing_after_delete" in true and "open_account_message" in true
    ):
        return outcome_from_code("account_deleted", source="dom", evidence=signals)
    if "account_opened_message" in true or "account_card_present" in true:
        if kind == "open_account" or "account_opened_message" in true:
            if "both_accounts_present" in true and "open_button_present" not in true:
                # Could be already-exists path; prefer opened message when set.
                if "account_opened_message" in true:
                    return outcome_from_code(
                        "account_opened", source="dom", evidence=signals
                    )
            if "account_opened_message" in true:
                return outcome_from_code("account_opened", source="dom", evidence=signals)

    if "both_accounts_present" in true and kind == "open_account":
        if "open_button_present" not in true and "account_opened_message" not in true:
            return outcome_from_code(
                "account_already_exists", source="dom", evidence=signals
            )

    if "account_card_missing" in true and kind in {"get_balance", "lookup_balance", ""}:
        return outcome_from_code("account_not_found", source="dom", evidence=signals)

    if "balance_visible" in true and kind in {"get_balance", "lookup_balance", ""}:
        return outcome_from_code("balance_retrieved", source="dom", evidence=signals)

    return None


def _heuristic_from_answer(
    *,
    task_kind: str | None,
    answer: str | None,
    error: str | None,
) -> OutcomeResult:
    """
    Legacy path: scan answer/error text.

    Marked source=answer_heuristic so evidence packs show when homework is checked.
    """
    text = f"{answer or ''}\n{error or ''}".strip()
    lowered = text.lower()

    if any(
        token in lowered
        for token in (
            "username not found",
            "invalid username",
            "member id not found",
            "unknown username",
        )
    ):
        return outcome_from_code(
            "username_not_found",
            source="answer_heuristic",
            evidence={"matched": "username"},
        )

    if "human intervention: rejected" in lowered:
        return outcome_from_code(
            "human_rejected",
            source="answer_heuristic",
            evidence={"matched": "human_rejected"},
        )

    if any(
        token in lowered
        for token in (
            "human did not confirm",
            "human approval was not given",
            "confirmation timed out",
            "timed out waiting for confirmation",
            "human declined",
        )
    ):
        return outcome_from_code(
            "human_did_not_confirm",
            source="answer_heuristic",
            evidence={"matched": "hitl"},
        )

    if "cannot be recovered" in lowered or "hard failure" in lowered:
        return outcome_from_code(
            "hard_failure",
            source="answer_heuristic",
            evidence={"matched": "hard_failure"},
        )

    if "page not found" in lowered or "page-not-found" in lowered:
        return outcome_from_code(
            "page_not_found",
            source="answer_heuristic",
            evidence={"matched": "page_not_found"},
        )

    if "still reloading" in lowered or (
        "reloading" in lowered and "cannot" in lowered
    ):
        return outcome_from_code(
            "reloading",
            source="answer_heuristic",
            evidence={"matched": "reloading"},
        )

    if any(
        token in lowered
        for token in (
            "ui changed",
            "checkpoint failed",
            "no matching element",
            "action failed",
            "replay_failed",
            "verify_failed",
        )
    ) and "human" not in lowered:
        return outcome_from_code(
            "hard_failure",
            source="answer_heuristic",
            evidence={"matched": "ui_or_action_failure"},
        )

    kind = (task_kind or "").strip().lower()

    if kind in {"get_balance", "lookup_balance"} or (
        not kind and ("balance" in lowered or "do not have a" in lowered)
    ):
        if (
            "do not have a" in lowered
            or "account not found" in lowered
            or "no checking" in lowered
            or "no savings" in lowered
        ):
            return outcome_from_code(
                "account_not_found",
                source="answer_heuristic",
                evidence={"matched": "missing_account"},
            )
        if re.search(r"\$\s*[\d,]+(?:\.\d{1,2})?", text):
            return outcome_from_code(
                "balance_retrieved",
                source="answer_heuristic",
                evidence={"matched": "currency"},
            )

    if kind == "open_account":
        if (
            "already have checking and savings" in lowered
            or "additional accounts are not allowed" in lowered
            or "already have a" in lowered
            or "already exists" in lowered
        ):
            return outcome_from_code(
                "account_already_exists",
                source="answer_heuristic",
                evidence={"matched": "already_exists"},
            )
        if "was not created" in lowered:
            return outcome_from_code(
                "human_did_not_confirm",
                source="answer_heuristic",
                evidence={"matched": "not_created"},
            )
        if (
            "created successfully" in lowered
            or "account created" in lowered
            or "opened" in lowered
        ):
            return outcome_from_code(
                "account_opened",
                source="answer_heuristic",
                evidence={"matched": "opened"},
            )

    if kind == "transfer":
        if "insufficient funds" in lowered:
            return outcome_from_code(
                "insufficient_funds",
                source="answer_heuristic",
                evidence={"matched": "insufficient_funds"},
            )
        if "checking account not found" in lowered or (
            "do not have a checking" in lowered and "transfer" in lowered
        ):
            return outcome_from_code(
                "checking_account_not_found",
                source="answer_heuristic",
                evidence={"matched": "checking_missing"},
            )
        if "savings account not found" in lowered or (
            "do not have a savings" in lowered and "transfer" in lowered
        ):
            return outcome_from_code(
                "savings_account_not_found",
                source="answer_heuristic",
                evidence={"matched": "savings_missing"},
            )
        if "account not found" in lowered or "do not have a" in lowered:
            return outcome_from_code(
                "account_not_found",
                source="answer_heuristic",
                evidence={"matched": "account_missing"},
            )
        if "transfer cancelled" in lowered or "human approval was not given" in lowered:
            return outcome_from_code(
                "human_did_not_confirm",
                source="answer_heuristic",
                evidence={"matched": "transfer_cancelled"},
            )
        if (
            "transfer to" in lowered
            or "transfer from" in lowered
            or "transferred" in lowered
        ):
            return outcome_from_code(
                "transfer_completed",
                source="answer_heuristic",
                evidence={"matched": "transfer_rows"},
            )

    if kind == "delete_account":
        if "there is no" in lowered and "account to receive" in lowered:
            return outcome_from_code(
                "account_not_found",
                source="answer_heuristic",
                evidence={"matched": "no_destination"},
            )
        if "do not have a" in lowered and "was not deleted" in lowered:
            return outcome_from_code(
                "account_not_found",
                source="answer_heuristic",
                evidence={"matched": "missing"},
            )
        if "there is no" in lowered and "account to delete" in lowered:
            return outcome_from_code(
                "account_not_found",
                source="answer_heuristic",
                evidence={"matched": "no_account"},
            )
        if "transfer" in lowered and "declined" in lowered and "was not deleted" in lowered:
            return outcome_from_code(
                "human_did_not_confirm",
                source="answer_heuristic",
                evidence={"matched": "transfer_declined"},
            )
        if "was not deleted" in lowered:
            if "transfer failed" in lowered:
                return outcome_from_code(
                    "hard_failure",
                    source="answer_heuristic",
                    evidence={"matched": "transfer_failed"},
                )
            return outcome_from_code(
                "human_did_not_confirm",
                source="answer_heuristic",
                evidence={"matched": "not_deleted"},
            )
        if "deleted" in lowered and "was not deleted" not in lowered:
            return outcome_from_code(
                "account_deleted",
                source="answer_heuristic",
                evidence={"matched": "deleted"},
            )

    if "was not created" in lowered or "was not deleted" in lowered:
        return outcome_from_code(
            "human_did_not_confirm",
            source="answer_heuristic",
            evidence={"matched": "not_completed"},
        )

    if not text or lowered in {"no answer.", "no answer"}:
        return outcome_from_code(
            "hard_failure",
            source="answer_heuristic",
            evidence={"matched": "empty"},
        )

    if any(
        token in lowered
        for token in (
            "failed",
            "could not",
            "blocked",
            "not allowed",
            "stopped after the maximum",
            "executable doesn't exist",
            "browserType.launch",
            "playwright",
            "target closed",
            "browser has been closed",
        )
    ):
        if "additional accounts" in lowered:
            return outcome_from_code(
                "account_already_exists",
                source="answer_heuristic",
                evidence={"matched": "additional_accounts"},
            )
        return outcome_from_code(
            "hard_failure",
            source="answer_heuristic",
            evidence={"matched": "generic_failure"},
        )

    return outcome_from_code(
        "completed",
        source="answer_heuristic",
        evidence={"matched": "default"},
    )


def resolve_outcome(
    *,
    task_kind: str | None = None,
    answer: str | None = None,
    error: str | None = None,
    outcome_code: str | None = None,
    guardrail_audit: list[dict[str, Any]] | None = None,
    error_events: list[dict[str, Any]] | None = None,
    dom_signals: dict[str, Any] | None = None,
) -> OutcomeResult:
    """
    Resolve run outcome from strongest evidence first.
    """
    if outcome_code:
        return outcome_from_code(
            outcome_code,
            source="explicit",
            evidence={"outcome_code": outcome_code},
        )

    from_guard = _from_guardrail_audit(guardrail_audit)
    if from_guard is not None:
        return from_guard

    from_err = _from_error_events(error_events)
    if from_err is not None:
        return from_err

    from_dom = _from_dom_signals(dom_signals, task_kind=task_kind)
    if from_dom is not None:
        return from_dom

    return _heuristic_from_answer(task_kind=task_kind, answer=answer, error=error)


def classify_run(
    *,
    task_kind: str | None = None,
    answer: str | None = None,
    error: str | None = None,
    outcome_code: str | None = None,
    guardrail_audit: list[dict[str, Any]] | None = None,
    error_events: list[dict[str, Any]] | None = None,
    dom_signals: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Back-compat: return (status, label). Prefer resolve_outcome for full evidence."""
    result = resolve_outcome(
        task_kind=task_kind,
        answer=answer,
        error=error,
        outcome_code=outcome_code,
        guardrail_audit=guardrail_audit,
        error_events=error_events,
        dom_signals=dom_signals,
    )
    return result.as_tuple()


def summarize_answers(task_results: list[dict[str, Any]]) -> tuple[str, str]:
    """
    Combine per-task classifications into one run conclusion.
    First failed task wins; otherwise last pass outcome.
    """
    if not task_results:
        return "failed", label_for("hard_failure")
    last_pass = ("pass", label_for("completed"))
    for item in task_results:
        status = item.get("status") or "failed"
        outcome = item.get("outcome") or label_for("hard_failure")
        if status == "failed":
            return status, outcome
        last_pass = (status, outcome)
    return last_pass


def summarize_task_results(task_results: list[dict[str, Any]]) -> OutcomeResult:
    """Like summarize_answers but preserves codes when present."""
    if not task_results:
        return outcome_from_code("hard_failure", source="empty")
    last_pass: OutcomeResult | None = None
    for item in task_results:
        status = item.get("status") or "failed"
        code = item.get("outcome_code") or code_from_label(item.get("outcome"))
        if not code:
            code = "hard_failure" if status == "failed" else "completed"
        result = outcome_from_code(
            code,
            source=str(item.get("outcome_source") or "task_result"),
            evidence=dict(item.get("outcome_evidence") or {}),
        )
        if status == "failed":
            return result
        last_pass = result
    return last_pass or outcome_from_code("completed", source="task_result")
