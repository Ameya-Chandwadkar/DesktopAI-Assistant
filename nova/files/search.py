"""Partial-filename search inside the configured folders."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .safety import OPENABLE_EXTENSIONS

SKIP_DIR_NAMES = frozenset(
    {"node_modules", "__pycache__", "$recycle.bin", "appdata", "site-packages", "venv", ".venv"}
)
MAX_DEPTH = 8
TIME_BUDGET_SECONDS = 8.0

_SEP_RE = re.compile(r"[_\-.()\[\]]+")


def normalise(text: str) -> str:
    return " ".join(_SEP_RE.sub(" ", text.lower()).split())


@dataclass(frozen=True)
class FileHit:
    path: Path
    score: int
    mtime: float


@dataclass
class SearchOutcome:
    hits: list[FileHit] = field(default_factory=list)
    missing_roots: list[str] = field(default_factory=list)
    truncated: bool = False  # stopped early because of the time budget


def _score(stem_norm: str, name_norm: str, query_norm: str, tokens: list[str]) -> int | None:
    if not all(t in name_norm for t in tokens):
        return None
    if stem_norm == query_norm:
        return 100
    if stem_norm.startswith(query_norm):
        return 80
    words = set(name_norm.split())
    if all(t in words for t in tokens):
        return 60
    return 40


def _is_link(entry: os.DirEntry) -> bool:
    if entry.is_symlink():
        return True
    is_junction = getattr(entry, "is_junction", None)
    return bool(is_junction and is_junction())


def search_files(
    query: str,
    roots: list[str],
    extensions: frozenset[str] | None = None,
    limit: int = 8,
    time_budget: float = TIME_BUDGET_SECONDS,
) -> SearchOutcome:
    """Find files whose name contains every word of `query` (case-insensitive).

    Symlinks/junctions are not followed, so a search can never leave the configured roots.
    """
    out = SearchOutcome()
    query_norm = normalise(query)
    tokens = query_norm.split()
    if not tokens:
        return out
    allowed = extensions or OPENABLE_EXTENSIONS
    deadline = time.monotonic() + time_budget
    seen: set[str] = set()
    hits: list[FileHit] = []

    for root in roots:
        root_path = Path(root)
        if not root_path.is_dir():
            out.missing_roots.append(root)
            continue
        stack: list[tuple[Path, int]] = [(root_path, 0)]
        while stack:
            if time.monotonic() > deadline:
                out.truncated = True
                break
            folder, depth = stack.pop()
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue  # unreadable folder: skip quietly
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        name = entry.name.lower()
                        if (
                            depth < MAX_DEPTH
                            and not name.startswith(".")
                            and name not in SKIP_DIR_NAMES
                            and not _is_link(entry)
                        ):
                            stack.append((Path(entry.path), depth + 1))
                        continue
                    if not entry.is_file(follow_symlinks=False) or entry.name.startswith("~$"):
                        continue
                    stem, ext = os.path.splitext(entry.name)
                    if ext.lower() not in allowed:
                        continue
                    score = _score(normalise(stem), normalise(entry.name), query_norm, tokens)
                    if score is None:
                        continue
                    key = os.path.normcase(os.path.realpath(entry.path))
                    if key in seen:
                        continue
                    seen.add(key)
                    hits.append(FileHit(Path(entry.path), score, entry.stat().st_mtime))
                except OSError:
                    continue

    hits.sort(key=lambda h: (-h.score, -h.mtime, len(h.path.name)))
    out.hits = hits[:limit]
    return out
