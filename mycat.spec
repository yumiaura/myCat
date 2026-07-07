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
    for name in ("plane.png", "plane.json", "icon.png"):
        p = assets_dir / name
        if p.is_file():
            datas.append((str(p), "mycat/assets"))
    planes_dir = assets_dir / "planes"
    if planes_dir.is_dir():
        for sprite in sorted(planes_dir.glob("*.png")):
            datas.append((str(sprite), "mycat/assets/planes"))


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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='mycat',
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

if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='mycat.app',
        icon=None,
        bundle_identifier='app.mycat',
        info_plist={
            'NSHighResolutionCapable': True,
            'CFBundleShortVersionString': '0.0.0',  # overwritten by CI at build time
            'NSHumanReadableCopyright': '© yumiaura',
        },
    )
