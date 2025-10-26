#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pixel Cat with PNG/GIF animation, PySide6 transparent overlay
- Shows cat.png for 5 seconds, then plays cat.gif once, then back to cat.png
- Shows a frameless, draggable, always-on-top transparent window.
- Right click → Quit.

Dependencies:
pip install PySide6
"""

import argparse
import configparser
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Config paths
CFG_DIR = Path.home() / ".config" / "pixelcat"
CFG_FILE = CFG_DIR / "config.ini"

# GIF animation settings
GIF_FPS = 1  # Frames per second for GIF playback (1.0 = 1 frame per second)

# Image scaling settings
MAX_IMAGE_WIDTH = 500  # Maximum width for images in pixels (images will be scaled down if larger)
PNG_TIME = 5.0  # Seconds to show PNG before playing GIF


def scan_images_directory() -> list[str]:
    """
    Scan the images/ directory for PNG/GIF pairs.
    Returns a list of base names (without extension) for which both PNG and GIF exist.
    """
    script_dir = Path(__file__).resolve().parent
    images_dir = script_dir / "images"
    
    if not images_dir.exists():
        return []
    
    found_pairs = []
    
    # Get all PNG files
    png_files = set(p.stem for p in images_dir.glob("*.png"))
    
    # Get all GIF files
    gif_files = set(p.stem for p in images_dir.glob("*.gif"))
    
    # Find pairs (files that have both PNG and GIF)
    found_pairs = sorted(png_files & gif_files)
    
    return found_pairs


def scale_pixmap_if_needed(pixmap: QtGui.QPixmap, max_width: int) -> QtGui.QPixmap:
    """
    Scale pixmap down if it's wider than max_width, maintaining aspect ratio.
    Returns the scaled pixmap (or original if no scaling needed).
    """
    original_width = pixmap.width()
    if original_width <= max_width:
        return pixmap
    
    # Calculate new size maintaining aspect ratio
    scale_factor = max_width / original_width
    new_width = max_width
    new_height = int(pixmap.height() * scale_factor)
    
    # Scale the pixmap
    return pixmap.scaled(
        new_width, new_height,
        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        QtCore.Qt.TransformationMode.SmoothTransformation
    )


def load_packaged_images(image_path: Optional[str] = None, default_image: Optional[str] = None) -> tuple[QtGui.QPixmap, QtGui.QMovie, str]:
    """
    Load PNG and GIF from images/ directory relative to the script.
    If image_path is provided, use it as the base for both PNG and GIF.
    Returns: (png_pixmap, gif_movie, base_name)
    """
    script_dir = Path(__file__).resolve().parent
    
    if image_path:
        # User provided image path
        image_file = Path(image_path)
        if image_file.exists():
            # Use the provided path
            png_path = image_file
            # Derive GIF path from PNG path
            gif_path = image_file.with_suffix('.gif')
            base_name = image_file.stem
        else:
            raise FileNotFoundError(f"Image not found: {image_file}")
    else:
        # Use default_image if provided, otherwise default to "cat"
        if default_image:
            base_name = default_image
        else:
            base_name = "cat"
        
        png_path = script_dir / "images" / f"{base_name}.png"
        gif_path = script_dir / "images" / f"{base_name}.gif"
    
    if not png_path.exists():
        raise FileNotFoundError(f"PNG not found: {png_path}")
    if not gif_path.exists():
        raise FileNotFoundError(f"GIF not found: {gif_path}")
    
    pixmap = QtGui.QPixmap(str(png_path))
    if pixmap.isNull():
        raise ValueError(f"Failed to load PNG: {png_path}")
    
    # Scale down if needed
    original_size = pixmap.size()
    pixmap = scale_pixmap_if_needed(pixmap, MAX_IMAGE_WIDTH)
    if original_size != pixmap.size():
        logger.info(f"Resized {Path(png_path).name}: {original_size.width()}x{original_size.height()} -> {pixmap.width()}x{pixmap.height()}")
    
    movie = QtGui.QMovie(str(gif_path))
    # Scale GIF to same size as PNG
    movie.setScaledSize(pixmap.size())
    
    return pixmap, movie, base_name


def load_config() -> dict:
    """Load configuration from INI file."""
    config_data = {'x': 100, 'y': 100}
    
    if not CFG_FILE.exists():
        return config_data
    
    try:
        config = configparser.ConfigParser()
        config.read(CFG_FILE)
        
        if 'window' in config:
            if 'x' in config['window']:
                config_data['x'] = int(config['window']['x'])
            if 'y' in config['window']:
                config_data['y'] = int(config['window']['y'])
    except Exception as e:
        logger.error(f"Config load error: {e}")
    
    return config_data


def save_config(config: dict) -> None:
    """Save configuration to INI file."""
    try:
        CFG_DIR.mkdir(parents=True, exist_ok=True)
        
        # Read existing config if it exists
        file_config = configparser.ConfigParser()
        if CFG_FILE.exists():
            file_config.read(CFG_FILE)
        
        # Ensure [window] section exists
        if 'window' not in file_config:
            file_config.add_section('window')
        
        # Update window position if provided
        if 'x' in config:
            file_config['window']['x'] = str(config['x'])
        if 'y' in config:
            file_config['window']['y'] = str(config['y'])
        
        # Write to file
        with open(CFG_FILE, 'w') as f:
            file_config.write(f)
    except Exception as e:
        logger.error(f"Config save error: {e}")


def load_image_from_ini() -> Optional[str]:
    """Load default image setting from INI file."""
    if not CFG_FILE.exists():
        logger.info(f"INI config not found, using default: cat")
        return None
    
    try:
        config = configparser.ConfigParser()
        config.read(CFG_FILE)
        
        if 'settings' in config and 'default_image' in config['settings']:
            image_name = config['settings']['default_image']
            logger.info(f"Loaded image from INI: {image_name}")
            return image_name
        else:
            logger.info(f"INI config exists but no default_image setting found, using default: cat")
            return None
    except Exception as e:
        logger.error(f"Error reading INI file: {e}, using default: cat")
        return None


def save_image_to_ini(image_name: str) -> None:
    """Save current image setting to INI file."""
    try:
        CFG_DIR.mkdir(parents=True, exist_ok=True)
        
        config = configparser.ConfigParser()
        
        # Read existing config if it exists
        if CFG_FILE.exists():
            config.read(CFG_FILE)
        
        # Ensure [settings] section exists
        if 'settings' not in config:
            config.add_section('settings')
        
        # Set the default_image value
        config['settings']['default_image'] = image_name
        
        # Write to file
        with open(CFG_FILE, 'w') as f:
            config.write(f)
        
        logger.info(f"Saved image setting to INI: {image_name}")
    except Exception as e:
        logger.error(f"Error saving to INI file: {e}")


class PixelCatWindow(QtWidgets.QWidget):
    """Main cat window widget with PNG/GIF animation and dragging."""
    
    def __init__(
        self,
        png_pixmap: QtGui.QPixmap,
        gif_movie: QtGui.QMovie,
        wait_time: float,
        file_name: str = "cat",
        available_images: list[str] = None,
    ) -> None:
        platform_name = ""
        app_instance = QtWidgets.QApplication.instance()
        if app_instance is not None:
            platform_name = (app_instance.platformName() or "").lower()
        
        # Window flags for transparent, frameless, always-on-top window
        flags = (
            QtCore.Qt.WindowType.FramelessWindowHint |
            QtCore.Qt.WindowType.Tool
        )
        if platform_name != "offscreen":
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        
        # Setup transparency
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("Pixel Cat")
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        
        # Store images
        self.png_pixmap = png_pixmap
        self.gif_movie = gif_movie
        self.current_pixmap = self.png_pixmap
        self.wait_time = wait_time
        self.file_name = file_name
        self.available_images = available_images or []
        
        # Animation state: 'png' -> show PNG, 'gif' -> play GIF
        self.state = 'png'
        self.next_change = time.time() + self.wait_time
        
        # Setup GIF movie - play once (no looping)
        self.gif_movie.setCacheMode(QtGui.QMovie.CacheMode.CacheAll)
        # Set speed to normal (100%) - uses native GIF frame delays
        self.gif_movie.setSpeed(100)
        
        # Track if we need to manually stop after one loop
        self.gif_played_once = False
        
        # Log GIF info
        frame_count = self.gif_movie.frameCount()
        gif_size = self.gif_movie.scaledSize()
        logger.info(f"Playing {self.file_name}.gif {gif_size.width()}x{gif_size.height()} ({frame_count} frames using native GIF timing)")
        
        # Setup GIF movie callbacks
        self.gif_movie.frameChanged.connect(self._on_gif_frame_changed)
        self.gif_movie.finished.connect(self._on_gif_finished)
        
        # Dragging state
        self.dragging = False
        self.drag_start_pos = QtCore.QPoint()
        
        # Set window size to pixmap size
        pixmap_size = self.current_pixmap.size()
        self.resize(pixmap_size)
        
        # Position window - defaults to top-left area
        self._load_position()
        
        # Setup context menu
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        
        # Setup animation timer (60 FPS)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(16)  # ~60 FPS
        
        # Save current image to INI on startup
        save_image_to_ini(self.file_name)
    
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
    
    def _load_image(self, image_name: str) -> None:
        """Load a different image pair."""
        try:
            png_path = Path(__file__).resolve().parent / "images" / f"{image_name}.png"
            gif_path = Path(__file__).resolve().parent / "images" / f"{image_name}.gif"
            
            # Load new pixmap
            new_pixmap = QtGui.QPixmap(str(png_path))
            if new_pixmap.isNull():
                logger.error(f"Failed to load {image_name}.png")
                return
            
            # Scale if needed
            original_size = new_pixmap.size()
            new_pixmap = scale_pixmap_if_needed(new_pixmap, MAX_IMAGE_WIDTH)
            if original_size != new_pixmap.size():
                logger.info(f"Resized {image_name}.png: {original_size.width()}x{original_size.height()} -> {new_pixmap.width()}x{new_pixmap.height()}")
            
            # Load new movie
            new_movie = QtGui.QMovie(str(gif_path))
            new_movie.setScaledSize(new_pixmap.size())
            new_movie.setCacheMode(QtGui.QMovie.CacheMode.CacheAll)
            new_movie.setSpeed(100)
            
            # Update current images
            self.png_pixmap = new_pixmap
            self.gif_movie = new_movie
            self.file_name = image_name
            
            # Reset to PNG state
            self.current_pixmap = self.png_pixmap
            self.state = 'png'
            self.gif_played_once = False
            self.next_change = time.time() + self.wait_time
            
            # Resize window
            self.resize(self.png_pixmap.size())
            
            # Reconnect movie callbacks
            self.gif_movie.frameChanged.connect(self._on_gif_frame_changed)
            self.gif_movie.finished.connect(self._on_gif_finished)
            
            # Save to INI
            save_image_to_ini(image_name)
            
            logger.info(f"Switched to {image_name}.png {self.png_pixmap.width()}x{self.png_pixmap.height()}")
            self.update()
            
        except Exception as e:
            logger.error(f"Error loading {image_name}: {e}")
    
    def _show_context_menu(self, pos: QtCore.QPoint) -> None:
        """Show context menu at the given position."""
        menu = QtWidgets.QMenu(self)
        
        # Add Images submenu if we have available images
        if len(self.available_images) > 0:
            images_menu = menu.addMenu("Images")
            for img_name in self.available_images:
                action = images_menu.addAction(img_name)
                # Mark current image with checkmark
                if img_name == self.file_name:
                    action.setCheckable(True)
                    action.setChecked(True)
                # Connect action to load image
                action.triggered.connect(lambda checked, name=img_name: self._load_image(name))
        
        # Add separator if we have both menu and quit
        if len(self.available_images) > 0:
            menu.addSeparator()
        
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(QtWidgets.QApplication.quit)
        menu.exec(self.mapToGlobal(pos))
    
    def _on_tick(self) -> None:
        """Called by timer to check if need to switch from PNG to GIF."""
        if self.state == 'png':
            now = time.time()
            if now >= self.next_change:
                # Time to show GIF - reset and play once
                gif_size = self.gif_movie.scaledSize()
                logger.info(f"Playing {self.file_name}.gif {gif_size.width()}x{gif_size.height()}")
                self.state = 'gif'
                self.gif_played_once = False
                # Immediately show first frame before starting animation
                self.gif_movie.jumpToFrame(0)
                first_frame = self.gif_movie.currentPixmap()
                if not first_frame.isNull():
                    self.current_pixmap = first_frame
                    if self.width() != first_frame.width() or self.height() != first_frame.height():
                        self.resize(first_frame.size())
                    self.update()
                self.gif_movie.start()
    
    def _on_gif_frame_changed(self, frame_number: int) -> None:
        """Called when GIF frame changes - update the display."""
        if self.state == 'gif':
            pixmap = self.gif_movie.currentPixmap()
            if not pixmap.isNull():
                self.current_pixmap = pixmap
                # Resize window to match GIF size
                if self.width() != pixmap.width() or self.height() != pixmap.height():
                    self.resize(pixmap.size())
                self.update()
            
            # Check if we've completed one full loop
            frame_count = self.gif_movie.frameCount()
            
            if not self.gif_played_once:
                # Stop at the first time we reach the last frame
                if frame_number == frame_count - 1:
                    self.gif_played_once = True
                    # Stop immediately and keep last frame visible
                    self.gif_movie.stop()
                    # Small delay before switching back to PNG
                    QtCore.QTimer.singleShot(100, self._stop_gif_after_loop)
    
    def _stop_gif_after_loop(self) -> None:
        """Stop GIF after it has played once."""
        if self.state == 'gif':
            self.gif_movie.stop()
            self.state = 'png'
            self.current_pixmap = self.png_pixmap
            # Resize window back to PNG size
            self.resize(self.png_pixmap.size())
            self.next_change = time.time() + self.wait_time
            logger.info(f"Playing {self.file_name}.png {self.png_pixmap.width()}x{self.png_pixmap.height()} for {self.wait_time:.1f}s")
            self.update()
    
    def _on_gif_finished(self) -> None:
        """Called when GIF animation finishes - go back to PNG."""
        # This is called when movie reaches end, but for looped GIFs this might not work
        # So we rely on _stop_gif_after_loop instead
        pass
    
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
        description="Pixel cat overlay with PNG/GIF animation."
    )
    parser.add_argument(
        "--image",
        type=str,
        default=None,
        help="Path to PNG file (default: images/cat.png). GIF will be derived from PNG path.",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=PNG_TIME,
        help="Seconds to show PNG before playing GIF (default: 5.0)",
    )
    parser.add_argument(
        "--pos",
        nargs=2,
        type=int,
        metavar=("X", "Y"),
        help="Start position (overrides remembered position)",
    )
    return parser.parse_args()

def main() -> None:
    """Main entry point."""
    args = parse_args()
    
    # Suppress Qt D-Bus warnings on Linux
    import os
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.theme.gnome=false")
    os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", "")
    os.environ.setdefault("QT_QPA_NO_NATIVE_MENUBAR", "1")
    
    # Suppress additional Qt warnings
    import warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    
    # Initialize Qt application with error handling
    try:
        app = QtWidgets.QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(True)
        platform_name = (app.platformName() or "").lower()
    except Exception as e:
        logger.error(f"Failed to initialize Qt application: {e}")
        sys.exit(1)
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        """Handle Ctrl+C gracefully."""
        logger.info("\nReceived interrupt signal, shutting down...")
        app.quit()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Allow signal handling during Qt event loop
    timer = QtCore.QTimer()
    timer.timeout.connect(lambda: None)  # Allow Python signal handlers to run
    timer.start(100)  # Check every 100ms
    
    # Scan for available image pairs
    available_images = scan_images_directory()
    logger.info(f"Found {len(available_images)} image pair(s): {', '.join(available_images)}")
    
    # Load default image from INI if no image path provided
    default_image = None
    if not args.image:
        default_image = load_image_from_ini()
        if default_image and default_image not in available_images:
            logger.warning(f"Image '{default_image}' from INI not found in available images, using default: cat")
            default_image = None
    
    # Load images
    try:
        png_pixmap, gif_movie, file_name = load_packaged_images(args.image, default_image)
        logger.info(f"Playing {file_name}.png {png_pixmap.width()}x{png_pixmap.height()} for {args.wait:.1f}s")
    except Exception as e:
        logger.error(f"Error loading images: {e}")
        sys.exit(2)
    
    # Create and show window
    window = PixelCatWindow(png_pixmap, gif_movie, args.wait, file_name, available_images)
    
    if args.pos:
        window.move(args.pos[0], args.pos[1])
    
    if platform_name == "offscreen":
        logger.info("Offscreen platform detected: skipping window display.")
        QtCore.QTimer.singleShot(0, app.quit)
    else:
        window.show()
    
    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        logger.info("\nShutdown requested by user")
        sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\nShutdown requested by user")
        sys.exit(0)

