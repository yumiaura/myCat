"""Self-updater pure logic: install-kind detection and asset naming."""

import copy
import hashlib
import json
import urllib.request

import pytest

from mycat import updater


class FakeResponse:
    """Minimal stand-in for the object urllib.request.urlopen returns."""

    def __init__(self, body, content_length):
        self.body = body
        self.pos = 0
        self.headers = {} if content_length is None else {"Content-Length": str(content_length)}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size):
        chunk = self.body[self.pos : self.pos + size]
        self.pos += len(chunk)
        return chunk


def test_install_kind_is_source_when_not_frozen():
    # The test process is a normal interpreter, never a PyInstaller build.
    assert updater.install_kind() == "source"


def test_can_self_update():
    # Only Windows/macOS download + relaunch; the rest just get notified.
    assert updater.can_self_update("macos")
    assert updater.can_self_update("windows")
    assert not updater.can_self_update("appimage")
    assert not updater.can_self_update("deb")
    assert not updater.can_self_update("source")


def test_update_hint():
    assert updater.update_hint("deb").lower().startswith("download")
    assert "AppImage" in updater.update_hint("appimage")
    assert updater.update_hint("source") in ("git pull", "pip install --upgrade mycat")


def test_asset_names():
    assert updater.asset_name("windows") == "mycat-windows-x64.exe"
    assert updater.asset_name("appimage") == "mycat-linux-x86_64.AppImage"
    assert updater.asset_name("deb") == "mycat-linux-amd64.deb"
    assert updater.asset_name("macos") in ("mycat-macos-arm64.zip", "mycat-macos-x64.zip")
    assert updater.asset_name("source") == ""


# Trimmed from the real api.github.com/repos/yumiaura/myCat/releases/latest
# response for 0.1.37 (no network in tests). It keeps the look-alikes: the
# AppImage's .zsync and the legacy mycat-x86_64.AppImage duplicate.
RELEASE_0_1_37 = json.loads(
    """
{
  "tag_name": "0.1.37",
  "draft": false,
  "prerelease": false,
  "assets": [
    {"name": "mycat-linux-amd64.deb", "state": "uploaded", "size": 93628574,
     "digest": "sha256:5f7637c90ce7b5c48bdf65497922273cb839dc9ec3f59341df30610c4e0abf97",
     "browser_download_url": "https://github.com/yumiaura/myCat/releases/download/0.1.37/mycat-linux-amd64.deb"},
    {"name": "mycat-linux-x86_64.AppImage", "state": "uploaded", "size": 95009272,
     "digest": "sha256:d8dede5e0fdf869ba8921f895fe8a474dc76addb996247084b2c621105d8f76f",
     "browser_download_url":
       "https://github.com/yumiaura/myCat/releases/download/0.1.37/mycat-linux-x86_64.AppImage"},
    {"name": "mycat-linux-x86_64.AppImage.zsync", "state": "uploaded", "size": 324969,
     "digest": "sha256:fa730a1406ca27d217526b446fc263df01aa360bc89bc6b6d8bc800628be46fc",
     "browser_download_url":
       "https://github.com/yumiaura/myCat/releases/download/0.1.37/mycat-linux-x86_64.AppImage.zsync"},
    {"name": "mycat-macos-arm64.zip", "state": "uploaded", "size": 48228511,
     "digest": "sha256:c3a6e91e6b1876d78e4c825cde6fb2bf556be4a0a1c7a205b66bd07ac63e3c0c",
     "browser_download_url": "https://github.com/yumiaura/myCat/releases/download/0.1.37/mycat-macos-arm64.zip"},
    {"name": "mycat-macos-x64.zip", "state": "uploaded", "size": 52406772,
     "digest": "sha256:cebe80bfaf30d1c5d92499f3b14cf8f126141e2cd2442447325c3b6efcbbb562",
     "browser_download_url": "https://github.com/yumiaura/myCat/releases/download/0.1.37/mycat-macos-x64.zip"},
    {"name": "mycat-windows-x64.exe", "state": "uploaded", "size": 61530582,
     "digest": "sha256:995546da86b5e0d94b08713511b5b3551ecd249cf1b27baf234b18ac26e5abf4",
     "browser_download_url": "https://github.com/yumiaura/myCat/releases/download/0.1.37/mycat-windows-x64.exe"},
    {"name": "mycat-x86_64.AppImage", "state": "uploaded", "size": 95009272,
     "digest": "sha256:d8dede5e0fdf869ba8921f895fe8a474dc76addb996247084b2c621105d8f76f",
     "browser_download_url": "https://github.com/yumiaura/myCat/releases/download/0.1.37/mycat-x86_64.AppImage"}
  ]
}
"""
)

WINDOWS_SHA256 = "995546da86b5e0d94b08713511b5b3551ecd249cf1b27baf234b18ac26e5abf4"


