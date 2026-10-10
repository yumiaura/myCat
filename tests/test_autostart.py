"""Tests for the cross-platform autostart toggle (Linux path)."""

import sys
import types
from contextlib import nullcontext
from pathlib import Path

import pytest

from mycat import autostart


def test_launch_command_is_nonempty():
    assert autostart.launch_command()


def test_launch_command_quotes_installed_script_path(monkeypatch):
    exe = "/home/anna maria/.local/bin/mycat"
    monkeypatch.setattr(autostart.shutil, "which", lambda _name: exe)
    assert autostart.launch_command() == f'"{exe}"'


def clear_install_env(monkeypatch):
    for name in ("SNAP", "SNAP_NAME", "APPIMAGE", "FLATPAK_ID"):
        monkeypatch.delenv(name, raising=False)


def test_launch_command_fallback_runs_main_py_by_path(monkeypatch):
    # "python -m mycat" only worked from the source directory; at login the
    # working directory is $HOME, so main.py is named by its absolute path.
    clear_install_env(monkeypatch)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(autostart.shutil, "which", lambda name: None)
    command = autostart.launch_command()
    main_script = Path(autostart.__file__).resolve().parent / "main.py"
    assert command == f'"{sys.executable}" "{main_script}"'
    assert main_script.is_absolute()
    assert main_script.is_file()


def test_frozen_appimage_names_the_appimage_file(monkeypatch):
    # sys.executable points inside the AppImage's mount, which changes every run.
    clear_install_env(monkeypatch)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/tmp/.mount_abc123/usr/bin/mycat")
    monkeypatch.setenv("APPIMAGE", "/home/anna maria/Apps/mycat.AppImage")
    assert autostart.start_command() == '"/home/anna maria/Apps/mycat.AppImage"'
    assert autostart.launch_command() == '"/home/anna maria/Apps/mycat.AppImage"'


def test_frozen_build_starts_its_own_binary_without_dash_m(monkeypatch):
    # The frozen binary does not understand -m, and a pip mycat on PATH is
    # another install, not this one.
    clear_install_env(monkeypatch)
    exe = r"C:\Users\anna maria\Downloads\mycat-windows-x64.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", exe)
    monkeypatch.setattr(autostart.shutil, "which", lambda name: "/usr/local/bin/mycat")
    command = autostart.launch_command()
    assert command == f'"{exe}"'
    assert "-m" not in command


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux XDG autostart")
def test_linux_desktop_exec_survives_space_in_path(monkeypatch, tmp_path):
    import shlex

    monkeypatch.setenv("HOME", str(tmp_path))
    exe = "/home/anna maria/.local/bin/mycat"
    monkeypatch.setattr(autostart.shutil, "which", lambda _name: exe)

    autostart.set_enabled(True)
    text = autostart.linux_desktop_path().read_text()
    exec_value = next(
        line for line in text.splitlines() if line.startswith("Exec=")
    ).removeprefix("Exec=")
    assert shlex.split(exec_value) == [exe]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux XDG autostart")
def test_linux_enable_disable_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    desktop = tmp_path / ".config" / "autostart" / "mycat.desktop"

    assert autostart.is_enabled() is False
    autostart.set_enabled(True)
    assert autostart.is_enabled() is True
    assert desktop.exists()
    assert "Exec=" in desktop.read_text()

    autostart.set_enabled(False)
    assert autostart.is_enabled() is False
    assert not desktop.exists()


def test_launch_command_inside_a_snap_names_the_snap(monkeypatch):
    # The $SNAP path changes with every revision; the snap's command does not.
    monkeypatch.setenv("SNAP_NAME", "mycat")
    assert autostart.launch_command() == "mycat"


def test_flatpak_asks_the_background_portal(monkeypatch, tmp_path):
    # Inside a Flatpak the sandbox's ~/.config/autostart reaches no session; the
    # portal writes the real entry. The sandbox copy stays as the record.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("FLATPAK_ID", "io.github.yumiaura.myCat")
    calls = []
    monkeypatch.setattr(autostart.subprocess, "run", lambda args, **kwargs: calls.append(args))

    autostart.linux_set(True)
    assert "org.freedesktop.portal.Background.RequestBackground" in calls[-1]
    assert "'autostart': <true>" in calls[-1][-1]
    assert "'commandline': <['mycat']>" in calls[-1][-1]
    assert autostart.linux_is_enabled()

    autostart.linux_set(False)
    assert "'autostart': <false>" in calls[-1][-1]
    assert not autostart.linux_is_enabled()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux XDG autostart")
def test_another_apps_flatpak_leaves_the_portal_alone(monkeypatch, tmp_path):
    # A terminal in another Flatpak (VS Code, say) passes its FLATPAK_ID on; the
    # portal would then change that app's login entry, not mycat's.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("FLATPAK_ID", "com.visualstudio.code")
    calls = []
    monkeypatch.setattr(autostart.subprocess, "run", lambda args, **kwargs: calls.append(args))

    autostart.linux_set(True)
    assert autostart.linux_is_enabled()
    autostart.linux_set(False)
    assert not autostart.linux_is_enabled()
    assert calls == []


