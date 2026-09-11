"""Application style sheet and the palette shared by widgets that paint themselves.

The dark theme matches the video view: near-black grounds, grey text and a blue accent
for checked and primary controls, with red for an active recording.
"""

from __future__ import annotations

from typing import Final

ACCENT: Final = "#3b6fd6"
ACCENT_HOVER: Final = "#4d7fe0"
RECORD_RED: Final = "#d84a3f"
BACKGROUND: Final = "#1b1c1f"
PANEL_BACKGROUND: Final = "#17181b"
GROUP_BACKGROUND: Final = "#212226"
BORDER: Final = "#2f3136"
CONTROL: Final = "#2c2e33"
CONTROL_BORDER: Final = "#3a3d44"
TEXT: Final = "#e8e8ea"
MUTED_TEXT: Final = "#9aa0a6"
DISABLED_TEXT: Final = "#6b6f78"
ERROR_TEXT: Final = "#ff5a3c"
LINK_TEXT: Final = "#4c8dff"
QR_DARK: Final = "black"
QR_LIGHT: Final = "white"

AI_PANEL_STYLE: Final = (
    f"QTextBrowser {{ background: {PANEL_BACKGROUND}; border: 1px solid {BORDER}; "
    "border-radius: 6px; padding: 6px; }"
)
DIVIDER_STYLE: Final = f"color: {BORDER};"

STYLE_SHEET: Final = f"""
QMainWindow, QWidget {{ background: {BACKGROUND}; color: {TEXT}; font-size: 13px; }}
QDialog {{ background: {BACKGROUND}; }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 8px; margin-top: 14px;
             padding: 8px 8px 4px 8px; background: {GROUP_BACKGROUND}; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px;
                    color: {MUTED_TEXT}; font-size: 11px; font-weight: 600;
                    letter-spacing: 1px; }}
QPushButton {{ background: {CONTROL}; border: 1px solid {CONTROL_BORDER};
               border-radius: 6px; padding: 6px 10px; }}
QPushButton:hover {{ background: #363940; }}
QPushButton:pressed {{ background: #24262a; }}
QPushButton:disabled {{ color: {DISABLED_TEXT}; }}
QPushButton:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: white; }}
QPushButton#record:checked {{ background: {RECORD_RED}; border-color: {RECORD_RED}; }}
QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; color: white;
                       font-weight: 600; }}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QSlider::groove:horizontal {{ height: 4px; background: {CONTROL_BORDER};
                              border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 14px; height: 14px; margin: -6px 0;
                              background: {TEXT}; border-radius: 7px; }}
QSlider::handle:horizontal:hover {{ background: white; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px;
                        border: 1px solid #4a4d55; background: {CONTROL}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QComboBox, QSpinBox {{ background: {CONTROL}; border: 1px solid {CONTROL_BORDER};
                       border-radius: 6px; padding: 5px 8px; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {CONTROL};
                               selection-background-color: {ACCENT};
                               border: 1px solid {CONTROL_BORDER}; }}
QListWidget {{ background: {BACKGROUND}; border: 1px solid {BORDER};
               border-radius: 6px; }}
QListWidget::item:selected {{ background: {ACCENT}; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {MUTED_TEXT}; padding: 7px 10px;
                border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QStatusBar {{ background: {PANEL_BACKGROUND}; color: {MUTED_TEXT}; }}
QStatusBar::item {{ border: none; }}
QMenu {{ background: #26272b; border: 1px solid {CONTROL_BORDER}; }}
QMenu::item:selected {{ background: {ACCENT}; }}
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: {CONTROL_BORDER}; border-radius: 4px;
                               min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QLabel#muted {{ color: {MUTED_TEXT}; }}
QLabel#small {{ color: {MUTED_TEXT}; font-size: 11px; }}
"""
