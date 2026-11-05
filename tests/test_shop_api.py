import hashlib
import urllib.request

import pytest

from mycat import char_catalog
from mycat.shop_api import (
    Catalog,
    CharEntry,
    ShopClient,
    ShopError,
    is_same_host,
    is_valid_version,
)


def test_is_valid_char_id():
    assert char_catalog.is_valid_char_id("cat")
    assert char_catalog.is_valid_char_id("custom-123")
    assert char_catalog.is_valid_char_id("my_cat_pet")
    assert char_catalog.is_valid_char_id("chibi-kitten-01")

    assert not char_catalog.is_valid_char_id("")
    assert not char_catalog.is_valid_char_id("../traversal")
    assert not char_catalog.is_valid_char_id("/absolute/path")
    assert not char_catalog.is_valid_char_id("sub/dir")
    assert not char_catalog.is_valid_char_id("sub\\win")
    assert not char_catalog.is_valid_char_id("-starts-with-dash")
    assert not char_catalog.is_valid_char_id(".hidden")


def test_is_valid_version():
    assert is_valid_version("0.1.0")
    assert is_valid_version("v1.2.3")
    assert is_valid_version("2024.1")

    assert not is_valid_version("")
    assert not is_valid_version("..")
    assert not is_valid_version("../../1.0")
    assert not is_valid_version("-1.0")


def test_is_same_host():
    base = "http://127.0.0.1:18000"
    assert is_same_host("http://127.0.0.1:18000/download/cat.zip", base)
    assert is_same_host("/api/v1/characters/cat/download", base)
    assert is_same_host("http://127.0.0.1:18000", base)

    # Different port or host
    assert not is_same_host("http://127.0.0.1:9000/download/cat.zip", base)
    assert not is_same_host("https://cdn.example.com/cat.zip", base)
    assert not is_same_host("http://malicious.com/cat.zip", base)


def test_char_entry_validation():
    valid = CharEntry.from_dict({
        "id": "valid-cat",
        "name": "Valid Cat",
        "version": "1.0.0",
        "download_url": "/cat.zip",
    })
    assert valid.id == "valid-cat"
    assert valid.version == "1.0.0"

    # Traversal id raises ValueError
    with pytest.raises(ValueError, match="Invalid char id"):
        CharEntry.from_dict({"id": "../../../../evil"})

    # Invalid version falls back safely to 0.0.0
    safe_ver = CharEntry.from_dict({"id": "valid-cat", "version": "../../0.1"})
    assert safe_ver.version == "0.0.0"


def test_catalog_skips_invalid_entries():
    raw_catalog = {
        "schema_version": 1,
        "generated_at": "2026-10-01T00:00:00Z",
        "characters": [
            {"id": "good-cat", "name": "Good"},
            {"id": "../../bad-cat", "name": "Bad"},
            {"id": "another-good-cat", "name": "Another"},
        ],
    }
    catalog = Catalog.from_dict(raw_catalog)
    assert len(catalog.chars) == 2
    assert [c.id for c in catalog.chars] == ["good-cat", "another-good-cat"]


def test_fetch_preview_rejects_unsafe_id(tmp_path):
    client = ShopClient(cache_dir=tmp_path)
    entry = CharEntry(
        id="../unsafe",
        name="Unsafe",
        author="",
        description="",
        preview_url="http://127.0.0.1:18000/preview.png",
        download_url="",
        sha256="",
        size_bytes=0,
        version="1.0.0",
        tier="free",
        released_at="",
    )
    assert client.fetch_preview(entry) is None


def test_download_char_rejects_unsafe_id(tmp_path):
    client = ShopClient(cache_dir=tmp_path)
    entry = CharEntry(
        id="../unsafe",
        name="Unsafe",
        author="",
        description="",
        preview_url="",
        download_url="/download.zip",
        sha256="",
        size_bytes=0,
        version="1.0.0",
        tier="free",
        released_at="",
    )
    with pytest.raises(ShopError, match="unsafe id"):
        client.download_char(entry, tmp_path / "chars")


class FakeHTTPResponse:
    def __init__(self, data: bytes, headers: dict | None = None) -> None:
        self.data = data
        self.headers = headers or {}

    def read(self, chunk_size: int = -1) -> bytes:
        if chunk_size == -1:
            ret, self.data = self.data, b""
            return ret
        ret = self.data[:chunk_size]
        self.data = self.data[chunk_size:]
        return ret

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_download_char_scopes_auth_token(tmp_path, monkeypatch):
    client = ShopClient(base_url="http://127.0.0.1:18000", cache_dir=tmp_path)
    sample_content = b"fake-zip-data"
    digest = hashlib.sha256(sample_content).hexdigest()

    intercepted_requests = []

    def fake_urlopen(request, timeout=None):
        if isinstance(request, str):
            request = urllib.request.Request(request)
        intercepted_requests.append(request)
        return FakeHTTPResponse(sample_content)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    # 1. Download from same host -> Authorization header present
    same_host_char = CharEntry(
        id="same-host-cat",
        name="Same Host",
        author="",
        description="",
        preview_url="",
        download_url="/api/v1/characters/same-host-cat/download",
        sha256=digest,
        size_bytes=len(sample_content),
        version="1.0.0",
        tier="free",
        released_at="",
    )
    dest_dir = tmp_path / "chars"
    client.download_char(same_host_char, dest_dir, auth_token="secret-token-123")
    assert len(intercepted_requests) == 1
    req = intercepted_requests[0]
    assert req.headers.get("Authorization") == "Bearer secret-token-123"

    # 2. Download from external CDN -> Authorization header MUST BE OMITTED
    intercepted_requests.clear()
    external_char = CharEntry(
        id="external-cat",
        name="External Cat",
        author="",
        description="",
        preview_url="",
        download_url="https://cdn.external-thirdparty.com/files/external-cat.zip",
        sha256=digest,
        size_bytes=len(sample_content),
        version="1.0.0",
        tier="free",
        released_at="",
    )
    client.download_char(external_char, dest_dir, auth_token="secret-token-123")
    assert len(intercepted_requests) == 1
    req_external = intercepted_requests[0]
    assert "Authorization" not in req_external.headers


def test_char_catalog_path_traversal_guards():
    assert char_catalog.find_char("../../secret") is None
    assert not char_catalog.remove_installed("../../secret")
    assert not char_catalog.is_user_installed("../../secret")
