#!/usr/bin/env python3
"""Bake a VRM/glb 3D model into a myCat 2D character zip.

Pipeline (all offline — nothing here runs inside the app):
  1. Pose the VRM with mycat.vrm_pose (drop the T-pose arms into a relaxed idle).
  2. Render the posed model headless with QtQuick3D onto a transparent canvas.
  3. Autocrop to the character and pack it as ``<id>.zip`` (config.json + static.png),
     which the app already discovers and loads with zero runtime changes.

MToon toon-shading is not rendered natively by QtQuick3D — materials fall back to
PBR, which looks acceptable for a still. Run under a display; on a headless box use
``xvfb-run`` (the model needs a real GL context):

    xvfb-run -a python3 tools/bake_vrm.py tools/vrm/N00.vrm

By default the baked zip lands in the per-user chars dir, so it shows up in the
right-click Chars menu immediately.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mycat import char_catalog, vrm_pose  # noqa: E402

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


def render_glb(glb_path: Path, width: int, height: int, cam_y: float, cam_z: float,
               look_y: float, fov: int, timeout_ms: int = 30000):
    """Headless-render a glb to a transparent QImage via QtQuick3D."""
    from PySide6 import QtCore, QtGui, QtQuick

    fmt = QtGui.QSurfaceFormat()
    fmt.setAlphaBufferSize(8)
    fmt.setDepthBufferSize(24)
    fmt.setSamples(4)
    QtGui.QSurfaceFormat.setDefaultFormat(fmt)

    app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication(sys.argv[:1])

    qml = SCENE_QML % {
        "width": width, "height": height,
        "cam_y": cam_y, "cam_z": cam_z, "look_y": look_y, "fov": fov,
    }
    with tempfile.NamedTemporaryFile("w", suffix=".qml", delete=False) as handle:
        handle.write(qml)
        qml_path = Path(handle.name)

    view = QtQuick.QQuickView()
    view.setColor(QtGui.QColor(0, 0, 0, 0))
    view.setResizeMode(QtQuick.QQuickView.ResizeMode.SizeRootObjectToView)
    view.resize(width, height)
    view.rootContext().setContextProperty("modelUrl", QtCore.QUrl.fromLocalFile(str(glb_path)))
    view.setSource(QtCore.QUrl.fromLocalFile(str(qml_path)))
    if view.status() == QtQuick.QQuickView.Status.Error:
        raise RuntimeError("; ".join(e.toString() for e in view.errors()))

    root = view.rootObject()
    view.show()

    captured = {"image": None}

    def grab():
        if not root.property("modelReady"):
            return
        image = view.grabWindow()
        if not image.isNull():
            captured["image"] = image
            app.quit()

    poll = QtCore.QTimer()
    poll.timeout.connect(grab)
    poll.start(150)
    watchdog = QtCore.QTimer()
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(app.quit)
    watchdog.start(timeout_ms)

    app.exec()
    qml_path.unlink(missing_ok=True)
    if captured["image"] is None:
        raise RuntimeError("model never rendered (RuntimeLoader failed or timed out)")
    return captured["image"]


def qimage_to_pil(image):
    from PIL import Image
    from PySide6 import QtCore

    buffer = QtCore.QBuffer()
    buffer.open(QtCore.QBuffer.OpenModeFlag.ReadWrite)
    image.save(buffer, "PNG")
    return Image.open(io.BytesIO(buffer.data().data())).convert("RGBA")


def autocrop(pil_image, pad: int = 12):
    bbox = pil_image.getbbox()
    if bbox is None:
        raise RuntimeError("rendered image is fully transparent")
    cropped = pil_image.crop(bbox)
    from PIL import Image

    canvas = Image.new("RGBA", (cropped.width + 2 * pad, cropped.height + 2 * pad), (0, 0, 0, 0))
    canvas.paste(cropped, (pad, pad), cropped)
    return canvas


def bake(src: Path, out_dir: Path, char_id: str, max_width: int, max_height: int,
         render_w: int, render_h: int, cam_y: float, cam_z: float, look_y: float, fov: int) -> Path:
    posed = vrm_pose.pose_glb_bytes(src.read_bytes(), vrm_pose.RELAXED_A_POSE)
    with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as handle:
        handle.write(posed)
        glb_path = Path(handle.name)
    try:
        image = render_glb(glb_path, render_w, render_h, cam_y, cam_z, look_y, fov)
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Bake a VRM/glb into a myCat char zip.")
    parser.add_argument("src", type=Path, help="path to the .vrm / .glb model")
    parser.add_argument("--out", type=Path, default=None,
                        help="output dir (default: the per-user chars dir)")
    parser.add_argument("--id", default=None, help="char id / menu name (default: filename stem)")
    parser.add_argument("--max-width", type=int, default=300)
    parser.add_argument("--max-height", type=int, default=500)
    parser.add_argument("--render-width", type=int, default=600)
    parser.add_argument("--render-height", type=int, default=900)
    parser.add_argument("--cam-y", type=float, default=0.9)
    parser.add_argument("--cam-z", type=float, default=2.6)
    parser.add_argument("--look-y", type=float, default=0.9)
    parser.add_argument("--fov", type=int, default=40)
    args = parser.parse_args()

    if not args.src.exists():
        parser.error(f"no such file: {args.src}")
    char_id = args.id or args.src.stem
    out_dir = args.out or char_catalog.user_chars_dir()

    zip_path = bake(
        args.src, out_dir, char_id, args.max_width, args.max_height,
        args.render_width, args.render_height, args.cam_y, args.cam_z, args.look_y, args.fov,
    )
    print(f"baked {char_id} -> {zip_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
