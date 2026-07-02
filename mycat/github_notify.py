#!/usr/bin/env python3
"""GitHub notifications delivered by the cat (opt-in).

Strictly bring-your-own-token, like the LLM vendors: the user pastes a
fine-grained PAT (read-only *Notifications* permission is enough) or exports
``GITHUB_TOKEN``; the client polls ``GET /notifications`` **directly against
GitHub** — no mycat server is ever in the loop. Until a token is configured
and the feature is enabled, this module makes zero network requests.

Polling etiquette follows GitHub's documentation: ``If-Modified-Since`` from
the previous response's ``Last-Modified``, a 304 means nothing new, and the
``X-Poll-Interval`` header dictates the minimum poll cadence.

The very first successful poll after startup only *baselines* the unread set
(no banners): re-announcing every old unread notification on every launch
would train the user to ignore the plane.
"""

import configparser
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore

if __package__:
    from . import secret_store
else:
    import importlib

    secret_store = importlib.import_module("mycat.secret_store")

logger = logging.getLogger(__name__)

CFG_DIR = Path.home() / ".config" / "mycat"
CFG_FILE = CFG_DIR / "config.ini"

API_URL = "https://api.github.com/notifications"
DEFAULT_POLL_SECONDS = 60
# Tokenless public mode polls the user's public received-events feed. The
# unauthenticated rate limit is 60 req/h per IP, so poll gently (a 304 on the
# ETag does not count against the limit).
PUBLIC_EVENTS_URL = "https://api.github.com/users/{username}/received_events/public"
PUBLIC_POLL_SECONDS = 300
DEFAULT_REASONS = ("review_requested", "mention", "assign")

REASON_LABELS = {
    "review_requested": "Review requested",
    "mention": "Mentioned",
    "assign": "Assigned",
    "ci_activity": "CI",
    "author": "Your thread",
    "comment": "Comment",
}


@dataclass
class GitHubSettings:
    enabled: bool = False
    token: str = ""  # literal token from config — takes priority
    token_env: str = "GITHUB_TOKEN"  # env var fallback when token is empty
    username: str = ""  # for the tokenless public mode
    reasons: tuple = DEFAULT_REASONS

    def resolve_token(self) -> str:
        if self.token:
            return self.token
        import os

        return os.getenv(self.token_env, "")


def load_github_settings(cfg_file: Path = CFG_FILE) -> GitHubSettings:
    settings = GitHubSettings()
    if not cfg_file.exists():
        return settings
    try:
        config = configparser.ConfigParser()
        config.read(cfg_file)
        if "github" not in config:
            return settings
        section = config["github"]
        settings.enabled = section.getboolean("enabled", fallback=False)
        settings.token = section.get("token", "")
        settings.token_env = section.get("token_env", settings.token_env)
        settings.username = section.get("username", "")
        raw_reasons = section.get("reasons", ",".join(DEFAULT_REASONS))
        reasons = tuple(reason.strip() for reason in raw_reasons.split(",") if reason.strip())
        settings.reasons = reasons or DEFAULT_REASONS
    except Exception as exc:  # noqa: BLE001 - never let a bad config crash the app
        logger.error("Failed to load [github] settings: %s", exc)
    return settings


def save_github_settings(settings: GitHubSettings, cfg_file: Path = CFG_FILE) -> None:
    try:
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        config = configparser.ConfigParser()
        if cfg_file.exists():
            config.read(cfg_file)
        if "github" not in config:
            config.add_section("github")
        section = config["github"]
        section["enabled"] = "true" if settings.enabled else "false"
        if settings.token:
            section["token"] = settings.token
        elif "token" in section:
            del section["token"]
        section["token_env"] = settings.token_env
        section["username"] = settings.username
        section["reasons"] = ",".join(settings.reasons)
        with open(cfg_file, "w") as fh:
            config.write(fh)
        secret_store.secure_file(cfg_file)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to save [github] settings: %s", exc)


# -- pure helpers (unit-tested without Qt or network) --------------------------


