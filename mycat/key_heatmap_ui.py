"""The on-screen keyboard heatmap window (opened by the Activity dialog).

Draws a Latin QWERTY board and colours each key by how often it was pressed
this session — cold blue for rarely, hot red for most. The counts are the
collector's in-memory per-cell tally: session-only, never written to disk, and
gone on restart. Collecting them is a separate opt-in (off by default) that
lives right here on the board.
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from . import activity as activity_mod
from . import key_heatmap
from .ui_theme import LIGHT_QSS

GREY = QtGui.QColor(210, 210, 210)
GREY_BORDER = QtGui.QColor(170, 170, 170)


class KeyboardBoard(QtWidgets.QWidget):
    """Paints KEYBOARD_ROWS, each key filled by its heat fraction."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.counts: dict[str, int] = {}
        self.peak = 0
        self.row_units = max(sum(w for _, _, w in row) for row in key_heatmap.KEYBOARD_ROWS)
        self.setMinimumSize(660, 250)

    def set_data(self, counts: dict[str, int]) -> None:
        self.counts = counts
        self.peak = max(counts.values()) if counts else 0
        self.update()

    def fraction(self, count: int) -> float:
        """Position on the 1→max scale: 1 press = 0.0 (blue), the peak = 1.0 (red)."""
        if self.peak <= 1:
            return 0.0
        return (count - 1) / (self.peak - 1)

    def paintEvent(self, event) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        gap = 4.0
        unit = (self.width() - gap) / self.row_units
        key_h = (self.height() - gap) / len(key_heatmap.KEYBOARD_ROWS)
        font = painter.font()
        font.setPointSizeF(max(7.0, min(unit, key_h) * 0.34))
        painter.setFont(font)

        y = gap / 2.0
        for row in key_heatmap.KEYBOARD_ROWS:
            x = gap / 2.0
            for cell_id, label, width in row:
                w = unit * width - gap
                h = key_h - gap
                rect = QtCore.QRectF(x, y, w, h)
                count = self.counts.get(cell_id, 0)
                if count > 0 and self.peak > 0:
                    r, g, b = key_heatmap.heat_rgb(self.fraction(count))
                    fill = QtGui.QColor(r, g, b)
                    border = fill.darker(130)
                    text_color = QtGui.QColor(20, 20, 20)
                else:
                    fill, border, text_color = GREY, GREY_BORDER, QtGui.QColor(90, 90, 90)
                painter.setBrush(fill)
                painter.setPen(QtGui.QPen(border, 1.0))
                painter.drawRoundedRect(rect, 4.0, 4.0)
                painter.setPen(text_color)
                if count > 0:
                    # Split the key: label in the top, the count below it, so the
                    # two never overlap on a 1-unit key.
                    label_rect = QtCore.QRectF(rect.x(), rect.y(), rect.width(), h * 0.60)
                    painter.drawText(label_rect, QtCore.Qt.AlignmentFlag.AlignCenter, label)
                    small = QtGui.QFont(font)
                    small.setPointSizeF(max(6.0, font.pointSizeF() * 0.72))
                    painter.setFont(small)
                    count_rect = QtCore.QRectF(rect.x(), rect.y() + h * 0.56, rect.width(), h * 0.40)
                    painter.drawText(count_rect, QtCore.Qt.AlignmentFlag.AlignCenter, f"{count:,}")
                    painter.setFont(font)
                else:
                    painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, label)
                x += unit * width
            y += key_h
        painter.end()


class HeatLegend(QtWidgets.QWidget):
    """Single-row colour scale: `1` (min) — gradient — peak (max), all inline."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.peak = 0
        self.setFixedHeight(24)

    def set_peak(self, peak: int) -> None:
        self.peak = peak
        self.update()

    def paintEvent(self, event) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        min_text = "1"
        max_text = f"{self.peak:,}" if self.peak > 0 else "—"
        metrics = painter.fontMetrics()
        min_w = metrics.horizontalAdvance(min_text)
        max_w = metrics.horizontalAdvance(max_text)
        h = float(self.height())

        painter.setPen(QtGui.QColor(110, 110, 110))
        left_cells = QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
        right_cells = QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        painter.drawText(QtCore.QRectF(0.0, 0.0, min_w, h), left_cells, min_text)
        painter.drawText(QtCore.QRectF(self.width() - max_w, 0.0, max_w, h), right_cells, max_text)

        pad = 8.0
        bar_h = 12.0
        bar = QtCore.QRectF(
            min_w + pad, (h - bar_h) / 2.0,
            max(1.0, self.width() - min_w - max_w - 2 * pad), bar_h,
        )
        gradient = QtGui.QLinearGradient(bar.left(), 0.0, bar.right(), 0.0)
        for step in range(11):
            r, g, b = key_heatmap.heat_rgb(step / 10.0)
            gradient.setColorAt(step / 10.0, QtGui.QColor(r, g, b))
        painter.setPen(QtGui.QPen(QtGui.QColor(150, 150, 150), 1.0))
        painter.setBrush(QtGui.QBrush(gradient))
        painter.drawRoundedRect(bar, 3.0, 3.0)
        painter.end()


class KeyboardHeatmapDialog(QtWidgets.QDialog):
    """A live keyboard heatmap for the current session."""

    def __init__(self, collector, parent=None) -> None:
        super().__init__(parent)
        self.collector = collector
        # Computed once — calling counts_available() opens (and closes) a fresh X
        # connection on the no-pynput path, which would stall the event loop if
        # done on the refresh timer. It can't change while the window is open.
        self.counting_available = activity_mod.counts_available()
        self.last_counts: dict[str, int] | None = None
        self.setWindowTitle("Keyboard heatmap")
        self.setModal(False)
        self.setMinimumWidth(700)
        self.resize(720, 400)
        self.setStyleSheet(LIGHT_QSS)

        layout = QtWidgets.QVBoxLayout(self)

        self.note = QtWidgets.QLabel("")
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: #888888;")
        layout.addWidget(self.note)

        self.board = KeyboardBoard(self)
        layout.addWidget(self.board, 1)
        layout.addSpacing(8)
        # The colour scale for the board, at the bottom.
        self.legend = HeatLegend(self)
        layout.addWidget(self.legend)
        # Keep a clear gap before the buttons — otherwise Close rides up against
        # the legend/board.
        layout.addSpacing(8)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch(1)
        self.close_button = QtWidgets.QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

        self.update_note()
        self.refresh()

    def update_note(self) -> None:
        if not self.counting_available:
            text = (
                "Key counting isn't available here (needs X11, or macOS Input Monitoring "
                "permission), so nothing can be collected."
            )
        elif not self.collector.settings.key_heatmap_enabled:
            text = "Collection is off — tick “Heatmap” in the Activity window and Save."
        else:
            text = ""
        if text != self.note.text():
            self.note.setText(text)

    def refresh(self) -> None:
        self.update_note()
        counts = self.collector.snapshot_key_cells()
        # Only repaint when the tally actually changed — an idle open window then
        # does no drawing work.
        if counts != self.last_counts:
            self.last_counts = counts
            self.board.set_data(counts)
            self.legend.set_peak(self.board.peak)

    def closeEvent(self, event) -> None:
        self.timer.stop()
        super().closeEvent(event)
