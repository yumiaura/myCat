"""Self-updater pure logic: install-kind detection and asset naming."""

import copy
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import types
import urllib.error
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
    # Windows/macOS/AppImage download + relaunch; the rest just get notified.
    assert updater.can_self_update("macos")
    assert updater.can_self_update("windows")
    assert updater.can_self_update("appimage")
    assert not updater.can_self_update("deb")
    assert not updater.can_self_update("source")
    assert not updater.can_self_update("winget")


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
    assert updater.asset_name("winget") == ""


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
    # deb/macos stage in the temp dir under their asset name.
    assert updater.staging_path("deb").endswith("mycat-linux-amd64.deb")


def test_windows_stages_beside_the_exe(monkeypatch):
    # Beside the exe, so the swapper's move is a same-volume rename.
    monkeypatch.setattr(updater.sys, "executable", r"D:\Игры\myCat\mycat.exe")
    assert updater.staging_path("windows") == r"D:\Игры\myCat\mycat.exe.new"


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


USER_WINGET_EXE = (
    r"C:\Users\anna maria\AppData\Local\Microsoft\WinGet\Packages"
    r"\yumiaura.myCat_Microsoft.Winget.Source_8wekyb3d8bbwe\mycat-windows-x64.exe"
)
LOCATION_EXE = r"D:\Tools\myCat\mycat-windows-x64.exe"


class FakeKey:
    """An open registry key: a context manager naming its path."""

    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_winreg(hives, opened=None):
    """A read-only winreg over {hive: {subkey name: {value name: data}}} for the
    Uninstall key. ``opened`` records every OpenKey access mode."""

    def open_key(parent, sub_key, reserved=0, access=0):
        if opened is not None:
            opened.append(access)
        if isinstance(parent, FakeKey):
            entries = hives[parent.path[0]]
            if sub_key not in entries:
                raise FileNotFoundError(sub_key)
            return FakeKey((parent.path[0], sub_key))
        if parent not in hives or sub_key != updater.UNINSTALL_KEY:
            raise FileNotFoundError(sub_key)
        return FakeKey((parent,))

    def enum_key(key, index):
        names = list(hives[key.path[0]])
        if index >= len(names):
            raise OSError("no more data")
        return names[index]

    def query_value(key, name):
        values = hives[key.path[0]][key.path[1]]
        if name not in values:
            raise FileNotFoundError(name)
        return values[name], 1

    return types.SimpleNamespace(
        HKEY_CURRENT_USER="HKCU",
        HKEY_LOCAL_MACHINE="HKLM",
        KEY_READ=0x20019,
        OpenKey=open_key,
        EnumKey=enum_key,
        QueryValueEx=query_value,
    )


def winget_entry(**overrides):
    entry = {
        "WinGetPackageIdentifier": "yumiaura.myCat",
        "WinGetInstallerType": "portable",
        "TargetFullPath": LOCATION_EXE,
        "InstallLocation": r"D:\Tools\myCat",
    }
    entry.update(overrides)
    return entry


def windows_build(monkeypatch, exe):
    """Pretend to be the frozen Windows exe at ``exe`` (realpath is identity, as
    on Linux it would prefix the cwd to a Windows path)."""
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater.sys, "platform", "win32")
    monkeypatch.setattr(updater.sys, "executable", exe)
    monkeypatch.setattr(updater.os.path, "realpath", lambda path: path)


@pytest.mark.parametrize(
    "exe",
    [
        USER_WINGET_EXE,
        r"C:\Program Files\WinGet\Packages\yumiaura.myCat_Microsoft.Winget.Source_8wekyb3d8bbwe\mycat.exe",
        r"c:\users\a\appdata\local\microsoft\winget\packages\YUMIAURA.MYCAT_msstore\mycat.exe",
        r"C:\Users\a\AppData\Local\Microsoft\WinGet\Packages\yumiaura.myCat_local\bin\mycat.exe",
        "C:/Users/a/AppData/Local/Microsoft/WinGet/Packages/yumiaura.myCat_x/mycat.exe",
    ],
)
def test_winget_package_paths_are_recognised(exe):
    # User and machine scope, any case, any source suffix, either slash.
    assert updater.is_winget_package_path(exe)


@pytest.mark.parametrize(
    "exe",
    [
        r"C:\Users\anna maria\Downloads\mycat-windows-x64.exe",
        r"C:\Tools\yumiaura.myCat_copy\mycat.exe",
        r"C:\Tools\Packages\yumiaura.myCat_x\mycat.exe",
        r"C:\WinGet\Other\Packages\yumiaura.myCat_x\mycat.exe",
        r"C:\WinGet\Packages\yumiaura.myCatalog_x\mycat.exe",
        r"C:\WinGet\Packages\yumiaura.myCat\mycat.exe",
        r"C:\WinGet\Packages\yumiaura.myCat_x.exe",
        "",
    ],
)
def test_look_alike_paths_are_not_winget(exe):
    # Only a yumiaura.myCat_* folder directly in WinGet\Packages counts, and the
    # exe's own file name never does.
    assert not updater.is_winget_package_path(exe)


def test_install_kind_is_winget_in_a_winget_package_folder(monkeypatch):
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg({}))
    windows_build(monkeypatch, USER_WINGET_EXE)
    assert updater.install_kind() == "winget"


def test_install_kind_is_windows_for_a_downloaded_exe(monkeypatch):
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg({"HKCU": {}, "HKLM": {}}))
    windows_build(monkeypatch, r"C:\Users\anna maria\Downloads\mycat-windows-x64.exe")
    assert updater.install_kind() == "windows"


def test_install_kind_uses_the_real_path_of_the_exe(monkeypatch):
    # WinGet's Links folder holds a symlink; its target is in Packages.
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg({}))
    windows_build(monkeypatch, r"C:\Users\a\AppData\Local\Microsoft\WinGet\Links\mycat.exe")
    monkeypatch.setattr(updater.os.path, "realpath", lambda path: USER_WINGET_EXE)
    assert updater.install_kind() == "winget"


@pytest.mark.parametrize("hive", ["HKCU", "HKLM"])
def test_install_kind_is_winget_for_a_location_install(monkeypatch, hive):
    # `winget install --location D:\Tools\myCat` leaves no Packages folder, only
    # the uninstall entry, under HKCU (user scope) or HKLM (machine scope).
    hives = {"HKCU": {"Some.Other_App": {}}, "HKLM": {}}
    hives[hive]["yumiaura.myCat_Microsoft.Winget.Source_8wekyb3d8bbwe"] = winget_entry()
    opened = []
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg(hives, opened))
    windows_build(monkeypatch, LOCATION_EXE)
    assert updater.install_kind() == "winget"
    assert set(opened) == {0x20019}  # read-only access only


@pytest.mark.parametrize(
    "entry",
    [
        winget_entry(TargetFullPath=r"d:\tools\MYCAT\mycat-windows-x64.exe", InstallLocation=""),
        winget_entry(TargetFullPath="", InstallLocation="D:\\Tools\\myCat\\"),
    ],
)
def test_registry_matches_the_target_or_the_install_location(monkeypatch, entry):
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg({"HKCU": {"yumiaura.myCat_local": entry}}))
    assert updater.winget_registry_lists(LOCATION_EXE)


