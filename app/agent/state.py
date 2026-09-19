from typing import Annotated, NotRequired, TypedDict

from langgraph.graph.message import add_messages


class Observation(TypedDict):
    url: str
    title: str
    text: str


class AgentState(TypedDict):
    goal: str
    messages: Annotated[list, add_messages]
    observation: NotRequired[Observation | None]
    action: NotRequired[dict | None]
    last_result: NotRequired[str | None]
    answer: NotRequired[str | None]
    action_log: NotRequired[list[str]]
    recorded_steps: NotRequired[list[dict]]
    artifact_path: NotRequired[str | None]
    outputs: NotRequired[dict[str, str]]
    checkpoints: NotRequired[dict[str, bool]]
    checkpoint_passed: NotRequired[bool]
    error: NotRequired[str | None]
    risk_level: NotRequired[str | None]
    iteration: int
    max_iterations: int
    status: str
