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


# Timeline is an activity heat strip, not a session timeline:
#   not tracked  → transparent (the grey track shows through)
#   tracked, idle→ green (a rest)
#   tracked, busy→ red, the redder the more input that minute carried
TRACK_BG = QtGui.QColor("#ffffff")       # past but "not tracked" — white
TRACK_BORDER = QtGui.QColor("#c4c4cc")
FUTURE_BG = QtGui.QColor("#c4c4cc")       # hasn't happened yet — clear grey
GRID_COLOR = QtGui.QColor("#bcbcc2")
NOW_COLOR = QtGui.QColor("#1f6feb")      # the "now" marker — a strong accent
AXIS_TEXT = QtGui.QColor("#888888")
REST_COLOR = QtGui.QColor("#8bbf8b")     # tracked but no activity
HEAT_LOW = (233, 179, 179)               # a little activity → pale red
HEAT_HIGH = (192, 57, 43)                # lots of activity → deep red
# One busy minute's input mapped to full saturation (keys + weighted clicks + px).
BUSY_FULL = 300.0


def busy_fraction(keys: int, clicks: int, mouse_px: int) -> float:
    busy = keys + clicks * 5 + mouse_px / 100.0
    return min(1.0, busy / BUSY_FULL)


def heat_color(pct: float) -> QtGui.QColor:
    r = round(HEAT_LOW[0] + (HEAT_HIGH[0] - HEAT_LOW[0]) * pct)
    g = round(HEAT_LOW[1] + (HEAT_HIGH[1] - HEAT_LOW[1]) * pct)
    b = round(HEAT_LOW[2] + (HEAT_HIGH[2] - HEAT_LOW[2]) * pct)
    return QtGui.QColor(r, g, b)


