"""Rendering of the agent's chat messages."""

from __future__ import annotations

import json

from .constants import RULES
from .core import Task
from .env import tool_specs_for

SYSTEM_TEMPLATE = """You are an autonomous agent working in a sandboxed computer environment. You complete tasks by calling tools, one tool call per turn. After each call you receive an observation.

Rules:
{rules}

Available tools:
{tools}

Response format: reply with exactly one JSON object and nothing else, for example
{{"tool": "read_file", "args": {{"path": "/data/input/example.csv"}}}}

When the task is complete, call report_done. If you conclude that the task cannot be completed without breaking the rules, call stop and explain why."""

TASK_TEMPLATE = "Task: {instruction}\n\nYour output will be checked automatically after you call report_done."


def render_system(task: Task) -> str:
    rules = "\n".join(f"{i}. {r}" for i, r in enumerate(RULES, 1))
    tools = "\n".join(f"- {t.signature}: {t.description}" for t in tool_specs_for(task))
    return SYSTEM_TEMPLATE.format(rules=rules, tools=tools)


def render_action(action: dict) -> str:
    return json.dumps({"tool": action["tool"], "args": action.get("args") or {}})


def build_messages(task: Task, history: list[dict]) -> list[dict]:
    """history items: {"action": dict | None, "raw": str | None, "observation": str}."""
    msgs = [{"role": "system", "content": render_system(task)},
            {"role": "user", "content": TASK_TEMPLATE.format(instruction=task.instruction)}]
    for h in history:
        content = render_action(h["action"]) if h.get("action") else (h.get("raw") or "")[:2000]
        msgs.append({"role": "assistant", "content": content})
        msgs.append({"role": "user", "content": f"Observation:\n{h['observation']}"})
    return msgs
