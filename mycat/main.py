#!/usr/bin/env python3
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
import io
import logging
import math
import os
import random
import shutil
import signal
import subprocess
import sys
import threading
import warnings
import zipfile
from pathlib import Path

# Allow running both as `python -m mycat` and `python mycat/main.py`
if __package__:
    from . import (
        activity,
        announcer,
        autostart,
        calendar_ics,
        char_catalog,
        char_pack,
        digest,
        focus,
        github_notify,
        llm,
        reminder,
        secret_store,
        update_check,
        updater,
    )
else:
    import importlib
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    llm = importlib.import_module("mycat.llm")
    char_catalog = importlib.import_module("mycat.char_catalog")
    reminder = importlib.import_module("mycat.reminder")
    secret_store = importlib.import_module("mycat.secret_store")
    autostart = importlib.import_module("mycat.autostart")
    char_pack = importlib.import_module("mycat.char_pack")
    announcer = importlib.import_module("mycat.announcer")
    focus = importlib.import_module("mycat.focus")
    github_notify = importlib.import_module("mycat.github_notify")
    calendar_ics = importlib.import_module("mycat.calendar_ics")
    activity = importlib.import_module("mycat.activity")
    digest = importlib.import_module("mycat.digest")
    update_check = importlib.import_module("mycat.update_check")
    updater = importlib.import_module("mycat.updater")

from PySide6 import QtCore, QtGui, QtWidgets

# Make logs readable for non-ASCII text (Cyrillic, emoji): force UTF-8 on the
# console streams when the locale left them as ASCII (otherwise the logger
# escapes e.g. "Ты" to "Ты").
for console_stream in (sys.stdout, sys.stderr):
    try:
        console_stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

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


def scan_chars() -> list[str]:
    """Return sorted unique char ids from bundled + user-installed locations."""
    return char_catalog.scan_all()


def movie_from_gif_bytes(gif_data: bytes) -> QtGui.QMovie:
    """A QMovie that reads the GIF from memory (a QBuffer), not a temp file.

    The QBuffer is parented to the movie so it lives exactly as long as the
    movie does — no dangling device, no /tmp file.
    """
    movie = QtGui.QMovie()
    buffer = QtCore.QBuffer(movie)
    buffer.setData(gif_data)
    buffer.open(QtCore.QIODevice.OpenModeFlag.ReadOnly)
    movie.setDevice(buffer)
    movie.setFormat(b"GIF")
    movie.setCacheMode(QtGui.QMovie.CacheMode.CacheAll)
    return movie


def parse_gif_frame_delays(gif_data: bytes) -> list[int]:
    """
    Parse GIF bytes using Pillow to extract frame delays.
    Returns list of delays in milliseconds.
    """
    try:
        try:
            from PIL import Image
        except ImportError:
            logger.warning("Pillow not available, falling back to manual parsing")
            return []

        img = Image.open(io.BytesIO(gif_data))
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


def get_gif_duration(movie: QtGui.QMovie, gif_data: bytes) -> tuple[float, list[int]]:
    """
    Calculate total duration of GIF animation in seconds and get frame delays.
    Returns: (total_duration_seconds, list_of_frame_delays_ms)
    """
    try:
        # Parse actual delays from the in-memory GIF bytes
        delays = parse_gif_frame_delays(gif_data)
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


def load_packaged_images(
    image_path: str | None = None, default_image: str | None = None
) -> tuple[QtGui.QPixmap, QtGui.QMovie, str, bytes]:
    """
    Load the GIF from a ZIP archive entirely in memory (no temp files).
    If image_path is provided, use it (should point to a ZIP file).
    Returns: (first_frame_pixmap, gif_movie, base_name, gif_bytes)
    """
    if image_path:
        char_path = Path(image_path)
        if not char_path.exists():
            raise FileNotFoundError(f"Char not found: {char_path}")
    else:
        base_name = default_image or "cat"
        resolved = char_catalog.find_char(base_name)
        if resolved is None:
            raise FileNotFoundError(f"Char '{base_name}' not found in bundled or user chars dir")
        char_path = resolved
    base_name = char_path.stem

    # Read the first GIF from the char (folder or zip, in memory).
    try:
        with char_pack.CharSource(char_path) as source:
            gif_files = sorted(n for n in source.names() if n.lower().endswith(".gif"))
            if not gif_files:
                raise ValueError(f"No GIF file found in char: {char_path}")
            gif_file_name = gif_files[0]
            gif_data = source.read(gif_file_name)
            logger.info(f"Extracted {gif_file_name} from {char_path.name}")
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Invalid char archive: {char_path}") from exc
    
    # Build the animated movie straight from the GIF bytes in memory.
    movie = movie_from_gif_bytes(gif_data)
    movie.jumpToFrame(0)
    first_frame = movie.currentPixmap()
    if first_frame.isNull():
        raise ValueError(f"Failed to extract first frame from GIF in char: {char_path}")

    # Scale if needed
    original_size = first_frame.size()
    pixmap = scale_pixmap_if_needed(first_frame, IMAGE_WIDTH_MAX, IMAGE_HEIGHT_MAX)
    if original_size != pixmap.size():
        logger.info(
            f"Resized {char_path.name}: "
            f"{original_size.width()}x{original_size.height()} -> "
            f"{pixmap.width()}x{pixmap.height()}"
        )
    if pixmap.isNull():
        raise ValueError(f"Failed to render first frame from GIF in char: {char_path}")

    # Scale GIF movie to same size as the first frame
    movie.setScaledSize(pixmap.size())
    movie.jumpToFrame(0)

    return pixmap, movie, base_name, gif_data


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
        secret_store.secure_file(CFG_FILE)
    except Exception as e:
        logger.error(f"Config save error: {e}")


def load_image_from_ini() -> str | None:
    """Load default image setting from INI file."""
    if not CFG_FILE.exists():
        logger.info("INI config not found, using default: cat")
        return None
    
    try:
        config = configparser.ConfigParser()
        config.read(CFG_FILE)
        
        if 'settings' in config and 'default_image' in config['settings']:
            image_name = config['settings']['default_image']
            logger.info(f"Loaded image from INI: {image_name}")
            return image_name
        else:
            logger.info("INI config exists but no default_image setting found, using default: cat")
            return None
    except Exception as e:
        logger.error(f"Error reading INI file: {e}, using default: cat")
        return None


def save_image_to_ini(image_name: str) -> None:
    """Save current image setting to INI file (skips writing if value is unchanged)."""
    try:
        CFG_DIR.mkdir(parents=True, exist_ok=True)

        config = configparser.ConfigParser()

        # Read existing config if it exists
        if CFG_FILE.exists():
            config.read(CFG_FILE)

        if (
            config.has_section('settings')
            and config.get('settings', 'default_image', fallback=None) == image_name
        ):
            return

        # Ensure [settings] section exists
        if 'settings' not in config:
            config.add_section('settings')

        # Set the default_image value
        config['settings']['default_image'] = image_name

        # Write to file
        with open(CFG_FILE, 'w') as f:
            config.write(f)
        secret_store.secure_file(CFG_FILE)

        logger.info(f"Saved image setting to INI: {image_name}")
    except Exception as e:
        logger.error(f"Error saving to INI file: {e}")


def autostart_was_prompted() -> bool:
    """Whether the first-run "start on login?" prompt has already been shown.

    Stored as ``[settings] autostart_prompted`` so the user is asked at most once.
    """
    if not CFG_FILE.exists():
        return False
    try:
        config = configparser.ConfigParser()
        config.read(CFG_FILE)
        return config.getboolean("settings", "autostart_prompted", fallback=False)
    except Exception as exc:
        logger.debug("Could not read autostart_prompted flag: %s", exc)
        return False


def mark_autostart_prompted() -> None:
    """Record that the first-run autostart prompt has been shown."""
    try:
        CFG_DIR.mkdir(parents=True, exist_ok=True)
        config = configparser.ConfigParser()
        if CFG_FILE.exists():
            config.read(CFG_FILE)
        if "settings" not in config:
            config.add_section("settings")
        config["settings"]["autostart_prompted"] = "true"
        with open(CFG_FILE, "w") as f:
            config.write(f)
        secret_store.secure_file(CFG_FILE)
    except Exception as exc:
        logger.error("Could not save autostart_prompted flag: %s", exc)


