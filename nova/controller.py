"""Ties text -> parser -> engine -> history together. Qt-free so it can be tested anywhere."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable

from .actions.engine import ActionEngine
from .actions.models import Action, ActionResult, Choice, Status
from .config import Settings
from .db import Database
from .nlu.parser import LocalParser, parse_selection

log = logging.getLogger("nova.controller")

HELP_HINT = "Try: 'open notepad', 'open YouTube', 'search YouTube for lo-fi music', or 'find resume pdf'."


@dataclass(frozen=True)
class Outcome:
    heard: str
    action: Action | None
    result: ActionResult


class Assistant:
    def __init__(
        self,
        engine: ActionEngine,
        parser: LocalParser,
        db: Database,
        settings_getter: Callable[[], Settings],
    ):
        self._engine = engine
        self._parser = parser
        self._db = db
        self._settings = settings_getter
        self._pending: tuple[Choice, ...] = ()
        self._lock = threading.Lock()

    @property
    def pending_choices(self) -> tuple[Choice, ...]:
        with self._lock:
            return self._pending

    def submit(self, text: str, source: str = "text") -> Outcome:
        """Handle one utterance (typed or spoken). Never raises."""
        heard = " ".join(text.split())
        if not heard:
            return Outcome(heard, None, ActionResult(Status.UNKNOWN, "I didn't catch anything. " + HELP_HINT))

        pending = self.pending_choices
        if pending:
            sel = parse_selection(heard, len(pending))
            if sel == "cancel":
                self._set_pending(())
                return self._finish(source, Outcome(heard, None, ActionResult(Status.OK, "Cancelled.")))
            if isinstance(sel, int):
                return self._open_choice(pending[sel], heard, source)

        action = self._parser.parse(heard)
        if action is None:
            self._set_pending(())
            return self._finish(source, Outcome(heard, None, ActionResult(Status.UNKNOWN, f"Sorry, I didn't understand that. {HELP_HINT}")))
        result = self._engine.execute(action)
        self._set_pending(result.choices if result.status is Status.NEEDS_CHOICE else ())
        return self._finish(source, Outcome(heard, action, result))

    def choose(self, index: int, source: str = "click") -> Outcome:
        """The user clicked entry `index` of the current result list."""
        pending = self.pending_choices
        if not 0 <= index < len(pending):
            return Outcome("", None, ActionResult(Status.INVALID, "That choice is no longer available."))
        return self._open_choice(pending[index], pending[index].label, source)

    # ------------------------------------------------------------------
    def _open_choice(self, choice: Choice, heard: str, source: str) -> Outcome:
        action = Action("open_file", {"path": choice.path})
        result = self._engine.execute(action)
        if result.ok:
            self._set_pending(())
        return self._finish(source, Outcome(heard, action, result))

    def _set_pending(self, choices: tuple[Choice, ...]) -> None:
        with self._lock:
            self._pending = choices

    def _finish(self, source: str, outcome: Outcome) -> Outcome:
        if self._settings().history_enabled:
            try:
                self._db.add_history(
                    source,
                    outcome.heard,
                    outcome.action.name if outcome.action else "-",
                    outcome.result.status.value,
                    outcome.result.message,
                )
            except Exception:
                log.exception("could not write history")
        return outcome
