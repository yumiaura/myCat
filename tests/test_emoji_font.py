"""The bundled emoji fallback font ships and is a usable font."""

from pathlib import Path

from PySide6 import QtGui

import mycat

FONT = Path(mycat.__file__).resolve().parent / "assets" / "fonts" / "NotoEmoji-Regular.ttf"


def test_emoji_font_is_bundled():
    assert FONT.is_file()
    # A real TTF, not an HTML error page from a bad download.
    assert FONT.stat().st_size > 100_000


def test_emoji_font_registers_with_qt(qapp):
    font_id = QtGui.QFontDatabase.addApplicationFont(str(FONT))
    assert font_id != -1
    assert QtGui.QFontDatabase.applicationFontFamilies(font_id)
