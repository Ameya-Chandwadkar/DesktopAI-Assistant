"""Composition root: builds the object graph and starts Qt."""

from __future__ import annotations

import logging
import sys

from ..actions.apps import AppResolver
from ..actions.engine import ActionEngine
from ..actions.system import WindowsSystem
from ..config import SettingsStore
from ..controller import Assistant
from ..db import Database
from ..nlu.parser import LocalParser

log = logging.getLogger("nova")


def build_assistant(db: Database, store: SettingsStore) -> tuple[Assistant, ActionEngine]:
    apps = AppResolver(store.get)
    engine = ActionEngine(store.get, WindowsSystem(), apps)
    parser = LocalParser(apps.known_names, lambda: store.get().custom_sites)
    return Assistant(engine, parser, db, store.get), engine


def run() -> int:
    from PySide6.QtWidgets import QApplication

    from . import theme
    from .main_window import MainWindow

    db = Database()
    store = SettingsStore(db)
    assistant, _ = build_assistant(db, store)

    app = QApplication(sys.argv)
    app.setApplicationName("NOVA")
    app.setStyleSheet(theme.STYLESHEET)
    window = MainWindow(assistant, store, db)
    window.show()
    log.info("NOVA started")
    code = app.exec()
    db.close()
    return code
