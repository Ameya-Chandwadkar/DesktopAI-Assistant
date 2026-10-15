"""The allowlist: the *only* actions NOVA can perform, and the exact shape of their arguments.

Anything that produces an Action (today the local parser, in Phase 2 an LLM) goes
through `validate()` before the engine will touch it. There is deliberately no
"run command" or "run code" action.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..files.safety import KIND_EXTENSIONS
from .apps import is_valid_app_name
from .models import Action

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


@dataclass(frozen=True)
class ArgSpec:
    type: type
    required: bool = True
    max_len: int = 200
    check: Callable[[Any], str | None] | None = None  # returns an error message, or None if fine


@dataclass(frozen=True)
class ActionSpec:
    name: str
    description: str
    args: dict[str, ArgSpec] = field(default_factory=dict)
    requires_confirmation: bool = False  # engine refuses to run it until confirmed=True


def _check_app_name(v: str) -> str | None:
    return None if is_valid_app_name(v) else "That is not a valid application name."


def _check_kind(v: str) -> str | None:
    return None if v in KIND_EXTENSIONS else f"Unknown file type '{v}'."


ACTION_SPECS: dict[str, ActionSpec] = {
    s.name: s
    for s in (
        ActionSpec("open_url", "Open a web address in the browser", {"url": ArgSpec(str, max_len=2048)}),
        ActionSpec("open_youtube", "Open YouTube, optionally searching", {"query": ArgSpec(str, required=False)}),
        ActionSpec("open_app", "Launch an installed application", {"name": ArgSpec(str, max_len=64, check=_check_app_name)}),
        ActionSpec(
            "search_files",
            "Search the configured folders for files by partial name",
            {
                "query": ArgSpec(str, max_len=100),
                "kind": ArgSpec(str, required=False, max_len=20, check=_check_kind),
                "open_if_single": ArgSpec(bool, required=False),
            },
        ),
        ActionSpec("open_file", "Open a file with its default application", {"path": ArgSpec(str, max_len=1024)}),
    )
}


def validate(action: Action) -> str | None:
    """Return a human-readable problem, or None if the action is allowed and well-formed."""
    spec = ACTION_SPECS.get(action.name)
    if spec is None:
        return f"'{action.name}' is not a supported action."
    if not isinstance(action.args, dict):
        return "Action arguments must be a dictionary."
    for key in action.args:
        if key not in spec.args:
            return f"'{key}' is not a valid argument for {action.name}."
    for key, arg in spec.args.items():
        if key not in action.args or action.args[key] is None:
            if arg.required:
                return f"Missing required argument '{key}'."
            continue
        value = action.args[key]
        if not isinstance(value, arg.type) or (arg.type is not bool and isinstance(value, bool)):
            return f"Argument '{key}' must be a {arg.type.__name__}."
        if isinstance(value, str):
            if arg.required and not value.strip():
                return f"Argument '{key}' is empty."
            if len(value) > arg.max_len:
                return f"Argument '{key}' is too long."
            if _CONTROL_RE.search(value):
                return f"Argument '{key}' contains control characters."
        if arg.check is not None:
            problem = arg.check(value)
            if problem:
                return problem
    return None