def subject_html_url(subject: dict, repository: dict) -> str:
    """Best-effort browser URL for a notification subject.

    The API hands us an *API* URL (``api.github.com/repos/o/r/pulls/1``);
    the browser wants ``github.com/o/r/pull/1``. Fall back to the repo page.
    """
    repo_html = str((repository or {}).get("html_url", "") or "https://github.com")
    api_url = str((subject or {}).get("url", "") or "")
    marker = "api.github.com/repos/"
    if marker not in api_url:
        return repo_html
    path = api_url.split(marker, 1)[1]  # "owner/repo/pulls/123"
    path = path.replace("/pulls/", "/pull/", 1).replace("/commits/", "/commit/", 1)
    return f"https://github.com/{path}"


def notification_text(item: dict) -> str:
    reason = str(item.get("reason", ""))
    label = REASON_LABELS.get(reason, reason.replace("_", " ").capitalize() or "GitHub")
    title = str((item.get("subject") or {}).get("title", "")).strip() or "(no title)"
    repo = str((item.get("repository") or {}).get("full_name", "")).strip()
    return f"{label}: {title} ({repo})" if repo else f"{label}: {title}"


class NotificationTracker:
    """Filters raw notification lists down to what deserves a banner.

    Keeps a ``thread id -> updated_at`` map; an item is announced when its id
    is new or its ``updated_at`` moved. The first feed only baselines.
    """

    def __init__(self, reasons=DEFAULT_REASONS) -> None:
        self.reasons = tuple(reasons)
        self.seen: dict[str, str] = {}
        self.baselined = False

    def feed(self, items: list) -> list:
        fresh = []
        for item in items:
            if str(item.get("reason", "")) not in self.reasons:
                continue
            thread_id = str(item.get("id", ""))
            updated_at = str(item.get("updated_at", ""))
            if not thread_id:
                continue
            if self.seen.get(thread_id) != updated_at:
                if self.baselined:
                    fresh.append(item)
                self.seen[thread_id] = updated_at
        self.baselined = True
        return fresh


EVENT_LABELS = {
    "WatchEvent": "⭐ starred",
    "ForkEvent": "🍴 forked",
    "IssuesEvent": "🐞 issue",
    "PullRequestEvent": "PR",
    "ReleaseEvent": "🚀 release",
}
PUBLIC_EVENT_TYPES = tuple(EVENT_LABELS)


def event_text(event: dict) -> str:
    """One public event as a banner line: '⭐ alice starred o/r'."""
    kind = str(event.get("type", ""))
    actor = str((event.get("actor") or {}).get("login", "")).strip() or "someone"
    repo = str((event.get("repo") or {}).get("name", "")).strip()
    payload = event.get("payload") or {}
    if kind == "IssuesEvent":
        issue = payload.get("issue") or {}
        title = str(issue.get("title", "")).strip() or f"#{issue.get('number', '?')}"
        return f"🐞 {actor}: {title} ({repo})"
    if kind == "PullRequestEvent":
        pull = payload.get("pull_request") or {}
        title = str(pull.get("title", "")).strip() or f"#{pull.get('number', '?')}"
        return f"PR by {actor}: {title} ({repo})"
    if kind == "ReleaseEvent":
        tag = str((payload.get("release") or {}).get("tag_name", "")).strip()
        return f"🚀 {repo} released {tag}"
    if kind == "WatchEvent":
        return f"⭐ {actor} starred {repo}"
    if kind == "ForkEvent":
        return f"🍴 {actor} forked {repo}"
    if kind == "PushEvent":
        return f"⬆ {actor} pushed to {repo}"
    if kind == "CreateEvent":
        ref_type = str(payload.get("ref_type", "")).strip() or "repo"
        ref = str(payload.get("ref", "") or "").strip()
        what = f"{ref_type} {ref}".strip()
        return f"✨ {actor} created {what} ({repo})"
    return f"{actor}: {kind or 'activity'} ({repo})"


def event_html_url(event: dict) -> str:
    payload = event.get("payload") or {}
    for key in ("issue", "pull_request", "release"):
        url = str((payload.get(key) or {}).get("html_url", "") or "")
        if url:
            return url
    repo = str((event.get("repo") or {}).get("name", "")).strip()
    return f"https://github.com/{repo}" if repo else "https://github.com"


