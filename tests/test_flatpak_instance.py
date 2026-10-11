"""Single-instance lock and activation socket inside the Flatpak."""

import os
import sys

import pytest

from mycat import main


def test_instance_dir_is_none_outside_a_flatpak(monkeypatch):
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    assert main.flatpak_instance_dir() is None


def test_instance_dir_is_none_inside_another_apps_flatpak(monkeypatch):
    # A terminal in another Flatpak (VS Code, say) passes its own FLATPAK_ID on.
    monkeypatch.setenv("FLATPAK_ID", "com.visualstudio.code")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    assert main.flatpak_instance_dir() is None


def test_instance_dir_is_the_shared_app_dir_inside_the_flatpak(monkeypatch, tmp_path):
    monkeypatch.setenv("FLATPAK_ID", "io.github.yumiaura.myCat")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert main.flatpak_instance_dir() == tmp_path / "app" / "io.github.yumiaura.myCat"


@pytest.mark.skipif(sys.platform == "win32", reason="flock is Unix-only, like the Flatpak")
def test_instance_lock_admits_one_holder_until_it_lets_go(tmp_path):
    directory = tmp_path / "app" / "io.github.yumiaura.myCat"
    first = main.flatpak_instance_lock(directory)
    assert first is not None
    assert main.flatpak_instance_lock(directory) is None
    # Closing the descriptor is what the kernel does when the holder dies,
    # whatever PID it had.
    os.close(first)
    again = main.flatpak_instance_lock(directory)
    assert again is not None
    os.close(again)
