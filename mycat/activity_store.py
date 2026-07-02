#!/usr/bin/env python3
"""Local activity database (SQLite, stdlib only).

One file — ``activity.db`` in the per-user data dir — holds everything the
companion features record on this machine: focus/break sessions now, minute
activity buckets later. Nothing in this module ever touches the network; the
whole point of the activity log is that it stays on this computer.

Timestamps are stored as local-time ISO strings: every analysis this app does
("today", "yesterday", "during that focus session") is anchored to the local
day the user actually lived through.
"""

import logging
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

FOCUS = "focus"
BREAK = "break"
LONG_BREAK = "long_break"

SCHEMA = """
CREATE TABLE IF NOT EXISTS focus_session (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,              -- 'focus' | 'break' | 'long_break'
    started_at TEXT NOT NULL,        -- local ISO
    ended_at TEXT NOT NULL,          -- local ISO
    planned_seconds INTEGER NOT NULL,
    completed INTEGER NOT NULL       -- 0 = stopped/skipped early, 1 = ran out
);
CREATE INDEX IF NOT EXISTS idx_focus_session_started ON focus_session(started_at);
"""


def user_data_dir() -> Path:
    """Per-user mycat data dir (same layout the skins roadmap uses)."""
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        return Path(base) / "mycat"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "mycat"
    base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    return Path(base) / "mycat"


class ActivityStore:
    """Thin sqlite3 wrapper. Main-thread only (one connection, no locks)."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or (user_data_dir() / "activity.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path))
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    def close(self) -> None:
        try:
            self.connection.close()
        except Exception as exc:  # noqa: BLE001 - closing must never crash the app
            logger.debug("ActivityStore close failed: %s", exc)

    # -- focus sessions -------------------------------------------------------

    def record_session(
        self,
        kind: str,
        started_at: datetime,
        ended_at: datetime,
        planned_seconds: int,
        completed: bool,
    ) -> None:
        self.connection.execute(
            "INSERT INTO focus_session (kind, started_at, ended_at, planned_seconds, completed)"
            " VALUES (?, ?, ?, ?, ?)",
            (kind, started_at.isoformat(), ended_at.isoformat(), int(planned_seconds), int(completed)),
        )
        self.connection.commit()

    def sessions_on(self, day: date) -> list[sqlite3.Row]:
        """All sessions that *started* on ``day``, in start order."""
        start = datetime.combine(day, datetime.min.time())
        end = start + timedelta(days=1)
        self.connection.row_factory = sqlite3.Row
        rows = self.connection.execute(
            "SELECT kind, started_at, ended_at, planned_seconds, completed"
            " FROM focus_session WHERE started_at >= ? AND started_at < ? ORDER BY started_at",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        self.connection.row_factory = None
        return rows

    def completed_focus_count(self, day: date) -> int:
        start = datetime.combine(day, datetime.min.time())
        end = start + timedelta(days=1)
        row = self.connection.execute(
            "SELECT COUNT(*) FROM focus_session"
            " WHERE kind = ? AND completed = 1 AND started_at >= ? AND started_at < ?",
            (FOCUS, start.isoformat(), end.isoformat()),
        ).fetchone()
        return int(row[0])


__all__ = ["ActivityStore", "user_data_dir", "FOCUS", "BREAK", "LONG_BREAK"]