def test_registry_matches_a_location_install_behind_a_junction(monkeypatch):
    # `--location D:\Tools\myCat` where D:\Tools is a junction to E:\Apps (or D:
    # a subst drive): WinGet records the D: path, realpath gives the E: one.
    resolved = r"E:\Apps\myCat\mycat-windows-x64.exe"
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg({"HKCU": {"yumiaura.myCat_local": winget_entry()}}))
    windows_build(monkeypatch, LOCATION_EXE)
    monkeypatch.setattr(updater.os.path, "realpath", lambda path: resolved if path == LOCATION_EXE else path)
    assert updater.install_kind() == "winget"

    # sys.executable already resolved: the registry path is resolved to match.
    monkeypatch.setattr(updater.sys, "executable", resolved)
    assert updater.install_kind() == "winget"

    location_only = winget_entry(TargetFullPath="", InstallLocation=r"D:\Tools\myCat")
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg({"HKCU": {"yumiaura.myCat_local": location_only}}))
    monkeypatch.setattr(
        updater.os.path, "realpath", lambda path: r"E:\Apps\myCat" if path == r"D:\Tools\myCat" else path
    )
    assert updater.winget_registry_lists(r"E:\Apps\myCat\mycat-windows-x64.exe")


@pytest.mark.parametrize(
    "entry",
    [
        winget_entry(WinGetPackageIdentifier="someone.myCat"),
        winget_entry(WinGetInstallerType="zip"),
        winget_entry(TargetFullPath=r"E:\Elsewhere\mycat.exe", InstallLocation=r"E:\Elsewhere"),
        {"TargetFullPath": LOCATION_EXE},
    ],
)
def test_registry_entries_that_are_not_this_winget_install(monkeypatch, entry):
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg({"HKCU": {"yumiaura.myCat_local": entry}, "HKLM": {}}))
    windows_build(monkeypatch, LOCATION_EXE)
    assert updater.install_kind() == "windows"


def test_registry_key_name_must_be_mycats(monkeypatch):
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg({"HKCU": {"Other.App_x": winget_entry()}}))
    assert not updater.winget_registry_lists(LOCATION_EXE)


def test_registry_errors_fall_back_to_the_path_test(monkeypatch):
    # No winreg at all (as on Linux), or one missing what the lookup needs, or
    # one that fails: the path test alone decides.
    monkeypatch.setitem(sys.modules, "winreg", None)
    windows_build(monkeypatch, LOCATION_EXE)
    assert updater.install_kind() == "windows"
    monkeypatch.setattr(updater.sys, "executable", USER_WINGET_EXE)
    assert updater.install_kind() == "winget"

    monkeypatch.setitem(sys.modules, "winreg", types.SimpleNamespace(HKEY_CURRENT_USER=1))
    assert not updater.winget_registry_lists(LOCATION_EXE)

    def broken(*args):
        raise PermissionError("access denied")

    failing = fake_winreg({"HKCU": {}, "HKLM": {}})
    failing.OpenKey = broken
    monkeypatch.setitem(sys.modules, "winreg", failing)
    monkeypatch.setattr(updater.sys, "executable", LOCATION_EXE)
    assert updater.install_kind() == "windows"


def test_winget_is_told_to_upgrade_not_self_updated():
    # Swapping the exe breaks WinGet's hash check on the next upgrade/uninstall.
    assert not updater.can_self_update("winget")
    assert updater.update_hint("winget") == "winget upgrade --id yumiaura.myCat --exact"
    assert updater.asset_name("winget") == ""
    with pytest.raises(ValueError):
        updater.apply_and_relaunch("winget", "unused")


# The Windows swapper. Paths with Cyrillic, Chinese and Korean letters, plus the
# characters cmd treats specially, must reach it intact through the environment.
UNICODE_DIR = "Ольга 文件 사용자 & 100% !"


def test_swapper_script_is_ascii_and_has_no_paths():
    script = updater.windows_swapper_script()
    assert script.isascii()
    assert "enabledelayedexpansion" not in script.lower()
    assert "!" not in script
    for name in ("%NEW%", "%EXE%", "%LOG%", "%PID%", "%RESULT%"):
        assert name in script
    assert 'move /Y "%NEW%" "%EXE%"' in script
    assert 'start "" "%EXE%"' in script
    # Every line ends CRLF, the way cmd expects.
    assert script.endswith("\r\n") and "\n" not in script.replace("\r\n", "")


def test_swapper_script_keeps_retry_wait_and_reports_outcome():
    script = updater.windows_swapper_script()
    assert 'tasklist /FI "PID eq %PID%"' in script
    assert "if %TRIES% LSS 30" in script
    assert f'echo {updater.SWAP_FAILED}> "%RESULT%"' in script
    assert f'echo {updater.SWAP_OK}> "%RESULT%"' in script
    # The failure still relaunches (the old exe), after writing the result.
    lines = script.split("\r\n")
    assert lines.index(":launch") > lines.index(f'echo {updater.SWAP_FAILED}> "%RESULT%"')
    for name in ("_MEIPASS2", "_PYI_ARCHIVE_FILE", "_PYI_APPLICATION_HOME_DIR", "_PYI_PARENT_PROCESS_LEVEL"):
        assert f'set "{name}="' in script


def test_swapper_env_carries_unicode_paths_and_drops_pyinstaller_vars():
    environ = {"PATH": "C:\\Windows", "_MEIPASS2": "x", "_PYI_ARCHIVE_FILE": "y", "PID": "stale"}
    env = updater.windows_swapper_env(
        "C:\\" + UNICODE_DIR + "\\mycat.exe.new",
        "C:\\" + UNICODE_DIR + "\\mycat.exe",
        "C:\\Temp\\Ольга\\mycat-update.log",
        4242,
        "C:\\Temp\\Ольга\\mycat-update.result",
        environ,
    )
    assert env["NEW"] == "C:\\" + UNICODE_DIR + "\\mycat.exe.new"
    assert env["EXE"] == "C:\\" + UNICODE_DIR + "\\mycat.exe"
    assert env["LOG"] == "C:\\Temp\\Ольга\\mycat-update.log"
    assert env["RESULT"] == "C:\\Temp\\Ольга\\mycat-update.result"
    assert env["PID"] == "4242"
    assert env["PATH"] == "C:\\Windows"
    assert not [key for key in env if key.startswith(("_PYI", "_MEIPASS"))]
    assert "_MEIPASS2" in environ  # the caller's dict is left alone


def test_clean_env_restores_the_original_library_path():
    environ = {"PATH": "/usr/bin", "LD_LIBRARY_PATH": "/tmp/_MEIabc:/opt/lib", "LD_LIBRARY_PATH_ORIG": "/opt/lib"}
    env = updater.clean_env(environ)
    assert env["LD_LIBRARY_PATH"] == "/opt/lib"
    assert "LD_LIBRARY_PATH_ORIG" not in env
    assert environ["LD_LIBRARY_PATH"] == "/tmp/_MEIabc:/opt/lib"  # the caller's dict is left alone


def test_clean_env_drops_a_library_path_the_bootloader_set():
    env = updater.clean_env({"PATH": "/usr/bin", "LD_LIBRARY_PATH": "/tmp/_MEIabc"})
    assert "LD_LIBRARY_PATH" not in env
    assert env["PATH"] == "/usr/bin"


def test_apply_windows_launches_ascii_swapper_with_paths_in_env(tmp_path, monkeypatch):
    temp = tmp_path / "Temp Ольга"
    temp.mkdir()
    exe_dir = tmp_path / UNICODE_DIR
    exe_dir.mkdir()
    exe = str(exe_dir / "mycat.exe")
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(temp))
    monkeypatch.setattr(updater.sys, "executable", exe)
    monkeypatch.setattr(updater.os, "getpid", lambda: 31337)
    monkeypatch.setenv("_MEIPASS2", "stale")
    (temp / "mycat-update.result").write_text("ok", encoding="ascii")
    launched = []

    class Recorder:
        def __init__(self, args, **kwargs):
            launched.append((args, kwargs))

    monkeypatch.setattr(updater.subprocess, "Popen", Recorder)
    updater.apply_windows(exe + ".new")

    ((args, kwargs),) = launched
    script = str(temp / "mycat-update.bat")
    assert args == ["cmd", "/c", script]
    assert kwargs["creationflags"] == updater.CREATE_NO_WINDOW
    raw = (temp / "mycat-update.bat").read_bytes()
    assert raw.decode("ascii") == updater.windows_swapper_script()  # CRLF kept, not doubled
    for part in ("Ольга", "文件", "사용자", "31337"):
        assert part.encode("utf-8") not in raw
    env = kwargs["env"]
    assert env["NEW"] == exe + ".new" and env["EXE"] == exe and env["PID"] == "31337"
    assert env["LOG"] == str(temp / "mycat-update.log")
    assert env["RESULT"] == str(temp / "mycat-update.result")
    assert "_MEIPASS2" not in env
    # A stale result from an earlier update is cleared before the swapper runs.
    assert not (temp / "mycat-update.result").exists()


