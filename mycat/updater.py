#!/usr/bin/env python3
"""In-app self-update for the prebuilt binaries.

Downloads this platform's asset from the latest GitHub release, swaps it in, and
relaunches. Source / pip installs are never modified — they only learn that a
newer version exists (the caller shows a message and a link). Everything is
fetched over HTTPS from the release's stable, version-less download URLs.

The GUI flow (menu action, confirm dialog, progress, relaunch) lives in
``main.py``; this module is pure logic so it stays testable.
"""

from __future__ import annotations

import logging
import os
import platform
import stat
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

RELEASE_DOWNLOAD = "https://github.com/yumiaura/myCat/releases/latest/download"
RELEASES_PAGE = "https://github.com/yumiaura/myCat/releases/latest"


def install_kind() -> str:
    """How this instance was installed.

    One of ``source`` (running from a checkout or pip — nothing to swap),
    ``appimage``, ``deb``, ``macos`` or ``windows``.
    """
    if not getattr(sys, "frozen", False):
        return "source"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    # Frozen Linux: an AppImage exports APPIMAGE with the real .AppImage path;
    # otherwise it's the binary installed from the .deb (in /usr/bin).
    if os.environ.get("APPIMAGE"):
        return "appimage"
    return "deb"


def can_self_update(kind: str) -> bool:
    """True for the frozen kinds we can actually replace + relaunch."""
    return kind in ("appimage", "deb", "macos", "windows")


def source_update_command() -> str:
    """How to update a non-frozen install: ``git pull`` from a git checkout,
    else ``pip install --upgrade mycat``."""
    if (Path(__file__).resolve().parent.parent / ".git").is_dir():
        return "git pull"
    return "pip install --upgrade mycat"


def asset_name(kind: str) -> str:
    """Version-less release asset filename for this platform, or ``""``."""
    if kind == "windows":
        return "mycat-windows-x64.exe"
    if kind == "macos":
        arch = platform.machine().lower()
        return "mycat-macos-arm64.zip" if arch in ("arm64", "aarch64") else "mycat-macos-x64.zip"
    if kind == "appimage":
        return "mycat-linux-x86_64.AppImage"
    if kind == "deb":
        return "mycat-linux-amd64.deb"
    return ""


def asset_url(kind: str) -> str:
    name = asset_name(kind)
    return f"{RELEASE_DOWNLOAD}/{name}" if name else ""


