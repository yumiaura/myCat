#!/usr/bin/env python3
"""Settings dialog for the opt-in GitHub notifier.

Mirrors the LLM settings dialog philosophy: bring your own token, test it
right here, and nothing polls until "Enabled" is on.
"""

import logging

from PySide6 import QtCore, QtWidgets

if __package__:
    from . import github_notify
else:
    import importlib

    github_notify = importlib.import_module("mycat.github_notify")

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
        layout.addLayout(form)

        hint = QtWidgets.QLabel(
            "A read-only fine-grained token with the <b>Notifications</b> permission is enough.<br>"
            "Requests go straight to api.github.com — nowhere else."
        )
        hint.setWordWrap(True)
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

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self.test_button = buttons.addButton("Test", QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)
        self.test_button.clicked.connect(self.run_test)
        buttons.accepted.connect(self.save_and_close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # -- actions ---------------------------------------------------------------

    def collect_settings(self) -> "github_notify.GitHubSettings":
        reasons = tuple(key for key, box in self.reason_boxes.items() if box.isChecked())
        return github_notify.GitHubSettings(
            enabled=self.enabled_box.isChecked(),
            token=self.token_edit.text().strip(),
            token_env=self.notifier.settings.token_env,
            reasons=reasons or github_notify.DEFAULT_REASONS,
        )

    def save_and_close(self) -> None:
        settings = self.collect_settings()
        github_notify.save_github_settings(settings)
        self.notifier.apply_settings(settings)
        logger.info("GitHub notifier settings saved (enabled=%s)", settings.enabled)
        self.accept()

    def run_test(self) -> None:
        token = self.collect_settings().resolve_token()
        if not token:
            self.status_label.setText("No token: paste one above or export $GITHUB_TOKEN.")
            return
        self.status_label.setText("Checking…")
        self.test_button.setEnabled(False)

        worker = github_notify.PollWorker(token, "")
        worker.emitter.finished.connect(self.show_test_result)
        QtCore.QThreadPool.globalInstance().start(worker)

    def show_test_result(self, result: dict) -> None:
        self.test_button.setEnabled(True)
        if result.get("error"):
            self.status_label.setText(f"Failed: {result['error']}")
            return
        count = len(result.get("items", []))
        self.status_label.setText(f"OK — {count} unread notification(s) visible to this token.")


__all__ = ["GitHubDialog"]
