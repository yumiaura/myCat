"""Tests for the app icon helper used for the taskbar entry."""

from mycat import main


def test_app_icon_not_null(qapp):
    icon = main.make_app_icon()
    assert not icon.isNull()
    assert not icon.pixmap(64, 64).isNull()
