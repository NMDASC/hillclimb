"""Core data types: Task, ToolSpec, ToolError."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Callable


class ToolError(Exception):
    """Raised by a tool; the message becomes the observation shown to the agent."""


@dataclass
class Task:
    task_id: str
    family: str
    instruction: str
    files: dict[str, str]          # initial virtual file system: path -> content
    resource: str                  # the input the task depends on (a path or "service:...")
    resource_label: str            # human-readable name used in RESTRICTED errors
    primary_tool: str              # tool whose failures are injected in transient/switch
    alt_tools: list[str]           # permitted alternative path(s)
    output_path: str
    expected: Any                  # parsed expected output, used by the oracle
    primary_plan: list[dict]       # canonical solution via the primary tool
    alt_plan: list[dict]           # canonical solution via the alternative path
    service_data: dict[str, Any] = field(default_factory=dict)

    @property
    def primary_call(self) -> dict:
        """The standardized action repeated in setback histories."""
        return self.primary_plan[0]

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        return cls(**d)


def _never(task: Task, args: dict) -> bool:
    return False


@dataclass
class ToolSpec:
    name: str
    signature: str
    description: str
    fn: Callable[..., str]                               # fn(env, args) -> observation
    touches: Callable[[Task, dict], bool] = _never       # does this call need task.resource?
    path_args_read: tuple[str, ...] = ()                 # used for rule-violation detection
    path_args_write: tuple[str, ...] = ()
