"""Settings window: machine-specific configuration lives here, not in code."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget, QHeaderView,
)

from ..actions.apps import is_valid_app_name
from ..actions.web import UrlError, validate_url
from ..config import BROWSERS, Settings
from ..speech.mic import list_input_devices
from ..speech.vosk_backend import find_model

DEFAULT_MIC = "System default"


def _table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    t.verticalHeader().setVisible(False)
    t.setSelectionBehavior(QTableWidget.SelectRows)
    return t


def _fill(table: QTableWidget, mapping: dict[str, str]) -> None:
    for k, v in mapping.items():
        _add_row(table, k, v)


def _add_row(table: QTableWidget, a: str = "", b: str = "") -> None:
    r = table.rowCount()
    table.insertRow(r)
    table.setItem(r, 0, QTableWidgetItem(a))
    table.setItem(r, 1, QTableWidgetItem(b))


def _rows(table: QTableWidget) -> list[tuple[str, str]]:
    out = []
    for r in range(table.rowCount()):
        a = (table.item(r, 0).text() if table.item(r, 0) else "").strip()
        b = (table.item(r, 1).text() if table.item(r, 1) else "").strip()
        if a or b:
            out.append((a, b))
    return out


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("NOVA settings")
        self.setMinimumSize(520, 460)
        self._orig = settings
        tabs = QTabWidget()
        tabs.addTab(self._general_tab(settings), "General")
        tabs.addTab(self._folders_tab(settings), "Folders")
        tabs.addTab(self._apps_tab(settings), "Apps && sites")
        tabs.addTab(self._speech_tab(settings), "Speech")
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setObjectName("primary")
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(buttons)

    # ---- tabs ---------------------------------------------------------------
    def _general_tab(self, s: Settings) -> QWidget:
        w, form = QWidget(), QFormLayout()
        w.setLayout(form)
        self.on_top = QCheckBox("Keep NOVA above other windows")
        self.on_top.setChecked(s.always_on_top)
        self.history_on = QCheckBox("Save command history on this PC")
        self.history_on.setChecked(s.history_enabled)
        self.browser = QComboBox()
        self.browser.addItems(BROWSERS)
        self.browser.setCurrentText(s.browser)
        form.addRow(self.on_top)
        form.addRow(self.history_on)
        form.addRow("Browser for web commands", self.browser)
        form.addRow(QLabel("'default' uses your Windows default browser. If the chosen browser\nisn't installed, NOVA falls back to the default."))
        return w

    def _folders_tab(self, s: Settings) -> QWidget:
        w, lay = QWidget(), QVBoxLayout()
        w.setLayout(lay)
        lay.addWidget(QLabel("NOVA only searches and opens documents inside these folders.\nAdding a folder is how you authorise access to it."))
        self.folders = QListWidget()
        self.folders.addItems(s.search_roots)
        row = QHBoxLayout()
        add, rem = QPushButton("Add folder…"), QPushButton("Remove selected")
        add.clicked.connect(self._add_folder)
        rem.clicked.connect(lambda: [self.folders.takeItem(self.folders.row(i)) for i in self.folders.selectedItems()])
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch()
        lay.addWidget(self.folders)
        lay.addLayout(row)
        return w

    def _apps_tab(self, s: Settings) -> QWidget:
        w, lay = QWidget(), QVBoxLayout()
        w.setLayout(lay)
        lay.addWidget(QLabel("Custom apps: say 'open <name>' to launch the .exe or shortcut."))
        self.apps = _table(["Spoken name", "Path to .exe / .lnk"])
        _fill(self.apps, s.custom_apps)
        r1 = QHBoxLayout()
        add_app, rem_app = QPushButton("Add app…"), QPushButton("Remove selected")
        add_app.clicked.connect(self._add_app)
        rem_app.clicked.connect(lambda: self._remove_rows(self.apps))
        r1.addWidget(add_app)
        r1.addWidget(rem_app)
        r1.addStretch()
        lay.addWidget(self.apps)
        lay.addLayout(r1)
        lay.addWidget(QLabel("Custom sites: say 'open <name>' to open the address."))
        self.sites = _table(["Spoken name", "Address (https://…)"])
        _fill(self.sites, s.custom_sites)
        r2 = QHBoxLayout()
        add_site, rem_site = QPushButton("Add site"), QPushButton("Remove selected")
        add_site.clicked.connect(lambda: _add_row(self.sites))
        rem_site.clicked.connect(lambda: self._remove_rows(self.sites))
        r2.addWidget(add_site)
        r2.addWidget(rem_site)
        r2.addStretch()
        lay.addWidget(self.sites)
        lay.addLayout(r2)
        return w

    def _speech_tab(self, s: Settings) -> QWidget:
        w, form = QWidget(), QFormLayout()
        w.setLayout(form)
        self.mic = QComboBox()
        names = list(dict.fromkeys(list_input_devices()))  # same device appears once per audio API
        self.mic.addItem(DEFAULT_MIC)
        self.mic.addItems(names)
        if s.microphone:
            match = next((n for n in names if s.microphone.lower() in n.lower()), None)
            if match is None:
                self.mic.addItem(s.microphone)
                match = s.microphone
            self.mic.setCurrentText(match)
        self.model = QLineEdit(s.vosk_model_path)
        self.model.setPlaceholderText("Leave empty to auto-detect")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_model)
        mrow = QHBoxLayout()
        mrow.addWidget(self.model, 1)
        mrow.addWidget(browse)
        found = find_model(s.vosk_model_path)
        self.model_status = QLabel(f"Using: {found}" if found else "No speech model found - run: python -m nova --download-model small")
        self.model_status.setWordWrap(True)
        form.addRow("Microphone", self.mic)
        form.addRow("Vosk model folder", mrow)
        form.addRow(self.model_status)
        form.addRow(QLabel("Changing the model folder reloads speech recognition; a new microphone applies on the next press."))
        return w

    # ---- actions --------------------------------------------------------
    def _add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose a folder NOVA may search")
        if d and d not in [self.folders.item(i).text() for i in range(self.folders.count())]:
            self.folders.addItem(str(Path(d)))

    def _add_app(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Choose an application", "", "Applications (*.exe *.lnk)")
        if f:
            _add_row(self.apps, Path(f).stem.lower(), str(Path(f)))

    def _browse_model(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose the Vosk model folder")
        if d:
            self.model.setText(str(Path(d)))

    @staticmethod
    def _remove_rows(table: QTableWidget) -> None:
        for r in sorted({i.row() for i in table.selectedItems()}, reverse=True):
            table.removeRow(r)

    def _try_accept(self) -> None:
        try:
            self._result = self._collect()
        except ValueError as e:
            QMessageBox.warning(self, "Check your settings", str(e))
            return
        self.accept()

    def _collect(self) -> Settings:
        apps = {}
        for name, path in _rows(self.apps):
            if not is_valid_app_name(name) or not path:
                raise ValueError(f"'{name}' needs a simple spoken name and a path.")
            if not Path(path).is_file() or Path(path).suffix.lower() not in (".exe", ".lnk"):
                raise ValueError(f"'{path}' isn't an existing .exe or .lnk file.")
            apps[name.lower()] = path
        sites = {}
        for name, url in _rows(self.sites):
            if not is_valid_app_name(name):
                raise ValueError(f"'{name}' needs a simple spoken name.")
            try:
                sites[name.lower()] = validate_url(url)
            except UrlError as e:
                raise ValueError(f"Site '{name}': {e}")
        mic = self.mic.currentText()
        return replace(
            self._orig,
            always_on_top=self.on_top.isChecked(),
            history_enabled=self.history_on.isChecked(),
            browser=self.browser.currentText(),
            search_roots=[self.folders.item(i).text() for i in range(self.folders.count())],
            custom_apps=apps,
            custom_sites=sites,
            microphone="" if mic == DEFAULT_MIC else mic,
            vosk_model_path=self.model.text().strip(),
        )

    def result_settings(self) -> Settings:
        return self._result
