#!/usr/bin/env python3
"""GitHub notifications delivered by the cat (opt-in).

Three independent data sources, each selectable per category with a checkbox:

- **inbox** (needs a token): review requests, mentions, assignments, CI, and
  Issue/PR activity — the private ``GET /notifications`` feed, filtered by
  ``reason`` and ``subject.type``;
- **your account, public** (no token): someone stars your repo, forks it, or
  follows you — the inbound poller (per-repo ``/repos/{owner}/{repo}/events``
  plus a ``/users/{login}/followers`` diff);
- **outbound** (no token): your own stars and follows — the account's own
  ``/users/{login}/events/public`` feed. The same feed also carries the public
  activity of any *other* accounts you list ("also follow").

Everything polls **directly against GitHub** — no mycat server is ever in the
loop. Until the feature is enabled and at least one source is configured, this
module makes zero network requests.

Polling etiquette follows GitHub's docs: ``If-Modified-Since`` / ``If-None-Match``
conditional requests (a 304 is free rate-limit-wise), and ``X-Poll-Interval``
sets the cadence for the inbox. Every source **baselines silently on its first
poll** — re-announcing old activity on each launch would train the user to
ignore the plane.

Main-thread only for announcing: pollers run in worker threads and hand their
results to the GUI thread via a Qt signal before anything is announced.
"""

import configparser
import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PySide6 import QtCore

if __package__:
    from . import config_store, github_api, paths, secret_store
else:
    import importlib

    config_store = importlib.import_module("mycat.config_store")
    github_api = importlib.import_module("mycat.github_api")
    secret_store = importlib.import_module("mycat.secret_store")
    paths = importlib.import_module("mycat.paths")

logger = logging.getLogger(__name__)

CFG_DIR = paths.config_dir()
CFG_FILE = paths.config_file()

API_URL = "https://api.github.com/notifications"
USER_URL = "https://api.github.com/user"
OWNED_REPOS_URL = "https://api.github.com/user/repos?affiliation=owner&sort=pushed&per_page=100"
PUBLIC_REPOS_URL = "https://api.github.com/users/{login}/repos?sort=pushed&per_page=100"
REPO_EVENTS_URL = "https://api.github.com/repos/{full_name}/events"
FOLLOWERS_URL = "https://api.github.com/users/{login}/followers?per_page=100&page={page}"
PUBLIC_EVENTS_URL = "https://api.github.com/users/{account}/events/public"

DEFAULT_POLL_SECONDS = 60
PUBLIC_POLL_SECONDS = 300
# The inbound poller multiplies requests by the watched-repo count, so it is
# paced far more gently. The anonymous limit is 60 req/h per IP; a token lifts
# it to 5000/h, which is why the interval and caps loosen when one is present.
INBOUND_POLL_SECONDS_TOKENLESS = 1800
INBOUND_POLL_SECONDS_TOKEN = 300
REPO_CAP_TOKENLESS = 8
REPO_CAP_TOKEN = 40
FOLLOWERS_MAX_PAGES_TOKENLESS = 3
FOLLOWERS_MAX_PAGES_TOKEN = 10
REPO_LIST_TTL_SECONDS = 6 * 3600
BASE_TICK_SECONDS = 30
RATE_LIMIT_COOLDOWN_SECONDS = 900


# -- category model ------------------------------------------------------------
#
# One checkbox per category. Six live in the token-only inbox; four work
# tokenless off public endpoints. The source that produces an item owns its
# text rendering — this table only declares identity, label, and token need.

INBOX_CATEGORIES = ("review_requested", "mention", "assign", "ci_activity", "issue", "pull_request")
INBOUND_REPO_CATEGORIES = ("inbound_star", "inbound_fork")
FOLLOWER_CATEGORY = "new_follower"
OUTBOUND_CATEGORY = "outbound"
PUBLIC_CATEGORIES = ("inbound_star", "inbound_fork", "new_follower", "outbound")

CATEGORY_LABELS = {
    "review_requested": "Review requested",
    "mention": "Mentions",
    "assign": "Assigned to me",
    "ci_activity": "CI status",
    "issue": "Issue activity",
    "pull_request": "PR activity",
    "inbound_star": "Star on my repo",
    "inbound_fork": "Fork of my repo",
    "new_follower": "New follower",
    "outbound": "My stars & follows",
}

