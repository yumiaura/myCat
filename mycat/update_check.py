"""Startup version banner + a best-effort GitHub release check.

The check runs on a background daemon thread, never blocks startup, and stays
silent on any network/parse error — it only *logs*, nothing is downloaded or
installed. Skipped for source/dev builds (version "0.0.0").
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.request

logger = logging.getLogger(__name__)

LATEST_RELEASE_URL = "https://api.github.com/repos/yumiaura/myCat/releases/latest"
RELEASES_PAGE = "https://github.com/yumiaura/myCat/releases/latest"


def current_version() -> str:
    """Version of the code actually running.

    Prefer the repo's ``pyproject.toml`` when run from a source checkout (that is
    the code in front of you, not whatever — possibly stale — version pip has
    installed). Fall back to the installed package metadata (pip / exe), then
    ``"0.0.0"``.
    """
    import re
    from pathlib import Path

    try:
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        if pyproject.is_file():
            match = re.search(
                r'(?m)^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8")
            )
            if match:
                return match.group(1)
    except Exception:
        pass
    try:
        from importlib.metadata import version

        return version("mycat")
    except Exception:
        return "0.0.0"


def parse_version(text: str) -> tuple:
    """Turn "0.1.10" / "v0.1.10" into (0, 1, 10) for comparison; junk parts -> 0."""
    parts = []
    for chunk in text.strip().lstrip("vV").split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def latest_release_tag(url: str = LATEST_RELEASE_URL, timeout: float = 6.0, opener=None) -> str | None:
    """Return the latest GitHub release tag, or None on any error."""
    open_fn = opener or urllib.request.urlopen
    request = urllib.request.Request(
        url, headers={"User-Agent": "mycat", "Accept": "application/vnd.github+json"}
    )
    try:
        with open_fn(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        tag = (data.get("tag_name") or "").strip()
        return tag or None
    except Exception as exc:  # network down, rate-limited, bad JSON — never fatal
        logger.debug("Update check failed: %s", exc)
        return None


def newer_release(current: str, **kwargs) -> str | None:
    """The latest tag if it is newer than `current`, else None. Skips dev builds."""
    if parse_version(current) == (0, 0, 0):
        return None
    latest = latest_release_tag(**kwargs)
    if latest and parse_version(latest) > parse_version(current):
        return latest
    return None


def check_in_background(current: str) -> None:
    """Fire the release check on a daemon thread; log if an update is available."""

    def run() -> None:
        latest = newer_release(current)
        if latest:
            logger.info(
                "Update available: mycat %s (you have %s) — %s",
                latest,
                current,
                RELEASES_PAGE,
            )
        else:
            logger.debug("mycat is up to date (%s)", current)

    threading.Thread(target=run, name="mycat-update-check", daemon=True).start()


__all__ = [
    "current_version",
    "parse_version",
    "latest_release_tag",
    "newer_release",
    "check_in_background",
]
