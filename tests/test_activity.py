"""Activity diary: collector buckets, day classification, totals, retention."""

from datetime import date, datetime, timedelta

from mycat import activity_store
from mycat.activity import (
    ACTIVE_MOUSE_PX_THRESHOLD,
    ActivityCollector,
    ActivitySettings,
    classify_day,
    cursor_km,
    day_summary,
    load_activity_settings,
    save_activity_settings,
)
from mycat.activity_store import ActivityStore


class FakePoint:
    def __init__(self, x, y):
        self.px = x
        self.py = y

    def x(self):
        return self.px

    def y(self):
        return self.py


class FakeNow:
    def __init__(self, start=datetime(2026, 7, 2, 9, 0, 0)):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


def make_collector(tmp_path, cursor_positions=None):
    store = ActivityStore(db_path=tmp_path / "activity.db")
    now = FakeNow()
    positions = iter(cursor_positions or [])

    def cursor_pos():
        try:
            return next(positions)
        except StopIteration:
            return FakePoint(0, 0)

    collector = ActivityCollector(
        store=store,
        settings=ActivitySettings(enabled=True),
        cursor_pos_fn=cursor_pos,
        now_fn=now,
        start_timers=False,
    )
    return collector, store, now


# -- collector -------------------------------------------------------------------


def test_collector_accumulates_cursor_distance(tmp_path):
    positions = [FakePoint(0, 0), FakePoint(30, 40), FakePoint(30, 40)]  # 3-4-5 → 50 px
    collector, store, now = make_collector(tmp_path, positions)
    collector.sample()
    collector.sample()
    collector.sample()
    now.advance(minutes=1)
    collector.sample()  # rollover flushes the previous minute
    rows = store.minutes_between(datetime(2026, 7, 2), datetime(2026, 7, 3))
    assert len(rows) == 1
    assert rows[0]["mouse_px"] == 50
    assert rows[0]["active"] == 1  # 50 px ≥ threshold


def test_collector_small_jitter_is_not_active(tmp_path):
    positions = [FakePoint(0, 0), FakePoint(3, 4)]  # 5 px, under threshold
    collector, store, now = make_collector(tmp_path, positions)
    collector.sample()
    collector.sample()
    now.advance(minutes=1)
    collector.sample()
    rows = store.minutes_between(datetime(2026, 7, 2), datetime(2026, 7, 3))
    assert rows[0]["mouse_px"] < ACTIVE_MOUSE_PX_THRESHOLD
    assert rows[0]["active"] == 0


def test_collector_key_counts_make_minute_active(tmp_path):
    collector, store, now = make_collector(tmp_path, [FakePoint(0, 0)])
    collector.sample()
    collector.bucket_keys += 12  # what the pynput callback does, minus the hook
    now.advance(minutes=1)
    collector.sample()
    rows = store.minutes_between(datetime(2026, 7, 2), datetime(2026, 7, 3))
    assert rows[0]["keys"] == 12
    assert rows[0]["active"] == 1


# -- settings --------------------------------------------------------------------


def test_activity_settings_round_trip(tmp_path):
    cfg = tmp_path / "config.ini"
    # Each track flips independently: activity off, mouse on, keyboard off.
    save_activity_settings(
        ActivitySettings(
            enabled=False, mouse_enabled=True, keyboard_enabled=False, retention_days=30, prompted=True
        ),
        cfg_file=cfg,
    )
    loaded = load_activity_settings(cfg_file=cfg)
    assert loaded.enabled is False  # opt-out round-trips
    assert loaded.mouse_enabled is True
    assert loaded.keyboard_enabled is False
    assert loaded.prompted is True
    assert loaded.retention_days == 30


def test_activity_settings_default_on(tmp_path):
    # The diary is core product behaviour: on by default (opt-out remains).
    loaded = load_activity_settings(cfg_file=tmp_path / "none.ini")
    assert loaded.enabled is True
    assert loaded.mouse_enabled is True
    assert loaded.keyboard_enabled is True


def test_mouse_disabled_skips_cursor_path(tmp_path):
    # With the mouse track off, cursor motion is not accumulated even though the
    # cursor keeps moving — the minute is a "rest" minute.
    positions = [FakePoint(0, 0), FakePoint(30, 40), FakePoint(60, 80)]  # would be 50+50 px
    collector, store, now = make_collector(tmp_path, positions)
    collector.settings.mouse_enabled = False
    collector.sample()
    collector.sample()
    collector.sample()
    now.advance(minutes=1)
    collector.sample()  # rollover flushes the previous minute
    rows = store.minutes_between(datetime(2026, 7, 2), datetime(2026, 7, 3))
    assert rows[0]["mouse_px"] == 0
    assert rows[0]["active"] == 0


def test_apply_settings_reconciles_each_hook_independently(tmp_path):
    collector, store, now = make_collector(tmp_path, [FakePoint(0, 0)])
    calls = []
    collector.start_keyboard_hook = lambda: calls.append("start_kb")
    collector.stop_keyboard_hook = lambda: calls.append("stop_kb")
    collector.start_mouse_hook = lambda: calls.append("start_mouse")
    collector.stop_mouse_hook = lambda: calls.append("stop_mouse")
    # Already enabled with both tracks on; turn the keyboard off, keep mouse on.
    collector.apply_settings(ActivitySettings(enabled=True, mouse_enabled=True, keyboard_enabled=False))
    assert "stop_kb" in calls
    assert "start_mouse" in calls
    assert "start_kb" not in calls


