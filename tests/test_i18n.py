"""i18n: folder-scanned catalogs, translation lookup, persistence and the menu."""

import ast
import configparser
import json
from pathlib import Path

from mycat import i18n, updater


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


UPDATE_FUNCTIONS = {"open_update", "update_box", "on_update_checked", "download_update", "on_update_failed"}


def update_flow_tr_literals():
    """Every string literal passed to i18n.tr() inside the update functions of main.py."""
    source = (Path(i18n.__file__).resolve().parent / "main.py").read_text(encoding="utf-8")
    literals = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name in UPDATE_FUNCTIONS:
            for call in ast.walk(node):
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "tr"
                    and call.args
                    and isinstance(call.args[0], ast.Constant)
                    and isinstance(call.args[0].value, str)
                ):
                    literals.add(call.args[0].value)
    return literals


def test_update_flow_strings_are_in_every_catalog():
    literals = update_flow_tr_literals()
    # The dialog, the progress dialog and the failure box all go through tr().
    assert {"Releases", "Update", "Close", "Cancel", "Update failed"} <= literals
    # The prose hints are translated at display time; the command hints are not.
    literals |= {updater.update_hint("deb"), updater.update_hint("appimage")}
    for code in ("en", "ru", "zh", "ko"):
        missing = sorted(text for text in literals if text not in i18n.CATALOGS[code])
        assert not missing, f"{code}.json is missing {missing}"


def test_update_flow_strings_have_no_em_dash_or_middle_dot():
    literals = update_flow_tr_literals() | {updater.update_hint("deb"), updater.update_hint("appimage")}
    for code in ("en", "ru", "zh", "ko"):
        for text in literals:
            translated = i18n.CATALOGS[code][text]
            assert "\u2014" not in translated and "\u00b7" not in translated, (code, text)
