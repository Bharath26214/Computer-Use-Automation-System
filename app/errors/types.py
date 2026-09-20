from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ErrorKind(str, Enum):
    """
    Faults the system is designed to handle (and stamp on operator artifacts).

    Artifact catalog: normal / reloading / page_not_found / hard_failure.
    human_intervention is runtime-only (guardrail HITL), not stored on operators.
    """

    NORMAL = "normal"
    RELOADING = "reloading"
    PAGE_NOT_FOUND = "page_not_found"
    HUMAN_INTERVENTION = "human_intervention"
    HARD_FAILURE = "hard_failure"


class RecoveryStatus(str, Enum):
    RECOVERED = "recovered"
    RETRYING = "retrying"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"
    TERMINAL = "terminal"


# Only these keys may appear on operators/{id}/vN.json → error_handling
# (and only when actually observed — blank {} otherwise).
ERROR_POLICIES: dict[str, dict[str, Any]] = {
    ErrorKind.NORMAL.value: {
        "description": "Happy path — no recovery required.",
        "policy": "none",
        "max_attempts": 0,
    },
    ErrorKind.RELOADING.value: {
        "description": "Page or app is reloading / still loading.",
        "policy": "retry_after_2s_then_5s",
        "delays_sec": [2, 5],
        "max_attempts": 2,
    },
    ErrorKind.PAGE_NOT_FOUND.value: {
        "description": "Target route returned 404 / page not found.",
        "policy": "one_retry",
        "delays_sec": [1],
        "max_attempts": 1,
    },
    ErrorKind.HARD_FAILURE.value: {
        "description": "Terminal failure after retry — no other error paths.",
        "policy": "one_retry_then_terminal",
        "max_attempts": 1,
    },
}

# Keys allowed on operators/{id}/vN.json → error_handling when observed.
ARTIFACT_ERROR_KEYS = tuple(
    key for key in ERROR_POLICIES.keys() if key != ErrorKind.NORMAL.value
)


@dataclass
class RuntimeErrorEvent:
    """One detected fault + recovery attempt, for runs and operator learning."""

    kind: ErrorKind
    message: str
    status: RecoveryStatus
    action: str | None = None
    target: str | None = None
    expected_page: str | None = None
    actual_page: str | None = None
    attempt: int = 0
    delay_sec: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        payload["status"] = self.status.value
        return payload


def default_error_handling_catalog() -> dict[str, Any]:
    """
    Full policy reference for handled artifact cases.

    Operator artifacts do NOT stamp this by default — they store only errors
    actually handled in a run (blank {} when none).
    """
    return {
        key: {
            **value,
            "recorded_occurrences": 0,
            "last_message": None,
        }
        for key, value in ERROR_POLICIES.items()
    }


def catalog_kind(kind: str | ErrorKind | None) -> str | None:
    """Map a runtime kind onto an artifact catalog key, or None if not stored."""
    if kind is None:
        return None
    value = kind.value if isinstance(kind, ErrorKind) else str(kind)
    aliases = {
        "cannot_recover": ErrorKind.HARD_FAILURE.value,
        "ui_changed": None,  # not a handled artifact error
        "human_intervention": None,  # runtime HITL only; not stored on operators
        "mfa": None,
    }
    if value in aliases:
        return aliases[value]
    if value in ERROR_POLICIES:
        return value
    return None
