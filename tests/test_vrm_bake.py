"""Unit tests for the non-rendering parts of the VRM baker (no GL / no display)."""

import pytest

from mycat import vrm_bake


def test_sanitize_char_id():
    assert vrm_bake.sanitize_char_id("N00") == "N00"
    assert vrm_bake.sanitize_char_id("my avatar 2") == "my-avatar-2"
    assert vrm_bake.sanitize_char_id("N00.vrm") == "N00-vrm"
    assert vrm_bake.sanitize_char_id("---") == "vrm-char"
    assert vrm_bake.sanitize_char_id("") == "vrm-char"
    assert vrm_bake.sanitize_char_id("ünïcodé!!") == "n-cod"


def test_vrm_rendering_available_returns_bool():
    assert isinstance(vrm_bake.vrm_rendering_available(), bool)


def test_autocrop_trims_transparent_margin():
    from PIL import Image

    canvas = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    canvas.paste(Image.new("RGBA", (10, 20), (255, 0, 0, 255)), (40, 30))
    result = vrm_bake.autocrop(canvas, pad=5)
    # cropped to the 10x20 opaque block, plus 5px padding each side
    assert result.size == (10 + 10, 20 + 10)


def test_autocrop_rejects_fully_transparent():
    from PIL import Image

    with pytest.raises(RuntimeError):
        vrm_bake.autocrop(Image.new("RGBA", (20, 20), (0, 0, 0, 0)))
