#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pixel Cat (from 2-frame PNG sprite), GTK transparent overlay for XFCE
- Loads a user PNG with TWO frames placed side-by-side (open eyes, closed eyes).
- Shows a frameless, draggable, always-on-top transparent window.
- Blink timing: 5 seconds open, 1 second closed, repeating.
- Right click → Quit.
- Optional: --image PATH (defaults to ./cat_sprite.png next to this script)
           --size N (scale long side to N px, default from $CAT_SIZE or 160)
           --pos X Y (start position, else restored from config)

Dependencies (Ubuntu/Debian):
sudo apt update
sudo apt install -y python3-gi gir1.2-gtk-3.0 gir1.2-gdkpixbuf-2.0 python3-gi-cairo

"""

import argparse
import json
import gi
import os
import sys
import time
from pathlib import Path

# Require versions before importing from gi.repository
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

import cairo
from gi.repository import Gdk
from gi.repository import GdkPixbuf
from gi.repository import GLib
from gi.repository import Gtk

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
CFG_DIR = Path.home() / ".config" / "pixelcat"
CFG_FILE = CFG_DIR / "config.json"
DEFAULT_SPRITE = SCRIPT_DIR / "images/cat.png"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Blinking pixel cat overlay (two-frame PNG sprite)."
    )
    p.add_argument(
        "--image",
        "-i",
        type=str,
        default=str(DEFAULT_SPRITE),
        help="Path to PNG sprite with two frames side-by-side (default: %(default)s)",
    )
    env_size = os.environ.get("CAT_SIZE")
    default_size = int(env_size) if (env_size and env_size.isdigit()) else 160
    p.add_argument(
        "--size",
        "-s",
        type=int,
        default=default_size,
        help=(
            "Target size (width of one frame) in pixels (default env CAT_SIZE or 160)"
        ),
    )
    p.add_argument(
        "--pos",
        nargs=2,
        type=int,
        metavar=("X", "Y"),
        help="Start position (overrides remembered position)",
    )
    p.add_argument(
        "--open",
        type=float,
        default=5.0,
        dest="open_sec",
        help="Seconds with eyes open (default: 5.0)",
    )
    p.add_argument(
        "--closed",
        type=float,
        default=1.0,
        dest="closed_sec",
        help="Seconds with eyes closed (default: 1.0)",
    )
    return p.parse_args()


def slice_sprite_to_pixbufs(
    sprite_path: str, target_width: int
) -> tuple[GdkPixbuf.Pixbuf, GdkPixbuf.Pixbuf]:
    """Load sprite PNG, split into two equal halves, scale to target_width keeping aspect."""
    if not os.path.exists(sprite_path):
        raise FileNotFoundError(f"Sprite not found: {sprite_path}")
    # Load whole sprite
    sprite = GdkPixbuf.Pixbuf.new_from_file(sprite_path)
    sw, sh = sprite.get_width(), sprite.get_height()
    if sw % 2 != 0:
        # If uneven, we still try: second frame assumed same width as first
        frame_w = sw // 2
    else:
        frame_w = sw // 2
    frame_h = sh

    # Crop first (open), second (closed)
    open_pb = GdkPixbuf.Pixbuf.new_subpixbuf(sprite, 0, 0, frame_w, frame_h)
    closed_pb = GdkPixbuf.Pixbuf.new_subpixbuf(
        sprite, frame_w, 0, sw - frame_w, frame_h
    )

    # Scale
    if target_width <= 0:
        target_width = frame_w
    scale = target_width / frame_w
    target_height = max(1, int(round(frame_h * scale)))
    interp = GdkPixbuf.InterpType.NEAREST  # preserve pixel look
    open_scaled = open_pb.scale_simple(target_width, target_height, interp)
    closed_scaled = closed_pb.scale_simple(target_width, target_height, interp)
    return open_scaled, closed_scaled


class PixelCatWindow(Gtk.Window):
    def __init__(
        self,
        open_pb: GdkPixbuf.Pixbuf,
        closed_pb: GdkPixbuf.Pixbuf,
        args: argparse.Namespace,
    ) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.stick()
        self.connect("draw", self.on_draw)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)
        else:
            print(
                "Hint: enable compositor in Xfce (Settings → Window Manager Tweaks → Compositor)."
            )

        # Input
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.connect("button-press-event", self.on_button_press)
        self.connect("button-release-event", self.on_button_release)
        self.connect("motion-notify-event", self.on_motion)

        # Menu
        self.menu = Gtk.Menu()
        mi_quit = Gtk.MenuItem.new_with_label("Quit")
        mi_quit.connect("activate", lambda *_: Gtk.main_quit())
        self.menu.append(mi_quit)
        self.menu.show_all()

        # Frames & timing
        self.open_pb = open_pb
        self.closed_pb = closed_pb
        self.current = self.open_pb
        self.open_sec = max(0.05, float(args.open_sec))
        self.closed_sec = max(0.05, float(args.closed_sec))
        self.state = "open"
        self.next_change = time.time() + self.open_sec

        # Size & position
        self.set_default_size(self.current.get_width(), self.current.get_height())
        if args.pos:
            x, y = args.pos
            self.move(int(x), int(y))
        else:
            self.load_pos()

        # Ticker (≈60 FPS)
        GLib.timeout_add(16, self.on_tick)

    def load_pos(self) -> None:
        try:
            if CFG_FILE.exists():
                data = json.loads(CFG_FILE.read_text())
                x, y = int(data.get("x", 100)), int(data.get("y", 100))
                self.move(x, y)
            else:
                self.move(100, 100)
        except Exception as e:
            print("Config load error:", e)
            self.move(100, 100)

    def save_pos(self) -> None:
        try:
            x, y = self.get_position()
            CFG_DIR.mkdir(parents=True, exist_ok=True)
            CFG_FILE.write_text(json.dumps({"x": x, "y": y}))
        except Exception as e:
            print("Config save error:", e)

    # Mouse
    def on_button_press(self, widget: Gtk.Widget, event: Gdk.EventButton) -> bool:
        if event.button == 1:
            self.dragging = True
            self.drag_origin = (int(event.x_root), int(event.y_root))
            self.window_pos_at_drag = self.get_position()
            return True
        if event.button == 3:
            self.menu.popup_at_pointer(event)
            return True
        return False

    def on_motion(self, widget: Gtk.Widget, event: Gdk.EventMotion) -> bool:
        if getattr(self, "dragging", False):
            dx = int(event.x_root) - self.drag_origin[0]
            dy = int(event.y_root) - self.drag_origin[1]
            self.move(self.window_pos_at_drag[0] + dx, self.window_pos_at_drag[1] + dy)
            return True
        return False

    def on_button_release(self, widget: Gtk.Widget, event: Gdk.EventButton) -> bool:
        if event.button == 1 and getattr(self, "dragging", False):
            self.dragging = False
            self.save_pos()
            return True
        return False

    def on_tick(self) -> bool:
        now = time.time()
        if now >= self.next_change:
            if self.state == "open":
                self.state = "closed"
                self.current = self.closed_pb
                self.next_change = now + self.closed_sec
            else:
                self.state = "open"
                self.current = self.open_pb
                self.next_change = now + self.open_sec
            self.queue_draw()
        return True

    def on_draw(self, widget: Gtk.Widget, cr: cairo.Context) -> bool:
        # Clear with transparent
        cr.set_operator(cairo.Operator.SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.Operator.OVER)

        win_w = self.get_allocated_width()
        win_h = self.get_allocated_height()
        img_w = self.current.get_width()
        img_h = self.current.get_height()
        x = (win_w - img_w) // 2
        y = (win_h - img_h) // 2
        Gdk.cairo_set_source_pixbuf(cr, self.current, x, y)
        cr.paint()
        return False


def ensure_sprite_exists(sprite_path: Path) -> None:
    """Ensure sprite file exists; create parent directory if needed (no-op if present)."""
    # Copy bundled demo file if user didn't provide one (placeholder; intentionally a no-op here)
    try:
        if not sprite_path.exists():
            sprite_path.parent.mkdir(parents=True, exist_ok=True)
            # If running from a sandbox, a sample could be copied here.
            raise FileNotFoundError
    except Exception:
        pass


def main() -> None:
    args = parse_args()
    sprite_path = Path(args.image).expanduser()
    if not sprite_path.exists():
        print(f"File not found: {sprite_path}")
        sys.exit(1)
    try:
        open_pb, closed_pb = slice_sprite_to_pixbufs(str(sprite_path), args.size)
    except Exception as e:
        print("Error loading sprite:", e)
        sys.exit(2)
    win = PixelCatWindow(open_pb, closed_pb, args)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
