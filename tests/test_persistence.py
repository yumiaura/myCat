"""Tests for first-run autostart-prompt bookkeeping (livability phase A)."""

from mycat import main


def use_temp_config(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "CFG_DIR", tmp_path)
    monkeypatch.setattr(main, "CFG_FILE", tmp_path / "config.ini")


def test_prompted_flag_roundtrips(monkeypatch, tmp_path):
    use_temp_config(monkeypatch, tmp_path)
    assert main.autostart_was_prompted() is False
    main.mark_autostart_prompted()
    assert main.autostart_was_prompted() is True


def test_mark_prompted_preserves_other_settings(monkeypatch, tmp_path):
    use_temp_config(monkeypatch, tmp_path)
    main.save_image_to_ini("girl1")
    main.mark_autostart_prompted()
    assert main.load_image_from_ini() == "girl1"
    assert main.autostart_was_prompted() is True


def test_should_offer_only_on_fresh_supported_disabled(monkeypatch, tmp_path):
    use_temp_config(monkeypatch, tmp_path)
    monkeypatch.setattr(main.autostart, "is_supported", lambda: True)
    monkeypatch.setattr(main.autostart, "is_enabled", lambda: False)
    assert main.should_offer_autostart() is True

    # Already prompted -> never again.
    main.mark_autostart_prompted()
    assert main.should_offer_autostart() is False


def test_should_not_offer_when_already_enabled(monkeypatch, tmp_path):
    use_temp_config(monkeypatch, tmp_path)
    monkeypatch.setattr(main.autostart, "is_supported", lambda: True)
    monkeypatch.setattr(main.autostart, "is_enabled", lambda: True)
    assert main.should_offer_autostart() is False


def test_should_not_offer_when_unsupported(monkeypatch, tmp_path):
    use_temp_config(monkeypatch, tmp_path)
    monkeypatch.setattr(main.autostart, "is_supported", lambda: False)
    monkeypatch.setattr(main.autostart, "is_enabled", lambda: False)
    assert main.should_offer_autostart() is False
