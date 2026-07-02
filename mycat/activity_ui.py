#!/usr/bin/env python3
"""Activity diary dialog: opt-in switches, the interval log, day totals.

The log speaks in honest wording ("away from the computer", not "not
working"); the only place silence is praised is a pomodoro break.
"""

import logging
from datetime import date, timedelta

from PySide6 import QtCore, QtGui, QtWidgets

if __package__:
    from . import activity as activity_mod
else:
    import importlib

    activity_mod = importlib.import_module("mycat.activity")

logger = logging.getLogger(__name__)

KIND_ICONS = {"focus": "🍅", "break": "☕", "long_break": "☕", "work": "💻"}

# Session table: start + duration per session, then the input counters.
# The bottom totals row deliberately carries NO start/end times.
TABLE_COLUMNS = ["Session", "Start", "Duration", "⌨ Keys", "🖱 Clicks", "Cursor path"]


def format_duration(seconds: int) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    return f"{minutes}:{secs:02d}"


def format_path(mouse_px: int, dpi: float) -> str:
    km = activity_mod.cursor_km(mouse_px, dpi)
    return f"{km:.2f} km" if km >= 0.1 else f"{int(km * 1000)} m"


def screen_dpi() -> float:
    screen = QtGui.QGuiApplication.primaryScreen()
    if screen is None:
        return 96.0
    try:
        return float(screen.physicalDotsPerInch()) or 96.0
    except Exception:  # noqa: BLE001
        return 96.0