# The macOS helper: paths reach it through the environment, never the script.
def test_macos_helper_script_has_no_paths_and_quotes_every_variable():
    import re

    script = updater.macos_helper_script()
    assert script.startswith("#!/bin/sh\nset -u\n")
    assert script.isascii()
    for name in ("NEW", "APP", "PID", "RESULT"):
        assert f'"${name}"' in script
    # Every variable opens a double-quoted word ($$, the shell's own PID, only
    # names the set-aside bundle inside one).
    for match in re.finditer(r"\$(\w+)", script.replace("$$", "")):
        assert script.replace("$$", "")[match.start() - 1] == '"', match.group()
    assert 'rm -rf "$APP"\n' not in script.split('if mv "$APP" "$old"')[0]


def test_macos_helper_script_swaps_only_after_a_checked_extract():
    script = updater.macos_helper_script()
    order = [
        'while kill -0 "$PID"',
        'case "$APP" in',
        '*.app) [ -d "$APP/Contents/MacOS" ] && tmp="$(mktemp -d "$parent/.mycat-update.XXXXXX")"',
        '/usr/bin/ditto -x -k "$NEW" "$tmp"',
        '[ -x "$tmp/mycat.app/Contents/MacOS/mycat" ]',
        'mv "$APP" "$old"',
        'mv "$tmp/mycat.app" "$APP"',
        f'outcome="{updater.SWAP_OK}"',
        'rm -rf "$old"',
        'mv "$old" "$APP"',
        'printf \'%s\\n\' "$outcome" > "$RESULT"',
        '/usr/bin/xattr -dr com.apple.quarantine "$APP"',
        '/usr/bin/open "$APP"',
        'rm -f "$NEW" "$0"',
    ]
    positions = [script.index(step) for step in order]
    assert positions == sorted(positions)
    # The old bundle is set aside beside the app under a dot name.
    assert 'old="$parent/.mycat-old.$$.app"' in script
    # Failure is the default outcome, so every path that does not reach the
    # swap reports it, and the app is reopened once whatever happened.
    assert script.index(f'outcome="{updater.SWAP_FAILED}"') < script.index("/usr/bin/ditto")
    assert script.count("/usr/bin/open ") == 1
    assert "\n/usr/bin/open" in script  # at the top level, not inside a branch


def test_macos_helper_env_carries_paths_and_drops_pyinstaller_vars():
    environ = {"PATH": "/usr/bin:/bin", "_MEIPASS2": "x", "_PYI_ARCHIVE_FILE": "y", "APP": "stale"}
    app = "/Users/olya/" + UNICODE_DIR + "/mycat.app"
    env = updater.macos_helper_env("/tmp/Ольга/mycat-macos.zip", app, 4242, "/tmp/r", environ)
    assert env["NEW"] == "/tmp/Ольга/mycat-macos.zip"
    assert env["APP"] == app
    assert env["PID"] == "4242"
    assert env["RESULT"] == "/tmp/r"
    assert env["PATH"] == "/usr/bin:/bin"
    assert not [key for key in env if key.startswith(("_PYI", "_MEIPASS"))]
    assert "_MEIPASS2" in environ


def test_macos_app_path_and_translocation(monkeypatch):
    exe = "/Applications/mycat.app/Contents/MacOS/mycat"
    assert updater.macos_app_path(exe) == "/Applications/mycat.app"
    assert not updater.is_translocated(exe)
    moved = "/private/var/folders/x/T/AppTranslocation/0A1B/d/mycat.app/Contents/MacOS/mycat"
    assert updater.is_translocated(moved)
    monkeypatch.setattr(updater.sys, "executable", moved)
    assert updater.is_translocated()
    assert updater.macos_app_path().endswith("/AppTranslocation/0A1B/d/mycat.app")


@pytest.mark.parametrize(
    ("executable", "expected"),
    [
        ("/Applications/mycat.app/Contents/MacOS/mycat", True),
        ("/Users/olya/Apps/My Cat.app/Contents/MacOS/mycat", True),
        # A bare PyInstaller build: three levels up is the user's Desktop.
        ("/Users/olya/Desktop/dist/mycat/mycat", False),
        ("/Users/olya/Desktop/mycat", False),
        ("/Applications/mycat.app/Contents/Resources/mycat", False),
        ("/Applications/mycat.app/MacOS/x/mycat", False),
    ],
)
def test_is_app_bundle_requires_the_bundle_layout(monkeypatch, executable, expected):
    assert updater.is_app_bundle(executable) is expected
    monkeypatch.setattr(updater.sys, "executable", executable)
    assert updater.is_app_bundle() is expected


def test_macos_helper_script_touches_nothing_but_a_bundle():
    # Defense in depth: without a .app with Contents/MacOS there is no temp
    # folder, so the extract, both moves and the delete are all skipped.
    script = updater.macos_helper_script()
    guard = script.index('case "$APP" in')
    assert script.index('tmp=""') < guard < script.index("mktemp")
    assert script.index("esac") < script.index('if [ -n "$tmp" ] && /usr/bin/ditto')
    assert script.count("mktemp") == 1


def test_macos_gate_probes_the_folder_beside_the_bundle(tmp_path):
    # main.py passes the bundle path to staging_writable: the probe lands in
    # the bundle's folder and the bundle itself is never touched.
    app = tmp_path / "mycat.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    assert updater.staging_writable(str(app))
    assert sorted(path.name for path in tmp_path.iterdir()) == ["mycat.app"]


def test_apply_macos_launches_helper_with_paths_in_env(tmp_path, monkeypatch):
    temp = tmp_path / "Temp Ольга"
    temp.mkdir()
    exe = str(tmp_path / UNICODE_DIR / "mycat.app" / "Contents" / "MacOS" / "mycat")
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(temp))
    monkeypatch.setattr(updater.sys, "executable", exe)
    monkeypatch.setattr(updater.os, "getpid", lambda: 31337)
    monkeypatch.setenv("_MEIPASS2", "stale")
    (temp / "mycat-update.result").write_text("ok", encoding="ascii")
    launched = []

    class Recorder:
        def __init__(self, args, **kwargs):
            launched.append((args, kwargs))

    monkeypatch.setattr(updater.subprocess, "Popen", Recorder)
    zip_path = str(temp / "mycat-macos.zip")
    updater.apply_and_relaunch("macos", zip_path)

    ((args, kwargs),) = launched
    script = temp / "mycat-update.sh"
    assert args == ["/bin/sh", str(script)]
    assert kwargs["start_new_session"] is True
    raw = script.read_bytes()
    assert raw.decode("utf-8") == updater.macos_helper_script()
    for part in ("Ольга", "文件", "사용자", "31337"):
        assert part.encode("utf-8") not in raw
    env = kwargs["env"]
    assert env["NEW"] == zip_path
    assert env["APP"] == str(tmp_path / UNICODE_DIR / "mycat.app")
    assert env["PID"] == "31337"
    assert env["RESULT"] == str(temp / "mycat-update.result")
    assert "_MEIPASS2" not in env
    # A stale result from an earlier update is cleared before the helper runs.
    assert not (temp / "mycat-update.result").exists()


