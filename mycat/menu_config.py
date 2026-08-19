"""Which feature entries appear in the cat / tray menus.

Users can hide the feature entries they don't use (right-click / tray menu) from
the Settings dialog; the choice lives in the ``[menu]`` section of config.ini.
The utility entries (Reset / Update / Autostart), Settings itself and Close /
Quit are always shown, so the app stays manageable and the toggles can always be
reached again. Hiding an entry only removes the menu shortcut — the feature
itself (reminders firing, activity tracking, …) keeps running.
"""

from pathlib import Path

from . import config_store, paths

MENU_SECTION = "menu"

# (config key, menu label) for the hideable feature entries, in menu order.
# "chars" only appears in the cat's right-click menu; the rest appear in both.
MENU_ITEMS = [
    ("chat", "Chat"),
    ("llm", "LLM…"),
    ("calendar", "Calendar…"),
    ("reminder", "Reminder…"),
    ("github", "GitHub…"),
    ("activity", "Activity…"),
    ("chars", "Chars"),
]

# Entries hidden from the menu by default — Chat / LLM / Calendar are opt-in
# (most users don't set up Ollama or a calendar), so they start hidden to keep
# the menu tidy. Everything else shows by default. Any of them can be flipped in
# Settings → Show in menu.
DEFAULT_HIDDEN = {"chat", "llm", "calendar"}


def default_visible(key: str) -> bool:
    """Whether a menu entry is shown before the user has chosen in Settings."""
    return key not in DEFAULT_HIDDEN


def load_menu_visibility(cfg_file: Path | None = None) -> dict:
    """Map each menu entry key to whether it should be shown (see DEFAULT_HIDDEN)."""
    cfg_file = cfg_file or paths.config_file()
    visible = {key: default_visible(key) for key, _ in MENU_ITEMS}
    config = config_store.read_config(cfg_file)
    if config is not None and config.has_section(MENU_SECTION):
        for key, _ in MENU_ITEMS:
            if config.has_option(MENU_SECTION, key):
                try:
                    visible[key] = config.getboolean(MENU_SECTION, key)
                except ValueError:
                    visible[key] = default_visible(key)
    return visible


def save_menu_visibility(visible: dict, cfg_file: Path | None = None) -> None:
    """Persist the shown/hidden state of every menu entry into ``[menu]``."""
    cfg_file = cfg_file or paths.config_file()
    values = {key: config_store.bool_str(bool(visible.get(key, default_visible(key)))) for key, _ in MENU_ITEMS}
    config_store.write_section(MENU_SECTION, values, cfg_file)
