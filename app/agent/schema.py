from typing import Literal, Optional

from pydantic import BaseModel


class AgentAction(BaseModel):
    action: Literal[
        "click",
        "fill",
        "read",
        "navigate",
        "finish",
        "request_human",
    ]
    target: Optional[str] = None
    value: Optional[str] = None
    reason: Optional[str] = None