def interesting_public_event(event: dict) -> bool:
    """New things only: opened issues/PRs, stars, forks, releases."""
    kind = str(event.get("type", ""))
    if kind not in PUBLIC_EVENT_TYPES:
        return False
    action = str((event.get("payload") or {}).get("action", ""))
    if kind in ("IssuesEvent", "PullRequestEvent") and action != "opened":
        return False
    return True


class PublicEventTracker:
    """Dedupe by event id; the first feed only baselines (like notifications)."""

    def __init__(self) -> None:
        self.seen: set[str] = set()
        self.baselined = False

    def feed(self, events: list) -> list:
        fresh = []
        for event in events:
            event_id = str(event.get("id", ""))
            if not event_id or event_id in self.seen:
                continue
            self.seen.add(event_id)
            if self.baselined and interesting_public_event(event):
                fresh.append(event)
        self.baselined = True
        return fresh


def fetch_public_events(username: str, etag: str = "", opener=None) -> dict:
    """One tokenless poll of the public received-events feed."""
    request = urllib.request.Request(PUBLIC_EVENTS_URL.format(username=username))
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("User-Agent", "mycat-desktop-pet")
    if etag:
        request.add_header("If-None-Match", etag)  # a 304 is free rate-limit-wise

    open_fn = opener or urllib.request.urlopen
    result = {"status": 0, "items": [], "etag": etag, "poll_seconds": PUBLIC_POLL_SECONDS, "error": ""}
    try:
        with open_fn(request, timeout=15) as response:
            result["status"] = response.status
            result["etag"] = response.headers.get("ETag", etag) or etag
            body = response.read()
            result["items"] = json.loads(body.decode("utf-8")) if body else []
    except urllib.error.HTTPError as exc:
        result["status"] = exc.code
        if exc.code != 304:
            result["error"] = f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - offline is a normal state, not a crash
        result["error"] = str(exc)
    return result


def fetch_notifications(token: str, last_modified: str = "", opener=None) -> dict:
    """One poll. Returns {status, items, last_modified, poll_seconds, error}."""
    request = urllib.request.Request(API_URL)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("User-Agent", "mycat-desktop-pet")
    if last_modified:
        request.add_header("If-Modified-Since", last_modified)

    open_fn = opener or urllib.request.urlopen
    result = {
        "status": 0,
        "items": [],
        "last_modified": last_modified,
        "poll_seconds": DEFAULT_POLL_SECONDS,
        "error": "",
    }
    try:
        with open_fn(request, timeout=15) as response:
            result["status"] = response.status
            result["last_modified"] = response.headers.get("Last-Modified", last_modified) or last_modified
            result["poll_seconds"] = parse_poll_interval(response.headers.get("X-Poll-Interval"))
            body = response.read()
            result["items"] = json.loads(body.decode("utf-8")) if body else []
    except urllib.error.HTTPError as exc:
        result["status"] = exc.code
        if exc.code == 304:
            result["poll_seconds"] = parse_poll_interval(exc.headers.get("X-Poll-Interval"))
        else:
            result["error"] = f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - offline is a normal state, not a crash
        result["error"] = str(exc)
    return result


