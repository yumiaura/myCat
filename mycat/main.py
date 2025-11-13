#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pixel Cat with GIF animation from ZIP archives, PySide6 transparent overlay
- Shows first frame of GIF from ZIP for 5 seconds, then plays GIF once, then back to first frame
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
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Optional

# Allow running both as `python -m mycat` and `python mycat/main.py`
if __package__:
    from . import llm
else:
    import importlib
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    llm = importlib.import_module("mycat.llm")

from PySide6 import QtCore, QtGui, QtWidgets

# Configure logging
LOGGING = {
    "handlers": [logging.StreamHandler()],
    "format": "%(asctime)s.%(msecs)03d [%(levelname)s]: (%(name)s) %(message)s",
    "level": logging.INFO,
    "datefmt": "%Y-%m-%d %H:%M:%S",
}
logging.basicConfig(**LOGGING)
logger = logging.getLogger(__name__)
logger.debug("LLM integration module path: %s", getattr(llm, "__file__", "builtin"))

# Config paths
CFG_DIR = Path.home() / ".config" / "mycat"
CFG_FILE = CFG_DIR / "config.ini"

# Image scaling settings
IMAGE_WIDTH_MAX = 300  # Maximum width for images in pixels (images will be scaled down if larger)
IMAGE_HEIGHT_MAX = 500  # Maximum height for images in pixels (images will be scaled down if larger)
STATIC_TIME = 5.0  # Seconds to show static first frame before playing GIF

# Window position settings
DEFAULT_POSITION_OFFSET_X = 10  # Offset from right edge of screen
DEFAULT_POSITION_OFFSET_Y = 10  # Offset from bottom edge of screen

# Global temp directory for extracted files
TEMP_DIR = None
STATIC_PNG_PATH = None
ANIMATION_GIF_PATH = None


def get_temp_dir() -> Path:
    """Get or create temp directory for extracted files."""
    global TEMP_DIR
    if TEMP_DIR is None:
        # Use tmpdir (which may be tmpfs on Linux) or fallback to system temp
        TEMP_DIR = Path(tempfile.gettempdir()) / "mycat"
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
    return TEMP_DIR


def scan_images_directory() -> list[str]:
    """
    Scan the images/ directory for ZIP archives containing GIF files.
    Returns a list of base names (without extension) for ZIP files.
    """
    script_dir = Path(__file__).resolve().parent
    images_dir = script_dir / "images"
    
    if not images_dir.exists():
        return []
    
    # Get all ZIP files
    zip_files = sorted(p.stem for p in images_dir.glob("*.zip"))
    
    return zip_files


def parse_gif_frame_delays(gif_path: Path) -> list[int]:
    """
    Parse GIF file using Pillow to extract frame delays.
    Returns list of delays in milliseconds.
    """
    try:
        try:
            from PIL import Image
        except ImportError:
            logger.warning("Pillow not available, falling back to manual parsing")
            return []
        
        img = Image.open(str(gif_path))
        if not hasattr(img, 'n_frames'):
            return []
        
        delays = []
        for i in range(img.n_frames):
            img.seek(i)
            # Get duration in milliseconds, default to 100ms if not specified
            duration_ms = img.info.get('duration', 100)
            delays.append(duration_ms)
        
        img.close()
        logger.info(f"Calculated GIF duration: {sum(delays)/1000:.2f}s from {len(delays)} frames")
        return delays
        
    except Exception as e:
        logger.debug(f"Could not parse GIF frame delays with Pillow: {e}")
        return []


