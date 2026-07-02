#!/usr/bin/env python3
"""One light theme for every mycat dialog.

Applied via ``dialog.setStyleSheet(LIGHT_QSS)`` so LLM, GitHub, Calendar,
Activity and Reminder windows all share the same look instead of each one
falling back to whatever the system theme happens to be.
"""

LIGHT_QSS = (
    "QDialog { background: #ffffff; color: #1c1c1c; }"
    "QLabel, QCheckBox, QGroupBox { color: #1c1c1c; background: transparent; }"
    "QLineEdit, QSpinBox, QComboBox {"
    " color: #1c1c1c; background: #ffffff;"
    " border: 1px solid #c0c0c0; border-radius: 4px; padding: 3px 5px;"
    " selection-color: white; selection-background-color: #ff6f91; }"
    "QLineEdit:read-only { background: #f3f3f3; color: #666666; }"
    "QComboBox QAbstractItemView {"
    " color: #1c1c1c; background: #ffffff;"
    " selection-color: white; selection-background-color: #ff6f91; }"
    "QPushButton {"
    " color: #1c1c1c; background: #f0f0f0;"
    " border: 1px solid #c0c0c0; border-radius: 4px; padding: 5px 14px; }"
    "QPushButton:hover { background: #e7e7e7; }"
    "QPushButton:disabled { color: #9a9a9a; background: #f5f5f5; }"
    "QTableWidget {"
    " background: #ffffff; color: #1c1c1c;"
    " gridline-color: #e6e6e6; border: 1px solid #d0d0d0; }"
    "QHeaderView::section {"
    " background: #f0f0f0; color: #1c1c1c;"
    " border: none; border-bottom: 1px solid #d0d0d0; padding: 4px 6px; }"
    "QListWidget { background: #ffffff; color: #1c1c1c; border: 1px solid #d0d0d0; }"
    "QTimeEdit, QDateTimeEdit, QTextEdit, QPlainTextEdit {"
    " color: #1c1c1c; background: #ffffff;"
    " border: 1px solid #c0c0c0; border-radius: 4px; padding: 3px 5px; }"
)

__all__ = ["LIGHT_QSS"]
