"""What NOVA is allowed to open, and where from.

Opening a file hands it to its default Windows app, so a .bat/.exe/.ps1 would
*run*. Only document-like extensions are ever opened, and only from folders the
user has configured (adding a folder in Settings is the explicit authorisation).
"""

from __future__ import annotations

import os
from pathlib import Path

KIND_EXTENSIONS: dict[str, frozenset[str]] = {
    "pdf": frozenset({".pdf"}),
    "word": frozenset({".doc", ".docx", ".rtf", ".odt"}),
    "text": frozenset({".txt", ".md", ".log"}),
    "excel": frozenset({".xls", ".xlsx", ".csv"}),
    "powerpoint": frozenset({".ppt", ".pptx"}),
    "image": frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}),
}

OPENABLE_EXTENSIONS: frozenset[str] = frozenset().union(*KIND_EXTENSIONS.values())


class PathNotAllowed(Exception):
    pass


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_allowed(path_str: str, roots: list[str]) -> Path:
    """Return the resolved file path if it is an existing, openable file inside a configured root."""
    if not isinstance(path_str, str) or not path_str.strip() or "\x00" in path_str:
        raise PathNotAllowed("No file path was given.")
    try:
        path = Path(path_str).resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        raise PathNotAllowed("That path is not valid.")
    resolved_roots = []
    for r in roots:
        try:
            resolved_roots.append(Path(r).resolve(strict=False))
        except (OSError, RuntimeError, ValueError):
            continue
    if not any(is_within(path, r) for r in resolved_roots):
        raise PathNotAllowed("That file is outside the folders NOVA may search. Add its folder in Settings.")
    if path.suffix.lower() not in OPENABLE_EXTENSIONS:
        raise PathNotAllowed(f"NOVA does not open '{path.suffix or 'this'}' files.")
    if not path.exists():
        raise FileNotFoundError(str(path))
    if not path.is_file():
        raise PathNotAllowed("That path is not a file.")
    return path
