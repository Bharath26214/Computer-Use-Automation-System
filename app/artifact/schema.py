from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict


class ArtifactParam(TypedDict):
    """Typed input the calling agent supplies per invocation."""

    type: str
    required: bool
    description: str
    example: NotRequired[str]
    pattern: NotRequired[str]
    enum: NotRequired[list[str]]


class ArtifactOutputField(TypedDict):
    """Typed output / extracted data shape returned to the calling agent."""

    type: str
    description: str
    shape: NotRequired[str]
    example: NotRequired[str]


class ArtifactTarget(TypedDict):
    """How a UI control is located via the DOM (never screen coordinates)."""

    strategy: str
    value: NotRequired[str]
    role: NotRequired[str]
    name: NotRequired[str]
    robustness: str
    interaction: NotRequired[str]  # always "dom"


class ArtifactStep(TypedDict):
    """One ordered browser action in the reusable capability."""

    id: str
    type: str
    description: str
    risk: str  # low | medium | high — from guardrail risk classification
    target: ArtifactTarget
    value: NotRequired[str]


class ArtifactSuccessCondition(TypedDict):
    """Human- and agent-readable checkpoint that the flow completed correctly."""

    id: str
    description: str
    required: bool


class ArtifactViewport(TypedDict):
    profile: str
    width: int
    height: int


class Artifact(TypedDict):
    """
    Structured, agent-invocable capability artifact.

    Versioned under operators/{artifact_id}/v{version}.json so both a human
    reviewer and a calling agent can see what the capability does, what it
    needs, and what it returns — without embedding sensitive member names.

    Locators are DOM-only (testid / role / label). The same artifact recorded
    on desktop should replay on tablet/mobile via scroll-into-view; if the UI
    structure differs, discovery writes a new version.
    """

    artifact_id: str
    version: int
    title: str
    description: str
    locator_policy: NotRequired[str]
    viewport: NotRequired[ArtifactViewport]
    viewports_validated: NotRequired[list[str]]
    error_handling: NotRequired[dict[str, Any]]
    inputs: dict[str, ArtifactParam]
    outputs: dict[str, ArtifactOutputField]
    steps: list[ArtifactStep]
    success_conditions: list[ArtifactSuccessCondition]
    query_signatures: NotRequired[list[str]]


ActionName = Literal["click", "fill", "read", "navigate", "finish", "request_human"]


class RecordedAction(TypedDict):
    action: ActionName
    target: dict[str, Any]
