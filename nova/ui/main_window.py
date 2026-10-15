"""The floating NOVA panel."""

from __future__ import annotations

import logging

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from ..actions.models import Status
from ..config import Settings, SettingsStore
from ..controller import Assistant, Outcome
from ..db import Database
from ..speech.mic import MicCapture
from ..speech.ptt import PushToTalk
from ..speech.vosk_backend import SpeechError, VoskRecognizer, find_model
from . import theme
from .history_dialog import HistoryDialog
from .settings_dialog import SettingsDialog
from .workers import SpeechBridge, run_in_background

log = logging.getLogger("nova.ui")

WIDTH = 380
POS_PREF = "window_pos"


class MainWindow(QWidget):
    def __init__(self, assistant: Assistant, store: SettingsStore, db: Database):
        super().__init__()
        self._assistant, self._store, self._db = assistant, store, db
        self._recognizer: VoskRecognizer | None = None
        self._ptt: PushToTalk | None = None
        self._bridge = SpeechBridge()
        self._speech_ready = False
        self._holding = False

        self.setWindowTitle("NOVA")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(WIDTH)
        self._build_ui()
        self._wire_speech_signals()
        self.apply_settings(first=True)
        self._restore_position()
        self._pos_timer = QTimer(self, singleShot=True, interval=500, timeout=self._save_position)
        QTimer.singleShot(0, self._load_speech)

    # ---- construction ---------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame(objectName="card")
        outer.addWidget(card)
        col = QVBoxLayout(card)
        col.setContentsMargins(14, 8, 14, 14)
        col.setSpacing(8)

        # title bar (drag handle + window buttons)
        self._bar = QWidget()
        bar = QHBoxLayout(self._bar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(2)
        self._dot = QLabel("●")
        self._dot.setStyleSheet(f"color: {theme.MUTED}; font-size: 10px;")
        title = QLabel("NOVA", objectName="title")
        bar.addWidget(self._dot)
        bar.addWidget(title)
        bar.addStretch()
        for text, tip, slot, name in (
            ("≡", "Command history", self._show_history, "bar"),
            ("⚙", "Settings", self._show_settings, "bar"),
            ("–", "Minimize", self.showMinimized, "bar"),
            ("✕", "Close", self.close, "bar"),
        ):
            b = QPushButton(text, objectName=name, toolTip=tip, cursor=Qt.PointingHandCursor)
            if text == "✕":
                b.setStyleSheet(f"QPushButton:hover {{ background: {theme.DANGER}; color: white; }}")
            b.clicked.connect(slot)
            bar.addWidget(b)
        col.addWidget(self._bar)

        self._heard = QLabel("Hold the mic and speak, or type a command.", objectName="heard", wordWrap=True)
        self._action = QLabel("", objectName="action", wordWrap=True)
        self._result = QLabel("", objectName="result", wordWrap=True)
        for w in (self._heard, self._action, self._result):
            col.addWidget(w)

        self._choices = QListWidget()
        self._choices.setVisible(False)
        self._choices.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._choices.setTextElideMode(Qt.ElideMiddle)
        self._choices.itemClicked.connect(self._on_choice_clicked)
        col.addWidget(self._choices)

        row = QHBoxLayout()
        row.setSpacing(10)
        self._input = QLineEdit(placeholderText="Type a command…")
        self._input.returnPressed.connect(self._on_text_entered)
        self._mic = QPushButton("🎤", objectName="mic", cursor=Qt.PointingHandCursor)
        self._mic.setProperty("recording", False)
        self._mic.pressed.connect(self._mic_pressed)
        self._mic.released.connect(self._mic_released)
        row.addWidget(self._input, 1)
        row.addWidget(self._mic)
        col.addLayout(row)
        self._status = QLabel("", objectName="muted", wordWrap=True)
        col.addWidget(self._status)

    def _wire_speech_signals(self) -> None:
        b = self._bridge
        b.listening.connect(self._on_listening)
        b.partial.connect(lambda t: self._heard.setText(f"“{t}…”"))
        b.final.connect(self._on_speech_final)
        b.error.connect(self._on_speech_error)

    # ---- window behaviour ---------------------------------------------
    def apply_settings(self, first: bool = False) -> None:
        s = self._store.get()
        was_visible = self.isVisible()
        flags = Qt.Window | Qt.FramelessWindowHint
        if s.always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        if was_visible and not first:
            self.show()  # changing flags hides the window

    def mousePressEvent(self, e) -> None:
        """Drag the panel from anywhere that isn't a control."""
        if e.button() == Qt.LeftButton and self.windowHandle() is not None:
            w = self.childAt(e.position().toPoint())
            while w is not None and w is not self:
                if isinstance(w, (QPushButton, QLineEdit, QListWidget)):
                    break
                w = w.parentWidget()
            else:
                self.windowHandle().startSystemMove()
        super().mousePressEvent(e)

    def moveEvent(self, e) -> None:
        super().moveEvent(e)
        if hasattr(self, "_pos_timer"):
            self._pos_timer.start()

    def _save_position(self) -> None:
        self._db.set_pref(POS_PREF, [self.x(), self.y()])

    def _restore_position(self) -> None:
        saved = self._db.get_pref(POS_PREF)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        if isinstance(saved, list) and len(saved) == 2:
            x, y = saved
            for sc in QGuiApplication.screens():  # only trust it if it's still on a connected screen
                if sc.availableGeometry().contains(QPoint(x + 40, y + 20)):
                    self.move(x, y)
                    return
        self.move(screen.right() - WIDTH - 24, screen.top() + 60)

    def closeEvent(self, e) -> None:
        if self._ptt:
            self._ptt.stop()
        self._save_position()
        super().closeEvent(e)

    # ---- speech ---------------------------------------------------------
    def _load_speech(self) -> None:
        s = self._store.get()
        model = find_model(s.vosk_model_path)
        if model is None:
            self._set_mic_unavailable(
                "Speech model not found - typing still works. Run: python -m nova --download-model small, then restart NOVA."
            )
            return
        self._mic.setEnabled(False)
        self._status.setText("Loading speech model…")
        rec = VoskRecognizer(model)

        def load():
            rec.load()
            return rec

        run_in_background(load, self._on_model_loaded, self._on_model_failed)

    def _on_model_loaded(self, rec: VoskRecognizer) -> None:
        self._recognizer = rec
        self._speech_ready = True
        self._mic.setEnabled(True)
        self._status.setText("")
        self._dot.setStyleSheet(f"color: {theme.OK}; font-size: 10px;")
        self._mic.setToolTip("Hold to talk")

    def _on_model_failed(self, msg: str) -> None:
        self._set_mic_unavailable(msg or "The speech model couldn't be loaded.")

    def _set_mic_unavailable(self, why: str) -> None:
        self._speech_ready = False
        self._mic.setEnabled(False)
        self._mic.setToolTip(why)
        self._status.setText(why)

    def _new_ptt(self) -> PushToTalk:
        mic_name = self._store.get().microphone
        b = self._bridge
        return PushToTalk(
            self._recognizer,
            lambda: MicCapture(mic_name),
            on_listening=b.listening.emit,
            on_partial=b.partial.emit,
            on_final=b.final.emit,
            on_error=b.error.emit,
        )

    def _mic_pressed(self) -> None:
        if not self._speech_ready or self._recognizer is None:
            return
        self._ptt = self._ptt if self._ptt and not self._ptt.busy else self._new_ptt()
        if self._ptt.start():
            self._holding = True
            self._result.setText("")
            self._action.setText("")
            self._status.setText("Starting microphone…")

    def _mic_released(self) -> None:
        if self._holding and self._ptt:
            self._holding = False
            self._ptt.stop()
            self._set_recording(False)
            self._status.setText("Recognising…")

    def _on_listening(self) -> None:
        if self._holding:
            self._set_recording(True)
            self._heard.setText("Listening…")
            self._status.setText("Release the button when you're done.")

    def _set_recording(self, on: bool) -> None:
        self._mic.setProperty("recording", on)
        self._mic.style().unpolish(self._mic)
        self._mic.style().polish(self._mic)

    def _on_speech_final(self, text: str) -> None:
        self._status.setText("")
        self._heard.setText(f"“{text}”")
        self._run_command(text, "voice")

    def _on_speech_error(self, msg: str) -> None:
        self._holding = False
        self._set_recording(False)
        self._status.setText("")
        self._heard.setText("Didn't catch that.")
        self._show_message(msg, Status.ERROR)

    # ---- running commands -------------------------------------------------
    def _on_text_entered(self) -> None:
        text = self._input.text().strip()
        if text:
            self._input.clear()
            self._heard.setText(f"“{text}”")
            self._run_command(text, "text")

    def _run_command(self, text: str, source: str) -> None:
        self._action.setText("Working…")
        self._input.setEnabled(False)
        run_in_background(lambda: self._assistant.submit(text, source), self._show_outcome, self._on_task_failed)

    def _on_choice_clicked(self, item: QListWidgetItem) -> None:
        row = self._choices.row(item)
        self._action.setText("Opening…")
        run_in_background(lambda: self._assistant.choose(row, "click"), self._show_outcome, self._on_task_failed)

    def _on_task_failed(self, msg: str) -> None:
        self._input.setEnabled(True)
        self._show_message(f"Unexpected error: {msg}", Status.ERROR)

    def _show_outcome(self, outcome: Outcome) -> None:
        self._input.setEnabled(True)
        self._input.setFocus()
        if outcome.heard:
            self._heard.setText(f"“{outcome.heard}”")
        self._action.setText(f"▶ {outcome.action.describe()}" if outcome.action else "")
        self._show_message(outcome.result.message, outcome.result.status)
        self._choices.clear()
        for c in outcome.result.choices:
            item = QListWidgetItem(f"{c.label}\n{c.detail}")
            item.setToolTip(c.path)
            self._choices.addItem(item)
        self._choices.setFixedHeight(min(190, 52 * self._choices.count() + 8))
        self._choices.setVisible(bool(outcome.result.choices))
        self.adjustSize()

    def _show_message(self, msg: str, status: Status) -> None:
        color = theme.STATUS_COLORS.get(status.value, theme.TEXT)
        self._result.setStyleSheet(f"color: {color};")
        self._result.setText(msg)
        self.adjustSize()

    # ---- dialogs ------------------------------------------------------------
    def _show_history(self) -> None:
        dlg = HistoryDialog(self._db, self)
        dlg.rerun.connect(lambda text: (self._heard.setText(f"“{text}”"), self._run_command(text, "history")))
        dlg.exec()

    def _show_settings(self) -> None:
        dlg = SettingsDialog(self._store.get(), self)
        if dlg.exec():
            old = self._store.get()
            new = dlg.result_settings()
            self._store.update(new)
            self.apply_settings()
            if (new.vosk_model_path, new.microphone) != (old.vosk_model_path, old.microphone):
                self._ptt = None  # next press picks up the new mic
                if new.vosk_model_path != old.vosk_model_path:
                    self._load_speech()
