"""A config.ini in the old locale codec survives the first save after the upgrade.

Before myCat named an encoding, config.ini was written in whatever codec the locale
supplied (cp1251 on a Russian Windows, cp949 on a Korean one). A writer that reads it as
strict UTF-8 fails, carries on with an empty parser and rewrites the file with only its own
section: the window position, the GitHub token and the prompt are gone. Every writer reads
through config_store.read_config_text, which falls back to the locale codec.
"""

from __future__ import annotations

import configparser

import pytest

CODEC = "cp1251"
PROMPT = "милый котик, пастельные тона"
LEGACY = (
    "[window]\nx = 100\ny = 200\n\n"
    "[github]\ntoken = ghp_example\n\n"
    f"[generation]\nopenai_prompt = {PROMPT}\n"
)


@pytest.fixture
def legacy_config(tmp_path, monkeypatch):
    """A cp1251 config.ini that every config module points at."""
    from mycat import ai_backends, config_store, llm_prompt, llm_vendors

    cfg = tmp_path / "config.ini"
    cfg.write_bytes(LEGACY.encode(CODEC))
    monkeypatch.setattr(config_store.locale, "getpreferredencoding", lambda do_setlocale=True: CODEC)
    for module in (ai_backends, llm_prompt):
        monkeypatch.setattr(module, "CFG_DIR", tmp_path)
        monkeypatch.setattr(module, "CFG_FILE", cfg)
    monkeypatch.setattr(llm_vendors, "CFG_FILE", cfg)
    return cfg


def saved_sections(cfg) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read(cfg, encoding="utf-8")
    return parser


def save_llm_enabled():
    from mycat import llm_prompt

    llm_prompt.save_llm_enabled(True)


def save_ollama_settings():
    from mycat import llm_prompt

    llm_prompt.save_ollama_settings("http://127.0.0.1:11434", "llama3")


def save_vendor():
    from mycat import llm_vendors

    llm_vendors.save_vendor(
        llm_vendors.Vendor("acme", llm_vendors.KIND_OPENAI, "https://api.example.com/v1", model="m"),
        make_active=True,
    )


def save_generation_settings():
    from mycat import ai_backends

    settings = dict.fromkeys(ai_backends.GENERATION_DEFAULTS)
    settings["openai_model"] = "gpt-image-1"
    ai_backends.save_generation_settings(settings)


@pytest.mark.parametrize(
    "save",
    [save_llm_enabled, save_ollama_settings, save_vendor, save_generation_settings],
    ids=lambda save: save.__name__,
)
def test_saving_keeps_every_section_of_a_legacy_config(legacy_config, save):
    save()

    parser = saved_sections(legacy_config)
    assert parser.get("window", "x") == "100"
    assert parser.get("github", "token") == "ghp_example"
    assert parser.get("generation", "openai_prompt") == PROMPT
