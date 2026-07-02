#!/usr/bin/env python3
"""Visual flyby + settings dialog for reminders.

``FlybyWindow`` is a frameless, always-on-top, click-through overlay spanning the
screen width. It paints a cartoon plane (with the current cat char riding it)
towing a banner that carries the reminder text, then animates the whole group
across the screen once and closes itself.

``ReminderDialog`` lets the user set the message, the flight direction, and when
the reminder should fire (relative "in N minutes" or absolute "at HH:MM"), with a
Test button that launches a flyby immediately.
"""

import logging
import math
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

if __package__:
    from . import reminder as reminder_mod
else:
    import importlib

    reminder_mod = importlib.import_module("mycat.reminder")

Reminder = reminder_mod.Reminder


def has_no_x11_compositor() -> bool:
    """True when running on X11 with no compositor (transparency would be a black box).

    Reuses the detector in main.py. On such sessions FlybyWindow must clip its
    window to the drawn silhouette instead of a bounding rectangle, otherwise the
    plane sits in a black box. Returns False if the detector is unavailable.
    """
    detect = None
    try:
        from .main import x11_compositor_active as detect
    except Exception:
        try:
            from mycat.main import x11_compositor_active as detect
        except Exception:
            return False
    try:
        return detect() is False
    except Exception:
        return False
DIRECTION_LTR = reminder_mod.DIRECTION_LTR
DIRECTION_RTL = reminder_mod.DIRECTION_RTL

logger = logging.getLogger(__name__)

# (No drawing primitives need a shared outline colour anymore — the plane is a
# raster sprite, the cat is drawn raw, the flag uses ``plane_color.darker()``.)

FLAG_TEXT_LIGHT = QtGui.QColor("#ffffff")
FLAG_TEXT_DARK = QtGui.QColor("#1a1a1a")
ROPE_COLOR = QtGui.QColor(60, 50, 60, 220)

GAP = 38                       # plane edge ↔ flag horizontal gap
BASE_DURATION_MS = 20000       # one full screen crossing at speed 1.0 (≈20 s)
DEFAULT_PLANE_WIDTH = 160
FLAG_POLE_COLOR = QtGui.QColor("#3a2b33")

# Plane livery — one shared shape, four named tints. Multiply-blend keeps the
# dark outlines dark regardless of tint, so a white-base sprite recolours
# cleanly to any of these.
PLANE_COLORS = {
    "pink": QtGui.QColor("#ff6f91"),
    "white": QtGui.QColor("#f5f5f5"),
    "blue": QtGui.QColor("#4a8fe2"),
    "red": QtGui.QColor("#d94a4a"),
}


def _resolve_plane_color(name: str) -> QtGui.QColor:
    """Map a colour name (or hex) to a QColor; fall back to pink if unknown."""
    if name in PLANE_COLORS:
        return PLANE_COLORS[name]
    qc = QtGui.QColor(name)
    if qc.isValid():
        return qc
    return PLANE_COLORS["pink"]


def _tinted_pixmap(base: QtGui.QPixmap, tint: QtGui.QColor) -> QtGui.QPixmap:
    """Multiply-blend ``base`` by ``tint``, then restore the alpha mask.

    Qt's ``CompositionMode_Multiply`` is Porter-Duff "src over with multiply";
    in transparent destination pixels its source-over term wins and paints the
    raw tint colour. We therefore re-apply ``DestinationIn`` with the original
    pixmap so the alpha mask of ``base`` is preserved (transparent stays
    transparent, opaque stays opaque, RGB is multiplied).
    """
    result = QtGui.QPixmap(base.size())
    result.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(result)
    p.drawPixmap(0, 0, base)
    p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Multiply)
    p.fillRect(result.rect(), tint)
    p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_DestinationIn)
    p.drawPixmap(0, 0, base)
    p.end()
    return result


# A single fixed plane sprite ships with the package at mycat/assets/plane.png.
# The bundled PNG is already chroma-keyed (transparent background) and cropped
# to the alpha bbox — no Pillow processing happens at runtime. CANOPY_FRACS
# (cx, cy, rx, ry as fractions of the cropped sprite, in its right-facing
# orientation) tells _draw_cat_face where to plant the cat head inside the
# fuselage. Multiply-blend recolouring (pink / white / blue / red) is applied
# on top of the bundled sprite — that's the only thing the user can customize.
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
PLANES_DIR = ASSETS_DIR / "planes"
CANOPY_FRACS = (0.485, 0.103, 0.118, 0.230)  # cx, cy, rx, ry (right-facing)


def available_planes() -> list:
    """Sorted stems of the selectable plane sprites under assets/planes/."""
    if not PLANES_DIR.is_dir():
        return []
    return sorted(p.stem for p in PLANES_DIR.glob("*.png"))


def plane_sprite_path(name: str) -> Path:
    """Path to the chosen plane sprite, falling back to the bundled plane.png."""
    candidate = PLANES_DIR / f"{name}.png"
    if name and candidate.exists():
        return candidate
    return ASSETS_DIR / "plane.png"


