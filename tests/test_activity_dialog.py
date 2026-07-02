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
    dialog = ActivityDialog(collector, focus_controller=controller)
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
