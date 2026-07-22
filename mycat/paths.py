"""Single source of truth for mycat's config location.

The config file has always lived in ``~/.config/mycat`` on every platform
(``Path.home()`` resolves per-OS), and it stays there so existing installs keep
their settings — no migration, no lost config on Windows/macOS. Data
(``activity.db``) and chars use the per-OS conventional dirs instead; see
``activity_store.user_data_dir`` / ``char_catalog.user_chars_dir``.
"""

from __future__ import annotations

from pathlib import Path

APP_NAME = "mycat"


def config_dir() -> Path:
    """Directory holding ``config.ini`` (and the LLM history) — ``~/.config/mycat``."""
    return Path.home() / ".config" / APP_NAME


def config_file() -> Path:
    """Path to the shared ``config.ini``."""
    return config_dir() / "config.ini"