class FlybyWindow(QtWidgets.QWidget):
    """A one-shot animated overlay: cat peeks from the cockpit of a banner plane.

    The plane is drawn with QPainterPath (streamlined fuselage, tail, wing,
    propeller disk). A trailing flag is built from a sampled polygon whose
    vertices follow a sine wave whose amplitude grows linearly from 0 at the
    leading pole to ``WAVE_AMP_MAX`` at the trailing edge — that gives real
    cloth-like ripple. Text on the flag is pre-rendered upright and then sliced
    into thin vertical strips, each translated to follow the local wave height,
    so the message bends with the cloth without unreadable distortion.
    """

    def __init__(self, cat_pixmap, reminder, parent=None) -> None:
        flags = QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.Tool
        app = QtWidgets.QApplication.instance()
        platform_name = (app.platformName() or "").lower() if app is not None else ""
        if platform_name != "offscreen":
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        super().__init__(parent, flags)

        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # We DELIBERATELY do not set WA_TransparentForMouseEvents /
        # WindowTransparentForInput here — the user can grab the plane to drag
        # it. paintEvent calls setMask() each frame so only the plane+flag
        # bounding box absorbs events; everywhere else in the band the click
        # passes through to the window beneath.
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Drag to move • Right-click for options")

        # Drag state — clicking the plane pauses the flight and lets the user
        # park it; right-click brings up a resume/close menu.
        self._dragging = False
        self._drag_anchor = QtCore.QPointF()
        self._drag_start_offset = QtCore.QPointF()
        self._user_offset = QtCore.QPointF(0.0, 0.0)

        # Without an X11 compositor a translucent window renders its transparent
        # pixels black, so a bounding-box mask would put the plane in a black box.
        # In that case clip the window to the actual drawn silhouette instead.
        # MYCAT_SHAPE_MASK=1/0 forces or disables it (mirrors PixelCatWindow).
        force_mask = os.environ.get("MYCAT_SHAPE_MASK")
        if force_mask in ("0", "1"):
            self.silhouette_mask = force_mask == "1"
        else:
            self.silhouette_mask = platform_name == "xcb" and has_no_x11_compositor()
        # Geometry of what was last painted, captured by the _draw_* helpers so
        # the mask can follow the real shapes (set each frame in paintEvent).
        self.flag_shape = None
        self.flag_pole = None
        self.rope_path = None
        self.plane_blit = None
        self.cat_blit = None

        # Optional link — announcements (a GitHub PR, the morning digest)
        # attach a URL; a double-click or the context menu opens it.
        self.link_url = str(getattr(reminder, "url", "") or "")
        if self.link_url:
            self.setToolTip("Double-click to open • Drag to move • Right-click for options")

        self._text = (reminder.text or reminder_mod.DEFAULT_TEXT).strip() or reminder_mod.DEFAULT_TEXT
        self._ltr = reminder.normalized_direction() != DIRECTION_RTL
        self._progress = 0.0
        # Set on start(); paintEvent reads monotonic time so the flag ripple and
        # propeller spin advance smoothly regardless of the position easing curve.
        self._start_time = None

        # Plane colour — applied to the sprite via multiply-blend. Same shape,
        # four liveries, all chosen client-side.
        self._plane_color = _resolve_plane_color(getattr(reminder, "plane_color", "pink"))

        # Chosen plane sprite (assets/planes/<name>.png, falling back to the
        # bundled plane.png). Tint baked in here so per-frame drawing is just a
        # drawPixmap call. If the PNG is missing, paintEvent draws only the flag.
        # Only plane1 has a cockpit the cat peeks from; the rest fly cat-free.
        self.plane_name = getattr(reminder, "plane", "plane1")
        sprite_path = plane_sprite_path(self.plane_name)
        sprite = QtGui.QPixmap(str(sprite_path))
        if sprite.isNull():
            logger.warning("Plane sprite missing at %s — flyby will be flag-only",
                            sprite_path)
            self._plane_sprite = None
        else:
            self._plane_sprite = _tinted_pixmap(sprite, self._plane_color)
        self._canopy_fracs = CANOPY_FRACS

        # Plane size — width is user-configurable, height follows the sprite's
        # cropped aspect ratio so the plane never gets squashed. Without a
        # sprite, fall back to a sensible default ratio so the geometry math
        # still works.
        self._plane_width = max(80, int(getattr(reminder, "plane_width", DEFAULT_PLANE_WIDTH)))
        if self._plane_sprite is not None and self._plane_sprite.width() > 0:
            aspect = self._plane_sprite.height() / self._plane_sprite.width()
        else:
            aspect = 0.55
        self._plane_height = max(40, int(self._plane_width * aspect))

        # Flag height tied to the plane height so they stay proportional
        # regardless of the user's chosen plane width.
        self._flag_h = max(36, int(self._plane_height * 0.58))
        # Band tall enough for the plane + bob + flag with some breathing room.
        self._band_h = max(self._plane_height, self._flag_h) + 40

        # Cat crop + scale picked so the visible cat is HEAD + SHOULDERS +
        # UPPER BODY (top 75% of the source) without getting wider than before.
        # 0.75 crop has aspect ~1.27 (vs 1.73 for top half), so target_h=0.46×ph
        # still lands at the same width (~48 px at ph=82) but yields a 36%
        # taller sprite — chest/neck now fills the cockpit area under the face
        # instead of leaving empty fuselage there.
        self._cat_face_pixmap = None
        if cat_pixmap is not None and not cat_pixmap.isNull():
            head_h = max(8, int(cat_pixmap.height() * 0.75))
            head = cat_pixmap.copy(0, 0, cat_pixmap.width(), head_h)
            target_h = int(self._plane_height * 0.46)
            self._cat_face_pixmap = head.scaledToHeight(
                target_h, QtCore.Qt.TransformationMode.FastTransformation
            )

        # Geometry: cover the full primary screen so the user can drag the plane
        # vertically anywhere on it. The plane normally sits inside a band at
        # ``band_top`` (~10% from the top). The setMask() call in paintEvent
        # keeps the rest of the screen click-through.
        screen = QtWidgets.QApplication.primaryScreen().geometry()
        self._screen_w = screen.width()
        self._band_top = int(screen.height() * 0.10)
        self.setGeometry(screen.x(), screen.y(), self._screen_w, screen.height())

        self._banner_w = self._compute_flag_length()

        speed = max(0.25, float(getattr(reminder, "speed", 1.0)))
        self._anim = QtCore.QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(int(BASE_DURATION_MS / speed))
        self._anim.setEasingCurve(QtCore.QEasingCurve.Type.InOutSine)
        self._anim.valueChanged.connect(self._on_value)
        # On finish we DON'T just close — if the user dragged the plane back,
        # it could still be on screen at progress=1.0 (the main animation
        # tracks a fixed travel distance, drag offsets aren't part of that).
        # _after_anim_finished checks the actual on-screen position and either
        # closes or starts an exit animation that pushes the plane the rest of
        # the way off the screen.
        self._anim.finished.connect(self._after_anim_finished)
        self._exit_anim = None  # set when an exit motion is in progress

    # -- public -------------------------------------------------------------

    def start(self) -> None:
        self._start_time = time.monotonic()
        self.show()
        self.raise_()
        self._anim.start()

    # -- sizing -------------------------------------------------------------

    def _banner_font(self) -> QtGui.QFont:
        font = QtGui.QFont()
        font.setBold(True)
        # 0.40 of the flag height: banner texts got longer (GitHub events,
        # digests), a smaller face keeps the flag from growing screen-wide.
        font.setPixelSize(max(10, int(self._flag_h * 0.40)))
        return font

    def _compute_flag_length(self) -> int:
        fm = QtGui.QFontMetrics(self._banner_font())
        text_w = fm.horizontalAdvance(self._text)
        max_w = int(self._screen_w * 0.6)
        # Min length scales with plane size so a tiny plane doesn't drag a
        # ridiculously long flag and vice versa.
        min_w = max(160, int(self._plane_width * 1.0))
        return max(min_w, min(text_w + 80, max_w))

    def _group_width(self) -> int:
        return self._banner_w + GAP + self._plane_width

    # -- animation ----------------------------------------------------------

    def _on_value(self, value) -> None:
        self._progress = float(value)
        self.update()

    # -- painting -----------------------------------------------------------

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)

        # Forget last frame's shapes; the _draw_* helpers re-record what they paint.
        self.flag_shape = None
        self.flag_pole = None
        self.rope_path = None
        self.plane_blit = None
        self.cat_blit = None

        t = 0.0 if self._start_time is None else max(0.0, time.monotonic() - self._start_time)
        bob = math.sin(t * 1.9) * 2.5  # gentle vertical "alive" motion

        pw, ph = self._plane_width, self._plane_height
        gw = self._group_width()
        travel = self._screen_w + gw
        if self._ltr:
            left = -gw + self._progress * travel
            plane_x = left + self._banner_w + GAP
            flag_attach_x = plane_x - 18           # flag attaches just behind the tail
            flag_dir = -1                          # flag trails to the left
        else:
            left = self._screen_w - self._progress * travel
            plane_x = left
            flag_attach_x = plane_x + pw + 18
            flag_dir = +1                          # flag trails to the right

        # Apply manual drag offset from the mouse handlers — the plane, flag,
        # rope and cat all move as one rigid group.
        plane_x += self._user_offset.x()
        flag_attach_x += self._user_offset.x()
        plane_y = self._band_top + (self._band_h - ph - 18) + bob + self._user_offset.y()
        plane_rect = QtCore.QRectF(plane_x, plane_y, pw, ph)

        # Rope: from plane belly (behind the wing) up to the flag.
        rope_from_frac_x = 0.18 if self._ltr else 0.82
        rope_from = QtCore.QPointF(
            plane_rect.x() + pw * rope_from_frac_x,
            plane_rect.y() + ph * 0.74,
        )
        flag_attach = QtCore.QPointF(flag_attach_x, plane_rect.y() + ph * 0.60)

        # Draw order: flag/rope, then the cat BEHIND the plane, then the plane
        # sprite on top. The plane silhouette hides the cat's body so only the
        # head peeks above it. With the taller crop (head+shoulders+chest), the
        # peek now shows roughly the full head — not just the ear tips.
        self._draw_flag(painter, flag_attach, flag_dir, self._banner_w, self._flag_h, self._text)
        if self._plane_sprite is not None:
            self._draw_rope(painter, rope_from, flag_attach)
            if self.plane_name == "plane1":
                self._draw_cat_face(painter, plane_rect, facing_right=self._ltr)
            self._draw_plane(painter, plane_rect, facing_right=self._ltr)

        # Refresh the input mask so only the plane+flag bbox is interactive.
        # Areas outside this region are click-through to whatever is below.
        self._update_input_mask(plane_rect, flag_attach, flag_dir)

    def _update_input_mask(self, plane_rect, flag_attach, flag_dir) -> None:
        # Without a compositor, clip to the drawn silhouette so transparent areas
        # are not painted black; with a compositor keep the cheap bounding box.
        if self.silhouette_mask:
            region = self.silhouette_region()
            if not region.isEmpty():
                self.setMask(region)
                return

        flag_x = flag_attach.x() - self._banner_w if flag_dir < 0 else flag_attach.x()
        flag_rect = QtCore.QRectF(flag_x, flag_attach.y() - self._flag_h / 2,
                                    self._banner_w, self._flag_h)
        if self._plane_sprite is not None:
            # Cat head pokes above the plane top — include that area in the mask
            # so the click-region matches what's actually drawn on screen.
            cat_top = plane_rect.y() - self._plane_height * 0.30
            union_rect = plane_rect.united(flag_rect)
            union_rect.setTop(min(union_rect.top(), cat_top))
        else:
            union_rect = flag_rect
        union_rect = union_rect.adjusted(-8, -8, 8, 8).toRect()
        self.setMask(QtGui.QRegion(union_rect))

    def silhouette_region(self) -> QtGui.QRegion:
        """Region matching the actually-drawn shapes (flag, pole, rope, plane, cat).

        Used on X11 without a compositor so the window clips to the silhouette
        instead of a bounding box (which would render a black rectangle).
        """
        region = QtGui.QRegion()
        if self.flag_shape is not None:
            region += QtGui.QRegion(self.flag_shape.toPolygon())
        if self.flag_pole is not None:
            region += QtGui.QRegion(self.flag_pole.toRect())
        if self.rope_path is not None:
            stroker = QtGui.QPainterPathStroker()
            stroker.setWidth(6)
            outline = stroker.createStroke(self.rope_path).toFillPolygon().toPolygon()
            region += QtGui.QRegion(outline)
        for blit in (self.cat_blit, self.plane_blit):
            if blit is None:
                continue
            pixmap, bx, by = blit
            bitmap = pixmap.mask()
            if bitmap.isNull():
                region += QtGui.QRegion(int(bx), int(by), pixmap.width(), pixmap.height())
            else:
                region += QtGui.QRegion(bitmap).translated(int(bx), int(by))

        # A window mask that is entirely off-screen stops the window from
        # receiving paint events, which would freeze the mask there forever and
        # the plane would never fly in. While the group is still fully off-screen,
        # keep a 2x2 on-screen anchor at the entry edge so repaints keep coming;
        # once any part of the plane is on screen the silhouette itself keeps the
        # cycle alive and no anchor (and no stray pixel) is added.
        screen = QtCore.QRect(0, 0, self._screen_w, self.height())
        if not region.boundingRect().intersects(screen):
            anchor_x = 0 if self._ltr else max(0, self._screen_w - 2)
            anchor_y = self._band_top + self._band_h // 2
            region += QtGui.QRegion(anchor_x, anchor_y, 2, 2)
        return region

    # -- flag (static rectangle, plane-coloured) ----------------------------

    def _draw_flag(self, painter, attach, direction, length, height, text) -> None:
        # Classic banner pennant: rectangular cloth on a pole at the attach
        # edge, with a V-notch (swallowtail) cut into the trailing edge. This
        # silhouette reads instantly as a "flag/banner" rather than a notification
        # badge — the rounded rectangle we had before was the wrong cue.
        notch_depth = height * 0.30
        pole_w = max(2.5, height * 0.07)
        top_y = attach.y() - height / 2
        bot_y = attach.y() + height / 2
        notch_y = attach.y()

        if direction < 0:  # flag extends LEFT of the attach point
            right_x = attach.x()
            left_x = attach.x() - length
            notch_x = left_x + notch_depth
            polygon = QtGui.QPolygonF([
                QtCore.QPointF(right_x, top_y),
                QtCore.QPointF(right_x, bot_y),
                QtCore.QPointF(left_x, bot_y),
                QtCore.QPointF(notch_x, notch_y),
                QtCore.QPointF(left_x, top_y),
            ])
            pole_x = right_x
            text_left = notch_x + 6
            text_right = right_x - pole_w - 6
        else:              # flag extends RIGHT of the attach point
            left_x = attach.x()
            right_x = attach.x() + length
            notch_x = right_x - notch_depth
            polygon = QtGui.QPolygonF([
                QtCore.QPointF(left_x, top_y),
                QtCore.QPointF(left_x, bot_y),
                QtCore.QPointF(right_x, bot_y),
                QtCore.QPointF(notch_x, notch_y),
                QtCore.QPointF(right_x, top_y),
            ])
            pole_x = left_x
            text_left = left_x + pole_w + 6
            text_right = notch_x - 6

        # Cloth
        painter.setBrush(self._plane_color)
        painter.setPen(QtGui.QPen(self._plane_color.darker(150), 2))
        painter.drawPolygon(polygon)
        self.flag_shape = polygon

        # Pole — a thin dark vertical bar overlapping the attach edge so the
        # cloth reads as "sewn to the pole".
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(FLAG_POLE_COLOR)
        pole_rect = QtCore.QRectF(pole_x - pole_w / 2, top_y - 5, pole_w, height + 10)
        painter.drawRect(pole_rect)
        self.flag_pole = pole_rect

        # Text — luminance-aware contrast so a white-livery flag stays readable.
        c = self._plane_color
        lum = (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) / 255.0
        text_color = FLAG_TEXT_DARK if lum > 0.7 else FLAG_TEXT_LIGHT

        font = self._banner_font()
        fm = QtGui.QFontMetrics(font)
        inner_w = max(20, int(text_right - text_left))
        while font.pixelSize() > 11 and fm.horizontalAdvance(text) > inner_w:
            font.setPixelSize(font.pixelSize() - 1)
            fm = QtGui.QFontMetrics(font)
        elided = fm.elidedText(text, QtCore.Qt.TextElideMode.ElideRight, inner_w)
        text_rect = QtCore.QRectF(text_left, top_y, inner_w, height)
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(text_rect, QtCore.Qt.AlignmentFlag.AlignCenter, elided)

    def _draw_rope(self, painter, p_from, p_to) -> None:
        mid = QtCore.QPointF((p_from.x() + p_to.x()) / 2,
                             max(p_from.y(), p_to.y()) + 16)
        path = QtGui.QPainterPath(p_from)
        path.quadTo(mid, p_to)
        pen = QtGui.QPen(ROPE_COLOR, 2)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        self.rope_path = path

    # -- plane --------------------------------------------------------------

    def _draw_plane(self, painter, rect, facing_right) -> None:
        """Render the PNG plane sprite (nearest-neighbour, aspect-preserved).

        ``FlybyWindow`` only flies when a sprite is loaded — paintEvent skips
        the plane (and the cat face) entirely if ``_plane_sprite`` is ``None``.
        """
        sprite = self._plane_sprite
        if sprite is None:
            return
        if not facing_right:
            sprite = sprite.transformed(QtGui.QTransform().scale(-1, 1))
        target_w = int(rect.width())
        target_h = int(rect.height())
        scaled = sprite.scaled(
            target_w, target_h,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.FastTransformation,
        )
        cw, ch = scaled.width(), scaled.height()
        px = int(rect.x() + (rect.width() - cw) / 2)
        py = int(rect.y() + (rect.height() - ch) / 2)
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawPixmap(px, py, scaled)
        painter.restore()
        self.plane_blit = (scaled, px, py)

    # -- cat face inside the cockpit ---------------------------------------

    def _draw_cat_face(self, painter, plane_rect, facing_right) -> None:
        """Stamp the cat head at the cockpit. No clip, no glass, no rim — the
        plane sprite is drawn AFTER this so it covers most of the cat; only the
        top of the head pokes above the plane's silhouette."""
        if self._cat_face_pixmap is None or self._cat_face_pixmap.isNull():
            return
        x, y, w, h = plane_rect.x(), plane_rect.y(), plane_rect.width(), plane_rect.height()
        cx_frac_r, cy_frac, _rx_frac, _ry_frac = self._canopy_fracs
        cx_frac = cx_frac_r if facing_right else (1.0 - cx_frac_r)
        canopy_cx = x + w * cx_frac
        canopy_cy = y + h * cy_frac

        cat = self._cat_face_pixmap
        if not facing_right:
            cat = cat.transformed(QtGui.QTransform().scale(-1, 1))
        cw, ch = cat.width(), cat.height()
        px = int(canopy_cx - cw / 2)
        py = int(canopy_cy - ch / 2)

        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawPixmap(px, py, cat)
        painter.restore()
        self.cat_blit = (cat, px, py)

    # -- interaction: pause + drag + context menu ---------------------------

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            # Pause whichever animation is running so the user has a stationary
            # target to grab. The exit animation is fully stopped — mouseRelease
            # will rebuild it from the new dropped position if the plane is
            # still on screen.
            if self._anim.state() == QtCore.QAbstractAnimation.State.Running:
                self._anim.pause()
            if self._exit_anim is not None:
                self._exit_anim.stop()
                self._exit_anim = None
            self._dragging = True
            self._drag_anchor = event.globalPosition()
            self._drag_start_offset = QtCore.QPointF(self._user_offset)
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._dragging:
            delta = event.globalPosition() - self._drag_anchor
            self._user_offset = QtCore.QPointF(
                self._drag_start_offset.x() + delta.x(),
                self._drag_start_offset.y() + delta.y(),
            )
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
            # Continue the flight from the dropped position. The accumulated
            # ``_user_offset`` is intentionally kept so the plane resumes from
            # wherever the user parked it rather than snapping back.
            if self._anim.state() == QtCore.QAbstractAnimation.State.Paused:
                self._anim.setPaused(False)
            elif self._anim.state() == QtCore.QAbstractAnimation.State.Stopped:
                # Main animation has already played out. Re-issue an exit
                # animation from the new position (or close if the plane is
                # already past every screen edge).
                if self._is_plane_fully_offscreen():
                    self.close()
                else:
                    self._begin_exit_animation()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:
        Paused = QtCore.QAbstractAnimation.State.Paused
        Running = QtCore.QAbstractAnimation.State.Running
        main_paused = self._anim.state() == Paused
        main_running = self._anim.state() == Running
        exit_paused = self._exit_anim is not None and self._exit_anim.state() == Paused
        exit_running = self._exit_anim is not None and self._exit_anim.state() == Running

        menu = QtWidgets.QMenu(self)
        if self.link_url:
            menu.addAction("Open link", self.open_link)
            menu.addSeparator()
        if main_paused or exit_paused or self._anim.state() == QtCore.QAbstractAnimation.State.Stopped:
            menu.addAction("Resume flight", self._resume_flight)
        elif main_running or exit_running:
            menu.addAction("Pause flight", self._pause_flight)
        menu.addSeparator()
        menu.addAction("Close", self.close)
        menu.exec(event.globalPos())

    def open_link(self) -> None:
        """Open the announcement's URL in the browser and end the flight."""
        if not self.link_url:
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(self.link_url))
        self.close()

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self.link_url:
            self.open_link()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _pause_flight(self) -> None:
        if self._anim.state() == QtCore.QAbstractAnimation.State.Running:
            self._anim.pause()
        if self._exit_anim is not None \
                and self._exit_anim.state() == QtCore.QAbstractAnimation.State.Running:
            self._exit_anim.pause()

    def _resume_flight(self) -> None:
        # Resume whichever animation was paused. Resuming the main animation
        # keeps the drag offset; resuming the exit animation continues the
        # linear push toward the screen edge. If the main animation already
        # finished and there's no exit animation, start one from the current
        # parked position (or close if the plane is already off-screen).
        if self._anim.state() == QtCore.QAbstractAnimation.State.Paused:
            self._anim.setPaused(False)
        elif self._exit_anim is not None \
                and self._exit_anim.state() == QtCore.QAbstractAnimation.State.Paused:
            self._exit_anim.setPaused(False)
        elif self._anim.state() == QtCore.QAbstractAnimation.State.Stopped:
            if self._is_plane_fully_offscreen():
                self.close()
            else:
                self._begin_exit_animation()

    # -- exit-from-screen: keep moving the plane until it's fully off ------

    def _after_anim_finished(self) -> None:
        """Main animation ran out — close only if the plane is actually gone."""
        if self._is_plane_fully_offscreen():
            self.close()
        else:
            self._begin_exit_animation()

    def _compute_current_plane_position(self) -> tuple[float, float]:
        """Return the plane's current (x, y) in window coords, drag offset included."""
        ph = self._plane_height
        gw = self._group_width()
        travel = self._screen_w + gw
        if self._ltr:
            plane_x = -gw + self._progress * travel + self._banner_w + GAP
        else:
            plane_x = self._screen_w - self._progress * travel
        plane_x += self._user_offset.x()
        plane_y = (self._band_top + (self._band_h - ph - 18)
                    + self._user_offset.y())
        return plane_x, plane_y

    def _is_plane_fully_offscreen(self) -> bool:
        plane_x, plane_y = self._compute_current_plane_position()
        pw, ph = self._plane_width, self._plane_height
        return (plane_x + pw <= 0 or plane_x >= self._screen_w
                or plane_y + ph <= 0 or plane_y >= self.height())

    def _begin_exit_animation(self) -> None:
        """Linearly continue pushing the plane in the flight direction until it
        clears the screen. Used after the main animation has finished but the
        plane is still visible (e.g. because the user dragged it back)."""
        if self._exit_anim is not None:
            self._exit_anim.stop()
        plane_x, _ = self._compute_current_plane_position()
        pw = self._plane_width
        if self._ltr:
            # How far the offset needs to move right so plane_x crosses the right edge
            dx_needed = (self._screen_w + 20) - plane_x
        else:
            dx_needed = -(plane_x + pw + 20)
        target_offset_x = self._user_offset.x() + dx_needed
        # Linear motion at "natural cruising speed" matching the main animation.
        cruise_px_per_sec = (self._screen_w + self._group_width()) / (BASE_DURATION_MS / 1000.0)
        duration_ms = max(150, int(abs(dx_needed) / max(1.0, cruise_px_per_sec) * 1000))

        self._exit_anim = QtCore.QVariantAnimation(self)
        self._exit_anim.setStartValue(float(self._user_offset.x()))
        self._exit_anim.setEndValue(float(target_offset_x))
        self._exit_anim.setDuration(duration_ms)
        self._exit_anim.setEasingCurve(QtCore.QEasingCurve.Type.Linear)
        self._exit_anim.valueChanged.connect(self._on_exit_value)
        self._exit_anim.finished.connect(self.close)
        self._exit_anim.start()

    def _on_exit_value(self, value) -> None:
        self._user_offset = QtCore.QPointF(float(value), self._user_offset.y())
        self.update()


