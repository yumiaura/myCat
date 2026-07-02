"""ActivityDialog: the live "Now" line mirrors the focus tooltip."""

from datetime import datetime, timedelta

from mycat.activity import ActivityCollector, ActivitySettings
from mycat.activity_store import ActivityStore
from mycat.activity_ui import ActivityDialog
from mycat.focus import FocusController


class FakeNow:
    def __init__(self):
        self.now = datetime(2026, 7, 2, 9, 0, 0)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


class AnnouncerStub:
    def set_dnd(self, active):
        pass

    def announce(self, *args, **kwargs):
        pass


def make_dialog(tmp_path):
    now = FakeNow()
    store = ActivityStore(db_path=tmp_path / "a.db")
    collector = ActivityCollector(
        store=store,
        settings=ActivitySettings(enabled=True),
        cursor_pos_fn=lambda: None,
        now_fn=now,
        start_timers=False,
    )
    controller = FocusController(None, announcer=AnnouncerStub(), store=store, now_fn=now, start_timer=False)
    controller.attach_collector(collector)
    dialog = ActivityDialog(collector, focus_controller=controller, start_now_timer=False)
    return dialog, controller, now


def test_now_line_idle(tmp_path, qapp):
    dialog, controller, now = make_dialog(tmp_path)
    dialog.refresh_now()
    assert dialog.now_label.text().startswith("Now: idle")


def test_now_line_mirrors_focus_tooltip(tmp_path, qapp):
    dialog, controller, now = make_dialog(tmp_path)
    controller.start_focus()
    now.advance(minutes=7, seconds=18)
    dialog.refresh_now()
    text = dialog.now_label.text()
    assert text.startswith("Now: Focus · 17:42 left")
    assert "🍅" in text


def test_table_has_session_rows_and_totals(tmp_path, qapp):
    from mycat import activity_store

    dialog, controller, now = make_dialog(tmp_path)
    store = controller.store
    start = datetime(2026, 7, 2, 9, 0)
    store.record_session(activity_store.FOCUS, start, start + timedelta(minutes=25), 1500, True)
    for offset in range(25):
        store.record_minute(start + timedelta(minutes=offset), 4000, 200, 8, True)
    dialog.refresh_log()
    # 1 finished session row + 1 TOTAL row (no session is active here).
    assert dialog.table.rowCount() == 2
    assert dialog.table.item(0, 0).text().startswith("🍅 Focus")
    assert dialog.table.item(0, 1).text() == "09:00"  # start time on the session row
    assert dialog.table.item(0, 2).text() == "25:00"  # duration
    assert dialog.table.item(0, 3).text() == "5,000"  # 25 min × 200 keys
    totals = dialog.table.item(1, 0).text()
    assert totals.startswith("TOTAL")
    assert "🍅 1" in totals
    assert dialog.table.item(1, 1).text() == ""  # TOTAL row carries NO start time
    assert dialog.table.item(1, 2).text() == "25:00"  # total duration, no "active"
    assert "active" not in dialog.table.item(1, 2).text()
    assert dialog.table.item(1, 3).text() == "5,000"


def test_current_row_reflects_activity_run(tmp_path, qapp):
    dialog, controller, now = make_dialog(tmp_path)
    collector = controller.collector
    # Simulate an ongoing activity run beginning at 09:00, "now" is 09:03.
    collector.run_start = datetime(2026, 7, 2, 9, 0)
    collector.last_input_at = datetime(2026, 7, 2, 9, 3)
    now.now = datetime(2026, 7, 2, 9, 3)
    for offset in range(3):
        collector.store.record_minute(datetime(2026, 7, 2, 9, offset), 3000, 100, 4, True)
    dialog.refresh_log()
    # Top row is the live Current period.
    assert dialog.current_row == 0
    assert dialog.table.item(0, 0).text() == "▶ Current"
    assert dialog.table.item(0, 1).text() == "09:00"
    assert dialog.table.item(0, 2).text() == "Current"
    assert dialog.table.item(0, 3).text() == "300"  # 3 min × 100 keys
    assert dialog.table.item(0, 6).text().endswith("%")  # active percentage
    # Typing moves the live cells without a full rebuild.
    collector.bucket_keys += 42
    dialog.refresh_now()
    assert dialog.table.item(0, 3).text() == "342"


def test_no_current_row_when_idle(tmp_path, qapp):
    dialog, controller, now = make_dialog(tmp_path)
    # No run started → no Current row, just the (empty) TOTAL row.
    dialog.refresh_log()
    assert dialog.current_row is None
    assert dialog.table.item(0, 0).text().startswith("TOTAL")


def test_interrupted_session_shows_banana(tmp_path, qapp):
    from mycat import activity_store

    dialog, controller, now = make_dialog(tmp_path)
    start = datetime(2026, 7, 2, 9, 0)
    controller.store.record_session(activity_store.FOCUS, start, start + timedelta(minutes=8), 1500, False)
    dialog.refresh_log()
    assert dialog.table.item(0, 0).text() == "🍌 Interrupted"
