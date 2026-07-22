"""State-machine engine tests: yawn / sleep / wake / click, driven by injected time."""

import io
import json
import zipfile

from PIL import Image

import mycat.main as m
from mycat import char_pack


def build_pack(tmp_path):
    def png():
        buffer = io.BytesIO()
        Image.new("RGBA", (20, 20), (200, 150, 90, 255)).save(buffer, "PNG")
        return buffer.getvalue()

    def gif():
        buffer = io.BytesIO()
        Image.new("RGBA", (20, 20), (120, 120, 120, 255)).save(buffer, "GIF")
        return buffer.getvalue()

    config = {
        "name": "t", "max_width": 200, "max_height": 400,
        "blink": {"enabled": False},
        "idle": {"yawn_after": 1, "sleep_after": 2, "random_every": [1000, 1000]},
    }
    path = tmp_path / "t.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name in ("static.png", "blink.png", "sleep.png"):
            archive.writestr(name, png())
        for name in ("sleep_in.gif", "sleep_out.gif", "yawn.gif", "idle1.gif", "click1.gif"):
            archive.writestr(name, gif())
        archive.writestr("config.json", json.dumps(config))
    return path


def make_window(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(m, "CFG_DIR", tmp_path)
    monkeypatch.setattr(m, "CFG_FILE", tmp_path / "config.ini")
    pack = char_pack.load_pack(build_pack(tmp_path))
    window = m.PixelCatWindow(pack.static, None, 0.0, "t", [], b"", pack=pack)
    window.last_interaction = 0.0
    window.last_cursor_move = 0.0
    window.next_idle = 1e9
    window.next_hungry = 1e9
    return window, pack


def test_pack_loads_all_state_assets(qapp, tmp_path, monkeypatch):
    _, pack = make_window(qapp, tmp_path, monkeypatch)
    assert pack.sleep is not None
    assert pack.sleep_in is not None and pack.sleep_out is not None and pack.yawn is not None
    assert len(pack.idle_anims) == 1 and len(pack.click_anims) == 1
    assert pack.yawn_after == 1 and pack.sleep_after == 2
    assert pack.eyes is None


def test_yawn_then_sleep_then_wake(qapp, tmp_path, monkeypatch):
    w, _ = make_window(qapp, tmp_path, monkeypatch)

    w.test_now = 0.5
    assert w.update_pack_frame() == "open"          # awake

    w.test_now = 1.5                                # cursor still > yawn_after
    assert w.update_pack_frame() == "anim"          # yawn one-shot
    assert w.yawned is True

    w.test_now = 1.8                                # yawn (100ms) finished
    assert w.update_pack_frame() == "open"

    w.test_now = 2.5                                # idle > sleep_after -> sleep_in
    assert w.update_pack_frame() == "anim"
    w.test_now = 2.8                                # sleep_in finished -> sleeping
    assert w.update_pack_frame() == "sleep"
    assert w.base_state == "sleeping"

    w.test_now = 3.0                                # interaction wakes -> sleep_out
    w.wake(w.pack_now())
    assert w.update_pack_frame() == "anim"
    w.test_now = 3.3                                # sleep_out finished -> awake
    assert w.update_pack_frame() == "open"
    assert w.base_state == "awake"


def test_click_plays_reaction(qapp, tmp_path, monkeypatch):
    w, _ = make_window(qapp, tmp_path, monkeypatch)
    w.test_now = 4.0
    w.on_pack_click()
    assert w.update_pack_frame() == "anim"          # click1 one-shot
