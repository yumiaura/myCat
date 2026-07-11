"""Local char discovery.

A char is either a **folder** or a **`.zip`** (read in memory) named by its id.
Chars live in two locations:
- **Bundled:** `mycat/chars/` — packaged with the wheel.
- **User:** platform-specific writable directory — receives downloads from the
  shop and user-imported chars.

The user directory takes precedence: if both a bundled and a user copy of a
char with the same id exist, the user one wins (so users can replace bundled
defaults with newer downloads from the shop).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

INSTALLED_JSON_NAME = "installed.json"
INSTALLED_SCHEMA_VERSION = 1


CHAR_MARKERS = ("config.json", "static.png")


def bundled_chars_dir() -> Path:
    return Path(__file__).resolve().parent / "chars"


def is_char_folder(path: Path) -> bool:
    """A directory counts as a char if it holds a marker or a GIF."""
    if not path.is_dir():
        return False
    if any((path / marker).is_file() for marker in CHAR_MARKERS):
        return True
    return any(path.glob("*.gif"))


def user_chars_dir() -> Path:
    """Platform-specific writable directory for downloaded/user-added chars."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "mycat" / "chars"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "mycat" / "chars"
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "mycat" / "chars"


def ensure_user_chars_dir() -> Path:
    path = user_chars_dir()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Could not create user chars dir %s: %s", path, exc)
    return path


def scan_all() -> list[str]:
    """Return sorted, deduplicated char ids available locally.

    A char id is the name of a `<id>.zip` archive or an `<id>/` folder. The same
    id in the user dir shadows the bundled one (resolved by `find_char`).
    """
    seen: set[str] = set()
    for directory in (user_chars_dir(), bundled_chars_dir()):
        if not directory.exists():
            continue
        for zip_path in directory.glob("*.zip"):
            seen.add(zip_path.stem)
        for child in directory.iterdir():
            if is_char_folder(child):
                seen.add(child.name)
    return sorted(seen)


def find_char(char_id: str) -> Path | None:
    """Resolve `char_id` to an existing char path (folder or .zip).

    User dir wins over bundled; within a dir an unpacked folder wins over a zip.
    """
    for directory in (user_chars_dir(), bundled_chars_dir()):
        folder = directory / char_id
        if is_char_folder(folder):
            return folder
        candidate = directory / f"{char_id}.zip"
        if candidate.exists():
            return candidate
    return None


def installed_metadata_path() -> Path:
    return ensure_user_chars_dir() / INSTALLED_JSON_NAME


def load_installed_metadata() -> dict:
    path = installed_metadata_path()
    if not path.exists():
        return {"schema_version": INSTALLED_SCHEMA_VERSION, "characters": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Corrupt installed.json (%s); starting fresh", exc)
        return {"schema_version": INSTALLED_SCHEMA_VERSION, "characters": []}


def record_installed(char_id: str, *, version: str, source: str, sha256: str, size_bytes: int) -> None:
    data = load_installed_metadata()
    data.setdefault("schema_version", INSTALLED_SCHEMA_VERSION)
    characters = [s for s in data.get("characters", []) if s.get("id") != char_id]
    characters.append(
        {
            "id": char_id,
            "version": version,
            "source": source,
            "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sha256": sha256,
            "size_bytes": size_bytes,
        }
    )
    data["characters"] = characters
    path = installed_metadata_path()
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write installed.json: %s", exc)


def remove_installed(char_id: str) -> bool:
    """Remove a user-installed char (does NOT touch bundled). Returns True on success."""
    user_zip = user_chars_dir() / f"{char_id}.zip"
    if not user_zip.exists():
        return False
    try:
        user_zip.unlink()
    except OSError as exc:
        logger.warning("Could not delete %s: %s", user_zip, exc)
        return False
    data = load_installed_metadata()
    data["characters"] = [s for s in data.get("characters", []) if s.get("id") != char_id]
    try:
        installed_metadata_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not update installed.json: %s", exc)
    return True


def is_user_installed(char_id: str) -> bool:
    return (user_chars_dir() / f"{char_id}.zip").exists()


def ai_generated_chars() -> list[str]:
    """Ids of locally generated characters, based on installed metadata."""
    return sorted(
        entry["id"]
        for entry in load_installed_metadata().get("characters", [])
        if entry.get("source") == "openai:image" and entry.get("id") and is_user_installed(entry["id"])
    )


__all__ = [
    "INSTALLED_JSON_NAME",
    "bundled_chars_dir",
    "user_chars_dir",
    "ensure_user_chars_dir",
    "is_char_folder",
    "scan_all",
    "find_char",
    "installed_metadata_path",
    "load_installed_metadata",
    "record_installed",
    "remove_installed",
    "is_user_installed",
    "ai_generated_chars",
]
