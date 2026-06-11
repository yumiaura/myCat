"""Cross-platform "start mycat on login" toggle.

Linux uses an XDG autostart .desktop file; Windows uses the HKCU Run key.
Everything degrades to a no-op / unsupported elsewhere.
"""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

APP_ID = "mycat"
WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command() -> str:
    """Command that starts mycat — the installed console script, else python -m."""
    exe = shutil.which("mycat")
    if exe:
        return exe
    return f'"{sys.executable}" -m mycat'


# -- Linux (XDG autostart) --------------------------------------------------

def linux_desktop_path() -> Path:
    return Path.home() / ".config" / "autostart" / f"{APP_ID}.desktop"


def linux_is_enabled() -> bool:
    return linux_desktop_path().exists()


def linux_set(enabled: bool) -> None:
    path = linux_desktop_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={APP_ID}\n"
            f"Exec={launch_command()}\n"
            "Terminal=false\n"
            "X-GNOME-Autostart-enabled=true\n"
        )
    elif path.exists():
        path.unlink()


# -- Windows (HKCU Run key) -------------------------------------------------

def windows_is_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_ID)
            return True
    except OSError:
        return False


def windows_set(enabled: bool) -> None:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, APP_ID)
            except OSError:
                pass


# -- public API -------------------------------------------------------------

def is_supported() -> bool:
    return sys.platform.startswith("linux") or sys.platform.startswith("win")


def is_enabled() -> bool:
    try:
        if sys.platform.startswith("win"):
            return windows_is_enabled()
        if sys.platform.startswith("linux"):
            return linux_is_enabled()
    except Exception as exc:  # noqa: BLE001 - never let autostart crash the app
        logger.warning("autostart is_enabled failed: %s", exc)
    return False


def set_enabled(enabled: bool) -> None:
    try:
        if sys.platform.startswith("win"):
            windows_set(enabled)
        elif sys.platform.startswith("linux"):
            linux_set(enabled)
        logger.info("Autostart %s", "enabled" if enabled else "disabled")
    except Exception as exc:  # noqa: BLE001
        logger.warning("autostart set_enabled failed: %s", exc)


__all__ = ["is_supported", "is_enabled", "set_enabled", "launch_command"]
