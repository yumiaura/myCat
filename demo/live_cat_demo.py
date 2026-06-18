#!/usr/bin/env python3
"""LOCAL demo — the cat made to feel ALIVE (roadmap vertical B, prototype).

It reuses the real mycat window and layers ambient liveliness on top, without
touching the app:

- idle ambient motion: the cat moves on its own at a varied cadence,
- CPU-reactive energy: a busy machine makes a busier cat (native /proc/stat),
- reacts to being clicked/grabbed — it perks up immediately,
- naps after a stretch with no interaction, wakes on activity or load.

A small pill above the cat narrates its current mood + CPU. This is a throwaway
prototype to *see* the idea; it is not wired into the app and not pushed.

Run it directly:
    python demo/live_cat_demo.py
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6 import QtCore, QtWidgets  # noqa: E402

import mycat.main as cat  # noqa: E402

MOOD_FACE = {"excited": "🙀", "lively": "😺", "calm": "🐱", "napping": "😴"}


def read_cpu_idle_total():
    """Return (idle, total) jiffies from /proc/stat, or None off Linux."""
    try:
        with open("/proc/stat") as handle:
            fields = handle.readline().split()[1:]
    except OSError:
        return None
    nums = [float(value) for value in fields]
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0.0)  # idle + iowait
    return idle, sum(nums)


class MoodHud(QtWidgets.QLabel):
    """A small solid pill that floats above the cat and shows its mood.

    Solid background on purpose: a translucent pill would render as a black box
    on X11 without a compositor, so the demo stays crisp everywhere.
    """

    def __init__(self):
        super().__init__(
            None,
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.Tool
            | QtCore.Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet(
            "QLabel { background: #2b2b2b; color: #ffd34d;"
            " padding: 4px 10px; font-size: 12px; font-weight: bold; }"
        )
        self.setText("…")

    def show_above(self, target: QtWidgets.QWidget) -> None:
        self.adjustSize()
        geo = target.geometry()
        self.move(int(geo.center().x() - self.width() / 2), max(0, geo.y() - self.height() - 6))
        self.show()
        self.raise_()


class LiveCat(QtCore.QObject):
    """Drives the cat's liveliness on a single 1 Hz tick."""

    NAP_AFTER = 30.0  # seconds with no interaction (and low CPU) -> nap

    def __init__(self, window: QtWidgets.QWidget, hud: MoodHud):
        super().__init__(window)
        self.window = window
        self.hud = hud
        self.clock = QtCore.QElapsedTimer()
        self.clock.start()
        self.prev_cpu = read_cpu_idle_total()
        self.cpu = 0.0
        self.mood = ""
        self.last_interaction = self.now()
        self.next_replay_at = self.now() + 4.0

        window.installEventFilter(self)
        self.tick_timer = QtCore.QTimer(self)
        self.tick_timer.timeout.connect(self.tick)
        self.tick_timer.start(1000)

    def now(self) -> float:
        return self.clock.elapsed() / 1000.0

    def sample_cpu(self) -> None:
        current = read_cpu_idle_total()
        if current and self.prev_cpu:
            delta_idle = current[0] - self.prev_cpu[0]
            delta_total = current[1] - self.prev_cpu[1]
            if delta_total > 0:
                self.cpu = max(0.0, min(100.0, (1.0 - delta_idle / delta_total) * 100.0))
        self.prev_cpu = current

    def replay(self) -> None:
        """Make the cat do its thing once. No-op while a play is in progress."""
        if getattr(self.window, "state", "png") == "png":
            self.window._start_animation()

    def interval_for(self, napping: bool) -> float:
        if napping:
            return random.uniform(35.0, 50.0)
        # 0% CPU -> ~22s between spontaneous moves; 100% CPU -> ~2.5s.
        base = 22.0 - (self.cpu / 100.0) * 19.5
        return random.uniform(base * 0.7, base * 1.3)

    def set_mood(self, mood: str) -> None:
        if mood != self.mood:
            self.mood = mood
            print(f"[live-cat] mood -> {mood} (CPU {self.cpu:.0f}%)", flush=True)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.window and event.type() == QtCore.QEvent.Type.MouseButtonPress:
            self.last_interaction = self.now()
            self.set_mood("excited")
            self.replay()
            self.next_replay_at = self.now() + 1.5
        return False

    def tick(self) -> None:
        self.sample_cpu()
        idle_for = self.now() - self.last_interaction
        napping = idle_for > self.NAP_AFTER and self.cpu < 15.0

        if idle_for < 2.0:
            self.set_mood("excited")
        elif napping:
            self.set_mood("napping")
        else:
            # ~25% whole-system CPU ≈ one busy core on a typical desktop.
            self.set_mood("lively" if self.cpu >= 25.0 else "calm")

        if self.now() >= self.next_replay_at:
            self.replay()
            self.next_replay_at = self.now() + self.interval_for(napping)

        self.hud.setText(f"{MOOD_FACE[self.mood]} {self.mood}  ·  CPU {self.cpu:.0f}%")
        self.hud.show_above(self.window)


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    available = cat.scan_images_directory()
    png, movie, name, data = cat.load_packaged_images(None, cat.load_image_from_ini() or "cat")
    window = cat.PixelCatWindow(png, movie, 1.0, name, available, data)
    window.show()
    hud = MoodHud()
    LiveCat(window, hud)
    print(
        "[live-cat] running — click/grab the cat to excite it; run a CPU load "
        "to see it perk up; leave it alone to watch it nap. Ctrl+C to quit.",
        flush=True,
    )
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