# A fresh install announces the public events that need only a username; the
# token-only inbox categories start OFF (they would be inert without a token).
DEFAULT_CATEGORIES = PUBLIC_CATEGORIES
# The legacy inbox default — used by the config migration and back-compat imports.
DEFAULT_REASONS = ("review_requested", "mention", "assign")

# Still used by notification_text for its human label.
REASON_LABELS = {
    "review_requested": "Review requested",
    "mention": "Mentioned",
    "assign": "Assigned",
    "ci_activity": "CI",
    "author": "Your thread",
    "comment": "Comment",
}


def parse_accounts(raw: str) -> tuple:
    """Comma-separated usernames → a clean tuple ("olya, bob" → ("olya","bob"))."""
    return tuple(account.strip() for account in str(raw or "").split(",") if account.strip())


def now_iso() -> str:
    """Current UTC time as a GitHub-style ISO stamp, for baseline comparisons."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class GitHubSettings:
    enabled: bool = False
    token: str = ""  # literal token from config — takes priority
    token_env: str = "GITHUB_TOKEN"  # env var fallback when token is empty
    accounts: str = ""  # comma-separated OTHER accounts to follow (public)
    me_login: str = ""  # your own login — drives inbound + your outbound feed
    categories: tuple = DEFAULT_CATEGORIES
    token_verified: bool = False  # a UI gate: the inbox checkboxes unlock on a good Test

    def resolve_token(self) -> str:
        return github_api.resolve_token(self.token, self.token_env)


def load_github_settings(cfg_file: Path = CFG_FILE) -> GitHubSettings:
    settings = GitHubSettings()
    config = config_store.read_config(cfg_file)
    if config is None or "github" not in config:
        return settings
    try:
        section = config["github"]
        settings.enabled = section.getboolean("enabled", fallback=False)
        settings.token = section.get("token", "")
        settings.token_env = section.get("token_env", settings.token_env)
        # "accounts" is the current key; fall back to the older "username".
        settings.accounts = section.get("accounts", "") or section.get("username", "")
        settings.me_login = section.get("me_login", "")
        settings.token_verified = section.getboolean("token_verified", fallback=False)
        # "categories" is the current key; fall back to the legacy "reasons"
        # (its values map 1:1 to the inbox category keys).
        raw = section.get("categories", "") or section.get("reasons", ",".join(DEFAULT_CATEGORIES))
        categories = tuple(item.strip() for item in raw.split(",") if item.strip())
        settings.categories = categories or DEFAULT_CATEGORIES
    except (ValueError, TypeError) as exc:  # a malformed value -> keep the defaults
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
        section["accounts"] = settings.accounts
        section["me_login"] = settings.me_login
        section["categories"] = ",".join(settings.categories)
        section["token_verified"] = "true" if settings.token_verified else "false"
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


def notification_category(item: dict) -> str:
    """The category key an inbox item belongs to, or "" if none.

    ``reason`` never distinguishes an Issue from a PR — that is ``subject.type``
    — so the two are matched on the subject while the rest match on the reason.
    """
    reason = str(item.get("reason", ""))
    subject_type = str((item.get("subject") or {}).get("type", ""))
    if reason == "review_requested":
        return "review_requested"
    if reason in ("mention", "team_mention"):
        return "mention"
    if reason == "assign":
        return "assign"
    if reason == "ci_activity":
        return "ci_activity"
    if subject_type == "Issue":
        return "issue"
    if subject_type == "PullRequest":
        return "pull_request"
    return ""


def notification_matches(item: dict, categories) -> bool:
    """True when the item's category is among the selected inbox categories."""
    category = notification_category(item)
    return bool(category) and category in set(categories)


