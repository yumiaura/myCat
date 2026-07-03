#!/usr/bin/env python3
"""Automatic focus, earned from activity — no timer, no button.

A *focus* is simply a continuous activity run: the activity collector already
tracks it (contiguous active minutes with gaps under ``IDLE_RESUME_MINUTES``
merged, reconstructed from the database so it survives a restart). This watcher
reads the collector's current run once a second and:

- shows it in the cat's hover tooltip ("Focus · 12:34 · 🍅 2 · ⌨ … · %");
- when the run reaches ``focus_minutes`` (25) you have **earned a 🍅** and a
  banner flies ("🍅 earned — time to rest"); it re-fires every ``focus_minutes``
  of unbroken work, but the run still counts as a single 🍅;
- keeps do-not-disturb on while a run is active (non-urgent banners wait) and
  releases it when you rest (idle past the gap).

The 🍅 / 🍌 accounting lives in :mod:`mycat.activity` (runs graded by length);
this class only drives the live tooltip, the rest banner and DND.
"""

import configparser
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6 import QtCore

if __package__:
    from . import activity as activity_mod
    from . import activity_store
else:
    import importlib

    activity_mod = importlib.import_module("mycat.activity")
    activity_store = importlib.import_module("mycat.activity_store")

logger = logging.getLogger(__name__)

# Same config file the rest of the app uses (see main.py / reminder.py).
CFG_DIR = Path.home() / ".config" / "mycat"
CFG_FILE = CFG_DIR / "config.ini"


def cursor_km_estimate(mouse_px: int) -> float:
    """Pixels → km via the primary screen's DPI (96 when unavailable)."""
    dpi = 96.0
    try:
        from PySide6 import QtGui

        screen = QtGui.QGuiApplication.primaryScreen()
        if screen is not None:
            dpi = float(screen.physicalDotsPerInch()) or 96.0
    except Exception:  # noqa: BLE001
        pass
    return mouse_px / dpi * 0.0254 / 1000.0


def format_elapsed(seconds: float) -> str:
    """Count-up clock for the current run: M:SS, or H:MM:SS past an hour."""
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


@dataclass
class FocusSettings:
    focus_minutes: int = 25  # a run this long earns a 🍅; anything shorter is a 🍌


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
    except Exception as exc:  # noqa: BLE001 - never let a bad config crash the app
        logger.error("Failed to load focus settings: %s", exc)
    return settings


class FocusController(QtCore.QObject):
    """Watches the collector's current activity run and drives the tooltip,
    the "time to rest" banner and do-not-disturb.

    ``announcer`` (an :class:`mycat.announcer.Announcer` or a stub) and
    ``store`` / ``now_fn`` are injectable for tests.
    """

    def __init__(self, window, announcer=None, store=None, now_fn=datetime.now, start_timer=True) -> None:
        super().__init__(window if isinstance(window, QtCore.QObject) else None)
        self.window = window
        self.announcer = announcer
        self.store = store if store is not None else activity_store.ActivityStore()
        self.now_fn = now_fn
        self.settings = load_focus_settings()

        self.collector = None
        self.run_start = None  # identity of the run we're currently watching
        self.rests_nudged = 0  # how many "time to rest" nudges fired this run
        self.dnd_on = False

        if start_timer:
            self.timer = QtCore.QTimer(self)
            self.timer.setInterval(1000)
            self.timer.timeout.connect(self.tick)
            self.timer.start()

    # -- wiring / reads --------------------------------------------------------

    def attach_collector(self, collector) -> None:
        """The activity collector supplies the current run; no signals needed."""
        self.collector = collector

    def today_count(self) -> int:
        return activity_mod.focus_count(self.store, self.now_fn().date(), self.settings.focus_minutes)

    def current_run_stats(self) -> dict | None:
        """Live stats for the ongoing run, or None when idle (no run)."""
        if self.collector is None or not hasattr(self.collector, "current_run_stats"):
            return None
        return self.collector.current_run_stats(self.now_fn())

    def run_elapsed_seconds(self, stats: dict) -> float:
        return (self.now_fn() - stats["start"]).total_seconds()

    def earned(self, stats: dict) -> bool:
        return self.run_elapsed_seconds(stats) >= self.settings.focus_minutes * 60

    # -- tooltip text ----------------------------------------------------------

    def period_parts(self, duration: str, stats: dict | None) -> str:
        """The agreed tooltip order: 🍅×N · duration · ⌨ keys · 🖱 clicks/path · %."""
        parts = [f"🍅 {self.today_count()}", duration]
        if stats is not None:
            parts.append(f"⌨ {stats['keys']:,}")
            km = cursor_km_estimate(stats["mouse_px"])
            path = f"{km:.1f} km" if km >= 0.1 else f"{int(km * 1000)} m"
            parts.append(f"🖱 {stats['clicks']:,} / {path}")
            parts.append(f"{stats['active_pct']}% active")
        return " · ".join(parts)

    def status_text(self) -> str:
        """Tooltip for the ongoing run — stats only (no "Focus" label), or "" when idle.

        The leading ``🍅 N`` is the day's earned count; the elapsed clock and the
        input stats follow. Empty string means idle (no run)."""
        stats = self.current_run_stats()
        if stats is None:
            return ""
        return self.period_parts(format_elapsed(self.run_elapsed_seconds(stats)), stats)

    # -- clock -----------------------------------------------------------------

    def tick(self) -> None:
        stats = self.current_run_stats()
        if stats is None:
            # Idle: release DND and forget the run we were watching.
            self.set_dnd(False)
            self.run_start = None
            self.rests_nudged = 0
            self.refresh_visuals()
            return

        start = stats["start"]
        if start != self.run_start:
            # A fresh run — reset the rest-nudge counter.
            self.run_start = start
            self.rests_nudged = 0
        self.set_dnd(True)

        elapsed_minutes = int(self.run_elapsed_seconds(stats) // 60)
        milestones = elapsed_minutes // self.settings.focus_minutes  # 0, 1, 2, …
        if milestones > self.rests_nudged:
            self.rests_nudged = milestones
            self.announce_rest(milestones)

        self.refresh_visuals()

    def announce_rest(self, milestone: int) -> None:
        if self.announcer is None:
            return
        text = "🍅 earned — time to rest" if milestone == 1 else "Still at it — time to rest 🍅"
        # Urgent so it breaks through the DND this very run put up.
        self.announcer.announce(text, urgent=True)
        logger.info("Focus rest nudge (milestone %d, %d min)", milestone, milestone * self.settings.focus_minutes)

    def set_dnd(self, active: bool) -> None:
        if active == self.dnd_on:
            return
        self.dnd_on = active
        if self.announcer is not None:
            self.announcer.set_dnd(active)

    # -- visuals: the cat's hover tooltip carries the current run --------------

    def refresh_visuals(self) -> None:
        window = self.window
        if window is None or not hasattr(window, "setToolTip"):
            return
        text = self.status_text() or f"🍅 {self.today_count()} today · idle"
        window.setToolTip(text)
        # While the tooltip is on screen, keep its clock/stats ticking.
        try:
            from PySide6 import QtGui, QtWidgets

            if QtWidgets.QToolTip.isVisible() and window.underMouse():
                QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), text, window)
        except Exception:  # noqa: BLE001 - a tooltip must never break the timer
            pass


__all__ = ["FocusController", "FocusSettings", "load_focus_settings", "format_elapsed", "cursor_km_estimate"]