# -- analysis --------------------------------------------------------------------


def fill_minutes(store, start, count, active=True, mouse_px=500, keys=40):
    for offset in range(count):
        px = mouse_px if active else 0
        pressed = keys if active else 0
        store.record_minute(start + timedelta(minutes=offset), px, pressed, 0, active)


def test_classify_focus_present_throughout(tmp_path):
    store = ActivityStore(db_path=tmp_path / "a.db")
    start = datetime(2026, 7, 2, 9, 0)
    store.record_session(activity_store.FOCUS, start, start + timedelta(minutes=25), 1500, True)
    fill_minutes(store, start, 25, active=True)
    intervals = classify_day(store, date(2026, 7, 2))
    assert len(intervals) == 1
    assert intervals[0]["kind"] == "focus"
    assert "throughout" in intervals[0]["label"]
    assert "✓" in intervals[0]["label"]


def test_classify_focus_with_absence(tmp_path):
    store = ActivityStore(db_path=tmp_path / "a.db")
    start = datetime(2026, 7, 2, 9, 0)
    store.record_session(activity_store.FOCUS, start, start + timedelta(minutes=25), 1500, True)
    fill_minutes(store, start, 10, active=True)
    fill_minutes(store, start + timedelta(minutes=10), 15, active=False)
    intervals = classify_day(store, date(2026, 7, 2))
    assert intervals[0]["kind"] == "focus"
    assert "away for ~15 min" in intervals[0]["label"]


def test_classify_break_rested_properly(tmp_path):
    store = ActivityStore(db_path=tmp_path / "a.db")
    start = datetime(2026, 7, 2, 9, 25)
    store.record_session(activity_store.BREAK, start, start + timedelta(minutes=5), 300, True)
    fill_minutes(store, start, 5, active=False)
    intervals = classify_day(store, date(2026, 7, 2))
    assert intervals[0]["kind"] == "break"
    assert "rested properly" in intervals[0]["label"]


def test_classify_break_spent_at_computer(tmp_path):
    store = ActivityStore(db_path=tmp_path / "a.db")
    start = datetime(2026, 7, 2, 9, 25)
    store.record_session(activity_store.BREAK, start, start + timedelta(minutes=5), 300, True)
    fill_minutes(store, start, 5, active=True)
    intervals = classify_day(store, date(2026, 7, 2))
    assert "spent at the computer" in intervals[0]["label"]


def test_classify_work_outside_pomodoro(tmp_path):
    store = ActivityStore(db_path=tmp_path / "a.db")
    start = datetime(2026, 7, 2, 14, 0)
    fill_minutes(store, start, 40, active=True)  # 40 active minutes, no session
    intervals = classify_day(store, date(2026, 7, 2))
    assert len(intervals) == 1
    assert intervals[0]["kind"] == "work"
    assert "outside pomodoro" in intervals[0]["label"]
    assert "40 min" in intervals[0]["label"]


def test_classify_short_bursts_are_ignored(tmp_path):
    store = ActivityStore(db_path=tmp_path / "a.db")
    fill_minutes(store, datetime(2026, 7, 2, 14, 0), 5, active=True)  # < RUN_MIN_MINUTES
    intervals = classify_day(store, date(2026, 7, 2))
    assert intervals == []


# -- totals / summary ---------------------------------------------------------------


def test_cursor_km_conversion():
    # 96 dpi → 96 px per inch → ~3.78 px per mm; 1 km ≈ 3.78e6 px.
    km = cursor_km(3_779_528, 96.0)
    assert abs(km - 1.0) < 0.01


def test_day_summary_totals(tmp_path):
    store = ActivityStore(db_path=tmp_path / "a.db")
    day = date(2026, 7, 2)
    start = datetime(2026, 7, 2, 9, 0)
    # A 25-minute continuous activity run earns one 🍅 (focus is derived from runs now).
    fill_minutes(store, start, 25, active=True, mouse_px=1000, keys=100)
    summary = day_summary(store, day, dpi=96.0)
    assert summary["keys"] == 2500
    assert summary["focus_count"] == 1
    assert summary["best_focus_minutes"] == 25
    assert summary["active_minutes"] == 25
    assert summary["cursor_km"] > 0


def test_retention_purges_old_minutes(tmp_path):
    store = ActivityStore(db_path=tmp_path / "a.db")
    old = datetime(2026, 3, 1, 12, 0)
    fresh = datetime(2026, 7, 1, 12, 0)
    store.record_minute(old, 100, 0, 0, True)
    store.record_minute(fresh, 100, 0, 0, True)
    dropped = store.purge_minutes_older_than(90, now=datetime(2026, 7, 2))
    assert dropped == 1
    assert len(store.minutes_between(datetime(2026, 1, 1), datetime(2027, 1, 1))) == 1


def test_delete_all_activity(tmp_path):
    store = ActivityStore(db_path=tmp_path / "a.db")
    store.record_minute(datetime(2026, 7, 2, 9, 0), 100, 5, 1, True)
    store.record_session(activity_store.FOCUS, datetime(2026, 7, 2, 9, 0), datetime(2026, 7, 2, 9, 25), 1500, True)
    store.delete_all_activity()
    assert store.day_totals(date(2026, 7, 2))["observed_minutes"] == 0
    assert store.sessions_on(date(2026, 7, 2)) == []
