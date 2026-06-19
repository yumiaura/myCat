"""HTTP client for the mycat char shop.

Talks to a mycat-server (FastAPI) instance: fetches the catalog and downloads
char ZIPs. No third-party dependencies — `urllib` only (consistent with
`llm_ollama.py`).
"""

from __future__ import annotations

import configparser
import hashlib
import json
import logging
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:18000"
CATALOG_PATH = "/api/v1/catalog"
CHAR_DOWNLOAD_PATH = "/api/v1/characters/{id}/download"

CATALOG_CACHE_TTL_SECONDS = 3600
DEFAULT_CATALOG_TIMEOUT = 10.0
DEFAULT_DOWNLOAD_TIMEOUT = 60.0
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024  # safety net


@dataclass
class CharEntry:
    id: str
    name: str
    author: str
    description: str
    preview_url: str
    download_url: str
    sha256: str
    size_bytes: int
    version: str
    tier: str
    released_at: str
    tags: list[str] = field(default_factory=list)
    license: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> CharEntry:
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", data["id"])),
            author=str(data.get("author", "")),
            description=str(data.get("description", "")),
            preview_url=str(data.get("preview_url", "")),
            download_url=str(data.get("download_url", "")),
            sha256=str(data.get("sha256", "")),
            size_bytes=int(data.get("size_bytes", 0)),
            version=str(data.get("version", "0.0.0")),
            tier=str(data.get("tier", "free")),
            released_at=str(data.get("released_at", "")),
            tags=list(data.get("tags", [])),
            license=str(data.get("license", "")),
        )


@dataclass
class Catalog:
    schema_version: int
    generated_at: str
    characters: list[CharEntry]

    @classmethod
    def from_dict(cls, data: dict) -> Catalog:
        return cls(
            schema_version=int(data.get("schema_version", 1)),
            generated_at=str(data.get("generated_at", "")),
            characters=[CharEntry.from_dict(s) for s in data.get("characters", [])],
        )


class ShopError(RuntimeError):
    """Raised for any shop-API failure that should surface to the user."""


def resolve_base_url(config_path: Path | None = None) -> str:
    """Resolve the shop base URL via env > config.ini > default."""
    env_url = (os.environ.get("MYCAT_SHOP_URL") or "").strip()
    if env_url:
        return env_url.rstrip("/")
    if config_path and config_path.exists():
        parser = configparser.ConfigParser()
        try:
            parser.read(config_path)
            if parser.has_section("shop"):
                url = parser.get("shop", "url", fallback="").strip()
                if url:
                    return url.rstrip("/")
        except configparser.Error as exc:
            logger.warning("Could not read shop URL from %s: %s", config_path, exc)
    return DEFAULT_BASE_URL


def default_cache_dir() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "mycat"