def should_offer_autostart() -> bool:
    """First run, on a platform that supports autostart, not enabled, not asked."""
    return (
        autostart.is_supported()
        and not autostart.is_enabled()
        and not autostart_was_prompted()
    )


def offer_autostart_on_first_run(window: QtWidgets.QWidget) -> None:
    """Ask once, on first run, whether to keep mycat on screen every login.

    The whole point of autostart is to make the cat persistent — but the toggle
    is buried in the right-click menu, so most users never find it. A single
    gentle first-run prompt is the biggest lever for "always running".
    """
    if not should_offer_autostart():
        return
    # Record first so a crash mid-prompt never re-asks on every launch.
    mark_autostart_prompted()
    answer = QtWidgets.QMessageBox.question(
        window,
        "mycat",
        "Keep mycat on screen every time you log in?\n\n"
        "You can change this any time from the right-click menu → Autostart.",
        QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        QtWidgets.QMessageBox.StandardButton.Yes,
    )
    if answer == QtWidgets.QMessageBox.StandardButton.Yes:
        autostart.set_enabled(True)
        logger.info("Autostart enabled via first-run prompt")


def flush_activity_on_quit(window: QtWidgets.QWidget) -> None:
    """On a clean Quit, flush the current activity minute to the database."""
    collector = getattr(window, "activity_collector", None)
    if collector is not None:
        try:
            collector.flush()
        except Exception as exc:  # noqa: BLE001 - shutdown must never raise
            logger.debug("Activity flush on quit failed: %s", exc)


def read_battery_percent():
    """Battery charge 0–100, or None if there is no battery / can't read it.

    Native Linux /sys first; optional psutil fallback. Used by the 'hungry'
    state — on a desktop with no battery it returns None (state never triggers)."""
    base = Path("/sys/class/power_supply")
    try:
        for entry in base.iterdir():
            try:
                if (entry / "type").read_text().strip() == "Battery":
                    return int((entry / "capacity").read_text().strip())
            except OSError:
                continue
    except OSError:
        pass
    try:
        import psutil
        battery = psutil.sensors_battery()
        if battery is not None:
            return int(battery.percent)
    except Exception:
        pass
    return None


def harden_pixmap(pixmap: QtGui.QPixmap, threshold: int = 128) -> QtGui.QPixmap:
    """Snap alpha to 0/255 so a smooth-scaled silhouette has a crisp edge that
    matches the 1-bit shape mask — otherwise the anti-aliased edge renders as a
    muddy fringe on X11 without a compositor.

    Uses Pillow's C-speed ``point`` on the alpha channel — a Python per-pixel
    loop here froze loads of large multi-frame chars (e.g. girl*, 120
    frames at 281×500)."""
    from PIL import Image

    image = pixmap.toImage().convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
    width, height = image.width(), image.height()
    pil = Image.frombytes("RGBA", (width, height), image.constBits().tobytes())
    pil.putalpha(pil.getchannel("A").point(lambda value: 255 if value >= threshold else 0))
    hardened = QtGui.QImage(pil.tobytes("raw", "RGBA"), width, height,
                            QtGui.QImage.Format.Format_RGBA8888)
    return QtGui.QPixmap.fromImage(hardened.copy())


class UpdateSignals(QtCore.QObject):
    """Marshals the self-update worker threads back onto the GUI thread."""

    checked = QtCore.Signal(str)          # latest tag if newer, else ""
    progress = QtCore.Signal(int, int)    # bytes done, total (0 = unknown)
    applied = QtCore.Signal()             # new build swapped in + spawned
    failed = QtCore.Signal(str)           # error message


