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

KIND_ICONS = {"focus": "🍅", "break": "☕", "work": "💻"}


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

    def __init__(self, collector, focus_controller=None, parent=None) -> None:
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
        self.now_timer.start()
        self.refresh_now()

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

        self.log_list = QtWidgets.QListWidget()
        layout.addWidget(self.log_list, 1)

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

    # -- data -------------------------------------------------------------------

    def refresh_now(self) -> None:
        """Mirror the focus tooltip: countdown + interim session stats."""
        controller = self.focus_controller
        status = controller.status_text() if controller is not None else ""
        if status:
            self.now_label.setText(f"Now: {status}")
        else:
            self.now_label.setText("Now: idle — auto-pomodoro starts a session when you get going.")

    def selected_day(self) -> date:
        today = self.collector.now_fn().date()
        return today if self.day_combo.currentIndex() == 0 else today - timedelta(days=1)

    def refresh_log(self) -> None:
        day = self.selected_day()
        store = self.collector.store
        self.log_list.clear()
        try:
            intervals = activity_mod.classify_day(store, day)
            summary = activity_mod.day_summary(store, day, dpi=screen_dpi())
        except Exception:  # noqa: BLE001 - a broken DB shows an empty log, not a crash
            logger.exception("Failed to build activity log")
            self.totals_label.setText("Could not read the activity database.")
            return

        if not intervals:
            self.log_list.addItem("No sessions or activity recorded.")
        for interval in intervals:
            icon = KIND_ICONS.get(interval["kind"], "·")
            span = f"{interval['start'].strftime('%H:%M')}–{interval['end'].strftime('%H:%M')}"
            self.log_list.addItem(f"{span}  {icon}  {interval['label']}")

        active_h, active_m = divmod(summary["active_minutes"], 60)
        parts = [f"🖱 {summary['cursor_km']:.2f} km"]
        if self.collector.settings.keyboard_enabled:
            parts.append(f"⌨ {summary['keys']:,}")
            parts.append(f"clicks {summary['clicks']:,}")
        parts.append(f"🍅 {summary['focus_count']}")
        if summary["best_focus_minutes"]:
            parts.append(f"best focus {summary['best_focus_minutes']} min")
        parts.append(f"at the computer {active_h} h {active_m:02d} min")
        self.totals_label.setText(" · ".join(parts))

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
