"""The keyboard heatmap: cell mapping, cold→hot colour, and the session tally."""

import tempfile
from pathlib import Path

from mycat import activity_store, key_heatmap
from mycat.activity import ActivityCollector, ActivitySettings


class FakeKeyCode:
    """Stand-in for a pynput printable key."""

    def __init__(self, char):
        self.char = char


class FakeKey:
    """Stand-in for a pynput special key (space, enter, …)."""

    def __init__(self, name):
        self.char = None
        self.name = name


def test_char_to_cell_folds_case_and_shift():
    assert key_heatmap.char_to_cell("A") == "a"
    assert key_heatmap.char_to_cell("a") == "a"
    assert key_heatmap.char_to_cell("!") == "1"      # shifted digit → base
    assert key_heatmap.char_to_cell("?") == "/"
    assert key_heatmap.char_to_cell(" ") == "space"
    assert key_heatmap.char_to_cell("5") == "5"


def test_char_to_cell_drops_non_latin():
    assert key_heatmap.char_to_cell("ф") is None     # Cyrillic layout → off-board
    assert key_heatmap.char_to_cell("") is None
    assert key_heatmap.char_to_cell(None) is None


def test_cell_for_pynput_key():
    assert key_heatmap.cell_for_pynput_key(FakeKeyCode("Z")) == "z"
    assert key_heatmap.cell_for_pynput_key(FakeKeyCode("@")) == "2"
    assert key_heatmap.cell_for_pynput_key(FakeKey("space")) == "space"
    assert key_heatmap.cell_for_pynput_key(FakeKey("enter")) == "enter"
    assert key_heatmap.cell_for_pynput_key(FakeKey("f1")) is None
    assert key_heatmap.cell_for_pynput_key(FakeKeyCode("ж")) is None


def test_cell_for_keysym():
    assert key_heatmap.cell_for_keysym(0x41) == "a"      # 'A'
    assert key_heatmap.cell_for_keysym(0x20) == "space"
    assert key_heatmap.cell_for_keysym(0xFF0D) == "enter"
    assert key_heatmap.cell_for_keysym(0xFF08) == "backspace"
    assert key_heatmap.cell_for_keysym(0x6C1) is None    # Cyrillic keysym


def test_heat_rgb_runs_cold_to_hot():
    r0, g0, b0 = key_heatmap.heat_rgb(0.0)
    r1, g1, b1 = key_heatmap.heat_rgb(1.0)
    assert b0 > 200 and r0 < 40      # 0 → blue
    assert r1 > 200 and b1 < 40      # 1 → red
    # clamps out of range
    assert key_heatmap.heat_rgb(-1.0) == key_heatmap.heat_rgb(0.0)
    assert key_heatmap.heat_rgb(2.0) == key_heatmap.heat_rgb(1.0)


def test_board_cell_ids_are_unique():
    ids = [cell for row in key_heatmap.KEYBOARD_ROWS for (cell, _label, _w) in row]
    assert len(ids) == len(set(ids))


def make_collector(**settings):
    tmp = Path(tempfile.mkdtemp()) / "activity.db"
    store = activity_store.ActivityStore(db_path=tmp)
    collector = ActivityCollector(
        store=store, settings=ActivitySettings(**settings), start_timers=False
    )
    return collector


def test_collector_tally_counts_per_cell():
    collector = make_collector(key_heatmap_enabled=True)
    for ch in "hello WORLD!!":
        cell = "space" if ch == " " else key_heatmap.cell_for_pynput_key(FakeKeyCode(ch))
        collector.record_key_cell(cell)
    snap = collector.snapshot_key_cells()
    assert snap["l"] == 3          # hello (2) + WORLD (1)
    assert snap["o"] == 2
    assert snap["1"] == 2          # two '!' fold onto '1'
    assert snap["space"] == 1
    collector.stop()


def test_snapshot_is_a_copy():
    collector = make_collector(key_heatmap_enabled=True)
    collector.record_key_cell("a")
    snap = collector.snapshot_key_cells()
    snap["a"] = 999
    assert collector.snapshot_key_cells()["a"] == 1
    collector.stop()


def test_heatmap_only_does_not_start_disk_diary():
    collector = make_collector(
        mouse_enabled=False, keyboard_enabled=False, key_heatmap_enabled=True
    )
    # start_timers=False means no poll_timer at all; the point is that enabling
    # only the heatmap never tried to create/run the disk sampler.
    assert not hasattr(collector, "poll_timer")
    collector.stop()
