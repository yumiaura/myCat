#!/usr/bin/env python3
"""LOCAL demo — procedural moods (roadmap vertical B, phase 1).

Makes the cat feel ALIVE by *animating the existing sprite with code* — no new
art and no numbers on screen. System load is expressed as the cat's mood, not as
a percentage.

Moods (all procedural transforms of the one sprite):
  sleep   slow breathing, dimmed, rising "z z Z"
  yawn    a stretch, used as the wake/sleep transition
  idle    gentle breathing
  play    bouncy hops + squash — triggered by clicking the cat
  aggro   a short random shake (personality)
  stress  constant jitter + puffed-up scale + red tint — when the box is busy

Throwaway prototype, run it directly (not wired into the app, not pushed):
    python demo/live_cat_demo.py
    python demo/live_cat_demo.py --mood stress   # force one mood (for testing)

Phase-2 (separate): real per-mood sprites (sleep curl, fur-on-end, presenting
its back to be petted) generated via the ComfyUI pipeline — those need actual
new poses that transforms can't fake.
"""

import argparse
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

import mycat.main as cat  # noqa: E402

PAD = 0.45            # transparent margin (fraction of sprite) for transform headroom
NAP_AFTER = 18.0      # seconds idle + calm before dozing off
PLAY_SECS = 1.6
AGGRO_SECS = 0.8
YAWN_SECS = 1.1
RED_TINT = QtGui.QColor(210, 40, 30, 70)


def read_cpu_idle_total():
    """(idle, total) jiffies from /proc/stat, or None off Linux. Internal signal."""
    try:
        with open("/proc/stat") as handle:
            fields = handle.readline().split()[1:]
    except OSError:
        return None
    nums = [float(value) for value in fields]
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0.0)
    return idle, sum(nums)


def render_frame(base, size, *, dx=0.0, dy=0.0, sx=1.0, sy=1.0, dim=0.0, tint=None, zzz=None):
    """Draw the sprite onto a fixed-size canvas with a foot-anchored transform.

    Every frame is the same canvas size, so the window never re-centres and the
    no-compositor shape-mask (rebuilt from the pixmap each paint) stays aligned.
    """
    width, height = size
    out = QtGui.QPixmap(width, height)
    out.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(out)
    painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, False)

    # Anchor at the sprite's bottom-centre so squash/stretch grows from the feet.
    painter.translate(width / 2 + dx, (height + base.height()) / 2 + dy)
    painter.scale(sx, sy)
    painter.drawPixmap(int(-base.width() / 2), int(-base.height()), base)
    painter.resetTransform()

    if dim > 0:
        painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceAtop)
        painter.fillRect(out.rect(), QtGui.QColor(0, 0, 0, int(dim * 255)))
    if tint is not None:
        painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceAtop)
        painter.fillRect(out.rect(), tint)

    painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)
    if zzz is not None:
        draw_zzz(painter, width, height, base, zzz)
    painter.end()
    return out


def draw_zzz(painter, width, height, base, phase):
    """Three rising, fading 'z' glyphs above the head."""
    top = (height - base.height()) / 2
    head_x = width / 2 + base.width() * 0.18
    painter.setPen(QtGui.QColor(120, 150, 220))
    for index in range(3):
        local = (phase + index / 3.0) % 1.0
        font = QtGui.QFont()
        font.setBold(True)
        font.setPixelSize(int(9 + index * 4))
        painter.setFont(font)
        color = QtGui.QColor(120, 150, 220, int(255 * (1.0 - local)))
        painter.setPen(color)
        painter.drawText(
            int(head_x + index * 7 + local * 6),
            int(top - 2 - local * 22),
            "z" if index < 2 else "Z",
        )


