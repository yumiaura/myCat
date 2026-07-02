"""GitHub notifier: tracker baseline/dedupe, URL mapping, settings, polling."""

import io
import json
import urllib.error

from mycat.github_notify import (
    DEFAULT_POLL_SECONDS,
    GitHubNotifier,
    GitHubSettings,
    NotificationTracker,
    fetch_notifications,
    load_github_settings,
    notification_text,
    parse_poll_interval,
    save_github_settings,
    subject_html_url,
)


def note(thread_id, reason="review_requested", updated="2026-07-02T10:00:00Z", title="Fix things"):
    return {
        "id": thread_id,
        "reason": reason,
        "updated_at": updated,
        "subject": {
            "title": title,
            "url": f"https://api.github.com/repos/o/r/pulls/{thread_id}",
            "type": "PullRequest",
        },
        "repository": {"full_name": "o/r", "html_url": "https://github.com/o/r"},
    }


# -- tracker --------------------------------------------------------------------


def test_first_feed_only_baselines():
    tracker = NotificationTracker()
    assert tracker.feed([note("1"), note("2")]) == []


def test_new_thread_after_baseline_is_announced():
    tracker = NotificationTracker()
    tracker.feed([note("1")])
    fresh = tracker.feed([note("1"), note("2")])
    assert [item["id"] for item in fresh] == ["2"]


def test_updated_thread_is_reannounced_once():
    tracker = NotificationTracker()
    tracker.feed([note("1", updated="t1")])
    assert tracker.feed([note("1", updated="t1")]) == []
    fresh = tracker.feed([note("1", updated="t2")])
    assert [item["id"] for item in fresh] == ["1"]
    assert tracker.feed([note("1", updated="t2")]) == []


def test_reason_filter():
    tracker = NotificationTracker(reasons=("mention",))
    tracker.feed([])
    fresh = tracker.feed([note("1", reason="review_requested"), note("2", reason="mention")])
    assert [item["id"] for item in fresh] == ["2"]


# -- pure helpers ----------------------------------------------------------------


def test_subject_html_url_maps_pulls_and_commits():
    repo = {"html_url": "https://github.com/o/r"}
    assert (
        subject_html_url({"url": "https://api.github.com/repos/o/r/pulls/49"}, repo)
        == "https://github.com/o/r/pull/49"
    )
    assert (
        subject_html_url({"url": "https://api.github.com/repos/o/r/issues/7"}, repo)
        == "https://github.com/o/r/issues/7"
    )
    assert (
        subject_html_url({"url": "https://api.github.com/repos/o/r/commits/abc"}, repo)
        == "https://github.com/o/r/commit/abc"
    )
    assert subject_html_url({"url": ""}, repo) == "https://github.com/o/r"


def test_notification_text_labels_reasons():
    text = notification_text(note("1", reason="review_requested", title="Fix flyby mask"))
    assert text == "Review requested: Fix flyby mask (o/r)"


def test_parse_poll_interval_clamps():
    assert parse_poll_interval("120") == 120
    assert parse_poll_interval("5") == DEFAULT_POLL_SECONDS
    assert parse_poll_interval(None) == DEFAULT_POLL_SECONDS
    assert parse_poll_interval("junk") == DEFAULT_POLL_SECONDS


# -- settings round-trip -----------------------------------------------------------


def test_settings_round_trip(tmp_path):
    cfg = tmp_path / "config.ini"
    settings = GitHubSettings(enabled=True, token="tok", reasons=("mention",))
    save_github_settings(settings, cfg_file=cfg)
    loaded = load_github_settings(cfg_file=cfg)
    assert loaded.enabled is True
    assert loaded.token == "tok"
    assert loaded.reasons == ("mention",)


def test_settings_default_when_absent(tmp_path):
    loaded = load_github_settings(cfg_file=tmp_path / "nope.ini")
    assert loaded.enabled is False
    assert loaded.token == ""


# -- fetch with fake opener ---------------------------------------------------------


class FakeResponse:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_fetch_success_parses_items_and_headers():
    def opener(request, timeout):
        assert request.get_header("Authorization") == "Bearer tok"
        headers = {"Last-Modified": "LM", "X-Poll-Interval": "90"}
        return FakeResponse(200, headers, json.dumps([note("1")]).encode())

    result = fetch_notifications("tok", opener=opener)
    assert result["status"] == 200
    assert result["last_modified"] == "LM"
    assert result["poll_seconds"] == 90
    assert len(result["items"]) == 1


def test_fetch_304_is_quiet():
    def opener(request, timeout):
        raise urllib.error.HTTPError(
            "url", 304, "Not Modified", {"X-Poll-Interval": "75"}, io.BytesIO(b"")
        )

    result = fetch_notifications("tok", last_modified="LM", opener=opener)
    assert result["status"] == 304
    assert result["error"] == ""
    assert result["poll_seconds"] == 75


def test_fetch_network_error_reported_not_raised():
    def opener(request, timeout):
        raise OSError("offline")

    result = fetch_notifications("tok", opener=opener)
    assert result["error"] == "offline"
    assert result["items"] == []


# -- notifier orchestration ----------------------------------------------------------


class AnnouncerStub:
    def __init__(self):
        self.announced = []

    def set_dnd(self, active):
        pass

    def announce(self, text, url="", urgent=False, **kwargs):
        self.announced.append((text, url))


def test_notifier_announces_fresh_items(qapp):
    ann = AnnouncerStub()
    settings = GitHubSettings(enabled=True, token="tok")
    notifier = GitHubNotifier(None, announcer=ann, settings=settings, start_timer=False)
    # Baseline poll result.
    notifier.handle_result({"status": 200, "items": [note("1")], "last_modified": "LM", "poll_seconds": 60})
    assert ann.announced == []
    # Second poll: a new thread arrives.
    notifier.handle_result({"status": 200, "items": [note("1"), note("2")], "last_modified": "LM2", "poll_seconds": 60})
    assert len(ann.announced) == 1
    text, url = ann.announced[0]
    assert "Review requested" in text
    assert url == "https://github.com/o/r/pull/2"


def test_notifier_pauses_on_401_until_settings_change(qapp):
    ann = AnnouncerStub()
    settings = GitHubSettings(enabled=True, token="bad")
    notifier = GitHubNotifier(None, announcer=ann, settings=settings, start_timer=False)
    notifier.handle_result({"status": 401, "items": [], "last_modified": "", "poll_seconds": 60, "error": "HTTP 401"})
    assert notifier.auth_failed is True
    notifier.poll()  # must be a no-op now
    assert notifier.polling is False
    notifier.apply_settings(GitHubSettings(enabled=True, token="good"))
    assert notifier.auth_failed is False


def test_notifier_never_polls_when_disabled_or_tokenless(qapp, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    ann = AnnouncerStub()
    notifier = GitHubNotifier(None, announcer=ann, settings=GitHubSettings(enabled=False), start_timer=False)
    notifier.poll()
    assert notifier.polling is False
    notifier2 = GitHubNotifier(None, announcer=ann, settings=GitHubSettings(enabled=True), start_timer=False)
    notifier2.poll()
    assert notifier2.polling is False
