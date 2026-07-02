#!/usr/bin/env python3
"""Pomodoro-style focus sessions delivered by the cat.

Design rule: **the cat is boring while you focus** — it settles down and a
thin progress bar under it is the only motion. All expressiveness happens at
the phase boundaries (a flyby banner announces the break and the next focus).

State machine: ``idle → focus → break → idle``; after every
``sessions_before_long_break`` completed focus sessions the break is a long
one. The break starts by itself (resting should need no click); the next
focus is started deliberately by the user.

Only ``QtCore`` is imported here; the progress bar lives in ``focus_ui`` and
is imported lazily so headless runs never need widgets (same split as
``reminder`` / ``reminder_ui``).
"""

import configparser
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from PySide6 import QtCore

if __package__:
    from . import activity_store
else:
    import importlib

    activity_store = importlib.import_module("mycat.activity_store")

logger = logging.getLogger(__name__)

# Same config file the rest of the app uses (see main.py / reminder.py).
CFG_DIR = Path.home() / ".config" / "mycat"
CFG_FILE = CFG_DIR / "config.ini"

IDLE = "idle"
FOCUS = "focus"
BREAK = "break"

# If a phase deadline was overshot by more than this (laptop lid closed,
# suspend, hibernation), the moment has passed: finish the phase quietly with
# no banner and no auto-break instead of celebrating hours later.
OVERSHOOT_GRACE_SECONDS = 300


@dataclass
class FocusSettings:
    focus_minutes: int = 25
    break_minutes: int = 5
    long_break_minutes: int = 15
    sessions_before_long_break: int = 4


def load_focus_settings() -> FocusSettings:
    """Read the ``[focus]`` section; every field falls back to the default."""
    settings = FocusSettings()
    if not CFG_FILE.exists():
        return settings
    try:
        config = configparser.ConfigParser()
        config.read(CFG_FILE)
        if "focus" not in config:
            return settings
        section = config["focus"]
        settings.focus_minutes = section.getint("focus_minutes", fallback=settings.focus_minutes)
        settings.break_minutes = section.getint("break_minutes", fallback=settings.break_minutes)
        settings.long_break_minutes = section.getint("long_break_minutes", fallback=settings.long_break_minutes)
        settings.sessions_before_long_break = section.getint(
            "sessions_before_long_break", fallback=settings.sessions_before_long_break
        )
    except Exception as exc:  # noqa: BLE001 - never let a bad config crash the app
        logger.error("Failed to load focus settings: %s", exc)
    return settings


