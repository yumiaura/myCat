"""Auto-focus watcher: tooltip, the earned/rest banner, DND on active vs idle."""

from datetime import datetime, timedelta

from mycat.activity_store import ActivityStore
from mycat.focus import FocusController, FocusSettings, format_elapsed, load_focus_settings, save_focus_settings


def test_focus_goal_round_trip(tmp_path):
    cfg = tmp_path / "config.ini"
    save_focus_settings(FocusSettings(focus_minutes=30, tooltip_enabled=False), cfg_file=cfg)
    loaded = load_focus_settings(cfg_file=cfg)
    assert loaded.focus_minutes == 30
    assert loaded.tooltip_enabled is False
    # Defaults (no file): 25-minute Pomodoro, hover tooltip off.
    default = load_focus_settings(cfg_file=tmp_path / "none.ini")
    assert default.focus_minutes == 25
    assert default.tooltip_enabled is False


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


class FakeCollector:
    """Hands the watcher whatever current run the test sets, like the real one."""

    def __init__(self) -> None:
        self.run = None

    def current_run_stats(self, now=None):
        return self.run


def make(tmp_path):
    now = FakeNow()
    ann = AnnouncerStub()
    store = ActivityStore(db_path=tmp_path / "a.db")
    controller = FocusController(None, announcer=ann, store=store, now_fn=now, start_timer=False)
    collector = FakeCollector()
    controller.attach_collector(collector)
    return controller, ann, store, now, collector


def run_stats(start, active_minutes=1, keys=0, clicks=0, mouse_px=0, active_pct=100):
    return {
        "start": start,
        "keys": keys,
        "clicks": clicks,
        "mouse_px": mouse_px,
        "active_minutes": active_minutes,
        "elapsed_minutes": active_minutes,
        "active_pct": active_pct,
    }


class FakeWindow:
    """Minimal cat-window stand-in: just captures the tooltip text."""

    def __init__(self) -> None:
        self.tip = None

    def setToolTip(self, text) -> None:
        self.tip = text

    def underMouse(self) -> bool:
        return False


def test_format_elapsed():
    assert format_elapsed(7 * 60 + 18) == "7:18"
    assert format_elapsed(3 * 3600 + 4 * 60 + 5) == "3:04:05"


def test_tooltip_toggle_controls_the_hover_tooltip(tmp_path, qapp):
    now = FakeNow()
    store = ActivityStore(db_path=tmp_path / "a.db")
    window = FakeWindow()
    controller = FocusController(window, announcer=AnnouncerStub(), store=store, now_fn=now, start_timer=False)
    col = FakeCollector()
    controller.attach_collector(col)
    col.run = run_stats(now(), keys=100)
    # On: the tooltip carries the live stats.
    controller.settings.tooltip_enabled = True
    controller.refresh_visuals()
    assert window.tip and "⌨ 100" in window.tip
    # Off (default): the tooltip is cleared (empty string also kills the hover-show).
    controller.settings.tooltip_enabled = False
    controller.refresh_visuals()
    assert window.tip == ""


def test_idle_has_no_tooltip_and_no_dnd(tmp_path, qapp):
    controller, ann, store, now, col = make(tmp_path)
    col.run = None
    controller.tick()
    assert controller.status_text() == ""
    assert ann.dnd_calls == []  # DND was never switched on


def test_active_run_sets_dnd_and_ticks_tooltip(tmp_path, qapp):
    controller, ann, store, now, col = make(tmp_path)
    col.run = run_stats(now(), keys=450, active_pct=96)
    now.advance(minutes=7, seconds=18)
    controller.tick()
    assert ann.dnd_calls == [True]
    text = controller.status_text()
    assert text.startswith("🍅 0 · 7:18")  # no "Focus" label, just the stats
    assert "⌨ 450" in text and "% active" in text


def test_earned_banner_fires_once_at_focus_minutes(tmp_path, qapp):
    controller, ann, store, now, col = make(tmp_path)
    col.run = run_stats(now())
    now.advance(minutes=24)
    controller.tick()
    assert ann.announced == []  # not yet 25 min
    now.advance(minutes=1)
    controller.tick()
    assert ann.announced == ["🍅 earned — time to rest"]
    assert controller.status_text().startswith("🍅 0 · 25:")  # tooltip is stats-only
    now.advance(minutes=10)
    controller.tick()
    assert ann.announced == ["🍅 earned — time to rest"]  # no re-fire before 50 min


def test_rest_reminder_repeats_every_interval(tmp_path, qapp):
    controller, ann, store, now, col = make(tmp_path)
    col.run = run_stats(now())
    now.advance(minutes=25)
    controller.tick()
    now.advance(minutes=25)
    controller.tick()  # 50 min of unbroken work
    assert ann.announced == ["🍅 earned — time to rest", "Still at it — time to rest 🍅"]


def test_dnd_released_when_the_run_ends(tmp_path, qapp):
    controller, ann, store, now, col = make(tmp_path)
    col.run = run_stats(now())
    controller.tick()
    assert ann.dnd_calls == [True]
    col.run = None  # rested past the gap
    controller.tick()
    assert ann.dnd_calls == [True, False]


def test_a_fresh_run_can_earn_again(tmp_path, qapp):
    controller, ann, store, now, col = make(tmp_path)
    col.run = run_stats(now())
    now.advance(minutes=25)
    controller.tick()
    col.run = None
    controller.tick()  # rest
    now.advance(minutes=10)
    col.run = run_stats(now())  # brand-new run
    now.advance(minutes=25)
    controller.tick()
    assert ann.announced == ["🍅 earned — time to rest", "🍅 earned — time to rest"]


def test_today_count_reads_earned_runs_from_the_store(tmp_path, qapp):
    controller, ann, store, now, col = make(tmp_path)
    start = datetime(2026, 7, 2, 8, 0)
    for offset in range(26):  # a 26-minute run → one 🍅
        store.record_minute(start + timedelta(minutes=offset), 4000, 200, 8, True)
    assert controller.today_count() == 1
