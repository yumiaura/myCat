"""Self-updater pure logic: install-kind detection and asset naming."""

from mycat import updater


def test_install_kind_is_source_when_not_frozen():
    # The test process is a normal interpreter, never a PyInstaller build.
    assert updater.install_kind() == "source"


def test_can_self_update():
    assert updater.can_self_update("appimage")
    assert updater.can_self_update("deb")
    assert updater.can_self_update("macos")
    assert updater.can_self_update("windows")
    assert not updater.can_self_update("source")


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


def test_source_update_command_is_git_pull_in_checkout():
    # The test suite runs from the git checkout, so it should suggest git pull.
    assert updater.source_update_command() == "git pull"
