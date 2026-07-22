#!/usr/bin/env python3
"""Calendar reminders from a secret ICS URL (opt-in).

Google Calendar ("Secret address in iCal format"), Apple iCloud (public
calendar link) and Outlook all export a private ``.ics`` subscription URL, so
one poller covers every provider with no OAuth. The URL *is* the secret: it
lives in the chmod-600 config like the other tokens, and until the feature is
enabled this module makes zero network requests.

Calendar banners go through the shared announcer like every other companion
message — always shown, just paced so flybys don't overlap.

Parsing needs ``icalendar`` + ``recurring-ical-events`` (recurring events —
the daily standup — are exactly what people want reminders for, and RRULE
expansion is a swamp not worth hand-rolling). They are an optional extra:
``pip install mycat[calendar]``; without them the settings dialog says so and
nothing else breaks.
"""

import configparser
import logging
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from PySide6 import QtCore

if __package__:
    from . import paths, secret_store
else:
    import importlib

    secret_store = importlib.import_module("mycat.secret_store")
    paths = importlib.import_module("mycat.paths")

logger = logging.getLogger(__name__)

CFG_DIR = paths.config_dir()
CFG_FILE = paths.config_file()

DEFAULT_REMIND_MINUTES = 10
DEFAULT_POLL_MINUTES = 10
LOOKAHEAD_HOURS = 24
TICK_SECONDS = 30


class CalendarDependencyError(RuntimeError):
    """icalendar / recurring-ical-events not installed."""


@dataclass
class CalendarSettings:
    enabled: bool = False
    url: str = ""
    remind_minutes: int = DEFAULT_REMIND_MINUTES
    poll_minutes: int = DEFAULT_POLL_MINUTES


def load_calendar_settings(cfg_file: Path = CFG_FILE) -> CalendarSettings:
    settings = CalendarSettings()
    if not cfg_file.exists():
        return settings
    try:
        config = configparser.ConfigParser()
        config.read(cfg_file)
        if "calendar" not in config:
            return settings
        section = config["calendar"]
        settings.enabled = section.getboolean("enabled", fallback=False)
        settings.url = section.get("url", "")
        settings.remind_minutes = section.getint("remind_minutes", fallback=DEFAULT_REMIND_MINUTES)
        settings.poll_minutes = section.getint("poll_minutes", fallback=DEFAULT_POLL_MINUTES)
    except Exception as exc:  # noqa: BLE001 - never let a bad config crash the app
        logger.error("Failed to load [calendar] settings: %s", exc)
    return settings


def save_calendar_settings(settings: CalendarSettings, cfg_file: Path = CFG_FILE) -> None:
    try:
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        config = configparser.ConfigParser()
        if cfg_file.exists():
            config.read(cfg_file)
        if "calendar" not in config:
            config.add_section("calendar")
        section = config["calendar"]
        section["enabled"] = "true" if settings.enabled else "false"
        section["url"] = settings.url
        section["remind_minutes"] = str(settings.remind_minutes)
        section["poll_minutes"] = str(settings.poll_minutes)
        with open(cfg_file, "w") as fh:
            config.write(fh)
        secret_store.secure_file(cfg_file)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to save [calendar] settings: %s", exc)


# -- pure helpers (unit-tested without Qt or network) ---------------------------


def normalize_ics_url(url: str) -> str:
    """Apple shares ``webcal://`` links; they are plain HTTPS underneath."""
    url = url.strip()
    if url.lower().startswith("webcal://"):
        return "https://" + url[len("webcal://"):]
    return url


def parse_upcoming(ics_bytes: bytes, window_start: datetime, window_end: datetime) -> list:
    """Expand the calendar (RRULE included) into concrete upcoming events.

    Returns ``[{"key", "start", "summary"}]`` with timezone-aware local
    starts, all-day events skipped (a date has no meaningful "10 minutes
    before"). Raises :class:`CalendarDependencyError` when the parser libs
    are missing.
    """
    try:
        import icalendar
        import recurring_ical_events
    except ImportError as exc:
        raise CalendarDependencyError("pip install mycat[calendar] to enable calendar reminders") from exc

    calendar = icalendar.Calendar.from_ical(ics_bytes)
    events = []
    for event in recurring_ical_events.of(calendar).between(window_start, window_end):
        start = event.get("DTSTART")
        if start is None:
            continue
        start_value = start.dt
        if not isinstance(start_value, datetime):
            continue  # date-only = all-day event
        if start_value.tzinfo is None:
            start_value = start_value.astimezone()
        start_local = start_value.astimezone()
        uid = str(event.get("UID", "")) or str(event.get("SUMMARY", ""))
        summary = str(event.get("SUMMARY", "")).strip() or "(untitled event)"
        events.append(
            {
                "key": f"{uid}|{start_local.isoformat()}",
                "start": start_local,
                "summary": summary,
            }
        )
    events.sort(key=lambda item: item["start"])
    return events


class ReminderTracker:
    """Decides which events deserve a banner right now (each fires once)."""

    def __init__(self, remind_minutes: int = DEFAULT_REMIND_MINUTES) -> None:
        self.remind_minutes = remind_minutes
        self.fired: set[str] = set()

    def due(self, events: list, now: datetime) -> list:
        """Events whose reminder window ``[start - remind, start)`` contains now."""
        result = []
        window = timedelta(minutes=self.remind_minutes)
        for event in events:
            if event["key"] in self.fired:
                continue
            start = event["start"]
            if start - window <= now < start:
                self.fired.add(event["key"])
                result.append(event)
        self.prune(now)
        return result

    def prune(self, now: datetime) -> None:
        """Drop fired keys older than a day so the set never grows forever."""
        if len(self.fired) < 500:
            return
        cutoff = (now - timedelta(days=1)).isoformat()
        self.fired = {key for key in self.fired if key.split("|", 1)[-1] >= cutoff}


