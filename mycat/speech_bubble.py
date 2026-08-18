"""Comic speech bubble shown above the cat, an alternative to the flyby plane.

When the *Speak messages in a bubble* toggle is on (Settings), every announcement
— reminders, GitHub, the digest, calendar, activity — is spoken by the cat in a
rounded comic bubble above its head: the text is typed out letter by letter (the
bubble grows as it types), held for a few seconds, then it disappears. The
message never flies a banner plane across the screen in this mode.

The setting lives in ``[settings] speech_bubble`` in config.ini.
"""

from __future__ import annotations

import logging

from PySide6 import QtCore, QtGui, QtWidgets

from . import config_store, paths

logger = logging.getLogger(__name__)

SETTINGS_SECTION = "settings"
# The Settings "Reminder" toggle: on (default) -> messages fly a plane across the
# screen; off -> the cat speaks them in a bubble instead, no plane at all.
CONFIG_KEY = "reminder_flyby"

TYPE_INTERVAL_MS = 35   # per revealed character
HOLD_SECONDS = 10.0     # how long the finished bubble lingers
MAX_TEXT_WIDTH = 280    # wrap long messages to this width
PAD_X, PAD_Y = 16, 12   # text padding inside the bubble body
TAIL_W, TAIL_H = 26, 18 # the downward tail pointing at the cat
CORNER = 16             # bubble corner radius
HEAD_GAP = 6            # gap between the tail tip and the cat's head


def reminder_flyby_enabled(cfg_file=None) -> bool:
    """Whether messages fly a plane (True, the default) rather than drop to a bubble."""
    config = config_store.read_config(cfg_file or paths.config_file())
    if config is not None and config.has_option(SETTINGS_SECTION, CONFIG_KEY):
        try:
            return config.getboolean(SETTINGS_SECTION, CONFIG_KEY)
        except ValueError:
            return True
    return True


def set_reminder_flyby(enabled: bool, cfg_file=None) -> None:
    """Persist the Settings 'Reminder' toggle (on = plane, off = bubble)."""
    config_store.write_section(
        SETTINGS_SECTION, {CONFIG_KEY: config_store.bool_str(bool(enabled))}, cfg_file or paths.config_file()
    )


def bubble_mode_enabled(cfg_file=None) -> bool:
    """Bubble mode is on exactly when the Reminder (flyby) toggle is off."""
    return not reminder_flyby_enabled(cfg_file)


class BubbleWindow(QtWidgets.QWidget):
    """A frameless bubble that types ``text`` above ``cat_window`` then vanishes.

    Duck-types :class:`reminder_ui.FlybyWindow` for the announcer: it exposes
    ``start()`` and, via ``WA_DeleteOnClose``, emits ``destroyed`` when it goes —
    so the announcer's pacing (one message at a time) keeps working.
    """

    def __init__(self, cat_window, text, url="", parent=None) -> None:
        flags = QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.Tool
        app = QtWidgets.QApplication.instance()
        platform_name = (app.platformName() or "").lower() if app is not None else ""
        if platform_name != "offscreen":
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        super().__init__(parent, flags)

        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        # Purely a speech bubble — clicks pass through to the cat/desktop beneath.
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        self.cat_window = cat_window
        self.full_text = (str(text) or "").strip()
        self.link_url = str(url or "")
        self.shown_chars = 0
        self.body_w = 40
        self.body_h = 30

        self.bubble_font = QtGui.QFont()
        self.bubble_font.setPointSize(11)

        self.type_timer = QtCore.QTimer(self)
        self.type_timer.setInterval(TYPE_INTERVAL_MS)
        self.type_timer.timeout.connect(self.on_type)

        self.hold_timer = QtCore.QTimer(self)
        self.hold_timer.setSingleShot(True)
        self.hold_timer.timeout.connect(self.close)

        # Re-anchor above the cat continuously, so the bubble follows a drag.
        self.follow_timer = QtCore.QTimer(self)
        self.follow_timer.setInterval(80)
        self.follow_timer.timeout.connect(self.reposition)

    # -- lifecycle -------------------------------------------------------------

    def start(self) -> None:
        if not self.full_text:
            QtCore.QTimer.singleShot(0, self.close)
            return
        self.relayout()
        self.show()
        self.raise_()
        self.type_timer.start()
        self.follow_timer.start()

    def on_type(self) -> None:
        self.shown_chars += 1
        self.relayout()
        if self.shown_chars >= len(self.full_text):
            self.type_timer.stop()
            self.hold_timer.start(int(HOLD_SECONDS * 1000))

    # -- geometry --------------------------------------------------------------

    def revealed_text(self) -> str:
        return self.full_text[: self.shown_chars]

    def measured_text_rect(self, text: str) -> QtCore.QRect:
        metrics = QtGui.QFontMetrics(self.bubble_font)
        flags = int(QtCore.Qt.TextFlag.TextWordWrap) | int(QtCore.Qt.AlignmentFlag.AlignLeft)
        return metrics.boundingRect(QtCore.QRect(0, 0, MAX_TEXT_WIDTH, 10000), flags, text or " ")

    def relayout(self) -> None:
        rect = self.measured_text_rect(self.revealed_text() or " ")
        self.body_w = max(rect.width(), 24) + 2 * PAD_X
        self.body_h = max(rect.height(), 20) + 2 * PAD_Y
        self.resize(self.body_w, self.body_h + TAIL_H)
        self.reposition()
        self.update()

    def reposition(self) -> None:
        cat = self.cat_window
        if cat is None:
            return
        head_top = cat.mapToGlobal(QtCore.QPoint(cat.width() // 2, 0))
        x = head_top.x() - self.width() // 2
        y = head_top.y() - self.height() - HEAD_GAP
        screen = cat.screen() or QtWidgets.QApplication.primaryScreen()
        if screen is not None:
            usable = screen.availableGeometry()
            x = max(usable.left(), min(x, usable.right() - self.width()))
            y = max(usable.top(), min(y, usable.bottom() - self.height()))
        self.move(x, y)

    def bubble_path(self) -> QtGui.QPainterPath:
        body = QtGui.QPainterPath()
        body.addRoundedRect(QtCore.QRectF(1, 1, self.body_w - 2, self.body_h - 2), CORNER, CORNER)
        center_x = self.body_w / 2
        tail = QtGui.QPainterPath()
        tail.moveTo(center_x - TAIL_W / 2, self.body_h - 2)
        tail.lineTo(center_x, self.body_h + TAIL_H - 2)
        tail.lineTo(center_x + TAIL_W / 2, self.body_h - 2)
        tail.closeSubpath()
        return body.united(tail)

    # -- paint -----------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        path = self.bubble_path()
        painter.setPen(QtGui.QPen(QtGui.QColor(40, 40, 40), 2))
        painter.setBrush(QtGui.QColor(255, 255, 255, 242))
        painter.drawPath(path)

        painter.setPen(QtGui.QColor(28, 28, 28))
        painter.setFont(self.bubble_font)
        text_area = QtCore.QRect(PAD_X, PAD_Y, self.body_w - 2 * PAD_X, self.body_h - 2 * PAD_Y)
        painter.drawText(
            text_area,
            int(QtCore.Qt.TextFlag.TextWordWrap)
            | int(QtCore.Qt.AlignmentFlag.AlignLeft)
            | int(QtCore.Qt.AlignmentFlag.AlignVCenter),
            self.revealed_text(),
        )
        painter.end()

        # On X11 with no compositor a translucent window paints its transparent
        # pixels black; clip the window to the bubble shape so no black box shows.
        self.setMask(QtGui.QRegion(path.toFillPolygon().toPolygon()))