def make_executable(path: str) -> None:
    mode = os.stat(path).st_mode
    os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def download(url: str, dest: str, progress=None) -> None:
    """Stream ``url`` to ``dest``; call ``progress(done, total)`` as it goes.

    ``total`` is 0 when the server doesn't send Content-Length.
    """
    request = urllib.request.Request(url, headers={"User-Agent": "mycat"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - official HTTPS release URL
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as out:
            while True:
                chunk = response.read(1 << 16)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)


def staging_path(kind: str) -> str:
    """Where to download the new build before swapping it in.

    For the AppImage we stage next to the running file so the final swap is an
    atomic same-filesystem rename; everything else stages in the temp dir.
    """
    if kind == "appimage":
        current = os.environ["APPIMAGE"]
        return os.path.join(os.path.dirname(current), ".mycat-update.AppImage")
    return os.path.join(tempfile.gettempdir(), asset_name(kind))


def apply_and_relaunch(kind: str, downloaded: str) -> None:
    """Swap in ``downloaded`` and spawn the new build. The caller must quit the
    app immediately afterwards so the old process exits."""
    if kind == "appimage":
        apply_appimage(downloaded)
    elif kind == "deb":
        apply_deb(downloaded)
    elif kind == "macos":
        apply_macos(downloaded)
    elif kind == "windows":
        apply_windows(downloaded)
    else:
        raise ValueError(f"cannot self-update install kind {kind!r}")


def apply_appimage(downloaded: str) -> None:
    target = os.environ["APPIMAGE"]
    make_executable(downloaded)
    # Same directory as the running file -> atomic replace; the running mount
    # keeps the old inode until this process exits.
    os.replace(downloaded, target)
    subprocess.Popen([target], close_fds=True, start_new_session=True)  # noqa: S603
    logger.info("AppImage updated in place: %s", target)


def apply_deb(downloaded: str) -> None:
    # /usr/bin/mycat is root-owned: install through polkit. apt replaces the
    # file in place; the running process keeps its old inode until it exits.
    subprocess.run(  # noqa: S603
        ["pkexec", "apt-get", "install", "-y", "--only-upgrade", "--allow-downgrades", downloaded],
        check=True,
    )
    subprocess.Popen([sys.executable], close_fds=True, start_new_session=True)  # noqa: S603
    logger.info("deb installed via pkexec; relaunching %s", sys.executable)


def apply_macos(zip_path: str) -> None:
    # sys.executable is .../mycat.app/Contents/MacOS/mycat.
    app = os.path.dirname(os.path.dirname(os.path.dirname(sys.executable)))
    pid = os.getpid()
    script = os.path.join(tempfile.gettempdir(), "mycat-update.sh")
    body = (
        "#!/bin/sh\n"
        f"while kill -0 {pid} 2>/dev/null; do sleep 1; done\n"
        'tmp="$(mktemp -d)"\n'
        f'/usr/bin/ditto -x -k "{zip_path}" "$tmp"\n'
        f'rm -rf "{app}"\n'
        f'/usr/bin/ditto "$tmp/mycat.app" "{app}"\n'
        f'/usr/bin/xattr -dr com.apple.quarantine "{app}" 2>/dev/null\n'
        f'open "{app}"\n'
        f'rm -rf "$tmp" "{zip_path}" "$0"\n'
    )
    with open(script, "w", encoding="utf-8") as handle:
        handle.write(body)
    make_executable(script)
    subprocess.Popen(["/bin/sh", script], start_new_session=True)  # noqa: S603
    logger.info("macOS update helper launched for %s", app)


def apply_windows(downloaded: str) -> None:
    exe = sys.executable
    pid = os.getpid()
    log = os.path.join(tempfile.gettempdir(), "mycat-update.log")
    script = os.path.join(tempfile.gettempdir(), "mycat-update.bat")
    # Wait for this process to exit, then KEEP RETRYING the overwrite: a onefile
    # build stays locked by its bootloader for a moment after the app PID is
    # gone, so a single `move` right away fails and nothing relaunches. Retry for
    # ~15 s, then start the (now updated) exe. Delayed expansion for the counter.
    body = (
        "@echo off\r\n"
        "setlocal enabledelayedexpansion\r\n"
        f'set "LOG={log}"\r\n'
        'echo update swapper started > "%LOG%"\r\n'
        ":wait\r\n"
        f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul\r\n'
        "if not errorlevel 1 ( timeout /t 1 /nobreak >nul & goto wait )\r\n"
        f'echo pid {pid} gone, swapping >> "%LOG%"\r\n'
        "set /a TRIES=0\r\n"
        ":swap\r\n"
        f'move /Y "{downloaded}" "{exe}" >nul 2>>"%LOG%"\r\n'
        "if not errorlevel 1 goto start\r\n"
        "set /a TRIES+=1\r\n"
        "if !TRIES! LSS 15 ( timeout /t 1 /nobreak >nul & goto swap )\r\n"
        'echo move failed after retries >> "%LOG%"\r\n'
        ":start\r\n"
        f'echo starting >> "%LOG%"\r\n'
        f'start "" "{exe}"\r\n'
        'del "%~f0"\r\n'
    )
    with open(script, "w", encoding="utf-8") as handle:
        handle.write(body)
    # DETACHED_PROCESS only — combining it with CREATE_NO_WINDOW can make
    # CreateProcess fail (then the swapper never runs). Detached alone survives
    # this process exiting and shows no console for a plain @echo off batch.
    subprocess.Popen(["cmd", "/c", script], creationflags=0x00000008, close_fds=True)  # noqa: S603
    logger.info("Windows update swapper launched for %s (log: %s)", exe, log)


__all__ = [
    "install_kind",
    "can_self_update",
    "asset_name",
    "asset_url",
    "download",
    "staging_path",
    "apply_and_relaunch",
    "RELEASES_PAGE",
]