def parse_poll_interval(raw) -> int:
    try:
        return max(DEFAULT_POLL_SECONDS, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_POLL_SECONDS


# -- Qt poller ------------------------------------------------------------------


class PollWorker(QtCore.QRunnable):
    """Runs one fetch off the UI thread and reports back via a signal.

    ``mode`` is "notifications" (token) or "public" (username only); the
    matching cache header (Last-Modified / ETag) travels in ``cache_key``.
    """

    class Emitter(QtCore.QObject):
        finished = QtCore.Signal(dict)

    def __init__(self, token: str, cache_key: str, mode: str = "notifications", username: str = "") -> None:
        super().__init__()
        self.token = token
        self.cache_key = cache_key
        self.mode = mode
        self.username = username
        self.emitter = PollWorker.Emitter()

    def run(self) -> None:
        if self.mode == "public":
            result = fetch_public_events(self.username, self.cache_key)
        else:
            result = fetch_notifications(self.token, self.cache_key)
        result["mode"] = self.mode
        self.emitter.finished.emit(result)


class GitHubNotifier(QtCore.QObject):
    """Polls GitHub and feeds the announcer.

    Two modes: with a token — your private notification inbox (review
    requests, mentions, assignments); without a token but with a username —
    only PUBLIC activity from that account's public feed (stars, forks, new
    issues/PRs, releases). No token and no username → zero requests.
    """

    def __init__(self, window, announcer=None, settings=None, start_timer=True) -> None:
        super().__init__(window if isinstance(window, QtCore.QObject) else None)
        self.window = window
        self.announcer = announcer
        self.settings = settings if settings is not None else load_github_settings()
        self.tracker = NotificationTracker(self.settings.reasons)
        self.public_tracker = PublicEventTracker()
        self.last_modified = ""
        self.etag = ""
        self.poll_seconds = DEFAULT_POLL_SECONDS
        self.polling = False  # a worker is in flight
        self.auth_failed = False

        self.timer = None
        if start_timer:
            self.timer = QtCore.QTimer(self)
            self.timer.setInterval(self.poll_seconds * 1000)
            self.timer.timeout.connect(self.poll)
            self.timer.start()
            # First poll shortly after startup (don't block the launch path).
            QtCore.QTimer.singleShot(3000, self.poll)

    def apply_settings(self, settings: GitHubSettings) -> None:
        """Called by the settings dialog after a save."""
        self.settings = settings
        self.tracker = NotificationTracker(settings.reasons)
        self.public_tracker = PublicEventTracker()
        self.last_modified = ""
        self.etag = ""
        self.auth_failed = False

    def mode(self) -> str:
        """"notifications" (token), "public" (username only) or "" (idle)."""
        if self.settings.resolve_token():
            return "notifications"
        if self.settings.username.strip():
            return "public"
        return ""

    def poll(self) -> None:
        if self.polling or not self.settings.enabled or self.auth_failed:
            return
        mode = self.mode()
        if not mode:
            return
        self.polling = True
        if mode == "public":
            worker = PollWorker("", self.etag, mode="public", username=self.settings.username.strip())
        else:
            worker = PollWorker(self.settings.resolve_token(), self.last_modified)
        worker.emitter.finished.connect(self.handle_result)
        QtCore.QThreadPool.globalInstance().start(worker)

    def handle_result(self, result: dict) -> None:
        self.polling = False
        self.poll_seconds = int(result.get("poll_seconds", DEFAULT_POLL_SECONDS))
        if self.timer is not None:
            self.timer.setInterval(self.poll_seconds * 1000)

        status = int(result.get("status", 0))
        if status == 401:
            # A rejected token would otherwise retry forever; stop until the
            # user re-opens the settings dialog (apply_settings resets this).
            self.auth_failed = True
            logger.warning("GitHub token rejected (401); polling paused until settings change")
            return
        if result.get("error"):
            logger.debug("GitHub poll failed: %s", result["error"])
            return
        if status == 304:
            return

        if result.get("mode") == "public":
            self.etag = str(result.get("etag", ""))
            for event in self.public_tracker.feed(list(result.get("items", []))):
                text = event_text(event)
                logger.info("GitHub public event: %s", text)
                if self.announcer is not None:
                    self.announcer.announce(text, url=event_html_url(event))
            return

        self.last_modified = str(result.get("last_modified", ""))
        fresh = self.tracker.feed(list(result.get("items", [])))
        for item in fresh:
            text = notification_text(item)
            url = subject_html_url(item.get("subject") or {}, item.get("repository") or {})
            logger.info("GitHub notification: %s", text)
            if self.announcer is not None:
                self.announcer.announce(text, url=url)


__all__ = [
    "GitHubNotifier",
    "GitHubSettings",
    "NotificationTracker",
    "PublicEventTracker",
    "load_github_settings",
    "save_github_settings",
    "fetch_notifications",
    "fetch_public_events",
    "notification_text",
    "event_text",
    "event_html_url",
    "interesting_public_event",
    "subject_html_url",
    "parse_poll_interval",
    "DEFAULT_REASONS",
]
