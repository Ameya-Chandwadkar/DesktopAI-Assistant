"""Logging setup. Logs record what happened, not what was said or opened."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from . import paths

_configured = False


def setup_logging(level: str = "INFO") -> None:
    global _configured
    root = logging.getLogger("nova")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    if _configured:
        return
    handler = RotatingFileHandler(
        paths.logs_dir() / "nova.log", maxBytes=512_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    if sys.stderr is not None:  # pythonw.exe (no console) has no stderr
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(console)
    def _log_uncaught(exc_type, exc, tb):  # pythonw.exe shows no traceback, so record it
        root.critical("uncaught exception", exc_info=(exc_type, exc, tb))

    sys.excepthook = _log_uncaught
    _configured = True
