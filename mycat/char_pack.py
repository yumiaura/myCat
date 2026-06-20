"""New interactive char-pack format (loaded fully in memory, no temp files).

A char ``<name>.zip`` contains:
  static.png      body, eyes open (empty sockets where the pupils show)
  blink.png       (optional) body, eyes closed / squint
  eye_left.png    (optional) left pupil sprite (drawn over the open socket)
  eye_right.png   (optional) right pupil sprite
  config.json     parameters (below)
  anim/*.gif      (optional) periodic full-body animations

config.json (coordinates are in static.png native pixels):
  {
    "name": "cat",
    "max_width": 200,
    "max_height": 400,
    "eyes": { "travel_radius": 34,
              "left":  {"x": 558, "y": 433},
              "right": {"x": 693, "y": 433} },
    "blink": { "enabled": true, "every": [3, 7], "duration": 0.28 },
    "click_squint": 0.5,
    "animations": [ {"file": "anim/stretch.gif", "enabled": true, "every": [20, 40]} ]
  }

The character is scaled proportionally to fit within max_width × max_height
(default 200×400, shrink-only); the renderer works in those scaled pixels.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from PySide6 import QtCore, QtGui

CONFIG_NAME = "config.json"
DEFAULT_MAX_WIDTH = 200
DEFAULT_MAX_HEIGHT = 400


class CharSource:
    """Read a char's files whether it is an unpacked folder or a .zip.

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
class CharPack:
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
    # state-machine assets (each optional; a state is only active if present)
    sleep: QtGui.QPixmap | None = None          # held sleeping pose
    sleep_in: Anim | None = None                # awake -> sleep transition
    sleep_out: Anim | None = None               # sleep -> awake transition
    yawn: Anim | None = None                    # idle yawn
    idle_anims: list = field(default_factory=list)    # idleN.gif pool
    click_anims: list = field(default_factory=list)   # clickN.gif pool
    hungry_anims: list = field(default_factory=list)  # hungryN.gif pool (low battery)
    # timings
    yawn_after: float = 60.0
    sleep_after: float = 300.0
    idle_random_every: tuple = (25.0, 60.0)
    hungry_below: float = 20.0
    hungry_every: tuple = (30.0, 60.0)


def is_new_pack(path) -> bool:
    """True if the char (folder or .zip) is the new interactive format."""
    try:
        with CharSource(path) as source:
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


def load_pack(path, max_width: int = DEFAULT_MAX_WIDTH, max_height: int = DEFAULT_MAX_HEIGHT) -> CharPack:
    """Read a new-format char (folder or .zip), scaled to fit a max box.

    The character is scaled proportionally to fit within ``max_width`` ×
    ``max_height`` (config ``max_width``/``max_height``, default 200×400); only
    downscaled, never enlarged. Everything (frames, sprites, eye coords) uses the
    same fit-scale.
    """
    with CharSource(path) as archive:
        names = archive.names()
        config = json.loads(archive.read(CONFIG_NAME))
        max_w = int(config.get("max_width") or max_width)
        max_h = int(config.get("max_height") or max_height)

        static_raw = pixmap_from_bytes(archive.read("static.png"))
        native_w = static_raw.width() or max_w
        native_h = static_raw.height() or max_h
        scale = min(max_w / native_w, max_h / native_h, 1.0)   # shrink-to-fit only

        def by_scale(raw):
            return raw.scaled(
                max(1, round(raw.width() * scale)), max(1, round(raw.height() * scale)),
                QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )

        def load_sprite(name: str):
            return by_scale(pixmap_from_bytes(archive.read(name))) if name in names else None

        static = by_scale(static_raw)
        blink = load_sprite("blink.png")
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

        def gif_body_frames(name: str):
            # Scale each body GIF so its on-screen HEIGHT matches the still's,
            # keeping the GIF's own aspect ratio. The GIF is often authored on a
            # different-sized canvas than static.png; sharing the static's scale
            # shrank it (animation smaller than the still), while fitting it to the
            # box independently left a different height (a vertical jump when it
            # played). Matching the still's height keeps the character the same size
            # in both states. (Pupil sprites/eye coords still use the static scale —
            # they live in static's pixel space.)
            from PIL import Image

            data = archive.read(name)
            native_w, native_h = Image.open(io.BytesIO(data)).size
            gif_scale = static.height() / native_h
            return gif_frames(data, gif_scale)

        blink_cfg = config.get("blink", {})
        anims = []
        for entry in config.get("animations", []):
            if not entry.get("enabled", True):
                continue
            name = entry.get("file")
            if not name or name not in names:
                continue
            frames, delays = gif_body_frames(name)
            every = tuple(entry.get("every", [20, 40]))
            anims.append(Anim(frames=frames, delays=delays, every=every))

        def load_anim(name: str):
            if name not in names:
                return None
            frames, delays = gif_body_frames(name)
            return Anim(frames=frames, delays=delays, every=(0.0, 0.0))

        def load_pool(prefix: str):
            pool = []
            for name in sorted(names):
                base = name.rsplit("/", 1)[-1]
                if base.startswith(prefix) and base.endswith(".gif"):
                    frames, delays = gif_body_frames(name)
                    pool.append(Anim(frames=frames, delays=delays, every=(0.0, 0.0)))
            return pool

        idle_cfg = config.get("idle", {})
        battery_cfg = config.get("battery", {})

        return CharPack(
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
            sleep=load_sprite("sleep.png"),
            sleep_in=load_anim("sleep_in.gif"),
            sleep_out=load_anim("sleep_out.gif"),
            yawn=load_anim("yawn.gif"),
            idle_anims=load_pool("idle"),
            click_anims=load_pool("click"),
            hungry_anims=load_pool("hungry"),
            yawn_after=float(idle_cfg.get("yawn_after", 60.0)),
            sleep_after=float(idle_cfg.get("sleep_after", 300.0)),
            idle_random_every=tuple(idle_cfg.get("random_every", [25.0, 60.0])),
            hungry_below=float(battery_cfg.get("hungry_below", 20.0)),
            hungry_every=tuple(battery_cfg.get("every", [30.0, 60.0])),
        )
