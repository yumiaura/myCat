"""New interactive skin-pack format (loaded fully in memory, no temp files).

A skin ``<name>.zip`` contains:
  static.png      body, eyes open (empty sockets where the pupils show)
  blink.png       (optional) body, eyes closed / squint
  eye_left.png    (optional) left pupil sprite (drawn over the open socket)
  eye_right.png   (optional) right pupil sprite
  config.json     parameters (below)
  anim/*.gif      (optional) periodic full-body animations

config.json (coordinates are in static.png native pixels):
  {
    "name": "cat",
    "render_height": 200,
    "eyes": { "travel_radius": 34,
              "left":  {"x": 558, "y": 433},
              "right": {"x": 693, "y": 433} },
    "blink": { "enabled": true, "every": [3, 7], "duration": 0.28 },
    "click_squint": 0.5,
    "animations": [ {"file": "anim/stretch.gif", "enabled": true, "every": [20, 40]} ]
  }

Everything is scaled to ``render_height`` on load, so the renderer works in
render-space pixels.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from PySide6 import QtCore, QtGui

CONFIG_NAME = "config.json"


class SkinSource:
    """Read a skin's files whether it is an unpacked folder or a .zip.

    A zip is opened in memory (no temp extraction); a folder is read from disk.
    Both expose the same ``names()`` / ``read()`` / ``has()`` interface.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.is_folder = self.path.is_dir()
        self.zip = None if self.is_folder else zipfile.ZipFile(self.path)

    def names(self) -> set:
        if self.is_folder:
            return {p.relative_to(self.path).as_posix() for p in self.path.rglob("*") if p.is_file()}
        return set(self.zip.namelist())

    def has(self, name: str) -> bool:
        if self.is_folder:
            return (self.path / name).is_file()
        return name in self.zip.namelist()

    def read(self, name: str) -> bytes:
        if self.is_folder:
            return (self.path / name).read_bytes()
        return self.zip.read(name)

    def close(self) -> None:
        if self.zip is not None:
            self.zip.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@dataclass
class EyeConfig:
    travel_radius: float
    left: QtCore.QPointF
    right: QtCore.QPointF


@dataclass
class Anim:
    frames: list             # list[QtGui.QPixmap], scaled to render height
    delays: list             # list[int] ms per frame
    every: tuple             # (min_s, max_s) random gap between plays


@dataclass
class SkinPack:
    name: str
    static: QtGui.QPixmap
    blink: QtGui.QPixmap | None = None
    eye_left: QtGui.QPixmap | None = None
    eye_right: QtGui.QPixmap | None = None
    eyes: EyeConfig | None = None
    blink_enabled: bool = False
    blink_every: tuple = (3.0, 7.0)
    blink_duration: float = 0.28
    click_squint: float = 0.5
    anims: list = field(default_factory=list)


def is_new_pack(path) -> bool:
    """True if the skin (folder or .zip) is the new interactive format."""
    try:
        with SkinSource(path) as source:
            return source.has(CONFIG_NAME)
    except (zipfile.BadZipFile, OSError):
        return False


def pixmap_from_bytes(data: bytes) -> QtGui.QPixmap:
    pixmap = QtGui.QPixmap()
    pixmap.loadFromData(data)
    return pixmap


def gif_frames(data: bytes, scale: float):
    """Decode a GIF (Pillow) into (scaled QPixmap frames, per-frame delays ms)."""
    from PIL import Image

    image = Image.open(io.BytesIO(data))
    frames, delays = [], []
    for index in range(getattr(image, "n_frames", 1)):
        image.seek(index)
        rgba = image.convert("RGBA")
        if scale != 1.0:
            rgba = rgba.resize((max(1, round(rgba.width * scale)), max(1, round(rgba.height * scale))))
        buffer = rgba.tobytes("raw", "RGBA")
        qimage = QtGui.QImage(buffer, rgba.width, rgba.height, QtGui.QImage.Format.Format_RGBA8888)
        frames.append(QtGui.QPixmap.fromImage(qimage.copy()))
        delays.append(int(image.info.get("duration", 100)))
    return frames, delays


def load_pack(path, render_height: int = 200) -> SkinPack:
    """Read a new-format skin (folder or .zip) into a render-height-scaled SkinPack."""
    with SkinSource(path) as archive:
        names = archive.names()
        config = json.loads(archive.read(CONFIG_NAME))

        static_raw = pixmap_from_bytes(archive.read("static.png"))
        native_h = static_raw.height() or render_height
        scale = render_height / native_h

        def load_scaled(name: str):
            if name not in names:
                return None
            return pixmap_from_bytes(archive.read(name)).scaledToHeight(
                render_height, QtCore.Qt.TransformationMode.SmoothTransformation
            )

        def load_sprite(name: str):
            if name not in names:
                return None
            raw = pixmap_from_bytes(archive.read(name))
            return raw.scaled(
                max(1, round(raw.width() * scale)), max(1, round(raw.height() * scale)),
                QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )

        static = static_raw.scaledToHeight(render_height, QtCore.Qt.TransformationMode.SmoothTransformation)
        blink = load_scaled("blink.png")
        eye_left = load_sprite("eye_left.png")
        eye_right = load_sprite("eye_right.png")

        eyes = None
        eye_cfg = config.get("eyes")
        if eye_cfg and "left" in eye_cfg and "right" in eye_cfg:
            eyes = EyeConfig(
                travel_radius=float(eye_cfg.get("travel_radius", 0)) * scale,
                left=QtCore.QPointF(eye_cfg["left"]["x"] * scale, eye_cfg["left"]["y"] * scale),
                right=QtCore.QPointF(eye_cfg["right"]["x"] * scale, eye_cfg["right"]["y"] * scale),
            )

        blink_cfg = config.get("blink", {})
        anims = []
        for entry in config.get("animations", []):
            if not entry.get("enabled", True):
                continue
            name = entry.get("file")
            if not name or name not in names:
                continue
            frames, delays = gif_frames(archive.read(name), scale)
            every = tuple(entry.get("every", [20, 40]))
            anims.append(Anim(frames=frames, delays=delays, every=every))

        return SkinPack(
            name=config.get("name") or Path(str(path)).stem,
            static=static,
            blink=blink,
            eye_left=eye_left,
            eye_right=eye_right,
            eyes=eyes,
            blink_enabled=bool(blink_cfg.get("enabled", blink is not None)),
            blink_every=tuple(blink_cfg.get("every", [3.0, 7.0])),
            blink_duration=float(blink_cfg.get("duration", 0.28)),
            click_squint=float(config.get("click_squint", 0.5)),
            anims=anims,
        )