def test_staging_writable_creates_and_removes_the_probe(tmp_path):
    path = tmp_path / "mycat.exe.new"
    assert updater.staging_writable(str(path))
    assert not path.exists()
    assert list(tmp_path.iterdir()) == []


def test_staging_writable_never_touches_a_download_in_progress(tmp_path):
    # A check that runs while a download writes the staging file must not
    # truncate it, so the probe is a separate file.
    path = tmp_path / "mycat.exe.new"
    path.write_bytes(b"half a download")
    assert updater.staging_writable(str(path))
    assert path.read_bytes() == b"half a download"


def test_staging_writable_clears_a_probe_left_by_a_crash(tmp_path):
    (tmp_path / ".mycat-write-test").write_bytes(b"")
    assert updater.staging_writable(str(tmp_path / "mycat.exe.new"))
    assert list(tmp_path.iterdir()) == []


def test_staging_writable_is_false_when_the_file_cannot_be_created(tmp_path, monkeypatch):
    def refuse(path, mode="r", *args, **kwargs):
        raise PermissionError(13, "Access is denied", path)

    monkeypatch.setattr("builtins.open", refuse)
    assert not updater.staging_writable(str(tmp_path / "mycat.exe.new"))


def test_remove_file_ignores_a_missing_file(tmp_path):
    leftover = tmp_path / "mycat.exe.new"
    leftover.write_bytes(b"partial")
    updater.remove_file(str(leftover))
    assert not leftover.exists()
    updater.remove_file(str(leftover))  # already gone: no error


@pytest.mark.parametrize("written", ["ok\r\n", "swap-failed \r\n"])
def test_take_update_result_reads_once(tmp_path, monkeypatch, written):
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    (tmp_path / "mycat-update.result").write_bytes(written.encode("ascii"))
    assert updater.take_update_result() == written.strip()
    assert not (tmp_path / "mycat-update.result").exists()
    assert updater.take_update_result() == ""


def test_new_update_messages_are_in_every_catalog():
    # Shown by the startup report and the bundle, not-writable and translocation checks in main.py.
    from mycat import i18n

    texts = [
        "The folder with myCat is not writable, so it cannot update itself. "
        "Download the new version from the releases page.",
        "The new version could not replace the old one, so the old one was started again.",
        "Move mycat.app to the Applications folder, then try again.",
        "This copy of myCat cannot update itself. Download the new version from the releases page.",
        "The new version could not replace the old one, so the old one was kept. "
        "Download the new version from the releases page.",
    ]
    for code in ("en", "ru", "zh", "ko"):
        for text in texts:
            translated = i18n.CATALOGS[code][text]
            assert "\u2014" not in translated and "\u00b7" not in translated


# The AppImage: staged beside itself, verified, renamed over the old file.
APPIMAGE_HEAD = b"\x7fELF\x02\x01\x01\x00AI\x02" + b"\x00" * 5


def fake_appimage(tmp_path, monkeypatch, mode=0o750):
    folder = tmp_path / "My Apps Ольга"
    folder.mkdir()
    old = folder / "mycat.AppImage"
    old.write_bytes(APPIMAGE_HEAD + b"old build")
    old.chmod(mode)
    monkeypatch.setenv("APPIMAGE", str(old))
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    return old


def test_appimage_stages_beside_itself_without_the_extension(tmp_path, monkeypatch):
    old = fake_appimage(tmp_path, monkeypatch)
    part = updater.staging_path("appimage")
    assert part == str(old.parent / ".mycat-update.part")
    assert not part.endswith(".AppImage")
    assert updater.staging_writable(part)
    assert sorted(path.name for path in old.parent.iterdir()) == ["mycat.AppImage"]


@pytest.mark.parametrize(
    ("machine", "appimage", "expected"),
    [
        ("x86_64", "/home/olya/Apps/mycat.AppImage", True),
        ("aarch64", "/home/olya/Apps/mycat.AppImage", False),
        ("x86_64", "", False),
    ],
)
def test_appimage_updatable(monkeypatch, machine, appimage, expected):
    monkeypatch.setattr(updater.platform, "machine", lambda: machine)
    monkeypatch.setenv("APPIMAGE", appimage)
    monkeypatch.setenv("APPDIR", "/tmp/.mount_mycatAb12")
    monkeypatch.setattr(updater.sys, "executable", "/tmp/.mount_mycatAb12/usr/bin/mycat")
    assert updater.appimage_updatable() is expected


@pytest.mark.parametrize(
    ("environ", "executable", "expected"),
    [
        (
            {"APPIMAGE": "/home/olya/Apps/mycat.AppImage", "APPDIR": "/tmp/.mount_mycat1"},
            "/tmp/.mount_mycat1/usr/bin/mycat",
            True,
        ),
        # The .deb build started from a terminal that is another app's AppImage.
        ({"APPIMAGE": "/home/olya/Apps/WezTerm.AppImage", "APPDIR": "/tmp/.mount_WezTe1"}, "/usr/bin/mycat", False),
        # A mount whose name merely starts like APPDIR is not inside it.
        (
            {"APPIMAGE": "/home/olya/Apps/WezTerm.AppImage", "APPDIR": "/tmp/.mount_x"},
            "/tmp/.mount_xy/usr/bin/mycat",
            False,
        ),
        ({"APPIMAGE": "/home/olya/Apps/mycat.AppImage"}, "/tmp/.mount_mycat1/usr/bin/mycat", False),
        ({"APPDIR": "/tmp/.mount_mycat1"}, "/tmp/.mount_mycat1/usr/bin/mycat", False),
    ],
)
def test_runs_from_appimage(environ, executable, expected):
    assert updater.runs_from_appimage(environ, executable) is expected


def test_deb_started_from_another_appimage_is_not_an_appimage(monkeypatch):
    # Another AppImage's runtime exports APPIMAGE and APPDIR to its children, so
    # the .deb build started from it must neither count as an AppImage nor offer
    # to put itself over that other app's file.
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater.sys, "platform", "linux")
    monkeypatch.setattr(updater.sys, "executable", "/usr/bin/mycat")
    monkeypatch.setattr(updater.platform, "machine", lambda: "x86_64")
    monkeypatch.delenv("SNAP", raising=False)
    monkeypatch.setenv("APPIMAGE", "/home/olya/Apps/WezTerm.AppImage")
    monkeypatch.setenv("APPDIR", "/tmp/.mount_WezTe1")
    assert updater.install_kind() == "deb"
    assert not updater.appimage_updatable()


def test_install_kind_is_appimage_inside_its_own_mount(monkeypatch):
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater.sys, "platform", "linux")
    monkeypatch.setattr(updater.sys, "executable", "/tmp/.mount_mycat1/usr/bin/mycat")
    monkeypatch.delenv("SNAP", raising=False)
    monkeypatch.setenv("APPIMAGE", "/home/olya/Apps/mycat.AppImage")
    monkeypatch.setenv("APPDIR", "/tmp/.mount_mycat1")
    assert updater.install_kind() == "appimage"


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (APPIMAGE_HEAD + b"payload", True),
        (b"\x7fELF\x02\x01\x01\x00AI\x01" + b"\x00" * 5, False),  # type 1
        (b"\x7fELF\x02\x01\x01\x00\x00\x00\x00", False),  # a plain ELF
        (b"<html>captive portal</html>", False),
        (b"\x7fELF", False),  # too short
    ],
)
def test_is_appimage_file(tmp_path, content, expected):
    path = tmp_path / ".mycat-update.part"
    path.write_bytes(content)
    assert updater.is_appimage_file(str(path)) is expected


