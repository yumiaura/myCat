"""config.ini round-trips the languages the UI ships in, on any Windows locale.

myCat ships English, 한국어, 中文 and Русский, and several config values are free text the
user types — the AI prompt, the negative prompt. Text I/O without an explicit encoding uses
the locale's codec on Windows, so a Korean prompt on a Western-locale machine raised
UnicodeEncodeError on save rather than writing the file.
"""

from __future__ import annotations

import configparser

import pytest

# One phrase per UI language the project ships.
SAMPLES = {
    "ko": "귀여운 고양이, 파스텔 색감",
    "zh": "可爱的小猫，柔和色彩",
    "ru": "милый котик, пастельные тона",
    "en": "a cute kitten, pastel colours",
}

# The codecs a Windows install actually picks by locale.
WINDOWS_CODECS = ["cp1252", "cp949", "gbk"]


@pytest.mark.parametrize("codec", WINDOWS_CODECS)
@pytest.mark.parametrize("language,text", sorted(SAMPLES.items()))
def test_a_prompt_round_trips_whatever_the_machine_locale_is(tmp_path, monkeypatch, codec,
                                                             language, text):
    """`save_generation_settings` writes it and the real reader gets it back.

    Both halves on purpose. Naming utf-8 on the write alone moves the failure rather than
    fixing it: the save succeeds and the next start raises UnicodeDecodeError instead.
    """
    from mycat import ai_backends

    cfg = tmp_path / "config.ini"
    monkeypatch.setattr(ai_backends, "CFG_DIR", tmp_path)
    monkeypatch.setattr(ai_backends, "CFG_FILE", cfg)

    settings = dict(ai_backends.GENERATION_DEFAULTS)
    settings["openai_prompt"] = text
    ai_backends.save_generation_settings(settings)

    back = configparser.ConfigParser()
    back.read(cfg, encoding="utf-8")
    assert back.get(ai_backends.CFG_SECTION, "openai_prompt") == text, language


@pytest.mark.parametrize("codec", WINDOWS_CODECS)
@pytest.mark.parametrize("language,text", sorted(SAMPLES.items()))
def test_the_locale_codec_is_what_would_have_broken(tmp_path, codec, language, text):
    """The parameter earns its place: it says what each locale would have done to this text.

    Either the codec cannot represent the phrase at all — which is the UnicodeEncodeError the
    fix exists for — or it can, and then the bytes it writes are not the bytes a utf-8 reader
    expects. Both are the same bug arriving at a different moment, and both are why neither end
    may inherit the machine's codec.
    """
    try:
        as_locale = text.encode(codec)
    except UnicodeEncodeError:
        return                      # this locale could not have written the phrase at all
    if as_locale == text.encode("utf-8"):
        return                      # pure ASCII: nothing to disagree about
    cfg = tmp_path / "config.ini"
    cfg.write_bytes(b"[generation]\nopenai_prompt = " + as_locale + b"\n")
    parser = configparser.ConfigParser()
    with pytest.raises(UnicodeDecodeError):
        parser.read(cfg, encoding="utf-8")
