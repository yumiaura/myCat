"""Cross-platform "start mycat on login" toggle.

Linux uses an XDG autostart .desktop file; Windows uses the HKCU Run key.
Everything degrades to a no-op / unsupported elsewhere.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import updater

logger = logging.getLogger(__name__)

APP_ID = "mycat"          # technical id: .desktop filename, Windows Run key value name
APP_NAME = "myCat"        # display name shown to the user (Name= in the .desktop)
WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def start_command() -> str:
    """The quoted command that starts this install from any working directory.

    A frozen build is its own binary (an AppImage names its .AppImage file,
    because sys.executable points inside a mount that changes on every run);
    otherwise the installed console script; otherwise main.py by absolute
    path, whose import shim lets it run as a script from anywhere.
    """
    if getattr(sys, "frozen", False):
        target = os.environ.get("APPIMAGE") or sys.executable
        return f'"{target}"'
    console = shutil.which("mycat")
    if console:
        return f'"{console}"'
    main_script = Path(__file__).resolve().parent / "main.py"
    return f'"{sys.executable}" "{main_script}"'


def launch_command() -> str:
    """Command that starts mycat at login: start_command(), or the snap's name.

    The path is always quoted: the .desktop Exec line is word-split on
    spaces, so an unquoted script path with a space in it (e.g. a home
    directory like ``/home/anna maria``) breaks the autostart entry. The
    same string goes into the Windows Run key, where unquoted paths with
    spaces are ambiguous.

    Inside a snap the path under $SNAP changes with every revision, so the
    entry names the snap's command instead; snapd starts the app from the
    ``autostart:`` key in snapcraft.yaml, which matches this file by name.
    Every snap sets SNAP_NAME and passes it on (a terminal in the VS Code snap
    has SNAP_NAME=code), so only mycat's own counts.
    """
    if os.environ.get("SNAP_NAME") == "mycat":
        return "mycat"
    return start_command()


# -- Linux (XDG autostart) --------------------------------------------------

def linux_desktop_path() -> Path:
    return Path.home() / ".config" / "autostart" / f"{APP_ID}.desktop"


def linux_is_enabled() -> bool:
    return linux_desktop_path().exists()


def flatpak_request_background(enabled: bool) -> None:
    """Ask the Background portal to start mycat at login, or to stop doing so.

    Inside a Flatpak, ~/.config/autostart is the sandbox's own copy, which no
    session reads; the portal writes the real entry on the host and runs the app
    through `flatpak run`. `gdbus` sends the call with exact D-Bus types (an
    ``as`` command line, ``b`` autostart), which a QVariant map cannot promise.
    The answer arrives later as a signal nobody here needs: the entry in the
    sandbox (linux_set) stays the record of what was asked.
    """
    options = (
        "{'reason': <'Keep mycat on screen every time you log in'>, "
        f"'autostart': <{'true' if enabled else 'false'}>, "
        "'commandline': <['mycat']>}"
    )
    subprocess.run(
        [
            "gdbus", "call", "--session",
            "--dest", "org.freedesktop.portal.Desktop",
            "--object-path", "/org/freedesktop/portal/desktop",
            "--method", "org.freedesktop.portal.Background.RequestBackground",
            "", options,
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )


def linux_set(enabled: bool) -> None:
    if updater.install_kind() == "flatpak":
        flatpak_request_background(enabled)
    path = linux_desktop_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={APP_NAME}\n"
            f"Exec={launch_command()}\n"
            "Terminal=false\n"
            "X-GNOME-Autostart-enabled=true\n",
            encoding="utf-8",
        )
    elif path.exists():
        path.unlink()


def linux_refresh(command: str) -> bool:
    """Point Exec= of the [Desktop Entry] group at ``command``, nothing else.

    Every other line, a user's Hidden=true or X-GNOME-Autostart-enabled=false
    included, is kept byte for byte, line endings too.
    """
    path = linux_desktop_path()
    with open(path, encoding="utf-8", newline="") as handle:
        lines = handle.read().splitlines(keepends=True)
    in_entry = False
    changed = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("["):
            in_entry = stripped == "[Desktop Entry]"
            continue
        if not in_entry or "=" not in stripped or stripped.startswith("#"):
            continue
        key, sep, value = stripped.partition("=")
        if key.strip() != "Exec" or value.strip() == command:
            continue
        ending = line[len(line.rstrip("\r\n")):]
        lines[index] = f"Exec={command}{ending}"
        changed = True
    if changed:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write("".join(lines))
    return changed


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


def windows_refresh(command: str) -> bool:
    """Rewrite the Run value's data in place when it is not ``command``."""
    import winreg

    access = winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY, 0, access) as key:
        try:
            stored, kind = winreg.QueryValueEx(key, APP_ID)
        except FileNotFoundError:
            return False
        if stored == command:
            return False
        winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, command)
        return True


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


def refresh_entry() -> bool:
    """Heal an enabled entry whose command no longer starts this install.

    Entries written by older versions may hold a command that cannot start
    the cat (``-m mycat`` given to a frozen binary, a path inside an
    AppImage's temporary mount). Only the stored command is rewritten; an
    entry that is off stays off. Flatpak and snap entries are left alone:
    the portal and snapd start the app, not the stored command. Only frozen
    builds heal, since only their command was broken: a run from a checkout,
    pip or ./run.sh must not take over the entry of the installed cat.
    Returns True when something was rewritten.
    """
    try:
        if not getattr(sys, "frozen", False):
            return False
        if not is_supported() or not is_enabled():
            return False
        if updater.install_kind() in ("flatpak", "snap"):
            return False
        command = launch_command()
        if sys.platform.startswith("win"):
            changed = windows_refresh(command)
        else:
            changed = linux_refresh(command)
        if changed:
            logger.info("Autostart entry now runs %s", command)
        return changed
    except Exception as exc:  # noqa: BLE001 - never let autostart crash the app
        logger.warning("autostart refresh_entry failed: %s", exc)
        return False


__all__ = [
    "is_supported",
    "is_enabled",
    "set_enabled",
    "launch_command",
    "start_command",
    "refresh_entry",
]