class NotificationTracker:
    """Filters raw notification lists down to what deserves a banner.

    Keeps a ``thread id -> updated_at`` map; an item is announced when its id
    is new or its ``updated_at`` moved. The first feed only baselines. An item
    matching several selected categories still fires once (dedupe is by id).
    """

    def __init__(self, categories=INBOX_CATEGORIES) -> None:
        self.categories = tuple(categories)
        self.seen: dict[str, str] = {}
        self.baselined = False

    def feed(self, items: list) -> list:
        fresh = []
        for item in items:
            if not notification_matches(item, self.categories):
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
    "FollowEvent": "👤 followed",
}
PUBLIC_EVENT_TYPES = ("WatchEvent", "ForkEvent", "IssuesEvent", "PullRequestEvent", "ReleaseEvent")


def event_text(event: dict) -> str:
    """One public/repo event as a banner line: '⭐ alice starred o/r'."""
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
    if kind == "FollowEvent":
        target = str((payload.get("target") or {}).get("login", "")).strip()
        return f"👤 {actor} followed {target}" if target else f"👤 {actor} followed someone"
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
    if str(event.get("type", "")) == "FollowEvent":
        target = payload.get("target") or {}
        url = str(target.get("html_url", "") or "")
        login = str(target.get("login", "") or "")
        if url:
            return url
        if login:
            return f"https://github.com/{login}"
    for key in ("issue", "pull_request", "release"):
        url = str((payload.get(key) or {}).get("html_url", "") or "")
        if url:
            return url
    repo = str((event.get("repo") or {}).get("name", "")).strip()
    return f"https://github.com/{repo}" if repo else "https://github.com"


def follower_text(login: str) -> str:
    return f"➕ new follower: {login}"


def follower_html_url(login: str) -> str:
    return f"https://github.com/{login}" if login else "https://github.com"


def interesting_public_event(event: dict) -> bool:
    """New things only: opened issues/PRs, stars, forks, releases."""
    kind = str(event.get("type", ""))
    if kind not in PUBLIC_EVENT_TYPES:
        return False
    action = str((event.get("payload") or {}).get("action", ""))
    if kind in ("IssuesEvent", "PullRequestEvent") and action != "opened":
        return False
    return True


def public_event_interesting(event: dict, me_login: str) -> bool:
    """Interest rule for the public feed.

    Your OWN feed (actor == you) only cares about the outbound social events
    you performed (stars, follows); any OTHER account you follow keeps the
    broader "something new happened" filter.
    """
    actor = str((event.get("actor") or {}).get("login", "")).strip().lower()
    if me_login and actor == me_login.strip().lower():
        return str(event.get("type", "")) in ("WatchEvent", "FollowEvent")
    return interesting_public_event(event)


class PublicEventTracker:
    """Dedupe by event id; the first feed only baselines (like notifications).

    ``interest_fn`` decides which events are announced; it defaults to the
    broad public filter so existing callers are unaffected.
    """

    def __init__(self) -> None:
        self.seen: set[str] = set()
        self.baselined = False

    def feed(self, events: list, interest_fn=interesting_public_event) -> list:
        fresh = []
        for event in events:
            event_id = str(event.get("id", ""))
            if not event_id or event_id in self.seen:
                continue
            self.seen.add(event_id)
            if self.baselined and interest_fn(event):
                fresh.append(event)
        self.baselined = True
        return fresh


class InboundEventTracker:
    """Inbound repo events (someone stars/forks MY repo).

    Deduped by event id and gated by a wall-clock baseline: only events created
    after the tracker was built are announced. That both suppresses startup
    spam and stops a repo added to the watch set later from replaying its
    history — its old events predate the baseline.
    """

    def __init__(self, baseline_iso: str = "") -> None:
        self.seen: set[str] = set()
        self.baseline = str(baseline_iso or "")
        self.kinds = {"WatchEvent": "inbound_star", "ForkEvent": "inbound_fork"}

    def feed(self, events: list, categories) -> list:
        wanted = set(categories)
        fresh = []
        for event in events:
            event_id = str(event.get("id", ""))
            if not event_id or event_id in self.seen:
                continue
            self.seen.add(event_id)
            category = self.kinds.get(str(event.get("type", "")))
            if category is None or category not in wanted:
                continue
            created = str(event.get("created_at", ""))
            if self.baseline and created and created <= self.baseline:
                continue
            fresh.append(event)
        return fresh


