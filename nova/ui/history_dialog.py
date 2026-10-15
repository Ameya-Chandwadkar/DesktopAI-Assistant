"""Command history viewer."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..db import Database


class HistoryDialog(QDialog):
    rerun = Signal(str)

    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(parent)
        self._db = db
        self.setWindowTitle("Command history")
        self.setMinimumSize(640, 380)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Time", "Via", "You said", "Action", "Result"])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemDoubleClicked.connect(lambda _: self._rerun())
        self.empty = QLabel("No commands yet.")
        run, clear, close = QPushButton("Run again"), QPushButton("Clear history…"), QPushButton("Close")
        run.clicked.connect(self._rerun)
        clear.clicked.connect(self._clear)
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addWidget(run)
        row.addWidget(clear)
        row.addStretch()
        row.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addWidget(self.table)
        lay.addWidget(self.empty)
        lay.addLayout(row)
        self._load()

    def _load(self) -> None:
        entries = self._db.recent_history()
        self.table.setRowCount(0)
        for e in entries:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, text in enumerate((e.ts.replace("T", " "), e.source, e.heard, e.action.replace("_", " "), e.message)):
                self.table.setItem(r, c, QTableWidgetItem(text))
        self.empty.setVisible(not entries)
        self.table.setVisible(bool(entries))

    def _rerun(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self.rerun.emit(self.table.item(rows[0].row(), 2).text())
            self.accept()

    def _clear(self) -> None:
        if QMessageBox.question(self, "Clear history", "Delete all saved command history?") == QMessageBox.Yes:
            self._db.clear_history()
            self._load()