class ShopClient:
    """Thin HTTP client. Methods are blocking; callers should run them off the UI thread."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        catalog_timeout: float = DEFAULT_CATALOG_TIMEOUT,
        download_timeout: float = DEFAULT_DOWNLOAD_TIMEOUT,
        cache_dir: Path | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.catalog_timeout = catalog_timeout
        self.download_timeout = download_timeout
        self.cache_dir = cache_dir or default_cache_dir()
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("Cannot create cache dir %s: %s", self.cache_dir, exc)

    # ---- catalog -----------------------------------------------------------

    def fetch_catalog(self, *, force_refresh: bool = False) -> Catalog:
        """Fetch catalog with ETag-aware caching.

        On network failure, returns the cached version if available, otherwise raises.
        """
        cache_file = self.cache_dir / "catalog.json"
        etag_file = self.cache_dir / "catalog.etag"

        cached_etag: str | None = None
        if etag_file.exists() and cache_file.exists() and not force_refresh:
            try:
                cached_etag = etag_file.read_text(encoding="utf-8").strip() or None
            except OSError:
                cached_etag = None

        headers = {"Accept": "application/json", "User-Agent": "mycat-client"}
        if cached_etag:
            headers["If-None-Match"] = cached_etag

        request = urllib.request.Request(self.base_url + CATALOG_PATH, headers=headers, method="GET")

        try:
            with urllib.request.urlopen(request, timeout=self.catalog_timeout) as response:
                status = response.status
                body = response.read()
                etag = response.headers.get("ETag")
                if etag:
                    try:
                        etag_file.write_text(etag, encoding="utf-8")
                    except OSError as exc:
                        logger.debug("Could not persist ETag: %s", exc)
                if status == 200 and body:
                    try:
                        cache_file.write_bytes(body)
                    except OSError as exc:
                        logger.debug("Could not persist catalog cache: %s", exc)
                    return Catalog.from_dict(json.loads(body.decode("utf-8")))
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                logger.debug("Catalog 304 Not Modified — using cached copy")
                return self._load_cached_catalog(cache_file)
            cached = self._maybe_load_cached_catalog(cache_file)
            if cached is not None:
                logger.warning("Catalog HTTP %s; falling back to cache: %s", exc.code, exc)
                return cached
            raise ShopError(f"Server returned HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            cached = self._maybe_load_cached_catalog(cache_file)
            if cached is not None:
                logger.warning("Catalog network error; falling back to cache: %s", exc.reason)
                return cached
            raise ShopError(f"Cannot reach shop: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise ShopError(f"Catalog response is not valid JSON: {exc}") from exc

        return self._load_cached_catalog(cache_file)

    def _maybe_load_cached_catalog(self, cache_file: Path) -> Catalog | None:
        if not cache_file.exists():
            return None
        try:
            return self._load_cached_catalog(cache_file)
        except ShopError:
            return None

    def _load_cached_catalog(self, cache_file: Path) -> Catalog:
        try:
            return Catalog.from_dict(json.loads(cache_file.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            raise ShopError(f"Cannot read cached catalog: {exc}") from exc

    # ---- preview -----------------------------------------------------------

    def fetch_preview(self, char: CharEntry) -> Path | None:
        """Download a char's preview into the cache, return local path or None on failure."""
        if not char.preview_url:
            return None
        previews_dir = self.cache_dir / "previews"
        try:
            previews_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None
        # Extension follows the URL suffix (.gif / .png).
        suffix = Path(urllib.parse.urlparse(char.preview_url).path).suffix.lower() or ".gif"
        dest = previews_dir / f"{char.id}-{char.version}{suffix}"
        if dest.exists() and dest.stat().st_size > 0:
            return dest
        try:
            request = urllib.request.Request(
                char.preview_url,
                headers={"User-Agent": "mycat-client"},
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=self.catalog_timeout) as response:
                data = response.read()
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, dest)
            return dest
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            logger.debug("Preview fetch failed for %s: %s", char.id, exc)
            return None

    # ---- download ----------------------------------------------------------

    def download_char(
        self,
        char: CharEntry,
        dest_dir: Path,
        *,
        progress_cb: Callable[[int, int], None] | None = None,
        auth_token: str | None = None,
    ) -> Path:
        """Download `char` into `dest_dir/<id>.zip`, verifying SHA-256.

        - Follows the server's 302 redirect to the CDN (urllib does this transparently).
        - Atomic: writes to a temp file in the same dir, then `os.replace`.
        - Raises ShopError on any failure; partial files are cleaned up.
        - `progress_cb(downloaded, total)` is invoked periodically (best-effort).
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        final_path = dest_dir / f"{char.id}.zip"
        url = self._resolve_download_url(char)

        headers = {"User-Agent": "mycat-client", "Accept": "application/zip, */*"}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        request = urllib.request.Request(url, headers=headers, method="GET")
        sha = hashlib.sha256()
        downloaded = 0
        expected = char.size_bytes or 0

        # Use a NamedTemporaryFile in dest_dir for atomic replace on same FS.
        tmp = tempfile.NamedTemporaryFile(
            mode="wb", suffix=".zip.partial", dir=dest_dir, delete=False
        )
        tmp_path = Path(tmp.name)
        try:
            with urllib.request.urlopen(request, timeout=self.download_timeout) as response:
                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        expected = int(content_length)
                    except ValueError:
                        pass
                if expected and expected > MAX_DOWNLOAD_BYTES:
                    raise ShopError(
                        f"Char {char.id} reports {expected} bytes which exceeds the "
                        f"{MAX_DOWNLOAD_BYTES}-byte safety limit"
                    )

                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > MAX_DOWNLOAD_BYTES:
                        raise ShopError(
                            f"Aborting {char.id}: exceeded {MAX_DOWNLOAD_BYTES}-byte safety limit"
                        )
                    sha.update(chunk)
                    tmp.write(chunk)
                    if progress_cb is not None:
                        try:
                            progress_cb(downloaded, expected or downloaded)
                        except Exception:
                            pass
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp.close()

            digest = sha.hexdigest()
            if char.sha256 and digest != char.sha256.lower():
                raise ShopError(
                    f"SHA-256 mismatch for {char.id}: server says {char.sha256}, got {digest}"
                )

            os.replace(tmp_path, final_path)
            logger.info("Downloaded %s (%d bytes) -> %s", char.id, downloaded, final_path)
            return final_path
        except urllib.error.HTTPError as exc:
            self._cleanup(tmp, tmp_path)
            raise ShopError(f"HTTP {exc.code} downloading {char.id}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            self._cleanup(tmp, tmp_path)
            raise ShopError(f"Network error downloading {char.id}: {exc.reason}") from exc
        except OSError as exc:
            self._cleanup(tmp, tmp_path)
            raise ShopError(f"I/O error downloading {char.id}: {exc}") from exc
        except ShopError:
            self._cleanup(tmp, tmp_path)
            raise
        except Exception as exc:
            self._cleanup(tmp, tmp_path)
            raise ShopError(f"Unexpected error downloading {char.id}: {exc}") from exc

    def _resolve_download_url(self, char: CharEntry) -> str:
        url = char.download_url
        if url.startswith("http://") or url.startswith("https://"):
            return url
        if not url.startswith("/"):
            url = "/" + url
        return self.base_url + url

    @staticmethod
    def _cleanup(tmp_file, tmp_path: Path) -> None:
        try:
            tmp_file.close()
        except Exception:
            pass
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


__all__ = [
    "Catalog",
    "DEFAULT_BASE_URL",
    "MAX_DOWNLOAD_BYTES",
    "ShopClient",
    "ShopError",
    "CharEntry",
    "default_cache_dir",
    "resolve_base_url",
]
