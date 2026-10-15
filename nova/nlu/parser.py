"""Fast, offline, deterministic command understanding (no LLM, no network).

Turns a sentence like "open notepad" or "find resume pdf" into an Action, or
returns None if it isn't recognised. Phase 2 will add an optional LLM that only
runs when this parser returns None, and produces the same Action objects.
"""

from __future__ import annotations

import re
from typing import Callable

from ..actions.models import Action
from ..actions.web import BUILTIN_SITES, looks_like_domain, spoken_to_url_text

_PREFIXES = (
    "hey nova", "ok nova", "okay nova", "nova", "please", "can you", "could you", "would you",
    "i want to", "i would like to", "i'd like to", "go ahead and", "just",
)
_SUFFIXES = ("please", "for me", "now", "thanks", "thank you")

_OPEN_VERBS = r"(?:open|launch|start|run|fire up|bring up)"
_NAV_VERBS = r"(?:go to|take me to|browse to|visit|navigate to)"

# phrase -> kind key in files.safety.KIND_EXTENSIONS
_KIND_PHRASES = {
    "pdf file": "pdf", "pdf document": "pdf", "pdf": "pdf",
    "word document": "word", "word file": "word", "word doc": "word", "docx": "word",
    "text file": "text", "text document": "text", "notes file": "text",
    "excel file": "excel", "excel sheet": "excel", "spreadsheet": "excel",
    "powerpoint": "powerpoint", "presentation": "powerpoint", "slides": "powerpoint",
}
_KIND_ALTERNATION = "|".join(sorted((re.escape(p) for p in _KIND_PHRASES), key=len, reverse=True))
_KIND_TRAILING = re.compile(rf"\s+({_KIND_ALTERNATION})$")
_KIND_LEADING = re.compile(rf"^({_KIND_ALTERNATION})\s+")
_FILLER_LEADING = re.compile(r"^(?:the |my |a |an )+")
_NOUN_EDGE = re.compile(r"^(?:files? |documents? |docs? |named |called |name )+|(?: files?| documents?| docs?)$")

_NUMBER_WORDS = {
    "one": 1, "first": 1, "two": 2, "second": 2, "to": 2, "too": 2, "three": 3, "third": 3,
    "four": 4, "for": 4, "fourth": 4, "five": 5, "fifth": 5, "six": 6, "sixth": 6,
    "seven": 7, "seventh": 7, "eight": 8, "eighth": 8, "nine": 9, "ninth": 9, "ten": 10, "tenth": 10,
}


def normalise_text(text: str) -> str:
    t = text.lower().strip()
    t = re.sub(r"[^\w\s./:'#+&-]", " ", t)  # keep characters that appear in URLs and names
    t = " ".join(t.split())
    changed = True
    while changed:
        changed = False
        for p in _PREFIXES:
            if t.startswith(p + " "):
                t, changed = t[len(p) + 1 :], True
        for s in _SUFFIXES:
            if t.endswith(" " + s):
                t, changed = t[: -len(s) - 1], True
    return t.strip(" .")


def split_kind(query: str) -> tuple[str, str | None]:
    """'resume pdf' -> ('resume', 'pdf'); also strips filler words like 'file'/'called'."""
    q = _FILLER_LEADING.sub("", query.strip())
    kind = None
    m = _KIND_TRAILING.search(q) or _KIND_LEADING.search(q)
    if m:
        kind = _KIND_PHRASES[m.group(1)]
        q = _KIND_TRAILING.sub("", q) if m.re is _KIND_TRAILING else _KIND_LEADING.sub("", q)
    q = _NOUN_EDGE.sub("", q.strip()).strip()
    q = _NOUN_EDGE.sub("", q).strip()
    return q, kind


class LocalParser:
    def __init__(
        self,
        known_apps: Callable[[], set[str]],
        custom_sites: Callable[[], dict[str, str]],
    ):
        self._apps = known_apps
        self._custom_sites = custom_sites

    def _sites(self) -> dict[str, str]:
        return {**BUILTIN_SITES, **self._custom_sites()}

    def parse(self, text: str) -> Action | None:
        t = normalise_text(text)
        if not t:
            return None

        # YouTube searches
        m = (
            re.match(rf"^(?:search|find|look up|look for)(?: on)? youtube(?: for)? (.+)$", t)
            or re.match(r"^(?:search|find|look up|look for) (.+) (?:on|in) youtube$", t)
            or re.match(r"^play (.+) on youtube$", t)
            or re.match(rf"^{_OPEN_VERBS} youtube and (?:search|play|look)(?: for)? (.+)$", t)
        )
        if m:
            return Action("open_youtube", {"query": m.group(1).strip()})

        # "open X" / "launch X": known apps and sites win ("open file explorer" is an app)
        open_m = re.match(rf"^{_OPEN_VERBS}(?: the)? (.+)$", t)
        if open_m:
            target = re.sub(r"\s+(?:app|application|website|site|program)$", "", open_m.group(1)).strip()
            action = self._target_action(target)
            if action:
                return action

        # "open the file/document X"
        m = re.match(rf"^{_OPEN_VERBS} (?:the |my )?((?:file|document|doc|pdf|word document|text file) .+)$", t)
        if m:
            return self._file_action(m.group(1), open_if_single=True)

        # "find / search for / where is X"
        m = re.match(r"^(?:find|search for|search|look for|locate|where is|where's)\s+(.+)$", t)
        if m:
            return self._file_action(m.group(1), open_if_single=False)

        # "open <something unknown>": maybe it's a document
        if open_m:
            return self._file_action(open_m.group(1), open_if_single=True)

        # "go to X" (websites only)
        m = re.match(rf"^{_NAV_VERBS} (.+)$", t)
        if m:
            return self._target_action(m.group(1).strip(), apps=False)

        # Just a name: "notepad", "youtube", "github.com"
        return self._target_action(t)

    def _target_action(self, target: str, apps: bool = True) -> Action | None:
        if apps and target in self._apps():
            return Action("open_app", {"name": target})
        sites = self._sites()
        if target in sites:
            if target == "youtube":
                return Action("open_youtube", {})
            return Action("open_url", {"url": sites[target]})
        if target.startswith(("http://", "https://")) or looks_like_domain(target):
            return Action("open_url", {"url": spoken_to_url_text(target)})
        return None

    @staticmethod
    def _file_action(raw_query: str, open_if_single: bool) -> Action | None:
        query, kind = split_kind(raw_query)
        if not query:
            return None
        args: dict = {"query": query, "open_if_single": open_if_single}
        if kind:
            args["kind"] = kind
        return Action("search_files", args)


def parse_selection(text: str, count: int) -> int | str | None:
    """Follow-up while a result list is showing.

    Returns a 0-based index, "cancel", or None if `text` isn't a selection.
    """
    t = normalise_text(text)
    if re.fullmatch(r"(?:cancel|never ?mind|dismiss|forget it|none|stop)", t):
        return "cancel"
    if t in ("last", "the last one", "last one"):
        return count - 1
    m = re.fullmatch(r"(?:open |pick |choose |select |show )?(?:the |number |option |no |item )*(\w+?)(?: one)?", t)
    if not m:
        return None
    word = m.group(1)
    n = int(word) if word.isdigit() else _NUMBER_WORDS.get(word)
    if n is None or not 1 <= n <= count:
        return None
    # bare "to"/"for"/"too" are only numbers when the speaker clearly said "number ..."
    if word in ("to", "too", "for") and not re.search(r"number|option|item|no\b", t):
        return None
    return n - 1
