"""Focus state machine: transitions, DND, session records, overshoot grace."""

from datetime import datetime, timedelta

from mycat import activity_store
from mycat.activity_store import ActivityStore
from mycat.focus import BREAK, FOCUS, IDLE, FocusController


class FakeNow:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 2, 9, 0, 0)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


class AnnouncerStub:
    def __init__(self) -> None:
        self.dnd_calls = []
        self.announced = []

    def set_dnd(self, active) -> None:
        self.dnd_calls.append(bool(active))

    def announce(self, text, url="", urgent=False, **kwargs):
        self.announced.append(text)


def make_controller(tmp_path, qapp):
    now = FakeNow()
    ann = AnnouncerStub()
    store = ActivityStore(db_path=tmp_path / "activity.db")
    controller = FocusController(None, announcer=ann, store=store, now_fn=now, start_timer=False)
    return controller, ann, store, now


def run_out_phase(controller, now):
    now.advance(seconds=controller.remaining_seconds() + 1)
    controller.tick()


def test_starts_idle(tmp_path, qapp):
    controller, ann, store, now = make_controller(tmp_path, qapp)
    assert controller.state == IDLE
    assert controller.status_text() == ""


def test_start_focus_enables_dnd(tmp_path, qapp):
    controller, ann, store, now = make_controller(tmp_path, qapp)
    controller.start_focus()
    assert controller.state == FOCUS
    assert ann.dnd_calls == [True]
    assert controller.remaining_seconds() == controller.settings.focus_minutes * 60


def test_focus_runs_out_into_break_with_banner(tmp_path, qapp):
    controller, ann, store, now = make_controller(tmp_path, qapp)
    controller.start_focus()
    run_out_phase(controller, now)
    assert controller.state == BREAK
    assert ann.dnd_calls == [True, False]
    assert any("Break time" in text for text in ann.announced)
    sessions = store.sessions_on(now().date())
    assert [(row["kind"], row["completed"]) for row in sessions] == [(activity_store.FOCUS, 1)]


def test_break_runs_out_into_idle(tmp_path, qapp):
    controller, ann, store, now = make_controller(tmp_path, qapp)
    controller.start_focus()
    run_out_phase(controller, now)  # -> break
    run_out_phase(controller, now)  # -> idle
    assert controller.state == IDLE
    assert any("Break's over" in text for text in ann.announced)
    kinds = [row["kind"] for row in store.sessions_on(now().date())]
    assert kinds == [activity_store.FOCUS, activity_store.BREAK]


def test_long_break_after_streak(tmp_path, qapp):
    controller, ann, store, now = make_controller(tmp_path, qapp)
    per_long = controller.settings.sessions_before_long_break
    for cycle in range(per_long):
        controller.start_focus()
        run_out_phase(controller, now)  # focus -> break
        if cycle < per_long - 1:
            run_out_phase(controller, now)  # break -> idle
    assert controller.on_long_break is True
    assert controller.remaining_seconds() == controller.settings.long_break_minutes * 60
    assert any("Break" in text for text in ann.announced)
    run_out_phase(controller, now)
    kinds = [row["kind"] for row in store.sessions_on(now().date())]
    assert kinds.count(activity_store.LONG_BREAK) == 1


def test_stop_mid_focus_records_incomplete_and_lifts_dnd(tmp_path, qapp):
    controller, ann, store, now = make_controller(tmp_path, qapp)
    controller.start_focus()
    now.advance(minutes=10)
    controller.stop()
    assert controller.state == IDLE
    assert ann.dnd_calls == [True, False]
    sessions = store.sessions_on(now().date())
    assert [(row["kind"], row["completed"]) for row in sessions] == [(activity_store.FOCUS, 0)]
    # No celebration banner for an abandoned session.
    assert ann.announced == []


def test_skip_break_starts_next_focus(tmp_path, qapp):
    controller, ann, store, now = make_controller(tmp_path, qapp)
    controller.start_focus()
    run_out_phase(controller, now)  # -> break
    controller.skip_break()
    assert controller.state == FOCUS
    kinds_completed = [(row["kind"], row["completed"]) for row in store.sessions_on(now().date())]
    assert kinds_completed == [(activity_store.FOCUS, 1), (activity_store.BREAK, 0)]


def test_today_count_counts_only_completed_focus(tmp_path, qapp):
    controller, ann, store, now = make_controller(tmp_path, qapp)
    controller.start_focus()
    run_out_phase(controller, now)  # completed focus
    controller.stop()  # abandon the break
    controller.start_focus()
    now.advance(minutes=1)
    controller.stop()  # abandoned focus
    assert controller.today_count() == 1


def test_overshoot_after_suspend_finishes_quietly(tmp_path, qapp):
    controller, ann, store, now = make_controller(tmp_path, qapp)
    controller.start_focus()
    # Lid closed: the deadline passed hours ago.
    now.advance(hours=3)
    controller.tick()
    assert controller.state == IDLE  # no auto-break hours later
    assert ann.announced == []  # and no stale banner
    sessions = store.sessions_on(now().date())
    assert [(row["kind"], row["completed"]) for row in sessions] == [(activity_store.FOCUS, 1)]


def test_status_text_formats_clock(tmp_path, qapp):
    controller, ann, store, now = make_controller(tmp_path, qapp)
    controller.start_focus()
    now.advance(minutes=7, seconds=18)
    text = controller.status_text()
    # Agreed order: Focus · 🍅 N · duration · (⌨/🖱/% when stats exist)
    assert text.startswith("Focus · 🍅 0 · 17:42 left")
