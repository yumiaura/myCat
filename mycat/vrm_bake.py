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

        poll = QtCore.QTimer(app)
        poll.timeout.connect(grab)
        poll.start(150)
        watchdog = QtCore.QTimer(app)
        watchdog.setSingleShot(True)
        watchdog.timeout.connect(loop.quit)
        watchdog.start(timeout_ms)

        loop.exec()
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
) -> Path:
    """Bake the VRM/glb at ``src`` into a ``<id>.zip`` char and return its path."""
    src = Path(src)
    char_id = sanitize_char_id(char_id or src.stem)
    out_dir = Path(out_dir) if out_dir is not None else char_catalog.ensure_user_chars_dir()

    posed = vrm_pose.pose_glb_bytes(src.read_bytes(), vrm_pose.RELAXED_A_POSE)
    glb_handle = tempfile.NamedTemporaryFile(suffix=".glb", delete=False)
    glb_handle.write(posed)
    glb_handle.close()
    glb_path = Path(glb_handle.name)
    try:
        image = render_glb_to_qimage(
            glb_path, render_width, render_height, cam_y, cam_z, look_y, fov,
        )
    finally:
        glb_path.unlink(missing_ok=True)

    static = autocrop(qimage_to_pil(image))
    static_bytes = io.BytesIO()
    static.save(static_bytes, "PNG")

    config = {"name": char_id, "max_width": max_width, "max_height": max_height}
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{char_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("config.json", json.dumps(config, indent=2))
        archive.writestr("static.png", static_bytes.getvalue())
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
    args = parser.parse_args(argv)

    if not args.src.exists():
        parser.error(f"no such file: {args.src}")

    zip_path = bake_vrm(
        args.src, args.out, args.id, args.max_width, args.max_height,
        args.render_width, args.render_height, args.cam_y, args.cam_z, args.look_y, args.fov,
    )
    print(f"baked {zip_path.stem} -> {zip_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
