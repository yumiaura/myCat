"""Cat-window behaviour: dragging the frameless window and pupil gaze."""

import io
import json
import math
import zipfile

from PIL import Image
from PySide6 import QtCore, QtGui

import mycat.main as m
from mycat import char_pack


def png():
    buffer = io.BytesIO()
    Image.new("RGBA", (20, 20), (200, 150, 90, 255)).save(buffer, "PNG")
    return buffer.getvalue()


def gif():
    buffer = io.BytesIO()
    Image.new("RGBA", (20, 20), (120, 120, 120, 255)).save(buffer, "GIF")
    return buffer.getvalue()


def build_pack(tmp_path):
    """A char with an eye pair (5,5)/(15,5), travel radius 3 — drives the gaze tests."""
    config = {
        "name": "t", "max_width": 200, "max_height": 400,
        "blink": {"enabled": False},
        "eyes": {"left": {"x": 5, "y": 5}, "right": {"x": 15, "y": 5}, "travel_radius": 3},
    }
    path = tmp_path / "t.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name in ("static.png", "eye_left.png", "eye_right.png"):
            archive.writestr(name, png())
        archive.writestr("click1.gif", gif())
        archive.writestr("config.json", json.dumps(config))
    return char_pack.load_pack(path)


def make_window(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(m, "CFG_DIR", tmp_path)
    monkeypatch.setattr(m, "CFG_FILE", tmp_path / "config.ini")
    pack = build_pack(tmp_path)
    window = m.PixelCatWindow(pack.static, None, 0.0, "t", [], b"", pack=pack)
    window.last_interaction = 0.0
    window.next_idle = 1e9
    window.next_hungry = 1e9
    return window


def mouse(kind, gx, gy, button, buttons):
    return QtGui.QMouseEvent(
        kind, QtCore.QPointF(0, 0), QtCore.QPointF(gx, gy),
        button, buttons, QtCore.Qt.KeyboardModifier.NoModifier,
    )


LEFT = QtCore.Qt.MouseButton.LeftButton
NONE = QtCore.Qt.MouseButton.NoButton


def test_drag_moves_the_window_by_the_cursor_delta(qapp, tmp_path, monkeypatch):
    window = make_window(qapp, tmp_path, monkeypatch)
    window.move(120, 120)
    qapp.processEvents()
    start = window.frameGeometry().topLeft()

    window.mousePressEvent(mouse(QtCore.QEvent.Type.MouseButtonPress, start.x() + 50, start.y() + 50, LEFT, LEFT))
    assert window.dragging is True

    window.mouseMoveEvent(mouse(QtCore.QEvent.Type.MouseMove, start.x() + 70, start.y() + 90, NONE, LEFT))
    qapp.processEvents()
    moved = window.frameGeometry().topLeft()
    assert (moved.x() - start.x(), moved.y() - start.y()) == (20, 40)  # window follows the cursor delta

    window.mouseReleaseEvent(mouse(QtCore.QEvent.Type.MouseButtonRelease, start.x() + 70, start.y() + 90, LEFT, NONE))
    assert window.dragging is False


def test_a_move_without_a_press_does_not_drag(qapp, tmp_path, monkeypatch):
    window = make_window(qapp, tmp_path, monkeypatch)
    window.move(120, 120)
    qapp.processEvents()
    start = window.frameGeometry().topLeft()

    window.mouseMoveEvent(mouse(QtCore.QEvent.Type.MouseMove, start.x() + 70, start.y() + 90, NONE, LEFT))
    qapp.processEvents()
    assert window.frameGeometry().topLeft() == start  # not dragging -> stays put


def test_gaze_falls_back_to_the_nose_when_tracking_is_off(qapp, tmp_path, monkeypatch):
    window = make_window(qapp, tmp_path, monkeypatch)
    window.move(120, 120)
    qapp.processEvents()

    class OffCollector:
        class settings:
            enabled = False

    window.activity_collector = OffCollector()
    # nose = midpoint of the eyes' x, lowest eye y + 2*travel_radius = (10, 11)
    assert window.gaze_target(0, 0) == window.mapToGlobal(QtCore.QPoint(10, 11))


def test_pupils_look_left_in_parallel_when_the_cursor_is_far_left(qapp, tmp_path, monkeypatch):
    window = make_window(qapp, tmp_path, monkeypatch)
    window.move(120, 120)
    qapp.processEvents()

    left_socket = window.mapToGlobal(QtCore.QPoint(5, 5))
    cursor = QtCore.QPoint(left_socket.x() - 500, left_socket.y())  # clearly left of both eyes
    (lox, loy), (rox, roy) = window.pupil_offsets(0, 0, cursor)

    assert (lox, loy) == (rox, roy)                 # cursor outside the pair -> parallel
    assert lox < 0                                  # looking left
    assert abs(loy) < 0.01                          # level with the sockets
    assert abs(math.hypot(lox, loy) - 3) < 0.01     # at the full travel radius
