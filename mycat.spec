# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for mycat — produces a one-file executable on Windows
# (mycat.exe) and a one-file .app bundle on macOS (mycat.app).
#
# Build locally with:   pyinstaller --noconfirm mycat.spec
# Build artifacts:      dist/mycat[.exe|.app]
#
# Data files are collected DEFENSIVELY: each is included only if it exists
# at spec-evaluation time. That keeps the spec valid across branches —
# main has only the core skins + PROMPT.j2, while feature branches (shop,
# reminder) drop additional resources into the same tree.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

# Make the in-tree `mycat` package importable while the spec is evaluated, so
# collect_submodules() below can enumerate it even when the package is not
# pip-installed in the build environment.
sys.path.insert(0, str(Path.cwd()))

# Ship the package metadata so importlib.metadata.version("mycat") resolves in
# the frozen exe (used for the startup version log + update check).
datas = copy_metadata("mycat")

# Bundled cat chars (cat.zip, classic.zip, ...). The folder was renamed
# images/ -> chars/; support both so older tags keep building and the runtime
# char_catalog (which now looks in mycat/chars) finds them.
for skin_dirname in ("chars", "images"):
    skin_dir = Path("mycat") / skin_dirname
    if skin_dir.is_dir():
        for p in sorted(skin_dir.iterdir()):
            if p.is_file():
                datas.append((str(p), f"mycat/{skin_dirname}"))

# LLM prompt template — handle both the current spelling (PROMPT.j2) and the
# legacy mis-spelling (PROMT.j2) so older tags also build.
for name in ("PROMPT.j2", "PROMT.j2"):
    p = Path("mycat") / name
    if p.is_file():
        datas.append((str(p), "mycat"))

# Plane sprites for the reminder flyby. plane.png is the legacy single sprite;
# planes/plane1..plane4.png are the four selectable variants. All are tracked in
# git and shipped in the pip wheel (see [tool.setuptools.package-data]), so bundle
# them into the frozen build too — otherwise the plane picker is empty in the
# exe/.app and every reminder falls back to the single default plane.
assets_dir = Path("mycat") / "assets"
if assets_dir.is_dir():
    for p in sorted(assets_dir.iterdir()):
        if p.is_file():  # plane.png/.json, icon.png, icon-w/icon-b.png, ...
            datas.append((str(p), "mycat/assets"))
    planes_dir = assets_dir / "planes"
    if planes_dir.is_dir():
        for sprite in sorted(planes_dir.glob("*.png")):
            datas.append((str(sprite), "mycat/assets/planes"))
    # Bundled emoji fallback font (used only where the system has no emoji font).
    fonts_dir = assets_dir / "fonts"
    if fonts_dir.is_dir():
        for font in sorted(fonts_dir.iterdir()):
            if font.is_file():
                datas.append((str(font), "mycat/assets/fonts"))


a = Analysis(
    ['mycat/main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    # Collect the whole `mycat` package explicitly. In the frozen exe the
    # entry runs as `__main__` (empty `__package__`), so main.py imports its
    # submodules dynamically via `importlib.import_module("mycat.llm")` — a
    # string import PyInstaller's static analysis cannot follow. Without this
    # the exe dies at startup with `ModuleNotFoundError: No module named
    # 'mycat.llm'`.
    hiddenimports=collect_submodules('mycat'),
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

# Build the platform app icon from mycat/assets/icon.png so the frozen .exe / .app
# carry a real icon (the PNG stays the single source of truth). Pillow is in the
# build env (a mycat dependency); never fail the build over the icon.
app_icon = None
icon_png = Path("mycat") / "assets" / "icon.png"
if icon_png.is_file():
    try:
        from PIL import Image

        Path("build").mkdir(exist_ok=True)
        if sys.platform == "win32":
            app_icon = str(Path("build") / "mycat.ico")
            Image.open(icon_png).save(
                app_icon,
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
            )
        elif sys.platform == "darwin":
            app_icon = str(Path("build") / "mycat.icns")
            Image.open(icon_png).convert("RGBA").resize((1024, 1024)).save(app_icon)
    except Exception as icon_error:  # noqa: BLE001
        print(f"mycat.spec: could not build the app icon ({icon_error})")
        app_icon = None

if sys.platform == 'darwin':
    # macOS: onedir -> .app. A onefile .app re-extracts its whole ~50 MB archive
    # to a temp dir on EVERY launch (and Gatekeeper rescans the extracted dylibs),
    # which made startup take ~30 s. A onedir bundle keeps the files in Contents/
    # and starts near-instantly.
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='mycat',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name='mycat',
    )
    app = BUNDLE(
        coll,
        name='mycat.app',
        icon=app_icon,
        bundle_identifier='app.mycat',
        info_plist={
            'NSHighResolutionCapable': True,
            'CFBundleShortVersionString': '0.0.0',  # overwritten by CI at build time
            'NSHumanReadableCopyright': '© yumiaura',
        },
    )
else:
    # Windows / Linux: onefile -> a single self-contained executable (the .exe,
    # and the binary the .deb / AppImage wrap).
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='mycat',
        icon=app_icon if sys.platform == 'win32' else None,  # .ico
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,                # no console window — pure GUI
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
