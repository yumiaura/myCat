"""Speech-bubble mode: the persisted setting and the bubble widget's growth."""

from PySide6 import QtWidgets

from mycat import speech_bubble


def test_bubble_mode_default_off(tmp_path):
    assert speech_bubble.bubble_mode_enabled(tmp_path / "config.ini") is False


def test_bubble_mode_roundtrip(tmp_path):
    cfg = tmp_path / "config.ini"
    speech_bubble.set_bubble_mode(True, cfg)
    assert speech_bubble.bubble_mode_enabled(cfg) is True
    speech_bubble.set_bubble_mode(False, cfg)
    assert speech_bubble.bubble_mode_enabled(cfg) is False


def test_set_bubble_mode_keeps_other_settings(tmp_path):
    cfg = tmp_path / "config.ini"
    cfg.write_text("[settings]\nwait_time = 3.0\n")
    speech_bubble.set_bubble_mode(True, cfg)
    assert "wait_time = 3.0" in cfg.read_text()  # [settings] preserved
    assert speech_bubble.bubble_mode_enabled(cfg) is True


def test_bubble_grows_as_it_types(qapp):
    cat = QtWidgets.QWidget()
    cat.resize(200, 300)
    bubble = speech_bubble.BubbleWindow(cat, "Hello there, little cat — nice to see you!")

    bubble.shown_chars = 1
    bubble.relayout()
    small = bubble.width() * bubble.height()

    bubble.shown_chars = len(bubble.full_text)
    bubble.relayout()
    full = bubble.width() * bubble.height()

    assert full > small  # the bubble expands as text is revealed
    assert bubble.revealed_text() == bubble.full_text