class FocusController(QtCore.QObject):
    """Owns the session state, ticks the clock, drives DND, bar and banners.

    ``announcer`` (an :class:`mycat.announcer.Announcer` or a stub) and
    ``store``/``now_fn`` are injectable for tests.
    """

    def __init__(
        self,
        window,
        announcer=None,
        store=None,
        now_fn=datetime.now,
        start_timer=True,
    ) -> None:
        super().__init__(window if isinstance(window, QtCore.QObject) else None)
        self.window = window
        self.announcer = announcer
        self.store = store if store is not None else activity_store.ActivityStore()
        self.now_fn = now_fn
        self.settings = load_focus_settings()

        self.state = IDLE
        self.phase_started: datetime | None = None
        self.phase_ends: datetime | None = None
        self.phase_planned_seconds = 0
        self.on_long_break = False
        # Completed focus sessions since the last long break (not per day).
        self.focus_streak = 0
        self.bar = None  # lazy FocusBarWindow; None while idle or headless

        if start_timer:
            self.timer = QtCore.QTimer(self)
            self.timer.setInterval(1000)
            self.timer.timeout.connect(self.tick)
            self.timer.start()

    # -- public API -----------------------------------------------------------

    def start_focus(self) -> None:
        """Begin a focus session (from idle, or cutting a break short)."""
        if self.state == BREAK:
            self.record_phase(completed=False)
        self.enter_phase(FOCUS, self.settings.focus_minutes * 60)
        if self.announcer is not None:
            self.announcer.set_dnd(True)
        logger.info("Focus session started (%d min)", self.settings.focus_minutes)

    def stop(self) -> None:
        """Abandon the current phase and go idle (no banner — user's choice)."""
        if self.state == IDLE:
            return
        self.record_phase(completed=False)
        if self.announcer is not None:
            self.announcer.set_dnd(False)
        self.leave_phase()
        logger.info("Focus session stopped by user")

    def skip_break(self) -> None:
        """Cut the break short and dive into the next focus session."""
        if self.state == BREAK:
            self.start_focus()

    def today_count(self) -> int:
        return self.store.completed_focus_count(self.now_fn().date())

    def remaining_seconds(self) -> int:
        if self.phase_ends is None:
            return 0
        return max(0, int((self.phase_ends - self.now_fn()).total_seconds()))

    def progress(self) -> float:
        """0.0 at phase start, 1.0 at the deadline."""
        if self.phase_planned_seconds <= 0:
            return 0.0
        done = self.phase_planned_seconds - self.remaining_seconds()
        return min(1.0, max(0.0, done / self.phase_planned_seconds))

    def status_text(self) -> str:
        minutes, seconds = divmod(self.remaining_seconds(), 60)
        clock = f"{minutes:02d}:{seconds:02d}"
        if self.state == FOCUS:
            return f"Focus · {clock} left · today {self.today_count()} 🍅"
        if self.state == BREAK:
            label = "Long break" if self.on_long_break else "Break"
            return f"{label} · {clock} left · today {self.today_count()} 🍅"
        return ""

    # -- clock ---------------------------------------------------------------

    def tick(self) -> None:
        if self.state == IDLE:
            return
        if self.phase_ends is not None and self.now_fn() >= self.phase_ends:
            self.finish_phase()
            return
        self.refresh_visuals()

    def finish_phase(self) -> None:
        overshoot = 0.0
        if self.phase_ends is not None:
            overshoot = (self.now_fn() - self.phase_ends).total_seconds()
        stale = overshoot > OVERSHOOT_GRACE_SECONDS

        if self.state == FOCUS:
            self.record_phase(completed=True)
            self.focus_streak += 1
            if self.announcer is not None:
                self.announcer.set_dnd(False)
            if stale:
                # Machine slept through the deadline — no banner hours later.
                self.leave_phase()
                return
            long_break = self.focus_streak % self.settings.sessions_before_long_break == 0
            minutes = self.settings.long_break_minutes if long_break else self.settings.break_minutes
            if self.announcer is not None:
                if long_break:
                    text = f"Long break — you earned it! 🍅 ×{self.settings.sessions_before_long_break}"
                else:
                    text = f"Break time! 🍅 #{self.today_count()} done"
                self.announcer.announce(text)
            self.on_long_break = long_break
            self.enter_phase(BREAK, minutes * 60)
            return

        # BREAK finished.
        self.record_phase(completed=True)
        if self.announcer is not None and not stale:
            self.announcer.announce("Break's over — another focus? 🍅")
        self.leave_phase()

    # -- phase bookkeeping ----------------------------------------------------

    def enter_phase(self, state: str, planned_seconds: int) -> None:
        self.state = state
        if state != BREAK:
            self.on_long_break = False
        self.phase_started = self.now_fn()
        self.phase_planned_seconds = planned_seconds
        self.phase_ends = self.phase_started + timedelta(seconds=planned_seconds)
        self.refresh_visuals()

    def leave_phase(self) -> None:
        self.state = IDLE
        self.phase_started = None
        self.phase_ends = None
        self.phase_planned_seconds = 0
        self.on_long_break = False
        self.refresh_visuals()

    def record_phase(self, completed: bool) -> None:
        if self.state == IDLE or self.phase_started is None:
            return
        if self.state == FOCUS:
            kind = activity_store.FOCUS
        elif self.on_long_break:
            kind = activity_store.LONG_BREAK
        else:
            kind = activity_store.BREAK
        try:
            self.store.record_session(
                kind=kind,
                started_at=self.phase_started,
                ended_at=self.now_fn(),
                planned_seconds=self.phase_planned_seconds,
                completed=completed,
            )
        except Exception:  # noqa: BLE001 - a broken DB must not kill the timer
            logger.exception("Failed to record %s session", self.state)

    # -- visuals (bar under the cat + tooltip on the cat) ----------------------

    def refresh_visuals(self) -> None:
        window = self.window
        if window is None or not hasattr(window, "setToolTip"):
            return
        if self.state == IDLE:
            window.setToolTip("")
            if self.bar is not None:
                self.bar.hide()
            return
        window.setToolTip(self.status_text())
        bar = self.ensure_bar()
        if bar is not None:
            bar.update_state(
                progress=self.progress(),
                on_break=self.state == BREAK,
                tooltip=self.status_text(),
            )
            bar.follow(window)
            bar.show()

    def ensure_bar(self):
        if self.bar is not None:
            return self.bar
        app = QtCore.QCoreApplication.instance()
        platform_name = ""
        if hasattr(app, "platformName"):
            platform_name = (app.platformName() or "").lower()
        if platform_name == "offscreen":
            return None
        try:
            if __package__:
                from .focus_ui import FocusBarWindow
            else:
                import importlib

                FocusBarWindow = importlib.import_module("mycat.focus_ui").FocusBarWindow
        except Exception:
            logger.exception("Failed to import focus bar")
            return None
        self.bar = FocusBarWindow()
        return self.bar


__all__ = ["FocusController", "FocusSettings", "load_focus_settings", "IDLE", "FOCUS", "BREAK"]
