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
    assert dialog.now_label.text().startswith("Current: idle")


def test_now_line_mirrors_focus_tooltip(tmp_path, qapp):
    dialog, controller, now = make_dialog(tmp_path)
    store = controller.store
    for offset in range(7):  # a 7-minute run reaching now
        store.record_minute(datetime(2026, 7, 2, 9, offset), 4000, 200, 8, True)
    now.now = datetime(2026, 7, 2, 9, 7, 18)
    dialog.refresh_now()
    text = dialog.now_label.text()
    assert text.startswith("Current: 🍅 0 · 7:18")


def test_table_has_session_rows_and_totals(tmp_path, qapp):
    from mycat import activity_store

    dialog, controller, now = make_dialog(tmp_path)
    store = controller.store
    start = datetime(2026, 7, 2, 9, 0)
    store.record_session(activity_store.FOCUS, start, start + timedelta(minutes=25), 1500, True)
    for offset in range(25):
        store.record_minute(start + timedelta(minutes=offset), 4000, 200, 8, True)
    now.now = datetime(2026, 7, 2, 10, 0)  # well past the last activity → no current period
    dialog.refresh_log()
    # Just the finished session row; the TOTAL is its own always-visible label.
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == "🍅 09:00"  # icon + start, merged
    assert dialog.table.item(0, 1).text() == "25min"  # duration (compact h/min)
    assert dialog.table.item(0, 2).text() == "5,000"  # 25 min × 200 keys
    assert dialog.totals_table.item(0, 0).text().startswith("TOTAL")
    assert "🍅 1" in dialog.totals_table.item(0, 0).text()
    assert dialog.totals_table.item(0, 1).text() == "25min"  # total duration
    assert dialog.totals_table.item(0, 2).text() == "5,000"  # total keys


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
    # Top row is the live current run — under 25 min, so still "▶" (no 🍅 yet).
    assert dialog.current_row == 0
    assert dialog.table.item(0, 0).text() == "▶ 09:00"  # marker + start, merged
    assert dialog.table.item(0, 1).text() == "3:00"  # elapsed so far (09:00 → 09:03)
    assert dialog.table.item(0, 2).text() == "300"  # 3 min × 100 keys
    assert dialog.table.item(0, 3).text().startswith("12 / ")  # merged clicks / path
    assert dialog.table.item(0, 4).text().endswith("%")  # active percentage
    # Typing moves the live cells on the next refresh.
    collector.bucket_keys += 42
    dialog.refresh_now()
    assert dialog.table.item(0, 2).text() == "342"


def test_current_row_says_focus_while_building(tmp_path, qapp):
    dialog, controller, now = make_dialog(tmp_path)
    store = controller.store
    for offset in range(3):  # a short live run, under 25 min
        store.record_minute(datetime(2026, 7, 2, 9, offset), 3000, 100, 4, True)
    now.now = datetime(2026, 7, 2, 9, 3)
    dialog.refresh_log()
    assert dialog.table.item(0, 0).text() == "▶ 09:00"
    assert dialog.current_phase == "focus"


def test_current_row_earns_tomato_past_25_min(tmp_path, qapp):
    dialog, controller, now = make_dialog(tmp_path)
    store = controller.store
    for offset in range(26):  # a live run already past 25 min
        store.record_minute(datetime(2026, 7, 2, 9, offset), 3000, 100, 4, True)
    now.now = datetime(2026, 7, 2, 9, 26)
    dialog.refresh_log()
    assert dialog.table.item(0, 0).text() == "▶ 🍅 09:00"
    assert "🍅 1" in dialog.totals_table.item(0, 0).text()  # counted in the TOTAL row


def test_timeline_cells_are_activity_heat(tmp_path, qapp):
    dialog, controller, now = make_dialog(tmp_path)
    store = controller.store
    # 9:00 busy (active), 9:01 idle (rest), 9:02 no data (gap).
    store.record_minute(datetime(2026, 7, 2, 9, 0), 4000, 250, 10, True)
    store.record_minute(datetime(2026, 7, 2, 9, 1), 0, 0, 0, False)
    now.now = datetime(2026, 7, 2, 9, 30)
    cells, ws, we, marker = dialog.build_timeline()
    kinds = {c[0].strftime("%H:%M"): c[1] for c in cells}
    assert kinds["09:00"] == "active"
    assert kinds["09:01"] == "rest"
    assert "09:02" not in kinds  # unrecorded minute → no cell (grey gap)
    # Full-day window even for today: midnight → next midnight, with a now marker.
    assert ws == datetime(2026, 7, 2, 0, 0)
    assert we == datetime(2026, 7, 3, 0, 0)
    assert marker == now.now


def test_timeline_window_full_day_for_yesterday(tmp_path, qapp):
    dialog, controller, now = make_dialog(tmp_path)
    now.now = datetime(2026, 7, 2, 14, 0)
    dialog.day_combo.setCurrentIndex(1)  # Yesterday
    cells, ws, we, marker = dialog.build_timeline()
    assert ws == datetime(2026, 7, 1, 0, 0)
    assert we == datetime(2026, 7, 2, 0, 0)  # full 24h
    assert marker is None  # no "now" line on a past day


def test_no_current_row_when_idle(tmp_path, qapp):
    dialog, controller, now = make_dialog(tmp_path)
    # No run started → no rows at all; the TOTAL label still shows (empty) totals.
    dialog.refresh_log()
    assert dialog.current_row is None
    assert dialog.table.rowCount() == 0
    assert dialog.totals_table.item(0, 0).text().startswith("TOTAL")


