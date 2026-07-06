#!/usr/bin/env python3
"""Private activity diary: collector + analysis (on by default, local-only).

Hard rules, in order of importance:

1. **Counters, never content.** The keyboard hook increments an integer and
   discards the key identity in the same callback; the mouse contributes a
   travelled distance, never a trajectory. Nothing here can reconstruct what
   was typed or where the cursor went.
2. **Local only.** Everything lands in ``activity.db`` next to the focus
   sessions and participates in no network request of any kind.
3. **Honest wording.** Minutes without input are "away from the computer",
   not "not working" — people read, think and talk. The single place where
   silence is praised is a pomodoro break ("rested properly").

Two tiers:

- Tier 1 (no dependencies, no OS permissions): cursor distance via
  ``QCursor.pos()`` polling at 10 Hz.
- Tier 2 (``pynput``, installed with ``mycat[basic]``): key press and mouse
  click *counts* via global hooks. Where hooks can't work (pynput not
  installed, Wayland, missing macOS Input Monitoring permission) the collector
  degrades to tier 1 at runtime.

The two COUNT tracks switch independently (``mouse_enabled`` = click counts,
``keyboard_enabled`` = key counts). The tier-1 cursor path always records while
the diary is on — the cat's eyes track the cursor anyway — so it has no toggle.
"""

import configparser
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6 import QtCore, QtGui

if __package__:
    from . import activity_store, secret_store
else:
    import importlib

    activity_store = importlib.import_module("mycat.activity_store")
    secret_store = importlib.import_module("mycat.secret_store")

logger = logging.getLogger(__name__)

CFG_DIR = Path.home() / ".config" / "mycat"
CFG_FILE = CFG_DIR / "config.ini"

CURSOR_POLL_MS = 100  # 10 Hz — plenty for a distance integral
# A minute counts as "active" from this much cursor travel (filters out the
# desk bumping the mouse) or any key/click at all.
ACTIVE_MOUSE_PX_THRESHOLD = 30
# Per-sample cursor movement below this is sensor noise, not input.
SAMPLE_MOVE_EPSILON_PX = 3
# Input after at least this much silence is "coming back to the computer" —
# the edge that auto-starts a focus session.
IDLE_RESUME_MINUTES = 5
DEFAULT_RETENTION_DAYS = 90
# Merge active stretches separated by gaps up to this long, and only call the
# result "work outside pomodoro" from this length up.
RUN_GAP_MINUTES = 5
RUN_MIN_MINUTES = 15
# During a focus session this share of active minutes counts as "at the
# computer throughout"; during a break, staying UNDER it means real rest.
FOCUS_PRESENT_RATIO = 0.8
BREAK_REST_RATIO = 0.2


@dataclass
class ActivitySettings:
    # The diary is core product behaviour: on by default, with an opt-out,
    # a retention limit and a delete-everything button in the dialog.
    enabled: bool = True
    # Two switchable COUNT tracks (both tier 2, need mycat[basic]): mouse = click
    # counts, keyboard = key counts. The tier-1 cursor path always records while
    # the diary is on — the cat's eyes need the cursor anyway — so it has no toggle.
    mouse_enabled: bool = True
    keyboard_enabled: bool = True
    retention_days: int = DEFAULT_RETENTION_DAYS
    prompted: bool = False  # kept for config compatibility (prompt removed)


def pynput_available() -> bool:
    """Whether the tier-2 hooks (mycat[basic]) can be imported at all."""
    try:
        import pynput  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def load_activity_settings(cfg_file: Path = CFG_FILE) -> ActivitySettings:
    settings = ActivitySettings()
    if not cfg_file.exists():
        return settings
    try:
        config = configparser.ConfigParser()
        config.read(cfg_file)
        if "activity" not in config:
            return settings
        section = config["activity"]
        settings.enabled = section.getboolean("enabled", fallback=True)
        settings.mouse_enabled = section.getboolean("mouse_enabled", fallback=True)
        settings.keyboard_enabled = section.getboolean("keyboard_enabled", fallback=True)
        settings.retention_days = section.getint("retention_days", fallback=DEFAULT_RETENTION_DAYS)
        settings.prompted = section.getboolean("prompted", fallback=False)
    except Exception as exc:  # noqa: BLE001 - never let a bad config crash the app
        logger.error("Failed to load [activity] settings: %s", exc)
    return settings