class FollowerTracker:
    """Announces logins that appear in the followers set after the baseline.

    ``known`` mirrors the *current* set each feed (not a running union), so an
    unfollow-then-refollow announces again and a drop-off stays quiet. A feed of
    ``None`` (an unchanged 304) never reaches here — the caller skips it.
    """

    def __init__(self) -> None:
        self.known: set[str] = set()
        self.baselined = False

    def feed(self, logins: list) -> list:
        current = {str(login).lower() for login in logins if str(login).strip()}
        if not self.baselined:
            self.known = current
            self.baselined = True
            return []
        fresh = [login for login in logins if str(login).strip() and str(login).lower() not in self.known]
        self.known = current
        return fresh


# -- fetchers ------------------------------------------------------------------


def github_request(url: str, token: str = "", etag: str = "", last_modified: str = ""):
    return github_api.build_request(url, token=token, etag=etag, last_modified=last_modified)


def rate_limit_reset(headers) -> int:
    try:
        remaining = int(headers.get("X-RateLimit-Remaining", "1"))
    except (TypeError, ValueError):
        remaining = 1
    if remaining > 0:
        return 0
    try:
        return int(headers.get("X-RateLimit-Reset", "0"))
    except (TypeError, ValueError):
        return 0


def fetch_user_login(token: str, opener=None) -> dict:
    """Resolve the authenticated user's login (identity for 'me')."""
    open_fn = opener or urllib.request.urlopen
    result = {"status": 0, "login": "", "error": ""}
    try:
        with open_fn(github_request(USER_URL, token=token), timeout=15) as response:
            result["status"] = response.status
            body = response.read()
            data = json.loads(body.decode("utf-8")) if body else {}
            result["login"] = str(data.get("login", "") or "")
    except urllib.error.HTTPError as exc:
        result["status"] = exc.code
        result["error"] = f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result


def fetch_verify(token: str, opener=None) -> dict:
    """Validate a token: resolve the login and sample the inbox for the banner."""
    who = fetch_user_login(token, opener)
    if who["status"] != 200 or who.get("error"):
        return {"status": who["status"], "login": "", "items": [], "error": who.get("error") or "verify failed"}
    sample = fetch_notifications(token, "", opener)
    return {"status": 200, "login": who["login"], "items": list(sample.get("items", [])), "error": ""}


def fetch_owned_repos(token: str, login: str, cap: int, opener=None) -> dict:
    """Full names of the repos to watch for inbound stars/forks."""
    url = OWNED_REPOS_URL if token else PUBLIC_REPOS_URL.format(login=login)
    open_fn = opener or urllib.request.urlopen
    result = {"status": 0, "repos": [], "error": ""}
    try:
        with open_fn(github_request(url, token=token), timeout=15) as response:
            result["status"] = response.status
            body = response.read()
            data = json.loads(body.decode("utf-8")) if body else []
            names = [str(repo.get("full_name", "")).strip() for repo in data if repo.get("full_name")]
            result["repos"] = names[:cap]
    except urllib.error.HTTPError as exc:
        result["status"] = exc.code
        result["error"] = f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result


def fetch_repo_events(full_name: str, etag: str = "", token: str = "", opener=None) -> dict:
    """One repo's recent events (stars/forks/issues/PRs by anyone). ETagged."""
    open_fn = opener or urllib.request.urlopen
    result = {"status": 0, "items": [], "etag": etag, "reset": 0, "error": ""}
    try:
        with open_fn(
            github_request(REPO_EVENTS_URL.format(full_name=full_name), token=token, etag=etag), timeout=15
        ) as response:
            result["status"] = response.status
            result["etag"] = response.headers.get("ETag", etag) or etag
            body = response.read()
            result["items"] = json.loads(body.decode("utf-8")) if body else []
    except urllib.error.HTTPError as exc:
        result["status"] = exc.code
        if exc.code == 304:
            pass  # unchanged: free, keep the old etag
        elif exc.code == 403:
            result["reset"] = rate_limit_reset(exc.headers)
            result["error"] = "rate limited"
        else:
            result["error"] = f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result