def test_is_appimage_file_is_false_for_a_missing_file(tmp_path):
    assert not updater.is_appimage_file(str(tmp_path / "nothing"))


def test_replace_appimage_renames_over_the_old_file_with_its_mode(tmp_path, monkeypatch):
    old = fake_appimage(tmp_path, monkeypatch, mode=0o640)
    part = old.parent / ".mycat-update.part"
    part.write_bytes(APPIMAGE_HEAD + b"new build")
    part.chmod(0o600)
    new_inode = part.stat().st_ino
    updater.replace_appimage(str(part), str(old))
    assert old.read_bytes() == APPIMAGE_HEAD + b"new build"
    assert old.stat().st_ino == new_inode
    assert (old.stat().st_mode & 0o777) == 0o740  # the old mode, plus u+x
    assert not part.exists()


def test_replace_appimage_keeps_the_old_file_when_the_download_is_no_appimage(tmp_path, monkeypatch):
    old = fake_appimage(tmp_path, monkeypatch)
    part = old.parent / ".mycat-update.part"
    part.write_bytes(b"<html>captive portal</html>")
    with pytest.raises(updater.DigestMismatch):
        updater.replace_appimage(str(part), str(old))
    assert old.read_bytes() == APPIMAGE_HEAD + b"old build"
    assert not part.exists()


def test_replace_appimage_keeps_the_old_file_when_the_rename_fails(tmp_path, monkeypatch):
    old = fake_appimage(tmp_path, monkeypatch)
    part = old.parent / ".mycat-update.part"
    part.write_bytes(APPIMAGE_HEAD + b"new build")

    def refuse(source, target):
        raise PermissionError(1, "Operation not permitted", target)

    monkeypatch.setattr(updater.os, "replace", refuse)
    with pytest.raises(updater.SwapFailed):
        updater.replace_appimage(str(part), str(old))
    assert old.read_bytes() == APPIMAGE_HEAD + b"old build"
    assert not part.exists()


def test_appimage_relaunch_script_waits_for_the_pid_and_has_no_paths():
    script = updater.APPIMAGE_RELAUNCH_SCRIPT
    assert script.isascii()
    assert script.index('kill -0 "$PID"') < script.index('exec "$APPIMAGE"')


def test_appimage_relaunch_env_is_clean_and_carries_path_and_pid():
    environ = {
        "PATH": "/usr/bin",
        "_MEIPASS2": "x",
        "_PYI_ARCHIVE_FILE": "y",
        "LD_LIBRARY_PATH": "/tmp/_MEIabc:/opt/lib",
        "LD_LIBRARY_PATH_ORIG": "/opt/lib",
        "APPIMAGE": "stale",
    }
    env = updater.appimage_relaunch_env("/home/Ольга/Apps/mycat.AppImage", 4242, environ)
    assert env["APPIMAGE"] == "/home/Ольга/Apps/mycat.AppImage"
    assert env["PID"] == "4242"
    assert env["PATH"] == "/usr/bin"
    assert env["LD_LIBRARY_PATH"] == "/opt/lib"
    assert not [key for key in env if key.startswith(("_PYI", "_MEIPASS")) or key == "LD_LIBRARY_PATH_ORIG"]


def test_apply_appimage_replaces_the_file_and_starts_the_helper(tmp_path, monkeypatch):
    old = fake_appimage(tmp_path, monkeypatch)
    part = old.parent / ".mycat-update.part"
    part.write_bytes(APPIMAGE_HEAD + b"new build")
    monkeypatch.setattr(updater.os, "getpid", lambda: 31337)
    monkeypatch.setenv("_MEIPASS2", "stale")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEIabc")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    (tmp_path / "mycat-update.result").write_text("swap-failed", encoding="ascii")
    launched = []

    class Recorder:
        def __init__(self, args, **kwargs):
            launched.append((args, kwargs))

    monkeypatch.setattr(updater.subprocess, "Popen", Recorder)
    updater.apply_and_relaunch("appimage", str(part))

    assert old.read_bytes() == APPIMAGE_HEAD + b"new build"
    assert not part.exists()
    ((args, kwargs),) = launched
    assert args == ["/bin/sh", "-c", updater.APPIMAGE_RELAUNCH_SCRIPT]
    assert kwargs["start_new_session"] is True
    env = kwargs["env"]
    assert env["APPIMAGE"] == str(old) and env["PID"] == "31337"
    assert "_MEIPASS2" not in env and "LD_LIBRARY_PATH" not in env
    # The stale result is replaced by this update's outcome, read once later.
    assert updater.take_update_result() == updater.SWAP_OK


def test_apply_appimage_reports_a_failed_restart_after_the_swap(tmp_path, monkeypatch):
    old = fake_appimage(tmp_path, monkeypatch)
    part = old.parent / ".mycat-update.part"
    part.write_bytes(APPIMAGE_HEAD + b"new build")

    def refuse(*args, **kwargs):
        raise BlockingIOError(11, "Resource temporarily unavailable")

    monkeypatch.setattr(updater.subprocess, "Popen", refuse)
    with pytest.raises(updater.RelaunchFailed):
        updater.apply_and_relaunch("appimage", str(part))
    # The new version is in place and is what the next start runs.
    assert old.read_bytes() == APPIMAGE_HEAD + b"new build"
    assert updater.take_update_result() == updater.SWAP_OK


def test_apply_appimage_starts_nothing_when_the_swap_fails(tmp_path, monkeypatch):
    old = fake_appimage(tmp_path, monkeypatch)
    part = old.parent / ".mycat-update.part"
    part.write_bytes(b"not an appimage at all")
    (tmp_path / "mycat-update.result").write_text("ok", encoding="ascii")
    launched = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda *args, **kwargs: launched.append(args))
    with pytest.raises(updater.DigestMismatch):
        updater.apply_and_relaunch("appimage", str(part))
    assert launched == []
    assert old.read_bytes() == APPIMAGE_HEAD + b"old build"
    assert not part.exists()
    # The failure is shown right away, so nothing is left to report at the next start.
    assert updater.take_update_result() == ""


# PyPI installs: pip, pipx and uv tool, told apart from a checkout by the
# installed distribution's own metadata.
def fake_site(tmp_path, record=True, direct_url=None):
    """A site-packages with mycat 0.1.37 installed, as a wheel install leaves it."""
    site_dir = tmp_path / "site-packages"
    package = site_dir / "mycat"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    info = site_dir / "mycat-0.1.37.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: mycat\nVersion: 0.1.37\n", encoding="utf-8")
    if record:
        (info / "RECORD").write_text("mycat/__init__.py,,\nmycat-0.1.37.dist-info/METADATA,,\n", encoding="utf-8")
    if direct_url is not None:
        (info / "direct_url.json").write_text(json.dumps(direct_url), encoding="utf-8")
    return site_dir, importlib.metadata.Distribution.at(info)


def use_site(monkeypatch, tmp_path, dist, package, venv=True):
    prefix = tmp_path / "prefix"
    prefix.mkdir(exist_ok=True)
    monkeypatch.setattr(updater, "package_dir", lambda: package)
    monkeypatch.setattr(updater, "installed_distribution", lambda: dist)
    monkeypatch.setattr(updater.sys, "prefix", str(prefix))
    monkeypatch.setattr(updater.sys, "base_prefix", str(tmp_path / "base") if venv else str(prefix))
    return prefix


def test_package_kind_is_pip_for_a_wheel_install(tmp_path, monkeypatch):
    site_dir, dist = fake_site(tmp_path)
    use_site(monkeypatch, tmp_path, dist, site_dir / "mycat")
    assert updater.package_kind() == "pip"


