"""GitHub notification settings dialog behaviour."""

from mycat.github_notify import GitHubSettings
from mycat.github_ui import INBOX_CHOICES, GitHubDialog


class _Notifier:
    def __init__(self, settings):
        self.settings = settings


def test_private_options_unlock_when_a_saved_token_is_present(qapp, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    dialog = GitHubDialog(_Notifier(GitHubSettings(token="token")))

    assert all(dialog.category_boxes[key].isEnabled() for key, _ in INBOX_CHOICES)


def test_private_options_unlock_while_typing_a_token(qapp, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    dialog = GitHubDialog(_Notifier(GitHubSettings()))

    assert not any(dialog.category_boxes[key].isEnabled() for key, _ in INBOX_CHOICES)
    dialog.token_edit.setText("token")
    assert all(dialog.category_boxes[key].isEnabled() for key, _ in INBOX_CHOICES)