def release_with(name, **changes):
    """A copy of the 0.1.37 fixture with the asset ``name`` changed (None drops a key)."""
    release = copy.deepcopy(RELEASE_0_1_37)
    for asset in release["assets"]:
        if asset["name"] == name:
            for key, value in changes.items():
                if value is None:
                    asset.pop(key, None)
                else:
                    asset[key] = value
    return release


def test_parse_sha256_digest():
    assert updater.parse_sha256_digest(f"sha256:{WINDOWS_SHA256}") == WINDOWS_SHA256
    assert updater.parse_sha256_digest(f"sha256:{WINDOWS_SHA256.upper()}") == WINDOWS_SHA256
    assert updater.parse_sha256_digest(f"sha1:{WINDOWS_SHA256[:40]}") == ""
    assert updater.parse_sha256_digest(f"sha256:{WINDOWS_SHA256[:63]}") == ""
    assert updater.parse_sha256_digest(f"sha256:{WINDOWS_SHA256}0") == ""
    assert updater.parse_sha256_digest("sha256:" + "g" * 64) == ""
    assert updater.parse_sha256_digest("") == ""
    assert updater.parse_sha256_digest(None) == ""


def test_release_asset_picks_versioned_url_and_digest():
    asset = updater.release_asset(RELEASE_0_1_37, "mycat-windows-x64.exe")
    assert asset == {
        "name": "mycat-windows-x64.exe",
        "url": "https://github.com/yumiaura/myCat/releases/download/0.1.37/mycat-windows-x64.exe",
        "sha256": WINDOWS_SHA256,
    }
    for name in ("mycat-macos-arm64.zip", "mycat-macos-x64.zip"):
        assert updater.release_asset(RELEASE_0_1_37, name)["url"].endswith(f"/0.1.37/{name}")


def test_release_asset_matches_the_name_exactly():
    # Neither the .zsync nor the legacy duplicate stands in for the AppImage.
    asset = updater.release_asset(RELEASE_0_1_37, "mycat-linux-x86_64.AppImage")
    assert asset["url"].endswith("/0.1.37/mycat-linux-x86_64.AppImage")
    only_lookalikes = copy.deepcopy(RELEASE_0_1_37)
    only_lookalikes["assets"] = [
        asset for asset in only_lookalikes["assets"] if asset["name"] != "mycat-linux-x86_64.AppImage"
    ]
    assert updater.release_asset(only_lookalikes, "mycat-linux-x86_64.AppImage") is None
    assert updater.release_asset(RELEASE_0_1_37, "mycat-windows-x64") is None
    assert updater.release_asset(RELEASE_0_1_37, "") is None


def test_release_asset_missing_when_not_listed():
    release = copy.deepcopy(RELEASE_0_1_37)
    release["assets"] = [asset for asset in release["assets"] if asset["name"] != "mycat-windows-x64.exe"]
    assert updater.release_asset(release, "mycat-windows-x64.exe") is None
    assert updater.release_asset({"tag_name": "0.1.37"}, "mycat-windows-x64.exe") is None
    assert updater.release_asset(None, "mycat-windows-x64.exe") is None


def test_release_asset_needs_a_sha256_digest():
    name = "mycat-windows-x64.exe"
    assert updater.release_asset(release_with(name, digest=None), name) is None
    assert updater.release_asset(release_with(name, digest="sha1:" + "a" * 40), name) is None


def test_release_asset_skips_uploads_in_progress():
    name = "mycat-windows-x64.exe"
    assert updater.release_asset(release_with(name, state="starter"), name) is None


def test_release_asset_only_from_this_repos_download_url():
    name = "mycat-windows-x64.exe"
    elsewhere = release_with(name, browser_download_url=f"https://example.com/0.1.37/{name}")
    assert updater.release_asset(elsewhere, name) is None
    latest = release_with(
        name, browser_download_url=f"https://github.com/yumiaura/myCat/releases/latest/download/{name}"
    )
    assert updater.release_asset(latest, name) is None


def test_staging_path_for_temp_kinds():
    # deb/macos/windows stage in the temp dir under their asset name.
    assert updater.staging_path("deb").endswith("mycat-linux-amd64.deb")


def test_update_hint_is_git_pull_in_checkout():
    # The test suite runs from the git checkout, so it should suggest git pull.
    assert updater.update_hint("source") == "git pull"


def test_download_writes_full_file(tmp_path, monkeypatch):
    body = b"x" * 500
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: FakeResponse(body, len(body)))
    dest = tmp_path / "build.bin"
    updater.download("https://example/build", str(dest))
    assert dest.read_bytes() == body