class ActivityDialog(QtWidgets.QDialog):
    """Settings + the per-day interval log for the local activity diary."""

    def __init__(self, collector, focus_controller=None, parent=None, start_now_timer=True) -> None:
        super().__init__(parent)
        self.collector = collector
        self.focus_controller = focus_controller
        self.setWindowTitle("Activity diary")
        self.setModal(False)
        self.resize(520, 500)

        settings = collector.settings
        layout = QtWidgets.QVBoxLayout(self)

        # Live line: what the focus tooltip shows, refreshed every second
        # while the dialog is open ("Focus · 17:42 left · ⌨ 1,204 · …").
        self.now_label = QtWidgets.QLabel("")
        self.now_label.setWordWrap(True)
        self.now_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.now_label)
        self.now_timer = QtCore.QTimer(self)
        self.now_timer.setInterval(1000)
        self.now_timer.timeout.connect(self.refresh_now)
        if start_now_timer:
            self.now_timer.start()
        # Live "Current" row bookkeeping.
        self.current_row = None
        self.current_start = None
        self.dpi = 96.0

        self.enabled_box = QtWidgets.QCheckBox("Keep a private activity diary (everything stays on this computer)")
        self.enabled_box.setChecked(settings.enabled)
        layout.addWidget(self.enabled_box)

        self.keyboard_box = QtWidgets.QCheckBox(
            "Also count keystrokes and clicks — counts only, never which keys"
        )
        self.keyboard_box.setChecked(settings.keyboard_enabled)
        layout.addWidget(self.keyboard_box)

        retention_row = QtWidgets.QHBoxLayout()
        retention_row.addWidget(QtWidgets.QLabel("Keep history for:"))
        self.retention_spin = QtWidgets.QSpinBox()
        self.retention_spin.setRange(7, 3650)
        self.retention_spin.setValue(settings.retention_days)
        self.retention_spin.setSuffix(" days")
        retention_row.addWidget(self.retention_spin)
        retention_row.addStretch(1)
        self.delete_button = QtWidgets.QPushButton("Delete all recorded data…")
        self.delete_button.clicked.connect(self.delete_all)
        retention_row.addWidget(self.delete_button)
        layout.addLayout(retention_row)

        day_row = QtWidgets.QHBoxLayout()
        day_row.addWidget(QtWidgets.QLabel("Show:"))
        self.day_combo = QtWidgets.QComboBox()
        self.day_combo.addItems(["Today", "Yesterday"])
        self.day_combo.currentIndexChanged.connect(self.refresh_log)
        day_row.addWidget(self.day_combo)
        day_row.addStretch(1)
        layout.addLayout(day_row)

        self.table = QtWidgets.QTableWidget(0, len(TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels(TABLE_COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        # Never elide labels to "Focus …" — show them in full.
        self.table.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(TABLE_COLUMNS)):
            header.setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        self.totals_label = QtWidgets.QLabel("")
        self.totals_label.setWordWrap(True)
        layout.addWidget(self.totals_label)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save | QtWidgets.QDialogButtonBox.StandardButton.Close
        )
        buttons.accepted.connect(self.save_and_close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.refresh_log()
        self.refresh_now()

    # -- data -------------------------------------------------------------------

    def refresh_now(self) -> None:
        """Every second: update the countdown line and the live Current row."""
        controller = self.focus_controller
        status = controller.status_text() if controller is not None else ""
        if status:
            self.now_label.setText(f"Now: {status}")
        else:
            self.now_label.setText("Now: idle — auto-pomodoro starts a session when you get going.")

        # The Current row only lives on the Today view.
        if self.day_combo.currentIndex() != 0:
            return
        stats = controller.current_session_stats() if controller is not None else None
        start = stats["start"] if stats else None
        if start != self.current_start:
            # A period began or ended — rebuild so the finished one drops into
            # the list and a fresh Current row (if any) appears on top.
            self.refresh_log()
            return
        if stats is not None and self.current_row is not None:
            self.set_cell(self.current_row, 3, f"{stats['keys']:,}")
            self.set_cell(self.current_row, 4, f"{stats['clicks']:,}")
            self.set_cell(self.current_row, 5, format_path(stats["mouse_px"], self.dpi))

    def selected_day(self) -> date:
        today = self.collector.now_fn().date()
        return today if self.day_combo.currentIndex() == 0 else today - timedelta(days=1)

    def refresh_log(self) -> None:
        day = self.selected_day()
        store = self.collector.store
        self.dpi = screen_dpi()
        self.table.setRowCount(0)
        self.current_row = None
        self.current_start = None
        try:
            rows = activity_mod.sessions_table(store, day)
            summary = activity_mod.day_summary(store, day, dpi=self.dpi)
        except Exception:  # noqa: BLE001 - a broken DB shows an empty table, not a crash
            logger.exception("Failed to build activity table")
            self.totals_label.setText("Could not read the activity database.")
            return

        controller = self.focus_controller
        stats = controller.current_session_stats() if controller is not None else None
        # A live "Current" row on top, only on the Today view.
        if stats is not None and self.day_combo.currentIndex() == 0:
            icon = KIND_ICONS.get(stats["kind"], "▶")
            label = "Focus" if stats["kind"] == "focus" else "Break"
            self.append_row(
                [
                    f"▶ {icon} {label}",
                    stats["start"].strftime("%H:%M"),
                    "Current",
                    f"{stats['keys']:,}",
                    f"{stats['clicks']:,}",
                    format_path(stats["mouse_px"], self.dpi),
                ],
                italic=True,
            )
            self.current_row = 0
            self.current_start = stats["start"]

        # Finished sessions, newest first.
        for session in reversed(rows):
            icon = KIND_ICONS.get(session["kind"], "·")
            label = "Focus" if session["kind"] == "focus" else "Break"
            if session["kind"] == "focus" and not session["completed"]:
                label = "Focus (stopped)"
            self.append_row(
                [
                    f"{icon} {label}",
                    session["start"].strftime("%H:%M"),
                    format_duration(session["duration_seconds"]),
                    f"{session['keys']:,}",
                    f"{session['clicks']:,}",
                    format_path(session["mouse_px"], self.dpi),
                ]
            )

        # Bottom TOTAL row — day aggregates, NO start/end times, no "active".
        total_duration = sum(session["duration_seconds"] for session in rows)
        self.append_row(
            [
                f"TOTAL  ·  🍅 {summary['focus_count']}",
                "",
                format_duration(total_duration),
                f"{summary['keys']:,}",
                f"{summary['clicks']:,}",
                format_path(summary["mouse_px_total"], self.dpi),
            ],
            bold=True,
        )

    def append_row(self, cells, bold=False, italic=False) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, text in enumerate(cells):
            item = QtWidgets.QTableWidgetItem(text)
            if column != 0:
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            if bold or italic:
                font = item.font()
                font.setBold(bold)
                font.setItalic(italic)
                item.setFont(font)
            self.table.setItem(row, column, item)

    def set_cell(self, row, column, text) -> None:
        item = self.table.item(row, column)
        if item is not None:
            item.setText(text)

    def closeEvent(self, event) -> None:
        # Stop the ticking so a closed dialog never touches a stale controller.
        self.now_timer.stop()
        super().closeEvent(event)

    # -- actions ----------------------------------------------------------------

    def delete_all(self) -> None:
        answer = QtWidgets.QMessageBox.question(
            self,
            "Delete activity history",
            "Delete ALL recorded activity and focus sessions from this computer?\nThis cannot be undone.",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            self.collector.store.delete_all_activity()
            logger.info("Activity history deleted by user")
        except Exception:  # noqa: BLE001
            logger.exception("Failed to delete activity history")
        self.refresh_log()

    def save_and_close(self) -> None:
        settings = activity_mod.ActivitySettings(
            enabled=self.enabled_box.isChecked(),
            keyboard_enabled=self.keyboard_box.isChecked(),
            retention_days=self.retention_spin.value(),
            prompted=True,
        )
        activity_mod.save_activity_settings(settings)
        self.collector.apply_settings(settings)
        logger.info("Activity settings saved (enabled=%s, keyboard=%s)", settings.enabled, settings.keyboard_enabled)
        self.accept()


__all__ = ["ActivityDialog"]
