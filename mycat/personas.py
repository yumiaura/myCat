"""Selectable companion personalities (cat, dog).

A persona bundles the system-prompt template, the on-screen name label, the
image/animation to display, and a preferred TTS voice. The choice is persisted
to config.ini under [persona].
"""

from __future__ import annotations

import configparser
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_CFG_FILE = Path.home() / ".config" / "mycat" / "config.ini"

# key -> persona definition. `template` is a file in this package directory;
# `image` is the <name>.zip in images/; `voice` is a Piper voice stem (or None).
PERSONAS: Dict[str, dict] = {
    "cat": {
        "label": "Cat",
        "image": "cat",
        "template": "PROMPT.j2",
        "voice": None,
    },
    "dog": {
        "label": "Dog",
        "image": "dog",
        "template": "PROMPT_dog.j2",
        "voice": "en_US-amy-medium",
    },
}
DEFAULT = "cat"

_current: Optional[str] = None


def keys() -> List[str]:
    return list(PERSONAS.keys())


def get() -> str:
    """Active persona key, read from config on first call."""
    global _current
    if _current is None:
        _current = _load_saved() or DEFAULT
    return _current


def info() -> dict:
    return PERSONAS[get()]


def label() -> str:
    return info()["label"]


def template_path() -> Path:
    return Path(__file__).resolve().parent / info()["template"]


def set(key: str, persist: bool = True) -> None:
    global _current
    if key not in PERSONAS:
        logger.warning("Unknown persona '%s'; ignoring", key)
        return
    _current = key
    if persist:
        _save(key)
    logger.info("Persona set to %s", key)


def _load_saved() -> Optional[str]:
    try:
        parser = configparser.ConfigParser()
        parser.read(_CFG_FILE)
        if parser.has_option("persona", "name"):
            name = parser.get("persona", "name").strip().lower()
            if name in PERSONAS:
                return name
    except (configparser.Error, OSError) as exc:  # pragma: no cover
        logger.debug("Could not read saved persona: %s", exc)
    return None


def _save(key: str) -> None:
    try:
        parser = configparser.ConfigParser()
        parser.read(_CFG_FILE)
        if not parser.has_section("persona"):
            parser.add_section("persona")
        parser.set("persona", "name", key)
        _CFG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CFG_FILE, "w", encoding="utf-8") as handle:
            parser.write(handle)
    except (configparser.Error, OSError) as exc:  # pragma: no cover
        logger.warning("Could not persist persona: %s", exc)


__all__ = ["PERSONAS", "DEFAULT", "keys", "get", "info", "label", "template_path", "set"]