def parse_gif_duration(gif_path: Path) -> float:
    """
    Parse GIF file to extract actual frame delays.
    Returns total duration in seconds.
    """
    # Try Pillow first
    duration = parse_gif_duration_pillow(gif_path)
    if duration > 0:
        return duration
    
    # Fallback to manual parsing
    try:
        import struct
        with open(gif_path, 'rb') as f:
            # Read GIF header (6 bytes: GIF89a or GIF87a)
            header = f.read(6)
            if not header.startswith(b'GIF'):
                return 0.0
            
            # Read logical screen descriptor (7 bytes)
            screen_desc = f.read(7)
            
            # Check if global color table exists
            packed = screen_desc[4]
            gct_exists = (packed & 0x80) >> 7
            gct_size = packed & 0x07
            
            # Skip global color table if present
            if gct_exists:
                gct_length = 3 * (2 << gct_size)
                f.read(gct_length)
            
            total_duration = 0.0
            
            # Parse image blocks
            while True:
                block_type = f.read(1)
                if not block_type:
                    break
                
                if block_type == b'\x21':  # Extension
                    ext_label = f.read(1)
                    if ext_label == b'\xF9':  # Graphic Control Extension
                        # Read block size
                        block_size = f.read(1)[0]
                        if block_size != 4:
                            # Skip this block
                            f.read(block_size)
                            f.read(1)  # Terminator
                            continue
                        
                        # Read GCE data: packed byte, delay (2 bytes little-endian), transparent color
                        packed_gce = f.read(1)[0]
                        delay_bytes = f.read(2)
                        delay = struct.unpack('<H', delay_bytes)[0]
                        transparent_color = f.read(1)[0]
                        
                        # Read block terminator
                        terminator = f.read(1)[0]
                        
                        # Only process valid GCE (terminator should be 0)
                        if terminator == 0:
                            # Duration in seconds (delay is in hundredths of a second)
                            if delay == 0:
                                # No explicit delay, use default animation speed
                                duration = 0.1  # 100ms default
                            else:
                                duration = delay / 100.0
                                # Clamp to reasonable minimum
                                if duration < 0.01:
                                    duration = 0.1
                            
                            total_duration += duration
                    elif ext_label == b'\xFF':  # Application Extension
                        # Skip it
                        ext_size = f.read(1)[0]
                        f.read(ext_size)
                        while True:
                            block_size = f.read(1)[0]
                            if block_size == 0:
                                break
                            f.read(block_size)
                    elif ext_label == b'\xFE':  # Comment Extension
                        # Skip it
                        while True:
                            block_size = f.read(1)[0]
                            if block_size == 0:
                                break
                            f.read(block_size)
                elif block_type == b'\x2C':  # Image descriptor
                    # Skip image descriptor (9 bytes)
                    f.read(9)
                    
                    # Read local color table if present
                    packed_id = f.read(1)[0]
                    lct_exists = (packed_id & 0x80) >> 7
                    lct_size = packed_id & 0x07
                    if lct_exists:
                        lct_length = 3 * (2 << lct_size)
                        f.read(lct_length)
                    
                    # Skip image data
                    while True:
                        block_size = f.read(1)[0]
                        if block_size == 0:
                            break
                        f.read(block_size)
                elif block_type == b'\x3B':  # Trailer
                    break
            
            logger.debug(f"Parsed GIF duration: {total_duration:.2f}s")
            return total_duration
            
    except Exception as e:
        logger.debug(f"Could not parse GIF duration: {e}")
        return 0.0


def get_gif_duration(movie: QtGui.QMovie) -> tuple[float, list[int]]:
    """
    Calculate total duration of GIF animation in seconds and get frame delays.
    Returns: (total_duration_seconds, list_of_frame_delays_ms)
    """
    try:
        global ANIMATION_GIF_PATH
        
        # Parse actual delays from GIF file
        if ANIMATION_GIF_PATH and ANIMATION_GIF_PATH.exists():
            delays = parse_gif_duration_pillow_fallback(ANIMATION_GIF_PATH)
            if delays:
                total_duration = sum(delays) / 1000.0
                return total_duration, delays
        
        # Fallback: estimate based on frame count
        frame_count = movie.frameCount()
        if frame_count > 0:
            estimated_duration = frame_count * 0.1  # Default 100ms per frame
            estimated_delays = [100] * frame_count
            logger.debug(f"Using estimated duration: {frame_count} frames * 0.1s = {estimated_duration:.2f}s")
            return estimated_duration, estimated_delays
        
        return 0.0, []
    except Exception as e:
        logger.debug(f"Could not calculate GIF duration: {e}")
        return 0.0, []


def parse_gif_duration_pillow_fallback(gif_path: Path) -> list[int]:
    """
    Try Pillow first, then fallback to manual parsing.
    """
    # Try Pillow first
    delays = parse_gif_frame_delays(gif_path)
    if delays:
        return delays
    
    # Fallback to manual parsing (keep existing code)
    # ... (keep the existing parse_gif_duration manual parsing code)
    return []


