"""Tests for pure reminder logic (no Qt event loop required)."""

from datetime import datetime

from mycat import reminder


def test_normalized_direction():
    assert reminder.Reminder(direction="rtl").normalized_direction() == reminder.DIRECTION_RTL
    assert reminder.Reminder(direction="ltr").normalized_direction() == reminder.DIRECTION_LTR
    assert reminder.Reminder(direction="nonsense").normalized_direction() == reminder.DIRECTION_LTR


def test_next_future_occurrence_advances_past_now():
    now = datetime(2026, 6, 11, 12, 0, 0)
    missed = datetime(2026, 6, 9, 8, 30, 0)
    nxt = reminder.next_future_occurrence(missed, now=now)
    assert nxt == datetime(2026, 6, 12, 8, 30, 0)
    assert nxt > now


def test_next_future_occurrence_keeps_future_value():
    now = datetime(2026, 6, 11, 12, 0, 0)
    later = datetime(2026, 6, 11, 18, 0, 0)
    assert reminder.next_future_occurrence(later, now=now) == later


def test_plane_field_defaults_to_plane1():
    assert reminder.Reminder().plane == "plane1"


def test_plane_roundtrips_through_config(monkeypatch, tmp_path):
    monkeypatch.setattr(reminder, "CFG_DIR", tmp_path)
    monkeypatch.setattr(reminder, "CFG_FILE", tmp_path / "config.ini")
    reminder.save_reminder(reminder.Reminder(text="hi", plane="plane3"))
    loaded = reminder.load_reminder()
    assert loaded is not None
    assert loaded.plane == "plane3"


def test_available_planes_lists_bundled_sprites():
    from mycat import reminder_ui

    planes = reminder_ui.available_planes()
    assert "plane1" in planes
    assert len(planes) >= 4
    assert reminder_ui.plane_sprite_path("plane2").name == "plane2.png"
    # Unknown name falls back to the bundled single sprite.
    assert reminder_ui.plane_sprite_path("nope").name == "plane.png"
