"""Self-updater pure logic: install-kind detection and asset naming."""

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


def test_asset_url_uses_stable_latest_download():
    url = updater.asset_url("appimage")
    assert url == "https://github.com/yumiaura/myCat/releases/latest/download/mycat-linux-x86_64.AppImage"
    assert updater.asset_url("source") == ""


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