def scale_pixmap_if_needed(pixmap: QtGui.QPixmap, max_width: int, max_height: int) -> QtGui.QPixmap:
    """
    Scale pixmap down if needed, maintaining aspect ratio.
    If image is larger than max_width or max_height, scale it down.
    Does not scale up smaller images.
    Returns the scaled pixmap.
    """
    original_width = pixmap.width()
    original_height = pixmap.height()
    
    # Calculate scale factors for both dimensions
    width_scale = 1.0
    height_scale = 1.0
    
    if original_width > max_width:
        width_scale = max_width / original_width
    if original_height > max_height:
        height_scale = max_height / original_height
    
    # Use the smaller scale factor to ensure both constraints are met
    scale_factor = min(width_scale, height_scale)
    
    # Only scale if needed
    if scale_factor < 1.0:
        new_width = int(original_width * scale_factor)
        new_height = int(original_height * scale_factor)
        
        return pixmap.scaled(
            new_width, new_height,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation
        )
    
    return pixmap


def load_packaged_images(image_path: Optional[str] = None, default_image: Optional[str] = None) -> tuple[QtGui.QPixmap, QtGui.QMovie, str]:
    """
    Load GIF from ZIP archive and extract to temp files.
    If image_path is provided, use it (should point to ZIP file).
    Returns: (first_frame_pixmap, gif_movie, base_name)
    """
    global STATIC_PNG_PATH, ANIMATION_GIF_PATH
    
    script_dir = Path(__file__).resolve().parent
    
    if image_path:
        # User provided ZIP path
        zip_path = Path(image_path)
        if not zip_path.exists():
            raise FileNotFoundError(f"ZIP not found: {zip_path}")
        base_name = zip_path.stem
    else:
        # Use default_image if provided, otherwise default to "cat"
        if default_image:
            base_name = default_image
        else:
            base_name = "cat"
        
        zip_path = script_dir / "images" / f"{base_name}.zip"
    
    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP not found: {zip_path}")
    
    # Extract first GIF from ZIP
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_file:
            # Find first GIF file in the archive
            gif_files = [f for f in zip_file.namelist() if f.lower().endswith('.gif')]
            if not gif_files:
                raise ValueError(f"No GIF file found in ZIP: {zip_path}")
            
            # Get first GIF file
            gif_file_name = gif_files[0]
            gif_data = zip_file.read(gif_file_name)
            logger.info(f"Extracted {gif_file_name} from {zip_path.name}")
    except zipfile.BadZipFile:
        raise ValueError(f"Invalid ZIP file: {zip_path}")
    
    # Write to temp directory with static names
    temp_dir = get_temp_dir()
    ANIMATION_GIF_PATH = temp_dir / "animation.gif"
    STATIC_PNG_PATH = temp_dir / "static.png"
    
    logger.info(f"Temporary files: {STATIC_PNG_PATH} / {ANIMATION_GIF_PATH}")
    
    # Write GIF file
    ANIMATION_GIF_PATH.write_bytes(gif_data)
    
    # Extract first frame and save as PNG
    movie = QtGui.QMovie(str(ANIMATION_GIF_PATH))
    movie.jumpToFrame(0)
    first_frame = movie.currentPixmap()
    if first_frame.isNull():
        raise ValueError(f"Failed to extract first frame from GIF in ZIP: {zip_path}")
    
    # Scale if needed
    original_size = first_frame.size()
    first_frame = scale_pixmap_if_needed(first_frame, IMAGE_WIDTH_MAX, IMAGE_HEIGHT_MAX)
    if original_size != first_frame.size():
        logger.info(f"Resized {Path(zip_path).name}: {original_size.width()}x{original_size.height()} -> {first_frame.width()}x{first_frame.height()}")
    
    # Save first frame as PNG
    first_frame.save(str(STATIC_PNG_PATH), "PNG")
    
    # Load the static PNG
    pixmap = QtGui.QPixmap(str(STATIC_PNG_PATH))
    if pixmap.isNull():
        raise ValueError(f"Failed to load static PNG: {STATIC_PNG_PATH}")
    
    # Scale GIF movie to same size as first frame
    movie.setScaledSize(pixmap.size())
    movie.jumpToFrame(0)
    
    return pixmap, movie, base_name