def test_export_csv_writes_period_rows(tmp_path, qapp):
    import csv

    dialog, controller, now = make_dialog(tmp_path)
    store = controller.store
    # A 25-minute run → 🍅 (completed=1); a later 10-minute run → 🍌 (completed=0).
    for offset in range(25):
        store.record_minute(datetime(2026, 7, 2, 9, offset), 4000, 200, 8, True)
    for offset in range(10):
        store.record_minute(datetime(2026, 7, 2, 9, 40 + offset), 1000, 50, 2, True)
    now.now = datetime(2026, 7, 2, 10, 0)

    out = tmp_path / "activity.csv"
    count = dialog.write_csv(str(out))
    assert count == 2

    rows = list(csv.DictReader(out.open()))
    assert [r["period"] for r in rows] == ["Focus", "Focus"]  # chronological
    tomato = rows[0]
    assert tomato["start"] == "2026-07-02T09:00:00"
    assert tomato["end"] == "2026-07-02T09:25:00"
    assert tomato["duration_seconds"] == "1500"
    assert tomato["keys"] == "5000"  # 25 min × 200
    assert tomato["clicks"] == "200"  # 25 min × 8
    assert tomato["active_minutes"] == "25"
    assert tomato["active_percent"] == "100"
    assert tomato["completed"] == "1"  # earned a 🍅
    banana = rows[1]
    assert banana["completed"] == "0"  # under 25 min → 🍌
    assert banana["keys"] == "500"  # 10 min × 50


def test_short_run_shows_banana(tmp_path, qapp):
    dialog, controller, now = make_dialog(tmp_path)
    store = controller.store
    for offset in range(8):  # an 8-minute run — under 25, so a 🍌
        store.record_minute(datetime(2026, 7, 2, 9, offset), 4000, 200, 8, True)
    now.now = datetime(2026, 7, 2, 10, 0)
    dialog.refresh_log()
    assert dialog.table.item(0, 0).text() == "🍌 09:00"


def test_activity_checkboxes_are_independent(tmp_path, qapp):
    dialog, controller, now = make_dialog(tmp_path)
    assert dialog.mouse_box.isChecked()
    assert dialog.keyboard_box.isChecked()
    assert dialog.mouse_box.isEnabled()
    assert dialog.keyboard_box.isEnabled()
    # Tracking, Mouse and Keyboard are independent: toggling Tracking (the eyes)
    # never greys out the Mouse/Keyboard count tracks.
    dialog.enabled_box.setChecked(False)
    assert dialog.mouse_box.isEnabled()
    assert dialog.keyboard_box.isEnabled()
    dialog.enabled_box.setChecked(True)
    assert dialog.mouse_box.isEnabled()
    assert dialog.keyboard_box.isEnabled()


def test_save_writes_three_flags(tmp_path, qapp, monkeypatch):
    dialog, controller, now = make_dialog(tmp_path)
    saved = []
    focus_saved = []
    # Never touch the real ~/.config/mycat/config.ini from a test.
    monkeypatch.setattr("mycat.activity.save_activity_settings", lambda settings, **kw: saved.append(settings))
    monkeypatch.setattr("mycat.focus.save_focus_settings", lambda settings, **kw: focus_saved.append(settings))
    dialog.enabled_box.setChecked(True)
    dialog.mouse_box.setChecked(True)
    dialog.keyboard_box.setChecked(False)
    dialog.save_settings()
    assert len(saved) == 1
    assert saved[0].enabled is True
    assert saved[0].mouse_enabled is True
    assert saved[0].keyboard_enabled is False
    assert "mouse ✓" in dialog.status_label.text()
    assert "keyboard ✗" in dialog.status_label.text()


def test_save_persists_and_applies_pomodoro_goal(tmp_path, qapp, monkeypatch):
    dialog, controller, now = make_dialog(tmp_path)
    focus_saved = []
    monkeypatch.setattr("mycat.activity.save_activity_settings", lambda settings, **kw: None)
    monkeypatch.setattr("mycat.focus.save_focus_settings", lambda settings, **kw: focus_saved.append(settings))
    dialog.goal_spin.setValue(30)
    dialog.save_settings()
    assert len(focus_saved) == 1
    assert focus_saved[0].focus_minutes == 30  # persisted
    assert controller.settings.focus_minutes == 30  # applied live
    assert "goal 30 min" in dialog.status_label.text()


def test_save_persists_and_applies_tooltip_toggle(tmp_path, qapp, monkeypatch):
    dialog, controller, now = make_dialog(tmp_path)
    focus_saved = []
    monkeypatch.setattr("mycat.activity.save_activity_settings", lambda settings, **kw: None)
    monkeypatch.setattr("mycat.focus.save_focus_settings", lambda settings, **kw: focus_saved.append(settings))
    assert not dialog.tooltip_box.isChecked()  # off by default
    dialog.tooltip_box.setChecked(True)
    dialog.save_settings()
    assert focus_saved[0].tooltip_enabled is True  # persisted
    assert controller.settings.tooltip_enabled is True  # applied live
    assert "tooltip ✓" in dialog.status_label.text()


def test_brief_run_is_a_banana(tmp_path, qapp):
    dialog, controller, now = make_dialog(tmp_path)
    store = controller.store
    for offset in range(3):  # a 3-minute run — any finished run under 25 min is a 🍌
        store.record_minute(datetime(2026, 7, 2, 9, offset), 4000, 200, 8, True)
    now.now = datetime(2026, 7, 2, 10, 0)
    dialog.refresh_log()
    assert dialog.table.rowCount() == 1  # not hidden
    assert dialog.table.item(0, 0).text() == "🍌 09:00"
