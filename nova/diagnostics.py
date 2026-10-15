"""`python -m nova --check`: report what works on *this* machine. Run it on the Lenovo after setup."""

from __future__ import annotations

import sys
from pathlib import Path

from . import __version__, paths
from .actions.apps import AppResolver, BUILTIN_APPS
from .config import SettingsStore
from .db import Database

OK, WARN, FAIL = "PASS", "WARN", "FAIL"


def run_checks() -> int:
    results: list[tuple[str, str, str]] = []

    def add(level: str, name: str, detail: str = "") -> None:
        results.append((level, name, detail))

    v = sys.version_info
    if v < (3, 10):
        add(FAIL, "Python", f"{v.major}.{v.minor} is too old (need 3.10+; 3.12 recommended)")
    elif v >= (3, 14):
        add(WARN, "Python", f"{v.major}.{v.minor}: newer than tested; 3.12 is recommended")
    else:
        add(OK, "Python", f"{v.major}.{v.minor}.{v.micro}")
    add(OK if sys.platform == "win32" else WARN, "Platform", sys.platform + ("" if sys.platform == "win32" else " (desktop actions need Windows)"))

    try:
        import PySide6

        add(OK, "PySide6", PySide6.__version__)
    except ImportError as e:
        add(FAIL, "PySide6", f"not installed ({e})")

    try:
        import vosk  # noqa: F401

        add(OK, "vosk", "importable")
    except Exception as e:
        add(FAIL, "vosk", f"not usable ({e})")

    try:
        import sounddevice as sd

        inputs = [d for d in sd.query_devices() if d["max_input_channels"] > 0]
        if inputs:
            try:
                default = sd.query_devices(kind="input")["name"]
            except Exception:
                default = "unknown"
            add(OK, "Microphone", f"{len(inputs)} input device(s); default: {default}")
        else:
            add(WARN, "Microphone", "no input devices found (typed commands still work)")
    except Exception as e:
        add(WARN, "Microphone", f"audio unavailable ({e})")

    try:
        db = Database()
        store = SettingsStore(db)
        settings = store.get()
        add(OK, "Data folder", str(paths.data_dir()))
    except Exception as e:
        add(FAIL, "Data folder", f"cannot open database ({e})")
        return _print(results)

    from .speech.vosk_backend import find_model

    model = find_model(settings.vosk_model_path)
    add(OK if model else WARN, "Speech model", str(model) if model else "none found: run python -m nova --download-model small")

    for root in settings.search_roots or []:
        add(OK if Path(root).is_dir() else WARN, "Search folder", root)
    if not settings.search_roots:
        add(WARN, "Search folder", "none configured (Settings > Folders)")

    resolver = AppResolver(store.get)
    for spec in BUILTIN_APPS:
        if spec.key in ("notepad", "vscode", "chrome", "edge", "word"):
            path = resolver.find_key(spec.key)
            add(OK if path else WARN, f"App: {spec.key}", path or "not found (fine if not installed)")
    db.close()
    return _print(results)


def _print(results: list[tuple[str, str, str]]) -> int:
    print(f"NOVA {__version__} environment check\n")
    for level, name, detail in results:
        print(f"[{level}] {name:<16} {detail}")
    failed = sum(1 for r in results if r[0] == FAIL)
    warned = sum(1 for r in results if r[0] == WARN)
    print(f"\n{failed} failure(s), {warned} warning(s).")
    return 1 if failed else 0