def test_install_kind_asks_package_kind_when_not_frozen(monkeypatch):
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setattr(updater, "package_kind", lambda: "pipx")
    assert updater.install_kind() == "pipx"


def test_package_kind_is_pipx_or_uvtool_by_their_venv_marker(tmp_path, monkeypatch):
    site_dir, dist = fake_site(tmp_path)
    prefix = use_site(monkeypatch, tmp_path, dist, site_dir / "mycat")
    (prefix / "uv-receipt.toml").write_text("[tool]\n", encoding="utf-8")
    assert updater.package_kind() == "uvtool"
    (prefix / "pipx_metadata.json").write_text("{}", encoding="utf-8")
    assert updater.package_kind() == "pipx"


def test_package_kind_is_source_in_a_git_checkout(tmp_path, monkeypatch):
    site_dir, dist = fake_site(tmp_path)
    (site_dir / ".git").mkdir()
    use_site(monkeypatch, tmp_path, dist, site_dir / "mycat")
    assert updater.package_kind() == "source"


def test_package_kind_is_source_without_a_distribution(tmp_path, monkeypatch):
    site_dir, dist = fake_site(tmp_path)
    use_site(monkeypatch, tmp_path, None, site_dir / "mycat")
    assert updater.package_kind() == "source"


def test_package_kind_is_source_when_the_dist_is_another_copy(tmp_path, monkeypatch):
    # A checkout run while another mycat is pip-installed elsewhere.
    site_dir, dist = fake_site(tmp_path)
    checkout = tmp_path / "checkout" / "mycat"
    checkout.mkdir(parents=True)
    (checkout / "__init__.py").write_text("", encoding="utf-8")
    use_site(monkeypatch, tmp_path, dist, checkout)
    assert updater.package_kind() == "source"


def test_package_kind_is_source_when_the_dist_lists_no_files(tmp_path, monkeypatch):
    site_dir, dist = fake_site(tmp_path, record=False)
    use_site(monkeypatch, tmp_path, dist, site_dir / "mycat")
    assert updater.package_kind() == "source"


@pytest.mark.parametrize(
    "direct_url",
    [
        {"url": "file:///home/olya/myCat", "dir_info": {"editable": True}},
        {"url": "file:///home/olya/myCat", "dir_info": {}},
    ],
)
def test_package_kind_is_source_for_a_local_folder_install(tmp_path, monkeypatch, direct_url):
    site_dir, dist = fake_site(tmp_path, direct_url=direct_url)
    use_site(monkeypatch, tmp_path, dist, site_dir / "mycat")
    assert updater.package_kind() == "source"


def test_package_kind_is_pip_for_a_wheel_from_an_index_url(tmp_path, monkeypatch):
    direct_url = {"url": "https://files.example.com/mycat-0.1.37-py3-none-any.whl", "archive_info": {}}
    site_dir, dist = fake_site(tmp_path, direct_url=direct_url)
    use_site(monkeypatch, tmp_path, dist, site_dir / "mycat")
    assert updater.package_kind() == "pip"


def pip_env(monkeypatch, tmp_path, venv=True, user_site=None, pip=True):
    """A writable site-packages and an interpreter with pip, in a venv or not."""
    site_dir = tmp_path / "site-packages"
    site_dir.mkdir(exist_ok=True)
    stdlib = tmp_path / "stdlib"
    stdlib.mkdir(exist_ok=True)
    prefix = str(tmp_path / "prefix")
    monkeypatch.setattr(updater.sys, "prefix", prefix)
    monkeypatch.setattr(updater.sys, "base_prefix", str(tmp_path / "base") if venv else prefix)
    monkeypatch.setattr(updater.sys, "executable", "/home/olya/.venv/bin/python")
    monkeypatch.setattr(updater.sysconfig, "get_path", lambda name: str(stdlib))
    monkeypatch.setattr(updater.site, "getusersitepackages", lambda: str(user_site or tmp_path / "user-site"))
    monkeypatch.setattr(updater, "pip_available", lambda: pip)
    return site_dir, stdlib


def test_upgrade_command_for_pip_pins_the_announced_version(tmp_path, monkeypatch):
    site_dir, stdlib = pip_env(monkeypatch, tmp_path)
    assert updater.upgrade_command("pip", "v0.1.38", site_dir) == [
        "/home/olya/.venv/bin/python", "-m", "pip", "install", "--upgrade", "mycat==0.1.38",
    ]
    # Nothing was left behind by the writability probe.
    assert list(site_dir.iterdir()) == []


def test_upgrade_command_for_pip_in_the_user_site_adds_user(tmp_path, monkeypatch):
    site_dir, stdlib = pip_env(monkeypatch, tmp_path, venv=False, user_site=tmp_path / "site-packages")
    assert updater.upgrade_command("pip", "0.1.38", site_dir) == [
        "/home/olya/.venv/bin/python", "-m", "pip", "install", "--user", "--upgrade", "mycat==0.1.38",
    ]


def test_upgrade_command_for_pip_outside_the_user_site_has_no_user(tmp_path, monkeypatch):
    site_dir, stdlib = pip_env(monkeypatch, tmp_path, venv=False)
    assert "--user" not in updater.upgrade_command("pip", "0.1.38", site_dir)


def test_upgrade_command_is_empty_on_an_externally_managed_python(tmp_path, monkeypatch):
    site_dir, stdlib = pip_env(monkeypatch, tmp_path, venv=False, user_site=tmp_path / "site-packages")
    (stdlib / "EXTERNALLY-MANAGED").write_text("[externally-managed]\n", encoding="utf-8")
    assert updater.externally_managed()
    assert updater.upgrade_command("pip", "0.1.38", site_dir) == []


def test_marker_does_not_matter_inside_a_venv(tmp_path, monkeypatch):
    site_dir, stdlib = pip_env(monkeypatch, tmp_path, venv=True)
    (stdlib / "EXTERNALLY-MANAGED").write_text("[externally-managed]\n", encoding="utf-8")
    assert not updater.externally_managed()
    assert updater.upgrade_command("pip", "0.1.38", site_dir)


def test_upgrade_command_is_empty_without_pip_or_for_an_odd_version(tmp_path, monkeypatch):
    site_dir, stdlib = pip_env(monkeypatch, tmp_path, pip=False)
    assert updater.upgrade_command("pip", "0.1.38", site_dir) == []
    monkeypatch.setattr(updater, "pip_available", lambda: True)
    for latest in ("", "latest", "0.1.38 --index-url=https://example.com", "0.1.38;rm"):
        assert updater.upgrade_command("pip", latest, site_dir) == []


def test_upgrade_command_is_empty_when_the_site_is_not_writable(tmp_path, monkeypatch):
    site_dir, stdlib = pip_env(monkeypatch, tmp_path)

    def refuse(path, mode="r", *args, **kwargs):
        raise PermissionError(13, "Permission denied", path)

    monkeypatch.setattr("builtins.open", refuse)
    assert updater.upgrade_command("pip", "0.1.38", site_dir) == []
    monkeypatch.setattr(updater.shutil, "which", lambda name: "/home/olya/.local/bin/" + name)
    assert updater.upgrade_command("pipx", "0.1.38", site_dir) == []


def test_upgrade_command_for_pipx_and_uv_needs_their_tool(tmp_path, monkeypatch):
    site_dir, stdlib = pip_env(monkeypatch, tmp_path)
    monkeypatch.setattr(updater.shutil, "which", lambda name: "/home/olya/.local/bin/" + name)
    assert updater.upgrade_command("pipx", "0.1.38", site_dir) == ["/home/olya/.local/bin/pipx", "upgrade", "mycat"]
    assert updater.upgrade_command("uvtool", "0.1.38", site_dir) == [
        "/home/olya/.local/bin/uv", "tool", "upgrade", "mycat",
    ]
    monkeypatch.setattr(updater.shutil, "which", lambda name: None)
    assert updater.upgrade_command("pipx", "0.1.38", site_dir) == []
    assert updater.upgrade_command("uvtool", "0.1.38", site_dir) == []