def fetch_ics(url: str, etag: str = "", opener=None) -> dict:
    """One download. Returns {status, ics_bytes, etag, error}."""
    request = urllib.request.Request(normalize_ics_url(url))
    request.add_header("User-Agent", "mycat-desktop-pet")
    if etag:
        request.add_header("If-None-Match", etag)
    open_fn = opener or urllib.request.urlopen
    result = {"status": 0, "ics_bytes": b"", "etag": etag, "error": ""}
    try:
        with open_fn(request, timeout=20) as response:
            result["status"] = response.status
            result["etag"] = response.headers.get("ETag", etag) or etag
            result["ics_bytes"] = response.read()
    except urllib.error.HTTPError as exc:
        result["status"] = exc.code
        if exc.code != 304:
            result["error"] = f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - offline is a normal state
        result["error"] = str(exc)
    return result


# -- Qt plumbing -----------------------------------------------------------------


class FetchWorker(QtCore.QRunnable):
    """Downloads + parses off the UI thread; big calendars parse slowly."""

    class Emitter(QtCore.QObject):
        finished = QtCore.Signal(dict)

    def __init__(self, url: str, etag: str) -> None:
        super().__init__()
        self.url = url
        self.etag = etag
        self.emitter = FetchWorker.Emitter()

    def run(self) -> None:
        result = fetch_ics(self.url, self.etag)
        if result["ics_bytes"] and not result["error"]:
            now = datetime.now().astimezone()
            try:
                result["events"] = parse_upcoming(
                    result["ics_bytes"], now, now + timedelta(hours=LOOKAHEAD_HOURS)
                )
            except CalendarDependencyError as exc:
                result["error"] = str(exc)
            except Exception as exc:  # noqa: BLE001 - a broken feed must not crash
                result["error"] = f"parse: {exc}"
        result.pop("ics_bytes", None)  # the raw bytes never leave the worker
        self.emitter.finished.emit(result)


class CalendarController(QtCore.QObject):
    """Polls the ICS feed and fires banners shortly before events."""

    def __init__(self, window, announcer=None, settings=None, now_fn=None, start_timers=True) -> None:
        super().__init__(window if isinstance(window, QtCore.QObject) else None)
        self.window = window
        self.announcer = announcer
        self.settings = settings if settings is not None else load_calendar_settings()
        self.now_fn = now_fn or (lambda: datetime.now().astimezone())
        self.tracker = ReminderTracker(self.settings.remind_minutes)
        self.events: list = []
        self.etag = ""
        self.fetching = False
        self.last_error = ""

        self.tick_timer = None
        self.poll_timer = None
        if start_timers:
            self.tick_timer = QtCore.QTimer(self)
            self.tick_timer.setInterval(TICK_SECONDS * 1000)
            self.tick_timer.timeout.connect(self.tick)
            self.tick_timer.start()
            self.poll_timer = QtCore.QTimer(self)
            self.poll_timer.setInterval(self.settings.poll_minutes * 60 * 1000)
            self.poll_timer.timeout.connect(self.poll)
            self.poll_timer.start()
            QtCore.QTimer.singleShot(5000, self.poll)

    def apply_settings(self, settings: CalendarSettings) -> None:
        self.settings = settings
        self.tracker = ReminderTracker(settings.remind_minutes)
        self.events = []
        self.etag = ""
        self.last_error = ""
        if self.poll_timer is not None:
            self.poll_timer.setInterval(settings.poll_minutes * 60 * 1000)
        self.poll()

    def poll(self) -> None:
        if self.fetching or not self.settings.enabled or not self.settings.url:
            return
        self.fetching = True
        worker = FetchWorker(self.settings.url, self.etag)
        worker.emitter.finished.connect(self.handle_fetch)
        QtCore.QThreadPool.globalInstance().start(worker)

    def handle_fetch(self, result: dict) -> None:
        self.fetching = False
        if result.get("error"):
            self.last_error = str(result["error"])
            logger.debug("Calendar poll failed: %s", self.last_error)
            return
        self.last_error = ""
        if int(result.get("status", 0)) == 304:
            return
        self.etag = str(result.get("etag", ""))
        self.events = list(result.get("events", []))
        logger.info("Calendar: %d event(s) in the next %dh", len(self.events), LOOKAHEAD_HOURS)
        self.tick()  # an event may already be inside the reminder window

    def tick(self) -> None:
        if not self.settings.enabled or not self.events:
            return
        now = self.now_fn()
        for event in self.tracker.due(self.events, now):
            minutes = max(1, int((event["start"] - now).total_seconds() // 60))
            text = f"📅 {event['summary']} — in {minutes} min"
            logger.info("Calendar reminder: %s", text)
            if self.announcer is not None:
                self.announcer.announce(text)


__all__ = [
    "CalendarController",
    "CalendarSettings",
    "CalendarDependencyError",
    "ReminderTracker",
    "load_calendar_settings",
    "save_calendar_settings",
    "normalize_ics_url",
    "parse_upcoming",
    "fetch_ics",
]
