#!/usr/bin/env python3
"""Reminder model, persistence and scheduler for the cat-on-a-plane flyby.

A reminder is a short message that the cat delivers by flying a banner across
the screen (see ``reminder_ui.FlybyWindow``). This module owns:

- the :class:`Reminder` data model,
- load/save to the shared ``~/.config/mycat/config.ini`` (``[reminder]`` section),
- :class:`ReminderController`, a 1-second polling scheduler that fires the flyby
  when the configured time arrives and re-arms daily repeats.

Only ``QtCore`` is imported here; the visual flyby and the settings dialog live
in ``reminder_ui`` and are imported lazily so a headless run never needs widgets.
"""

import configparser
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from PySide6 import QtCore

from . import secret_store

logger = logging.getLogger(__name__)

# Same config file the rest of the app uses (see main.py). Derived locally to
# avoid importing main and creating an import cycle.
CFG_DIR = Path.home() / ".config" / "mycat"
CFG_FILE = CFG_DIR / "config.ini"

DIRECTION_LTR = "ltr"  # plane flies left -> right, banner trailing on the left
DIRECTION_RTL = "rtl"  # plane flies right -> left, banner trailing on the right

DEFAULT_TEXT = "Reminder!"
# How the flyby duration scales: 1.0 = the leisurely default in FlybyWindow.
DEFAULT_SPEED = 1.0


@dataclass
class Reminder:
    """One scheduled (or just-edited) reminder."""

    text: str = DEFAULT_TEXT
    direction: str = DIRECTION_LTR
    fire_at: datetime | None = None  # absolute, local, tz-naive
    repeat_daily: bool = False
    enabled: bool = True
    speed: float = DEFAULT_SPEED
    # One of "pink" / "white" / "blue" / "red" (or any QColor-valid hex). The
    # FlybyWindow recolours a single shared plane sprite via multiply-blend, so
    # all colour variants stay geometrically identical.
    plane_color: str = "pink"
    # Plane width in screen pixels; the height scales by the sprite's aspect
    # ratio (after alpha-bbox crop) so the plane never gets squashed.
    plane_width: int = 160
    # Which bundled plane sprite to fly (stem under assets/planes/, e.g.
    # "plane1".."plane4"). Empty falls back to the single bundled plane.png.
    plane: str = "plane1"
    # Cosmetic — how the user last set the schedule, only used to pre-fill the
    # dialog. The scheduler always trusts ``fire_at``.
    mode: str = "in"  # "in" (relative) | "at" (absolute time of day)
    in_minutes: int = 10

    def normalized_direction(self) -> str:
        return DIRECTION_RTL if self.direction == DIRECTION_RTL else DIRECTION_LTR


