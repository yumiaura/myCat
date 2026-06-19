"""Local skin discovery.

A skin is either a **folder** or a **`.zip`** (read in memory) named by its id.
Skins live in two locations:
- **Bundled:** `mycat/skins/` — packaged with the wheel.
- **User:** platform-specific writable directory — receives downloads from the
  shop and user-imported skins.

The user directory takes precedence: if both a bundled and a user copy of a
skin with the same id exist, the user one wins (so users can replace bundled
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


SKIN_MARKERS = ("config.json", "static.png")


def bundled_skins_dir() -> Path:
    return Path(__file__).resolve().parent / "skins"


def is_skin_folder(path: Path) -> bool:
    """A directory counts as a skin if it holds a marker or a GIF."""
    if not path.is_dir():
        return False
    if any((path / marker).is_file() for marker in SKIN_MARKERS):
        return True
    return any(path.glob("*.gif"))


def user_skins_dir() -> Path:
    """Platform-specific writable directory for downloaded/user-added skins."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "mycat" / "skins"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "mycat" / "skins"
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "mycat" / "skins"


def ensure_user_skins_dir() -> Path:
    path = user_skins_dir()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Could not create user skins dir %s: %s", path, exc)
    return path


def scan_all() -> list[str]:
    """Return sorted, deduplicated skin ids available locally.

    A skin id is the name of a `<id>.zip` archive or an `<id>/` folder. The same
    id in the user dir shadows the bundled one (resolved by `find_skin`).
    """
    seen: set[str] = set()
    for directory in (user_skins_dir(), bundled_skins_dir()):
        if not directory.exists():
            continue
        for zip_path in directory.glob("*.zip"):
            seen.add(zip_path.stem)
        for child in directory.iterdir():
            if is_skin_folder(child):
                seen.add(child.name)
    return sorted(seen)


def find_skin(skin_id: str) -> Path | None:
    """Resolve `skin_id` to an existing skin path (folder or .zip).

    User dir wins over bundled; within a dir an unpacked folder wins over a zip.
    """
    for directory in (user_skins_dir(), bundled_skins_dir()):
        folder = directory / skin_id
        if is_skin_folder(folder):
            return folder
        candidate = directory / f"{skin_id}.zip"
        if candidate.exists():
            return candidate
    return None


def find_skin_zip(skin_id: str) -> Path | None:
    """Back-compat alias — now returns a folder or zip path (see `find_skin`)."""
    return find_skin(skin_id)


def installed_metadata_path() -> Path:
    return ensure_user_skins_dir() / INSTALLED_JSON_NAME


def load_installed_metadata() -> dict:
    path = installed_metadata_path()
    if not path.exists():
        return {"schema_version": INSTALLED_SCHEMA_VERSION, "skins": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Corrupt installed.json (%s); starting fresh", exc)
        return {"schema_version": INSTALLED_SCHEMA_VERSION, "skins": []}


def record_installed(skin_id: str, *, version: str, source: str, sha256: str, size_bytes: int) -> None:
    data = load_installed_metadata()
    data.setdefault("schema_version", INSTALLED_SCHEMA_VERSION)
    skins = [s for s in data.get("skins", []) if s.get("id") != skin_id]
    skins.append(
        {
            "id": skin_id,
            "version": version,
            "source": source,
            "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sha256": sha256,
            "size_bytes": size_bytes,
        }
    )
    data["skins"] = skins
    path = installed_metadata_path()
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write installed.json: %s", exc)


def remove_installed(skin_id: str) -> bool:
    """Remove a user-installed skin (does NOT touch bundled). Returns True on success."""
    user_zip = user_skins_dir() / f"{skin_id}.zip"
    if not user_zip.exists():
        return False
    try:
        user_zip.unlink()
    except OSError as exc:
        logger.warning("Could not delete %s: %s", user_zip, exc)
        return False
    data = load_installed_metadata()
    data["skins"] = [s for s in data.get("skins", []) if s.get("id") != skin_id]
    try:
        installed_metadata_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not update installed.json: %s", exc)
    return True


def is_user_installed(skin_id: str) -> bool:
    return (user_skins_dir() / f"{skin_id}.zip").exists()


__all__ = [
    "INSTALLED_JSON_NAME",
    "bundled_skins_dir",
    "user_skins_dir",
    "ensure_user_skins_dir",
    "is_skin_folder",
    "scan_all",
    "find_skin",
    "find_skin_zip",
    "installed_metadata_path",
    "load_installed_metadata",
    "record_installed",
    "remove_installed",
    "is_user_installed",
]
