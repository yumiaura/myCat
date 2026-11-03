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
    "animations": [
        {"file": "anim/stretch.gif", "enabled": true, "every": [20, 40]}
    ]
  }

The char is scaled proportionally to fit within max_width × max_height
(default 200×400, shrink-only); the renderer works in those scaled pixels.
"""

from __future__ import annotations

import io
import json
import zipfile
import colorsys

from dataclasses import dataclass, field
from pathlib import Path

from PySide6 import QtCore, QtGui


CONFIG_NAME = "config.json"
DEFAULT_MAX_WIDTH = 200
DEFAULT_MAX_HEIGHT = 400

# ============================================================
# CAT COLOR
# ============================================================

# Light blush rose
BLUSH_COLOR = (240, 196, 203)  # #F0C4CB


def recolor_orange_image(image):
    """
    Change orange/yellow cat pixels to light blush #F0C4CB.

    Black outlines, white eyes, transparent pixels, etc.
    are kept unchanged.
    """

    image = image.convert("RGBA")
    pixels = image.load()

    # Target blush color
    target_h, target_s, target_v = colorsys.rgb_to_hsv(
        BLUSH_COLOR[0] / 255.0,
        BLUSH_COLOR[1] / 255.0,
        BLUSH_COLOR[2] / 255.0,
    )

    for y in range(image.height):
        for x in range(image.width):

            r, g, b, a = pixels[x, y]

            # Keep transparent pixels unchanged
            if a == 0:
                continue

            # Convert current pixel to HSV
            h, s, v = colorsys.rgb_to_hsv(
                r / 255.0,
                g / 255.0,
                b / 255.0,
            )

            # Detect orange/yellow pixels.
            #
            # Hue:
            #   0.03 ≈ orange/yellow
            #   0.12 ≈ yellow/orange
            #
            # Saturation prevents gray/white pixels
            # from being changed.
            if 0.03 <= h <= 0.12 and s > 0.25 and v > 0.20:

                # Keep the original brightness.
                # Only change the hue/saturation toward blush.
                nr, ng, nb = colorsys.hsv_to_rgb(
                    target_h,
                    target_s,
                    v,
                )

                pixels[x, y] = (
                    int(nr * 255),
                    int(ng * 255),
                    int(nb * 255),
                    a,
                )

    return image


def recolor_image_bytes(data: bytes):
    """
    Load PNG/image bytes and recolor orange pixels to blush.

    Returns PNG bytes.
    """

    from PIL import Image

    image = Image.open(io.BytesIO(data)).convert("RGBA")

    image = recolor_orange_image(image)

    output = io.BytesIO()
    image.save(output, format="PNG")

    return output.getvalue()


# ============================================================
# CHARACTER SOURCE
# ============================================================


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
            return {
                p.relative_to(self.path).as_posix()
                for p in self.path.rglob("*")
                if p.is_file()
            }

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


# ============================================================
# DATA CLASSES
# ============================================================


@dataclass
class EyeConfig:
    travel_radius: float
    left: QtCore.QPointF
    right: QtCore.QPointF


@dataclass
class Anim:
    frames: list
    delays: list
    every: tuple


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

    # State-machine assets
    sleep: QtGui.QPixmap | None = None
    sleep_in: Anim | None = None
    sleep_out: Anim | None = None
    yawn: Anim | None = None

    idle_anims: list = field(default_factory=list)
    click_anims: list = field(default_factory=list)
    hungry_anims: list = field(default_factory=list)

    # Timings
    yawn_after: float = 60.0
    sleep_after: float = 300.0
    idle_random_every: tuple = (25.0, 60.0)

    hungry_below: float = 20.0
    hungry_every: tuple = (30.0, 60.0)


# ============================================================
# CHARACTER DETECTION
# ============================================================


def is_new_pack(path) -> bool:
    """True if the char (folder or .zip) is the new interactive format."""

    try:
        with CharSource(path) as source:
            return source.has(CONFIG_NAME)

    except (zipfile.BadZipFile, OSError):
        return False


# ============================================================
# IMAGE FUNCTIONS
# ============================================================


def pixmap_from_bytes(data: bytes) -> QtGui.QPixmap:
    pixmap = QtGui.QPixmap()
    pixmap.loadFromData(data)
    return pixmap


def gif_frames(data: bytes, scale: float):
    """
    Decode a GIF into scaled QPixmap frames.

    IMPORTANT:
    Every GIF frame is recolored from orange to
    light blush #F0C4CB before being displayed.
    """

    from PIL import Image

    image = Image.open(io.BytesIO(data))

    frames = []
    delays = []

    frame_count = getattr(image, "n_frames", 1)

    for index in range(frame_count):

        image.seek(index)

        # Convert frame to RGBA
        rgba = image.convert("RGBA")

        # Recolor orange -> blush
        rgba = recolor_orange_image(rgba)

        # Resize
        if scale != 1.0:
            rgba = rgba.resize(
                (
                    max(1, round(rgba.width * scale)),
                    max(1, round(rgba.height * scale)),
                )
            )

        # Convert PIL image to QImage
        buffer = rgba.tobytes("raw", "RGBA")

        qimage = QtGui.QImage(
            buffer,
            rgba.width,
            rgba.height,
            QtGui.QImage.Format.Format_RGBA8888,
        )

        frames.append(
            QtGui.QPixmap.fromImage(qimage.copy())
        )

        delays.append(
            int(image.info.get("duration", 100))
        )

    return frames, delays


# ============================================================
# LOAD CHARACTER PACK
# ============================================================


def load_pack(
    path,
    max_width: int = DEFAULT_MAX_WIDTH,
    max_height: int = DEFAULT_MAX_HEIGHT,
) -> CharPack:
    """
    Read a new-format char (folder or .zip), scaled to fit a max box.

    The char is scaled proportionally to fit within
    max_width × max_height.

    Orange pixels are automatically changed to
    light blush #F0C4CB.
    """

    with CharSource(path) as archive:

        names = archive.names()

        config = json.loads(
            archive.read(CONFIG_NAME)
        )

        max_w = int(
            config.get("max_width") or max_width
        )

        max_h = int(
            config.get("max_height") or max_height
        )

        # ----------------------------------------------------
        # STATIC IMAGE
        # ----------------------------------------------------

        static_data = archive.read("static.png")

        # Recolor orange -> blush
        static_data = recolor_image_bytes(
            static_data
        )

        static_raw = pixmap_from_bytes(
            static_data
        )

        native_w = static_raw.width() or max_w
        native_h = static_raw.height() or max_h

        scale = min(
            max_w / native_w,
            max_h / native_h,
            1.0,
        )

        # ----------------------------------------------------
        # SCALE FUNCTION
        # ----------------------------------------------------

        def by_scale(raw):

            return raw.scaled(
                max(
                    1,
                    round(raw.width() * scale),
                ),
                max(
                    1,
                    round(raw.height() * scale),
                ),
                QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )

        # ----------------------------------------------------
        # LOAD PNG SPRITE
        # ----------------------------------------------------

        def load_sprite(name: str):

            if name not in names:
                return None

            data = archive.read(name)

            # Recolor PNG sprite
            data = recolor_image_bytes(data)

            pixmap = pixmap_from_bytes(data)

            return by_scale(pixmap)

        # ----------------------------------------------------
        # MAIN IMAGES
        # ----------------------------------------------------

        static = by_scale(static_raw)

        blink = load_sprite("blink.png")

        eye_left = load_sprite("eye_left.png")

        eye_right = load_sprite("eye_right.png")

        # ----------------------------------------------------
        # EYES
        # ----------------------------------------------------

        eyes = None

        eye_cfg = config.get("eyes")

        if (
            eye_cfg
            and "left" in eye_cfg
            and "right" in eye_cfg
        ):

            eyes = EyeConfig(
                travel_radius=float(
                    eye_cfg.get(
                        "travel_radius",
                        0,
                    )
                ) * scale,

                left=QtCore.QPointF(
                    eye_cfg["left"]["x"] * scale,
                    eye_cfg["left"]["y"] * scale,
                ),

                right=QtCore.QPointF(
                    eye_cfg["right"]["x"] * scale,
                    eye_cfg["right"]["y"] * scale,
                ),
            )

        # ----------------------------------------------------
        # GIF BODY FRAMES
        # ----------------------------------------------------

        def gif_body_frames(name: str):

            from PIL import Image

            data = archive.read(name)

            # Find original GIF dimensions
            native_w, native_h = Image.open(
                io.BytesIO(data)
            ).size

            # Match animation height to static image
            gif_scale = static.height() / native_h

            # gif_frames() automatically recolors
            # every animation frame.
            return gif_frames(
                data,
                gif_scale,
            )

        # ----------------------------------------------------
        # NORMAL ANIMATIONS
        # ----------------------------------------------------

        blink_cfg = config.get(
            "blink",
            {},
        )

        anims = []

        for entry in config.get(
            "animations",
            [],
        ):

            if not entry.get(
                "enabled",
                True,
            ):
                continue

            name = entry.get("file")

            if not name or name not in names:
                continue

            frames, delays = gif_body_frames(
                name
            )

            every = tuple(
                entry.get(
                    "every",
                    [20, 40],
                )
            )

            anims.append(
                Anim(
                    frames=frames,
                    delays=delays,
                    every=every,
                )
            )

        # ----------------------------------------------------
        # SINGLE ANIMATION
        # ----------------------------------------------------

        def load_anim(name: str):

            if name not in names:
                return None

            frames, delays = gif_body_frames(
                name
            )

            return Anim(
                frames=frames,
                delays=delays,
                every=(0.0, 0.0),
            )

        # ----------------------------------------------------
        # ANIMATION POOL
        # ----------------------------------------------------

        def load_pool(prefix: str):

            pool = []

            for name in sorted(names):

                base = name.rsplit(
                    "/",
                    1,
                )[-1]

                if (
                    base.startswith(prefix)
                    and base.endswith(".gif")
                ):

                    frames, delays = gif_body_frames(
                        name
                    )

                    pool.append(
                        Anim(
                            frames=frames,
                            delays=delays,
                            every=(0.0, 0.0),
                        )
                    )

            return pool

        # ----------------------------------------------------
        # CONFIG
        # ----------------------------------------------------

        idle_cfg = config.get(
            "idle",
            {},
        )

        battery_cfg = config.get(
            "battery",
            {},
        )

        # ----------------------------------------------------
        # RETURN CHARACTER
        # ----------------------------------------------------

        return CharPack(
            name=config.get(
                "name"
            ) or Path(
                str(path)
            ).stem,

            static=static,

            blink=blink,

            eye_left=eye_left,

            eye_right=eye_right,

            eyes=eyes,

            blink_enabled=bool(
                blink_cfg.get(
                    "enabled",
                    blink is not None,
                )
            ),

            blink_every=tuple(
                blink_cfg.get(
                    "every",
                    [3.0, 7.0],
                )
            ),

            blink_duration=float(
                blink_cfg.get(
                    "duration",
                    0.28,
                )
            ),

            click_squint=float(
                config.get(
                    "click_squint",
                    0.5,
                )
            ),

            anims=anims,

            sleep=load_sprite(
                "sleep.png"
            ),

            sleep_in=load_anim(
                "sleep_in.gif"
            ),

            sleep_out=load_anim(
                "sleep_out.gif"
            ),

            yawn=load_anim(
                "yawn.gif"
            ),

            idle_anims=load_pool(
                "idle"
            ),

            click_anims=load_pool(
                "click"
            ),

            hungry_anims=load_pool(
                "hungry"
            ),

            yawn_after=float(
                idle_cfg.get(
                    "yawn_after",
                    60.0,
                )
            ),

            sleep_after=float(
                idle_cfg.get(
                    "sleep_after",
                    300.0,
                )
            ),

            idle_random_every=tuple(
                idle_cfg.get(
                    "random_every",
                    [25.0, 60.0],
                )
            ),

            hungry_below=float(
                battery_cfg.get(
                    "hungry_below",
                    20.0,
                )
            ),

            hungry_every=tuple(
                battery_cfg.get(
                    "every",
                    [30.0, 60.0],
                )
            ),
        )