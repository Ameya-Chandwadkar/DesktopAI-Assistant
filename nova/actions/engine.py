"""Executes validated actions. Every outcome is an ActionResult - nothing here raises to the UI."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from ..config import Settings
from ..files.safety import KIND_EXTENSIONS, PathNotAllowed, resolve_allowed
from ..files.search import search_files
from .apps import AppResolver
from .models import Action, ActionResult, Choice, Status
from .registry import ACTION_SPECS, validate
from .system import SystemOps
from .web import UrlError, validate_url, youtube_search_url, YOUTUBE_HOME

log = logging.getLogger("nova.actions")


class ActionEngine:
    def __init__(
        self,
        settings_getter: Callable[[], Settings],
        system: SystemOps,
        apps: AppResolver | None = None,
    ):
        self._settings = settings_getter
        self._system = system
        self._apps = apps or AppResolver(settings_getter)

    @property
    def apps(self) -> AppResolver:
        return self._apps

    def execute(self, action: Action, confirmed: bool = False) -> ActionResult:
        problem = validate(action)
        if problem:
            log.warning("rejected action %s: %s", action.name, problem)
            return ActionResult(Status.INVALID, problem)
        if ACTION_SPECS[action.name].requires_confirmation and not confirmed:
            return ActionResult(Status.NEEDS_CONFIRMATION, f"Please confirm: {action.describe()}")
        handler = getattr(self, f"_do_{action.name}")
        try:
            result = handler(**{k: v for k, v in action.args.items() if v is not None})
        except Exception:  # last-resort guard so the UI never crashes on an action
            log.exception("action %s crashed", action.name)
            return ActionResult(Status.ERROR, "Something went wrong running that. Details are in the log file.")
        log.info("action=%s args=%s status=%s", action.name, sorted(action.args), result.status.value)
        return result

    # ---- web ----------------------------------------------------------
    def _open_in_browser(self, url: str) -> str:
        """Open `url`; returns an optional note (e.g. when the preferred browser is missing)."""
        browser = self._settings().browser
        note = ""
        if browser != "default":
            exe = self._apps.find_key(browser)
            if exe:
                self._system.launch(exe, [url])
                return ""
            note = f" ({browser.title()} wasn't found, so I used your default browser.)"
        self._system.open_url_default(url)
        return note

    def _do_open_url(self, url: str) -> ActionResult:
        try:
            safe = validate_url(url)
        except UrlError as e:
            return ActionResult(Status.INVALID, str(e))
        try:
            note = self._open_in_browser(safe)
        except OSError as e:
            return ActionResult(Status.ERROR, f"I couldn't open the browser: {e}")
        return ActionResult(Status.OK, f"Opened {safe}{note}")

    def _do_open_youtube(self, query: str | None = None) -> ActionResult:
        url = youtube_search_url(query.strip()) if query and query.strip() else YOUTUBE_HOME
        try:
            note = self._open_in_browser(url)
        except OSError as e:
            return ActionResult(Status.ERROR, f"I couldn't open the browser: {e}")
        what = f"YouTube search for '{query.strip()}'" if query and query.strip() else "YouTube"
        return ActionResult(Status.OK, f"Opened {what}.{note}")

    # ---- applications -------------------------------------------------
    def _do_open_app(self, name: str) -> ActionResult:
        match = self._apps.lookup(name)
        if match is None:
            return ActionResult(
                Status.NOT_FOUND,
                f"I don't know an app called '{name}'. You can add it in Settings > Apps & sites.",
            )
        if match.path is None:
            return ActionResult(Status.NOT_FOUND, f"{match.key.title()} doesn't seem to be installed on this PC.")
        try:
            self._system.launch(match.path)
        except OSError as e:
            return ActionResult(Status.ERROR, f"I couldn't start {match.key.title()}: {e}")
        return ActionResult(Status.OK, f"Opened {match.key.title()}.")

    # ---- files --------------------------------------------------------
    def _do_search_files(
        self, query: str, kind: str | None = None, open_if_single: bool = False
    ) -> ActionResult:
        s = self._settings()
        if not s.search_roots:
            return ActionResult(Status.NOT_FOUND, "No search folders are set up. Add some in Settings > Folders.")
        outcome = search_files(
            query,
            s.search_roots,
            extensions=KIND_EXTENSIONS.get(kind) if kind else None,
            limit=s.max_search_results,
        )
        if len(outcome.missing_roots) == len(s.search_roots):
            return ActionResult(Status.NOT_FOUND, "None of the configured search folders exist. Check Settings > Folders.")
        extra = ""
        if outcome.missing_roots:
            extra += f" ({len(outcome.missing_roots)} search folder(s) were not found.)"
        if outcome.truncated:
            extra += " (Search stopped early to stay responsive; results may be incomplete.)"
        if not outcome.hits:
            return ActionResult(Status.NOT_FOUND, f"I couldn't find a file matching '{query}'.{extra}")

        exact = [h for h in outcome.hits if h.score == 100]
        if open_if_single and (len(outcome.hits) == 1 or len(exact) == 1):
            return self._do_open_file(str((exact or outcome.hits)[0].path))

        choices = tuple(Choice(h.path.name, str(h.path.parent), str(h.path)) for h in outcome.hits)
        n = len(choices)
        lead = f"Found {n} file{'s' if n != 1 else ''} matching '{query}'."
        return ActionResult(Status.NEEDS_CHOICE, f"{lead} Pick one to open, or say its number.{extra}", choices)

    def _do_open_file(self, path: str) -> ActionResult:
        try:
            resolved = resolve_allowed(path, self._settings().search_roots)
        except FileNotFoundError:
            return ActionResult(Status.NOT_FOUND, f"'{Path(path).name}' no longer exists. It may have been moved or deleted.")
        except PathNotAllowed as e:
            return ActionResult(Status.INVALID, str(e))
        try:
            self._system.open_path(str(resolved))
        except OSError as e:
            return ActionResult(Status.ERROR, f"Windows couldn't open '{resolved.name}': {e}")
        return ActionResult(Status.OK, f"Opened {resolved.name}.")
