"""Menu-entry visibility: defaults, persistence, and robustness."""

from mycat import menu_config


def test_all_entries_shown_by_default(tmp_path):
    visible = menu_config.load_menu_visibility(tmp_path / "config.ini")
    assert set(visible) == {key for key, _ in menu_config.MENU_ITEMS}
    assert all(visible.values())


def test_save_and_load_roundtrip(tmp_path):
    cfg = tmp_path / "config.ini"
    menu_config.save_menu_visibility({"chat": False, "github": False}, cfg)
    visible = menu_config.load_menu_visibility(cfg)
    assert visible["chat"] is False
    assert visible["github"] is False
    assert visible["reminder"] is True  # unlisted keys default to shown


def test_bad_value_falls_back_to_shown(tmp_path):
    cfg = tmp_path / "config.ini"
    cfg.write_text("[menu]\nchat = notabool\n")
    assert menu_config.load_menu_visibility(cfg)["chat"] is True


def test_save_keeps_other_sections(tmp_path):
    cfg = tmp_path / "config.ini"
    cfg.write_text("[settings]\nwait_time = 3.0\n")
    menu_config.save_menu_visibility({"activity": False}, cfg)
    text = cfg.read_text()
    assert "wait_time = 3.0" in text  # [settings] left intact
    assert menu_config.load_menu_visibility(cfg)["activity"] is False
