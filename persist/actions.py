"""Parse a model response into an action dict {"tool": str, "args": dict}."""

from __future__ import annotations

import json
import re

_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def strip_thinking(text: str) -> str:
    text = _THINK_RE.sub("", text)
    if "</think>" in text:  # opening tag was in the prompt (some chat templates)
        text = text.split("</think>", 1)[1]
    return text.replace("<think>", "")


def _normalize(obj) -> dict | None:
    if not isinstance(obj, dict):
        return None
    if "function" in obj and isinstance(obj["function"], dict):  # OpenAI-style tool call
        obj = obj["function"]
    tool = obj.get("tool", obj.get("name"))
    if not isinstance(tool, str) or not tool.strip():
        return None
    args = obj.get("args", obj.get("arguments", obj.get("parameters", {})))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return None
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return None
    return {"tool": tool.strip(), "args": args}


def parse_action(text: str | None) -> dict | None:
    """Return the first JSON object in the text that looks like a tool call, else None."""
    if not text:
        return None
    text = strip_thinking(text)
    decoder = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        action = _normalize(obj)
        if action:
            return action
    return None
