#!/usr/bin/env python3
"""The thin progress bar under the cat during a focus session.

Deliberately the least exciting widget in the app: a 6-px rounded bar that
fills over the session. Opaque painting plus a rounded ``setMask`` keeps it
correct on X11 without a compositor (no translucency involved at all), and
``WA_TransparentForMouseEvents`` means it never steals a click — the status
tooltip lives on the cat itself.
"""

import logging

from PySide6 import QtCore, QtGui, QtWidgets

logger = logging.getLogger(__name__)

BAR_HEIGHT = 6
BAR_GAP = 3  # vertical gap between the cat window and the bar
CORNER_RADIUS = 3

TRACK_COLOR = QtGui.QColor("#3a2b33")
FOCUS_FILL = QtGui.QColor("#d94a4a")  # matches the red plane livery
BREAK_FILL = QtGui.QColor("#4caf50")


class FocusBarWindow(QtWidgets.QWidget):
    """Frameless, click-through, always-on-top strip that follows the cat."""

    def __init__(self) -> None:
        flags = (
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.Tool
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
        )
        super().__init__(None, flags)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.progress = 0.0
        self.on_break = False

    def update_state(self, progress: float, on_break: bool, tooltip: str) -> None:
        self.progress = min(1.0, max(0.0, progress))
        self.on_break = on_break
        self.setToolTip(tooltip)  # only visible if click-through is ever lifted
        self.update()

    def follow(self, cat_window: QtWidgets.QWidget) -> None:
        """Sit right under the cat, matching its width."""
        geometry = cat_window.geometry()
        self.setGeometry(
            geometry.x(),
            geometry.y() + geometry.height() + BAR_GAP,
            max(40, geometry.width()),
            BAR_HEIGHT,
        )
        # Clip to the rounded shape so the corners don't show as black squares
        # on X11 sessions without a compositor.
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(self.rect()), CORNER_RADIUS, CORNER_RADIUS)
        self.setMask(QtGui.QRegion(path.toFillPolygon().toPolygon()))

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(TRACK_COLOR)
        painter.drawRoundedRect(self.rect(), CORNER_RADIUS, CORNER_RADIUS)
        fill_width = int(self.width() * self.progress)
        if fill_width > 0:
            painter.setBrush(BREAK_FILL if self.on_break else FOCUS_FILL)
            width = max(fill_width, CORNER_RADIUS * 2)
            painter.drawRoundedRect(0, 0, width, self.height(), CORNER_RADIUS, CORNER_RADIUS)
        painter.end()


__all__ = ["FocusBarWindow"]
