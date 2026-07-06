#!/usr/bin/env python3
"""Settings dialog for the opt-in GitHub notifier.

Public-first: you pick, with checkboxes, exactly which GitHub things ping the
cat. The account fields come first; the token is optional and sits at the
bottom — it only unlocks the private inbox categories, which stay greyed out
until the token is entered and verified with "Test".
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

INBOX_CHOICES = [(key, github_notify.CATEGORY_LABELS[key]) for key in github_notify.INBOX_CATEGORIES]
PUBLIC_CHOICES = [(key, github_notify.CATEGORY_LABELS[key]) for key in github_notify.PUBLIC_CATEGORIES]


class GitHubDialog(QtWidgets.QDialog):
    """Enable/disable, identity, per-category checkboxes and a live "Test"."""

    def __init__(self, notifier, parent=None) -> None:
        super().__init__(parent)
        self.notifier = notifier
        self.setWindowTitle("GitHub notifications")
        self.setModal(False)
        self.resize(400, 500)
        self.setStyleSheet(LIGHT_QSS)

        settings = notifier.settings
        self.token_verified = bool(settings.token_verified and settings.resolve_token())
        layout = QtWidgets.QVBoxLayout(self)

        self.enabled_box = QtWidgets.QCheckBox("Enabled — announces GitHub activity")
        self.enabled_box.setChecked(settings.enabled)
        layout.addWidget(self.enabled_box)

        form = QtWidgets.QFormLayout()
        self.me_edit = QtWidgets.QLineEdit(settings.me_login)
        self.me_edit.setPlaceholderText("auto-filled when you verify a token")
        form.addRow("GitHub username:", self.me_edit)
        self.token_edit = QtWidgets.QLineEdit(settings.token)
        self.token_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.token_edit.setPlaceholderText(f"empty → ${settings.token_env}")
        self.token_edit.textChanged.connect(self.on_token_changed)
        form.addRow("Token (optional):", self.token_edit)
        layout.addLayout(form)

        self.category_boxes: dict = {}

        public_box = QtWidgets.QGroupBox("Public options")
        public_layout = QtWidgets.QVBoxLayout(public_box)
        for key, label in PUBLIC_CHOICES:
            box = QtWidgets.QCheckBox(label)
            box.setChecked(key in settings.categories)
            self.category_boxes[key] = box
            public_layout.addWidget(box)
        layout.addWidget(public_box)

        self.inbox_box = QtWidgets.QGroupBox("Private options (token required)")
        inbox_layout = QtWidgets.QVBoxLayout(self.inbox_box)
        for key, label in INBOX_CHOICES:
            box = QtWidgets.QCheckBox(label)
            box.setChecked(key in settings.categories)
            self.category_boxes[key] = box
            inbox_layout.addWidget(box)
        self.inbox_box.setToolTip(
            "Enter a token above and press Test to unlock these. They are served only with a\n"
            "token (read-only Notifications scope is enough); requests go straight to api.github.com."
        )
        layout.addWidget(self.inbox_box)
        self.set_inbox_enabled(self.token_verified)

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

    # -- state -----------------------------------------------------------------

    def set_inbox_enabled(self, enabled: bool) -> None:
        for key, label in INBOX_CHOICES:
            self.category_boxes[key].setEnabled(enabled)

    def on_token_changed(self, text: str) -> None:
        # Editing the token invalidates any prior verification.
        self.token_verified = False
        self.set_inbox_enabled(False)

    def set_status(self, text: str, ok: bool | None = None) -> None:
        """Status line: green when ok, red when not, neutral otherwise."""
        color = {True: "#1c7c2f", False: "#c0392b", None: "#555555"}[ok]
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(text)

    def collect_settings(self) -> "github_notify.GitHubSettings":
        categories = tuple(key for key, box in self.category_boxes.items() if box.isChecked())
        return github_notify.GitHubSettings(
            enabled=self.enabled_box.isChecked(),
            token=self.token_edit.text().strip(),
            token_env=self.notifier.settings.token_env,
            # "Also follow" is no longer shown; preserve any value already in config.
            accounts=self.notifier.settings.accounts,
            me_login=self.me_edit.text().strip(),
            categories=categories,
            token_verified=self.token_verified,
        )

    # -- actions ---------------------------------------------------------------

    def save_settings(self) -> None:
        """Persist + apply, but keep the dialog open (save → then test)."""
        settings = self.collect_settings()
        github_notify.save_github_settings(settings)
        self.notifier.apply_settings(settings)
        logger.info("GitHub notifier settings saved (enabled=%s)", settings.enabled)
        public_on = sum(1 for key, label in PUBLIC_CHOICES if self.category_boxes[key].isChecked())
        private_on = sum(1 for key, label in INBOX_CHOICES if self.category_boxes[key].isChecked())
        state = "on" if settings.enabled else "off"
        who = settings.me_login or "no username"
        token_note = "token verified" if self.token_verified else "no token"
        self.set_status(
            f"Saved ({state}): {who} · {public_on} public + {private_on} private options · {token_note}.",
            ok=True,
        )

    def run_test(self) -> None:
        settings = self.collect_settings()
        token = settings.resolve_token()
        accounts = list(self.sample_accounts(settings))
        if not token and not accounts:
            self.set_status("Enter your username, list accounts, or paste a token.", ok=False)
            return
        self.set_status("Checking…")
        self.test_button.setEnabled(False)

        if token:
            worker = github_notify.PollWorker(token, "", mode="verify")
        else:
            worker = github_notify.PollWorker("", "", mode="public", accounts=accounts)
        worker.emitter.finished.connect(self.show_test_result)
        QtCore.QThreadPool.globalInstance().start(worker)

    def sample_accounts(self, settings) -> tuple:
        """Accounts to sample in the tokenless Test: yourself + those you follow."""
        me = settings.me_login.strip()
        accounts = list(github_notify.parse_accounts(settings.accounts))
        if me and me.lower() not in {a.lower() for a in accounts}:
            accounts.insert(0, me)
        return tuple(accounts)

    def fly_sample(self, text: str, url: str) -> None:
        """Fly the sample banner — same plane as a real notification."""
        announcer = getattr(self.notifier, "announcer", None)
        if announcer is not None:
            announcer.announce(text, url=url)

    def show_test_result(self, result: dict) -> None:
        self.test_button.setEnabled(True)
        mode = result.get("mode")

        if mode == "verify":
            if result.get("error") or int(result.get("status", 0)) != 200:
                self.token_verified = False
                self.set_inbox_enabled(False)
                self.set_status("Token rejected — check the PAT (read-only Notifications scope).", ok=False)
                return
            login = str(result.get("login", ""))
            self.token_verified = True
            self.set_inbox_enabled(True)
            if login:
                self.me_edit.setText(login)
            items = list(result.get("items", []))
            if items:
                text = github_notify.notification_text(items[0])
                self.set_status(f"OK · verified as {login} · {text}", ok=True)
                url = github_notify.subject_html_url(items[0].get("subject") or {}, items[0].get("repository") or {})
                self.fly_sample(text, url)
            else:
                self.set_status(f"OK · verified as {login} · no notifications.", ok=True)
            return

        if result.get("error"):
            self.set_status(f"Failed: {result['error']}", ok=False)
            return

        items = list(result.get("items", []))
        me = self.me_edit.text().strip()

        def interest(event):
            return github_notify.public_event_interesting(event, me)

        latest = next((event for event in items if interest(event)), None)
        if latest is None and items:
            latest = items[0]  # quiet feed: show the newest event of any kind
        if latest is not None:
            text = github_notify.event_text(latest)
            self.set_status(f"OK · {text}", ok=True)
            self.fly_sample(text, github_notify.event_html_url(latest))
        else:
            self.set_status("OK — public mode, no recent activity.", ok=True)


__all__ = ["GitHubDialog"]
