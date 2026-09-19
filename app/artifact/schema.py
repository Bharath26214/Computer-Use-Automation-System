from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict


class ArtifactInput(TypedDict):
    type: str
    required: bool


class ArtifactOutput(TypedDict):
    type: str


class ArtifactTarget(TypedDict):
    strategy: str
    value: NotRequired[str]
    role: NotRequired[str]
    name: NotRequired[str]


class ArtifactStep(TypedDict):
    id: str
    type: str
    target: ArtifactTarget
    value: NotRequired[str]


class Artifact(TypedDict):
    artifact_id: str
    version: int
    inputs: dict[str, ArtifactInput]
    outputs: dict[str, ArtifactOutput]
    steps: list[ArtifactStep]
    checkpoints: list[str]
    recorded_for: NotRequired[str]
    source_query: NotRequired[str]


ActionName = Literal["click", "fill", "read", "navigate", "finish", "request_human"]


class RecordedAction(TypedDict):
    action: ActionName
    target: dict[str, Any]