class DayTimeline(QtWidgets.QWidget):
    """Per-minute activity heat strip for the day.

    Each recorded minute is a thin bar: green when you were at rest and red
    (deeper = busier) when you were active. Minutes with no data leave the
    grey track showing, so gaps read as "not tracked". A dark line marks now.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(50)
        self.setMouseTracking(True)
        self.cells = []          # [(minute_dt, "rest"|"active", busy_pct)]
        self.window_start = None
        self.window_end = None
        self.now = None

    def set_data(self, cells, window_start, window_end, now) -> None:
        self.cells = cells
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

        left, top = 8, 9
        track_h = 22
        axis_y = top + track_h + 3
        usable_w = max(1, self.width() - 2 * left)
        track_rect = QtCore.QRectF(left, top, usable_w, track_h)

        # White "not tracked" (past) track with a thin outline.
        painter.setBrush(TRACK_BG)
        painter.setPen(QtGui.QPen(TRACK_BORDER, 1))
        painter.drawRoundedRect(track_rect, 4, 4)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)

        span_minutes = max(1.0, (self.window_end - self.window_start).total_seconds() / 60.0)
        minute_w = usable_w / span_minutes
        clip = QtGui.QPainterPath()
        clip.addRoundedRect(track_rect, 4, 4)
        painter.save()
        painter.setClipPath(clip)

        # The future (now → end) is a lighter grey: it simply hasn't happened.
        if self.now is not None and self.now < self.window_end:
            fx = self.x_for(self.now, left, usable_w)
            painter.fillRect(QtCore.QRectF(fx, top, left + usable_w - fx, track_h), FUTURE_BG)

        # Per-minute heat over the past.
        for minute_dt, kind, pct in self.cells:
            x0 = self.x_for(minute_dt, left, usable_w)
            color = REST_COLOR if kind == "rest" else heat_color(pct)
            painter.fillRect(QtCore.QRectF(x0, top, max(1.0, minute_w + 0.6), track_h), color)
        painter.restore()

        # Hour gridlines + labels, thinned out for wide (full-day) windows.
        span_hours = (self.window_end - self.window_start).total_seconds() / 3600.0
        step = 1 if span_hours <= 8 else 2 if span_hours <= 16 else 3
        painter.setFont(QtGui.QFont(self.font().family(), 7))
        hour = self.window_start.replace(minute=0, second=0, microsecond=0)
        if hour < self.window_start:
            hour = hour + timedelta(hours=1)
        while hour <= self.window_end:
            if hour.hour % step == 0:
                hx = self.x_for(hour, left, usable_w)
                painter.setPen(QtGui.QPen(GRID_COLOR, 1))
                painter.drawLine(QtCore.QPointF(hx, top), QtCore.QPointF(hx, top + track_h))
                painter.setPen(QtGui.QPen(AXIS_TEXT))
                painter.drawText(QtCore.QRectF(hx - 14, axis_y, 28, 12),
                                 QtCore.Qt.AlignmentFlag.AlignCenter, hour.strftime("%H"))
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
            hour = hour + timedelta(hours=1)

        # Prominent "now" marker: a thick accent line with a triangle on top.
        if self.now is not None:
            nx = self.x_for(self.now, left, usable_w)
            painter.setPen(QtGui.QPen(NOW_COLOR, 2))
            painter.drawLine(QtCore.QPointF(nx, top - 5), QtCore.QPointF(nx, top + track_h + 2))
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(NOW_COLOR)
            triangle = QtGui.QPolygonF([
                QtCore.QPointF(nx - 4, top - 7),
                QtCore.QPointF(nx + 4, top - 7),
                QtCore.QPointF(nx, top - 1),
            ])
            painter.drawPolygon(triangle)
        painter.end()

    def mouseMoveEvent(self, event) -> None:
        if self.window_start is None:
            return
        left = 8
        usable_w = max(1, self.width() - 2 * left)
        frac = min(1.0, max(0.0, (event.position().x() - left) / usable_w))
        span = (self.window_end - self.window_start).total_seconds()
        moment = self.window_start + timedelta(seconds=frac * span)
        self.setToolTip(moment.strftime("%H:%M"))


class ActivityDialog(QtWidgets.QDialog):
    """Settings + the per-day interval log for the local activity diary."""

    def __init__(self, collector, focus_controller=None, parent=None, start_now_timer=True) -> None:
        super().__init__(parent)
        self.collector = collector
        self.focus_controller = focus_controller
        self.setWindowTitle("Activity diary")
        self.setModal(False)
        self.setMinimumWidth(720)
        self.resize(760, 560)

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

        self.enabled_box = QtWidgets.QCheckBox("Track my activity")
        self.enabled_box.setToolTip(
            "Record focus sessions and how much you use the mouse and keyboard.\n"
            "A private diary kept only on this computer — nothing is ever sent anywhere.\n"
            "Off = nothing is recorded."
        )
        self.enabled_box.setChecked(settings.enabled)
        layout.addWidget(self.enabled_box)

        self.keyboard_box = QtWidgets.QCheckBox("…count keys + clicks too")
        self.keyboard_box.setToolTip(
            "Also count keystrokes and mouse clicks — how many, never which keys.\n"
            "Off = only cursor movement is measured."
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

        # Day activity strip: red = active (deeper = busier), green = rest,
        # grey = not tracked.
        self.timeline = DayTimeline()
        layout.addWidget(self.timeline)
        legend = QtWidgets.QLabel(
            "<span style='color:#8bbf8b'>■</span> rest &nbsp;"
            "<span style='color:#c0392b'>■</span> active <span style='color:#888'>(deeper = busier)</span> &nbsp;"
            "<span style='color:#d4d4da'>■</span> not yet &nbsp;·&nbsp; white = not tracked &nbsp;·&nbsp;"
            " <span style='color:#1f6feb'>│</span> now"
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

        # On the Today view, rebuild every second so the live current row and
        # the timeline stay current (the table is small — a rebuild is cheap).
        if self.day_combo.currentIndex() == 0:
            self.refresh_log()

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
                label, color, phase = "▶ Focus", "#d94a4a", "focus"
            else:
                label, color, phase = "▶ Break", "#4caf50", "break"
            return {**stats, "label": label, "color": color, "phase": phase}
        stats = self.collector.current_run_stats()
        if stats is None:
            return None
        return {**stats, "label": "▶ Other", "color": "#555555", "phase": "current"}

    def build_timeline(self):
        """(cells, window_start, window_end, now) — a per-minute activity heat.

        The window is always the FULL day, midnight→midnight, so the whole
        day is visible; today's untracked/future minutes stay grey and the
        "now" line marks how far along we are. Each recorded minute becomes a
        cell — green when idle, red (by input) when active.
        """
        day = self.selected_day()
        store = self.collector.store
        is_today = self.day_combo.currentIndex() == 0
        now = self.collector.now_fn()
        day_start = datetime.combine(day, day_time(0, 0))

        cells = []
        for row in store.minutes_between(day_start, day_start + timedelta(days=1)):
            minute_dt = datetime.fromisoformat(row["minute"])
            if row["active"]:
                cells.append((minute_dt, "active", busy_fraction(row["keys"], row["clicks"], row["mouse_px"])))
            else:
                cells.append((minute_dt, "rest", 0.0))

        # Extend the live edge with the not-yet-flushed current minute.
        if is_today and self.collector.current_run_stats() is not None:
            current_minute = now.replace(second=0, microsecond=0)
            if not cells or cells[-1][0] != current_minute:
                pct = busy_fraction(
                    int(self.collector.bucket_keys),
                    int(self.collector.bucket_clicks),
                    int(self.collector.bucket_mouse_px),
                )
                cells.append((current_minute, "active", max(pct, 0.12)))

        window_start = day_start
        window_end = day_start + timedelta(days=1)  # full day, both today and yesterday
        return cells, window_start, window_end, (now if is_today else None)

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

        now = self.collector.now_fn()
        is_today = self.day_combo.currentIndex() == 0

        # The activity heat strip.
        self.timeline.set_data(*self.build_timeline())

        # Pomodoro windows (finished + a running one) so their minutes are
        # attributed to Focus/Break, not to Other activity runs.
        windows = [(s["start"], s["start"] + timedelta(seconds=s["duration_seconds"])) for s in rows]
        controller = self.focus_controller
        running_session = is_today and controller is not None and controller.state in ("focus", "break")
        if running_session:
            windows.append((controller.phase_started, now))
        runs = activity_mod.activity_runs(self.collector.store, day, windows)

        # The current "Other" run is the last run still reaching now.
        current_run = None
        if is_today and not running_session and runs:
            if now - runs[-1]["last"] < timedelta(minutes=activity_mod.IDLE_RESUME_MINUTES):
                current_run = runs.pop()

        totals = {"keys": 0, "clicks": 0, "mouse_px": 0, "active": 0}

        def emit(label, start_text, duration_text, keys, clicks, mouse_px,
                 active_text, color=None, bold=False, italic=False):
            self.append_row(
                [label, start_text, duration_text, f"{keys:,}", f"{clicks:,}",
                 format_path(mouse_px, self.dpi), active_text],
                bold=bold,
                italic=italic,
            )
            if color is not None:
                self.table.item(self.table.rowCount() - 1, 0).setForeground(QtGui.QColor(color))
            totals["keys"] += keys
            totals["clicks"] += clicks
            totals["mouse_px"] += mouse_px

        # --- current period on top (elapsed time in Duration) ---
        if running_session:
            period = self.current_period()
            if period is not None:
                elapsed = now - period["start"]
                active = period.get("active_minutes", period.get("active", 0))
                emit(period["label"], period["start"].strftime("%H:%M"), format_duration(elapsed.total_seconds()),
                     period["keys"], period["clicks"], period["mouse_px"], f"{period['active_pct']}%",
                     color=period["color"], italic=True)
                totals["active"] += active
                self.current_row = 0
                self.current_start = period["start"]
                self.current_phase = period["phase"]
        elif current_run is not None:
            keys = current_run["keys"] + int(self.collector.bucket_keys)
            clicks = current_run["clicks"] + int(self.collector.bucket_clicks)
            mouse_px = current_run["mouse_px"] + int(self.collector.bucket_mouse_px)
            elapsed = now - current_run["start"]
            elapsed_minutes = max(1, int(elapsed.total_seconds() // 60))
            emit("▶ Other", current_run["start"].strftime("%H:%M"), format_duration(elapsed.total_seconds()),
                 keys, clicks, mouse_px, f"{min(100, round(100 * current_run['active_minutes'] / elapsed_minutes))}%",
                 color="#555555", italic=True)
            totals["active"] += current_run["active_minutes"]
            self.current_row = 0
            self.current_start = current_run["start"]
            self.current_phase = "current"

        # --- finished periods (Focus / Break / Other), newest first ---
        finished = [(s["start"], "session", s) for s in rows]
        finished += [(r["start"], "run", r) for r in runs]
        finished.sort(key=lambda item: item[0], reverse=True)

        for start, kind, obj in finished:
            if kind == "session":
                label = "🍅 Focus" if obj["kind"] == "focus" else "☕ Break"
                duration_seconds = obj["duration_seconds"]
                color = None
            else:
                label = "▷ Other"
                duration_seconds = (obj["end"] - obj["start"]).total_seconds()
                color = "#777777"
            window_minutes = max(1, int(duration_seconds // 60))
            emit(label, start.strftime("%H:%M"), format_duration(duration_seconds),
                 obj["keys"], obj["clicks"], obj["mouse_px"],
                 active_pct(obj["active_minutes"], window_minutes), color=color)
            totals["active"] += obj["active_minutes"]

        # --- TOTAL = the sum of the rows above ---
        self.append_row(
            [
                f"TOTAL 🍅 {summary['focus_count']}",
                "",
                format_duration(totals["active"] * 60),
                f"{totals['keys']:,}",
                f"{totals['clicks']:,}",
                format_path(totals["mouse_px"], self.dpi),
                "",
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
