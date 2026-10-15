"""SQLite storage for preferences and command history."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from . import paths

_SCHEMA = """
CREATE TABLE IF NOT EXISTS prefs (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS history (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    source  TEXT NOT NULL,
    heard   TEXT NOT NULL,
    action  TEXT NOT NULL,
    status  TEXT NOT NULL,
    message TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class HistoryEntry:
    id: int
    ts: str
    source: str
    heard: str
    action: str
    status: str
    message: str


class Database:
    """Small thread-safe wrapper (the UI and worker threads both write to it)."""

    def __init__(self, path: Path | str | None = None):
        self.path = str(path) if path is not None else str(paths.data_dir() / "nova.db")
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---- preferences -------------------------------------------------
    def get_pref(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value FROM prefs WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return default

    def set_pref(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO prefs(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )
            self._conn.commit()

    # ---- history -----------------------------------------------------
    def add_history(self, source: str, heard: str, action: str, status: str, message: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO history(ts, source, heard, action, status, message) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"), source, heard, action, status, message),
            )
            self._conn.commit()

    def recent_history(self, limit: int = 200) -> list[HistoryEntry]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [HistoryEntry(**dict(r)) for r in rows]

    def clear_history(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM history")
            self._conn.commit()
