"""Tests for the cross-platform autostart toggle (Linux path)."""

import sys

import pytest

from mycat import autostart


def test_launch_command_is_nonempty():
    assert autostart.launch_command()


def test_launch_command_quotes_installed_script_path(monkeypatch):
    exe = "/home/anna maria/.local/bin/mycat"
    monkeypatch.setattr(autostart.shutil, "which", lambda _name: exe)
    assert autostart.launch_command() == f'"{exe}"'


def test_launch_command_fallback_quotes_python(monkeypatch):
    monkeypatch.setattr(autostart.shutil, "which", lambda _name: None)
    command = autostart.launch_command()
    assert command.startswith(f'"{sys.executable}"')
    assert command.endswith("-m mycat")


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
