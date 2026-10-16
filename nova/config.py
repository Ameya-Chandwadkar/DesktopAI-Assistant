"""User settings: typed, validated, persisted in SQLite.

Machine-specific values (search folders, app paths, microphone, model folder)
live here and are edited in the Settings window - never in source code.
`python -m nova --import-config config.json` loads a file such as
config.example.json into the database (handy when setting up the Lenovo).
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import paths
from .db import Database

BROWSERS = ("default", "chrome", "edge", "firefox")
SPEECH_ENGINES = ("auto", "whisper", "vosk")
_PREF_KEY = "settings"


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def _str_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out = {}
    for k, v in value.items():
        k, v = str(k).strip().lower(), str(v).strip()
        if k and v:
            out[k] = v
    return out


@dataclass
class Settings:
    search_roots: list[str] = field(default_factory=paths.default_search_roots)
    browser: str = "default"
    always_on_top: bool = True
    speech_engine: str = "auto"  # auto = Whisper if downloaded, else Vosk
    microphone: str = ""  # substring of a device name; "" = system default
    vosk_model_path: str = ""  # "" = auto-detect inside the models folder
    custom_apps: dict[str, str] = field(default_factory=dict)  # spoken name -> .exe/.lnk path
    custom_sites: dict[str, str] = field(default_factory=dict)  # spoken name -> URL
    history_enabled: bool = True
    max_search_results: int = 8

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        """Build from untrusted data: unknown keys are dropped, bad values fall back to defaults."""
        s = cls()
        if not isinstance(data, dict):
            return s
        if "search_roots" in data:
            s.search_roots = _str_list(data["search_roots"])
        if data.get("browser") in BROWSERS:
            s.browser = data["browser"]
        if data.get("speech_engine") in SPEECH_ENGINES:
            s.speech_engine = data["speech_engine"]
        for name in ("always_on_top", "history_enabled"):
            if isinstance(data.get(name), bool):
                setattr(s, name, data[name])
        for name in ("microphone", "vosk_model_path"):
            if isinstance(data.get(name), str):
                setattr(s, name, data[name].strip())
        if "custom_apps" in data:
            s.custom_apps = _str_map(data["custom_apps"])
        if "custom_sites" in data:
            s.custom_sites = _str_map(data["custom_sites"])
        n = data.get("max_search_results")
        if isinstance(n, int) and not isinstance(n, bool):
            s.max_search_results = max(1, min(n, 25))
        return s

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)



class SettingsStore:
    """Holds the current Settings; safe to read from worker threads."""

    def __init__(self, db: Database):
        self._db = db
        self._lock = threading.Lock()
        stored = db.get_pref(_PREF_KEY)
        self._settings = Settings.from_dict(stored) if stored is not None else Settings()

    def get(self) -> Settings:
        with self._lock:
            return self._settings

    def update(self, settings: Settings) -> None:
        with self._lock:
            self._settings = settings
        self._db.set_pref(_PREF_KEY, settings.to_dict())

    def import_file(self, path: Path | str) -> Settings:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        data = {k: v for k, v in data.items() if not k.startswith("_")}
        merged = {**self.get().to_dict(), **data}
        self.update(Settings.from_dict(merged))
        return self.get()