def test_upgrade_command_is_empty_for_other_kinds(tmp_path, monkeypatch):
    site_dir, stdlib = pip_env(monkeypatch, tmp_path)
    for kind in ("source", "deb", "windows", "flatpak"):
        assert updater.upgrade_command(kind, "0.1.38", site_dir) == []


def test_package_kinds_have_hints_and_no_download():
    assert updater.update_hint("pipx") == "pipx upgrade mycat"
    assert updater.update_hint("uvtool") == "uv tool upgrade mycat"
    assert updater.update_hint("pip") == "pip install --upgrade mycat"
    for kind in updater.PACKAGE_KINDS:
        assert not updater.can_self_update(kind)
        assert updater.asset_name(kind) == ""


def test_pypi_has_version_reads_the_release_json_without_a_token(monkeypatch):
    seen = []
    body = json.dumps({"info": {"version": "0.1.38"}, "urls": [{"filename": "mycat-0.1.38.tar.gz"}]}).encode()

    def urlopen(request, timeout):
        seen.append(request)
        return FakeResponse(body, len(body))

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert updater.pypi_has_version("v0.1.38")
    (request,) = seen
    assert request.full_url == "https://pypi.org/pypi/mycat/0.1.38/json"
    assert request.get_header("Authorization") is None


def test_pypi_has_version_is_false_when_missing_empty_or_offline(monkeypatch):
    def missing(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", missing)
    assert not updater.pypi_has_version("0.1.38")
    body = json.dumps({"info": {}, "urls": []}).encode()
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: FakeResponse(body, len(body)))
    assert not updater.pypi_has_version("0.1.38")

    def offline(request, timeout):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr(urllib.request, "urlopen", offline)
    assert not updater.pypi_has_version("0.1.38")
    assert not updater.pypi_has_version("../../evil")


def test_run_package_upgrade_runs_quietly_without_stdin(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="Successfully installed mycat-0.1.38\n", stderr="")

    monkeypatch.setattr(updater.subprocess, "run", run)
    updater.run_package_upgrade(["/usr/bin/python3", "-m", "pip", "install", "--upgrade", "mycat==0.1.38"])
    ((command, kwargs),) = calls
    assert command[-1] == "mycat==0.1.38"
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["capture_output"] is True and kwargs["encoding"] == "utf-8"
    assert kwargs["timeout"] == updater.UPGRADE_TIMEOUT
    assert "shell" not in kwargs


def test_run_package_upgrade_reports_the_end_of_stderr(monkeypatch):
    stderr = "".join(f"line {number}\n" for number in range(40)) + "ERROR: No matching distribution found\n"
    monkeypatch.setattr(
        updater.subprocess, "run", lambda command, **kwargs: subprocess.CompletedProcess(command, 1, "", stderr)
    )
    with pytest.raises(updater.UpgradeFailed) as error:
        updater.run_package_upgrade(["pip"])
    message = str(error.value)
    assert message.endswith("ERROR: No matching distribution found")
    assert "line 26" in message and "line 25" not in message


