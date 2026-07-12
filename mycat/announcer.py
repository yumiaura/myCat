#!/usr/bin/env python3
"""One shared announcement queue for the companion features.

Every companion feature (pomodoro, GitHub notifications, calendar reminders,
the morning digest) delivers its messages through a single :class:`Announcer`.
Every message is always shown — nothing is ever suppressed (a focus session is
NOT do-not-disturb). The queue exists only to pace flybys so they don't overlap:
one flyby is on screen at a time, with a small gap between flights, in FIFO order.

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


def _reminder_plane_defaults() -> tuple[str, str, int]:
    """Plane look defaults — always from Reminder, the single settings source."""
    try:
        if __package__:
            from .reminder import Reminder
        else:
            from mycat.reminder import Reminder

        r = Reminder()
        return r.plane_color, r.plane, r.plane_width
    except Exception:  # noqa: BLE001
        return "white", "plane1", 160


_DEFAULT_PLANE_COLOR, _DEFAULT_PLANE, _DEFAULT_PLANE_WIDTH = _reminder_plane_defaults()


@dataclass
class Announcement:
    """One queued message. Duck-types the fields FlybyWindow reads.

    Plane look is owned by Reminder settings; Announcer fills these from
    ``default_cosmetics()`` so Activity/digest/GitHub match Reminder flybys.
    """

    text: str
    url: str = ""  # opened on double-click when non-empty
    direction: str = "ltr"
    speed: float = 1.0
    plane_color: str = _DEFAULT_PLANE_COLOR
    plane_width: int = _DEFAULT_PLANE_WIDTH
    plane: str = _DEFAULT_PLANE

    def normalized_direction(self) -> str:
        return "rtl" if self.direction == "rtl" else "ltr"


class Announcer(QtCore.QObject):
    """Owns the queue and paces take-offs so flybys never overlap.

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
        """Plane look from Reminder — the only place the user picks it.

        Saved ``[reminder]`` wins (including a disabled stub after Reset).
        If nothing is on disk yet, use ``Reminder()`` defaults so Activity,
        digest, and GitHub flybys match what the Reminder dialog shows.
        """
        try:
            if __package__:
                from . import reminder as reminder_mod
            else:
                import importlib

                reminder_mod = importlib.import_module("mycat.reminder")
            saved = reminder_mod.load_reminder()
            source = saved if saved is not None else reminder_mod.Reminder()
            return {
                "plane_color": source.plane_color,
                "plane": source.plane,
                "plane_width": source.plane_width,
            }
        except Exception:  # noqa: BLE001 - cosmetics must never break announcing
            color, plane, width = _reminder_plane_defaults()
            return {"plane_color": color, "plane": plane, "plane_width": width}

    def announce(self, text: str, url: str = "", **cosmetics) -> Announcement:
        """Queue a message. Every message is shown; the queue only paces them."""
        merged = self.default_cosmetics()
        merged.update(cosmetics)
        item = Announcement(text=text, url=url, **merged)
        self.queue.append(item)
        logger.info("Announcement queued: %r", text)
        self.pump()
        if item in self.queue:
            logger.info("Announcement held (%s): %r", self.hold_reason(), text)
        return item

    def pending_count(self) -> int:
        return len(self.queue)

    def hold_reason(self) -> str:
        """Why the queue head can't take off right now — for the log only."""
        if self.active is not None and self.clock() - self.active_since <= SKY_STALE_SECONDS:
            return "another flyby is still on screen"
        if self.clock() < self.ready_at:
            return "pacing gap between flybys"
        return "waiting for the next pump tick"

    # -- queue pump -----------------------------------------------------------

    def next_item(self) -> Announcement | None:
        return self.queue[0] if self.queue else None

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
        logger.info("Flyby launched: %r (%d still queued)", item.text, len(self.queue))

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
