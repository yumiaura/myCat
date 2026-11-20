# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for mycat — produces a one-file executable on Windows
# (mycat.exe) and a one-file .app bundle on macOS (mycat.app).
#
# Build locally with:   pyinstaller --noconfirm mycat.spec
# Build artifacts:      dist/mycat[.exe|.app]

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

# Resolve project root from PyInstaller's SPECPATH (independent of CWD)
ROOT_DIR = Path(globals().get("SPECPATH", Path.cwd())).resolve()
sys.path.insert(0, str(ROOT_DIR))

# Ship package metadata so importlib.metadata.version("mycat") works in the frozen exe.
# Safe fallback if package is not pip-installed in the build environment.
try:
    datas = copy_metadata("mycat")
except Exception as meta_error:
    print(f"mycat.spec: warning: package metadata not found ({meta_error})")
    datas = []


# --- Defensive Data Collection Helpers ---
def add_file(src: Path, dest_dir: str) -> None:
    """Include a single file defensively if it exists."""
    if src.is_file():
        datas.append((str(src), dest_dir))


def collect_files(src_dir: Path, pattern: str, dest_dir: str) -> None:
    """Include files matching pattern from src_dir defensively if it exists."""
    if src_dir.is_dir():
        for item in sorted(src_dir.glob(pattern)):
            if item.is_file():
                datas.append((str(item), dest_dir))


mycat_dir = ROOT_DIR / "mycat"
assets_dir = mycat_dir / "assets"

# Bundled cat chars (legacy images/ vs modern chars/)
for skin_dirname in ("chars", "images"):
    collect_files(mycat_dir / skin_dirname, "*", f"mycat/{skin_dirname}")

# LLM prompt template (modern PROMPT.j2 vs legacy PROMT.j2)
for prompt_name in ("PROMPT.j2", "PROMT.j2"):
    add_file(mycat_dir / prompt_name, "mycat")

# Assets & subdirectories (planes, fonts)
collect_files(assets_dir, "*", "mycat/assets")
collect_files(assets_dir / "planes", "*.png", "mycat/assets/planes")
collect_files(assets_dir / "fonts", "*", "mycat/assets/fonts")

# UI translation files
collect_files(mycat_dir / "locale", "*.json", "mycat/locale")


# --- Analysis & PYZ ---
a = Analysis(
    [str(mycat_dir / "main.py")],
    pathex=[str(ROOT_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("mycat"),
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)


# --- Platform App Icon ---
app_icon = None
icon_png = assets_dir / "icon.png"
if icon_png.is_file():
    try:
        from PIL import Image

        build_dir = Path(globals().get("workpath", ROOT_DIR / "build"))
        build_dir.mkdir(parents=True, exist_ok=True)

        if sys.platform == "win32":
            target_icon = build_dir / "mycat.ico"
            # Rebuild only if icon doesn't exist or PNG was updated
            if not target_icon.is_file() or target_icon.stat().st_mtime < icon_png.stat().st_mtime:
                Image.open(icon_png).save(
                    str(target_icon),
                    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
                )
            app_icon = str(target_icon)
        elif sys.platform == "darwin":
            target_icon = build_dir / "mycat.icns"
            if not target_icon.is_file() or target_icon.stat().st_mtime < icon_png.stat().st_mtime:
                Image.open(icon_png).convert("RGBA").resize((1024, 1024)).save(str(target_icon))
            app_icon = str(target_icon)
    except Exception as icon_error:  # noqa: BLE001
        print(f"mycat.spec: could not build the app icon ({icon_error})")
        app_icon = None


# --- Shared Executable Options ---
common_exe_kwargs = {
    "debug": False,
    "bootloader_ignore_signals": False,
    "strip": False,
    "upx": False,
    "upx_exclude": [],
    "console": False,  # pure GUI, no console window
    "disable_windowed_traceback": False,
    "target_arch": None,
    "codesign_identity": None,
    "entitlements_file": None,
}


# --- Platform Packaging ---
if sys.platform == "darwin":
    # macOS: onedir -> .app bundle (fast startup, bypasses onefile extraction delay)
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="mycat",
        **common_exe_kwargs,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="mycat",
    )
    app = BUNDLE(
        coll,
        name="mycat.app",
        icon=app_icon,
        bundle_identifier="app.mycat",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": "0.0.0",  # Overwritten by CI at build time
            "NSHumanReadableCopyright": "© yumiaura",
        },
    )
else:
    # Windows / Linux: onefile self-contained executable
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="mycat",
        icon=app_icon if sys.platform == "win32" else None,
        runtime_tmpdir=None,
        **common_exe_kwargs,
    )
