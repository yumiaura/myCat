"""ActivityStore: schema, session records, per-day queries."""

from datetime import date, datetime

from mycat.activity_store import BREAK, FOCUS, ActivityStore


def test_creates_db_and_records_sessions(tmp_path):
    store = ActivityStore(db_path=tmp_path / "activity.db")
    store.record_session(
        kind=FOCUS,
        started_at=datetime(2026, 7, 2, 9, 0),
        ended_at=datetime(2026, 7, 2, 9, 25),
        planned_seconds=1500,
        completed=True,
    )
    rows = store.sessions_on(date(2026, 7, 2))
    assert len(rows) == 1
    assert rows[0]["kind"] == FOCUS
    assert rows[0]["completed"] == 1
    assert rows[0]["planned_seconds"] == 1500
    store.close()


def test_sessions_are_bucketed_by_local_day(tmp_path):
    store = ActivityStore(db_path=tmp_path / "activity.db")
    store.record_session(FOCUS, datetime(2026, 7, 1, 23, 50), datetime(2026, 7, 2, 0, 15), 1500, True)
    store.record_session(FOCUS, datetime(2026, 7, 2, 9, 0), datetime(2026, 7, 2, 9, 25), 1500, True)
    assert len(store.sessions_on(date(2026, 7, 1))) == 1  # bucketed by start time
    assert len(store.sessions_on(date(2026, 7, 2))) == 1
    store.close()


def test_completed_focus_count_ignores_breaks_and_incomplete(tmp_path):
    store = ActivityStore(db_path=tmp_path / "activity.db")
    day = date(2026, 7, 2)
    store.record_session(FOCUS, datetime(2026, 7, 2, 9, 0), datetime(2026, 7, 2, 9, 25), 1500, True)
    store.record_session(BREAK, datetime(2026, 7, 2, 9, 25), datetime(2026, 7, 2, 9, 30), 300, True)
    store.record_session(FOCUS, datetime(2026, 7, 2, 10, 0), datetime(2026, 7, 2, 10, 5), 1500, False)
    assert store.completed_focus_count(day) == 1
    store.close()


def test_reopen_keeps_data(tmp_path):
    path = tmp_path / "activity.db"
    store = ActivityStore(db_path=path)
    store.record_session(FOCUS, datetime(2026, 7, 2, 9, 0), datetime(2026, 7, 2, 9, 25), 1500, True)
    store.close()
    reopened = ActivityStore(db_path=path)
    assert reopened.completed_focus_count(date(2026, 7, 2)) == 1
    reopened.close()
