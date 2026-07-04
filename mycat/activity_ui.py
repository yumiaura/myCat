#!/usr/bin/env python3
"""Activity diary dialog: opt-in switches, the interval log, day totals.

The log speaks in honest wording ("away from the computer", not "not
working"); the only place silence is praised is a pomodoro break.
"""

import csv
import logging
from datetime import date, datetime, timedelta
from datetime import time as day_time
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

if __package__:
    from . import activity as activity_mod
    from . import focus as focus_mod
    from .ui_theme import LIGHT_QSS
else:
    import importlib

    activity_mod = importlib.import_module("mycat.activity")
    focus_mod = importlib.import_module("mycat.focus")
    LIGHT_QSS = importlib.import_module("mycat.ui_theme").LIGHT_QSS

logger = logging.getLogger(__name__)

KIND_ICONS = {"focus": "🍅", "break": "☕", "long_break": "☕", "work": "💻"}

# Session table: start + duration per session, then the input counters and
# how active that stretch was. The bottom TOTAL row carries NO start/end times.
# U+FE0E forces a monochrome (text) glyph — the keyboard obeys it. The mouse has
# no text glyph so it stays a colour emoji; the cursor's travel uses a plain path
# symbol (⤳) that always renders monochrome.
MONO = "︎"
TABLE_COLUMNS = ["Session", "Duration", f"⌨{MONO} Keys", f"🖱{MONO} Mouse", "Active"]


def active_pct(active_minutes: int, window_minutes: int) -> str:
    if window_minutes <= 0:
        return "—"
    return f"{min(100, round(100 * active_minutes / window_minutes))}%"


