"""Bake a VRM/glb 3D model into a myCat 2D character zip.

Shared by the dev CLI (``tools/bake_vrm.py`` / ``python -m mycat.vrm_bake``) and
the in-app **Import VRM…** action. The pipeline:

  1. Pose the model with :mod:`mycat.vrm_pose` (drop the T-pose arms to a relaxed
     idle).
  2. Render the posed model with QtQuick3D onto a transparent canvas — rendered
     *offscreen* (the window is created but never shown, so nothing flashes) using
     a local event loop, so it runs safely inside the already-running app.
  3. Autocrop to the character and pack ``config.json`` + ``static.png`` into
     ``<id>.zip``, which the app already discovers and loads with no runtime change.

The 3D imports are lazy, so importing this module never pulls QtQuick3D in — the
app can call :func:`vrm_rendering_available` first and degrade gracefully where
QtQuick3D is not bundled (e.g. some prebuilt binaries). MToon materials fall back
to PBR, which reads fine for a still.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

from mycat import char_catalog, vrm_pose

DEFAULT_MAX_WIDTH = 300
DEFAULT_MAX_HEIGHT = 500
DEFAULT_RENDER_WIDTH = 600
DEFAULT_RENDER_HEIGHT = 900

SCENE_QML = """
import QtQuick
import QtQuick3D
import QtQuick3D.AssetUtils

Item {
    id: root
    width: %(width)d
    height: %(height)d
    property bool modelReady: false

    View3D {
        anchors.fill: parent
        renderMode: View3D.Offscreen
        environment: SceneEnvironment {
            clearColor: "transparent"
            backgroundMode: SceneEnvironment.Transparent
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
        }
        PerspectiveCamera {
            id: cam
            position: Qt.vector3d(0, %(cam_y).3f, %(cam_z).3f)
            clipNear: 0.01
            clipFar: 100
            fieldOfView: %(fov)d
        }
        DirectionalLight { eulerRotation.x: -25; eulerRotation.y: -25; brightness: 1.0 }
        DirectionalLight { eulerRotation.x: -10; eulerRotation.y: 155; brightness: 0.5 }
        DirectionalLight { eulerRotation.x: 80; brightness: 0.3 }
        RuntimeLoader {
            source: modelUrl
            onStatusChanged: {
                if (status === RuntimeLoader.Success) {
                    cam.lookAt(Qt.vector3d(0, %(look_y).3f, 0))
                    root.modelReady = true
                }
            }
        }
    }
}
"""


def vrm_rendering_available() -> bool:
    """True if the QtQuick / QtQuick3D modules needed to render a VRM are present."""
    return all(
        importlib.util.find_spec(name) is not None
        for name in ("PySide6.QtQuick", "PySide6.QtQuick3D")
    )


def sanitize_char_id(name: str) -> str:
    """Turn a filename stem into a safe char id (menu name / zip stem)."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-")
    return cleaned or "vrm-char"


def render_glb_to_qimage(
    glb_path: Path,
    width: int = DEFAULT_RENDER_WIDTH,
    height: int = DEFAULT_RENDER_HEIGHT,
    cam_y: float = 0.9,
    cam_z: float = 2.6,
    look_y: float = 0.9,
    fov: int = 40,
    timeout_ms: int = 30000,
):
    """Render a glb to a transparent QImage with QtQuick3D, offscreen (no window shown)."""
    from PySide6 import QtCore, QtGui, QtQuick

    app = QtGui.QGuiApplication.instance()
    if app is None:
        surface = QtGui.QSurfaceFormat()
        surface.setAlphaBufferSize(8)
        surface.setDepthBufferSize(24)
        surface.setSamples(4)
        QtGui.QSurfaceFormat.setDefaultFormat(surface)
        app = QtGui.QGuiApplication(sys.argv[:1])

    qml = SCENE_QML % {
        "width": width, "height": height,
        "cam_y": cam_y, "cam_z": cam_z, "look_y": look_y, "fov": fov,
    }
    handle = tempfile.NamedTemporaryFile("w", suffix=".qml", delete=False)
    handle.write(qml)
    handle.close()
    qml_path = Path(handle.name)

    view = QtQuick.QQuickView()
    view_format = view.format()
    view_format.setAlphaBufferSize(8)
    view.setFormat(view_format)
    view.setColor(QtGui.QColor(0, 0, 0, 0))
    view.setResizeMode(QtQuick.QQuickView.ResizeMode.SizeRootObjectToView)
    view.resize(width, height)
    view.rootContext().setContextProperty("modelUrl", QtCore.QUrl.fromLocalFile(str(glb_path)))
    view.setSource(QtCore.QUrl.fromLocalFile(str(qml_path)))

    try:
        if view.status() == QtQuick.QQuickView.Status.Error:
            raise RuntimeError("; ".join(e.toString() for e in view.errors()))

        root = view.rootObject()
        view.create()  # realise the GL surface without mapping a visible window

        captured = {"image": None}
        loop = QtCore.QEventLoop()

        def grab():
            if root is None or not root.property("modelReady"):
                return
            image = view.grabWindow()
            if not image.isNull():
                captured["image"] = image
                loop.quit()

        poll = QtCore.QTimer(view)
        poll.timeout.connect(grab)
        poll.start(150)
        watchdog = QtCore.QTimer(view)
        watchdog.setSingleShot(True)
        watchdog.timeout.connect(loop.quit)
        watchdog.start(timeout_ms)

        loop.exec()
        poll.stop()           # stop before the view is torn down, so no stray tick
        watchdog.stop()       # fires grab() on an already-deleted root
        if captured["image"] is None:
            raise RuntimeError("model did not render (RuntimeLoader failed or timed out)")
        return captured["image"]
    finally:
        view.close()
        view.deleteLater()
        qml_path.unlink(missing_ok=True)


