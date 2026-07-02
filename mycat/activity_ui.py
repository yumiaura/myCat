#!/usr/bin/env python3
"""Activity diary dialog: opt-in switches, the interval log, day totals.

The log speaks in honest wording ("away from the computer", not "not
working"); the only place silence is praised is a pomodoro break.
"""

import logging
from datetime import date, datetime, timedelta
from datetime import time as day_time

from PySide6 import QtCore, QtGui, QtWidgets

if __package__:
    from . import activity as activity_mod
else:
    import importlib

    activity_mod = importlib.import_module("mycat.activity")

logger = logging.getLogger(__name__)

KIND_ICONS = {"focus": "🍅", "break": "☕", "long_break": "☕", "work": "💻"}

# Session table: start + duration per session, then the input counters and
# how active that stretch was. The bottom TOTAL row carries NO start/end times.
TABLE_COLUMNS = ["Session", "Start", "Duration", "⌨ Keys", "🖱 Clicks", "Cursor path", "Active"]


def active_pct(active_minutes: int, window_minutes: int) -> str:
    if window_minutes <= 0:
        return "—"
    return f"{min(100, round(100 * active_minutes / window_minutes))}%"


def format_duration(seconds: int) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    return f"{minutes}:{secs:02d}"


def format_path(mouse_px: int, dpi: float) -> str:
    km = activity_mod.cursor_km(mouse_px, dpi)
    return f"{km:.2f} km" if km >= 0.1 else f"{int(km * 1000)} m"


def screen_dpi() -> float:
    screen = QtGui.QGuiApplication.primaryScreen()
    if screen is None:
        return 96.0
    try:
        return float(screen.physicalDotsPerInch()) or 96.0
    except Exception:  # noqa: BLE001
        return 96.0


SEGMENT_COLORS = {
    "focus": QtGui.QColor("#d94a4a"),        # matches the focus progress bar
    "break": QtGui.QColor("#4caf50"),        # rest
    "interrupted": QtGui.QColor("#e0a52e"),  # 🍌 a stopped pomodoro
    "current": QtGui.QColor("#4a8fe2"),      # the live period
}
TRACK_BG = QtGui.QColor("#e9e9ec")
GRID_COLOR = QtGui.QColor("#c8c8cc")
NOW_COLOR = QtGui.QColor("#333333")
AXIS_TEXT = QtGui.QColor("#666666")


