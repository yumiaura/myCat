"""Pure layout + key-to-cell mapping for the optional keyboard heatmap.

No Qt here — this module is imported both by the Qt dialog and by the X11
record thread, so it must stay dependency-free. It knows two things:

1. **Which diagram cell a keypress belongs to.** Counting is by *logical
   character* on a Latin QWERTY board: `A`/`a`/Shift+`a` all land on the `a`
   cell, `!` lands on `1`, and non-Latin input (e.g. a Cyrillic layout) maps
   to nothing and is simply not shown. Only aggregate per-cell counts ever
   exist, and only in memory — never the order, timing or text.
2. **The board to draw.** `KEYBOARD_ROWS` is a Latin QWERTY with a function
   row, modifiers and space; every key has a stable cell id, a label and a
   width in key units.
"""

from __future__ import annotations

# Shifted punctuation folds back onto its unshifted key so the heatmap counts
# by physical letter, not by the shifted glyph.
SHIFTED_TO_BASE = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7",
    "*": "8", "(": "9", ")": "0", "_": "-", "+": "=", "{": "[", "}": "]",
    "|": "\\", ":": ";", '"': "'", "<": ",", ">": ".", "?": "/", "~": "`",
}

# The unshifted glyphs that are their own cell on the board.
BASE_KEYS = set("`1234567890-=qwertyuiop[]\\asdfghjkl;'zxcvbnm,./")

# pynput's Key.<name> for the non-character keys we colour.
SPECIAL_CELLS = {
    "space": "space", "enter": "enter", "return": "enter",
    "tab": "tab", "backspace": "backspace",
}

# X11 keysyms for those same non-character keys (space arrives as 0x20 and is
# handled through the ASCII path, so it isn't listed here).
SPECIAL_KEYSYMS = {
    0xFF0D: "enter",       # XK_Return
    0xFF8D: "enter",       # XK_KP_Enter
    0xFF09: "tab",         # XK_Tab
    0xFF08: "backspace",   # XK_BackSpace
}


def char_to_cell(ch: str | None) -> str | None:
    """The board cell a produced character belongs to, or None if off-board."""
    if not ch or len(ch) != 1:
        return None
    if ch == " ":
        return "space"
    lower = ch.lower()
    if "a" <= lower <= "z":
        return lower
    if ch in SHIFTED_TO_BASE:
        return SHIFTED_TO_BASE[ch]
    if ch in BASE_KEYS:
        return ch
    return None


def cell_for_pynput_key(key) -> str | None:
    """Map a pynput key (Windows/macOS) to a board cell, or None."""
    ch = getattr(key, "char", None)
    if ch:
        return char_to_cell(ch)
    name = getattr(key, "name", None)
    if name:
        return SPECIAL_CELLS.get(name.lower())
    return None


def cell_for_keysym(keysym: int) -> str | None:
    """Map an X11 keysym to a board cell, or None (non-Latin layouts fall here)."""
    if 0x20 <= keysym <= 0x7E:
        return char_to_cell(chr(keysym))
    return SPECIAL_KEYSYMS.get(keysym)


def heat_rgb(fraction: float) -> tuple[int, int, int]:
    """Cold→hot colour for a 0..1 fraction: blue → cyan → green → yellow → red.

    A hue sweep from 240° (blue, rarely pressed) down to 0° (red, most
    pressed) — the familiar thermal ramp Olya asked for ("синий → красный").
    """
    fraction = 0.0 if fraction < 0 else 1.0 if fraction > 1 else fraction
    hue = 240.0 * (1.0 - fraction)     # 240=blue … 0=red
    saturation = 1.0
    value = 0.92
    sector = hue / 60.0
    i = int(sector) % 6
    f = sector - int(sector)
    p = value * (1.0 - saturation)
    q = value * (1.0 - saturation * f)
    t = value * (1.0 - saturation * (1.0 - f))
    r, g, b = (
        (value, t, p), (q, value, p), (p, value, t),
        (p, q, value), (t, p, value), (value, p, q),
    )[i]
    return round(r * 255), round(g * 255), round(b * 255)


# Each row: (cell_id, label, width in key units). Cell ids that key resolution
# never produces (modifiers, function keys) simply stay grey.
KEYBOARD_ROWS = [
    [
        ("esc", "Esc", 1.0), ("f1", "F1", 1.0), ("f2", "F2", 1.0), ("f3", "F3", 1.0),
        ("f4", "F4", 1.0), ("f5", "F5", 1.0), ("f6", "F6", 1.0), ("f7", "F7", 1.0),
        ("f8", "F8", 1.0), ("f9", "F9", 1.0), ("f10", "F10", 1.0), ("f11", "F11", 1.0),
        ("f12", "F12", 1.0),
    ],
    [
        ("`", "`", 1.0), ("1", "1", 1.0), ("2", "2", 1.0), ("3", "3", 1.0), ("4", "4", 1.0),
        ("5", "5", 1.0), ("6", "6", 1.0), ("7", "7", 1.0), ("8", "8", 1.0), ("9", "9", 1.0),
        ("0", "0", 1.0), ("-", "-", 1.0), ("=", "=", 1.0), ("backspace", "⌫", 2.0),
    ],
    [
        ("tab", "Tab", 1.5), ("q", "Q", 1.0), ("w", "W", 1.0), ("e", "E", 1.0), ("r", "R", 1.0),
        ("t", "T", 1.0), ("y", "Y", 1.0), ("u", "U", 1.0), ("i", "I", 1.0), ("o", "O", 1.0),
        ("p", "P", 1.0), ("[", "[", 1.0), ("]", "]", 1.0), ("\\", "\\", 1.5),
    ],
    [
        ("caps", "Caps", 1.75), ("a", "A", 1.0), ("s", "S", 1.0), ("d", "D", 1.0), ("f", "F", 1.0),
        ("g", "G", 1.0), ("h", "H", 1.0), ("j", "J", 1.0), ("k", "K", 1.0), ("l", "L", 1.0),
        (";", ";", 1.0), ("'", "'", 1.0), ("enter", "⏎", 2.25),
    ],
    [
        ("lshift", "Shift", 2.25), ("z", "Z", 1.0), ("x", "X", 1.0), ("c", "C", 1.0), ("v", "V", 1.0),
        ("b", "B", 1.0), ("n", "N", 1.0), ("m", "M", 1.0), (",", ",", 1.0), (".", ".", 1.0),
        ("/", "/", 1.0), ("rshift", "Shift", 2.75),
    ],
    [
        ("lctrl", "Ctrl", 1.5), ("lsuper", "Super", 1.25), ("lalt", "Alt", 1.25),
        ("space", "Space", 6.5), ("ralt", "Alt", 1.25), ("rsuper", "Super", 1.25),
        ("rctrl", "Ctrl", 1.5),
    ],
]
