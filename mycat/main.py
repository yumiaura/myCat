#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pixel Cat (from 2-frame PNG sprite), PySide6 transparent overlay
- Loads a PNG sprite with TWO frames placed side-by-side (open eyes, closed eyes).
- Shows a frameless, draggable, always-on-top transparent window.
- Blink timing: 5 seconds open, 1 second closed, repeating.
- Right click → Quit.
- Optional: --image PATH (if omitted, uses packaged mycat/images/cat.png)
           --size N (width of one frame; default from $CAT_SIZE or 160)
           --pos X Y (start position, else restored from config)

Dependencies:
pip install PySide6
"""

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path
from importlib.resources import files, as_file
from typing import Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

# Config paths
CFG_DIR = Path.home() / ".config" / "pixelcat"
CFG_FILE = CFG_DIR / "config.json"


def slice_sprite_to_pixmaps(
    sprite_path: str, target_width: int
) -> Tuple[QtGui.QPixmap, QtGui.QPixmap]:
    """
    Load sprite PNG, split into two halves, scale to target_width while keeping aspect.
    The left half is the 'open eyes' frame, right half is the 'closed eyes' frame.
    """
    if not os.path.exists(sprite_path):
        raise FileNotFoundError(f"Sprite not found: {sprite_path}")
    
    sprite = QtGui.QPixmap(sprite_path)
    if sprite.isNull():
        raise ValueError(f"Failed to load sprite: {sprite_path}")
    
    sprite_width = sprite.width()
    sprite_height = sprite.height()
    frame_width = sprite_width // 2
    frame_height = sprite_height

    # Crop first (open), second (closed)
    open_pixmap = sprite.copy(0, 0, frame_width, frame_height)
    closed_pixmap = sprite.copy(frame_width, 0, sprite_width - frame_width, frame_height)

    # Scale if needed
    if target_width <= 0:
        target_width = frame_width
    
    if target_width != frame_width:
        scale = target_width / frame_width
        target_height = max(1, int(round(frame_height * scale)))
        # Use Qt.SmoothTransformation for better quality or Qt.FastTransformation for speed
        transform_mode = QtCore.Qt.TransformationMode.FastTransformation
        open_pixmap = open_pixmap.scaled(
            target_width, target_height, 
            QtCore.Qt.AspectRatioMode.IgnoreAspectRatio, 
            transform_mode
        )
        closed_pixmap = closed_pixmap.scaled(
            target_width, target_height,
            QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
            transform_mode
        )
    
    return open_pixmap, closed_pixmap


def load_packaged_pixmaps(target_width: int) -> Tuple[QtGui.QPixmap, QtGui.QPixmap]:
    """
    Load the bundled sprite from mycat/images/cat.png inside the installed package.
    """
    resource = files("mycat").joinpath("images/cat.png")
    with as_file(resource) as sprite_path:
        return slice_sprite_to_pixmaps(str(sprite_path), target_width)


def load_config() -> dict:
    """Load configuration from file."""
    try:
        if CFG_FILE.exists():
            return json.loads(CFG_FILE.read_text())
        return {}
    except Exception as e:
        print(f"Config load error: {e}")
        return {}


def save_config(config: dict) -> None:
    """Save configuration to file."""
    try:
        CFG_DIR.mkdir(parents=True, exist_ok=True)
        CFG_FILE.write_text(json.dumps(config, indent=2))
    except Exception as e:
        print(f"Config save error: {e}")


class PixelCatWindow(QtWidgets.QWidget):
    """Main cat window widget with blinking animation and dragging."""
    
    def __init__(
        self,
        open_pixmap: QtGui.QPixmap,
        closed_pixmap: QtGui.QPixmap,
        args: argparse.Namespace,
    ) -> None:
        # Window flags for transparent, frameless, always-on-top window
        flags = (
            QtCore.Qt.WindowType.FramelessWindowHint |
            QtCore.Qt.WindowType.Tool |
            QtCore.Qt.WindowType.WindowStaysOnTopHint
        )
        super().__init__(None, flags)
        
        # Setup transparency
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("Pixel Cat")
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        
        # Store pixmaps and timing
        self.open_pixmap = open_pixmap
        self.closed_pixmap = closed_pixmap
        self.current_pixmap = self.open_pixmap
        self.open_sec = max(0.05, float(args.open_sec))
        self.closed_sec = max(0.05, float(args.closed_sec))
        
        # Animation state
        self.state = "open"
        self.next_change = time.time() + self.open_sec
        
        # Dragging state
        self.dragging = False
        self.drag_start_pos = QtCore.QPoint()
        
        # Set window size to pixmap size
        pixmap_size = self.current_pixmap.size()
        self.resize(pixmap_size)
        
        # Position window
        if args.pos:
            self.move(args.pos[0], args.pos[1])
        else:
            self._load_position()
        
        # Setup context menu
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        
        # Setup animation timer (60 FPS)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(16)  # ~60 FPS
    
    def _load_position(self) -> None:
        """Load window position from config."""
        config = load_config()
        x = config.get("x", 100)
        y = config.get("y", 100)
        self.move(x, y)
    
    def _save_position(self) -> None:
        """Save current window position to config."""
        pos = self.pos()
        config = {"x": pos.x(), "y": pos.y()}
        save_config(config)
    
    def _show_context_menu(self, pos: QtCore.QPoint) -> None:
        """Show context menu at the given position."""
        menu = QtWidgets.QMenu(self)
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(QtWidgets.QApplication.quit)
        menu.exec(self.mapToGlobal(pos))
    
    def _on_tick(self) -> None:
        """Called by timer to update animation state."""
        now = time.time()
        if now >= self.next_change:
            if self.state == "open":
                self.state = "closed"
                self.current_pixmap = self.closed_pixmap
                self.next_change = now + self.closed_sec
            else:
                self.state = "open"
                self.current_pixmap = self.open_pixmap
                self.next_change = now + self.open_sec
            self.update()
    
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """Paint the current pixmap."""
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        
        # Draw pixmap centered in widget
        widget_rect = self.rect()
        pixmap_rect = self.current_pixmap.rect()
        x = (widget_rect.width() - pixmap_rect.width()) // 2
        y = (widget_rect.height() - pixmap_rect.height()) // 2
        painter.drawPixmap(x, y, self.current_pixmap)
    
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse press for dragging."""
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
    
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse move for dragging."""
        if self.dragging and event.buttons() == QtCore.Qt.MouseButton.LeftButton:
            new_pos = event.globalPosition().toPoint() - self.drag_start_pos
            self.move(new_pos)
    
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse release to stop dragging and save position."""
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self.dragging:
            self.dragging = False
            self._save_position()

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Blinking pixel cat overlay (two-frame PNG sprite)."
    )
    parser.add_argument(
        "--image", "-i",
        type=str,
        default=None,  # use packaged resource by default
        help="Path to PNG sprite with two frames side-by-side "
             "(default: packaged mycat/images/cat.png)",
    )
    env_size = os.environ.get("CAT_SIZE")
    default_size = int(env_size) if (env_size and env_size.isdigit()) else 160
    parser.add_argument(
        "--size", "-s",
        type=int,
        default=default_size,
        help="Target size (width of one frame) in pixels "
             "(default from env CAT_SIZE or 160)",
    )
    parser.add_argument(
        "--pos",
        nargs=2,
        type=int,
        metavar=("X", "Y"),
        help="Start position (overrides remembered position)",
    )
    parser.add_argument(
        "--open",
        type=float,
        default=5.0,
        dest="open_sec",
        help="Seconds with eyes open (default: 5.0)",
    )
    parser.add_argument(
        "--closed",
        type=float,
        default=1.0,
        dest="closed_sec",
        help="Seconds with eyes closed (default: 1.0)",
    )
    return parser.parse_args()

def main() -> None:
    """Main entry point."""
    args = parse_args()
    
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        """Handle Ctrl+C gracefully."""
        print("\nReceived interrupt signal, shutting down...")
        app.quit()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Allow signal handling during Qt event loop
    timer = QtCore.QTimer()
    timer.timeout.connect(lambda: None)  # Allow Python signal handlers to run
    timer.start(100)  # Check every 100ms
    
    # Load sprite pixmaps
    try:
        if args.image:
            sprite_path = Path(args.image).expanduser()
            if not sprite_path.exists():
                print(f"File not found: {sprite_path}")
                sys.exit(1)
            open_pixmap, closed_pixmap = slice_sprite_to_pixmaps(str(sprite_path), args.size)
        else:
            open_pixmap, closed_pixmap = load_packaged_pixmaps(args.size)
    except Exception as e:
        print(f"Error loading sprite: {e}")
        sys.exit(2)
    
    # Create and show window
    window = PixelCatWindow(open_pixmap, closed_pixmap, args)
    window.show()
    
    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
        sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
        sys.exit(0)
