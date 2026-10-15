"""Machine-specific locations. Nothing in here is hardcoded to a particular PC."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

ENV_DATA_DIR = "NOVA_DATA_DIR"


def data_dir() -> Path:
    """Where NOVA keeps its database, logs and speech models.

    Override with the NOVA_DATA_DIR environment variable (used by tests and
    for portable installs). Default: %APPDATA%\\NOVA on Windows.
    """
    override = os.environ.get(ENV_DATA_DIR)
    if override:
        base = Path(override)
    elif sys.platform == "win32" and os.environ.get("APPDATA"):
        base = Path(os.environ["APPDATA"]) / "NOVA"
    else:
        base = Path.home() / ".nova"
    base.mkdir(parents=True, exist_ok=True)
    return base


def models_dir() -> Path:
    d = data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    d = data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


# Windows Known Folder IDs (handles OneDrive-redirected Documents/Desktop).
_KNOWN_FOLDER_IDS = {
    "Documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "Desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "Downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
}


def _windows_known_folder(name: str) -> Path | None:
    if sys.platform != "win32" or name not in _KNOWN_FOLDER_IDS:
        return None
    try:
        from ctypes import wintypes
        import uuid

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        guid_bytes = uuid.UUID(_KNOWN_FOLDER_IDS[name]).bytes_le
        guid = GUID.from_buffer_copy(guid_bytes)
        out = ctypes.c_wchar_p()
        result = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(guid), 0, None, ctypes.byref(out)
        )
        if result != 0 or not out.value:
            return None
        path = Path(out.value)
        ctypes.windll.ole32.CoTaskMemFree(out)
        return path
    except Exception:
        return None


def known_folder(name: str) -> Path:
    """Documents / Desktop / Downloads for the current user."""
    return _windows_known_folder(name) or (Path.home() / name)


def default_search_roots() -> list[str]:
    """Sensible first-run search folders; the user edits them in Settings."""
    roots = [known_folder(n) for n in ("Documents", "Desktop", "Downloads")]
    return [str(p) for p in roots if p.is_dir()]
