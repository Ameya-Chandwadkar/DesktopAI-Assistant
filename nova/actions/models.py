"""Plain data types shared by the parser, the engine and the UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Status(str, Enum):
    OK = "ok"
    NEEDS_CHOICE = "needs_choice"  # several matches; the user must pick one
    NEEDS_CONFIRMATION = "needs_confirmation"
    NOT_FOUND = "not_found"
    INVALID = "invalid"  # failed argument validation / not allowed
    ERROR = "error"
    UNKNOWN = "unknown"  # command not understood


@dataclass(frozen=True)
class Action:
    """A request to run one allowlisted action. Produced by the parser (later: the LLM)."""

    name: str
    args: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        shown = ", ".join(f"{k}={v}" for k, v in self.args.items() if k in _SHOWN_ARGS)
        return f"{self.name.replace('_', ' ')}" + (f" ({shown})" if shown else "")


_SHOWN_ARGS = {"name", "query", "url", "kind"}


@dataclass(frozen=True)
class Choice:
    label: str
    detail: str
    path: str


@dataclass(frozen=True)
class ActionResult:
    status: Status
    message: str
    choices: tuple[Choice, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status is Status.OK
