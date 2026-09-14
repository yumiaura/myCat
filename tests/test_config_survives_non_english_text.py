"""config.ini round-trips the languages the UI ships in, on any Windows locale.

myCat ships English, 한국어, 中文 and Русский, and several config values are free text the
user types — the AI prompt, the negative prompt. Text I/O without an explicit encoding uses
the locale's codec on Windows, so a Korean prompt on a Western-locale machine raised
UnicodeEncodeError on save rather than writing the file.
"""

from __future__ import annotations

import ast
import configparser
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "mycat"

# One phrase per UI language the project ships.
SAMPLES = {
    "ko": "귀여운 고양이, 파스텔 색감",
    "zh": "可爱的小猫，柔和色彩",
    "ru": "милый котик, пастельные тона",
    "en": "a cute kitten, pastel colours",
}

# The codecs a Windows install actually picks by locale.
WINDOWS_CODECS = ["cp1252", "cp949", "gbk"]


def text_io_without_encoding() -> list[str]:
    """Builtin text `open`/`read_text`/`write_text` calls that take the locale codec."""
    found = []
    for path in sorted(SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            keywords = {kw.arg for kw in node.keywords}
            if isinstance(node.func, ast.Name) and node.func.id == "open":
                mode = node.args[1].value if len(node.args) > 1 and isinstance(node.args[1], ast.Constant) else "r"
                if "b" not in str(mode) and "encoding" not in keywords:
                    found.append(f"{path.name}:{node.lineno}")
            # Attribute calls only — PIL's Image.open and zipfile's open are not this.
            elif isinstance(node.func, ast.Attribute) and node.func.attr in ("read_text", "write_text"):
                if "encoding" not in keywords:
                    found.append(f"{path.name}:{node.lineno}")
    return found


def test_no_text_io_is_left_to_the_locale():
    assert text_io_without_encoding() == []


@pytest.mark.parametrize("codec", WINDOWS_CODECS)
@pytest.mark.parametrize("language,text", sorted(SAMPLES.items()))
def test_a_prompt_round_trips_whatever_the_machine_locale_is(tmp_path, codec, language, text):
    """What `save_generation_settings` writes must come back as what it wrote."""
    from mycat import ai_backends

    cfg = tmp_path / "config.ini"
    parser = configparser.ConfigParser()
    parser.add_section(ai_backends.CFG_SECTION)
    parser.set(ai_backends.CFG_SECTION, "openai_prompt", text)
    with open(cfg, "w", encoding="utf-8") as handle:
        parser.write(handle)

    # A reader on a machine whose locale codec is `codec` still gets the text back,
    # because both ends name the encoding instead of inheriting one.
    back = configparser.ConfigParser()
    back.read(cfg, encoding="utf-8")
    assert back.get(ai_backends.CFG_SECTION, "openai_prompt") == text, language