def qimage_to_pil(image):
    from PIL import Image
    from PySide6 import QtCore

    buffer = QtCore.QBuffer()
    buffer.open(QtCore.QBuffer.OpenModeFlag.ReadWrite)
    image.save(buffer, "PNG")
    return Image.open(io.BytesIO(buffer.data().data())).convert("RGBA")


def autocrop(pil_image, pad: int = 12):
    from PIL import Image

    bbox = pil_image.getbbox()
    if bbox is None:
        raise RuntimeError("rendered image is fully transparent")
    cropped = pil_image.crop(bbox)
    canvas = Image.new("RGBA", (cropped.width + 2 * pad, cropped.height + 2 * pad), (0, 0, 0, 0))
    canvas.paste(cropped, (pad, pad), cropped)
    return canvas


def render_posed_frame(src_bytes: bytes, deltas: dict, framing: dict):
    """Pose ``src_bytes`` with ``deltas``, render it, and return a PIL RGBA image."""
    posed = vrm_pose.pose_glb_bytes(src_bytes, deltas)
    glb_handle = tempfile.NamedTemporaryFile(suffix=".glb", delete=False)
    glb_handle.write(posed)
    glb_handle.close()
    glb_path = Path(glb_handle.name)
    try:
        image = render_glb_to_qimage(glb_path, **framing)
    finally:
        glb_path.unlink(missing_ok=True)
    return qimage_to_pil(image)


def render_motion_frames(src_bytes, motion_fn, count, framing, progress, base_done, total_steps):
    """Render ``count`` frames of a motion (a ``frame,total -> deltas`` function)."""
    frames = []
    for index in range(count):
        frames.append(render_posed_frame(src_bytes, motion_fn(index, count), framing))
        if progress is not None and not progress(base_done + index + 1, total_steps):
            raise RuntimeError("cancelled")
    return frames


def rgba_frame_to_indexed(pil_frame):
    """Convert an RGBA frame to a palettised GIF frame with a transparent index."""
    from PIL import Image

    rgba = pil_frame.convert("RGBA")
    alpha = rgba.getchannel("A")
    indexed = rgba.convert("RGB").quantize(colors=255, method=Image.Quantize.FASTOCTREE)
    transparent = alpha.point(lambda value: 255 if value < 128 else 0)
    indexed.paste(255, transparent.convert("1"))
    indexed.info["transparency"] = 255
    return indexed


def frames_to_gif_bytes(pil_frames, duration_ms, max_width, max_height, pad: int = 12) -> bytes:
    """Crop every frame to one shared bbox (no jitter), scale to fit, return GIF bytes."""
    from PIL import Image

    boxes = [box for box in (frame.getbbox() for frame in pil_frames) if box is not None]
    if not boxes:
        raise RuntimeError("animation frames are fully transparent")
    left = min(box[0] for box in boxes)
    top = min(box[1] for box in boxes)
    right = max(box[2] for box in boxes)
    bottom = max(box[3] for box in boxes)

    indexed_frames = []
    for frame in pil_frames:
        cropped = frame.crop((left, top, right, bottom))
        canvas = Image.new("RGBA", (cropped.width + 2 * pad, cropped.height + 2 * pad), (0, 0, 0, 0))
        canvas.paste(cropped, (pad, pad), cropped)
        canvas.thumbnail((max_width, max_height), Image.LANCZOS)
        indexed_frames.append(rgba_frame_to_indexed(canvas))

    buffer = io.BytesIO()
    indexed_frames[0].save(
        buffer, format="GIF", save_all=True, append_images=indexed_frames[1:],
        duration=duration_ms, loop=0, disposal=2, transparency=255, optimize=False,
    )
    return buffer.getvalue()


