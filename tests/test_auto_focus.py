"""Auto-pomodoro: idle-resume edge detection and the auto-start guards."""

from datetime import datetime, timedelta

from mycat.activity import ActivityCollector, ActivitySettings
from mycat.activity_store import ActivityStore
from mycat.focus import FOCUS, IDLE, FocusController


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


class AnnouncerStub:
    def set_dnd(self, active):
        pass

    def announce(self, *args, **kwargs):
        pass


def make_pair(tmp_path):
    """Collector + controller sharing a store and a clock, fully wired."""
    now = FakeNow()
    store = ActivityStore(db_path=tmp_path / "a.db")
    positions = {"pos": FakePoint(0, 0)}

    collector = ActivityCollector(
        store=store,
        settings=ActivitySettings(enabled=True),
        cursor_pos_fn=lambda: positions["pos"],
        now_fn=now,
        start_timers=False,
    )
    controller = FocusController(None, announcer=AnnouncerStub(), store=store, now_fn=now, start_timer=False)
    controller.attach_collector(collector)
    collector.sample()  # seed last_pos so the next movement registers as input
    return collector, controller, now, positions


def move_cursor(positions, dx):
    old = positions["pos"]
    positions["pos"] = FakePoint(old.x() + dx, old.y())


def test_idle_resume_auto_starts_focus(tmp_path, qapp):
    collector, controller, now, positions = make_pair(tmp_path)
    # Baseline input (first input after startup never triggers).
    move_cursor(positions, 100)
    collector.sample()
    assert controller.state == IDLE
    # 10 minutes of silence, then input again → auto-start.
    for _ in range(10):
        now.advance(minutes=1)
        collector.sample()
    assert controller.state == IDLE  # silence alone starts nothing
    move_cursor(positions, 100)
    collector.sample()
    assert controller.state == FOCUS


def test_short_pause_does_not_trigger(tmp_path, qapp):
    collector, controller, now, positions = make_pair(tmp_path)
    move_cursor(positions, 100)
    collector.sample()
    now.advance(minutes=2)  # under IDLE_RESUME_MINUTES
    move_cursor(positions, 100)
    collector.sample()
    assert controller.state == IDLE


def test_first_input_after_startup_only_baselines(tmp_path, qapp):
    collector, controller, now, positions = make_pair(tmp_path)
    now.advance(hours=2)  # app just started, whatever happened before is unknown
    move_cursor(positions, 100)
    collector.sample()
    assert controller.state == IDLE


def test_auto_start_disabled_by_setting(tmp_path, qapp):
    collector, controller, now, positions = make_pair(tmp_path)
    controller.settings.auto_start = False
    move_cursor(positions, 100)
    collector.sample()
    now.advance(minutes=10)
    collector.sample()
    move_cursor(positions, 100)
    collector.sample()
    assert controller.state == IDLE


def test_manual_stop_blocks_auto_start_for_a_while(tmp_path, qapp):
    collector, controller, now, positions = make_pair(tmp_path)
    controller.start_focus()
    now.advance(minutes=3)
    controller.stop()
    # Idle-resume right after the stop must NOT restart the session…
    controller.maybe_auto_start()
    assert controller.state == IDLE
    # …but after the cooldown it may again.
    now.advance(minutes=controller.settings.break_minutes + 1)
    controller.maybe_auto_start()
    assert controller.state == FOCUS


def test_no_auto_start_during_active_session(tmp_path, qapp):
    collector, controller, now, positions = make_pair(tmp_path)
    controller.start_focus()
    started = controller.phase_started
    controller.maybe_auto_start()
    assert controller.phase_started == started  # unchanged, not restarted


def test_tooltip_carries_live_session_stats(tmp_path, qapp):
    collector, controller, now, positions = make_pair(tmp_path)
    controller.start_focus()
    # Two active minutes: typing + mouse, flushed into the store.
    collector.sample()
    collector.bucket_keys += 300
    move_cursor(positions, 5000)
    collector.sample()
    now.advance(minutes=1)
    collector.sample()  # rollover: minute 1 flushed
    collector.bucket_keys += 150
    now.advance(minutes=1)
    collector.sample()  # rollover: minute 2 flushed
    text = controller.status_text()
    # Agreed order: Focus · 🍅 N · duration · ⌨ keys · 🖱 clicks/path · % active
    assert text.startswith("Focus · 🍅 0 ·")
    assert "⌨ 450" in text
    assert "🖱" in text and "/" in text  # clicks and path share the mouse icon
    assert "% active" in text