def test_run_package_upgrade_reports_timeout_and_missing_tool(monkeypatch):
    def slow(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(updater.subprocess, "run", slow)
    with pytest.raises(updater.UpgradeFailed) as error:
        updater.run_package_upgrade(["/home/olya/.local/bin/pipx", "upgrade", "mycat"])
    # The UI translates the sentence from the reason and its details.
    assert error.value.reason == "timeout"
    assert error.value.details == {"tool": "pipx", "seconds": updater.UPGRADE_TIMEOUT}

    def missing(command, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", command[0])

    monkeypatch.setattr(updater.subprocess, "run", missing)
    with pytest.raises(updater.UpgradeFailed) as error:
        updater.run_package_upgrade(["/home/olya/.local/bin/pipx", "upgrade", "mycat"])
    assert error.value.reason == "output"


def test_run_package_upgrade_silent_failure_carries_tool_and_code(monkeypatch):
    monkeypatch.setattr(
        updater.subprocess, "run", lambda command, **kwargs: subprocess.CompletedProcess(command, 3, "", "\n")
    )
    with pytest.raises(updater.UpgradeFailed) as error:
        updater.run_package_upgrade(["/usr/bin/python3", "-m", "pip", "install", "--upgrade", "mycat==0.1.38"])
    assert error.value.reason == "exit"
    assert error.value.details == {"tool": "pip", "code": 3}


def test_tool_name_names_pip_pipx_and_uv():
    assert updater.tool_name(["C:\\Python\\python.exe", "-m", "pip", "install"]) == "pip"
    assert updater.tool_name(["C:\\Users\\Ольга\\pipx.EXE", "upgrade", "mycat"]) == "pipx"
    assert updater.tool_name(["/home/olya/.local/bin/uv", "tool", "upgrade", "mycat"]) == "uv"


def test_check_upgraded_wants_the_announced_version_on_disk(monkeypatch):
    # pipx and uv tool exit 0 when their view of PyPI has nothing newer yet.
    monkeypatch.setattr(updater.importlib.metadata, "version", lambda name: "0.1.38")
    with pytest.raises(updater.UpgradeFailed) as error:
        updater.check_upgraded(["/usr/bin/pipx", "upgrade", "mycat"], "v0.1.39")
    assert error.value.reason == "stale"
    assert error.value.details == {"tool": "pipx", "latest": "0.1.39"}
    updater.check_upgraded(["/usr/bin/pipx", "upgrade", "mycat"], "v0.1.38")

    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(updater.importlib.metadata, "version", missing)
    assert updater.installed_version() == ""
    with pytest.raises(updater.UpgradeFailed):
        updater.check_upgraded(["/usr/bin/uv", "tool", "upgrade", "mycat"], "0.1.38")


def test_relaunch_command_reuses_the_console_script(tmp_path):
    script = tmp_path / "Ольга bin" / "mycat"
    script.parent.mkdir()
    script.write_text("", encoding="utf-8")
    argv = [str(script), "--image", "/home/Ольга/my cat.zip", "--debug"]
    assert updater.relaunch_command(argv, "/usr/bin/python3") == argv


def test_relaunch_command_finds_the_windows_launcher_exe(tmp_path):
    launcher = tmp_path / "Scripts" / "mycat.exe"
    launcher.parent.mkdir()
    launcher.write_text("", encoding="utf-8")
    argv = [str(tmp_path / "Scripts" / "mycat"), "--pos", "10", "20"]
    assert updater.relaunch_command(argv, "python.exe") == [str(launcher), "--pos", "10", "20"]


def test_relaunch_command_falls_back_to_the_module(tmp_path):
    argv = [str(tmp_path / "site-packages" / "mycat" / "__main__.py"), "--ollama"]
    assert updater.relaunch_command(argv, "/opt/venv/bin/python") == ["/opt/venv/bin/python", "-m", "mycat", "--ollama"]


def test_relaunch_after_exit_waits_for_the_pid_then_runs_the_command(monkeypatch):
    launched = []

    class Recorder:
        def __init__(self, args, **kwargs):
            launched.append((args, kwargs))

    monkeypatch.setattr(updater.subprocess, "Popen", Recorder)
    monkeypatch.setattr(updater.os, "getpid", lambda: 31337)
    command = ["/home/olya/.local/bin/mycat", "--image", "/home/Ольга/a cat's $HOME.zip"]
    updater.relaunch_after_exit(command)
    ((args, kwargs),) = launched
    assert args == ["/bin/sh", "-c", updater.PACKAGE_RELAUNCH_SCRIPT, "mycat-relaunch", *command]
    assert kwargs["start_new_session"] is True
    assert kwargs["env"]["PID"] == "31337"
    script = updater.PACKAGE_RELAUNCH_SCRIPT
    assert script.isascii() and script.index('kill -0 "$PID"') < script.index('exec "$@"')


def test_relaunch_after_exit_reports_a_helper_that_cannot_start(monkeypatch):
    def refuse(*args, **kwargs):
        raise BlockingIOError(11, "Resource temporarily unavailable")

    monkeypatch.setattr(updater.subprocess, "Popen", refuse)
    with pytest.raises(updater.RelaunchFailed):
        updater.relaunch_after_exit(["/usr/bin/mycat"])


def test_windows_package_script_is_ascii_waits_then_upgrades_then_relaunches():
    script = updater.windows_package_script()
    assert script.isascii()
    assert script.endswith("\r\n") and "\n" not in script.replace("\r\n", "")
    assert "enabledelayedexpansion" not in script.lower()
    lines = script.split("\r\n")
    wait = lines.index('tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul')
    # "call" so a .bat or .cmd shim of pipx or uv returns to the helper.
    tool = lines.index('call "%TOOL%" %TOOLARGS% >>"%LOG%" 2>&1')
    verify = lines.index(f'"%PY%" -c "{updater.WINDOWS_VERSION_CODE}" >>"%LOG%" 2>&1')
    assert lines[tool + 1] == lines[verify + 1] == "if errorlevel 1 goto failed"
    ok = lines.index(f'echo {updater.SWAP_OK}> "%RESULT%"')
    failed = lines.index(f'echo {updater.UPGRADE_FAILED}> "%RESULT%"')
    launch = lines.index(f'"%PY%" -c "{updater.WINDOWS_RELAUNCH_CODE}" >>"%LOG%" 2>&1')
    assert wait < tool < verify < ok < failed < launch
    # The Python lines have no double quote or percent sign to break the cmd line.
    for code in (updater.WINDOWS_RELAUNCH_CODE, updater.WINDOWS_VERSION_CODE):
        assert '"' not in code and "%" not in code


def test_windows_version_code_fails_unless_the_version_is_installed(monkeypatch):
    monkeypatch.setattr(updater.importlib.metadata, "version", lambda name: "0.1.38")
    for wanted, code in (("0.1.38", 0), ("0.1.39", 1)):
        monkeypatch.setenv("VERSION", wanted)
        with pytest.raises(SystemExit) as stop:
            exec(updater.WINDOWS_VERSION_CODE, {})  # noqa: S102 - our own constant
        assert int(stop.value.code) == code


def test_windows_package_env_carries_unicode_paths_and_the_relaunch_as_json():
    environ = {"PATH": "C:\\Windows", "PID": "stale"}
    relaunch = ["C:\\" + UNICODE_DIR + "\\Scripts\\mycat.exe", "--image", "C:\\" + UNICODE_DIR + "\\cat.zip"]
    env = updater.windows_package_env(
        ["C:\\" + UNICODE_DIR + "\\python.exe", "-m", "pip", "install", "--user", "--upgrade", "mycat==0.1.38"],
        relaunch,
        "C:\\" + UNICODE_DIR + "\\pythonw.exe",
        "C:\\Temp\\Ольга\\mycat-update.log",
        4242,
        "C:\\Temp\\Ольга\\mycat-update.result",
        "v0.1.38",
        environ,
    )
    assert env["VERSION"] == "0.1.38"
    assert env["TOOL"] == "C:\\" + UNICODE_DIR + "\\python.exe"
    assert env["TOOLARGS"] == "-m pip install --user --upgrade mycat==0.1.38"
    assert json.loads(env["RELAUNCH"]) == relaunch
    assert env["PY"] == "C:\\" + UNICODE_DIR + "\\pythonw.exe"
    assert env["PID"] == "4242" and env["PATH"] == "C:\\Windows"
    assert environ["PID"] == "stale"  # the caller's dict is left alone


def test_windows_package_env_refuses_arguments_cmd_would_parse():
    for argument in ("mycat==0.1.38&calc", "a b", '"x"', "100%"):
        with pytest.raises(ValueError):
            updater.windows_package_env(["pip.exe", argument], [], "py", "log", 1, "result", "0.1.38", {})
    for version in ("0.1.38&calc", "", "1 2"):
        with pytest.raises(ValueError):
            updater.windows_package_env(["pip.exe", "-m", "pip"], [], "py", "log", 1, "result", version, {})


def test_apply_package_windows_writes_the_helper_and_starts_it(tmp_path, monkeypatch):
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(updater.os, "getpid", lambda: 31337)
    monkeypatch.setattr(updater.sys, "executable", str(tmp_path / "python.exe"))
    monkeypatch.setattr(updater.sys, "argv", [str(tmp_path / "mycat" / "__main__.py"), "--debug"])
    (tmp_path / "mycat-update.result").write_text("swap-failed", encoding="ascii")
    launched = []

    class Recorder:
        def __init__(self, args, **kwargs):
            launched.append((args, kwargs))

    monkeypatch.setattr(updater.subprocess, "Popen", Recorder)
    updater.apply_package_windows(
        [str(tmp_path / "python.exe"), "-m", "pip", "install", "--upgrade", "mycat==0.1.38"], "0.1.38"
    )
    script = tmp_path / "mycat-update.bat"
    assert script.read_bytes() == updater.windows_package_script().encode("ascii")
    ((args, kwargs),) = launched
    assert args == ["cmd", "/c", str(script)]
    assert kwargs["creationflags"] == updater.CREATE_NO_WINDOW
    env = kwargs["env"]
    assert env["PID"] == "31337" and env["VERSION"] == "0.1.38"
    assert json.loads(env["RELAUNCH"]) == [str(tmp_path / "python.exe"), "-m", "mycat", "--debug"]
    # The stale result is gone; the helper writes this run's outcome.
    assert updater.take_update_result() == ""


def test_windowless_python_prefers_pythonw(tmp_path):
    python = tmp_path / "python.exe"
    assert updater.windowless_python(str(python)) == str(python)
    (tmp_path / "pythonw.exe").write_text("", encoding="utf-8")
    assert updater.windowless_python(str(python)) == str(tmp_path / "pythonw.exe")


def test_pip_update_messages_are_in_every_catalog():
    # Shown by on_update_checked, install_update and the startup report in main.py.
    from mycat import i18n

    texts = [
        "Update available. Click Update to install it and restart.",
        "Installing update…",
        "Version {latest} is not on PyPI yet. Try again later.",
        "The new version could not be installed, so the old one was started again.",
        "{tool} did not finish in {seconds} seconds.",
        "{tool} failed with exit code {code}.",
        "{tool} finished, but version {latest} is not installed yet. Try again later.",
    ]
    for code in ("en", "ru", "zh", "ko"):
        for text in texts:
            translated = i18n.CATALOGS[code][text]
            assert "\u2014" not in translated and "\u00b7" not in translated
            for placeholder in ("{latest}", "{tool}", "{seconds}", "{code}"):
                assert (placeholder in text) == (placeholder in translated)


def test_busy_dialog_ignores_escape_and_close_until_the_work_ends(qapp):
    from PySide6 import QtCore, QtGui

    from mycat.main import BusyProgressDialog

    dialog = BusyProgressDialog("Installing update…")
    dialog.show()
    escape = QtGui.QKeyEvent(
        QtCore.QEvent.Type.KeyPress, QtCore.Qt.Key.Key_Escape, QtCore.Qt.KeyboardModifier.NoModifier
    )
    qapp.sendEvent(dialog, escape)
    dialog.reject()
    assert not dialog.close()
    assert dialog.isVisible()
    dialog.finish_busy()
    assert not dialog.isVisible()