def save_activity_settings(settings: ActivitySettings, cfg_file: Path = CFG_FILE) -> None:
    try:
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        config = configparser.ConfigParser()
        if cfg_file.exists():
            config.read(cfg_file)
        if "activity" not in config:
            config.add_section("activity")
        section = config["activity"]
        section["enabled"] = "true" if settings.enabled else "false"
        section["mouse_enabled"] = "true" if settings.mouse_enabled else "false"
        section["keyboard_enabled"] = "true" if settings.keyboard_enabled else "false"
        section["retention_days"] = str(settings.retention_days)
        section["prompted"] = "true" if settings.prompted else "false"
        with open(cfg_file, "w") as fh:
            config.write(fh)
        secret_store.secure_file(cfg_file)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to save [activity] settings: %s", exc)


# -- collector -------------------------------------------------------------------


class ActivityCollector(QtCore.QObject):
    """Samples input into minute buckets and flushes them to the store.

    ``cursor_pos_fn`` / ``now_fn`` are injectable for tests. The pynput
    listeners only touch two integers from their callback threads (atomic
    enough under the GIL for counters we read once a minute).

    Emits :attr:`resumed_after_idle` when input appears after at least
    ``IDLE_RESUME_MINUTES`` of silence — the trigger for auto-pomodoro. The
    very first input after startup only baselines (no signal), so launching
    the app never auto-starts a session by itself.
    """

    resumed_after_idle = QtCore.Signal()

    def __init__(
        self,
        store=None,
        settings=None,
        cursor_pos_fn=None,
        now_fn=datetime.now,
        start_timers=True,
    ) -> None:
        super().__init__()
        self.store = store if store is not None else activity_store.ActivityStore()
        self.settings = settings if settings is not None else load_activity_settings()
        self.cursor_pos_fn = cursor_pos_fn or (lambda: QtGui.QCursor.pos())
        self.now_fn = now_fn

        self.last_pos = None
        self.bucket_minute = None
        self.bucket_mouse_px = 0.0
        self.bucket_keys = 0
        self.bucket_clicks = 0
        self.key_listener = None
        self.mouse_listener = None
        self.xinput = None  # pure-Python X11 counter, the fallback when pynput is absent
        self.purged_today = False
        # Idle-edge detection (auto-pomodoro trigger) + current activity run.
        self.last_input_at = None
        self.run_start = None  # start of the current continuous activity run
        self.prev_keys = 0
        self.prev_clicks = 0

        if start_timers:
            self.poll_timer = QtCore.QTimer(self)
            self.poll_timer.setInterval(CURSOR_POLL_MS)
            self.poll_timer.timeout.connect(self.sample)
            if self.settings.enabled:
                self.start()

    # -- lifecycle --------------------------------------------------------------

    def start(self) -> None:
        if hasattr(self, "poll_timer"):
            self.poll_timer.start()
        self.reconcile_hooks()
        logger.info(
            "Activity collector started (mouse=%s keyboard=%s)",
            self.settings.mouse_enabled,
            self.settings.keyboard_enabled,
        )

    def stop(self) -> None:
        if hasattr(self, "poll_timer"):
            self.poll_timer.stop()
        self.stop_keyboard_hook()
        self.stop_mouse_hook()
        self.stop_xinput()
        self.flush()
        logger.info("Activity collector stopped")

    def apply_settings(self, settings: ActivitySettings) -> None:
        was_enabled = self.settings.enabled
        self.settings = settings
        if settings.enabled and not was_enabled:
            self.start()
        elif not settings.enabled and was_enabled:
            self.stop()
        elif settings.enabled:
            # Still on — reconcile each tier to its own toggle.
            self.reconcile_hooks()

    def reconcile_hooks(self) -> None:
        """Start/stop the keyboard and mouse click hooks to match the settings."""
        if self.settings.keyboard_enabled:
            self.start_keyboard_hook()
        else:
            self.stop_keyboard_hook()
        if self.settings.mouse_enabled:
            self.start_mouse_hook()
        else:
            self.stop_mouse_hook()

    # -- tier 2: key/click counts — pynput (Windows/macOS) or python-xlib (Linux) --

    def start_keyboard_hook(self) -> None:
        if self.key_listener is not None:
            return
        try:
            from pynput import keyboard
        except Exception:  # noqa: BLE001 - pynput absent (Linux base install) -> X11 fallback
            self.ensure_xinput()
            return

        def on_press(key) -> None:
            # The key identity is dropped RIGHT HERE — only the count survives.
            self.bucket_keys += 1

        try:
            self.key_listener = keyboard.Listener(on_press=on_press)
            self.key_listener.start()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to start keyboard hook")
            self.stop_keyboard_hook()

    def start_mouse_hook(self) -> None:
        if self.mouse_listener is not None:
            return
        try:
            from pynput import mouse
        except Exception:  # noqa: BLE001 - pynput absent (Linux base install) -> X11 fallback
            self.ensure_xinput()
            return

        def on_click(x, y, button, pressed) -> None:
            if pressed:
                self.bucket_clicks += 1

        try:
            self.mouse_listener = mouse.Listener(on_click=on_click)
            self.mouse_listener.start()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to start mouse hook")
            self.stop_mouse_hook()

    def stop_keyboard_hook(self) -> None:
        if self.key_listener is not None:
            try:
                self.key_listener.stop()
            except Exception:  # noqa: BLE001
                pass
            self.key_listener = None

    def stop_mouse_hook(self) -> None:
        if self.mouse_listener is not None:
            try:
                self.mouse_listener.stop()
            except Exception:  # noqa: BLE001
                pass
            self.mouse_listener = None

    def ensure_xinput(self) -> None:
        """Fallback counter for Linux, where pynput isn't installed. One X RECORD
        context feeds both tallies; the settings gate which are counted."""
        if self.xinput is not None:
            return
        try:
            from . import xinput_linux
        except Exception:  # noqa: BLE001
            logger.warning("key/click counting off — no pynput and no python-xlib; cursor path still recorded")
            return
        if not xinput_linux.available():
            logger.warning("key/click counting off — no X11 RECORD (Wayland?); cursor path still recorded")
            return
        counter = xinput_linux.InputCounter(on_key=self.on_xinput_key, on_click=self.on_xinput_click)
        if counter.start():
            self.xinput = counter
            logger.info("Key/click counting via python-xlib (X11)")
        else:
            logger.warning("key/click counting off — X11 RECORD unavailable; cursor path still recorded")

    def on_xinput_key(self) -> None:
        # The key identity never leaves the record thread — only the count survives.
        if self.settings.keyboard_enabled:
            self.bucket_keys += 1

    def on_xinput_click(self) -> None:
        if self.settings.mouse_enabled:
            self.bucket_clicks += 1

    def stop_xinput(self) -> None:
        if self.xinput is not None:
            try:
                self.xinput.stop()
            except Exception:  # noqa: BLE001
                pass
            self.xinput = None

    # -- tier 1: cursor sampling ---------------------------------------------------

    def sample(self) -> None:
        now = self.now_fn()
        minute = now.replace(second=0, microsecond=0)
        if self.bucket_minute is None:
            self.bucket_minute = minute
        elif minute != self.bucket_minute:
            self.flush()
            self.bucket_minute = minute

        moved = 0.0
        pos = self.cursor_pos_fn()
        # Cursor path always records while the diary is on — the cat's eyes track
        # the cursor anyway, so "Enable Mouse" gates only the click count, not this.
        if pos is not None and self.last_pos is not None:
            dx = pos.x() - self.last_pos.x()
            dy = pos.y() - self.last_pos.y()
            moved = (dx * dx + dy * dy) ** 0.5
            self.bucket_mouse_px += moved
        self.last_pos = pos

        input_now = (
            moved > SAMPLE_MOVE_EPSILON_PX
            or self.bucket_keys != self.prev_keys
            or self.bucket_clicks != self.prev_clicks
        )
        self.prev_keys = self.bucket_keys
        self.prev_clicks = self.bucket_clicks
        if input_now:
            new_run = self.last_input_at is None or (now - self.last_input_at) >= timedelta(minutes=IDLE_RESUME_MINUTES)
            if new_run and self.last_input_at is not None:
                logger.info("Input after %s of silence — idle-resume edge", now - self.last_input_at)
                self.resumed_after_idle.emit()
            if new_run:
                self.run_start = now
            self.last_input_at = now

    def flush(self) -> None:
        if self.bucket_minute is None:
            return
        mouse_px = int(self.bucket_mouse_px)
        keys = self.bucket_keys
        clicks = self.bucket_clicks
        active = mouse_px >= ACTIVE_MOUSE_PX_THRESHOLD or keys > 0 or clicks > 0
        try:
            self.store.record_minute(self.bucket_minute, mouse_px, keys, clicks, active)
        except Exception:  # noqa: BLE001 - a broken DB must not kill sampling
            logger.exception("Failed to record minute bucket")
        self.bucket_mouse_px = 0.0
        self.bucket_keys = 0
        self.bucket_clicks = 0
        self.prev_keys = 0
        self.prev_clicks = 0
        self.maybe_purge()

    def current_run(self, now=None):
        """The ongoing activity run {start}, or None when currently idle.

        Reconstructed from the recorded minutes in the database (plus the live
        bucket), NOT from in-memory state — so closing and reopening the app
        continues the same period instead of resetting it. A run is the last
        contiguous block of active minutes (gaps under IDLE_RESUME_MINUTES
        tolerated) reaching up to now.
        """
        now = now or self.now_fn()
        cutoff = (now - timedelta(hours=6)).replace(second=0, microsecond=0)
        try:
            rows = self.store.minutes_between(cutoff, now + timedelta(minutes=1))
        except Exception:  # noqa: BLE001 - a broken DB must not break the dialog
            rows = []
        active = [datetime.fromisoformat(row["minute"]) for row in rows if row["active"]]

        # The not-yet-flushed current minute counts as active if there's input.
        current_minute = now.replace(second=0, microsecond=0)
        live = self.bucket_keys or self.bucket_clicks or self.bucket_mouse_px >= ACTIVE_MOUSE_PX_THRESHOLD
        if live and (not active or active[-1] != current_minute):
            active.append(current_minute)

        if not active or now - active[-1] >= timedelta(minutes=IDLE_RESUME_MINUTES):
            return None
        run_start = active[-1]
        index = len(active) - 1
        while index > 0 and run_start - active[index - 1] <= timedelta(minutes=IDLE_RESUME_MINUTES):
            index -= 1
            run_start = active[index]
        return {"start": run_start}

    def current_run_stats(self, now=None):
        """Live counters for the current run: keys, clicks, path, active %."""
        now = now or self.now_fn()
        run = self.current_run(now)
        if run is None:
            return None
        start = run["start"]
        try:
            rows = self.store.minutes_between(start, now)
        except Exception:  # noqa: BLE001 - stats must never break the dialog
            rows = []
        elapsed_minutes = max(1, int((now - start).total_seconds() // 60))
        active = sum(row["active"] for row in rows)
        return {
            "start": start,
            "keys": sum(row["keys"] for row in rows) + int(self.bucket_keys),
            "clicks": sum(row["clicks"] for row in rows) + int(self.bucket_clicks),
            "mouse_px": sum(row["mouse_px"] for row in rows) + int(self.bucket_mouse_px),
            "active_minutes": active,
            "elapsed_minutes": elapsed_minutes,
            "active_pct": min(100, round(100 * active / elapsed_minutes)),
        }

    def maybe_purge(self) -> None:
        """Apply retention once per process run (cheap, good enough)."""
        if self.purged_today:
            return
        self.purged_today = True
        try:
            dropped = self.store.purge_minutes_older_than(self.settings.retention_days, self.now_fn())
            if dropped:
                logger.info("Activity retention: dropped %d old minute(s)", dropped)
        except Exception:  # noqa: BLE001
            logger.exception("Activity retention purge failed")


# -- analysis --------------------------------------------------------------------


def cursor_km(mouse_px: int, dpi: float) -> float:
    """Pixels → kilometres via the screen's physical DPI (an honest estimate)."""
    if dpi <= 0:
        dpi = 96.0
    meters = mouse_px / dpi * 0.0254
    return meters / 1000.0


def active_minutes_between(minutes: list, start: datetime, end: datetime) -> tuple:
    """(active, observed) minute counts within [start, end)."""
    active = 0
    observed = 0
    for row in minutes:
        moment = datetime.fromisoformat(row["minute"])
        if start <= moment < end:
            observed += 1
            if row["active"]:
                active += 1
    return active, observed


def classify_day(store, day: date) -> list:
    """Interval log for one local day, in honest wording.

    Returns dicts: {start, end, kind, label} where kind is one of
    ``focus`` / ``break`` / ``work`` (activity outside any session).
    """
    day_start = datetime.combine(day, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    sessions = store.sessions_on(day)
    minutes = store.minutes_between(day_start, day_end)

    intervals = []
    session_spans = []
    for row in sessions:
        started = datetime.fromisoformat(row["started_at"])
        ended = datetime.fromisoformat(row["ended_at"])
        session_spans.append((started, ended))
        active, observed = active_minutes_between(minutes, started, ended)
        ratio = active / observed if observed else 0.0

        if row["kind"] == activity_store.FOCUS:
            if not row["completed"]:
                label = "stopped early"
            elif observed == 0:
                label = "completed"
            elif ratio >= FOCUS_PRESENT_RATIO:
                label = f"at the computer throughout ({int(ratio * 100)}%) ✓"
            else:
                away = observed - active
                label = f"away for ~{away} min"
            intervals.append({"start": started, "end": ended, "kind": "focus", "label": label})
        else:
            if observed == 0:
                label = "break"
            elif ratio <= BREAK_REST_RATIO:
                label = "rested properly — away from the computer ✓"
            else:
                label = "spent at the computer"
            intervals.append({"start": started, "end": ended, "kind": "break", "label": label})

    # Active stretches outside any session → "work outside pomodoro".
    def in_session(moment: datetime) -> bool:
        return any(start <= moment < end for start, end in session_spans)

    run_start = None
    run_end = None
    for row in minutes:
        moment = datetime.fromisoformat(row["minute"])
        if not row["active"] or in_session(moment):
            continue
        if run_end is not None and moment - run_end <= timedelta(minutes=RUN_GAP_MINUTES):
            run_end = moment + timedelta(minutes=1)
            continue
        if run_start is not None and run_end - run_start >= timedelta(minutes=RUN_MIN_MINUTES):
            intervals.append(run_interval(run_start, run_end))
        run_start = moment
        run_end = moment + timedelta(minutes=1)
    if run_start is not None and run_end - run_start >= timedelta(minutes=RUN_MIN_MINUTES):
        intervals.append(run_interval(run_start, run_end))

    intervals.sort(key=lambda item: item["start"])
    return intervals


def run_interval(start: datetime, end: datetime) -> dict:
    total = int((end - start).total_seconds() // 60)
    hours, minutes = divmod(total, 60)
    length = f"{hours} h {minutes} min" if hours else f"{minutes} min"
    return {
        "start": start,
        "end": end,
        "kind": "work",
        "label": f"at the computer outside pomodoro ({length})",
    }


def sessions_table(store, day: date) -> list:
    """Per-session rows for the Activity table.

    Each focus/break session on ``day`` becomes a row with its start time,
    duration, and the keystrokes / clicks / cursor path summed over the
    minute buckets that fall inside it. Ordered by start time.
    """
    rows = []
    for session in store.sessions_on(day):
        started = datetime.fromisoformat(session["started_at"])
        ended = datetime.fromisoformat(session["ended_at"])
        minutes = store.minutes_between(started, ended)
        rows.append(
            {
                "kind": session["kind"],
                "completed": bool(session["completed"]),
                "start": started,
                "duration_seconds": int((ended - started).total_seconds()),
                "keys": sum(row["keys"] for row in minutes),
                "clicks": sum(row["clicks"] for row in minutes),
                "mouse_px": sum(row["mouse_px"] for row in minutes),
                "active_minutes": sum(row["active"] for row in minutes),
            }
        )
    return rows


def activity_runs(store, day: date, session_windows, gap_minutes: int = IDLE_RESUME_MINUTES) -> list:
    """Contiguous active-minute runs OUTSIDE the given pomodoro windows.

    Each run is a stretch you were at the computer without a running timer
    (short gaps under ``gap_minutes`` merged). Returns dicts with start / end /
    keys / clicks / mouse_px / active_minutes, oldest first.
    """
    day_start = datetime.combine(day, datetime.min.time())
    minutes = store.minutes_between(day_start, day_start + timedelta(days=1))
    runs = []
    run = None
    for row in minutes:
        if not row["active"]:
            continue
        moment = datetime.fromisoformat(row["minute"])
        if any(start <= moment < end for start, end in session_windows):
            continue
        if run is not None and moment - run["last"] <= timedelta(minutes=gap_minutes):
            run["last"] = moment
            run["keys"] += row["keys"]
            run["clicks"] += row["clicks"]
            run["mouse_px"] += row["mouse_px"]
            run["active_minutes"] += 1
        else:
            if run is not None:
                runs.append(run)
            run = {
                "start": moment,
                "last": moment,
                "keys": row["keys"],
                "clicks": row["clicks"],
                "mouse_px": row["mouse_px"],
                "active_minutes": 1,
            }
    if run is not None:
        runs.append(run)
    for entry in runs:
        entry["end"] = entry["last"] + timedelta(minutes=1)
    return runs


# Auto-focus grading: a continuous activity run (gaps ≤ IDLE_RESUME_MINUTES
# merged) IS the focus session. A run that lasted at least FOCUS_MINUTES earned
# a 🍅; any shorter finished run is a 🍌.
FOCUS_MINUTES = 25


def run_minutes(run) -> int:
    """Elapsed length of a run in whole minutes (start → end)."""
    return max(1, int((run["end"] - run["start"]).total_seconds() // 60))


def grade_run(minutes: int, focus_minutes: int = FOCUS_MINUTES) -> str:
    """A run's grade: "focus" (🍅, ≥ focus_minutes) or "banana" (🍌, shorter)."""
    return "focus" if minutes >= focus_minutes else "banana"


def graded_runs(store, day: date, focus_minutes: int = FOCUS_MINUTES) -> list:
    """The day's activity runs, each tagged with ``minutes`` and ``grade``."""
    runs = activity_runs(store, day, [])
    for run in runs:
        run["minutes"] = run_minutes(run)
        run["grade"] = grade_run(run["minutes"], focus_minutes)
    return runs


def focus_count(store, day: date, focus_minutes: int = FOCUS_MINUTES) -> int:
    """How many 🍅 were earned on ``day`` (runs of at least ``focus_minutes``)."""
    return sum(1 for run in activity_runs(store, day, []) if run_minutes(run) >= focus_minutes)


def longest_focus_minutes(store, day: date, focus_minutes: int = FOCUS_MINUTES) -> int:
    """Length of the day's longest earned 🍅, or 0 when none was earned."""
    lengths = [run_minutes(run) for run in activity_runs(store, day, []) if run_minutes(run) >= focus_minutes]
    return max(lengths) if lengths else 0


def day_summary(store, day: date, dpi: float = 96.0, focus_minutes: int = FOCUS_MINUTES) -> dict:
    """Totals for banners and the dialog: km, keys, clicks, 🍅, best focus."""
    totals = store.day_totals(day)
    return {
        "cursor_km": cursor_km(totals["mouse_px"], dpi),
        "mouse_px_total": totals["mouse_px"],
        "keys": totals["keys"],
        "clicks": totals["clicks"],
        "active_minutes": totals["active_minutes"],
        "observed_minutes": totals["observed_minutes"],
        "focus_count": focus_count(store, day, focus_minutes),
        "best_focus_minutes": longest_focus_minutes(store, day, focus_minutes),
    }


__all__ = [
    "ActivityCollector",
    "ActivitySettings",
    "pynput_available",
    "load_activity_settings",
    "save_activity_settings",
    "classify_day",
    "day_summary",
    "cursor_km",
    "active_minutes_between",
    "activity_runs",
    "graded_runs",
    "grade_run",
    "run_minutes",
    "focus_count",
    "longest_focus_minutes",
    "FOCUS_MINUTES",
    "IDLE_RESUME_MINUTES",
    "ACTIVE_MOUSE_PX_THRESHOLD",
]
