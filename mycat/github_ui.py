#!/usr/bin/env python3
"""Settings dialog for the opt-in GitHub notifier.

Mirrors the LLM settings dialog philosophy: bring your own token, test it
right here, and nothing polls until "Enabled" is on.
"""

import logging

from PySide6 import QtCore, QtWidgets

if __package__:
    from . import github_notify
    from .ui_theme import LIGHT_QSS
else:
    import importlib

    github_notify = importlib.import_module("mycat.github_notify")
    LIGHT_QSS = importlib.import_module("mycat.ui_theme").LIGHT_QSS

logger = logging.getLogger(__name__)

REASON_CHOICES = (
    ("review_requested", "Review requested"),
    ("mention", "Mentions"),
    ("assign", "Assigned to me"),
    ("ci_activity", "CI activity"),
)


class GitHubDialog(QtWidgets.QDialog):
    """Enable/disable, token, reason filter and a live "Test" button."""

    def __init__(self, notifier, parent=None) -> None:
        super().__init__(parent)
        self.notifier = notifier
        self.setWindowTitle("GitHub notifications")
        self.setModal(False)
        self.resize(380, 320)
        self.setStyleSheet(LIGHT_QSS)

        settings = notifier.settings
        layout = QtWidgets.QVBoxLayout(self)

        self.enabled_box = QtWidgets.QCheckBox("Enabled — the cat announces new GitHub notifications")
        self.enabled_box.setChecked(settings.enabled)
        layout.addWidget(self.enabled_box)

        form = QtWidgets.QFormLayout()
        self.token_edit = QtWidgets.QLineEdit(settings.token)
        self.token_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.token_edit.setPlaceholderText(f"fine-grained PAT (empty → ${settings.token_env})")
        form.addRow("Token:", self.token_edit)
        self.username_edit = QtWidgets.QLineEdit(settings.username)
        self.username_edit.setPlaceholderText("GitHub username (for the tokenless mode)")
        form.addRow("Username:", self.username_edit)
        layout.addLayout(form)

        hint = QtWidgets.QLabel(
            "Token → your inbox (reviews, mentions).<br>"
            "No token → <b>public activity only</b> (stars, forks, issues, releases)."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555;")
        hint.setToolTip(
            "The notification inbox is private API — GitHub serves it only with a token\n"
            "(read-only, Notifications permission is enough). Without one, the cat follows\n"
            "the username's public feed instead; private repos and the inbox stay invisible.\n"
            "Requests go straight to api.github.com — nowhere else."
        )
        layout.addWidget(hint)

        reasons_box = QtWidgets.QGroupBox("Announce")
        reasons_layout = QtWidgets.QVBoxLayout(reasons_box)
        self.reason_boxes = {}
        for key, label in REASON_CHOICES:
            box = QtWidgets.QCheckBox(label)
            box.setChecked(key in settings.reasons)
            self.reason_boxes[key] = box
            reasons_layout.addWidget(box)
        layout.addWidget(reasons_box)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Test (left) · Save, Close (right). Save applies without closing,
        # so the flow "save, then test" works in one open dialog.
        button_row = QtWidgets.QHBoxLayout()
        self.test_button = QtWidgets.QPushButton("Test")
        self.save_button = QtWidgets.QPushButton("Save")
        self.close_button = QtWidgets.QPushButton("Close")
        self.test_button.clicked.connect(self.run_test)
        self.save_button.clicked.connect(self.save_settings)
        self.close_button.clicked.connect(self.reject)
        button_row.addWidget(self.test_button)
        button_row.addStretch(1)
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)

    # -- actions ---------------------------------------------------------------

    def set_status(self, text: str, ok: bool | None = None) -> None:
        """Status line: green when ok, red when not, neutral otherwise."""
        color = {True: "#1c7c2f", False: "#c0392b", None: "#555555"}[ok]
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(text)

    def collect_settings(self) -> "github_notify.GitHubSettings":
        reasons = tuple(key for key, box in self.reason_boxes.items() if box.isChecked())
        return github_notify.GitHubSettings(
            enabled=self.enabled_box.isChecked(),
            token=self.token_edit.text().strip(),
            token_env=self.notifier.settings.token_env,
            username=self.username_edit.text().strip(),
            reasons=reasons or github_notify.DEFAULT_REASONS,
        )

    def save_settings(self) -> None:
        """Persist + apply, but keep the dialog open (save → then test)."""
        settings = self.collect_settings()
        github_notify.save_github_settings(settings)
        self.notifier.apply_settings(settings)
        logger.info("GitHub notifier settings saved (enabled=%s)", settings.enabled)
        self.set_status("Saved.", ok=True)

    def run_test(self) -> None:
        settings = self.collect_settings()
        token = settings.resolve_token()
        if not token and not settings.username:
            self.set_status("Paste a token, or a username for the public-only mode.", ok=False)
            return
        self.set_status("Checking…")
        self.test_button.setEnabled(False)

        if token:
            worker = github_notify.PollWorker(token, "")
        else:
            worker = github_notify.PollWorker("", "", mode="public", username=settings.username)
        worker.emitter.finished.connect(self.show_test_result)
        QtCore.QThreadPool.globalInstance().start(worker)

    def show_test_result(self, result: dict) -> None:
        self.test_button.setEnabled(True)
        if result.get("error"):
            self.set_status(f"Failed: {result['error']}", ok=False)
            return
        items = list(result.get("items", []))
        # Show the latest item as its banner would read — and actually FLY it
        # (urgent, so a running focus session's DND can't hold the test back).
        announcer = getattr(self.notifier, "announcer", None)
        if result.get("mode") == "public":
            latest = next((e for e in items if github_notify.interesting_public_event(e)), None)
            if latest is None and items:
                latest = items[0]  # quiet feed: show the newest event of any kind
            if latest is not None:
                text = github_notify.event_text(latest)
                self.set_status(f"OK · {text}", ok=True)
                if announcer is not None:
                    announcer.announce(text, url=github_notify.event_html_url(latest), urgent=True,
                                       speed=0.6, plane_width=220)
            else:
                self.set_status("OK — public mode, no recent activity.", ok=True)
        else:
            if items:
                item = items[0]
                text = github_notify.notification_text(item)
                self.set_status(f"OK · {text}", ok=True)
                if announcer is not None:
                    url = github_notify.subject_html_url(item.get("subject") or {}, item.get("repository") or {})
                    announcer.announce(text, url=url, urgent=True, speed=0.6, plane_width=220)
            else:
                self.set_status("OK — no unread notifications.", ok=True)


__all__ = ["GitHubDialog"]
