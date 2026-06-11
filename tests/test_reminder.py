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