def fetch_followers(
    login: str, token: str = "", etag: str = "", max_pages: int = FOLLOWERS_MAX_PAGES_TOKENLESS, opener=None
) -> dict:
    """Current followers, paginated. Page 1 is ETagged: a 304 means unchanged,
    reported as ``logins = None`` so the caller keeps its known set."""
    open_fn = opener or urllib.request.urlopen
    result = {"status": 0, "logins": None, "etag": etag, "reset": 0, "error": ""}
    logins: list[str] = []
    try:
        with open_fn(
            github_request(FOLLOWERS_URL.format(login=login, page=1), token=token, etag=etag), timeout=15
        ) as response:
            result["status"] = response.status
            result["etag"] = response.headers.get("ETag", etag) or etag
            body = response.read()
            page = json.loads(body.decode("utf-8")) if body else []
            logins.extend(str(user.get("login", "")).strip() for user in page if user.get("login"))
            more = len(page) >= 100
    except urllib.error.HTTPError as exc:
        result["status"] = exc.code
        if exc.code == 304:
            return result  # unchanged
        if exc.code == 403:
            result["reset"] = rate_limit_reset(exc.headers)
            result["error"] = "rate limited"
        else:
            result["error"] = f"HTTP {exc.code}"
        return result
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        return result

    pages_read = 1
    while more and pages_read < max_pages:
        pages_read += 1
        try:
            with open_fn(
                github_request(FOLLOWERS_URL.format(login=login, page=pages_read), token=token), timeout=15
            ) as response:
                body = response.read()
                page = json.loads(body.decode("utf-8")) if body else []
                logins.extend(str(user.get("login", "")).strip() for user in page if user.get("login"))
                more = len(page) >= 100
        except Exception as exc:  # noqa: BLE001 - a partial follower list is still useful
            result["error"] = str(exc)
            break
    result["logins"] = logins
    return result


def fetch_inbound(
    login: str, token: str, repos, repo_etags: dict, followers_etag: str, categories, opener=None
) -> dict:
    """One off-thread pass over the inbound sources: per-repo events + followers.

    ``repos`` empty forces a repo-list refresh; the fresh list rides back in the
    result so the notifier can cache it.
    """
    cap = REPO_CAP_TOKEN if token else REPO_CAP_TOKENLESS
    max_pages = FOLLOWERS_MAX_PAGES_TOKEN if token else FOLLOWERS_MAX_PAGES_TOKENLESS
    wanted = set(categories)
    result = {
        "status": 200,
        "repo_events": [],
        "followers": None,
        "repos": list(repos),
        "repo_etags": dict(repo_etags or {}),
        "followers_etag": followers_etag,
        "poll_seconds": INBOUND_POLL_SECONDS_TOKEN if token else INBOUND_POLL_SECONDS_TOKENLESS,
        "reset": 0,
        "error": "",
    }
    errors = []

    watch = list(repos)
    if not watch:
        listing = fetch_owned_repos(token, login, cap, opener)
        if listing.get("error"):
            errors.append(f"repos: {listing['error']}")
            if listing["status"] in (401, 403):
                result["status"] = listing["status"]
        watch = listing["repos"]
        result["repos"] = watch

    if wanted & set(INBOUND_REPO_CATEGORIES):
        for full_name in watch[:cap]:
            repo_result = fetch_repo_events(full_name, result["repo_etags"].get(full_name, ""), token, opener)
            result["repo_etags"][full_name] = repo_result["etag"]
            if repo_result.get("error"):
                errors.append(f"{full_name}: {repo_result['error']}")
                if repo_result["status"] == 403:
                    result["status"] = 403
                    result["reset"] = repo_result["reset"]
            else:
                result["repo_events"].extend(repo_result["items"])

    if FOLLOWER_CATEGORY in wanted:
        followers = fetch_followers(login, token, followers_etag, max_pages, opener)
        result["followers"] = followers.get("logins")
        result["followers_etag"] = followers.get("etag", followers_etag)
        if followers.get("error"):
            errors.append(f"followers: {followers['error']}")
            if followers["status"] == 403:
                result["status"] = 403
                result["reset"] = followers["reset"]

    quiet = not result["repo_events"] and result["followers"] is None
    result["error"] = "; ".join(errors) if errors and quiet else ""
    result["warnings"] = "; ".join(errors)
    return result