def bake_vrm(
    src,
    out_dir=None,
    char_id: str | None = None,
    max_width: int = DEFAULT_MAX_WIDTH,
    max_height: int = DEFAULT_MAX_HEIGHT,
    render_width: int = DEFAULT_RENDER_WIDTH,
    render_height: int = DEFAULT_RENDER_HEIGHT,
    cam_y: float = 0.9,
    cam_z: float = 2.6,
    look_y: float = 0.9,
    fov: int = 40,
    animate: bool = True,
    idle_frames: int = 10,
    wave_frames: int = 10,
    idle_duration_ms: int = 150,
    wave_duration_ms: int = 70,
    progress=None,
) -> Path:
    """Bake the VRM/glb at ``src`` into a ``<id>.zip`` char and return its path.

    With ``animate`` (default) the pack also gets a looping ``idle0.gif`` (breathing
    / sway, played periodically) and a ``click0.gif`` wave (played on click). The
    optional ``progress(done, total)`` callback is invoked after every rendered
    frame and may return ``False`` to cancel.
    """
    src = Path(src)
    char_id = sanitize_char_id(char_id or src.stem)
    out_dir = Path(out_dir) if out_dir is not None else char_catalog.ensure_user_chars_dir()
    src_bytes = src.read_bytes()
    framing = {
        "width": render_width, "height": render_height,
        "cam_y": cam_y, "cam_z": cam_z, "look_y": look_y, "fov": fov,
    }

    config = {"name": char_id, "max_width": max_width, "max_height": max_height}
    archive_files = {}

    if not animate:
        static = autocrop(render_posed_frame(src_bytes, vrm_pose.RELAXED_A_POSE, framing))
    else:
        total_steps = idle_frames + wave_frames
        idle_pils = render_motion_frames(
            src_bytes, vrm_pose.idle_motion, idle_frames, framing, progress, 0, total_steps)
        wave_pils = render_motion_frames(
            src_bytes, vrm_pose.wave_motion, wave_frames, framing, progress, idle_frames, total_steps)
        # frame 0 of the idle loop is the clean rest pose — reuse it as the still
        # (full PNG alpha, no GIF quantisation).
        static = autocrop(idle_pils[0])
        archive_files["idle0.gif"] = frames_to_gif_bytes(idle_pils, idle_duration_ms, max_width, max_height)
        archive_files["click0.gif"] = frames_to_gif_bytes(wave_pils, wave_duration_ms, max_width, max_height)
        config["idle"] = {"random_every": [6.0, 14.0]}

    static_bytes = io.BytesIO()
    static.save(static_bytes, "PNG")
    archive_files["static.png"] = static_bytes.getvalue()
    archive_files["config.json"] = json.dumps(config, indent=2).encode("utf-8")

    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{char_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in archive_files.items():
            archive.writestr(name, data)
    return zip_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Bake a VRM/glb into a myCat char zip.")
    parser.add_argument("src", type=Path, help="path to the .vrm / .glb model")
    parser.add_argument("--out", type=Path, default=None, help="output dir (default: per-user chars dir)")
    parser.add_argument("--id", default=None, help="char id / menu name (default: filename stem)")
    parser.add_argument("--max-width", type=int, default=DEFAULT_MAX_WIDTH)
    parser.add_argument("--max-height", type=int, default=DEFAULT_MAX_HEIGHT)
    parser.add_argument("--render-width", type=int, default=DEFAULT_RENDER_WIDTH)
    parser.add_argument("--render-height", type=int, default=DEFAULT_RENDER_HEIGHT)
    parser.add_argument("--cam-y", type=float, default=0.9)
    parser.add_argument("--cam-z", type=float, default=2.6)
    parser.add_argument("--look-y", type=float, default=0.9)
    parser.add_argument("--fov", type=int, default=40)
    parser.add_argument("--no-animate", action="store_true", help="bake only a still (no idle/wave)")
    parser.add_argument("--idle-frames", type=int, default=10)
    parser.add_argument("--wave-frames", type=int, default=10)
    args = parser.parse_args(argv)

    if not args.src.exists():
        parser.error(f"no such file: {args.src}")

    def report(done, total):
        print(f"  rendering frame {done}/{total}", flush=True)
        return True

    zip_path = bake_vrm(
        args.src, args.out, args.id, args.max_width, args.max_height,
        args.render_width, args.render_height, args.cam_y, args.cam_z, args.look_y, args.fov,
        animate=not args.no_animate, idle_frames=args.idle_frames, wave_frames=args.wave_frames,
        progress=report,
    )
    print(f"baked {zip_path.stem} -> {zip_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