class MoodCat(QtCore.QObject):
    """Procedural mood machine driving window.current_pixmap."""

    def __init__(self, window, base, canvas_size, forced=None):
        super().__init__(window)
        self.window = window
        self.base = base
        self.size = canvas_size
        self.forced = forced

        self.clock = QtCore.QElapsedTimer()
        self.clock.start()
        self.prev_cpu = read_cpu_idle_total()
        self.busy = 0.0
        self.mood = "idle"
        self.mood_since = 0.0
        self.last_interaction = self.now()

        window.installEventFilter(self)

        self.brain = QtCore.QTimer(self)
        self.brain.timeout.connect(self.think)
        self.brain.start(1000)

        self.render_timer = QtCore.QTimer(self)
        self.render_timer.timeout.connect(self.render)
        self.render_timer.start(40)  # ~25 fps

    def now(self):
        return self.clock.elapsed() / 1000.0

    def set_mood(self, mood):
        if mood != self.mood:
            self.mood = mood
            self.mood_since = self.now()
            print(f"[live-cat] {mood}", flush=True)

    def sample_busy(self):
        current = read_cpu_idle_total()
        cpu = self.busy
        if current and self.prev_cpu:
            d_idle = current[0] - self.prev_cpu[0]
            d_total = current[1] - self.prev_cpu[1]
            if d_total > 0:
                cpu = max(0.0, min(100.0, (1.0 - d_idle / d_total) * 100.0))
        self.prev_cpu = current
        # Smooth so a one-second spike doesn't whiplash the cat.
        self.busy = self.busy * 0.6 + cpu * 0.4

    def eventFilter(self, obj, event):
        if obj is self.window and event.type() == QtCore.QEvent.Type.MouseButtonPress:
            self.last_interaction = self.now()
            self.set_mood("play")
        return False

    def think(self):
        if self.forced:
            return
        self.sample_busy()
        age = self.now() - self.mood_since
        idle_for = self.now() - self.last_interaction

        # One-shots run to completion.
        if self.mood == "play" and age < PLAY_SECS:
            return
        if self.mood == "aggro" and age < AGGRO_SECS:
            return
        if self.mood == "yawn" and age < YAWN_SECS:
            return

        if self.busy >= 30.0:
            self.set_mood("stress")
        elif self.mood == "yawn":
            self.set_mood("sleep")
        elif idle_for > NAP_AFTER and self.busy < 12.0:
            self.set_mood("sleep" if self.mood == "sleep" else "yawn")
        elif random.random() < 0.04:
            self.set_mood("aggro")
        else:
            self.set_mood("idle")

    def params(self):
        time = self.now()
        age = time - self.mood_since
        mood = self.mood
        if mood == "sleep":
            breathe = math.sin(time * 1.4)
            return {"sy": 1.0 + 0.05 * breathe, "sx": 1.0 - 0.02 * breathe,
                    "dim": 0.28, "zzz": (time * 0.35) % 1.0}
        if mood == "yawn":
            ease = math.sin(min(1.0, age / YAWN_SECS) * math.pi)
            return {"sy": 1.0 + 0.20 * ease, "sx": 1.0 - 0.08 * ease, "dy": -4 * ease}
        if mood == "play":
            hop = abs(math.sin(time * 9.0))
            return {"dy": -22 * hop, "sy": 1.0 + 0.10 * hop, "sx": 1.0 - 0.06 * hop}
        if mood == "aggro":
            return {"dx": random.uniform(-6, 6), "sy": 1.06, "dy": -2}
        if mood == "stress":
            jitter = random.uniform(-3, 3)
            puff = 0.08 + 0.02 * math.sin(time * 20)
            return {"dx": jitter, "dy": random.uniform(-2, 2),
                    "sx": 1.0 + puff, "sy": 1.0 + puff, "tint": RED_TINT}
        breathe = math.sin(time * 2.1)  # idle
        return {"sy": 1.0 + 0.025 * breathe, "sx": 1.0 - 0.012 * breathe}

    def render(self):
        frame = render_frame(self.base, self.size, **self.params())
        self.window.current_pixmap = frame
        self.window.update()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mood", choices=["sleep", "yawn", "idle", "play", "aggro", "stress"])
    args = parser.parse_args()

    app = QtWidgets.QApplication([])
    available = cat.scan_images_directory()
    base, movie, name, data = cat.load_packaged_images(None, cat.load_image_from_ini() or "cat")

    # Padded canvas so squash/stretch/jitter have headroom and never get clipped.
    pad_w = int(base.width() * PAD)
    pad_h = int(base.height() * PAD)
    canvas_size = (base.width() + 2 * pad_w, base.height() + 2 * pad_h)
    canvas = QtGui.QPixmap(*canvas_size)
    canvas.fill(QtCore.Qt.GlobalColor.transparent)
    holder = QtGui.QPainter(canvas)
    holder.drawPixmap(pad_w, pad_h, base)
    holder.end()

    window = cat.PixelCatWindow(canvas, movie, 9999.0, name, available, data)
    # We drive the pixmap ourselves — neutralise the window's own GIF auto-play.
    window._start_animation = lambda: None
    window.show()

    MoodCat(window, base, canvas_size, forced=args.mood)
    if args.mood:
        print(f"[live-cat] forced mood: {args.mood}", flush=True)
    print("[live-cat] running — click the cat to play; leave it to doze; load the "
          "CPU to stress it. Right-click → Quit.", flush=True)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
