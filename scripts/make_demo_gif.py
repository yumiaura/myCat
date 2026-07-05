#!/usr/bin/env python3
"""Render a looping demo GIF of the cat: eyes aimed right between them, then a blink.

Built straight from the packaged ``cat`` char (``mycat/chars/cat.zip``) so the
demo matches what the app actually draws:

- ``static.png`` is the body with empty eye sockets; the pupils
  (``eye_left.png`` / ``eye_right.png``) are pasted onto the socket coordinates
  from ``config.json``, each shifted inward by the full ``travel_radius`` — the
  exact gaze the char engine draws when the cursor sits at the midpoint between
  the eyes (see ``pupil_offsets`` in main.py: cursor between the sockets mirrors
  the pupils so the gaze converges).
- ``blink.png`` is the same body with the eyes closed.

Two frames, looped forever: gaze for 4 s, blink for 0.5 s. Writes
``docs/cat.gif`` — a 200x200, 1-bit-transparent GIF (same format as
``docs/classic.gif``).
"""

import io
import json
import zipfile
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
CAT_ZIP = REPO / "mycat" / "chars" / "cat.zip"
OUTPUT = REPO / "docs" / "cat.gif"

CANVAS = 200          # final GIF is CANVAS x CANVAS, like docs/cat.gif
GAZE_MS = 4000        # eyes aimed between them
BLINK_MS = 500        # eyes closed
ALPHA_CUTOFF = 128    # GIF transparency is 1-bit; threshold the soft alpha edge


def load_pack(zip_path):
    with zipfile.ZipFile(zip_path) as archive:
        config = json.loads(archive.read("config.json"))
        images = {}
        for name in ("static.png", "blink.png", "eye_left.png", "eye_right.png"):
            images[name] = Image.open(io.BytesIO(archive.read(name))).convert("RGBA")
    return config, images


def gaze_between_eyes_frame(config, images):
    """Static body with both pupils converged on the point midway between the eyes.

    That is exactly what the char engine draws when the cursor sits at that
    midpoint: for a cursor horizontally between the sockets it mirrors the two
    pupils, and since ``aim`` always uses the full ``travel_radius`` magnitude,
    each pupil shifts inward (toward the nose) by the whole radius — a gentle
    cross-eyed gaze. Sockets sit at equal height, so the shift is purely
    horizontal: left pupil +travel, right pupil −travel.
    """
    frame = images["static.png"].copy()
    eyes = config["eyes"]
    travel = eyes["travel_radius"]
    offsets = {"left": (travel, 0), "right": (-travel, 0)}  # both inward, toward centre
    for side, pupil_name in (("left", "eye_left.png"), ("right", "eye_right.png")):
        pupil = images[pupil_name]
        ox, oy = offsets[side]
        cx, cy = eyes[side]["x"] + ox, eyes[side]["y"] + oy
        box = (round(cx - pupil.width / 2.0), round(cy - pupil.height / 2.0))
        frame.alpha_composite(pupil, box)
    return frame


def fit_canvas(frame):
    """Scale into a CANVAS x CANVAS square, aspect preserved, centred."""
    scaled = frame.copy()
    scaled.thumbnail((CANVAS, CANVAS), Image.LANCZOS)
    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.alpha_composite(scaled, ((CANVAS - scaled.width) // 2, (CANVAS - scaled.height) // 2))
    return canvas


def to_transparent_palette(frame):
    """RGBA → palette image with a 1-bit transparent index (like docs/cat.gif)."""
    alpha = frame.getchannel("A")
    palette = frame.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=255)
    transparent = alpha.point(lambda a: 255 if a < ALPHA_CUTOFF else 0)
    palette.paste(255, transparent)  # index 255 = the transparent slot
    palette.info["transparency"] = 255
    return palette


def main():
    config, images = load_pack(CAT_ZIP)
    gaze = to_transparent_palette(fit_canvas(gaze_between_eyes_frame(config, images)))
    blink = to_transparent_palette(fit_canvas(images["blink.png"]))

    if __import__("os").environ.get("PREVIEW"):
        preview = Image.new("RGBA", (CANVAS * 2 + 20, CANVAS), (235, 235, 240, 255))
        preview.alpha_composite(fit_canvas(gaze_between_eyes_frame(config, images)), (0, 0))
        preview.alpha_composite(fit_canvas(images["blink.png"]), (CANVAS + 20, 0))
        preview_path = Path(__import__("os").environ["PREVIEW"])
        preview.convert("RGB").save(preview_path)
        print(f"Wrote preview {preview_path}")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    gaze.save(
        OUTPUT,
        save_all=True,
        append_images=[blink],
        duration=[GAZE_MS, BLINK_MS],
        loop=0,
        transparency=255,
        disposal=2,
        optimize=False,
    )
    print(f"Wrote {OUTPUT.relative_to(REPO)} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
