"""Shared read/write plumbing for the ``~/.config/mycat/config.ini`` sections.

Every feature owns its own dataclass and decides which fields map to which keys
(including any legacy-key fallbacks); this module does the identical
``ConfigParser`` dance once instead of once per feature:

- :func:`read_config` — parse the file (or ``None`` if absent/unreadable),
- :func:`write_section` — merge one section back without touching the others,
  create the file, and secure it,
- :func:`bool_str` — serialize a bool the way the config has always stored it.
"""

from __future__ import annotations

import configparser
import logging
from pathlib import Path

from . import secret_store

logger = logging.getLogger(__name__)


def bool_str(value: bool) -> str:
    """``True``/``False`` -> the ``"true"``/``"false"`` the config stores."""
    return "true" if value else "false"


def read_config(cfg_file: Path) -> configparser.ConfigParser | None:
    """Parse ``cfg_file``, or ``None`` if it is absent or cannot be read."""
    if not cfg_file.exists():
        return None
    config = configparser.ConfigParser()
    try:
        config.read(cfg_file)
    except (configparser.Error, OSError) as exc:
        logger.error("Failed to read %s: %s", cfg_file, exc)
        return None
    return config


def write_section(name: str, values: dict, cfg_file: Path) -> None:
    """Merge ``values`` into the ``[name]`` section of ``cfg_file``.

    Creates the file and the section as needed and leaves every other section
    untouched, then secures the file. Persistence is best-effort: failures are
    logged, never raised.
    """
    try:
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        config = configparser.ConfigParser()
        if cfg_file.exists():
            config.read(cfg_file)
        if name not in config:
            config.add_section(name)
        config[name].update({key: str(value) for key, value in values.items()})
        with open(cfg_file, "w") as fh:
            config.write(fh)
        secret_store.secure_file(cfg_file)
    except (OSError, configparser.Error) as exc:
        logger.error("Failed to save [%s] to %s: %s", name, cfg_file, exc)


def remove_section(name: str, cfg_file: Path) -> None:
    """Drop the whole ``[name]`` section from ``cfg_file`` (no-op if absent)."""
    try:
        if not cfg_file.exists():
            return
        config = configparser.ConfigParser()
        config.read(cfg_file)
        if config.remove_section(name):
            with open(cfg_file, "w") as fh:
                config.write(fh)
            secret_store.secure_file(cfg_file)
    except (OSError, configparser.Error) as exc:
        logger.error("Failed to clear [%s] in %s: %s", name, cfg_file, exc)
