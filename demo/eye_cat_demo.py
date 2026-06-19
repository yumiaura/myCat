#!/usr/bin/env python3
"""LOCAL demo — a cat whose eyes follow the mouse cursor.

Uses ~/Pictures/mycat2.png (an orange cat drawn WITHOUT pupils), scales it to
200 px tall, auto-detects the two white eye sockets, and draws pupils that track
the global cursor (clamped inside each socket). Frameless, transparent,
always-on-top, draggable.

    python demo/eye_cat_demo.py
    python demo/eye_cat_demo.py --image /path/to/cat.png
"""

import argparse
import random
import sys
from collections import deque
from math import hypot, sqrt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

DEFAULT_IMAGE = Path(__file__).resolve().parent / "assets" / "mycat.png"
TARGET_HEIGHT = 200


def is_white(pixel):
    return pixel[3] > 40 and pixel[0] > 225 and pixel[1] > 225 and pixel[2] > 225


def detect_eyes(image: Image.Image):
    """Find the eye sockets: interior white blobs (white not connected to the
    border background), split left/right. Returns [(cx, cy, radius), ...]."""
    image = image.convert("RGBA")
    width, height = image.size
    px = image.load()
    background = set()
    queue = deque()
    for x in range(width):
        queue.extend([(x, 0), (x, height - 1)])
    for y in range(height):
        queue.extend([(0, y), (width - 1, y)])
    while queue:
        x, y = queue.popleft()
        if (x, y) in background or not (0 <= x < width and 0 <= y < height):
            continue
        if not is_white(px[x, y]):
            continue
        background.add((x, y))
        queue.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])
    interior = [(x, y) for x in range(width) for y in range(height)
                if is_white(px[x, y]) and (x, y) not in background]
    if not interior:
        return []
    mid_x = sum(p[0] for p in interior) / len(interior)
    eyes = []
    for blob in ([p for p in interior if p[0] < mid_x], [p for p in interior if p[0] >= mid_x]):
        if not blob:
            continue
        xs = [p[0] for p in blob]
        ys = [p[1] for p in blob]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        radius = min(max(xs) - min(xs), max(ys) - min(ys)) / 2
        eyes.append((cx, cy, radius))
    return eyes


def pil_to_pixmap(image: Image.Image) -> QtGui.QPixmap:
    image = image.convert("RGBA")
    data = image.tobytes("raw", "RGBA")
    qimage = QtGui.QImage(data, image.width, image.height, QtGui.QImage.Format.Format_RGBA8888)
    return QtGui.QPixmap.fromImage(qimage.copy())


def harden_alpha(image: Image.Image, threshold: int = 128) -> Image.Image:
    """Make the alpha binary (0/255). Downscaling anti-aliases the silhouette to
    partial alpha; without a compositor those pixels render as a muddy dark
    fringe. Snapping alpha to 0/255 gives a crisp edge that matches the 1-bit
    window mask exactly."""
    image = image.convert("RGBA")
    image.putalpha(image.getchannel("A").point(lambda value: 255 if value >= threshold else 0))
    return image