class PixelCatWindow(QtWidgets.QWidget):
    """Main cat window widget with PNG/GIF animation and dragging."""
    
    def __init__(
        self,
        png_pixmap: QtGui.QPixmap,
        gif_movie: QtGui.QMovie,
        wait_time: float,
        file_name: str = "cat",
        available_images: list[str] = None,
        gif_data: bytes = b"",
        pack: "char_pack.CharPack | None" = None,
    ) -> None:
        platform_name = ""
        app_instance = QtWidgets.QApplication.instance()
        if app_instance is not None:
            platform_name = (app_instance.platformName() or "").lower()
        
        # Window flags for transparent, frameless, always-on-top window
        # Qt.Window (not Qt.Tool) so the cat gets an entry in the taskbar /
        # program list at startup — Tool windows are hidden from it.
        flags = (
            QtCore.Qt.WindowType.FramelessWindowHint |
            QtCore.Qt.WindowType.Window
        )
        if platform_name != "offscreen":
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)

        # Setup transparency
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("mycat")
        self.setWindowIcon(make_app_icon())
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        # On X11 without a compositor, per-pixel alpha renders as a black box.
        # Fall back to clipping the window to the image silhouette (setMask) so
        # transparency works without a compositor — important for remote desktops
        # where enabling compositing adds noticeable latency. Edges are hard
        # (1-bit), which suits the pixel-art cat. MYCAT_SHAPE_MASK=1/0 forces it.
        self.shape_mask_key = None
        force_mask = os.environ.get("MYCAT_SHAPE_MASK")
        if force_mask in ("0", "1"):
            self.shape_mask_enabled = force_mask == "1"
        else:
            self.shape_mask_enabled = platform_name == "xcb" and x11_compositor_active() is False
        if self.shape_mask_enabled:
            logger.warning(
                "No X11 compositor detected — switching to alternative transparency mode "
                "(shape mask: window clipped to the image silhouette, hard 1-bit edges, no smooth alpha). "
                "Enable display compositing for smooth edges, or force this mode with MYCAT_SHAPE_MASK=1."
            )

        # Common content fields
        self.wait_time = wait_time
        self.file_name = file_name
        self.available_images = available_images or []
        self.char_pack = pack

        # Content setup branches by char type; the chrome below is shared.
        if self.char_pack is not None:
            self._setup_pack_content()
        else:
            self._setup_gif_content(png_pixmap, gif_movie, gif_data)

        # Dragging state
        self.dragging = False
        self.drag_start_pos = QtCore.QPoint()

        # Set window size to pixmap size (pack: bounding box over all frames).
        self.resize(self._pack_content_size() if self.char_pack is not None else self.current_pixmap.size())

        # Position window - defaults to bottom-right
        self._load_position()

        # Setup context menu
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Schedule first animation pass (GIF chars only)
        if self.char_pack is None:
            self._schedule_next_animation()

        # Save current image to INI on startup
        save_image_to_ini(self.file_name)

        # Reminder scheduler (cat-on-a-plane flyby). Loads any saved reminder
        # and re-arms it; the flyby UI is imported lazily on first use.
        self.reminder_controller = reminder.ReminderController(self)

        # Shared announcement queue: every companion feature (focus sessions,
        # GitHub, calendar, digest) flies its banners through this one object
        # so flybys never overlap and focus time stays quiet.
        self.announcer = announcer.Announcer(self)

        # Pomodoro-style focus sessions: the cat settles down while you work,
        # a thin bar under it shows the remaining time, banners mark breaks.
        self.focus_controller = focus.FocusController(self, announcer=self.announcer)

        # GitHub notifications (opt-in, BYO token): silent — zero network
        # requests — until enabled in its settings dialog.
        self.github_notifier = github_notify.GitHubNotifier(self, announcer=self.announcer)

        # Calendar reminders (opt-in, secret ICS URL): banners shortly before
        # each event, shown like every other announcement.
        self.calendar_controller = calendar_ics.CalendarController(self, announcer=self.announcer)

        # Activity diary (on by default, local-only): counters, never content;
        # the collector shares activity.db with the focus session log above.
        self.activity_collector = activity.ActivityCollector(store=self.focus_controller.store)
        # Auto-pomodoro: coming back to the keyboard after an idle stretch
        # quietly starts the focus countdown ([focus] auto_start to disable).
        self.focus_controller.attach_collector(self.activity_collector)

        # The morning newspaper: yesterday's stats once per day, first thing
        # after 05:00 — another small reason the cat is running at dawn.
        self.morning_digest = digest.MorningDigest(self.focus_controller.store, announcer=self.announcer)

    def _setup_gif_content(self, png_pixmap, gif_movie, gif_data) -> None:
        """Legacy single-GIF char: static first frame + play-once animation."""
        self.png_pixmap = png_pixmap
        self.gif_movie = gif_movie
        self.gif_data = gif_data
        self.current_pixmap = self.png_pixmap
        self.gif_movie.jumpToFrame(0)
        original_size = self.gif_movie.currentPixmap().size()
        self.original_size = original_size
        self.gif_duration, self.frame_delays = get_gif_duration(self.gif_movie, self.gif_data)
        if not self.frame_delays:
            frame_count = self.gif_movie.frameCount()
            if frame_count > 0 and self.gif_duration > 0:
                self.frame_delays = [int((self.gif_duration / frame_count) * 1000)] * frame_count
            else:
                self.frame_delays = [100]
        self.first_frame_pixmap = self.png_pixmap.copy()
        self.state = 'png'
        self.gif_movie.setCacheMode(QtGui.QMovie.CacheMode.CacheAll)
        self.gif_movie.setSpeed(100)
        self.animation_timer = QtCore.QTimer(self)
        self.animation_timer.timeout.connect(self._on_animation_frame)
        self.current_frame = 0
        gif_size = self.gif_movie.scaledSize()
        logger.info(
            f"Playing {self.file_name}.zip {original_size.width()}x{original_size.height()} > "
            f"{gif_size.width()}x{gif_size.height()} (first_frame, {self.wait_time:.1f}s static)"
        )

    def _all_pack_clips(self):
        """Every Anim in the pack (for hardening / preprocessing)."""
        pack = self.char_pack
        clips = list(pack.anims) + list(pack.idle_anims) + list(pack.click_anims) + list(pack.hungry_anims)
        clips += [a for a in (pack.sleep_in, pack.sleep_out, pack.yawn) if a is not None]
        return clips

    def _pack_content_size(self) -> QtCore.QSize:
        """Bounding box over the static and every frame, so the window fits the
        largest pose. Frames are box-fit independently and a body GIF may be taller
        than the still; the window must hold it or it would be clipped. Each frame
        is centred within this box at paint time."""
        pack = self.char_pack
        width, height = pack.static.width(), pack.static.height()
        for still in (pack.blink, pack.sleep):
            if still is not None:
                width, height = max(width, still.width()), max(height, still.height())
        for anim in self._all_pack_clips():
            for frame in anim.frames:
                width, height = max(width, frame.width()), max(height, frame.height())
        return QtCore.QSize(width, height)

    def _setup_pack_content(self) -> None:
        """Interactive char pack: drives the state machine (awake/blink/click/idle/yawn/sleep/hungry)."""
        pack = self.char_pack
        # No compositor → snap body-frame edges to binary alpha (crisp, no fringe).
        # Pupil sprites stay smooth (drawn over the opaque face, never fringe).
        if self.shape_mask_enabled:
            pack.static = harden_pixmap(pack.static)
            for still in ("blink", "sleep"):
                if getattr(pack, still) is not None:
                    setattr(pack, still, harden_pixmap(getattr(pack, still)))
            for anim in self._all_pack_clips():
                anim.frames = [harden_pixmap(frame) for frame in anim.frames]
        self.png_pixmap = pack.static
        self.gif_movie = None
        self.gif_data = b""
        self.current_pixmap = pack.static
        self.first_frame_pixmap = pack.static.copy()
        self.original_size = pack.static.size()
        self.state = 'png'
        self.gif_duration, self.frame_delays = 0.0, []
        self.eye_clock = QtCore.QElapsedTimer()
        self.eye_clock.start()
        self._test_now = None                 # tests inject time here
        now = self._pack_now()

        # --- state-machine state ---
        self.base_state = "awake"             # "awake" | "sleeping"
        self.active_clip = None               # (anim, start_t, next_state) one-shot
        self.squint_until = -10.0
        self.yawned = False
        self.last_interaction = now           # mouse over the cat / click / drag
        self.last_cursor_move = now           # global cursor movement
        self.next_blink = now + random.uniform(*pack.blink_every) if pack.blink_enabled else float("inf")
        self.next_idle = now + random.uniform(*pack.idle_random_every)
        self.next_hungry = now + random.uniform(*pack.hungry_every)
        self.anim_next = [now + random.uniform(*anim.every) for anim in pack.anims]
        self._battery_pct = None
        self._battery_checked = -1e9
        self._pack_mode = "open"
        self._last_cursor = QtGui.QCursor.pos()
        self._mask_cache: dict = {}

        self.pack_timer = QtCore.QTimer(self)
        self.pack_timer.timeout.connect(self._pack_tick)
        self.pack_timer.start(33)             # ~30 fps; only repaints when something changed
        logger.info(
            f"Loaded interactive char '{pack.name}' ({pack.static.width()}x{pack.static.height()}; "
            f"eyes={pack.eyes is not None} blink={pack.blink_enabled} "
            f"sleep={pack.sleep is not None} yawn={pack.yawn is not None} "
            f"idle={len(pack.idle_anims)} click={len(pack.click_anims)} "
            f"hungry={len(pack.hungry_anims)} anims={len(pack.anims)})"
        )

    def _pack_now(self) -> float:
        if getattr(self, "_test_now", None) is not None:
            return self._test_now
        return self.eye_clock.elapsed() / 1000.0

    def _pack_tick(self) -> None:
        """Advance the state machine; repaint only when the frame or gaze changes."""
        now = self._pack_now()
        cursor = QtGui.QCursor.pos()
        moved = cursor != self._last_cursor
        if moved:
            self._last_cursor = cursor
            self.last_cursor_move = now
            self.yawned = False
        previous = self.current_pixmap
        self._pack_mode = self._update_pack_frame()
        changed = self.current_pixmap is not previous
        if moved and self._pack_mode == "open" and self.char_pack.eyes is not None:
            changed = True
        if changed:
            self.update()

    def _clip_frame(self, anim, age_ms: float):
        accumulated = 0
        for frame, delay in zip(anim.frames, anim.delays):
            accumulated += delay
            if age_ms < accumulated:
                return frame
        return anim.frames[-1]

    def _start_clip(self, anim, next_state: str, now: float) -> None:
        self.active_clip = (anim, now, next_state)
        if anim.frames:
            self.current_pixmap = anim.frames[0]

    def _wake(self, now: float) -> bool:
        """If asleep (or falling asleep), wake via sleep_out (or instantly). True if woke."""
        going_to_sleep = self.active_clip is not None and self.active_clip[2] == "sleeping"
        if self.base_state != "sleeping" and not going_to_sleep:
            return False
        self.last_interaction = now      # waking is an interaction; don't re-sleep/yawn instantly
        self.last_cursor_move = now
        self.yawned = False
        if self.char_pack.sleep_out is not None:
            self._start_clip(self.char_pack.sleep_out, "awake", now)
        else:
            self.active_clip = None
            self.base_state = "awake"
        return True

    def _battery_low(self) -> bool:
        now = self._pack_now()
        if now - self._battery_checked > 10.0:
            self._battery_checked = now
            self._battery_pct = read_battery_percent()
        return self._battery_pct is not None and self._battery_pct <= self.char_pack.hungry_below

    def _on_pack_click(self) -> None:
        """Click reaction: wake if asleep, else play a clickN anim or squint."""
        if self.char_pack is None:
            return
        now = self._pack_now()
        self.last_interaction = now
        self.yawned = False
        if self._wake(now):
            self.update()
            return
        pack = self.char_pack
        if pack.click_anims:
            self._start_clip(random.choice(pack.click_anims), "awake", now)
        elif pack.blink is not None:
            self.squint_until = now + pack.click_squint
        self.update()

    def _update_pack_frame(self) -> str:
        """State machine: hungry > sleep > yawn > reaction > blink > awake. Sets current_pixmap."""
        pack = self.char_pack
        now = self._pack_now()

        # An active one-shot clip (transition or reaction) plays to completion.
        if self.active_clip is not None:
            anim, start, next_state = self.active_clip
            age_ms = (now - start) * 1000.0
            if not anim.frames or age_ms >= sum(anim.delays):
                self.active_clip = None
                if next_state:
                    self.base_state = next_state
            else:
                self.current_pixmap = self._clip_frame(anim, age_ms)
                return "anim"

        # Held sleeping pose (wake is driven by interaction, not here).
        if self.base_state == "sleeping":
            self.current_pixmap = pack.sleep or pack.static
            return "sleep"

        idle_for = now - self.last_interaction
        cursor_still = now - self.last_cursor_move

        # hungry (low battery)
        if pack.hungry_anims and now >= self.next_hungry and self._battery_low():
            self._start_clip(random.choice(pack.hungry_anims), "awake", now)
            self.next_hungry = now + random.uniform(*pack.hungry_every)
            return "anim"
        # sleep
        if (pack.sleep is not None or pack.sleep_in is not None) and idle_for > pack.sleep_after:
            if pack.sleep_in is not None:
                self._start_clip(pack.sleep_in, "sleeping", now)
                return "anim"
            self.base_state = "sleeping"
            self.current_pixmap = pack.sleep or pack.static
            return "sleep"
        # yawn (precursor to sleep)
        if pack.yawn is not None and not self.yawned and cursor_still > pack.yawn_after:
            self.yawned = True
            self._start_clip(pack.yawn, "awake", now)
            return "anim"
        # idle-random pool
        if pack.idle_anims and now >= self.next_idle:
            self._start_clip(random.choice(pack.idle_anims), "awake", now)
            self.next_idle = now + random.uniform(*pack.idle_random_every)
            return "anim"
        # periodic config animations
        for index, anim in enumerate(pack.anims):
            if now >= self.anim_next[index]:
                self._start_clip(anim, "awake", now)
                self.anim_next[index] = now + sum(anim.delays) / 1000.0 + random.uniform(*anim.every)
                return "anim"
        # blink
        if pack.blink_enabled and now >= self.next_blink:
            self.squint_until = now + pack.blink_duration
            self.next_blink = now + random.uniform(*pack.blink_every)
        squinting = now < self.squint_until
        self.current_pixmap = pack.blink if (squinting and pack.blink is not None) else pack.static
        return "blink" if squinting else "open"

    def pupil_offsets(self, x: int, y: int, cursor: QtCore.QPoint):
        """Gaze offsets (scaled px) for the (left, right) pupils.

        Both pupils share one angle — that of whichever eye is nearer the cursor.
        When the cursor is outside the eye pair they move in parallel (the same
        offset); when it is horizontally between the eyes they mirror each other
        (the nearer eye aims at the cursor, the other takes the horizontal
        mirror), so the gaze converges. Sockets sit at equal height, so the two
        cases meet continuously at the boundaries. Returns ((lox, loy), (rox, roy))."""
        pack = self.char_pack
        travel = pack.eyes.travel_radius
        left_socket = self.mapToGlobal(QtCore.QPoint(round(x + pack.eyes.left.x()), round(y + pack.eyes.left.y())))
        right_socket = self.mapToGlobal(QtCore.QPoint(round(x + pack.eyes.right.x()), round(y + pack.eyes.right.y())))

        def aim(socket):
            dx, dy = cursor.x() - socket.x(), cursor.y() - socket.y()
            dist = math.hypot(dx, dy)
            return (dx / dist * travel, dy / dist * travel) if dist > 1 else (0.0, 0.0)

        left_dist = math.hypot(cursor.x() - left_socket.x(), cursor.y() - left_socket.y())
        right_dist = math.hypot(cursor.x() - right_socket.x(), cursor.y() - right_socket.y())
        left_nearer = left_dist <= right_dist
        base = aim(left_socket if left_nearer else right_socket)

        if left_socket.x() < cursor.x() < right_socket.x():     # between the eyes -> converge (mirror)
            mirrored = (-base[0], base[1])
            return (base, mirrored) if left_nearer else (mirrored, base)
        return base, base                                       # outside the pair -> parallel

    def gaze_target(self, x: int, y: int) -> QtCore.QPoint:
        """Where the pupils look: the cursor while "Enable Tracking" is on AND the
        cursor is on the cat's screen; otherwise the cat's own nose — a point
        between and just below the eyes so the pupils converge downward. So the cat
        looks at its nose when Tracking is off, or when the cursor has left for
        another monitor. (Independent of the Mouse/Keyboard diary toggles.)"""
        collector = getattr(self, "activity_collector", None)
        tracking = collector is None or collector.settings.enabled
        if tracking:
            cursor = QtGui.QCursor.pos()
            app = QtWidgets.QApplication.instance()
            cat_screen = self.screen()
            if app is not None and cat_screen is not None and app.screenAt(cursor) is cat_screen:
                return cursor
        eyes = self.char_pack.eyes
        nose_x = (eyes.left.x() + eyes.right.x()) / 2.0
        nose_y = max(eyes.left.y(), eyes.right.y()) + eyes.travel_radius * 2
        return self.mapToGlobal(QtCore.QPoint(round(x + nose_x), round(y + nose_y)))

    def _draw_pupils(self, painter, x: int, y: int) -> None:
        """Draw the L/R pupil sprites at the computed gaze offsets."""
        pack = self.char_pack
        if not pack.eyes or pack.eye_left is None or pack.eye_right is None:
            return
        left_off, right_off = self.pupil_offsets(x, y, self.gaze_target(x, y))
        for center, sprite, (ox, oy) in (
            (pack.eyes.left, pack.eye_left, left_off),
            (pack.eyes.right, pack.eye_right, right_off),
        ):
            px = x + center.x() + ox - sprite.width() / 2.0
            py = y + center.y() + oy - sprite.height() / 2.0
            painter.drawPixmap(QtCore.QPointF(px, py), sprite)

    def _load_position(self) -> None:
        """Load window position from config; default to the bottom-right corner."""
        rect = usable_screen_rect()
        window_width = self.width()
        window_height = self.height()

        config = load_config(rect.width(), rect.height(), window_width, window_height)
        default_x, default_y = self.bottom_right_position(window_width, window_height)
        x = config.get("x", default_x)
        y = config.get("y", default_y)
        x, y = self._clamp_to_screens(x, y, window_width, window_height)
        self.move(x, y)

    def bottom_right_position(self, width: int, height: int) -> tuple[int, int]:
        """Bottom-right corner of the usable screen area (robust to a 0x0 Qt screen)."""
        rect = usable_screen_rect()
        x = rect.x() + rect.width() - width - DEFAULT_POSITION_OFFSET_X
        y = rect.y() + rect.height() - height - DEFAULT_POSITION_OFFSET_Y
        return x, y

    def _clamp_to_screens(self, x: int, y: int, width: int, height: int) -> tuple[int, int]:
        """Keep the window visible; robust to Qt reporting empty screen geometry."""
        rect = usable_screen_rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return x, y  # screen size unknown — trust the requested position

        window_rect = QtCore.QRect(x, y, width, height)
        union = QtCore.QRect(rect)
        app = QtWidgets.QApplication.instance()
        for screen in (app.screens() if app is not None else []):
            geo = screen.availableGeometry()
            if geo.width() > 0 and geo.height() > 0:
                union = union.united(geo)
        if union.intersects(window_rect):
            return x, y

        fallback_x = rect.x() + rect.width() - width - DEFAULT_POSITION_OFFSET_X
        fallback_y = rect.y() + rect.height() - height - DEFAULT_POSITION_OFFSET_Y
        logger.warning(
            "Saved position (%d, %d) is off-screen (usable=%s); resetting to (%d, %d)",
            x, y, union, fallback_x, fallback_y,
        )
        return fallback_x, fallback_y
    
    def _save_position(self) -> None:
        """Save current window position to config."""
        pos = self.pos()
        config = {"x": pos.x(), "y": pos.y()}
        save_config(config)

    def _reset_position(self) -> None:
        """Snap the cat to the bottom-right corner, an equal inset from each edge.

        Measured from the true screen corner (full geometry, not the
        panel-aware area) so the cat sits right by the edge. A rescue for when
        it wanders off-screen or gets lost across multiple monitors.
        """
        margin = 18
        screen = QtWidgets.QApplication.primaryScreen()
        rect = screen.geometry() if screen is not None else usable_screen_rect()
        x = rect.x() + rect.width() - self.width() - margin
        y = rect.y() + rect.height() - self.height() - margin
        self.move(x, y)
        self._save_position()

    def _load_image(self, image_name: str) -> None:
        """Switch chars — a new interactive pack or a legacy single-GIF."""
        zip_path = char_catalog.find_char(image_name)
        if zip_path is None:
            logger.error(f"ZIP file not found for char: {image_name}")
            return
        if char_pack.is_new_pack(zip_path):
            self._switch_to_pack(image_name, zip_path)
            return
        if self.char_pack is not None:
            self._teardown_pack_mode()
        try:
            # Read the first GIF from the char (folder or zip, in memory).
            with char_pack.CharSource(zip_path) as source:
                gif_files = sorted(n for n in source.names() if n.lower().endswith(".gif"))
                if not gif_files:
                    logger.error(f"No GIF found in char: {image_name}")
                    return
                gif_data = source.read(gif_files[0])
                logger.info(f"Extracted {gif_files[0]} from {Path(zip_path).name}")
            
            # Build the new movie from the GIF bytes in memory (no temp files).
            new_movie = movie_from_gif_bytes(gif_data)
            new_movie.jumpToFrame(0)
            first_frame = new_movie.currentPixmap()
            if first_frame.isNull():
                logger.error(f"Failed to extract first frame from {image_name}.zip")
                return

            # Scale if needed
            original_size = first_frame.size()
            new_pixmap = scale_pixmap_if_needed(first_frame, IMAGE_WIDTH_MAX, IMAGE_HEIGHT_MAX)
            if original_size != new_pixmap.size():
                logger.info(
                    f"Resized {image_name}.zip: "
                    f"{original_size.width()}x{original_size.height()} -> "
                    f"{new_pixmap.width()}x{new_pixmap.height()}"
                )
            if new_pixmap.isNull():
                logger.error(f"Failed to render first frame from {image_name}.zip")
                return

            # Configure movie
            new_movie.setScaledSize(new_pixmap.size())
            new_movie.setSpeed(100)
            new_movie.jumpToFrame(0)

            # Update current images
            self.png_pixmap = new_pixmap
            self.gif_movie = new_movie
            self.gif_data = gif_data
            self.file_name = image_name

            # Update original size
            new_movie.jumpToFrame(0)
            self.original_size = new_movie.currentPixmap().size()

            # Calculate GIF duration and frame delays for new movie
            self.gif_duration, self.frame_delays = get_gif_duration(new_movie, gif_data)
            
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
            self.animation_timer.stop()
            self._schedule_next_animation()

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

            # Save to INI
            save_image_to_ini(image_name)
            
            # Save new position
            self._save_position()
            
            logger.info(f"Switched to {image_name}.zip {self.png_pixmap.width()}x{self.png_pixmap.height()}")
            self.update()
            
        except Exception as e:
            logger.error(f"Error loading {image_name}: {e}")

    def _teardown_pack_mode(self) -> None:
        """Leave interactive-pack mode so the legacy GIF path can take over."""
        if getattr(self, "pack_timer", None) is not None:
            self.pack_timer.stop()
            self.pack_timer = None
        self.char_pack = None
        if getattr(self, "animation_timer", None) is None:
            self.animation_timer = QtCore.QTimer(self)
            self.animation_timer.timeout.connect(self._on_animation_frame)
        self.current_frame = 0

    def _switch_to_pack(self, image_name: str, zip_path) -> None:
        """Switch to a new interactive char pack, preserving the bottom-right corner."""
        try:
            pack = char_pack.load_pack(zip_path)
        except Exception as exc:
            logger.error(f"Error loading pack {image_name}: {exc}")
            return
        if getattr(self, "animation_timer", None) is not None:
            self.animation_timer.stop()
        if getattr(self, "pack_timer", None) is not None:
            self.pack_timer.stop()
        old_size = self.size()
        top_left = self.pos()
        bottom_right_x = top_left.x() + old_size.width()
        bottom_right_y = top_left.y() + old_size.height()

        self.char_pack = pack
        self.file_name = image_name
        self._setup_pack_content()

        new_size = self._pack_content_size()
        self.resize(new_size)
        self.move(bottom_right_x - new_size.width(), bottom_right_y - new_size.height())
        save_image_to_ini(image_name)
        self._save_position()
        self.update()
        logger.info(f"Switched to interactive char {image_name}")

    def _show_context_menu(self, pos: QtCore.QPoint) -> None:
        """Show context menu at the given position."""
        menu = QtWidgets.QMenu(self)

        # "Chat" appears only once Ollama is configured (a controller exists),
        # and is greyed out while the LLM is disabled.
        toggle_chat = getattr(self, "_toggle_llm_chat", None)
        if callable(toggle_chat):
            chat_action = menu.addAction("Chat")
            chat_action.triggered.connect(toggle_chat)
            llm_is_enabled = getattr(self, "_is_llm_enabled", None)
            if callable(llm_is_enabled):
                chat_action.setEnabled(bool(llm_is_enabled()))
            menu.addSeparator()

        # Settings entries, in the agreed order: LLM, Calendar, Reminder,
        # GitHub, Activity.
        llm_action = menu.addAction("LLM…")
        llm_action.triggered.connect(self.open_llm_settings)

        calendar_action = menu.addAction("Calendar…")
        calendar_action.triggered.connect(self.open_calendar_settings)

        reminder_action = menu.addAction("Reminder…")
        reminder_action.triggered.connect(self._open_reminder)

        github_action = menu.addAction("GitHub…")
        github_action.triggered.connect(self.open_github_settings)

        activity_action = menu.addAction("Activity…")
        activity_action.triggered.connect(self.open_activity_dialog)

        # Shop temporarily hidden from the menu (work in progress). The dialog
        # and its handler stay in the codebase; re-enable by uncommenting:
        # shop_action = menu.addAction("Open Shop…")
        # shop_action.triggered.connect(self._open_shop)

        # Focus is fully automatic now (earned from activity) — no menu action.
        menu.addSeparator()

        # Rebuild the list every time so freshly-installed chars appear without restart.
        self.available_images = char_catalog.scan_all()
        if len(self.available_images) > 0:
            images_menu = menu.addMenu("Chars")
            for img_name in self.available_images:
                action = images_menu.addAction(img_name)
                if img_name == self.file_name:
                    action.setCheckable(True)
                    action.setChecked(True)
                action.triggered.connect(lambda checked, name=img_name: self._load_image(name))
            menu.addSeparator()

        reset_action = menu.addAction("Reset")
        reset_action.triggered.connect(self._reset_position)

        update_action = menu.addAction("Update…")
        update_action.triggered.connect(self.open_update)

        if autostart.is_supported():
            login_action = menu.addAction("Autostart")
            login_action.setCheckable(True)
            login_action.setChecked(autostart.is_enabled())
            login_action.toggled.connect(autostart.set_enabled)

        # With a system tray, "Quit" from the cat only hides it to the tray —
        # the real Quit lives in the tray menu (restore via tray double-click or
        # its "Show"). Without a tray there's nowhere to hide, so keep a real Quit.
        if getattr(self, "tray_icon", None) is not None:
            hide_action = menu.addAction("Hide")
            hide_action.triggered.connect(self.hide)
        else:
            quit_action = menu.addAction("Quit")
            quit_action.triggered.connect(QtWidgets.QApplication.quit)
        menu.exec(self.mapToGlobal(pos))

    def open_llm_settings(self) -> None:
        """Open the LLM vendor settings dialog (vendor, model, test, save)."""
        try:
            if __package__:
                from .llm_settings_ui import LLMSettingsDialog
            else:
                import importlib

                LLMSettingsDialog = importlib.import_module(
                    "mycat.llm_settings_ui"
                ).LLMSettingsDialog
        except Exception:
            logger.exception("Failed to import LLM settings dialog")
            return
        dialog = LLMSettingsDialog(self, parent=self)
        dialog.exec()

    def open_github_settings(self) -> None:
        """Open the GitHub notifier settings dialog (token, filters, test)."""
        notifier = getattr(self, "github_notifier", None)
        if notifier is None:
            return
        try:
            if __package__:
                from .github_ui import GitHubDialog
            else:
                import importlib
                GitHubDialog = importlib.import_module("mycat.github_ui").GitHubDialog
        except Exception:
            logger.exception("Failed to import GitHub settings UI")
            return
        dialog = GitHubDialog(notifier, parent=self)
        dialog.show()
        dialog.raise_()

    def open_calendar_settings(self) -> None:
        """Open the calendar reminder settings dialog (ICS URL, lead time)."""
        controller = getattr(self, "calendar_controller", None)
        if controller is None:
            return
        try:
            if __package__:
                from .calendar_ui import CalendarDialog
            else:
                import importlib
                CalendarDialog = importlib.import_module("mycat.calendar_ui").CalendarDialog
        except Exception:
            logger.exception("Failed to import calendar settings UI")
            return
        dialog = CalendarDialog(controller, parent=self)
        dialog.show()
        dialog.raise_()

    def open_activity_dialog(self) -> None:
        """Open the activity diary dialog (settings + interval log)."""
        collector = getattr(self, "activity_collector", None)
        if collector is None:
            return
        try:
            if __package__:
                from .activity_ui import ActivityDialog
            else:
                import importlib
                ActivityDialog = importlib.import_module("mycat.activity_ui").ActivityDialog
        except Exception:
            logger.exception("Failed to import activity UI")
            return
        dialog = ActivityDialog(collector, focus_controller=getattr(self, "focus_controller", None), parent=self)
        dialog.show()
        dialog.raise_()

    def _open_shop(self) -> None:
        """Lazily import and show the shop dialog."""
        existing = getattr(self, "_shop_dialog", None)
        if existing is not None:
            try:
                existing.show()
                existing.raise_()
                existing.activateWindow()
                return
            except RuntimeError:
                self._shop_dialog = None  # Qt object was deleted

        try:
            if __package__:
                from .shop_ui import ShopDialog
            else:
                import importlib
                ShopDialog = importlib.import_module("mycat.shop_ui").ShopDialog
        except Exception:
            logger.exception("Failed to import shop UI")
            return

        dialog = ShopDialog(self, config_path=CFG_FILE)
        dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.destroyed.connect(lambda _=None: setattr(self, "_shop_dialog", None))
        dialog.char_installed.connect(self._on_char_installed)
        dialog.char_uninstalled.connect(self._on_char_uninstalled)
        self._shop_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _open_reminder(self) -> None:
        """Open the reminder settings dialog."""
        controller = getattr(self, "reminder_controller", None)
        if controller is not None:
            controller.open_dialog()

    def open_update(self) -> None:
        """Check the latest release; for a frozen build, offer to self-update."""
        kind = updater.install_kind()
        current = update_check.current_version()
        signals = UpdateSignals(self)
        self.update_signals = signals  # keep alive while the flow runs
        signals.checked.connect(lambda latest: self.on_update_checked(kind, current, latest))
        signals.failed.connect(self.on_update_failed)

        def check() -> None:
            try:
                signals.checked.emit(update_check.newer_release(current) or "")
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                signals.failed.emit(str(exc))

        threading.Thread(target=check, name="mycat-update-check", daemon=True).start()

    def on_update_checked(self, kind: str, current: str, latest: str) -> None:
        if not latest:
            QtWidgets.QMessageBox.information(
                self, "mycat", f"You're on the latest version ({current})."
            )
            return
        if not updater.can_self_update(kind):
            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle("mycat")
            box.setText(f"mycat {latest} is available (you have {current}).")
            box.setInformativeText(
                "You're running from source — update with git/pip, or grab a prebuilt build."
            )
            open_button = box.addButton("Open releases", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
            box.addButton(QtWidgets.QMessageBox.StandardButton.Close)
            box.exec()
            if box.clickedButton() is open_button:
                QtGui.QDesktopServices.openUrl(QtCore.QUrl(updater.RELEASES_PAGE))
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            "Update mycat",
            f"Update to {latest}? mycat will download the new build and restart.",
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self.download_update(kind)

    def download_update(self, kind: str) -> None:
        signals = self.update_signals
        dialog = QtWidgets.QProgressDialog("Downloading update…", "Cancel", 0, 100, self)
        dialog.setWindowTitle("Updating mycat")
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setValue(0)
        cancelled = threading.Event()
        dialog.canceled.connect(cancelled.set)

        signals.progress.connect(
            lambda done, total: dialog.setValue(int(done * 100 / total) if total else 0)
        )
        signals.applied.connect(lambda: (dialog.setLabelText("Restarting…"), self.finish_update()))
        signals.failed.connect(lambda message: (dialog.close(), self.on_update_failed(message)))

        def worker() -> None:
            try:
                dest = updater.staging_path(kind)

                def progress(done: int, total: int) -> None:
                    if cancelled.is_set():
                        raise RuntimeError("cancelled")
                    signals.progress.emit(done, total)

                updater.download(updater.asset_url(kind), dest, progress)
                if cancelled.is_set():
                    return
                updater.apply_and_relaunch(kind, dest)
                signals.applied.emit()
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                if not cancelled.is_set():
                    signals.failed.emit(str(exc))

        threading.Thread(target=worker, name="mycat-update", daemon=True).start()
        dialog.exec()

    def finish_update(self) -> None:
        """New build spawned — quit so the old process exits (and frees the file)."""
        flush_activity_on_quit(self)
        QtWidgets.QApplication.quit()

    def on_update_failed(self, message: str) -> None:
        logger.warning("Update failed: %s", message)
        QtWidgets.QMessageBox.warning(self, "Update failed", f"Couldn't update: {message}")

    def _on_char_installed(self, _char_id: str) -> None:
        self.available_images = char_catalog.scan_all()

    def _on_char_uninstalled(self, char_id: str) -> None:
        self.available_images = char_catalog.scan_all()
        if self.file_name == char_id and self.available_images:
            self._load_image(self.available_images[0])
    
    def _schedule_next_animation(self) -> None:
        """Schedule the next PNG -> GIF transition with a single-shot timer."""
        delay_ms = max(0, int(self.wait_time * 1000))
        QtCore.QTimer.singleShot(delay_ms, self._start_animation)

    def _start_animation(self) -> None:
        """Switch from static PNG to one-shot GIF playback."""
        if self.state != 'png':
            return

        gif_size = self.gif_movie.scaledSize()
        logger.debug(
            f"Playing {self.file_name}.zip {self.original_size.width()}x{self.original_size.height()} > "
            f"{gif_size.width()}x{gif_size.height()} (animation, {self.gif_duration:.2f}s)"
        )
        self.state = 'gif'

        # Reset to the in-memory first frame for a fresh start
        if not self.png_pixmap.isNull():
            self.current_pixmap = self.png_pixmap
            self.update()

        # Recreate the movie from the in-memory GIF bytes for a fresh start
        self.gif_movie = movie_from_gif_bytes(self.gif_data)
        self.gif_movie.setScaledSize(self.current_pixmap.size())
        self.gif_movie.setCacheMode(QtGui.QMovie.CacheMode.CacheAll)
        self.gif_movie.setSpeed(100)
        self.gif_movie.jumpToFrame(0)

        # Start manual frame-by-frame animation with per-frame delays
        self.current_frame = 0
        self.animation_timer.stop()
        if self.frame_delays:
            self.animation_timer.start(self.frame_delays[0])
        else:
            self.animation_timer.start(100)

    def _on_animation_frame(self) -> None:
        """Manually advance to next frame at controlled speed."""
        frame_count = self.gif_movie.frameCount()

        # Check if we've completed the animation
        if self.current_frame >= frame_count:
            self.animation_timer.stop()
            logger.debug(f"Animation complete for {self.file_name} ({frame_count} frames)")
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

    def _complete_switch_to_png(self) -> None:
        """Complete the switch from GIF to PNG state."""
        if self.state == 'gif':
            # Switch to PNG state
            self.state = 'png'

            # Reuse the in-memory first frame
            static_pixmap = self.png_pixmap
            if not static_pixmap.isNull():
                self.current_pixmap = static_pixmap
                self.first_frame_pixmap = static_pixmap

            logger.debug(
                f"Playing {self.file_name}.zip {self.original_size.width()}x{self.original_size.height()} > "
                f"{self.png_pixmap.width()}x{self.png_pixmap.height()} (first_frame, {self.wait_time:.1f}s static)"
            )
            self.update()
            self._schedule_next_animation()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """Paint the current pixmap (+ tracking pupils for interactive chars)."""
        mode = getattr(self, "_pack_mode", None) if self.char_pack is not None else None

        # Centre the pixmap in the widget.
        widget_rect = self.rect()
        pixmap_rect = self.current_pixmap.rect()
        x = (widget_rect.width() - pixmap_rect.width()) // 2
        y = (widget_rect.height() - pixmap_rect.height()) // 2

        # Update the silhouette mask BEFORE painting: the backing-store -> screen
        # blit at the end of this paint is clipped to the *current* mask, so any
        # pixels newly revealed by a shape change (e.g. switching to a char
        # with a larger silhouette) must be inside the mask now, or they never
        # get blitted and stay as stale/black framebuffer until the next repaint.
        if self.shape_mask_enabled:
            self.refresh_shape_mask(x, y)

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.drawPixmap(x, y, self.current_pixmap)
        if mode == "open":
            self._draw_pupils(painter, x, y)
        painter.end()

    def refresh_shape_mask(self, x: int, y: int) -> None:
        """Clip the window to the current pixmap's alpha silhouette (no-compositor path).

        Recomputed only when the frame/position actually changes (cache key guard),
        so the setMask never triggers a repaint loop.
        """
        pixmap = self.current_pixmap
        key = (pixmap.cacheKey(), x, y, self.width(), self.height())
        if key == self.shape_mask_key:
            return
        self.shape_mask_key = key

        # Reuse the silhouette region per frame — building QRegion from a big
        # bitmap each paint is what made multi-frame chars lag.
        cache = getattr(self, "_mask_cache", None)
        region = cache.get(pixmap.cacheKey()) if cache is not None else None
        if region is None:
            bitmap = pixmap.mask()
            if bitmap.isNull():
                self.clearMask()
                return
            region = QtGui.QRegion(bitmap)
            if cache is not None:
                cache[pixmap.cacheKey()] = region
        self.setMask(region.translated(x, y) if (x or y) else region)

        # Growing the shape reveals window area the X server does not auto-expose
        # (no compositor), so the just-painted backing store never reaches those
        # newly-unmasked pixels — they linger as stale/black framebuffer. Schedule
        # one more paint now that the new mask is in effect to fill them. The
        # cache-key guard above makes that follow-up paint a no-op for the mask,
        # so this settles in a single extra frame (no repaint loop). Without it a
        # char switch onto a static frame freezes the gap as black until the
        # next animation happens to repaint everything.
        self.update()

    def enterEvent(self, event: QtCore.QEvent) -> None:
        """Show the current-period tooltip immediately — no hover delay."""
        tip = self.toolTip()
        if tip:
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), tip, self)
        super().enterEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse press for dragging (+ click reaction / wake on interactive chars)."""
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._on_pack_click()
            self.dragging = True
            self.drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse move for dragging (+ counts as interaction: resets idle, wakes)."""
        if self.char_pack is not None:
            now = self._pack_now()
            self.last_interaction = now
            self._wake(now)
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
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose DEBUG logging (per-frame animation cycle, GIF timing, etc.)",
    )
    llm.add_arguments(parser)
    return parser.parse_args()

