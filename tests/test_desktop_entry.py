"""Linux application-menu entry installation."""

import sys
from pathlib import Path

import pytest

from mycat import main


def test_desktop_exec_command_is_quoted():
    cmd = main.desktop_exec_command()
    assert cmd.startswith('"') and cmd.endswith('"')


@pytest.mark.skipif(sys.platform != "linux", reason="menu entry is Linux-only")
def test_install_desktop_entry_creates_files(tmp_path, monkeypatch):
    if Path("/usr/share/applications/mycat.desktop").exists():
        pytest.skip("a system-wide mycat.desktop is installed here")
    monkeypatch.setenv("HOME", str(tmp_path))
    main.install_desktop_entry()
    desktop = tmp_path / ".local" / "share" / "applications" / "mycat.desktop"
    assert desktop.is_file()
    text = desktop.read_text(encoding="utf-8")
    assert "Name=myCat" in text
    # Icon= must be an absolute path that actually points at a copied file.
    icon_line = next(line for line in text.splitlines() if line.startswith("Icon="))
    icon_path = Path(icon_line.split("=", 1)[1])
    assert icon_path.is_absolute() and icon_path.is_file()
