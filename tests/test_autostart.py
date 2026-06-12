"""Tests for the cross-platform autostart toggle (Linux path)."""

import sys

import pytest

from mycat import autostart


def test_launch_command_is_nonempty():
    assert autostart.launch_command()


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