def _parse_dt(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def load_reminder() -> Reminder | None:
    """Read the ``[reminder]`` section, or ``None`` if absent/unreadable."""
    if not CFG_FILE.exists():
        return None
    try:
        config = configparser.ConfigParser()
        config.read(CFG_FILE)
        if "reminder" not in config:
            return None
        section = config["reminder"]
        return Reminder(
            text=section.get("text", DEFAULT_TEXT),
            direction=section.get("direction", DIRECTION_LTR),
            fire_at=_parse_dt(section.get("fire_at", "")),
            repeat_daily=section.getboolean("repeat_daily", fallback=False),
            enabled=section.getboolean("enabled", fallback=True),
            speed=section.getfloat("speed", fallback=DEFAULT_SPEED),
            plane_color=section.get("plane_color", "pink"),
            plane_width=section.getint("plane_width", fallback=160),
            plane=section.get("plane", "plane1"),
            mode=section.get("mode", "in"),
            in_minutes=section.getint("in_minutes", fallback=10),
        )
    except Exception as exc:  # noqa: BLE001 - never let a bad config crash the app
        logger.error("Failed to load reminder from config: %s", exc)
        return None


def save_reminder(reminder: Reminder) -> None:
    """Persist ``reminder`` into ``[reminder]`` without touching other sections."""
    try:
        CFG_DIR.mkdir(parents=True, exist_ok=True)
        config = configparser.ConfigParser()
        if CFG_FILE.exists():
            config.read(CFG_FILE)
        if "reminder" not in config:
            config.add_section("reminder")
        section = config["reminder"]
        section["text"] = reminder.text
        section["direction"] = reminder.normalized_direction()
        section["fire_at"] = reminder.fire_at.isoformat() if reminder.fire_at else ""
        section["repeat_daily"] = "true" if reminder.repeat_daily else "false"
        section["enabled"] = "true" if reminder.enabled else "false"
        section["speed"] = str(reminder.speed)
        section["plane_color"] = reminder.plane_color
        section["plane_width"] = str(reminder.plane_width)
        section["plane"] = reminder.plane
        section["mode"] = reminder.mode
        section["in_minutes"] = str(reminder.in_minutes)
        with open(CFG_FILE, "w") as fh:
            config.write(fh)
        secret_store.secure_file(CFG_FILE)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to save reminder to config: %s", exc)


def clear_reminder() -> None:
    """Disable the reminder (drop the whole ``[reminder]`` section)."""
    try:
        if not CFG_FILE.exists():
            return
        config = configparser.ConfigParser()
        config.read(CFG_FILE)
        if config.remove_section("reminder"):
            with open(CFG_FILE, "w") as fh:
                config.write(fh)
            secret_store.secure_file(CFG_FILE)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to clear reminder in config: %s", exc)


def next_future_occurrence(fire_at: datetime, now: datetime | None = None) -> datetime:
    """Advance ``fire_at`` by whole days until it is in the future (for daily repeat)."""
    now = now or datetime.now()
    nxt = fire_at
    while nxt <= now:
        nxt += timedelta(days=1)
    return nxt


class ReminderController(QtCore.QObject):
    """Owns the active reminder, polls the clock, and triggers the flyby.

    A 1-second timer (rather than a single long ``QTimer.singleShot``) keeps the
    schedule correct across system sleep/resume and wall-clock changes, and costs
    nothing measurable.
    """

    def __init__(self, window: QtCore.QObject) -> None:
        super().__init__(window)
        self._window = window
        self._reminder = load_reminder()
        self._flyby = None  # keep a ref so the window isn't garbage-collected mid-flight

        self._normalize_on_start()

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # -- public API ---------------------------------------------------------

    @property
    def reminder(self) -> Reminder | None:
        return self._reminder

    def set_reminder(self, reminder: Reminder) -> None:
        self._reminder = reminder
        save_reminder(reminder)
        when = reminder.fire_at.isoformat() if reminder.fire_at else "—"
        logger.info("Reminder set: %r at %s (%s)", reminder.text, when, reminder.normalized_direction())

    def clear(self) -> None:
        self._reminder = None
        clear_reminder()
        logger.info("Reminder cleared")

    def test(self, reminder: Reminder) -> None:
        """Show the flyby right now without changing the schedule."""
        self.show_flyby(reminder)

    def open_dialog(self) -> None:
        """Lazily build and show the settings dialog."""
        try:
            if __package__:
                from .reminder_ui import ReminderDialog
            else:
                import importlib

                ReminderDialog = importlib.import_module("mycat.reminder_ui").ReminderDialog
        except Exception:
            logger.exception("Failed to import reminder UI")
            return

        dialog = ReminderDialog(self, self._reminder, parent=self._window)
        dialog.exec()

    def show_flyby(self, reminder: Reminder) -> None:
        """Create and launch a flyby for ``reminder`` (no-op on headless platforms)."""
        app = QtCore.QCoreApplication.instance()
        platform_name = ""
        if hasattr(app, "platformName"):
            platform_name = (app.platformName() or "").lower()
        if platform_name == "offscreen":
            logger.info("Offscreen platform: skipping flyby for %r", reminder.text)
            return

        try:
            if __package__:
                from .reminder_ui import FlybyWindow
            else:
                import importlib

                FlybyWindow = importlib.import_module("mycat.reminder_ui").FlybyWindow
        except Exception:
            logger.exception("Failed to import flyby window")
            return

        cat_pixmap = getattr(self._window, "first_frame_pixmap", None)
        flyby = FlybyWindow(cat_pixmap, reminder)
        flyby.destroyed.connect(lambda _=None: setattr(self, "_flyby", None))
        self._flyby = flyby
        flyby.start()

    # -- internal -----------------------------------------------------------

    def _normalize_on_start(self) -> None:
        """Avoid surprise flybys at launch for reminders whose time already passed."""
        r = self._reminder
        if not r or not r.enabled or r.fire_at is None:
            return
        if r.fire_at > datetime.now():
            return
        if r.repeat_daily:
            r.fire_at = next_future_occurrence(r.fire_at)
            save_reminder(r)
        else:
            # One-shot reminder we missed while the app was closed: disable it.
            r.enabled = False
            save_reminder(r)

    def _tick(self) -> None:
        r = self._reminder
        if not r or not r.enabled or r.fire_at is None:
            return
        if datetime.now() >= r.fire_at:
            self._fire()

    def _fire(self) -> None:
        r = self._reminder
        if r is None:
            return
        logger.info("Firing reminder: %r", r.text)
        self.show_flyby(r)
        if r.repeat_daily and r.fire_at is not None:
            r.fire_at = next_future_occurrence(r.fire_at)
            save_reminder(r)
        else:
            r.enabled = False
            save_reminder(r)
