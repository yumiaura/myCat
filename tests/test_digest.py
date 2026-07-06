"""Morning digest: once per day, after 05:00, only when there is a story."""

from datetime import datetime, timedelta

from mycat import activity_store
from mycat.activity_store import ActivityStore
from mycat.digest import MorningDigest, compose_digest, load_digest_date


class FakeNow:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


class AnnouncerStub:
    def __init__(self):
        self.announced = []

    def announce(self, text, url="", **kwargs):
        self.announced.append(text)


def store_with_yesterday(tmp_path):
    store = ActivityStore(db_path=tmp_path / "a.db")
    yesterday_morning = datetime(2026, 7, 1, 9, 0)
    store.record_session(
        activity_store.FOCUS, yesterday_morning, yesterday_morning + timedelta(minutes=25), 1500, True
    )
    for offset in range(60):
        store.record_minute(yesterday_morning + timedelta(minutes=offset), 4000, 220, 10, True)
    return store


def make_digest(tmp_path, store, start):
    ann = AnnouncerStub()
    now = FakeNow(start)
    dig = MorningDigest(
        store,
        announcer=ann,
        now_fn=now,
        dpi_fn=lambda: 96.0,
        cfg_file=tmp_path / "config.ini",
        start_timer=False,
    )
    return dig, ann, now


def test_delivers_once_after_morning_hour(tmp_path):
    store = store_with_yesterday(tmp_path)
    dig, ann, now = make_digest(tmp_path, store, datetime(2026, 7, 2, 9, 0))
    dig.tick()
    assert len(ann.announced) == 1
    text = ann.announced[0]
    assert text.startswith("Yesterday:")
    assert "🍅 1" in text
    assert "⌨ 13,200" in text  # 60 min × 220 keys
    assert "best focus 60 min" in text  # one unbroken 60-min run = one long 🍅
    dig.tick()
    assert len(ann.announced) == 1  # once per day


def test_not_before_morning_hour(tmp_path):
    store = store_with_yesterday(tmp_path)
    dig, ann, now = make_digest(tmp_path, store, datetime(2026, 7, 2, 1, 30))
    dig.tick()
    assert ann.announced == []
    now.now = datetime(2026, 7, 2, 5, 1)
    dig.tick()
    assert len(ann.announced) == 1


def test_empty_yesterday_marks_delivered_without_banner(tmp_path):
    store = ActivityStore(db_path=tmp_path / "a.db")  # nothing recorded
    dig, ann, now = make_digest(tmp_path, store, datetime(2026, 7, 2, 9, 0))
    dig.tick()
    assert ann.announced == []
    assert dig.delivered_date == "2026-07-02"


def test_delivery_date_survives_restart(tmp_path):
    store = store_with_yesterday(tmp_path)
    dig, ann, now = make_digest(tmp_path, store, datetime(2026, 7, 2, 9, 0))
    dig.tick()
    assert load_digest_date(tmp_path / "config.ini") == "2026-07-02"
    # A "restarted" digest with the same config re-delivers nothing.
    dig2, ann2, now2 = make_digest(tmp_path, store, datetime(2026, 7, 2, 10, 0))
    dig2.tick()
    assert ann2.announced == []


def test_next_day_delivers_again(tmp_path):
    store = store_with_yesterday(tmp_path)
    dig, ann, now = make_digest(tmp_path, store, datetime(2026, 7, 2, 9, 0))
    dig.tick()
    # 2026-07-03 morning: yesterday (07-02) has no data → no banner, but the
    # date advances.
    now.now = datetime(2026, 7, 3, 9, 0)
    dig.tick()
    assert len(ann.announced) == 1
    assert dig.delivered_date == "2026-07-03"


def test_compose_digest_skips_empty_parts():
    assert compose_digest(
        {"cursor_km": 0.0, "keys": 0, "focus_count": 0, "best_focus_minutes": 0}
    ) == ""
    text = compose_digest(
        {"cursor_km": 2.13, "keys": 0, "focus_count": 6, "best_focus_minutes": 52}
    )
    assert text == "Yesterday: 🖱 2.1 km · 🍅 6 · best focus 52 min"
