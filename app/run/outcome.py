from __future__ import annotations

import re
from typing import Any


# System / safety failures — run status is failed.
FAILURE_OUTCOMES = {
    "username_not_found": "Username not found",
    "human_did_not_confirm": "Human did not confirm",
    "human_rejected": "Human intervention: rejected",
    "page_not_found": "Page not found",
    "reloading": "Reloading failed",
    "hard_failure": "Hard failure",
    # Legacy labels still referenced by older messages → hard failure.
    "cannot_recover": "Hard failure",
    "ui_changed": "Hard failure",
}


def classify_run(
    *,
    task_kind: str | None = None,
    answer: str | None = None,
    error: str | None = None,
) -> tuple[str, str]:
    """
    Return (status, outcome) for run.json.

    status is \"pass\" or \"failed\".
    Business conclusions (account missing, already exists, etc.) are pass.
    Username not found, UI changed, human non-confirmation, and recovery
    exhaustion are failed.
    """
    text = f"{answer or ''}\n{error or ''}".strip()
    lowered = text.lower()

    # --- hard failures ---
    if any(
        token in lowered
        for token in (
            "username not found",
            "invalid username",
            "member id not found",
            "unknown username",
        )
    ):
        return "failed", FAILURE_OUTCOMES["username_not_found"]

    if "human intervention: rejected" in lowered:
        return "failed", FAILURE_OUTCOMES["human_rejected"]

    if any(
        token in lowered
        for token in (
            "human did not confirm",
            "human approval was not given",
            "confirmation timed out",
            "timed out waiting for confirmation",
            "human intervention: rejected",
        )
    ):
        return "failed", FAILURE_OUTCOMES["human_did_not_confirm"]

    if "cannot be recovered" in lowered or "hard failure" in lowered:
        return "failed", FAILURE_OUTCOMES["hard_failure"]

    if "page not found" in lowered or "page-not-found" in lowered:
        return "failed", FAILURE_OUTCOMES["page_not_found"]

    if "still reloading" in lowered or (
        "reloading" in lowered and "cannot" in lowered
    ):
        return "failed", FAILURE_OUTCOMES["reloading"]

    if any(
        token in lowered
        for token in (
            "ui changed",
            "checkpoint failed",
            "no matching element",
            "action failed",
            "locator.",
            "timeout",
            "replay_failed",
            "verify_failed",
        )
    ) and "human" not in lowered:
        # Prefer specific human timeout message above; other timeouts → UI changed.
        if "timed out waiting for confirmation" in lowered or "confirmation timed out" in lowered:
            return "failed", FAILURE_OUTCOMES["human_did_not_confirm"]
        if "timeout" in lowered or "ui changed" in lowered or "checkpoint failed" in lowered or "action failed" in lowered or "no matching element" in lowered or "replay_failed" in lowered:
            return "failed", FAILURE_OUTCOMES["hard_failure"]

    kind = (task_kind or "").strip().lower()

    # --- business pass outcomes ---
    if kind in {"get_balance", "lookup_balance"} or (
        not kind and ("balance" in lowered or "do not have a" in lowered)
    ):
        if "do not have a" in lowered or "account not found" in lowered or "no checking" in lowered or "no savings" in lowered:
            return "pass", "Account not found"
        if re.search(r"\$\s*[\d,]+(?:\.\d{1,2})?", text):
            return "pass", "Balance retrieved"

    if kind == "open_account":
        if "already have checking and savings" in lowered or "additional accounts are not allowed" in lowered:
            return "pass", "Account already exists"
        if "already have a" in lowered or "already exists" in lowered:
            return "pass", "Account already exists"
        if "was not created" in lowered:
            return "failed", FAILURE_OUTCOMES["human_did_not_confirm"]
        if "created successfully" in lowered or "opened" in lowered:
            return "pass", "Account opened"

    if kind == "transfer":
        if "insufficient funds" in lowered:
            return "pass", "Insufficient funds"
        if "checking account not found" in lowered or (
            "do not have a checking" in lowered and "transfer" in lowered
        ):
            return "pass", "Checking account not found"
        if "savings account not found" in lowered or (
            "do not have a savings" in lowered and "transfer" in lowered
        ):
            return "pass", "Savings account not found"
        if "account not found" in lowered or "do not have a" in lowered:
            return "pass", "Account not found"
        if "transfer cancelled" in lowered or "human approval was not given" in lowered:
            return "failed", FAILURE_OUTCOMES["human_did_not_confirm"]
        if "transfer to" in lowered or "transfer from" in lowered or "transferred" in lowered:
            return "pass", "Transfer completed"

    if kind == "delete_account":
        if "there is no" in lowered and "account to receive" in lowered:
            return "pass", "Account not found"
        if "do not have a" in lowered and "was not deleted" in lowered:
            return "pass", "Account not found"
        if "there is no" in lowered and "account to delete" in lowered:
            return "pass", "Account not found"
        if "transfer" in lowered and "declined" in lowered and "was not deleted" in lowered:
            return "failed", FAILURE_OUTCOMES["human_did_not_confirm"]
        if "was not deleted" in lowered:
            if "transfer failed" in lowered:
                return "failed", FAILURE_OUTCOMES["ui_changed"]
            return "failed", FAILURE_OUTCOMES["human_did_not_confirm"]
        if "deleted" in lowered and "was not deleted" not in lowered:
            return "pass", "Account deleted"

    if "was not created" in lowered or "was not deleted" in lowered:
        return "failed", FAILURE_OUTCOMES["human_did_not_confirm"]

    if not text or lowered in {"no answer.", "no answer"}:
        return "failed", FAILURE_OUTCOMES["ui_changed"]

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
        # "not allowed" for additional accounts already handled above
        if "additional accounts" in lowered:
            return "pass", "Account already exists"
        return "failed", FAILURE_OUTCOMES["ui_changed"]

    return "pass", "Completed"


def summarize_answers(task_results: list[dict[str, Any]]) -> tuple[str, str]:
    """
    Combine per-task classifications into one run conclusion.
    First failed task wins; otherwise last pass outcome.
    """
    if not task_results:
        return "failed", FAILURE_OUTCOMES["ui_changed"]
    last_pass = ("pass", "Completed")
    for item in task_results:
        status = item.get("status") or "failed"
        outcome = item.get("outcome") or FAILURE_OUTCOMES["ui_changed"]
        if status == "failed":
            return status, outcome
        last_pass = (status, outcome)
    return last_pass