def write_entry(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def read_entry(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


STALE_ENTRY = (
    "[Desktop Entry]\n"
    "Type=Application\n"
    "Name=myCat\n"
    'Exec="/tmp/.mount_old/usr/bin/mycat" -m mycat\n'
    "Terminal=false\n"
    "Hidden=true\n"
    "X-GNOME-Autostart-enabled=false\n"
    "\n"
    "[Desktop Action new]\n"
    "Exec=something-else\n"
)


def linux_frozen_install(monkeypatch, tmp_path):
    # A frozen .deb build: install_kind() is "deb", the command is its binary.
    monkeypatch.setenv("HOME", str(tmp_path))
    clear_install_env(monkeypatch)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "executable", "/usr/bin/mycat")
    return autostart.linux_desktop_path()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux XDG autostart")
def test_refresh_rewrites_only_exec_and_keeps_a_disabled_entry_disabled(monkeypatch, tmp_path):
    path = linux_frozen_install(monkeypatch, tmp_path)
    write_entry(path, STALE_ENTRY)

    assert autostart.refresh_entry() is True
    expected = STALE_ENTRY.replace(
        'Exec="/tmp/.mount_old/usr/bin/mycat" -m mycat',
        f"Exec={autostart.launch_command()}",
    )
    assert read_entry(path) == expected
    assert "Hidden=true\n" in read_entry(path)
    assert "X-GNOME-Autostart-enabled=false\n" in read_entry(path)
    assert "Exec=something-else\n" in read_entry(path)

    assert autostart.refresh_entry() is False
    assert read_entry(path) == expected


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux XDG autostart")
def test_refresh_keeps_crlf_line_endings(monkeypatch, tmp_path):
    path = linux_frozen_install(monkeypatch, tmp_path)
    write_entry(path, "[Desktop Entry]\r\nExec=old\r\nName=myCat")

    assert autostart.refresh_entry() is True
    assert read_entry(path) == f"[Desktop Entry]\r\nExec={autostart.launch_command()}\r\nName=myCat"
    assert autostart.refresh_entry() is False


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux XDG autostart")
def test_refresh_without_an_entry_creates_nothing(monkeypatch, tmp_path):
    path = linux_frozen_install(monkeypatch, tmp_path)
    assert autostart.refresh_entry() is False
    assert not path.exists()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux XDG autostart")
def test_refresh_leaves_our_flatpak_alone(monkeypatch, tmp_path):
    path = linux_frozen_install(monkeypatch, tmp_path)
    # The Flatpak runs unfrozen, from source.
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setenv("FLATPAK_ID", "io.github.yumiaura.myCat")
    write_entry(path, STALE_ENTRY)

    assert autostart.refresh_entry() is False
    assert read_entry(path) == STALE_ENTRY


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux XDG autostart")
def test_refresh_leaves_a_snap_install_alone(monkeypatch, tmp_path):
    path = linux_frozen_install(monkeypatch, tmp_path)
    monkeypatch.setenv("SNAP", "/snap/mycat/12")
    monkeypatch.setenv("SNAP_NAME", "mycat")
    write_entry(path, STALE_ENTRY)

    assert autostart.refresh_entry() is False
    assert read_entry(path) == STALE_ENTRY


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux XDG autostart")
def test_refresh_leaves_a_source_run_alone(monkeypatch, tmp_path):
    # A checkout, pip or ./run.sh must not take over the installed cat's entry.
    path = linux_frozen_install(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(autostart.shutil, "which", lambda name: "/home/anna maria/.local/bin/mycat")
    write_entry(path, STALE_ENTRY)

    assert autostart.refresh_entry() is False
    assert read_entry(path) == STALE_ENTRY


def test_another_snaps_name_is_not_the_command(monkeypatch):
    # A terminal in the VS Code snap passes SNAP_NAME=code on.
    clear_install_env(monkeypatch)
    monkeypatch.setenv("SNAP_NAME", "code")
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(autostart.shutil, "which", lambda name: "/home/anna maria/.local/bin/mycat")
    assert autostart.launch_command() == '"/home/anna maria/.local/bin/mycat"'


def fake_winreg(values):
    def query_value(key, name):
        if name not in values:
            raise FileNotFoundError(name)
        return values[name], 1

    def set_value(key, name, reserved, kind, data):
        values[name] = data

    return types.SimpleNamespace(
        HKEY_CURRENT_USER=1,
        KEY_QUERY_VALUE=1,
        KEY_SET_VALUE=2,
        KEY_READ=4,
        REG_SZ=1,
        OpenKey=lambda *args: nullcontext(object()),
        QueryValueEx=query_value,
        SetValueEx=set_value,
        DeleteValue=lambda key, name: values.pop(name),
    )


def test_refresh_rewrites_a_stale_windows_run_value(monkeypatch):
    values = {"mycat": r'"C:\app\mycat.exe" -m mycat'}
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg(values))
    monkeypatch.setattr(sys, "platform", "win32")
    clear_install_env(monkeypatch)
    exe = r"C:\Users\anna maria\Downloads\mycat-windows-x64.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", exe)

    assert autostart.refresh_entry() is True
    assert values["mycat"] == f'"{exe}"'
    assert autostart.refresh_entry() is False


def test_refresh_without_a_windows_run_value_creates_nothing(monkeypatch):
    values = {}
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg(values))
    monkeypatch.setattr(sys, "platform", "win32")
    clear_install_env(monkeypatch)

    assert autostart.refresh_entry() is False
    assert values == {}
