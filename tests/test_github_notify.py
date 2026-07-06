"""GitHub notifier: tracker baseline/dedupe, URL mapping, settings, polling."""

import io
import json
import urllib.error

from mycat.github_notify import (
    DEFAULT_POLL_SECONDS,
    FollowerTracker,
    GitHubNotifier,
    GitHubSettings,
    InboundEventTracker,
    NotificationTracker,
    PublicEventTracker,
    event_html_url,
    event_text,
    fetch_followers,
    fetch_inbound,
    fetch_notifications,
    fetch_owned_repos,
    fetch_repo_events,
    fetch_user_login,
    follower_text,
    interesting_public_event,
    load_github_settings,
    notification_category,
    notification_matches,
    notification_text,
    parse_poll_interval,
    public_event_interesting,
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


def test_category_filter():
    tracker = NotificationTracker(categories=("mention",))
    tracker.feed([])
    fresh = tracker.feed([note("1", reason="review_requested"), note("2", reason="mention")])
    assert [item["id"] for item in fresh] == ["2"]


# -- pure helpers ----------------------------------------------------------------


def test_subject_html_url_maps_pulls_and_commits():
    repo = {"html_url": "https://github.com/o/r"}
    assert (
        subject_html_url({"url": "https://api.github.com/repos/o/r/pulls/49"}, repo) == "https://github.com/o/r/pull/49"
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
    settings = GitHubSettings(
        enabled=True, token="tok", me_login="olya", categories=("mention", "inbound_star"), token_verified=True
    )
    save_github_settings(settings, cfg_file=cfg)
    loaded = load_github_settings(cfg_file=cfg)
    assert loaded.enabled is True
    assert loaded.token == "tok"
    assert loaded.me_login == "olya"
    assert loaded.categories == ("mention", "inbound_star")
    assert loaded.token_verified is True


def test_settings_migrates_legacy_reasons(tmp_path):
    legacy = tmp_path / "legacy.ini"
    legacy.write_text("[github]\nenabled = true\nreasons = review_requested,mention\n")
    loaded = load_github_settings(cfg_file=legacy)
    assert loaded.categories == ("review_requested", "mention")


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
        raise urllib.error.HTTPError("url", 304, "Not Modified", {"X-Poll-Interval": "75"}, io.BytesIO(b""))

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

    def announce(self, text, url="", **kwargs):
        self.announced.append((text, url))


def test_notifier_announces_fresh_items(qapp):
    ann = AnnouncerStub()
    settings = GitHubSettings(enabled=True, token="tok", categories=("review_requested",))
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


def test_notifier_never_polls_when_disabled_or_unconfigured(qapp, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    ann = AnnouncerStub()
    notifier = GitHubNotifier(None, announcer=ann, settings=GitHubSettings(enabled=False), start_timer=False)
    notifier.poll()
    assert notifier.polling is False
    # No token AND no username → nothing to poll.
    notifier2 = GitHubNotifier(None, announcer=ann, settings=GitHubSettings(enabled=True), start_timer=False)
    assert notifier2.mode() == ""
    notifier2.poll()
    assert notifier2.polling is False


# -- tokenless public mode ---------------------------------------------------------


def public_event(event_id, kind="WatchEvent", action="", title="T"):
    payload = {}
    if action:
        payload["action"] = action
    if kind == "IssuesEvent":
        payload["issue"] = {"title": title, "html_url": "https://github.com/o/r/issues/1"}
    if kind == "PullRequestEvent":
        payload["pull_request"] = {"title": title, "html_url": "https://github.com/o/r/pull/2"}
    return {
        "id": event_id,
        "type": kind,
        "actor": {"login": "alice"},
        "repo": {"name": "o/r"},
        "payload": payload,
    }


def test_mode_selection(qapp, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with_token = GitHubNotifier(
        None, settings=GitHubSettings(enabled=True, token="t", categories=("mention",)), start_timer=False
    )
    assert with_token.mode() == "notifications"
    username_only = GitHubNotifier(None, settings=GitHubSettings(enabled=True, accounts="olya"), start_timer=False)
    assert username_only.mode() == "public"


def test_interesting_public_events_filter():
    assert interesting_public_event(public_event("1", "WatchEvent"))
    assert interesting_public_event(public_event("2", "IssuesEvent", action="opened"))
    assert not interesting_public_event(public_event("3", "IssuesEvent", action="closed"))
    assert not interesting_public_event(public_event("4", "PushEvent"))


def test_event_text_and_url():
    star = public_event("1", "WatchEvent")
    assert event_text(star) == "⭐ alice starred o/r"
    assert event_html_url(star) == "https://github.com/o/r"
    issue = public_event("2", "IssuesEvent", action="opened", title="Bug!")
    assert event_text(issue) == "🐞 alice: Bug! (o/r)"
    assert event_html_url(issue) == "https://github.com/o/r/issues/1"


def test_public_tracker_baselines_then_dedupes():
    tracker = PublicEventTracker()
    assert tracker.feed([public_event("1")]) == []  # baseline
    fresh = tracker.feed([public_event("1"), public_event("2")])
    assert [e["id"] for e in fresh] == ["2"]
    assert tracker.feed([public_event("2")]) == []


def test_notifier_public_mode_announces(qapp, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    ann = AnnouncerStub()
    notifier = GitHubNotifier(
        None, announcer=ann, settings=GitHubSettings(enabled=True, accounts="olya"), start_timer=False
    )
    notifier.handle_result(
        {"mode": "public", "status": 200, "items": [public_event("1")], "etag": "E1", "poll_seconds": 300}
    )
    assert ann.announced == []  # baseline
    notifier.handle_result(
        {
            "mode": "public",
            "status": 200,
            "items": [public_event("1"), public_event("2", "IssuesEvent", action="opened")],
            "etag": "E2",
            "poll_seconds": 300,
        }
    )
    assert len(ann.announced) == 1
    text, url = ann.announced[0]
    assert "🐞" in text
    assert url == "https://github.com/o/r/issues/1"


def test_settings_accounts_round_trip_and_migration(tmp_path):
    cfg = tmp_path / "config.ini"
    save_github_settings(GitHubSettings(enabled=True, accounts="olya, bob"), cfg_file=cfg)
    assert load_github_settings(cfg_file=cfg).accounts == "olya, bob"
    # Legacy configs that still say "username" are honoured.
    legacy = tmp_path / "legacy.ini"
    legacy.write_text("[github]\nenabled = true\nusername = olya\n")
    assert load_github_settings(cfg_file=legacy).accounts == "olya"


def test_parse_accounts():
    from mycat.github_notify import parse_accounts

    assert parse_accounts("olya, bob,  carol ") == ("olya", "bob", "carol")
    assert parse_accounts("") == ()


# -- inbox categories ----------------------------------------------------------


def test_notification_category_and_matches():
    issue = {"reason": "subscribed", "subject": {"type": "Issue"}}
    pr = {"reason": "subscribed", "subject": {"type": "PullRequest"}}
    assert notification_category(issue) == "issue"
    assert notification_category(pr) == "pull_request"
    assert notification_category({"reason": "team_mention", "subject": {"type": "Issue"}}) == "mention"
    assert notification_category({"reason": "ci_activity", "subject": {"type": "CheckSuite"}}) == "ci_activity"
    assert notification_matches(issue, ("issue",))
    assert not notification_matches(issue, ("pull_request",))
    assert not notification_matches({"reason": "subscribed", "subject": {"type": "Discussion"}}, ("issue", "mention"))


def test_notification_tracker_dedupes_by_thread():
    tracker = NotificationTracker(categories=("issue", "pull_request"))
    tracker.feed([])
    item = note("1", reason="subscribed")  # subject.type PullRequest → pull_request
    fresh = tracker.feed([item, item])
    assert [i["id"] for i in fresh] == ["1"]  # same thread announced once


# -- follow + inbound rendering ------------------------------------------------


def test_follow_event_text_and_url():
    event = {
        "type": "FollowEvent",
        "actor": {"login": "bob"},
        "payload": {"target": {"login": "olya", "html_url": "https://github.com/olya"}},
    }
    assert event_text(event) == "👤 bob followed olya"
    assert event_html_url(event) == "https://github.com/olya"


def test_follower_text():
    assert follower_text("carol") == "➕ new follower: carol"


def test_public_event_interesting_me_vs_foreign():
    star_by_me = {"type": "WatchEvent", "actor": {"login": "olya"}}
    push_by_me = {"type": "PushEvent", "actor": {"login": "Olya"}}
    assert public_event_interesting(star_by_me, "olya")
    assert not public_event_interesting(push_by_me, "olya")  # my own noise is dropped
    foreign_issue = {"type": "IssuesEvent", "actor": {"login": "bob"}, "payload": {"action": "opened"}}
    assert public_event_interesting(foreign_issue, "olya")  # a followed account keeps the broad filter


def repo_event(event_id, kind="WatchEvent", created="2026-07-02T12:00:00Z", actor="alice", repo="olya/app"):
    return {
        "id": event_id,
        "type": kind,
        "actor": {"login": actor},
        "repo": {"name": repo},
        "payload": {},
        "created_at": created,
    }


def test_inbound_tracker_baseline_dedupe_and_categories():
    tracker = InboundEventTracker(baseline_iso="2026-07-02T11:00:00Z")
    cats = ("inbound_star", "inbound_fork")
    assert tracker.feed([repo_event("1", created="2026-07-02T10:00:00Z")], cats) == []  # before baseline
    fresh = tracker.feed([repo_event("2", created="2026-07-02T12:00:00Z")], cats)
    assert [e["id"] for e in fresh] == ["2"]
    assert tracker.feed([repo_event("2", created="2026-07-02T12:00:00Z")], cats) == []  # dedupe
    assert tracker.feed([repo_event("3", "IssuesEvent", created="2026-07-02T12:05:00Z")], cats) == []  # not star/fork
    assert tracker.feed([repo_event("4", "ForkEvent", created="2026-07-02T12:06:00Z")], ("inbound_star",)) == []
    fork = tracker.feed([repo_event("5", "ForkEvent", created="2026-07-02T12:07:00Z")], cats)
    assert [e["id"] for e in fork] == ["5"]


def test_follower_tracker_diff():
    tracker = FollowerTracker()
    assert tracker.feed(["a", "b"]) == []  # baseline
    assert tracker.feed(["a", "b", "c"]) == ["c"]
    assert tracker.feed(["a", "c"]) == []  # b unfollowed → quiet
    assert tracker.feed(["a", "c", "b"]) == ["b"]  # b refollowed → new again


# -- new fetchers with fake opener ---------------------------------------------


def test_fetch_user_login():
    def opener(request, timeout):
        assert request.get_header("Authorization") == "Bearer tok"
        return FakeResponse(200, {}, json.dumps({"login": "olya"}).encode())

    result = fetch_user_login("tok", opener=opener)
    assert result["status"] == 200 and result["login"] == "olya"


def test_fetch_user_login_401():
    def opener(request, timeout):
        raise urllib.error.HTTPError("u", 401, "no", {}, io.BytesIO(b""))

    result = fetch_user_login("bad", opener=opener)
    assert result["status"] == 401 and result["login"] == ""


def test_fetch_owned_repos_token_url_and_cap():
    def opener(request, timeout):
        assert "/user/repos" in request.full_url
        body = json.dumps([{"full_name": f"olya/r{i}"} for i in range(20)]).encode()
        return FakeResponse(200, {}, body)

    result = fetch_owned_repos("tok", "olya", cap=8, opener=opener)
    assert len(result["repos"]) == 8 and result["repos"][0] == "olya/r0"


def test_fetch_owned_repos_public_url():
    def opener(request, timeout):
        assert "/users/olya/repos" in request.full_url
        return FakeResponse(200, {}, json.dumps([{"full_name": "olya/a"}]).encode())

    result = fetch_owned_repos("", "olya", cap=8, opener=opener)
    assert result["repos"] == ["olya/a"]


def test_fetch_repo_events_and_304_is_free():
    def opener(request, timeout):
        if request.get_header("If-none-match"):
            raise urllib.error.HTTPError("u", 304, "nm", {"ETag": "E1"}, io.BytesIO(b""))
        return FakeResponse(200, {"ETag": "E1"}, json.dumps([repo_event("1")]).encode())

    first = fetch_repo_events("olya/app", opener=opener)
    assert first["status"] == 200 and first["etag"] == "E1" and len(first["items"]) == 1
    second = fetch_repo_events("olya/app", etag="E1", opener=opener)
    assert second["status"] == 304 and second["items"] == [] and second["error"] == ""


def test_fetch_followers_pagination_and_304():
    def opener(request, timeout):
        if request.get_header("If-none-match"):
            raise urllib.error.HTTPError("u", 304, "nm", {"ETag": "F1"}, io.BytesIO(b""))
        page = "page=2" in request.full_url
        logins = [] if page else [{"login": f"u{i}"} for i in range(100)]
        return FakeResponse(200, {"ETag": "F1"}, json.dumps(logins).encode())

    changed = fetch_followers("olya", opener=opener)
    assert changed["etag"] == "F1" and len(changed["logins"]) == 100
    unchanged = fetch_followers("olya", etag="F1", opener=opener)
    assert unchanged["logins"] is None  # a 304 keeps the caller's known set


def test_fetch_inbound_merges_events_and_followers():
    def opener(request, timeout):
        url = request.full_url
        if "/repos" in url and "/events" not in url:  # repo listing
            return FakeResponse(200, {}, json.dumps([{"full_name": "olya/app"}]).encode())
        if "/repos/olya/app/events" in url:
            return FakeResponse(200, {"ETag": "RE"}, json.dumps([repo_event("s1")]).encode())
        if "/followers" in url:
            return FakeResponse(200, {"ETag": "FE"}, json.dumps([{"login": "bob"}]).encode())
        raise AssertionError(url)

    result = fetch_inbound("olya", "", [], {}, "", ("inbound_star", "new_follower"), opener=opener)
    assert result["repos"] == ["olya/app"]
    assert [e["id"] for e in result["repo_events"]] == ["s1"]
    assert result["repo_etags"] == {"olya/app": "RE"}
    assert result["followers"] == ["bob"]
    assert result["followers_etag"] == "FE"


# -- multi-source notifier -----------------------------------------------------


def test_active_sources_combinations(qapp, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    both = GitHubNotifier(
        None,
        settings=GitHubSettings(enabled=True, token="t", me_login="olya", categories=("mention", "inbound_star")),
        start_timer=False,
    )
    assert both.active_sources() == {"notifications", "inbound"}
    follower_only = GitHubNotifier(
        None, settings=GitHubSettings(enabled=True, me_login="olya", categories=("new_follower",)), start_timer=False
    )
    assert follower_only.active_sources() == {"inbound"}
    outbound = GitHubNotifier(
        None, settings=GitHubSettings(enabled=True, me_login="olya", categories=("outbound",)), start_timer=False
    )
    assert outbound.active_sources() == {"public"}


def test_notifier_inbound_announces_star_and_follower(qapp):
    ann = AnnouncerStub()
    settings = GitHubSettings(enabled=True, me_login="olya", categories=("inbound_star", "new_follower"))
    notifier = GitHubNotifier(None, announcer=ann, settings=settings, start_timer=False)
    notifier.inbound_tracker.baseline = "2026-07-02T00:00:00Z"
    notifier.follower_tracker.feed(["existing"])  # baseline the follower set
    notifier.handle_result(
        {
            "mode": "inbound",
            "status": 200,
            "repo_events": [repo_event("s1", created="2026-07-02T12:00:00Z")],
            "followers": ["existing", "newbie"],
            "repos": ["olya/app"],
            "repo_etags": {},
            "followers_etag": "",
            "poll_seconds": 300,
        }
    )
    texts = [text for text, url in ann.announced]
    assert any("starred" in text for text in texts)
    assert any("new follower: newbie" in text for text in texts)


def test_401_latches_only_notifications(qapp):
    settings = GitHubSettings(enabled=True, token="bad", me_login="olya", categories=("mention", "inbound_star"))
    notifier = GitHubNotifier(None, settings=settings, start_timer=False)
    notifier.handle_result(
        {"mode": "notifications", "status": 401, "items": [], "error": "HTTP 401", "poll_seconds": 60}
    )
    assert notifier.auth_failed is True
    assert "inbound" in notifier.active_sources()  # tokenless inbound keeps working


def test_multi_account_fetch_merges_and_keeps_etags():
    from mycat.github_notify import fetch_accounts_events

    def opener(request, timeout):
        url = request.full_url
        account = url.split("/users/")[1].split("/")[0]
        body = json.dumps([public_event(f"{account}-1", "WatchEvent")]).encode()
        return FakeResponse(200, {"ETag": f"etag-{account}"}, body)

    result = fetch_accounts_events(("olya", "bob"), {}, opener=opener)
    assert result["status"] == 200
    assert {e["id"] for e in result["items"]} == {"olya-1", "bob-1"}
    assert result["etags"] == {"olya": "etag-olya", "bob": "etag-bob"}
    assert result["poll_seconds"] >= 300