def x11_compositor_active() -> bool | None:
    """Return True/False when an X11 compositing manager is running, None if undetermined.

    Every EWMH-compliant compositor (picom, xfwm4, mutter, kwin, ...) owns the
    `_NET_WM_CM_Sn` selection while active. We query that owner via libX11 so the
    check works on any X11 desktop, not just XFCE. Returns None on non-X11
    platforms or when libX11 / the display is unavailable.
    """
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return None
    if not os.environ.get("DISPLAY"):
        return None
    try:
        import ctypes

        x11 = ctypes.CDLL("libX11.so.6")
    except OSError:
        return None

    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XDefaultScreen.restype = ctypes.c_int
    x11.XDefaultScreen.argtypes = [ctypes.c_void_p]
    x11.XInternAtom.restype = ctypes.c_ulong
    x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    x11.XGetSelectionOwner.restype = ctypes.c_ulong
    x11.XGetSelectionOwner.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

    display = x11.XOpenDisplay(None)
    if not display:
        return None
    try:
        screen = x11.XDefaultScreen(display)
        atom = x11.XInternAtom(display, f"_NET_WM_CM_S{screen}".encode(), False)
        return x11.XGetSelectionOwner(display, atom) != 0
    finally:
        x11.XCloseDisplay(display)


def x11_screen_size() -> tuple | None:
    """Root window size straight from the X server, for when Qt reports a 0x0 screen.

    Some X setups (nested or remote servers without RANDR) leave QScreen geometry
    empty even though the display has a real size. libX11's XDisplayWidth/Height
    still return the true dimensions. Returns None off X11 or when unavailable.
    """
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return None
    if not os.environ.get("DISPLAY"):
        return None
    try:
        import ctypes

        x11 = ctypes.CDLL("libX11.so.6")
    except OSError:
        return None

    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XDefaultScreen.restype = ctypes.c_int
    x11.XDefaultScreen.argtypes = [ctypes.c_void_p]
    x11.XDisplayWidth.restype = ctypes.c_int
    x11.XDisplayWidth.argtypes = [ctypes.c_void_p, ctypes.c_int]
    x11.XDisplayHeight.restype = ctypes.c_int
    x11.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

    display = x11.XOpenDisplay(None)
    if not display:
        return None
    try:
        screen = x11.XDefaultScreen(display)
        width = x11.XDisplayWidth(display, screen)
        height = x11.XDisplayHeight(display, screen)
        if width > 0 and height > 0:
            return width, height
        return None
    finally:
        x11.XCloseDisplay(display)