def test_download_raises_on_truncated_transfer(tmp_path, monkeypatch):
    # Server promises 500 bytes but the stream ends after 100 — a silent
    # truncation that must NOT be swapped in.
    calls = {"n": 0}

    def fake_urlopen(request, timeout):
        calls["n"] += 1
        return FakeResponse(b"x" * 100, content_length=500)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(OSError):
        updater.download("https://example/build", str(tmp_path / "build.bin"), attempts=3)
    assert calls["n"] == 3  # retried the full number of attempts before giving up


def test_download_retries_then_succeeds(tmp_path, monkeypatch):
    body = b"x" * 500
    responses = [FakeResponse(b"x" * 100, 500), FakeResponse(body, 500)]  # truncated, then whole
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: responses.pop(0))
    dest = tmp_path / "build.bin"
    updater.download("https://example/build", str(dest), attempts=3)
    assert dest.read_bytes() == body


def test_download_does_not_retry_on_cancel(tmp_path, monkeypatch):
    # A cancelling progress callback is not a network error — it must abort
    # immediately, not burn through the retries.
    calls = {"n": 0}

    def fake_urlopen(request, timeout):
        calls["n"] += 1
        return FakeResponse(b"x" * 500, 500)

    def cancel(done, total):
        raise RuntimeError("cancelled")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="cancelled"):
        updater.download("https://example/build", str(tmp_path / "build.bin"), progress=cancel)
    assert calls["n"] == 1  # no retry on cancel


def test_install_kind_is_snap_inside_a_snap(monkeypatch):
    # snapd sets SNAP for every snap app; it wins over APPIMAGE and the .deb default.
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater.sys, "platform", "linux")
    monkeypatch.setenv("SNAP", "/snap/mycat/12")
    assert updater.install_kind() == "snap"


def test_snap_is_told_to_refresh_not_self_updated():
    assert not updater.can_self_update("snap")
    assert updater.update_hint("snap") == "snap refresh mycat"
    assert updater.asset_name("snap") == ""


def test_install_kind_is_flatpak_inside_a_flatpak(monkeypatch):
    # A Flatpak runs the package unfrozen; FLATPAK_ID is what tells it apart from pip.
    monkeypatch.setenv("FLATPAK_ID", "io.github.yumiaura.myCat")
    assert updater.install_kind() == "flatpak"
    assert not updater.can_self_update("flatpak")
    assert updater.update_hint("flatpak") == "flatpak update io.github.yumiaura.myCat"


def test_install_kind_ignores_another_apps_flatpak(monkeypatch):
    # Every Flatpak app gets a FLATPAK_ID and passes it on, so a checkout run from
    # a terminal in a Flatpak editor is still a source install.
    monkeypatch.setenv("FLATPAK_ID", "com.visualstudio.code")
    assert updater.install_kind() == "source"


def test_download_accepts_matching_sha256(tmp_path, monkeypatch):
    body = b"x" * 500
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: FakeResponse(body, len(body)))
    dest = tmp_path / "build.bin"
    updater.download("https://example/build", str(dest), sha256=hashlib.sha256(body).hexdigest().upper())
    assert dest.read_bytes() == body


def test_download_deletes_file_on_sha256_mismatch(tmp_path, monkeypatch):
    # A complete file with the wrong hash is deleted and never retried, so the
    # caller cannot swap it in.
    calls = {"n": 0}

    def fake_urlopen(request, timeout):
        calls["n"] += 1
        return FakeResponse(b"x" * 500, 500)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    dest = tmp_path / "build.bin"
    with pytest.raises(updater.DigestMismatch):
        updater.download("https://example/build", str(dest), sha256=hashlib.sha256(b"other").hexdigest())
    assert not dest.exists()
    assert calls["n"] == 1


def test_download_mismatch_survives_a_locked_file(tmp_path, monkeypatch):
    # An AV scanner holding the file makes the delete fail; that must still be a
    # DigestMismatch, not a retried network error.
    calls = {"n": 0}

    def fake_urlopen(request, timeout):
        calls["n"] += 1
        return FakeResponse(b"x" * 500, 500)

    def locked_remove(path):
        raise PermissionError(32, "The process cannot access the file")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(updater.os, "remove", locked_remove)
    dest = tmp_path / "build.bin"
    with pytest.raises(updater.DigestMismatch):
        updater.download("https://example/build", str(dest), sha256=hashlib.sha256(b"other").hexdigest())
    assert calls["n"] == 1


def test_download_hashes_only_the_final_attempt(tmp_path, monkeypatch):
    # The hash restarts with each attempt, so a truncated first try does not
    # spoil the digest of the complete second one.
    body = b"y" * 500
    responses = [FakeResponse(body[:100], 500), FakeResponse(body, 500)]
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: responses.pop(0))
    dest = tmp_path / "build.bin"
    updater.download("https://example/build", str(dest), sha256=hashlib.sha256(body).hexdigest())
    assert dest.read_bytes() == body
