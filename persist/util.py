"""Small helpers shared by the environment and the task families."""

from __future__ import annotations

import posixpath
from typing import Any

from .core import ToolError


def norm_path(p: Any) -> str:
    """Normalize a path argument to an absolute POSIX path or raise ToolError."""
    if not isinstance(p, str) or not p.strip():
        raise ToolError("Error: path must be a non-empty string.")
    p = "/" + p.strip().lstrip("/")
    n = posixpath.normpath(p)
    return "/" if n in ("/", "//") else n


def safe_norm(p: Any) -> str | None:
    """Like norm_path but returns None instead of raising."""
    try:
        return norm_path(p)
    except ToolError:
        return None


def under(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


_TYPE_NAMES = {str: "a string", list: "a list", dict: "an object"}


def arg(args: dict, name: str, typ: type = str, required: bool = True, default: Any = None) -> Any:
    """Fetch and type-check a tool argument."""
    if not isinstance(args, dict):
        raise ToolError("Error: 'args' must be a JSON object.")
    if name not in args or args[name] is None:
        if required:
            raise ToolError(f"Error: missing required argument '{name}'.")
        return default
    value = args[name]
    if not isinstance(value, typ):
        raise ToolError(f"Error: argument '{name}' must be {_TYPE_NAMES.get(typ, typ.__name__)}.")
    return value
