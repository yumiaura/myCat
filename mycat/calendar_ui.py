#!/usr/bin/env python3
"""Settings dialog for the opt-in ICS calendar reminders."""

import logging

from PySide6 import QtCore, QtWidgets

if __package__:
    from . import calendar_ics
    from . import i18n
    from .ui_theme import LIGHT_QSS
else:
    import importlib

    calendar_ics = importlib.import_module("mycat.calendar_ics")
    i18n = importlib.import_module("mycat.i18n")
    LIGHT_QSS = importlib.import_module("mycat.ui_theme").LIGHT_QSS

logger = logging.getLogger(__name__)
tr = i18n.tr


class CalendarDialog(QtWidgets.QDialog):
    """Enable/disable, the secret ICS URL, lead time, and a live Test."""

    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle(tr("Calendar"))
        self.setModal(False)
        self.setStyleSheet(LIGHT_QSS)

        settings = controller.settings
        layout = QtWidgets.QVBoxLayout(self)

        self.enabled_box = QtWidgets.QCheckBox(tr("Enabled — announces upcoming events"))
        self.enabled_box.setChecked(settings.enabled)
        layout.addWidget(self.enabled_box)

        form = QtWidgets.QFormLayout()
        self.url_edit = QtWidgets.QLineEdit(settings.url)
        self.url_edit.setPlaceholderText("https://…/basic.ics (or webcal://…)")
        form.addRow(tr("ICS URL:"), self.url_edit)

        self.remind_spin = QtWidgets.QSpinBox()
        self.remind_spin.setRange(1, 120)
        self.remind_spin.setValue(settings.remind_minutes)
        self.remind_spin.setSuffix(tr(" min before"))
        form.addRow(tr("Remind:"), self.remind_spin)

        self.poll_spin = QtWidgets.QSpinBox()
        self.poll_spin.setRange(5, 120)
        self.poll_spin.setValue(settings.poll_minutes)
        self.poll_spin.setSuffix(tr(" min"))
        form.addRow(tr("Refresh every:"), self.poll_spin)
        layout.addLayout(form)

        hint = QtWidgets.QLabel(
            tr("Google Calendar → Settings → <i>Secret address in iCal format</i>. "
               "Apple/Outlook: any private calendar link works.<br>"
               "Treat the URL as a password — it's stored in the owner-only config. "
               "Calendar banners fly even during a focus session.")
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555;")
        layout.addWidget(hint)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Test (left) · Save, Close (right); Save keeps the dialog open.
        button_row = QtWidgets.QHBoxLayout()
        self.test_button = QtWidgets.QPushButton(tr("Test"))
        self.save_button = QtWidgets.QPushButton(tr("Save"))
        self.close_button = QtWidgets.QPushButton(tr("Close"))
        self.test_button.clicked.connect(self.run_test)
        self.save_button.clicked.connect(self.save_settings)
        self.close_button.clicked.connect(self.reject)
        button_row.addWidget(self.test_button)
        button_row.addStretch(1)
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)

    def collect_settings(self) -> "calendar_ics.CalendarSettings":
        return calendar_ics.CalendarSettings(
            enabled=self.enabled_box.isChecked(),
            url=self.url_edit.text().strip(),
            remind_minutes=self.remind_spin.value(),
            poll_minutes=self.poll_spin.value(),
        )

    def set_status(self, text: str, ok: bool | None = None) -> None:
        """Status line: green when ok, red when not, neutral otherwise."""
        color = {True: "#1c7c2f", False: "#c0392b", None: "#555555"}[ok]
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(text)

    def save_settings(self) -> None:
        """Persist + apply, but keep the dialog open (save → then test)."""
        settings = self.collect_settings()
        calendar_ics.save_calendar_settings(settings)
        self.controller.apply_settings(settings)
        logger.info("Calendar settings saved (enabled=%s)", settings.enabled)
        state = "on" if settings.enabled else "off"
        url_note = tr("URL set") if settings.url else tr("no URL")
        self.set_status(
            tr("Saved ({state}): {url_note}, remind {min} min before, "
               "refresh every {poll} min.").format(
                state=state, url_note=url_note, min=settings.remind_minutes, poll=settings.poll_minutes
            ),
            ok=True,
        )

    def run_test(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            self.set_status(tr("Paste the secret ICS URL first."), ok=False)
            return
        self.set_status(tr("Fetching…"))
        self.test_button.setEnabled(False)
        worker = calendar_ics.FetchWorker(url, "")
        worker.emitter.finished.connect(self.show_test_result)
        QtCore.QThreadPool.globalInstance().start(worker)

    def show_test_result(self, result: dict) -> None:
        self.test_button.setEnabled(True)
        if result.get("error"):
            self.set_status(tr("Failed: {error}").format(error=result["error"]), ok=False)
            return
        events = list(result.get("events", []))
        if not events:
            self.set_status(tr("OK — feed reachable, no events in the next 24 h."), ok=True)
            return
        nearest = events[0]
        when = nearest["start"].strftime("%H:%M")
        text = tr("📅 {summary} — at {when}").format(
            summary=nearest["summary"], when=when
        )
        self.set_status(
            tr("OK — {count} event(s) in 24 h · {text}").format(count=len(events), text=text),
            ok=True,
        )
        # Fly the nearest event as a real banner — same plane as every other
        # announcement.
        announcer = getattr(self.controller, "announcer", None)
        if announcer is not None:
            announcer.announce(text)


__all__ = ["CalendarDialog"]
