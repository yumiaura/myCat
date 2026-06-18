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
import sys
from collections import deque
from math import hypot
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

DEFAULT_IMAGE = Path.home() / "Pictures" / "mycat2.png"
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

        source = Image.open(image_path).convert("RGBA")
        scaled = source.resize(
            (round(source.width * TARGET_HEIGHT / source.height), TARGET_HEIGHT), Image.LANCZOS
        )
        self.pixmap = pil_to_pixmap(scaled)
        self.eyes = detect_eyes(scaled)
        self.setFixedSize(self.pixmap.size())

        self.test_cursor = None       # set in tests to fake the cursor
        self.drag_offset = None
        self.shape_mask = no_compositor()

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)          # ~60 fps

    def cursor_global(self) -> QtCore.QPoint:
        return self.test_cursor if self.test_cursor is not None else QtGui.QCursor.pos()

    def showEvent(self, event):
        super().showEvent(event)
        if self.shape_mask and not self.pixmap.mask().isNull():
            self.setMask(self.pixmap.mask())

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.drawPixmap(0, 0, self.pixmap)
        cursor = self.cursor_global()
        for cx, cy, radius in self.eyes:
            pupil_r = max(2.5, radius * 0.45)
            max_offset = max(0.0, radius - pupil_r - 1.0)
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
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
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
