#!/usr/bin/env python3
"""One shared announcement queue for the companion features.

Every companion feature (pomodoro, GitHub notifications, calendar reminders,
the morning digest) delivers its messages through a single :class:`Announcer`
so that flybys never overlap and focus time stays quiet:

- one flyby is on screen at a time, with a small gap between flights;
- while do-not-disturb is on (an active focus session), normal announcements
  are held and released on the next break;
- urgent announcements (an upcoming meeting) fly immediately, DND or not.

Main-thread only: pollers running in worker threads must hand their events to
the GUI thread (e.g. via a Qt signal) before calling :meth:`Announcer.announce`.
"""

import logging
import time
from dataclasses import dataclass

from PySide6 import QtCore

logger = logging.getLogger(__name__)

# Seconds between the previous flyby leaving the screen and the next take-off.
MIN_GAP_SECONDS = 4.0
# A crossing takes ~20 s; a flyby older than this is parked (the user grabbed
# it) — stop letting it block the queue.
SKY_STALE_SECONDS = 180.0


@dataclass
class Announcement:
    """One queued message. Duck-types the fields FlybyWindow reads."""

    text: str
    url: str = ""  # opened on double-click when non-empty
    urgent: bool = False  # bypasses DND and jumps ahead of normal items
    direction: str = "ltr"
    speed: float = 1.0
    plane_color: str = "pink"
    plane_width: int = 160
    plane: str = "plane1"

    def normalized_direction(self) -> str:
        return "rtl" if self.direction == "rtl" else "ltr"


class Announcer(QtCore.QObject):
    """Owns the queue, paces take-offs, and enforces do-not-disturb.

    ``launch`` and ``clock`` are injectable for tests: ``launch(item)`` must
    return an object whose disappearance the caller reports via
    :meth:`flyby_gone` (the default launcher wires this to ``destroyed``), or
    ``None`` when nothing was shown (headless platform).
    """

    def __init__(self, window, launch=None, clock=time.monotonic, start_timer=True) -> None:
        super().__init__(window)
        self.window = window
        self.launch = launch if launch is not None else self.launch_flyby
        self.clock = clock
        self.queue: list[Announcement] = []
        self.dnd = False
        self.active = None  # the in-flight window; also guards "one at a time"
        self.active_since = 0.0
        self.ready_at = 0.0  # earliest monotonic time for the next take-off

        if start_timer:
            self.timer = QtCore.QTimer(self)
            self.timer.setInterval(1000)
            self.timer.timeout.connect(self.pump)
            self.timer.start()

    # -- public API -----------------------------------------------------------

    def default_cosmetics(self) -> dict:
        """Plane look from the saved Reminder settings, so every banner —
        reminders, GitHub, digest — flies the same customized plane."""
        try:
            if __package__:
                from . import reminder as reminder_mod
            else:
                import importlib

                reminder_mod = importlib.import_module("mycat.reminder")
            saved = reminder_mod.load_reminder()
        except Exception:  # noqa: BLE001 - cosmetics must never break announcing
            return {}
        if saved is None:
            return {}
        return {
            "plane_color": saved.plane_color,
            "plane": saved.plane,
            "plane_width": saved.plane_width,
        }

    def announce(
        self,
        text: str,
        url: str = "",
        urgent: bool = False,
        **cosmetics,
    ) -> Announcement:
        """Queue a message. Urgent items keep FIFO order among themselves but
        go ahead of every normal item already waiting."""
        merged = self.default_cosmetics()
        merged.update(cosmetics)
        item = Announcement(text=text, url=url, urgent=urgent, **merged)
        if urgent:
            position = 0
            while position < len(self.queue) and self.queue[position].urgent:
                position += 1
            self.queue.insert(position, item)
        else:
            self.queue.append(item)
        logger.info("Announcement queued (urgent=%s): %r", urgent, text)
        self.pump()
        return item

    def set_dnd(self, active: bool) -> None:
        """Focus sessions turn DND on; breaks / idle turn it off."""
        self.dnd = bool(active)
        logger.debug("Announcer DND -> %s", self.dnd)
        if not self.dnd:
            self.pump()

    def pending_count(self) -> int:
        return len(self.queue)

    # -- queue pump -----------------------------------------------------------

    def next_item(self) -> Announcement | None:
        if not self.queue:
            return None
        if not self.dnd:
            return self.queue[0]
        for item in self.queue:
            if item.urgent:
                return item
        return None

    def pump(self) -> None:
        """Launch the next eligible announcement, if the sky is clear."""
        if self.active is not None:
            # A parked plane (grabbed mid-flight) must not block the queue
            # forever — after SKY_STALE_SECONDS treat the sky as clear.
            if self.clock() - self.active_since <= SKY_STALE_SECONDS:
                return
            logger.info("Flyby parked/stale — releasing the sky for the queue")
            self.active = None
        if self.clock() < self.ready_at:
            return
        item = self.next_item()
        if item is None:
            return
        self.queue.remove(item)
        shown = self.launch(item)
        if shown is None:
            # Nothing on screen (headless / no pixmap): keep pacing anyway so a
            # burst of announcements doesn't collapse into one instant.
            self.ready_at = self.clock() + MIN_GAP_SECONDS
            self.pump()
            return
        self.active = shown
        self.active_since = self.clock()

    def flyby_gone(self) -> None:
        """The current flyby left the screen; schedule the next take-off."""
        self.active = None
        self.ready_at = self.clock() + MIN_GAP_SECONDS

    # -- default launcher -----------------------------------------------------

    def launch_flyby(self, item: Announcement):
        """Show ``item`` as a FlybyWindow (no-op on headless platforms)."""
        app = QtCore.QCoreApplication.instance()
        platform_name = ""
        if hasattr(app, "platformName"):
            platform_name = (app.platformName() or "").lower()
        if platform_name == "offscreen":
            logger.info("Offscreen platform: skipping flyby for %r", item.text)
            return None

        try:
            if __package__:
                from .reminder_ui import FlybyWindow
            else:
                import importlib

                FlybyWindow = importlib.import_module("mycat.reminder_ui").FlybyWindow
        except Exception:
            logger.exception("Failed to import flyby window")
            return None

        cat_pixmap = getattr(self.window, "first_frame_pixmap", None)
        # Interactive char packs carry a closed-eyes frame — hand it over so the
        # cat blinks in the cockpit (GIF chars have none, so it just stays awake).
        pack = getattr(self.window, "char_pack", None)
        blink_pixmap = getattr(pack, "blink", None) if pack is not None else None
        flyby = FlybyWindow(cat_pixmap, item, blink_pixmap=blink_pixmap)
        flyby.destroyed.connect(lambda _=None: self.flyby_gone())
        flyby.start()
        return flyby


__all__ = ["Announcement", "Announcer", "MIN_GAP_SECONDS"]
