from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class HITLState(str, Enum):
    """Human-in-the-loop gate for an action."""

    ALLOW = "allow"
    BLOCK = "block"
    REQUIRE_APPROVAL = "require_approval"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class GuardrailDecision:
    """Outcome of evaluating one action against the guardrail engine."""

    decision: HITLState
    risk: RiskLevel
    rule: str
    message: str
    status: str = "evaluated"
    action: str | None = None
    target: str | None = None
    expected_page: str | None = None
    actual_page: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def blocked(self) -> bool:
        return self.decision == HITLState.BLOCK

    def needs_approval(self) -> bool:
        return self.decision == HITLState.REQUIRE_APPROVAL

    def to_audit(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["decision"] = self.decision.value
        payload["risk"] = self.risk.value
        payload["guardrail_decision"] = self.decision.value
        return payload