def usable_screen_rect() -> "QtCore.QRect":
    """Best-effort usable screen rectangle, robust to Qt reporting a 0x0 screen.

    Prefers Qt's panel-aware availableGeometry, then full geometry, then the X
    server's root size (XDisplayWidth/Height). Returns an empty rect only when
    nothing is determinable.
    """
    screen = QtWidgets.QApplication.primaryScreen()
    if screen is not None:
        for rect in (screen.availableGeometry(), screen.geometry()):
            if rect.width() > 0 and rect.height() > 0:
                return rect
    size = x11_screen_size()
    if size is not None:
        return QtCore.QRect(0, 0, size[0], size[1])
    return QtCore.QRect(0, 0, 0, 0)


def randr_monitor_count() -> int | None:
    """Number of active RANDR monitors via `xrandr --listmonitors`, or None if unknown."""
    xrandr = shutil.which("xrandr")
    if not xrandr:
        return None
    try:
        result = subprocess.run(
            [xrandr, "--listmonitors"], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in result.stdout.splitlines():
        head, sep, rest = line.partition("Monitors:")
        if sep:
            try:
                return int(rest.strip())
            except ValueError:
                return None
    return None


def ensure_virtual_monitor() -> None:
    """Register a virtual RANDR monitor when a headless/VNC X server exposes none.

    Such servers have a real framebuffer but zero active RANDR monitors, so Qt
    reports a 0x0 screen and window positioning plus menu/dialog popups break.
    Adding a monitor spanning the framebuffer makes Qt see the real screen size.
    Must run before the QApplication is created. No-op when a monitor already
    exists, on non-X11 platforms, or when xrandr is unavailable.
    """
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return
    if not os.environ.get("DISPLAY") or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return
    count = randr_monitor_count()
    if count is None or count > 0:
        return
    size = x11_screen_size()
    if size is None:
        return
    width, height = size
    mm_width = round(width / 96 * 25.4)
    mm_height = round(height / 96 * 25.4)
    geometry = f"{width}/{mm_width}x{height}/{mm_height}+0+0"
    xrandr = shutil.which("xrandr")
    if not xrandr:
        return
    try:
        subprocess.run(
            [xrandr, "--setmonitor", "mycat-virtual", geometry, "none"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return
    logger.info("No active RANDR monitor — registered virtual monitor %s so Qt sees the screen.", geometry)


def ensure_emoji_font(app) -> None:
    """Give emoji glyphs a fallback so they don't render as tofu boxes on systems
    with no emoji font (common on minimal Linux `pip install`s).

    If the system already has any emoji font (Noto Color Emoji, Segoe UI Emoji,
    Apple Color Emoji, …) this is a no-op, so colour emoji stay colour. Only when
    none is present do we register the bundled monochrome NotoEmoji and add it as
    a fallback on the application font — which flows to every widget and to the
    banners' QFont().
    """
    families = QtGui.QFontDatabase.families()
    if any("emoji" in family.lower() for family in families):
        return
    font_path = Path(__file__).resolve().parent / "assets" / "fonts" / "NotoEmoji-Regular.ttf"
    if not font_path.is_file():
        return
    font_id = QtGui.QFontDatabase.addApplicationFont(str(font_path))
    bundled = QtGui.QFontDatabase.applicationFontFamilies(font_id)
    if not bundled:
        return
    base = app.font()
    base.setFamilies([base.family(), bundled[0]])
    app.setFont(base)
    logger.info("No system emoji font — using the bundled %s fallback", bundled[0])


def make_app_icon() -> QtGui.QIcon:
    """A 😽 cat icon, used for the tray, the app icon and the splash."""
    pixmap = QtGui.QPixmap(64, 64)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    font = QtGui.QFont()
    font.setPointSize(40)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, "😽")
    painter.end()
    return QtGui.QIcon(pixmap)


def setup_tray(app, window, icon_pixmap):
    """A persistent cat icon in the system tray with a quick-action menu.

    Returns the tray icon (kept alive by the caller), or None when no system
    tray is available.
    """
    if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
        return None
    icon = QtGui.QIcon(icon_pixmap) if icon_pixmap and not icon_pixmap.isNull() else make_app_icon()
    tray = QtWidgets.QSystemTrayIcon(icon, app)
    tray.setToolTip("mycat 🐱")

    def show_window():
        window.show()
        window.raise_()

    menu = QtWidgets.QMenu(window)
    toggle_chat = getattr(window, "_toggle_llm_chat", None)
    if callable(toggle_chat):
        menu.addAction("Chat", toggle_chat)
    # Same order as the context menu: LLM, Calendar, Reminder, GitHub, Activity.
    menu.addAction("LLM…", window.open_llm_settings)
    menu.addAction("Calendar…", window.open_calendar_settings)
    menu.addAction("Reminder…", window._open_reminder)
    menu.addAction("GitHub…", window.open_github_settings)
    menu.addAction("Activity…", window.open_activity_dialog)

    # Focus is fully automatic now (earned from activity) — no tray toggle.

    menu.addAction("Reset", window._reset_position)
    menu.addAction("Update…", window.open_update)
    if autostart.is_supported():
        menu.addSeparator()
        login_action = menu.addAction("Autostart")
        login_action.setCheckable(True)
        login_action.setChecked(autostart.is_enabled())
        login_action.toggled.connect(autostart.set_enabled)
    menu.addSeparator()
    menu.addAction("Show", show_window)
    menu.addAction("Quit", QtWidgets.QApplication.quit)
    tray.setContextMenu(menu)

    def on_activated(reason):
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick:
            show_window()

    tray.activated.connect(on_activated)
    tray.show()
    return tray


def main() -> None:
    """Main entry point."""
    args = parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    app_version = update_check.current_version()
    logger.info("mycat %s", app_version)
    update_check.check_in_background(app_version)

    llm_context = llm.initialize(args)
    
    # Suppress Qt D-Bus warnings on Linux
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.theme.gnome=false")
    os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", "")
    os.environ.setdefault("QT_QPA_NO_NATIVE_MENUBAR", "1")

    # Suppress additional Qt warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    # Headless/VNC X servers may expose a framebuffer with no RANDR monitor,
    # which makes Qt see a 0x0 screen (breaks positioning and menu popups).
    # Register a virtual monitor before the QApplication reads screen geometry.
    ensure_virtual_monitor()

    # WM_CLASS instance name (read by Qt at QApplication construction). Without
    # this the taskbar uses the script name ("main.py") and groups mycat with
    # other python apps launched the same way.
    os.environ.setdefault("RESOURCE_NAME", "mycat")

    # Initialize Qt application with error handling
    try:
        app = QtWidgets.QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(True)
        ensure_emoji_font(app)
        app.setWindowIcon(make_app_icon())  # 😽 — used for the taskbar entry and dialogs
        # Give the window a distinct WM_CLASS so the taskbar doesn't group it with
        # other python "main.py" apps. setDesktopFileName drives the X11 class.
        app.setApplicationName("mycat")
        app.setDesktopFileName("mycat")
        platform_name = (app.platformName() or "").lower()
    except Exception as e:
        logger.error(f"Failed to initialize Qt application: {e}")
        sys.exit(1)
    
    # Single instance: a second launch must not spawn a second cat. Hold the
    # lock for the whole process lifetime (it is released when the process
    # exits). A lock left by a crashed instance is reclaimed automatically
    # because QLockFile records the owner PID and detects a dead owner.
    if platform_name != "offscreen":
        CFG_DIR.mkdir(parents=True, exist_ok=True)
        instance_lock = QtCore.QLockFile(str(CFG_DIR / "mycat.lock"))
        instance_lock.setStaleLockTime(0)
        if not instance_lock.tryLock(100):
            logger.info("Another mycat instance is already running — exiting.")
            sys.exit(0)

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
    available_images = scan_chars()
    logger.info(f"Found {len(available_images)} ZIP archive(s): {', '.join(available_images)}")
    
    # Load default image from INI if no image path provided
    default_image = None
    if not args.image:
        default_image = load_image_from_ini()
        if default_image and default_image not in available_images:
            logger.warning(f"Image '{default_image}' from INI not found in available images, using default: cat")
            default_image = None
    
    # Resolve the chosen char's ZIP, then branch on format: a new interactive
    # pack (static/blink/eyes/config) or a legacy single-GIF char.
    try:
        if args.image:
            zip_path = Path(args.image)
        else:
            zip_path = (char_catalog.find_char(default_image or "cat")
                        or char_catalog.find_char("cat"))
        if zip_path and char_pack.is_new_pack(zip_path):
            pack = char_pack.load_pack(zip_path)
            window = PixelCatWindow(pack.static, None, args.wait, Path(zip_path).stem,
                                    available_images, b"", pack=pack)
        else:
            png_pixmap, gif_movie, file_name, gif_data = load_packaged_images(args.image, default_image)
            logger.info(
                f"Playing {file_name}.zip (first frame) "
                f"{png_pixmap.width()}x{png_pixmap.height()} for {args.wait:.1f}s"
            )
            window = PixelCatWindow(png_pixmap, gif_movie, args.wait, file_name, available_images, gif_data)
    except Exception as e:
        logger.error(f"Error loading char: {e}")
        sys.exit(2)
    if llm_context:
        llm.attach(window, llm_context)
    
    if args.pos:
        window.move(args.pos[0], args.pos[1])

    if platform_name == "offscreen":
        logger.info("Offscreen platform detected: skipping window display.")
        QtCore.QTimer.singleShot(0, app.quit)
    else:
        window.show()
        # Persistent cat tray icon (kept on the window so it isn't GC'd).
        window.tray_icon = setup_tray(app, window, window.png_pixmap)
        # Live in the tray: hiding/closing windows no longer quits the app —
        # only the explicit Quit action does. With no tray to quit from, keep
        # the old behaviour so the user is never stuck with an invisible process.
        app.setQuitOnLastWindowClosed(window.tray_icon is None)
        # Flush the in-progress activity minute on a clean Quit.
        app.aboutToQuit.connect(lambda: flush_activity_on_quit(window))
        # First-run nudge to start on login (after the cat is up).
        QtCore.QTimer.singleShot(600, lambda: offer_autostart_on_first_run(window))

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
