#!/usr/bin/env python3
"""The morning newspaper: yesterday's stats, delivered once per day.

On the first tick of a new day after 05:00 local — i.e. when the user is
actually back at the computer — the cat flies one banner with yesterday's
numbers: cursor kilometres, keystroke count (when the keyboard tier is on),
completed pomodoros and the longest focus. Delivered at normal priority
through the shared announcer, so it politely waits out an early focus
session. The last delivered date is remembered in the config so a restart
never re-delivers the same paper.
"""

import configparser
import logging
from datetime import datetime, timedelta
from pathlib import Path

from PySide6 import QtCore, QtGui

if __package__:
    from . import activity as activity_mod
    from . import paths
else:
    import importlib

    activity_mod = importlib.import_module("mycat.activity")
    paths = importlib.import_module("mycat.paths")

logger = logging.getLogger(__name__)

CFG_DIR = paths.config_dir()
CFG_FILE = paths.config_file()

# Before this local hour a "new day" hasn't really started — a 01:00 session
# is yesterday's late evening, and getting yesterday's paper then feels off.
MORNING_HOUR = 5
TICK_SECONDS = 60


def load_digest_date(cfg_file: Path = CFG_FILE) -> str:
    if not cfg_file.exists():
        return ""
    try:
        config = configparser.ConfigParser()
        config.read(cfg_file)
        return config.get("activity", "digest_date", fallback="")
    except Exception:  # noqa: BLE001
        return ""


def save_digest_date(day_iso: str, cfg_file: Path = CFG_FILE) -> None:
    try:
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        config = configparser.ConfigParser()
        if cfg_file.exists():
            config.read(cfg_file)
        if "activity" not in config:
            config.add_section("activity")
        config["activity"]["digest_date"] = day_iso
        with open(cfg_file, "w") as fh:
            config.write(fh)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to save digest date: %s", exc)


def compose_digest(summary: dict) -> str:
    """One line of yesterday's numbers; empty string when there is no story."""
    parts = []
    if summary["cursor_km"] >= 0.01:
        parts.append(f"🖱 {summary['cursor_km']:.1f} km")
    if summary["keys"]:
        parts.append(f"⌨ {summary['keys']:,}")
    if summary["focus_count"]:
        parts.append(f"🍅 {summary['focus_count']}")
    if summary["best_focus_minutes"]:
        parts.append(f"best focus {summary['best_focus_minutes']} min")
    if not parts:
        return ""
    return "Yesterday: " + " · ".join(parts)


def screen_dpi() -> float:
    screen = QtGui.QGuiApplication.primaryScreen()
    if screen is None:
        return 96.0
    try:
        return float(screen.physicalDotsPerInch()) or 96.0
    except Exception:  # noqa: BLE001
        return 96.0


class MorningDigest(QtCore.QObject):
    """Watches the clock and delivers yesterday's paper exactly once."""

    def __init__(
        self,
        store,
        announcer=None,
        now_fn=datetime.now,
        dpi_fn=screen_dpi,
        cfg_file: Path = CFG_FILE,
        start_timer=True,
    ) -> None:
        super().__init__()
        self.store = store
        self.announcer = announcer
        self.now_fn = now_fn
        self.dpi_fn = dpi_fn
        self.cfg_file = cfg_file
        self.delivered_date = load_digest_date(cfg_file)

        if start_timer:
            self.timer = QtCore.QTimer(self)
            self.timer.setInterval(TICK_SECONDS * 1000)
            self.timer.timeout.connect(self.tick)
            self.timer.start()
            QtCore.QTimer.singleShot(10000, self.tick)  # also check soon after launch

    def tick(self) -> None:
        now = self.now_fn()
        if now.hour < MORNING_HOUR:
            return
        today_iso = now.date().isoformat()
        if self.delivered_date == today_iso:
            return

        yesterday = now.date() - timedelta(days=1)
        try:
            summary = activity_mod.day_summary(self.store, yesterday, dpi=self.dpi_fn())
        except Exception:  # noqa: BLE001 - a broken DB must not loop forever
            logger.exception("Failed to build the morning digest")
            self.delivered_date = today_iso
            save_digest_date(today_iso, self.cfg_file)
            return

        text = compose_digest(summary)
        # Mark delivered even when there is nothing to tell — otherwise an
        # empty yesterday would be re-checked every minute all day long.
        self.delivered_date = today_iso
        save_digest_date(today_iso, self.cfg_file)
        if not text:
            return
        logger.info("Morning digest: %s", text)
        if self.announcer is not None:
            self.announcer.announce(text)


__all__ = ["MorningDigest", "compose_digest", "load_digest_date", "save_digest_date", "MORNING_HOUR"]
