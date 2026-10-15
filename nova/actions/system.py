"""The only module that actually touches the OS. Swapped for a fake in tests.

Everything is launched with an argument list - never through a shell - so
spoken text can never be interpreted as a command line.
"""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from typing import Protocol, Sequence


class SystemOps(Protocol):
    def open_path(self, path: str) -> None: ...
    def launch(self, exe: str, args: Sequence[str] = ()) -> None: ...
    def open_url_default(self, url: str) -> None: ...


class WindowsSystem:
    def open_path(self, path: str) -> None:
        """Open a file with its default application (like double-clicking it)."""
        if sys.platform != "win32":
            raise OSError("Opening files is only supported on Windows.")
        os.startfile(path)  # noqa: S606 - path is validated by the engine first

    def launch(self, exe: str, args: Sequence[str] = ()) -> None:
        if exe.lower().endswith(".lnk") and not args:
            self.open_path(exe)
            return
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        subprocess.Popen(  # noqa: S603 - list args, shell=False
            [exe, *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=flags,
        )

    def open_url_default(self, url: str) -> None:
        if not webbrowser.open(url):
            raise OSError("No default web browser could be opened.")
