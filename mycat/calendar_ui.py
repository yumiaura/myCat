#!/usr/bin/env python3
"""Settings dialog for the opt-in ICS calendar reminders."""

import logging

from PySide6 import QtCore, QtWidgets

if __package__:
    from . import calendar_ics
else:
    import importlib

    calendar_ics = importlib.import_module("mycat.calendar_ics")

logger = logging.getLogger(__name__)


class CalendarDialog(QtWidgets.QDialog):
    """Enable/disable, the secret ICS URL, lead time, and a live Test."""

    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Calendar reminders")
        self.setModal(False)

        settings = controller.settings
        layout = QtWidgets.QVBoxLayout(self)

        self.enabled_box = QtWidgets.QCheckBox("Enabled — the cat announces upcoming events")
        self.enabled_box.setChecked(settings.enabled)
        layout.addWidget(self.enabled_box)

        form = QtWidgets.QFormLayout()
        self.url_edit = QtWidgets.QLineEdit(settings.url)
        self.url_edit.setPlaceholderText("https://…/basic.ics  (or webcal://…)")
        form.addRow("ICS URL:", self.url_edit)

        self.remind_spin = QtWidgets.QSpinBox()
        self.remind_spin.setRange(1, 120)
        self.remind_spin.setValue(settings.remind_minutes)
        self.remind_spin.setSuffix(" min before")
        form.addRow("Remind:", self.remind_spin)

        self.poll_spin = QtWidgets.QSpinBox()
        self.poll_spin.setRange(5, 120)
        self.poll_spin.setValue(settings.poll_minutes)
        self.poll_spin.setSuffix(" min")
        form.addRow("Refresh every:", self.poll_spin)
        layout.addLayout(form)

        hint = QtWidgets.QLabel(
            "Google: Calendar settings → <i>Secret address in iCal format</i>. "
            "Apple/Outlook: any private calendar link works.<br>"
            "Treat the URL as a password — it is stored in the owner-only config. "
            "Calendar banners fly even during focus sessions."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self.test_button = buttons.addButton("Test", QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)
        self.test_button.clicked.connect(self.run_test)
        buttons.accepted.connect(self.save_and_close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def collect_settings(self) -> "calendar_ics.CalendarSettings":
        return calendar_ics.CalendarSettings(
            enabled=self.enabled_box.isChecked(),
            url=self.url_edit.text().strip(),
            remind_minutes=self.remind_spin.value(),
            poll_minutes=self.poll_spin.value(),
        )

    def save_and_close(self) -> None:
        settings = self.collect_settings()
        calendar_ics.save_calendar_settings(settings)
        self.controller.apply_settings(settings)
        logger.info("Calendar settings saved (enabled=%s)", settings.enabled)
        self.accept()

    def run_test(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            self.status_label.setText("Paste the secret ICS URL first.")
            return
        self.status_label.setText("Fetching…")
        self.test_button.setEnabled(False)
        worker = calendar_ics.FetchWorker(url, "")
        worker.emitter.finished.connect(self.show_test_result)
        QtCore.QThreadPool.globalInstance().start(worker)

    def show_test_result(self, result: dict) -> None:
        self.test_button.setEnabled(True)
        if result.get("error"):
            self.status_label.setText(f"Failed: {result['error']}")
            return
        events = list(result.get("events", []))
        if not events:
            self.status_label.setText("OK — feed reachable, no events in the next 24 h.")
            return
        nearest = events[0]
        when = nearest["start"].strftime("%H:%M")
        self.status_label.setText(
            f"OK — {len(events)} event(s) in the next 24 h; nearest: “{nearest['summary']}” at {when}."
        )


__all__ = ["CalendarDialog"]