def fetch_account_events(account: str, etag: str = "", opener=None) -> dict:
    """One tokenless poll of ONE account's own public events."""
    open_fn = opener or urllib.request.urlopen
    result = {"status": 0, "items": [], "etag": etag, "error": ""}
    try:
        with open_fn(github_request(PUBLIC_EVENTS_URL.format(account=account), etag=etag), timeout=15) as response:
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


def fetch_accounts_events(accounts, etags: dict, opener=None) -> dict:
    """Poll every listed account; merge their events newest-first.

    Per-account ETags ride along so unchanged feeds cost no rate limit. The
    poll interval stretches with the account count to stay well inside the
    anonymous 60 req/h budget.
    """
    items = []
    new_etags = {}
    errors = []
    for account in accounts:
        result = fetch_account_events(account, etags.get(account, ""), opener)
        new_etags[account] = result["etag"]
        if result["error"]:
            errors.append(f"{account}: {result['error']}")
        items.extend(result["items"])
    items.sort(key=lambda event: str(event.get("created_at", "")), reverse=True)
    return {
        "status": 200,
        "items": items,
        "etags": new_etags,
        "poll_seconds": max(PUBLIC_POLL_SECONDS, 90 * max(1, len(accounts))),
        # Only a total failure is an error; a single typo'd account rides
        # along as a warning so the healthy accounts keep working.
        "error": "; ".join(errors) if errors and not items else "",
        "warnings": "; ".join(errors),
    }


