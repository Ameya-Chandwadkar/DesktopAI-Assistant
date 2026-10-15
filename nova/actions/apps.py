"""Finding installed applications by spoken name.

Resolution order for an app: user's custom path -> Windows "App Paths" registry
-> PATH -> well-known install folders. Nothing is assumed to be installed.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..config import Settings


@dataclass(frozen=True)
class AppSpec:
    key: str
    aliases: tuple[str, ...]
    exe: str  # file name used for the registry / PATH lookup
    install_paths: tuple[str, ...] = ()  # %ENV% templates


BUILTIN_APPS: tuple[AppSpec, ...] = (
    AppSpec("notepad", ("notepad", "note pad"), "notepad.exe"),
    AppSpec(
        "vscode",
        ("vs code", "vscode", "visual studio code", "code"),
        "Code.exe",
        (
            r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
            r"%ProgramFiles%\Microsoft VS Code\Code.exe",
            r"%ProgramFiles(x86)%\Microsoft VS Code\Code.exe",
        ),
    ),
    AppSpec(
        "chrome",
        ("chrome", "google chrome"),
        "chrome.exe",
        (
            r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
            r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
            r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
        ),
    ),
    AppSpec(
        "edge",
        ("edge", "microsoft edge"),
        "msedge.exe",
        (r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",),
    ),
    AppSpec(
        "firefox",
        ("firefox", "mozilla firefox"),
        "firefox.exe",
        (r"%ProgramFiles%\Mozilla Firefox\firefox.exe",),
    ),
    AppSpec("calculator", ("calculator", "calc"), "calc.exe"),
    AppSpec("explorer", ("file explorer", "explorer", "windows explorer"), "explorer.exe"),
    AppSpec("paint", ("paint", "ms paint"), "mspaint.exe"),
    AppSpec("task manager", ("task manager",), "taskmgr.exe"),
    AppSpec("word", ("word", "microsoft word", "ms word"), "WINWORD.EXE"),
    AppSpec("excel", ("excel", "microsoft excel", "ms excel"), "EXCEL.EXE"),
    AppSpec("powerpoint", ("powerpoint", "microsoft powerpoint", "power point"), "POWERPNT.EXE"),
)

_NAME_RE = re.compile(r"^[\w .+#&'-]{1,64}$")


def clean_app_name(name: str) -> str:
    return " ".join(name.lower().split())


def is_valid_app_name(name: object) -> bool:
    return isinstance(name, str) and bool(_NAME_RE.match(name.strip()))


@dataclass(frozen=True)
class AppMatch:
    key: str
    path: str | None  # None = known app, but not found on this PC


def _registry_app_path(exe: str) -> str | None:
    if sys.platform != "win32":
        return None
    import winreg

    sub = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, sub) as key:
                value, _ = winreg.QueryValueEx(key, None)
                value = str(value).strip().strip('"')
                if value and Path(value).is_file():
                    return value
        except OSError:
            continue
    return None


def _which(exe: str) -> str | None:
    return shutil.which(exe)


class AppResolver:
    """Maps spoken names to executables. `registry` and `which` are injectable for tests."""

    def __init__(
        self,
        settings_getter: Callable[[], Settings],
        registry: Callable[[str], str | None] = _registry_app_path,
        which: Callable[[str], str | None] = _which,
        search_install_dirs: bool = True,
    ):
        self._settings = settings_getter
        self._search_install_dirs = search_install_dirs
        self._registry = registry
        self._which = which

    def known_names(self) -> set[str]:
        names = {a for spec in BUILTIN_APPS for a in spec.aliases}
        names |= set(self._settings().custom_apps)
        return names

    def lookup(self, spoken: str) -> AppMatch | None:
        """None = never heard of that app. AppMatch.path None = known but not installed."""
        name = clean_app_name(spoken)
        custom = self._settings().custom_apps.get(name)
        if custom:
            ok = Path(os.path.expandvars(custom)).is_file()
            return AppMatch(name, os.path.expandvars(custom) if ok else None)
        for spec in BUILTIN_APPS:
            if name in spec.aliases or name == spec.key:
                return AppMatch(spec.key, self._find(spec))
        return None

    def find_key(self, key: str) -> str | None:
        """Resolve a built-in app by key (used to pick the browser)."""
        for spec in BUILTIN_APPS:
            if spec.key == key:
                return self._find(spec)
        return None

    def _find(self, spec: AppSpec) -> str | None:
        on_path = self._which(spec.exe)  # first: system apps live in System32, not in the Store folder
        if on_path:
            return on_path
        found = self._registry(spec.exe)
        if found:
            return found
        if spec.key == "vscode":  # `code` on PATH is a .cmd shim; the real exe is two levels up
            shim = self._which("code")
            if shim:
                real = Path(shim).resolve().parent.parent / "Code.exe"
                if real.is_file():
                    return str(real)
        for template in spec.install_paths if self._search_install_dirs else ():
            expanded = os.path.expandvars(template)
            if "%" not in expanded and Path(expanded).is_file():
                return expanded
        return None