def format_duration(seconds: int) -> str:
    """Ticking clock for the live current row: M:SS, or H:MM:SS past an hour."""
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_hm(seconds: int) -> str:
    """Compact length for finished rows and the TOTAL: "45min", "1h05min"."""
    minutes = int(seconds // 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}min" if hours else f"{minutes}min"


def format_path(mouse_px: int, dpi: float) -> str:
    km = activity_mod.cursor_km(mouse_px, dpi)
    return f"{km:.2f} km" if km >= 0.1 else f"{int(km * 1000)} m"


def format_meters(mouse_px: int, dpi: float) -> str:
    return f"{int(activity_mod.cursor_km(mouse_px, dpi) * 1000):,} m"


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
TRACK_BG = QtGui.QColor("#ffffff")  # past but "not tracked" — white
TRACK_BORDER = QtGui.QColor("#c4c4cc")
FUTURE_BG = QtGui.QColor("#c4c4cc")  # hasn't happened yet — clear grey
GRID_COLOR = QtGui.QColor("#bcbcc2")
NOW_COLOR = QtGui.QColor("#1f6feb")  # the "now" marker — a strong accent
AXIS_TEXT = QtGui.QColor("#888888")
REST_COLOR = QtGui.QColor("#8bbf8b")  # tracked but no activity
HEAT_LOW = (233, 179, 179)  # a little activity → pale red
HEAT_HIGH = (192, 57, 43)  # lots of activity → deep red
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
        self.cells = []  # [(minute_dt, "rest"|"active", busy_pct)]
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
                painter.drawText(
                    QtCore.QRectF(hx - 14, axis_y, 28, 12), QtCore.Qt.AlignmentFlag.AlignCenter, hour.strftime("%H")
                )
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
            hour = hour + timedelta(hours=1)

        # Prominent "now" marker: a thick accent line with a triangle on top.
        if self.now is not None:
            nx = self.x_for(self.now, left, usable_w)
            painter.setPen(QtGui.QPen(NOW_COLOR, 2))
            painter.drawLine(QtCore.QPointF(nx, top - 5), QtCore.QPointF(nx, top + track_h + 2))
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(NOW_COLOR)
            triangle = QtGui.QPolygonF(
                [
                    QtCore.QPointF(nx - 4, top - 7),
                    QtCore.QPointF(nx + 4, top - 7),
                    QtCore.QPointF(nx, top - 1),
                ]
            )
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
        self.setWindowTitle("Activity")
        self.setModal(False)
        self.setMinimumWidth(720)
        self.resize(760, 560)
        self.setStyleSheet(LIGHT_QSS)

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

        # All three toggles on one line: master Enable Activity, then the two
        # COUNT sub-tracks — Mouse = click count, Keyboard = key count — which
        # grey out while Activity is off. (Cursor path always records while
        # Activity is on — the cat's eyes need it.)
        self.enabled_box = QtWidgets.QCheckBox("Enable Activity")
        self.enabled_box.setToolTip(
            "Record your focus and how much you use the mouse and keyboard — how many\n"
            "keystrokes and clicks, never which keys. A private diary kept only on this\n"
            "computer; nothing is ever sent anywhere. Off = nothing is recorded."
        )
        self.enabled_box.setChecked(settings.enabled)
        self.mouse_box = QtWidgets.QCheckBox("Enable Mouse")
        self.mouse_box.setToolTip("Click count. Cursor path always records for the cat's eyes.")
        self.mouse_box.setChecked(settings.mouse_enabled)
        self.keyboard_box = QtWidgets.QCheckBox("Enable Keyboard")
        self.keyboard_box.setToolTip("Keystroke count (never which keys).")
        self.keyboard_box.setChecked(settings.keyboard_enabled)
        # Delete-all sits top-right, apart from the toggles — a destructive
        # action kept away from the day-picker row, which is already crowded.
        self.delete_button = QtWidgets.QPushButton("Delete all…")
        self.delete_button.clicked.connect(self.delete_all)
        toggles_row = QtWidgets.QHBoxLayout()
        toggles_row.addWidget(self.enabled_box)
        toggles_row.addSpacing(16)
        toggles_row.addWidget(self.mouse_box)
        toggles_row.addWidget(self.keyboard_box)
        toggles_row.addStretch(1)
        toggles_row.addWidget(self.delete_button)
        layout.addLayout(toggles_row)
        self.enabled_box.toggled.connect(self.mouse_box.setEnabled)
        self.enabled_box.toggled.connect(self.keyboard_box.setEnabled)
        self.mouse_box.setEnabled(settings.enabled)
        self.keyboard_box.setEnabled(settings.enabled)

        # Cursor path works without pynput; only the counts need mycat[basic].
        if not activity_mod.pynput_available():
            hint = QtWidgets.QLabel(
                "Key/click counts need <code>pip install mycat[basic]</code> — cursor path works without it."
            )
            hint.setTextFormat(QtCore.Qt.TextFormat.RichText)
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #888888;")
            layout.addWidget(hint)

        controls_row = QtWidgets.QHBoxLayout()
        controls_row.addWidget(QtWidgets.QLabel("Show:"))
        self.day_combo = QtWidgets.QComboBox()
        self.day_combo.addItems(["Today", "Yesterday"])
        self.day_combo.currentIndexChanged.connect(self.refresh_log)
        controls_row.addWidget(self.day_combo)
        controls_row.addSpacing(16)
        controls_row.addWidget(QtWidgets.QLabel("History:"))
        self.retention_spin = QtWidgets.QSpinBox()
        self.retention_spin.setRange(7, 3650)
        self.retention_spin.setValue(settings.retention_days)
        self.retention_spin.setSuffix(" days")
        controls_row.addWidget(self.retention_spin)
        controls_row.addSpacing(16)
        # The Pomodoro goal: a run this long earns a 🍅 (persisted to [focus]).
        controls_row.addWidget(QtWidgets.QLabel("Pomodoro goal:"))
        self.goal_spin = QtWidgets.QSpinBox()
        self.goal_spin.setRange(1, 240)
        self.goal_spin.setValue(self.focus_minutes())
        self.goal_spin.setSuffix(" min")
        controls_row.addWidget(self.goal_spin)
        controls_row.addStretch(1)
        layout.addLayout(controls_row)

        # Day activity strip: red = active (deeper = busier), green = rest,
        # grey = not tracked.
        self.timeline = DayTimeline()
        layout.addWidget(self.timeline)
        legend = QtWidgets.QLabel(
            "<span style='color:#8bbf8b'>■</span> rest"
            "&nbsp;&nbsp;&nbsp;<span style='color:#c0392b'>■</span> active"
            "&nbsp;&nbsp;&nbsp;<span style='color:#c4c4cc'>■</span> future"
            "&nbsp;&nbsp;&nbsp;<span style='color:#1f6feb'>│</span> now"
        )
        legend.setTextFormat(QtCore.Qt.TextFormat.RichText)
        legend.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        # No style override — the legend text uses the dialog's main font; only
        # the swatch squares and the "now" bar are colour-coded (inline spans).
        layout.addWidget(legend)

        self.table = QtWidgets.QTableWidget(0, len(TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels(TABLE_COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        # Never elide labels to "Focus …" — show them in full.
        self.table.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)
        header = self.table.horizontalHeader()
        # Even columns: every section shares the width equally so the grid reads
        # tidily, instead of each numeric column hugging its content raggedly.
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setDefaultAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.table, 1)

        # TOTAL as a pinned one-row table under the columns — always visible, and
        # its cells line up under the main table (widths kept in sync below).
        self.totals_table = QtWidgets.QTableWidget(1, len(TABLE_COLUMNS))
        self.totals_table.horizontalHeader().setVisible(False)
        self.totals_table.verticalHeader().setVisible(False)
        self.totals_table.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.totals_table.setShowGrid(False)  # no gridlines under the totals
        # No border, and tight cell padding so the summary row sits compact.
        self.totals_table.setStyleSheet(
            "QTableWidget { border: none; background: #ffffff; color: #1c1c1c; }"
            "QTableWidget::item { padding: 0px 6px; }"
        )
        self.totals_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.totals_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.totals_table.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.totals_table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.totals_table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for column in range(len(TABLE_COLUMNS)):
            self.totals_table.horizontalHeader().setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.totals_table.verticalHeader().setDefaultSectionSize(22)
        self.totals_table.setRowHeight(0, 22)
        self.totals_table.setFixedHeight(22)
        layout.addWidget(self.totals_table)
        self.table.horizontalHeader().sectionResized.connect(self.sync_total_widths)
        QtCore.QTimer.singleShot(0, self.sync_total_widths)

        # Save/Export feedback sits right above the buttons (green on success).
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Export (left) · Save, Close (right), same style as the other dialogs.
        button_row = QtWidgets.QHBoxLayout()
        self.export_button = QtWidgets.QPushButton("Export CSV…")
        self.export_button.clicked.connect(self.export_csv)
        button_row.addWidget(self.export_button)
        button_row.addStretch(1)
        self.save_button = QtWidgets.QPushButton("Save")
        self.close_button = QtWidgets.QPushButton("Close")
        self.save_button.clicked.connect(self.save_settings)
        self.close_button.clicked.connect(self.reject)
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)

        self.refresh_log()
        self.refresh_now()

    # -- data -------------------------------------------------------------------

    def refresh_now(self) -> None:
        """Every second: update the countdown line and the live Current row."""
        controller = self.focus_controller
        status = controller.status_text() if controller is not None else ""
        if status:
            self.now_label.setText(f"Current: {status}")
        else:
            self.now_label.setText("Current: idle — start working and a 🍅 builds after 25 min.")

        # On the Today view, rebuild every second so the live current row and
        # the timeline stay current (the table is small — a rebuild is cheap).
        if self.day_combo.currentIndex() == 0:
            self.refresh_log()

    def focus_minutes(self) -> int:
        controller = self.focus_controller
        if controller is not None and getattr(controller, "settings", None) is not None:
            return controller.settings.focus_minutes
        return activity_mod.FOCUS_MINUTES

    def current_period(self):
        """The live current activity run as a labelled dict, or None when idle.

        Focus is purely activity-driven now: a run at/over ``focus_minutes``
        has earned its 🍅; before that it is still building toward one.
        """
        stats = self.collector.current_run_stats()
        if stats is None:
            return None
        elapsed = self.collector.now_fn() - stats["start"]
        earned = elapsed.total_seconds() >= self.focus_minutes() * 60
        label = "▶ 🍅" if earned else "▶"
        return {**stats, "label": label, "color": "#d94a4a", "phase": "focus", "earned": earned}

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
            runs = activity_mod.graded_runs(store, day, self.focus_minutes())
        except Exception:  # noqa: BLE001 - a broken DB shows an empty table, not a crash
            logger.exception("Failed to build activity table")
            self.set_totals(["Could not read the activity database.", "", "", "", "", ""])
            return

        now = self.collector.now_fn()
        is_today = self.day_combo.currentIndex() == 0

        # The activity heat strip.
        self.timeline.set_data(*self.build_timeline())

        # The live current run is the last one still reaching now.
        current_run = None
        if is_today and runs and now - runs[-1]["last"] < timedelta(minutes=activity_mod.IDLE_RESUME_MINUTES):
            current_run = runs.pop()

        totals = {"keys": 0, "clicks": 0, "mouse_px": 0, "active": 0, "elapsed": 0}

        def emit(
            label, start_text, duration_text, keys, clicks, mouse_px, active_text, color=None, bold=False, italic=False
        ):
            session = f"{label} {start_text}".strip() if start_text else label
            self.append_row(
                [
                    session,
                    duration_text,
                    f"{keys:,}",
                    f"{clicks:,} / {format_path(mouse_px, self.dpi)}",
                    active_text,
                ],
                bold=bold,
                italic=italic,
            )
            if color is not None:
                self.table.item(self.table.rowCount() - 1, 0).setForeground(QtGui.QColor(color))
            totals["keys"] += keys
            totals["clicks"] += clicks
            totals["mouse_px"] += mouse_px

        tomatoes = sum(1 for run in runs if run["grade"] == "focus")

        # --- current run on top (elapsed time in Duration; 🍅 once earned) ---
        if current_run is not None:
            period = self.current_period()
            if period is not None:
                elapsed = now - period["start"]
                emit(
                    period["label"],
                    period["start"].strftime("%H:%M"),
                    format_duration(elapsed.total_seconds()),
                    period["keys"],
                    period["clicks"],
                    period["mouse_px"],
                    f"{period['active_pct']}%",
                    color=period["color"],
                    italic=True,
                )
                totals["active"] += period.get("active_minutes", 0)
                totals["elapsed"] += max(1, int(elapsed.total_seconds() // 60))
                if period["earned"]:
                    tomatoes += 1
                self.current_row = 0
                self.current_start = period["start"]
                self.current_phase = "focus"

        # --- finished runs, newest first: 🍅 (≥25 min) or 🍌 (any shorter run) ---
        for run in sorted(runs, key=lambda r: r["start"], reverse=True):
            label = "🍅" if run["grade"] == "focus" else "🍌"
            duration_seconds = (run["end"] - run["start"]).total_seconds()
            emit(
                label,
                run["start"].strftime("%H:%M"),
                format_hm(duration_seconds),
                run["keys"],
                run["clicks"],
                run["mouse_px"],
                active_pct(run["active_minutes"], run["minutes"]),
                color=None,
            )
            totals["active"] += run["active_minutes"]
            totals["elapsed"] += run["minutes"]

        # --- TOTAL = 🍅 earned today + summed activity of the rows above ---
        # TOTAL lives in its own pinned row under the table, aligned to the
        # columns, so it stays visible even when the rows scroll.
        self.set_totals(
            [
                f"TOTAL 🍅 {tomatoes}",
                format_hm(totals["active"] * 60),
                f"{totals['keys']:,}",
                f"{totals['clicks']:,} / {format_meters(totals['mouse_px'], self.dpi)}",
                active_pct(totals["active"], totals["elapsed"]),
            ]
        )

    def sync_total_widths(self, *args) -> None:
        """Keep the TOTAL row's columns lined up under the main table's."""
        header = self.table.horizontalHeader()
        for column in range(self.table.columnCount()):
            self.totals_table.setColumnWidth(column, header.sectionSize(column))

    def set_totals(self, cells) -> None:
        """Fill the pinned TOTAL row (bold; centered like the main table)."""
        for column, text in enumerate(cells):
            item = self.totals_table.item(0, column)
            if item is None:
                item = QtWidgets.QTableWidgetItem()
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                if column != 0:
                    item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                self.totals_table.setItem(0, column, item)
            item.setText(text)
        self.sync_total_widths()

    def append_row(self, cells, bold=False, italic=False) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, text in enumerate(cells):
            item = QtWidgets.QTableWidgetItem(text)
            if column != 0:
                # Centered under the centered headers → an even, tidy grid.
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
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

    def period_rows(self):
        """Finished focus attempts for the selected day, as plain numbers in
        chronological order — ready for CSV. Each is a 🍅 (``completed=1``, ran
        ≥ focus_minutes) or a 🍌 (fell short). The still-running current run is
        left out (it lands in the file once it ends); sub-threshold blips are
        skipped."""
        day = self.selected_day()
        store = self.collector.store
        dpi = screen_dpi()
        now = self.collector.now_fn()
        is_today = self.day_combo.currentIndex() == 0

        runs = activity_mod.graded_runs(store, day, self.focus_minutes())
        if is_today and runs and now - runs[-1]["last"] < timedelta(minutes=activity_mod.IDLE_RESUME_MINUTES):
            runs.pop()  # still running — leave it out of the record

        rows = [
            {
                "period": "Focus",
                "start": run["start"],
                "end": run["end"],
                "duration_seconds": int((run["end"] - run["start"]).total_seconds()),
                "keys": run["keys"],
                "clicks": run["clicks"],
                "mouse_px": run["mouse_px"],
                "active_minutes": run["active_minutes"],
                "completed": run["grade"] == "focus",
            }
            for run in runs
        ]
        rows.sort(key=lambda entry: entry["start"])
        return rows, dpi

    def write_csv(self, path: str) -> int:
        """Write the selected day's periods to ``path``; returns rows written."""
        rows, dpi = self.period_rows()
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "period",
                    "start",
                    "end",
                    "duration_seconds",
                    "keys",
                    "clicks",
                    "mouse_pixels",
                    "mouse_meters",
                    "active_minutes",
                    "active_percent",
                    "completed",
                ]
            )
            for entry in rows:
                meters = round(activity_mod.cursor_km(entry["mouse_px"], dpi) * 1000.0, 1)
                window_minutes = max(1, entry["duration_seconds"] // 60)
                percent = min(100, round(100 * entry["active_minutes"] / window_minutes))
                writer.writerow(
                    [
                        entry["period"],
                        entry["start"].isoformat(timespec="seconds"),
                        entry["end"].isoformat(timespec="seconds"),
                        entry["duration_seconds"],
                        entry["keys"],
                        entry["clicks"],
                        entry["mouse_px"],
                        meters,
                        entry["active_minutes"],
                        percent,
                        int(entry["completed"]),
                    ]
                )
        return len(rows)

    def export_csv(self) -> None:
        day = self.selected_day()
        default_name = f"mycat-activity-{day.isoformat()}.csv"
        path, chosen = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export activity to CSV", default_name, "CSV files (*.csv)"
        )
        if not path:
            return
        if chosen and chosen.startswith("CSV") and not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            count = self.write_csv(path)
        except OSError:
            logger.exception("Failed to export activity CSV")
            self.set_status("Could not write the CSV file.", ok=False)
            return
        logger.info("Activity exported to CSV (%d periods) -> %s", count, path)
        self.set_status(f"Exported {count} periods to {Path(path).name}.", ok=True)

    def set_status(self, text: str, ok: bool | None = None) -> None:
        """Status line above the buttons: green when ok, red when not."""
        color = {True: "#1c7c2f", False: "#c0392b", None: "#555555"}[ok]
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(text)

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

    def save_settings(self) -> None:
        """Persist + apply, keeping the dialog open (matches GitHub/Calendar)."""
        settings = activity_mod.ActivitySettings(
            enabled=self.enabled_box.isChecked(),
            mouse_enabled=self.mouse_box.isChecked(),
            keyboard_enabled=self.keyboard_box.isChecked(),
            retention_days=self.retention_spin.value(),
            prompted=True,
        )
        activity_mod.save_activity_settings(settings)
        self.collector.apply_settings(settings)

        # Persist + apply the Pomodoro goal (lives in [focus]).
        goal = self.goal_spin.value()
        focus_mod.save_focus_settings(focus_mod.FocusSettings(focus_minutes=goal))
        controller = self.focus_controller
        if controller is not None and getattr(controller, "settings", None) is not None:
            controller.settings.focus_minutes = goal
        self.refresh_log()  # re-grade runs against the new goal right away

        logger.info(
            "Activity settings saved (enabled=%s mouse=%s keyboard=%s goal=%dmin)",
            settings.enabled,
            settings.mouse_enabled,
            settings.keyboard_enabled,
            goal,
        )
        if settings.enabled:
            mouse = "✓" if settings.mouse_enabled else "✗"
            keyboard = "✓" if settings.keyboard_enabled else "✗"
            status = (
                f"Saved: activity on · mouse {mouse} · keyboard {keyboard} · "
                f"goal {goal} min, keep {settings.retention_days} days."
            )
        else:
            status = f"Saved: activity off · goal {goal} min, keep {settings.retention_days} days."
        self.set_status(status, ok=True)


__all__ = ["ActivityDialog"]
