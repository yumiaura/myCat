"""Speech-bubble mode: driven by the Reminder entry in Show in menu.

There is no separate toggle — hiding **Reminder** in Settings → *Show in menu*
switches every message from a flyby plane to a speech bubble above the cat.
"""

from PySide6 import QtWidgets

from mycat import menu_config, speech_bubble


def test_plane_by_default(tmp_path):
    # Reminder is shown by default -> messages fly a plane, not a bubble.
    assert speech_bubble.bubble_mode_enabled(tmp_path / "config.ini") is False


def test_hiding_reminder_switches_to_bubble(tmp_path):
    cfg = tmp_path / "config.ini"
    menu_config.save_menu_visibility({"reminder": False}, cfg)  # hide Reminder
    assert speech_bubble.bubble_mode_enabled(cfg) is True  # -> bubble, no plane
    menu_config.save_menu_visibility({"reminder": True}, cfg)  # show it again
    assert speech_bubble.bubble_mode_enabled(cfg) is False  # -> plane


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