class DayTimeline(QtWidgets.QWidget):
    """A horizontal strip of the day: focus / rest / interrupted segments.

    Makes the pomodoro rhythm visible — a red focus block, a green rest, then
    the next block — so "отдохнув, начинается следующий период" is something
    you can see at a glance. The live current period is a blue lane below the
    session track, and a dark line marks "now".
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(66)
        self.setMouseTracking(True)
        self.segments = []       # [{start, end, kind}]
        self.current = None      # {start, end, kind: "current"} or None
        self.window_start = None
        self.window_end = None
        self.now = None
        self.hit_areas = []      # [(QRectF, tooltip)]

    def set_data(self, segments, current, window_start, window_end, now) -> None:
        self.segments = segments
        self.current = current
        self.window_start = window_start
        self.window_end = window_end
        self.now = now
        self.update()

    def x_for(self, moment, left, usable_w) -> float:
        span = (self.window_end - self.window_start).total_seconds() or 1.0
        frac = (moment - self.window_start).total_seconds() / span
        return left + usable_w * min(1.0, max(0.0, frac))

    def paintEvent(self, event) -> None:
        if self.window_start is None or self.window_end is None:
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)

        left, right, top = 8, 8, 6
        track_h, gap, cur_h = 22, 4, 8
        usable_w = max(1, self.width() - left - right)
        track_y = top
        cur_y = track_y + track_h + gap
        axis_y = cur_y + cur_h + 3
        self.hit_areas = []

        # Empty background track.
        painter.setBrush(TRACK_BG)
        painter.drawRoundedRect(QtCore.QRectF(left, track_y, usable_w, track_h), 4, 4)

        # Hour gridlines + labels.
        painter.setFont(QtGui.QFont(self.font().family(), 7))
        hour = self.window_start.replace(minute=0, second=0, microsecond=0)
        if hour < self.window_start:
            hour = hour + timedelta(hours=1)
        while hour <= self.window_end:
            hx = self.x_for(hour, left, usable_w)
            painter.setPen(QtGui.QPen(GRID_COLOR, 1))
            painter.drawLine(QtCore.QPointF(hx, track_y), QtCore.QPointF(hx, cur_y + cur_h))
            painter.setPen(QtGui.QPen(AXIS_TEXT))
            painter.drawText(QtCore.QRectF(hx - 14, axis_y, 28, 12),
                             QtCore.Qt.AlignmentFlag.AlignCenter, hour.strftime("%H"))
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            hour = hour + timedelta(hours=1)

        # Session segments.
        for seg in self.segments:
            x0 = self.x_for(seg["start"], left, usable_w)
            x1 = self.x_for(seg["end"], left, usable_w)
            rect = QtCore.QRectF(x0, track_y, max(2.0, x1 - x0), track_h)
            painter.setBrush(SEGMENT_COLORS.get(seg["kind"], TRACK_BG))
            painter.drawRoundedRect(rect, 2, 2)
            label = "Interrupted" if seg["kind"] == "interrupted" else seg["kind"].capitalize()
            self.hit_areas.append(
                (rect, f"{label}  {seg['start'].strftime('%H:%M')}–{seg['end'].strftime('%H:%M')}")
            )

        # Live current period, in its own thin lane.
        if self.current is not None:
            x0 = self.x_for(self.current["start"], left, usable_w)
            x1 = self.x_for(self.current["end"], left, usable_w)
            rect = QtCore.QRectF(x0, cur_y, max(2.0, x1 - x0), cur_h)
            painter.setBrush(SEGMENT_COLORS["current"])
            painter.drawRoundedRect(rect, 2, 2)
            self.hit_areas.append((rect, f"Current  from {self.current['start'].strftime('%H:%M')}"))

        # "Now" marker.
        if self.now is not None:
            nx = self.x_for(self.now, left, usable_w)
            painter.setPen(QtGui.QPen(NOW_COLOR, 1))
            painter.drawLine(QtCore.QPointF(nx, track_y - 2), QtCore.QPointF(nx, cur_y + cur_h + 1))
        painter.end()

    def mouseMoveEvent(self, event) -> None:
        point = event.position()
        for rect, tip in self.hit_areas:
            if rect.contains(point):
                self.setToolTip(tip)
                return
        self.setToolTip("")


class ActivityDialog(QtWidgets.QDialog):
    """Settings + the per-day interval log for the local activity diary."""

    def __init__(self, collector, focus_controller=None, parent=None, start_now_timer=True) -> None:
        super().__init__(parent)
        self.collector = collector
        self.focus_controller = focus_controller
        self.setWindowTitle("Activity diary")
        self.setModal(False)
        self.resize(520, 500)

        settings = collector.settings
        layout = QtWidgets.QVBoxLayout(self)

        # Live line: what the focus tooltip shows, refreshed every second
        # while the dialog is open ("Focus · 17:42 left · ⌨ 1,204 · …").
        self.now_label = QtWidgets.QLabel("")
        self.now_label.setWordWrap(True)
        self.now_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.now_label)
        self.now_timer = QtCore.QTimer(self)
        self.now_timer.setInterval(1000)
        self.now_timer.timeout.connect(self.refresh_now)
        if start_now_timer:
            self.now_timer.start()
        # Live "Current" row bookkeeping.
        self.current_row = None
        self.current_start = None
        self.dpi = 96.0

        self.enabled_box = QtWidgets.QCheckBox("Keep a private activity diary (everything stays on this computer)")
        self.enabled_box.setChecked(settings.enabled)
        layout.addWidget(self.enabled_box)

        self.keyboard_box = QtWidgets.QCheckBox(
            "Also count keystrokes and clicks — counts only, never which keys"
        )
        self.keyboard_box.setChecked(settings.keyboard_enabled)
        layout.addWidget(self.keyboard_box)

        retention_row = QtWidgets.QHBoxLayout()
        retention_row.addWidget(QtWidgets.QLabel("Keep history for:"))
        self.retention_spin = QtWidgets.QSpinBox()
        self.retention_spin.setRange(7, 3650)
        self.retention_spin.setValue(settings.retention_days)
        self.retention_spin.setSuffix(" days")
        retention_row.addWidget(self.retention_spin)
        retention_row.addStretch(1)
        self.delete_button = QtWidgets.QPushButton("Delete all recorded data…")
        self.delete_button.clicked.connect(self.delete_all)
        retention_row.addWidget(self.delete_button)
        layout.addLayout(retention_row)

        day_row = QtWidgets.QHBoxLayout()
        day_row.addWidget(QtWidgets.QLabel("Show:"))
        self.day_combo = QtWidgets.QComboBox()
        self.day_combo.addItems(["Today", "Yesterday"])
        self.day_combo.currentIndexChanged.connect(self.refresh_log)
        day_row.addWidget(self.day_combo)
        day_row.addStretch(1)
        layout.addLayout(day_row)

        # Day rhythm strip: work → rest → next period, at a glance.
        self.timeline = DayTimeline()
        layout.addWidget(self.timeline)
        legend = QtWidgets.QLabel(
            "<span style='color:#d94a4a'>■</span> Work &nbsp;"
            "<span style='color:#4caf50'>■</span> Rest &nbsp;"
            "<span style='color:#e0a52e'>■</span> Interrupted &nbsp;"
            "<span style='color:#4a8fe2'>■</span> Current &nbsp;·&nbsp; │ now"
        )
        legend.setTextFormat(QtCore.Qt.TextFormat.RichText)
        legend.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(legend)

        self.table = QtWidgets.QTableWidget(0, len(TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels(TABLE_COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        # Never elide labels to "Focus …" — show them in full.
        self.table.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(TABLE_COLUMNS)):
            header.setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        self.totals_label = QtWidgets.QLabel("")
        self.totals_label.setWordWrap(True)
        layout.addWidget(self.totals_label)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save | QtWidgets.QDialogButtonBox.StandardButton.Close
        )
        buttons.accepted.connect(self.save_and_close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.refresh_log()
        self.refresh_now()

    # -- data -------------------------------------------------------------------

    def refresh_now(self) -> None:
        """Every second: update the countdown line and the live Current row."""
        controller = self.focus_controller
        status = controller.status_text() if controller is not None else ""
        if status:
            self.now_label.setText(f"Now: {status}")
        else:
            self.now_label.setText("Now: idle — auto-pomodoro starts a session when you get going.")

        # The Current row only lives on the Today view.
        if self.day_combo.currentIndex() != 0:
            return
        period = self.current_period()
        start = period["start"] if period else None
        phase = period["phase"] if period else None
        if start != self.current_start or phase != self.current_phase:
            # A period began, ended, or flipped work↔rest — rebuild.
            self.refresh_log()
            return
        if period is not None and self.current_row is not None:
            self.set_cell(self.current_row, 3, f"{period['keys']:,}")
            self.set_cell(self.current_row, 4, f"{period['clicks']:,}")
            self.set_cell(self.current_row, 5, format_path(period["mouse_px"], self.dpi))
            self.set_cell(self.current_row, 6, f"{period['active_pct']}%")
            self.timeline.set_data(*self.build_timeline())

    def current_period(self):
        """The current period as a work/rest-labelled dict, or None.

        Prefers the pomodoro phase (so the row plainly says Work or Rest);
        falls back to the raw activity run ("Working", no timer) when no
        session is running.
        """
        controller = self.focus_controller
        if controller is not None and controller.state in ("focus", "break"):
            stats = controller.current_session_stats()
            if stats is None:
                return None
            if controller.state == "focus":
                label, color, phase = "▶ Work", "#d94a4a", "focus"
            else:
                rest = "Long rest" if getattr(controller, "on_long_break", False) else "Rest"
                label, color, phase = f"▶ {rest}", "#4caf50", "break"
            return {**stats, "label": label, "color": color, "phase": phase}
        stats = self.collector.current_run_stats()
        if stats is None:
            return None
        return {**stats, "label": "▶ Working", "color": "#555555", "phase": "current"}

    def build_timeline(self):
        """(segments, current, window_start, window_end, now) for DayTimeline."""
        day = self.selected_day()
        store = self.collector.store
        is_today = self.day_combo.currentIndex() == 0
        now = self.collector.now_fn()
        segments = []
        for session in activity_mod.sessions_table(store, day):
            end = session["start"] + timedelta(seconds=session["duration_seconds"])
            if session["kind"] == "focus" and not session["completed"]:
                kind = "interrupted"
            elif session["kind"] == "focus":
                kind = "focus"
            else:
                kind = "break"
            segments.append({"start": session["start"], "end": end, "kind": kind})
        current = None
        if is_today:
            period = self.current_period()
            if period is not None:
                kind = period["phase"] if period["phase"] in ("focus", "break") else "current"
                current = {"start": period["start"], "end": now, "kind": kind}
        starts = [s["start"] for s in segments] + ([current["start"]] if current else [])
        ends = [s["end"] for s in segments] + ([current["end"]] if current else [])
        if starts:
            window_start = min(starts).replace(minute=0, second=0, microsecond=0)
            window_end = max(ends)
        else:
            window_start = datetime.combine(day, day_time(9, 0))
            window_end = datetime.combine(day, day_time(18, 0))
        if is_today:
            window_end = max(window_end, now)
        return segments, current, window_start, window_end, (now if is_today else None)

    def selected_day(self) -> date:
        today = self.collector.now_fn().date()
        return today if self.day_combo.currentIndex() == 0 else today - timedelta(days=1)

    def refresh_log(self) -> None:
        day = self.selected_day()
        store = self.collector.store
        self.dpi = screen_dpi()
        self.table.setRowCount(0)
        self.current_row = None
        self.current_start = None
        self.current_phase = None
        try:
            rows = activity_mod.sessions_table(store, day)
            summary = activity_mod.day_summary(store, day, dpi=self.dpi)
        except Exception:  # noqa: BLE001 - a broken DB shows an empty table, not a crash
            logger.exception("Failed to build activity table")
            self.totals_label.setText("Could not read the activity database.")
            return

        # The day-rhythm strip.
        self.timeline.set_data(*self.build_timeline())

        # A live "Current period" row on top — labelled Work / Rest / Working
        # so it is obvious what you should be doing right now.
        period = self.current_period() if self.day_combo.currentIndex() == 0 else None
        if period is not None:
            self.append_row(
                [
                    period["label"],
                    period["start"].strftime("%H:%M"),
                    "Current",
                    f"{period['keys']:,}",
                    f"{period['clicks']:,}",
                    format_path(period["mouse_px"], self.dpi),
                    f"{period['active_pct']}%",
                ],
                italic=True,
            )
            self.table.item(0, 0).setForeground(QtGui.QColor(period["color"]))
            self.current_row = 0
            self.current_start = period["start"]
            self.current_phase = period["phase"]

        # Finished sessions, newest first.
        for session in reversed(rows):
            if session["kind"] == "focus" and not session["completed"]:
                label = "🍌 Interrupted"  # a stopped pomodoro
            elif session["kind"] == "focus":
                label = "🍅 Focus"
            else:
                label = "☕ Break"
            window_minutes = session["duration_seconds"] // 60
            self.append_row(
                [
                    label,
                    session["start"].strftime("%H:%M"),
                    format_duration(session["duration_seconds"]),
                    f"{session['keys']:,}",
                    f"{session['clicks']:,}",
                    format_path(session["mouse_px"], self.dpi),
                    active_pct(session["active_minutes"], window_minutes),
                ]
            )

        # Bottom TOTAL row — day aggregates, only completed 🍅, no dot, no times.
        total_duration = sum(session["duration_seconds"] for session in rows)
        total_active = sum(session["active_minutes"] for session in rows)
        self.append_row(
            [
                f"TOTAL   🍅 {summary['focus_count']}",
                "",
                format_duration(total_duration),
                f"{summary['keys']:,}",
                f"{summary['clicks']:,}",
                format_path(summary["mouse_px_total"], self.dpi),
                active_pct(total_active, total_duration // 60),
            ],
            bold=True,
        )

    def append_row(self, cells, bold=False, italic=False) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, text in enumerate(cells):
            item = QtWidgets.QTableWidgetItem(text)
            if column != 0:
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            if bold or italic:
                font = item.font()
                font.setBold(bold)
                font.setItalic(italic)
                item.setFont(font)
            self.table.setItem(row, column, item)

    def set_cell(self, row, column, text) -> None:
        item = self.table.item(row, column)
        if item is not None:
            item.setText(text)

    def closeEvent(self, event) -> None:
        # Stop the ticking so a closed dialog never touches a stale controller.
        self.now_timer.stop()
        super().closeEvent(event)

    # -- actions ----------------------------------------------------------------

    def delete_all(self) -> None:
        answer = QtWidgets.QMessageBox.question(
            self,
            "Delete activity history",
            "Delete ALL recorded activity and focus sessions from this computer?\nThis cannot be undone.",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            self.collector.store.delete_all_activity()
            logger.info("Activity history deleted by user")
        except Exception:  # noqa: BLE001
            logger.exception("Failed to delete activity history")
        self.refresh_log()

    def save_and_close(self) -> None:
        settings = activity_mod.ActivitySettings(
            enabled=self.enabled_box.isChecked(),
            keyboard_enabled=self.keyboard_box.isChecked(),
            retention_days=self.retention_spin.value(),
            prompted=True,
        )
        activity_mod.save_activity_settings(settings)
        self.collector.apply_settings(settings)
        logger.info("Activity settings saved (enabled=%s, keyboard=%s)", settings.enabled, settings.keyboard_enabled)
        self.accept()


__all__ = ["ActivityDialog"]
