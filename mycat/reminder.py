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

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from PySide6 import QtCore

from . import config_store, paths

logger = logging.getLogger(__name__)

# The shared config file — paths.py is the single source (importing main here
# would create an import cycle).
CFG_DIR = paths.config_dir()
CFG_FILE = paths.config_file()

DIRECTION_LTR = "ltr"  # plane flies left -> right, banner trailing on the left
DIRECTION_RTL = "rtl"  # plane flies right -> left, banner trailing on the right

DEFAULT_TEXT = "Do you feed mycat?"
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
    plane_color: str = "white"
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


def parse_dt(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def load_reminder() -> Reminder | None:
    """Read the ``[reminder]`` section, or ``None`` if absent/unreadable."""
    config = config_store.read_config(CFG_FILE)
    if config is None or "reminder" not in config:
        return None
    try:
        section = config["reminder"]
        return Reminder(
            text=section.get("text", DEFAULT_TEXT),
            direction=section.get("direction", DIRECTION_LTR),
            fire_at=parse_dt(section.get("fire_at", "")),
            repeat_daily=section.getboolean("repeat_daily", fallback=False),
            enabled=section.getboolean("enabled", fallback=True),
            speed=section.getfloat("speed", fallback=DEFAULT_SPEED),
            plane_color=section.get("plane_color", "white"),
            plane_width=section.getint("plane_width", fallback=160),
            plane=section.get("plane", "plane1"),
            mode=section.get("mode", "in"),
            in_minutes=section.getint("in_minutes", fallback=10),
        )
    except (ValueError, TypeError) as exc:  # a malformed value -> None
        logger.error("Failed to load reminder from config: %s", exc)
        return None


def save_reminder(reminder: Reminder) -> None:
    """Persist ``reminder`` into ``[reminder]`` without touching other sections."""
    config_store.write_section(
        "reminder",
        {
            "text": reminder.text,
            "direction": reminder.normalized_direction(),
            "fire_at": reminder.fire_at.isoformat() if reminder.fire_at else "",
            "repeat_daily": config_store.bool_str(reminder.repeat_daily),
            "enabled": config_store.bool_str(reminder.enabled),
            "speed": reminder.speed,
            "plane_color": reminder.plane_color,
            "plane_width": reminder.plane_width,
            "plane": reminder.plane,
            "mode": reminder.mode,
            "in_minutes": reminder.in_minutes,
        },
        CFG_FILE,
    )


def clear_reminder() -> None:
    """Disable the reminder (drop the whole ``[reminder]`` section)."""
    config_store.remove_section("reminder", CFG_FILE)


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
        self.window = window
        self.reminder = load_reminder()
        self.flyby = None  # keep a ref so the window isn't garbage-collected mid-flight
        self.settings_dialog = None  # non-modal dialog ref (kept alive while open)

        self.normalize_on_start()

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    # -- public API ---------------------------------------------------------

    def set_reminder(self, reminder: Reminder) -> None:
        self.reminder = reminder
        save_reminder(reminder)
        when = reminder.fire_at.isoformat() if reminder.fire_at else "—"
        logger.info("Reminder set: %r at %s (%s)", reminder.text, when, reminder.normalized_direction())

    def clear(self) -> None:
        self.reminder = None
        clear_reminder()
        logger.info("Reminder cleared")

    def test(self, reminder: Reminder) -> None:
        """Show the flyby right now without changing the schedule."""
        self.show_flyby(reminder)

    def open_dialog(self) -> None:
        """Build and show the settings dialog NON-modally.

        Non-modal on purpose: a modal ``exec()`` grabs all input, so the Test
        flyby launched from the dialog could not be clicked or dragged while the
        dialog stayed open. With ``show()`` the user can fire Test, then grab and
        park the plane, and keep tweaking settings — all at once.
        """
        if self.settings_dialog is not None and self.settings_dialog.isVisible():
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return
        try:
            if __package__:
                from .reminder_ui import ReminderDialog
            else:
                import importlib

                ReminderDialog = importlib.import_module("mycat.reminder_ui").ReminderDialog
        except Exception:
            logger.exception("Failed to import reminder UI")
            return

        dialog = ReminderDialog(self, self.reminder, parent=self.window)
        dialog.setModal(False)
        dialog.finished.connect(lambda result: setattr(self, "settings_dialog", None))
        self.settings_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

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

        cat_pixmap = getattr(self.window, "first_frame_pixmap", None)
        flyby = FlybyWindow(cat_pixmap, reminder)
        flyby.destroyed.connect(lambda _=None: setattr(self, "flyby", None))
        self.flyby = flyby
        flyby.start()

    # -- internal -----------------------------------------------------------

    def normalize_on_start(self) -> None:
        """Avoid surprise flybys at launch for reminders whose time already passed."""
        r = self.reminder
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

    def tick(self) -> None:
        r = self.reminder
        if not r or not r.enabled or r.fire_at is None:
            return
        if datetime.now() >= r.fire_at:
            self.fire()

    def fire(self) -> None:
        r = self.reminder
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