def load_config(screen_width: int, screen_height: int, window_width: int, window_height: int) -> dict:
    """Load configuration from INI file. Returns position for bottom-right corner."""
    # Calculate default position (bottom-right with offset)
    default_x = screen_width - window_width - DEFAULT_POSITION_OFFSET_X
    default_y = screen_height - window_height - DEFAULT_POSITION_OFFSET_Y
    config_data = {'x': default_x, 'y': default_y}
    
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
        
        # Get original size before scaling
        self.gif_movie.jumpToFrame(0)
        original_size = self.gif_movie.currentPixmap().size()
        self.original_size = original_size
        
        # Calculate GIF duration from file and get frame delays
        self.gif_duration, self.frame_delays = get_gif_duration(self.gif_movie)
        
        # Fallback if no delays
        if not self.frame_delays:
            frame_count = self.gif_movie.frameCount()
            if frame_count > 0 and self.gif_duration > 0:
                self.frame_delays = [int((self.gif_duration / frame_count) * 1000)] * frame_count
            else:
                self.frame_delays = [100]  # Default 100ms per frame
        
        # Save first frame permanently (use the already scaled png_pixmap)
        self.first_frame_pixmap = self.png_pixmap.copy()
        
        # Animation state: 'png' -> show PNG, 'gif' -> play GIF
        self.state = 'png'
        self.next_change = time.time() + self.wait_time
        
        # Setup GIF movie - play once (no looping)
        self.gif_movie.setCacheMode(QtGui.QMovie.CacheMode.CacheAll)
        # Set speed to normal (100%) - uses native GIF frame delays
        self.gif_movie.setSpeed(100)
        
        # Manual frame timing
        self.animation_timer = QtCore.QTimer(self)
        self.current_frame = 0
        
        # Track if we need to manually stop after one loop
        self.gif_played_once = False
        
        # Log GIF info
        frame_count = self.gif_movie.frameCount()
        gif_size = self.gif_movie.scaledSize()
        logger.debug(f"GIF info: {frame_count} frames, duration: {self.gif_duration:.2f}s")
        logger.info(f"Playing {self.file_name}.zip {original_size.width()}x{original_size.height()} > {gif_size.width()}x{gif_size.height()} (first_frame, {self.wait_time:.1f}s static)")
        
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
        screen = QtWidgets.QApplication.primaryScreen().geometry()
        screen_width = screen.width()
        screen_height = screen.height()
        window_width = self.width()
        window_height = self.height()
        
        config = load_config(screen_width, screen_height, window_width, window_height)
        x = config.get("x", screen_width - window_width - DEFAULT_POSITION_OFFSET_X)
        y = config.get("y", screen_height - window_height - DEFAULT_POSITION_OFFSET_Y)
        self.move(x, y)
    
    def _save_position(self) -> None:
        """Save current window position to config."""
        pos = self.pos()
        config = {"x": pos.x(), "y": pos.y()}
        save_config(config)
    
    def _load_image(self, image_name: str) -> None:
        """Load a different GIF from ZIP and extract first frame."""
        try:
            zip_path = Path(__file__).resolve().parent / "images" / f"{image_name}.zip"
            
            if not zip_path.exists():
                logger.error(f"ZIP file not found: {image_name}.zip")
                return
            
            # Extract first GIF from ZIP
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                gif_files = [f for f in zip_file.namelist() if f.lower().endswith('.gif')]
                if not gif_files:
                    logger.error(f"No GIF file found in ZIP: {image_name}.zip")
                    return
                
                gif_data = zip_file.read(gif_files[0])
                logger.info(f"Extracted {gif_files[0]} from {zip_path.name}")
            
            # Write to temp directory
            global STATIC_PNG_PATH, ANIMATION_GIF_PATH
            temp_dir = get_temp_dir()
            ANIMATION_GIF_PATH = temp_dir / "animation.gif"
            STATIC_PNG_PATH = temp_dir / "static.png"
            
            # Write GIF
            ANIMATION_GIF_PATH.write_bytes(gif_data)
            
            # Extract first frame
            new_movie = QtGui.QMovie(str(ANIMATION_GIF_PATH))
            new_movie.jumpToFrame(0)
            first_frame = new_movie.currentPixmap()
            if first_frame.isNull():
                logger.error(f"Failed to extract first frame from {image_name}.zip")
                return
            
            # Scale if needed
            original_size = first_frame.size()
            first_frame = scale_pixmap_if_needed(first_frame, IMAGE_WIDTH_MAX, IMAGE_HEIGHT_MAX)
            if original_size != first_frame.size():
                logger.info(f"Resized {image_name}.zip: {original_size.width()}x{original_size.height()} -> {first_frame.width()}x{first_frame.height()}")
            
            # Save as PNG
            first_frame.save(str(STATIC_PNG_PATH), "PNG")
            
            # Load PNG
            new_pixmap = QtGui.QPixmap(str(STATIC_PNG_PATH))
            if new_pixmap.isNull():
                logger.error(f"Failed to load static PNG: {STATIC_PNG_PATH}")
                return
            
            # Configure movie
            new_movie.setScaledSize(new_pixmap.size())
            new_movie.setCacheMode(QtGui.QMovie.CacheMode.CacheAll)
            new_movie.setSpeed(100)
            new_movie.jumpToFrame(0)
            
            # Update current images
            self.png_pixmap = new_pixmap
            self.gif_movie = new_movie
            self.file_name = image_name
            
            # Update original size
            new_movie.jumpToFrame(0)
            self.original_size = new_movie.currentPixmap().size()
            
            # Calculate GIF duration and frame delays for new movie
            self.gif_duration, self.frame_delays = get_gif_duration(new_movie)
            
            # Fallback if no delays
            if not self.frame_delays:
                frame_count = new_movie.frameCount()
                if frame_count > 0 and self.gif_duration > 0:
                    self.frame_delays = [int((self.gif_duration / frame_count) * 1000)] * frame_count
                else:
                    self.frame_delays = [100]  # Default 100ms per frame
            
            # Save first frame (use the already scaled new_pixmap)
            self.first_frame_pixmap = new_pixmap.copy()
            
            # Reset to PNG state
            self.current_pixmap = self.png_pixmap
            self.state = 'png'
            self.gif_played_once = False
            self.next_change = time.time() + self.wait_time
            
            # Save bottom-right corner position before resize
            old_size = self.size()
            top_left = self.pos()
            bottom_right_x = top_left.x() + old_size.width()
            bottom_right_y = top_left.y() + old_size.height()
            
            # Resize window
            self.resize(self.png_pixmap.size())
            
            # Restore position to keep bottom-right corner in same place
            new_size = self.png_pixmap.size()
            new_x = bottom_right_x - new_size.width()
            new_y = bottom_right_y - new_size.height()
            self.move(new_x, new_y)
            
            # Reconnect movie callbacks
            self.gif_movie.frameChanged.connect(self._on_gif_frame_changed)
            self.gif_movie.finished.connect(self._on_gif_finished)
            
            # Save to INI
            save_image_to_ini(image_name)
            
            # Save new position
            self._save_position()
            
            logger.info(f"Switched to {image_name}.zip {self.png_pixmap.width()}x{self.png_pixmap.height()}")
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
        global STATIC_PNG_PATH
        
        if self.state == 'png':
            now = time.time()
            if now >= self.next_change:
                # Time to show GIF - reset and play once
                gif_size = self.gif_movie.scaledSize()
                logger.info(f"Playing {self.file_name}.zip {self.original_size.width()}x{self.original_size.height()} > {gif_size.width()}x{gif_size.height()} (animation, {self.gif_duration:.2f}s)")
                self.state = 'gif'
                self.gif_played_once = False
                
                # Reload from static.png to ensure we have fresh first frame
                static_pixmap = QtGui.QPixmap(str(STATIC_PNG_PATH))
                if not static_pixmap.isNull():
                    self.current_pixmap = static_pixmap
                    self.update()
                
                # Recreate movie from file to ensure fresh start
                self.gif_movie = QtGui.QMovie(str(ANIMATION_GIF_PATH))
                self.gif_movie.setScaledSize(self.current_pixmap.size())
                self.gif_movie.setCacheMode(QtGui.QMovie.CacheMode.CacheAll)
                self.gif_movie.setSpeed(100)
                
                # Jump to first frame
                self.gif_movie.jumpToFrame(0)
                
                # Start manual frame-by-frame animation with per-frame delays
                self.current_frame = 0
                # Stop and disconnect any existing timer
                self.animation_timer.stop()
                # Disconnect if connected (suppress RuntimeWarning)
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    try:
                        self.animation_timer.timeout.disconnect()
                    except RuntimeError:
                        pass
                self.animation_timer.timeout.connect(self._on_animation_frame)
                # Start with delay for first frame
                if self.frame_delays:
                    self.animation_timer.start(self.frame_delays[0])
                else:
                    self.animation_timer.start(100)
    
    def _on_animation_frame(self) -> None:
        """Manually advance to next frame at controlled speed."""
        frame_count = self.gif_movie.frameCount()
        
        # Check if we've completed the animation
        if self.current_frame >= frame_count:
            # Stop the timer
            self.animation_timer.stop()
            # Disconnect if connected (suppress RuntimeWarning)
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                try:
                    self.animation_timer.timeout.disconnect()
                except RuntimeError:
                    pass
            
            # Log completion
            logger.info(f"Animation complete for {self.file_name} ({frame_count} frames)")
            
            # Switch back to static
            QtCore.QTimer.singleShot(50, self._complete_switch_to_png)
            return
        
        # Jump to current frame and display it
        self.gif_movie.jumpToFrame(self.current_frame)
        pixmap = self.gif_movie.currentPixmap()
        if not pixmap.isNull():
            self.current_pixmap = pixmap
            self.update()
        
        # Move to next frame
        self.current_frame += 1
        
        # If not done, stop current timer and restart with next frame's delay
        if self.current_frame < frame_count and self.frame_delays and self.current_frame < len(self.frame_delays):
            delay = self.frame_delays[self.current_frame]
            self.animation_timer.stop()
            self.animation_timer.start(delay)
    
    def _on_gif_frame_changed(self, frame_number: int) -> None:
        """Called when GIF frame changes - update the display."""
        if self.state == 'gif':
            frame_count = self.gif_movie.frameCount()
            
            # Update current pixmap
            pixmap = self.gif_movie.currentPixmap()
            if not pixmap.isNull():
                self.current_pixmap = pixmap
                # Don't resize during animation - keep window size
                self.update()
            
            # Check if we've completed one full loop
            if not self.gif_played_once:
                # Stop before we reach the last frame
                if frame_number >= frame_count - 1:
                    logger.info(f"Animation complete for {self.file_name} ({frame_count} frames)")
                    self.gif_played_once = True
                    
                    # Stop the movie
                    self.gif_movie.stop()
                    
                    # Jump to first frame for next time
                    self.gif_movie.jumpToFrame(0)
                    
                    # Switch back to static.png
                    QtCore.QTimer.singleShot(50, self._complete_switch_to_png)
    
    def _complete_switch_to_png(self) -> None:
        """Complete the switch from GIF to PNG state."""
        global STATIC_PNG_PATH
        
        if self.state == 'gif':
            # Switch to PNG state
            self.state = 'png'
            self.next_change = time.time() + self.wait_time
            
            # Reload from static.png file
            static_pixmap = QtGui.QPixmap(str(STATIC_PNG_PATH))
            if not static_pixmap.isNull():
                self.current_pixmap = static_pixmap
                self.png_pixmap = static_pixmap
                self.first_frame_pixmap = static_pixmap
            
            logger.info(f"Playing {self.file_name}.zip {self.original_size.width()}x{self.original_size.height()} > {self.png_pixmap.width()}x{self.png_pixmap.height()} (first_frame, {self.wait_time:.1f}s static)")
            self.update()
    
    def _on_gif_finished(self) -> None:
        """Called when GIF animation finishes."""
        # Handled in _on_gif_frame_changed
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
        description="Pixel cat overlay with GIF animation (first frame used as static image)."
    )
    parser.add_argument(
        "-i", "--image",
        type=str,
        default=None,
        help="Path to ZIP file containing GIF (default: images/cat.zip). First frame used as static image.",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=STATIC_TIME,
        help="Seconds to show first frame before playing GIF (default: 5.0)",
    )

    parser.add_argument(
        "--pos",
        nargs=2,
        type=int,
        metavar=("X", "Y"),
        help="Start position (overrides remembered position)",
    )
    llm.add_arguments(parser)
    return parser.parse_args()

def main() -> None:
    """Main entry point."""
    args = parse_args()

    llm_context = llm.initialize(args)
    
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
    
    # Scan for available ZIP files
    available_images = scan_images_directory()
    logger.info(f"Found {len(available_images)} ZIP archive(s): {', '.join(available_images)}")
    
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
        logger.info(f"Playing {file_name}.zip (first frame) {png_pixmap.width()}x{png_pixmap.height()} for {args.wait:.1f}s")
    except Exception as e:
        logger.error(f"Error loading images: {e}")
        sys.exit(2)
    
    # Create and show window
    window = PixelCatWindow(png_pixmap, gif_movie, args.wait, file_name, available_images)
    if llm_context:
        llm.attach(window, llm_context)
    
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
