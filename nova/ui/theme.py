"""Dark theme."""

BG = "#14161c"
SURFACE = "#1e212b"
SURFACE_HOVER = "#272b38"
BORDER = "#2c3040"
TEXT = "#e6e8ee"
MUTED = "#8b90a0"
ACCENT = "#6c8cff"
OK = "#4cd08a"
WARN = "#f0b455"
DANGER = "#ff5d6c"

STATUS_COLORS = {
    "ok": OK,
    "needs_choice": ACCENT,
    "needs_confirmation": WARN,
    "not_found": WARN,
    "unknown": MUTED,
    "invalid": DANGER,
    "error": DANGER,
}

STYLESHEET = f"""
* {{ font-family: "Segoe UI", sans-serif; font-size: 13px; color: {TEXT}; }}
QFrame#card {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 14px; }}
QLabel#title {{ font-weight: 600; font-size: 13px; letter-spacing: 1px; }}
QLabel#heard {{ color: {MUTED}; font-style: italic; }}
QLabel#action {{ color: {ACCENT}; font-weight: 600; }}
QLabel#result {{ color: {TEXT}; }}
QLabel#muted {{ color: {MUTED}; }}
QPushButton#bar {{ background: transparent; border: none; border-radius: 6px; color: {MUTED}; padding: 0;
                   min-width: 28px; max-width: 28px; min-height: 24px; max-height: 24px; font-size: 14px; }}
QPushButton#bar:hover {{ background: {SURFACE_HOVER}; color: {TEXT}; }}
QPushButton#mic {{ background: {ACCENT}; border: none; padding: 0; border-radius: 26px; min-width: 52px; max-width: 52px;
                   min-height: 52px; max-height: 52px; font-size: 20px; color: white; }}
QPushButton#mic:hover {{ background: #839dff; }}
QPushButton#mic:disabled {{ background: {SURFACE}; color: {MUTED}; }}
QPushButton#mic[recording="true"] {{ background: {DANGER}; }}
QLineEdit, QPlainTextEdit, QComboBox, QTableWidget, QListWidget {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 8px;
    selection-background-color: {ACCENT}; }}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
QListWidget::item {{ padding: 6px 4px; border-radius: 6px; }}
QListWidget::item:hover, QListWidget::item:selected {{ background: {SURFACE_HOVER}; }}
QPushButton {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 12px; }}
QPushButton:hover {{ background: {SURFACE_HOVER}; }}
QPushButton#primary {{ background: {ACCENT}; border: none; color: white; }}
QDialog {{ background: {BG}; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; }}
QTabBar::tab {{ background: transparent; padding: 7px 14px; color: {MUTED}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QHeaderView::section {{ background: {SURFACE}; color: {MUTED}; border: none; padding: 5px; }}
QCheckBox {{ spacing: 8px; }}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 20px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""
