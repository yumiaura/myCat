"""Speech-bubble mode: the Settings 'Reminder' toggle and the bubble's growth.

The Settings "Reminder" toggle is on by default (messages fly a plane). Turning
it off means every message is spoken in a bubble above the cat instead.
"""

from PySide6 import QtWidgets

from mycat import speech_bubble


def test_flyby_on_by_default(tmp_path):
    cfg = tmp_path / "config.ini"
    assert speech_bubble.reminder_flyby_enabled(cfg) is True  # plane by default
    assert speech_bubble.bubble_mode_enabled(cfg) is False


def test_reminder_off_switches_to_bubble(tmp_path):
    cfg = tmp_path / "config.ini"
    speech_bubble.set_reminder_flyby(False, cfg)  # turn the Reminder toggle off
    assert speech_bubble.reminder_flyby_enabled(cfg) is False
    assert speech_bubble.bubble_mode_enabled(cfg) is True  # -> bubble, no plane
    speech_bubble.set_reminder_flyby(True, cfg)
    assert speech_bubble.bubble_mode_enabled(cfg) is False  # -> plane again


def test_set_reminder_keeps_other_settings(tmp_path):
    cfg = tmp_path / "config.ini"
    cfg.write_text("[settings]\nwait_time = 3.0\n")
    speech_bubble.set_reminder_flyby(False, cfg)
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
