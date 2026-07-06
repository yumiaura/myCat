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

from PyInstaller.utils.hooks import collect_submodules

# Make the in-tree `mycat` package importable while the spec is evaluated, so
# collect_submodules() below can enumerate it even when the package is not
# pip-installed in the build environment.
sys.path.insert(0, str(Path.cwd()))

datas = []

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

# Optional AI-generated plane sprite + canopy manifest used by the reminder
# flyby. Gitignored, so the CI build normally ships without them — the
# reminder feature degrades to a flag-only flyby. Local builds will include
# whatever the developer has in mycat/assets/.
assets_dir = Path("mycat") / "assets"
if assets_dir.is_dir():
    for name in ("plane.png", "plane.json"):
        p = assets_dir / name
        if p.is_file():
            datas.append((str(p), "mycat/assets"))


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
