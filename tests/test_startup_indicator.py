"""Tests for the startup indicator helpers (icon + splash card)."""

from mycat import main


def test_app_icon_not_null(qapp):
    assert not main.make_app_icon().isNull()


def test_splash_pixmap_has_expected_size(qapp):
    pixmap = main.make_splash_pixmap()
    assert not pixmap.isNull()
    assert (pixmap.width(), pixmap.height()) == (300, 140)