def dominant_fur(image: Image.Image) -> QtGui.QColor:
    """Most common body colour (ignore white eyes, dark outline, transparent)."""
    counts: dict = {}
    for r, g, b, a in image.convert("RGBA").getdata():
        if a < 200 or (r > 225 and g > 225 and b > 225) or (r < 60 and g < 60 and b < 60):
            continue
        key = (r // 16, g // 16, b // 16)
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return QtGui.QColor(240, 170, 90)
    r, g, b = max(counts, key=counts.get)
    return QtGui.QColor(r * 16 + 8, g * 16 + 8, b * 16 + 8)


def no_compositor() -> bool:
    try:
        from mycat.main import x11_compositor_active
        return x11_compositor_active() is False
    except Exception:
        return False


class EyeCat(QtWidgets.QWidget):
    def __init__(self, image_path: Path):
        flags = QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.Tool
        app = QtWidgets.QApplication.instance()
        if (app.platformName() or "").lower() != "offscreen":
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self.shape_mask = no_compositor()
        source = Image.open(image_path).convert("RGBA")
        scaled = source.resize(
            (round(source.width * TARGET_HEIGHT / source.height), TARGET_HEIGHT), Image.LANCZOS
        )
        # No compositor → 1-bit window mask; snap the anti-aliased edge to binary
        # alpha so it doesn't render as a muddy fringe. With a compositor we keep
        # the smooth alpha (it blends nicely).
        if self.shape_mask:
            scaled = harden_alpha(scaled)
        self.pixmap = pil_to_pixmap(scaled)
        self.eyes = detect_eyes(scaled)
        self.setFixedSize(self.pixmap.size())

        self.fur_color = dominant_fur(scaled)
        self.test_cursor = None       # set in tests to fake the cursor
        self.test_blink = None        # set in tests to force a blink amount
        self.drag_offset = None

        # Blink: a quick lid close/open every few seconds.
        self.blink_dur = 0.16
        self.clock = QtCore.QElapsedTimer()
        self.clock.start()
        self.blink_start = -10.0
        self.next_blink = random.uniform(2.5, 6.0)
        self.squint_start = -10.0      # set on click: a held "scrunch" close

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)          # ~60 fps

    def cursor_global(self) -> QtCore.QPoint:
        return self.test_cursor if self.test_cursor is not None else QtGui.QCursor.pos()

    def blink_amount(self) -> float:
        """0 = open, 1 = fully closed; triangular over the blink duration."""
        if self.test_blink is not None:
            return self.test_blink
        now = self.clock.elapsed() / 1000.0
        if now >= self.next_blink:
            self.blink_start = now
            self.next_blink = now + self.blink_dur + random.uniform(2.5, 6.0)
        progress = (now - self.blink_start) / self.blink_dur
        if 0.0 <= progress <= 1.0:
            return 1.0 - abs(2.0 * progress - 1.0)
        return 0.0

    def squint_amount(self) -> float:
        """Click reaction: snap shut, hold, then open (a held scrunch)."""
        elapsed = self.clock.elapsed() / 1000.0 - self.squint_start
        close, hold_end, total = 0.07, 0.45, 0.62
        if elapsed < 0.0:
            return 0.0
        if elapsed < close:
            return elapsed / close
        if elapsed < hold_end:
            return 1.0
        if elapsed < total:
            return 1.0 - (elapsed - hold_end) / (total - hold_end)
        return 0.0

    def showEvent(self, event):
        super().showEvent(event)
        if self.shape_mask and not self.pixmap.mask().isNull():
            self.setMask(self.pixmap.mask())

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.drawPixmap(0, 0, self.pixmap)
        cursor = self.cursor_global()
        blink = max(self.blink_amount(), self.squint_amount())
        for cx, cy, radius in self.eyes:
            pupil_r = max(2.5, radius * 0.45)
            max_offset = max(0.0, radius - pupil_r * 0.6)
            socket = self.mapToGlobal(QtCore.QPoint(round(cx), round(cy)))
            dx, dy = cursor.x() - socket.x(), cursor.y() - socket.y()
            dist = hypot(dx, dy)
            ox, oy = (dx / dist * max_offset, dy / dist * max_offset) if dist > 1 else (0.0, 0.0)
            px, py = cx + ox, cy + oy
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(QtGui.QColor(20, 20, 24))
            painter.drawEllipse(QtCore.QPointF(px, py), pupil_r, pupil_r)
            painter.setBrush(QtGui.QColor(255, 255, 255, 220))
            painter.drawEllipse(QtCore.QPointF(px - pupil_r * 0.3, py - pupil_r * 0.3),
                                pupil_r * 0.3, pupil_r * 0.3)

            if blink > 0.0:
                lid_r = radius + 4.0                       # also hide the socket outline
                lid_bottom = (cy - lid_r) + blink * 2.0 * lid_r
                painter.save()
                painter.setClipRect(QtCore.QRectF(cx - lid_r - 1, cy - lid_r - 1,
                                                  2 * lid_r + 2, lid_bottom - (cy - lid_r) + 1))
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(self.fur_color)
                painter.drawEllipse(QtCore.QPointF(cx, cy), lid_r, lid_r)
                painter.restore()
                # eyelid crease — rides the lid edge, settling to a full-width
                # closed-eye line across the socket centre when fully shut.
                crease_y = min(lid_bottom, cy)
                gap = abs(crease_y - cy)
                lid_bottom = crease_y
                half = sqrt(max(0.0, lid_r * lid_r - gap * gap))
                pen = QtGui.QPen(QtGui.QColor(40, 30, 25), 1.4)
                pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(QtCore.QPointF(cx - half, lid_bottom), QtCore.QPointF(cx + half, lid_bottom))
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.squint_start = self.clock.elapsed() / 1000.0   # scrunch shut on click
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_offset = None

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu(self)
        menu.addAction("Quit", QtWidgets.QApplication.quit)
        menu.exec(event.globalPos())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=str(DEFAULT_IMAGE))
    args = parser.parse_args()
    if not Path(args.image).exists():
        sys.exit(f"image not found: {args.image}")
    app = QtWidgets.QApplication(sys.argv)
    cat = EyeCat(Path(args.image))
    cat.show()
    print(f"[eye-cat] {len(cat.eyes)} eyes detected; following the cursor. Right-click → Quit.",
          flush=True)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
