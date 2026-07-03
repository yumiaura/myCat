"""Auto-focus grading: activity runs become 🍅 (≥25 min) or 🍌 (fell short)."""

from datetime import datetime, timedelta

from mycat.activity import focus_count, grade_run, graded_runs, longest_focus_minutes, run_minutes
from mycat.activity_store import ActivityStore

DAY = datetime(2026, 7, 2).date()


def record_run(store, start, minutes):
    for offset in range(minutes):
        store.record_minute(start + timedelta(minutes=offset), 4000, 200, 8, True)


def test_grade_run_thresholds():
    assert grade_run(25) == "focus"
    assert grade_run(100) == "focus"
    assert grade_run(24) == "banana"
    assert grade_run(1) == "banana"  # any finished run under 25 min is a 🍌
    # Custom threshold honoured.
    assert grade_run(30, focus_minutes=45) == "banana"


def test_run_of_25_plus_minutes_is_a_tomato(tmp_path):
    store = ActivityStore(db_path=tmp_path / "a.db")
    record_run(store, datetime(2026, 7, 2, 9, 0), 30)
    runs = graded_runs(store, DAY)
    assert [(r["minutes"], r["grade"]) for r in runs] == [(30, "focus")]
    assert focus_count(store, DAY) == 1
    assert longest_focus_minutes(store, DAY) == 30


def test_short_run_is_a_banana_not_counted(tmp_path):
    store = ActivityStore(db_path=tmp_path / "a.db")
    record_run(store, datetime(2026, 7, 2, 9, 0), 10)
    runs = graded_runs(store, DAY)
    assert runs[0]["grade"] == "banana"
    assert focus_count(store, DAY) == 0
    assert longest_focus_minutes(store, DAY) == 0


def test_short_blip_is_a_banana(tmp_path):
    store = ActivityStore(db_path=tmp_path / "a.db")
    record_run(store, datetime(2026, 7, 2, 9, 0), 3)  # a 3-min run — still a 🍌 now
    assert graded_runs(store, DAY)[0]["grade"] == "banana"


def test_gap_over_five_minutes_splits_the_run(tmp_path):
    store = ActivityStore(db_path=tmp_path / "a.db")
    record_run(store, datetime(2026, 7, 2, 9, 0), 26)  # 🍅
    record_run(store, datetime(2026, 7, 2, 10, 0), 6)  # 🍌 after a 35-min gap
    runs = graded_runs(store, DAY)
    assert [r["grade"] for r in runs] == ["focus", "banana"]
    assert focus_count(store, DAY) == 1


def test_short_gap_keeps_one_run(tmp_path):
    store = ActivityStore(db_path=tmp_path / "a.db")
    record_run(store, datetime(2026, 7, 2, 9, 0), 20)
    # 3-minute gap (≤ 5), then more work — still one continuous run past 25 min.
    record_run(store, datetime(2026, 7, 2, 9, 23), 10)
    runs = graded_runs(store, DAY)
    assert len(runs) == 1
    assert runs[0]["grade"] == "focus"
    assert run_minutes(runs[0]) >= 25
