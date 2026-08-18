"""Menu-entry visibility: defaults, persistence, and robustness."""

from mycat import menu_config


def test_default_visibility(tmp_path):
    visible = menu_config.load_menu_visibility(tmp_path / "config.ini")
    assert set(visible) == {key for key, _ in menu_config.MENU_ITEMS}
    # Chat / LLM / Calendar start hidden; the rest are shown.
    assert visible["chat"] is False
    assert visible["llm"] is False
    assert visible["calendar"] is False
    assert visible["reminder"] is True
    assert visible["github"] is True
    assert visible["activity"] is True
    assert visible["chars"] is True


def test_save_and_load_roundtrip(tmp_path):
    cfg = tmp_path / "config.ini"
    menu_config.save_menu_visibility({"chat": True, "github": False}, cfg)
    visible = menu_config.load_menu_visibility(cfg)
    assert visible["chat"] is True  # explicitly re-enabled
    assert visible["github"] is False
    assert visible["reminder"] is True  # untouched -> its default (shown)


def test_bad_value_falls_back_to_default(tmp_path):
    cfg = tmp_path / "config.ini"
    cfg.write_text("[menu]\nreminder = notabool\nchat = alsobad\n")
    visible = menu_config.load_menu_visibility(cfg)
    assert visible["reminder"] is True  # shown by default
    assert visible["chat"] is False  # hidden by default


def test_save_keeps_other_sections(tmp_path):
    cfg = tmp_path / "config.ini"
    cfg.write_text("[settings]\nwait_time = 3.0\n")
    menu_config.save_menu_visibility({"activity": False}, cfg)
    text = cfg.read_text()
    assert "wait_time = 3.0" in text  # [settings] left intact
    assert menu_config.load_menu_visibility(cfg)["activity"] is False
