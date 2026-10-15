"""Run blocking work (file search, model loading) off the UI thread."""

from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

log = logging.getLogger("nova.ui")


class _Signals(QObject):
    finished = Signal(object)  # result of fn
    failed = Signal(str)


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], Any]):
        super().__init__()
        self.fn = fn
        self.signals = _Signals()

    def run(self) -> None:
        try:
            self.signals.finished.emit(self.fn())
        except Exception as e:
            log.exception("background task failed")
            self.signals.failed.emit(str(e))


def run_in_background(fn: Callable[[], Any], on_done: Callable[[Any], None], on_fail: Callable[[str], None]) -> None:
    task = _Task(fn)
    task.signals.finished.connect(on_done)
    task.signals.failed.connect(on_fail)
    QThreadPool.globalInstance().start(task)


class SpeechBridge(QObject):
    """Turns push-to-talk worker-thread callbacks into thread-safe Qt signals."""

    listening = Signal()
    partial = Signal(str)
    final = Signal(str)
    error = Signal(str)
