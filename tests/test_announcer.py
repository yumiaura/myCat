"""Announcer queue: pacing, one-at-a-time, DND hold/release, urgent bypass."""

from mycat.announcer import MIN_GAP_SECONDS, SKY_STALE_SECONDS, Announcer


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


def test_dnd_holds_normal_items(qapp):
    ann, sky, clock = make_announcer(qapp)
    ann.set_dnd(True)
    ann.announce("github ping")
    assert sky.launched == []
    assert ann.pending_count() == 1


def test_dnd_release_flushes_queue_in_order(qapp):
    ann, sky, clock = make_announcer(qapp)
    ann.set_dnd(True)
    ann.announce("one")
    ann.announce("two")
    ann.set_dnd(False)
    assert [a.text for a in sky.launched] == ["one"]
    finish_flight(ann)
    clock.advance(MIN_GAP_SECONDS + 0.1)
    ann.pump()
    assert [a.text for a in sky.launched] == ["one", "two"]


def test_urgent_bypasses_dnd(qapp):
    ann, sky, clock = make_announcer(qapp)
    ann.set_dnd(True)
    ann.announce("normal")
    ann.announce("meeting in 10", urgent=True)
    assert [a.text for a in sky.launched] == ["meeting in 10"]
    # The normal item is still held.
    finish_flight(ann)
    clock.advance(MIN_GAP_SECONDS + 0.1)
    ann.pump()
    assert [a.text for a in sky.launched] == ["meeting in 10"]
    assert ann.pending_count() == 1


def test_urgent_jumps_ahead_but_keeps_fifo_among_urgent(qapp):
    ann, sky, clock = make_announcer(qapp)
    ann.announce("blocker")  # takes off immediately, occupies the sky
    ann.announce("normal")
    ann.announce("urgent-1", urgent=True)
    ann.announce("urgent-2", urgent=True)
    order = []
    while ann.pending_count():
        finish_flight(ann)
        clock.advance(MIN_GAP_SECONDS + 0.1)
        ann.pump()
        order.append(sky.launched[-1].text)
    assert order == ["urgent-1", "urgent-2", "normal"]


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