def fetch_notifications(token: str, last_modified: str = "", opener=None) -> dict:
    """One poll. Returns {status, items, last_modified, poll_seconds, error}."""
    open_fn = opener or urllib.request.urlopen
    result = {
        "status": 0,
        "items": [],
        "last_modified": last_modified,
        "poll_seconds": DEFAULT_POLL_SECONDS,
        "error": "",
    }
    try:
        with open_fn(github_request(API_URL, token=token, last_modified=last_modified), timeout=15) as response:
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

    ``mode`` selects the source: "notifications" (token inbox), "public"
    (account events), "inbound" (repo events + followers), or "verify"
    (validate a token and resolve the login). The result dict carries ``mode``
    back so the notifier can route it.
    """

    class Emitter(QtCore.QObject):
        finished = QtCore.Signal(dict)

    def __init__(
        self,
        token: str = "",
        cache_key: str = "",
        mode: str = "notifications",
        accounts=(),
        etags=None,
        login: str = "",
        repos=(),
        repo_etags=None,
        followers_etag: str = "",
        categories=(),
    ) -> None:
        super().__init__()
        self.token = token
        self.cache_key = cache_key
        self.mode = mode
        self.accounts = tuple(accounts)
        self.etags = dict(etags or {})
        self.login = login
        self.repos = tuple(repos)
        self.repo_etags = dict(repo_etags or {})
        self.followers_etag = followers_etag
        self.categories = tuple(categories)
        self.emitter = PollWorker.Emitter()

    def run(self) -> None:
        if self.mode == "public":
            result = fetch_accounts_events(self.accounts, self.etags)
        elif self.mode == "verify":
            result = fetch_verify(self.token)
        elif self.mode == "inbound":
            result = fetch_inbound(
                self.login, self.token, list(self.repos), self.repo_etags, self.followers_etag, self.categories
            )
        else:
            result = fetch_notifications(self.token, self.cache_key)
        result["mode"] = self.mode
        self.emitter.finished.emit(result)


class GitHubNotifier(QtCore.QObject):
    """Polls GitHub's three sources and feeds the announcer.

    Each source is scheduled independently on its own interval so their
    cadences don't fight; a single base-tick timer launches whichever sources
    are due. Categories decide which sources are active at all.
    """

    def __init__(self, window, announcer=None, settings=None, start_timer=True, clock=time.monotonic) -> None:
        super().__init__(window if isinstance(window, QtCore.QObject) else None)
        self.window = window
        self.announcer = announcer
        self.settings = settings if settings is not None else load_github_settings()
        self.clock = clock
        self.build_trackers()
        self.last_modified = ""
        self.account_etags: dict = {}
        self.repo_etags: dict = {}
        self.followers_etag = ""
        self.repos: list = []
        self.repos_fetched_at = 0.0
        self.in_flight: set = set()
        self.next_due: dict = {}
        self.source_interval = {
            "notifications": DEFAULT_POLL_SECONDS,
            "public": PUBLIC_POLL_SECONDS,
            "inbound": self.inbound_interval(),
        }
        self.auth_failed = False  # a rejected token latches the inbox source only

        self.timer = None
        if start_timer:
            self.timer = QtCore.QTimer(self)
            self.timer.setInterval(BASE_TICK_SECONDS * 1000)
            self.timer.timeout.connect(self.poll)
            self.timer.start()
            # First poll shortly after startup (don't block the launch path).
            QtCore.QTimer.singleShot(3000, self.poll)

    # -- setup / state ---------------------------------------------------------

    def build_trackers(self) -> None:
        self.tracker = NotificationTracker(self.settings.categories)
        self.public_tracker = PublicEventTracker()
        self.inbound_tracker = InboundEventTracker(now_iso())
        self.follower_tracker = FollowerTracker()

    def inbound_interval(self) -> int:
        return INBOUND_POLL_SECONDS_TOKEN if self.settings.resolve_token() else INBOUND_POLL_SECONDS_TOKENLESS

    @property
    def polling(self) -> bool:
        return bool(self.in_flight)

    def me(self) -> str:
        return (self.settings.me_login or "").strip()

    def foreign_accounts(self) -> tuple:
        me = self.me().lower()
        return tuple(account for account in parse_accounts(self.settings.accounts) if account.lower() != me)

    def public_accounts(self) -> list:
        accounts = list(self.foreign_accounts())
        if OUTBOUND_CATEGORY in set(self.settings.categories) and self.me():
            accounts.append(self.me())
        return accounts

    def active_sources(self) -> set:
        sources: set = set()
        if not self.settings.enabled:
            return sources
        categories = set(self.settings.categories)
        token = self.settings.resolve_token()
        me = self.me()
        if token and (categories & set(INBOX_CATEGORIES)):
            sources.add("notifications")
        if (OUTBOUND_CATEGORY in categories and me) or self.foreign_accounts():
            sources.add("public")
        if me and (categories & (set(INBOUND_REPO_CATEGORIES) | {FOLLOWER_CATEGORY})):
            sources.add("inbound")
        return sources

    def mode(self) -> str:
        """A representative single source, for callers that want one label."""
        sources = self.active_sources()
        for source in ("notifications", "public", "inbound"):
            if source in sources:
                return source
        return ""

    def apply_settings(self, settings: GitHubSettings) -> None:
        """Called by the settings dialog after a save."""
        self.settings = settings
        self.build_trackers()
        self.last_modified = ""
        self.account_etags = {}
        self.repo_etags = {}
        self.followers_etag = ""
        self.repos = []
        self.repos_fetched_at = 0.0
        self.in_flight = set()
        self.next_due = {}
        self.source_interval = {
            "notifications": DEFAULT_POLL_SECONDS,
            "public": PUBLIC_POLL_SECONDS,
            "inbound": self.inbound_interval(),
        }
        self.auth_failed = False

    # -- scheduling ------------------------------------------------------------

    def poll(self) -> None:
        if not self.settings.enabled:
            return
        now = self.clock()
        for source in self.active_sources():
            if source in self.in_flight:
                continue
            if source == "notifications" and self.auth_failed:
                continue
            if now < self.next_due.get(source, 0.0):
                continue
            self.launch(source)

    def current_repos(self) -> list:
        now = self.clock()
        if self.repos_fetched_at > 0 and (now - self.repos_fetched_at) < REPO_LIST_TTL_SECONDS:
            return list(self.repos)
        return []  # stale/never-fetched → force a refresh in the worker

    def launch(self, source: str) -> None:
        token = self.settings.resolve_token()
        if source == "public":
            worker = PollWorker("", "", mode="public", accounts=self.public_accounts(), etags=self.account_etags)
        elif source == "inbound":
            worker = PollWorker(
                token,
                "",
                mode="inbound",
                login=self.me(),
                repos=self.current_repos(),
                repo_etags=self.repo_etags,
                followers_etag=self.followers_etag,
                categories=self.settings.categories,
            )
        else:
            worker = PollWorker(token, self.last_modified, mode="notifications")
        self.in_flight.add(source)
        worker.emitter.finished.connect(self.handle_result)
        QtCore.QThreadPool.globalInstance().start(worker)

    # -- result handling -------------------------------------------------------

    def emit(self, text: str, url: str) -> None:
        if self.announcer is not None:
            self.announcer.announce(text, url=url)

    def handle_result(self, result: dict) -> None:
        source = str(result.get("mode", "notifications"))
        self.in_flight.discard(source)
        status = int(result.get("status", 0))
        interval = int(result.get("poll_seconds", self.source_interval.get(source, DEFAULT_POLL_SECONDS)))
        self.source_interval[source] = interval
        now = self.clock()

        if status == 403:
            self.next_due[source] = now + max(interval, RATE_LIMIT_COOLDOWN_SECONDS)
            logger.debug("GitHub %s rate-limited; backing off", source)
            return
        self.next_due[source] = now + interval

        if status == 401:
            if source == "notifications":
                self.auth_failed = True
                logger.warning("GitHub token rejected (401); inbox paused until settings change")
            else:
                logger.debug("GitHub %s got 401", source)
            return
        if result.get("error"):
            logger.debug("GitHub %s poll failed: %s", source, result["error"])
            return
        if status == 304:
            return

        if source == "public":
            self.handle_public(result)
        elif source == "inbound":
            self.handle_inbound(result)
        else:
            self.handle_notifications(result)

    def handle_notifications(self, result: dict) -> None:
        self.last_modified = str(result.get("last_modified", self.last_modified))
        for item in self.tracker.feed(list(result.get("items", []))):
            text = notification_text(item)
            url = subject_html_url(item.get("subject") or {}, item.get("repository") or {})
            logger.info("GitHub notification: %s", text)
            self.emit(text, url)

    def handle_public(self, result: dict) -> None:
        self.account_etags = dict(result.get("etags", self.account_etags))
        if result.get("warnings"):
            logger.debug("GitHub public poll warnings: %s", result["warnings"])
        me = self.me()

        def interest(event):
            return public_event_interesting(event, me)

        for event in self.public_tracker.feed(list(result.get("items", [])), interest):
            text = event_text(event)
            logger.info("GitHub public event: %s", text)
            self.emit(text, event_html_url(event))

    def handle_inbound(self, result: dict) -> None:
        self.repos = list(result.get("repos", self.repos))
        self.repos_fetched_at = self.clock()
        self.repo_etags = dict(result.get("repo_etags", self.repo_etags))
        self.followers_etag = str(result.get("followers_etag", self.followers_etag))
        if result.get("warnings"):
            logger.debug("GitHub inbound poll warnings: %s", result["warnings"])

        for event in self.inbound_tracker.feed(list(result.get("repo_events", [])), set(self.settings.categories)):
            text = event_text(event)
            logger.info("GitHub inbound event: %s", text)
            self.emit(text, event_html_url(event))

        followers = result.get("followers")
        if followers is not None:
            for login in self.follower_tracker.feed(list(followers)):
                logger.info("GitHub new follower: %s", login)
                self.emit(follower_text(login), follower_html_url(login))


__all__ = [
    "GitHubNotifier",
    "GitHubSettings",
    "NotificationTracker",
    "PublicEventTracker",
    "InboundEventTracker",
    "FollowerTracker",
    "load_github_settings",
    "save_github_settings",
    "parse_accounts",
    "fetch_notifications",
    "fetch_account_events",
    "fetch_accounts_events",
    "fetch_user_login",
    "fetch_verify",
    "fetch_owned_repos",
    "fetch_repo_events",
    "fetch_followers",
    "fetch_inbound",
    "notification_text",
    "notification_category",
    "notification_matches",
    "event_text",
    "event_html_url",
    "follower_text",
    "follower_html_url",
    "interesting_public_event",
    "public_event_interesting",
    "subject_html_url",
    "parse_poll_interval",
    "CATEGORY_LABELS",
    "INBOX_CATEGORIES",
    "PUBLIC_CATEGORIES",
    "DEFAULT_CATEGORIES",
    "DEFAULT_REASONS",
]