class ReminderDialog(QtWidgets.QDialog):
    """Edit the message, direction and timing of the reminder."""

    def __init__(self, controller, reminder, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("Reminder")
        self.setMinimumWidth(380)
        # Force a complete light theme on the whole dialog. Styling only the input
        # fields left the dialog background, labels, group box and buttons to the
        # system palette, which is unreadable (dark text on dark) under a dark
        # desktop theme. Pin every widget type to dark-on-light with a pink accent.
        self.setStyleSheet(
            "QDialog { background: #ffffff; color: #1c1c1c; }"
            "QLabel, QRadioButton, QCheckBox, QGroupBox {"
            " color: #1c1c1c; background: transparent; }"
            "QGroupBox { border: 1px solid #d6d6d6; border-radius: 6px;"
            " margin-top: 8px; padding-top: 6px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px;"
            " padding: 0 4px; color: #1c1c1c; }"
            "QLineEdit, QSpinBox, QTimeEdit, QComboBox {"
            " color: #1c1c1c; background: #ffffff;"
            " border: 1px solid #c0c0c0; border-radius: 4px; padding: 2px 4px;"
            " selection-color: white; selection-background-color: #ff6f91; }"
            "QComboBox QAbstractItemView {"
            " color: #1c1c1c; background: #ffffff;"
            " selection-color: white; selection-background-color: #ff6f91; }"
            "QPushButton {"
            " color: #1c1c1c; background: #f0f0f0;"
            " border: 1px solid #c0c0c0; border-radius: 4px; padding: 4px 14px; }"
            "QPushButton:hover { background: #e7e7e7; }"
            "QPushButton:disabled { color: #9a9a9a; background: #f5f5f5; }"
        )

        existing = reminder or Reminder()

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        self._text_edit = QtWidgets.QLineEdit(existing.text)
        self._text_edit.setPlaceholderText("What should the cat remind you about?")
        self._text_edit.setMaxLength(120)
        form.addRow("Message", self._text_edit)

        self._direction = QtWidgets.QComboBox()
        self._direction.addItem("Left → Right", DIRECTION_LTR)
        self._direction.addItem("Right → Left", DIRECTION_RTL)
        idx = self._direction.findData(existing.normalized_direction())
        self._direction.setCurrentIndex(max(0, idx))
        form.addRow("Direction", self._direction)

        self.plane_combo = QtWidgets.QComboBox()
        self.plane_combo.setIconSize(QtCore.QSize(48, 24))
        for name in available_planes():
            sprite = QtGui.QPixmap(str(plane_sprite_path(name)))
            icon = QtGui.QIcon(
                sprite.scaled(
                    48, 24,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
            ) if not sprite.isNull() else QtGui.QIcon()
            self.plane_combo.addItem(icon, name.capitalize(), name)
        idx = self.plane_combo.findData(existing.plane)
        self.plane_combo.setCurrentIndex(max(0, idx))
        form.addRow("Plane", self.plane_combo)

        self._color = QtWidgets.QComboBox()
        for name, qcolor in PLANE_COLORS.items():
            swatch = QtGui.QPixmap(20, 20)
            swatch.fill(qcolor)
            self._color.addItem(QtGui.QIcon(swatch), name.capitalize(), name)
        idx = self._color.findData(existing.plane_color)
        self._color.setCurrentIndex(max(0, idx))
        form.addRow("Plane color", self._color)

        self._plane_width_spin = QtWidgets.QSpinBox()
        self._plane_width_spin.setRange(120, 500)
        self._plane_width_spin.setSuffix(" px")
        # Height follows the sprite's aspect ratio — only the width is user-set.
        self._plane_width_spin.setValue(max(120, int(existing.plane_width)))
        form.addRow("Plane width", self._plane_width_spin)

        layout.addLayout(form)

        # Timing: "in N minutes" or "at HH:MM".
        timing_box = QtWidgets.QGroupBox("When")
        timing_layout = QtWidgets.QGridLayout(timing_box)

        self._in_radio = QtWidgets.QRadioButton("In")
        self._in_spin = QtWidgets.QSpinBox()
        self._in_spin.setRange(0, 1440)
        self._in_spin.setSuffix(" min")
        # 0 = fire on the very next scheduler tick (within ~1s).
        self._in_spin.setSpecialValueText("now")
        self._in_spin.setValue(max(0, existing.in_minutes))

        self._at_radio = QtWidgets.QRadioButton("At")
        self._at_time = QtWidgets.QTimeEdit()
        self._at_time.setDisplayFormat("HH:mm")
        if existing.mode == "at" and existing.fire_at is not None:
            self._at_time.setTime(QtCore.QTime(existing.fire_at.hour, existing.fire_at.minute))
        else:
            self._at_time.setTime(QtCore.QTime.currentTime().addSecs(600))

        timing_layout.addWidget(self._in_radio, 0, 0)
        timing_layout.addWidget(self._in_spin, 0, 1)
        timing_layout.addWidget(self._at_radio, 1, 0)
        timing_layout.addWidget(self._at_time, 1, 1)

        self._repeat = QtWidgets.QCheckBox("Repeat daily")
        self._repeat.setChecked(existing.repeat_daily)
        timing_layout.addWidget(self._repeat, 2, 0, 1, 2)

        layout.addWidget(timing_box)

        if existing.mode == "at":
            self._at_radio.setChecked(True)
        else:
            self._in_radio.setChecked(True)
        self._sync_timing_enabled()
        self._in_radio.toggled.connect(self._sync_timing_enabled)

        # Buttons: Test, Reset (left) · Save, Close (right) — same order as
        # every other mycat dialog.
        buttons = QtWidgets.QHBoxLayout()
        test_btn = QtWidgets.QPushButton("Test")
        reset_btn = QtWidgets.QPushButton("Reset")
        close_btn = QtWidgets.QPushButton("Close")
        save_btn = QtWidgets.QPushButton("Save")
        save_btn.setDefault(True)
        test_btn.clicked.connect(self._on_test)
        reset_btn.clicked.connect(self._on_clear)
        close_btn.clicked.connect(self.reject)
        save_btn.clicked.connect(self._on_save)
        buttons.addWidget(test_btn)
        buttons.addWidget(reset_btn)
        buttons.addStretch(1)
        buttons.addWidget(save_btn)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

    def _sync_timing_enabled(self) -> None:
        in_mode = self._in_radio.isChecked()
        self._in_spin.setEnabled(in_mode)
        self._at_time.setEnabled(not in_mode)
        # Daily repeat only makes sense for a fixed time of day.
        self._repeat.setEnabled(not in_mode)
        if in_mode:
            self._repeat.setChecked(False)

    def _build_reminder(self) -> Reminder:
        text = self._text_edit.text().strip() or reminder_mod.DEFAULT_TEXT
        direction = self._direction.currentData()
        plane_color = self._color.currentData() or "pink"
        plane_width = self._plane_width_spin.value()
        plane = self.plane_combo.currentData() or "plane1"
        now = datetime.now()
        if self._in_radio.isChecked():
            minutes = self._in_spin.value()
            fire_at = now + timedelta(minutes=minutes)
            return Reminder(
                text=text,
                direction=direction,
                fire_at=fire_at,
                repeat_daily=False,
                enabled=True,
                plane_color=plane_color,
                plane_width=plane_width,
                plane=plane,
                mode="in",
                in_minutes=minutes,
            )
        qt_time = self._at_time.time()
        fire_at = now.replace(hour=qt_time.hour(), minute=qt_time.minute(), second=0, microsecond=0)
        if fire_at <= now:
            fire_at += timedelta(days=1)
        return Reminder(
            text=text,
            direction=direction,
            fire_at=fire_at,
            repeat_daily=self._repeat.isChecked(),
            enabled=True,
            plane_color=plane_color,
            plane_width=plane_width,
            plane=plane,
            mode="at",
            in_minutes=self._in_spin.value(),
        )

    def _on_test(self) -> None:
        # Force left->right when previewing? No — honour the chosen direction.
        self._controller.test(self._build_reminder())

    def _on_clear(self) -> None:
        self._controller.clear()
        self.accept()

    def _on_save(self) -> None:
        self._controller.set_reminder(self._build_reminder())
        self.accept()
