"""Headless UI checks (Qt 'offscreen' platform). These prove the wiring, NOT how it looks or sounds on a real screen."""

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from nova.config import SettingsStore  # noqa: E402
from nova.ui import theme  # noqa: E402
from nova.ui.history_dialog import HistoryDialog  # noqa: E402
from nova.ui.main_window import MainWindow  # noqa: E402
from nova.ui.settings_dialog import SettingsDialog  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(theme.STYLESHEET)
    return app


def wait_for(qapp, cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def window(qapp, assistant, db, settings):
    store = SettingsStore(db)
    store.update(settings)  # same folders as the assistant's engine
    w = MainWindow(assistant, store, db)
    w.show()
    yield w
    w.close()


def type_command(w, qapp, text):
    w._input.setText(text)
    w._on_text_entered()
    assert wait_for(qapp, lambda: w._input.isEnabled() and w._action.text() != "Working…")


def test_window_flags_and_missing_model(qapp, window):
    assert window.windowFlags() & Qt.WindowStaysOnTopHint
    assert window.windowFlags() & Qt.FramelessWindowHint
    assert wait_for(qapp, lambda: "no speech model found" in window._status.text().lower())
    assert not window._mic.isEnabled()


def test_text_command_opens_youtube(qapp, window, system):
    type_command(window, qapp, "search youtube for lo-fi")
    assert "lo-fi" in system.urls[0]
    assert "Opened" in window._result.text() and "open youtube" in window._action.text()
    assert "lo-fi" in window._heard.text()


def test_unknown_command_message(qapp, window):
    type_command(window, qapp, "dance for me")
    assert "didn't understand" in window._result.text()


def test_ambiguous_files_then_click(qapp, window, system):
    type_command(window, qapp, "find re")
    assert not window._choices.isHidden() and window._choices.count() >= 2
    window._on_choice_clicked(window._choices.item(0))
    assert wait_for(qapp, lambda: "Opened" in window._result.text())
    assert len(system.opened_paths) == 1 and window._choices.isHidden()


def test_ambiguous_files_then_spoken_number(qapp, window, system):
    type_command(window, qapp, "find re")
    type_command(window, qapp, "number two")
    assert len(system.opened_paths) == 1


def test_history_dialog_lists_commands(qapp, window, db):
    type_command(window, qapp, "open youtube")
    dlg = HistoryDialog(db)
    assert dlg.table.rowCount() == 1 and dlg.table.item(0, 2).text() == "open youtube"
    got = []
    dlg.rerun.connect(got.append)
    dlg.table.selectRow(0)
    dlg._rerun()
    assert got == ["open youtube"]


def test_always_on_top_toggle(qapp, window):
    s = window._store.get()
    s.always_on_top = False
    window._store.update(s)
    window.apply_settings()
    assert not window.windowFlags() & Qt.WindowStaysOnTopHint


def test_settings_dialog_roundtrip_and_validation(qapp, settings):
    dlg = SettingsDialog(settings)
    assert dlg._collect() == settings  # untouched dialog changes nothing
    dlg.browser.setCurrentText("edge")
    from nova.ui.settings_dialog import _add_row

    _add_row(dlg.sites, "portal", "javascript:alert(1)")
    with pytest.raises(ValueError):
        dlg._collect()
    dlg.sites.item(0, 1).setText("portal.example.edu")
    out = dlg._collect()
    assert out.browser == "edge" and out.custom_sites == {"portal": "https://portal.example.edu"}


def test_settings_dialog_rejects_missing_app(qapp, settings):
    from nova.ui.settings_dialog import _add_row

    dlg = SettingsDialog(settings)
    _add_row(dlg.apps, "ghost", "C:\\nope\\ghost.exe")
    with pytest.raises(ValueError):
        dlg._collect()
