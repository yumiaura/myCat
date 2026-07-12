"""Announcer queue: pacing, one-at-a-time, FIFO order (nothing is suppressed)."""

from mycat.announcer import MIN_GAP_SECONDS, SKY_STALE_SECONDS, Announcement, Announcer
from mycat import reminder


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeSky:
    """Records launches; pretends a window is on screen until finish()."""

    def __init__(self) -> None:
        self.launched = []

    def launch(self, item):
        self.launched.append(item)
        return object()  # opaque "window" handle


def make_announcer(qapp):
    clock = FakeClock()
    sky = FakeSky()
    ann = Announcer(None, launch=sky.launch, clock=clock, start_timer=False)
    return ann, sky, clock


def finish_flight(ann):
    ann.flyby_gone()


def test_first_announcement_flies_immediately(qapp):
    ann, sky, clock = make_announcer(qapp)
    ann.announce("hello")
    assert [a.text for a in sky.launched] == ["hello"]
    assert ann.pending_count() == 0


def test_second_announcement_waits_for_active_flight(qapp):
    ann, sky, clock = make_announcer(qapp)
    ann.announce("first")
    ann.announce("second")
    assert [a.text for a in sky.launched] == ["first"]
    assert ann.pending_count() == 1


def test_min_gap_between_flights(qapp):
    ann, sky, clock = make_announcer(qapp)
    ann.announce("first")
    ann.announce("second")
    finish_flight(ann)
    ann.pump()  # gap not yet elapsed
    assert [a.text for a in sky.launched] == ["first"]
    clock.advance(MIN_GAP_SECONDS + 0.1)
    ann.pump()
    assert [a.text for a in sky.launched] == ["first", "second"]


def test_every_announcement_is_shown_in_fifo_order(qapp):
    # Nothing is ever suppressed (no do-not-disturb); the queue only paces
    # flybys, draining strictly in the order they were queued.
    ann, sky, clock = make_announcer(qapp)
    ann.announce("first")  # takes off immediately
    ann.announce("second")
    ann.announce("third")
    order = []
    while ann.pending_count():
        finish_flight(ann)
        clock.advance(MIN_GAP_SECONDS + 0.1)
        ann.pump()
    order = [a.text for a in sky.launched]
    assert order == ["first", "second", "third"]


def test_parked_flyby_stops_blocking_after_stale_timeout(qapp):
    ann, sky, clock = make_announcer(qapp)
    ann.announce("parked one")  # takes off, user grabs and parks it
    ann.announce("waiting")
    # Still blocked while the parked plane is fresh…
    clock.advance(60)
    ann.pump()
    assert [a.text for a in sky.launched] == ["parked one"]
    # …but after the stale timeout the sky is released and the queue moves.
    clock.advance(SKY_STALE_SECONDS + 1)
    ann.pump()
    assert [a.text for a in sky.launched] == ["parked one", "waiting"]


def test_headless_launch_returns_none_keeps_pacing(qapp):
    clock = FakeClock()
    launched = []

    def null_launch(item):
        launched.append(item.text)
        return None

    ann = Announcer(None, launch=null_launch, clock=clock, start_timer=False)
    ann.announce("a")
    ann.announce("b")
    # "a" launched, returned None -> pacing gap applies, "b" still queued.
    assert launched == ["a"]
    clock.advance(MIN_GAP_SECONDS + 0.1)
    ann.pump()
    assert launched == ["a", "b"]


def test_announcement_default_plane_color_matches_reminder():
    # 0.1.9 made Reminder white; Activity/digest flybys must match even before
    # the user saves a [reminder] section.
    assert Announcement.plane_color == reminder.Reminder.plane_color == "white"


def test_default_cosmetics_white_when_no_saved_reminder(monkeypatch, tmp_path, qapp):
    monkeypatch.setattr(reminder, "CFG_DIR", tmp_path)
    monkeypatch.setattr(reminder, "CFG_FILE", tmp_path / "config.ini")
    ann, sky, _clock = make_announcer(qapp)
    assert ann.default_cosmetics()["plane_color"] == "white"
    item = ann.announce("🍅 earned — time to rest")
    assert item.plane_color == "white"
    assert sky.launched[0].plane_color == "white"


def test_default_cosmetics_uses_saved_plane_color(monkeypatch, tmp_path, qapp):
    monkeypatch.setattr(reminder, "CFG_DIR", tmp_path)
    monkeypatch.setattr(reminder, "CFG_FILE", tmp_path / "config.ini")
    reminder.save_reminder(reminder.Reminder(plane_color="blue", plane="plane2", plane_width=200))
    ann, sky, _clock = make_announcer(qapp)
    item = ann.announce("digest")
    assert item.plane_color == "blue"
    assert item.plane == "plane2"
    assert item.plane_width == 200
    assert sky.launched[0].plane_color == "blue"


def test_clear_reminder_keeps_plane_cosmetics_for_announcer(monkeypatch, tmp_path, qapp):
    # Reset must not leave Activity on a different plane than Reminder defaults.
    monkeypatch.setattr(reminder, "CFG_DIR", tmp_path)
    monkeypatch.setattr(reminder, "CFG_FILE", tmp_path / "config.ini")
    reminder.save_reminder(reminder.Reminder(plane_color="pink", enabled=True))
    reminder.clear_reminder()
    saved = reminder.load_reminder()
    assert saved is not None
    assert saved.enabled is False
    assert saved.plane_color == "white"
    ann, sky, _clock = make_announcer(qapp)
    item = ann.announce("🍅 earned — time to rest")
    assert item.plane_color == "white"
    assert sky.launched[0].plane_color == "white"
