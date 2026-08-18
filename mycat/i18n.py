"""File-based internationalization for myCat.

Every language lives in its own JSON file under ``mycat/locale/<code>.json``:

    {
      "language": {"code": "ru", "name": "Русский"},
      "strings": {
        "Chat": "Чат",
        "Reminder…": "Напоминание…"
      }
    }

The folder is scanned once at import time, so adding a language is just dropping
a new file in there — no code change. The available languages and their display
names come from the files; :func:`tr` looks a string up in the active language
and falls back to the English source string when a translation is missing.

The active language is chosen from **right-click / tray menu → under Settings →
Language** and persisted in ``config.ini`` under ``[settings] language``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6 import QtGui, QtWidgets

from . import config_store, paths

logger = logging.getLogger(__name__)

# Bundled locale files live next to this module (i18n.py is a package module, so
# __file__ keeps the mycat/ prefix and resolves correctly in the frozen exe too).
LOCALE_DIR = Path(__file__).resolve().parent / "locale"

CONFIG_SECTION = "settings"
CONFIG_KEY = "language"
DEFAULT_LANGUAGE = "en"


def scan_locales() -> tuple[dict, dict]:
    """Read ``mycat/locale/*.json`` -> ({code: display name}, {code: {en: text}})."""
    languages: dict = {}
    catalogs: dict = {}
    if LOCALE_DIR.is_dir():
        for path in sorted(LOCALE_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                logger.warning("Skipping locale %s: %s", path.name, exc)
                continue
            meta = data.get("language", {})
            code = meta.get("code") or path.stem
            languages[code] = meta.get("name") or code
            catalogs[code] = data.get("strings", {}) or {}
    # English is the source language and always available, even with no file.
    languages.setdefault(DEFAULT_LANGUAGE, "English")
    catalogs.setdefault(DEFAULT_LANGUAGE, {})
    return languages, catalogs


LANGUAGES, CATALOGS = scan_locales()
active_code = DEFAULT_LANGUAGE


def available_languages() -> dict:
    """``{code: display name}`` for every locale found in the folder."""
    return dict(LANGUAGES)


def current_language() -> str:
    return active_code


def tr(text: str) -> str:
    """Translate ``text`` into the active language, or return it unchanged."""
    return CATALOGS.get(active_code, {}).get(text, text)


def config_file() -> Path:
    return paths.config_file()


def load_language(config_path: Path | None = None) -> str:
    """Read the saved language from config and make it active."""
    global active_code
    config = config_store.read_config(config_path or config_file())
    if config is not None and config.has_option(CONFIG_SECTION, CONFIG_KEY):
        value = config.get(CONFIG_SECTION, CONFIG_KEY)
        if value in LANGUAGES:
            active_code = value
    return active_code


def set_language(code: str, config_path: Path | None = None) -> str:
    """Switch the active language and persist the choice."""
    global active_code
    if code in LANGUAGES:
        active_code = code
        config_store.write_section(CONFIG_SECTION, {CONFIG_KEY: code}, config_path or config_file())
    return active_code


def build_language_menu(config_path: Path | None = None, on_changed=None) -> QtWidgets.QMenu:
    """A "Language" submenu with one radio entry per available language.

    Meant to sit under the Settings entry in the cat / tray menu. Picking a
    language switches and persists it; ``on_changed`` (if given) is called so the
    caller can refresh anything already on screen.
    """
    menu = QtWidgets.QMenu(tr("Language"))
    group = QtGui.QActionGroup(menu)
    group.setExclusive(True)
    for code, name in LANGUAGES.items():
        action = menu.addAction(name)
        action.setCheckable(True)
        action.setChecked(code == active_code)
        group.addAction(action)

        def choose(checked, code=code):
            if checked:
                set_language(code, config_path)
                if callable(on_changed):
                    on_changed()

        action.triggered.connect(choose)
    return menu
