"""i18n: translation lookup, language persistence and the language menu."""

import configparser

from PySide6 import QtWidgets

from mycat import i18n


def test_default_language_is_english(monkeypatch):
    monkeypatch.setattr(i18n, "_current", "en")
    assert i18n.current_language() == "en"
    assert i18n.is_chinese() is False


def test_tr_returns_english_in_english_mode(monkeypatch):
    monkeypatch.setattr(i18n, "_current", "en")
    # English mode returns the source string unchanged.
    assert i18n.tr("Close") == "Close"
    assert i18n.tr("No such string") == "No such string"


def test_tr_translates_in_chinese_mode(monkeypatch):
    monkeypatch.setattr(i18n, "_current", "zh")
    assert i18n.tr("Close") == "关闭"
    # Untranslated strings fall through to English.
    assert i18n.tr("No such string") == "No such string"


def test_tr_keeps_format_placeholders(monkeypatch):
    monkeypatch.setattr(i18n, "_current", "zh")
    translated = i18n.tr("Current: {status}")
    assert "{status}" in translated
    assert translated.format(status="工作") == "当前：工作"


def test_set_language_persists_to_config(tmp_path):
    config_file = tmp_path / "config.ini"
    i18n.set_language("zh", config_file)
    config = configparser.ConfigParser()
    config.read(config_file)
    assert config["settings"]["language"] == "zh"


def test_load_language_restores_persisted_language(tmp_path, monkeypatch):
    config_file = tmp_path / "config.ini"
    i18n.set_language("zh", config_file)
    monkeypatch.setattr(i18n, "_current", "en")
    assert i18n.load_language(config_file) == "zh"
    assert i18n.is_chinese() is True


def test_set_language_falls_back_on_unknown_code(tmp_path):
    config_file = tmp_path / "config.ini"
    i18n.set_language("fr", config_file)
    assert i18n.current_language() == i18n.DEFAULT_LANGUAGE


def test_build_language_menu_has_radio_actions(qapp):
    menu = QtWidgets.QMenu()
    i18n.build_language_menu(menu, config_path=None)
    # The "Language" submenu carries the two radio actions.
    submenus = [a.menu() for a in menu.actions() if a.menu() is not None]
    language_menu = submenus[0]
    labels = [action.text() for action in language_menu.actions()]
    assert set(labels) == {"English", "简体中文"}