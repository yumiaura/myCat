"""i18n: folder-scanned catalogs, translation lookup, persistence and the menu."""

import configparser
import json

from mycat import i18n


def test_locales_scanned_from_folder():
    langs = i18n.available_languages()
    assert langs.get("en") == "English"
    assert "zh" in langs and "ru" in langs


def test_default_language_is_english(monkeypatch):
    monkeypatch.setattr(i18n, "active_code", "en")
    assert i18n.current_language() == "en"
    assert i18n.tr("Close") == "Close"
    assert i18n.tr("No such string") == "No such string"


def test_tr_translates_in_active_language(monkeypatch):
    monkeypatch.setattr(i18n, "active_code", "zh")
    assert i18n.tr("Chat") == i18n.CATALOGS["zh"]["Chat"] != "Chat"
    # Untranslated strings fall through to the English source.
    assert i18n.tr("No such string") == "No such string"


def test_set_language_persists_to_config(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "active_code", "en")
    cfg = tmp_path / "config.ini"
    i18n.set_language("zh", cfg)
    config = configparser.ConfigParser()
    config.read(cfg)
    assert config["settings"]["language"] == "zh"


def test_load_language_restores_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "active_code", "en")
    cfg = tmp_path / "config.ini"
    i18n.set_language("ru", cfg)
    monkeypatch.setattr(i18n, "active_code", "en")
    assert i18n.load_language(cfg) == "ru"


def test_set_language_ignores_unknown_code(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "active_code", "en")
    i18n.set_language("fr", tmp_path / "config.ini")
    assert i18n.current_language() == "en"


def test_build_language_menu_lists_all_languages(qapp):
    menu = i18n.build_language_menu(config_path=None)
    labels = {action.text() for action in menu.actions()}
    assert labels == set(i18n.available_languages().values())


def test_scan_locales_parses_meta_and_strings(tmp_path, monkeypatch):
    (tmp_path / "xx.json").write_text(
        json.dumps({"language": {"code": "xx", "name": "Testish"}, "strings": {"Chat": "ZZ"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(i18n, "LOCALE_DIR", tmp_path)
    langs, catalogs = i18n.scan_locales()
    assert langs["xx"] == "Testish"
    assert catalogs["xx"]["Chat"] == "ZZ"
    assert langs["en"] == "English"  # English is always available
