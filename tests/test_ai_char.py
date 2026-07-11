"""AI character generation: validation, API request, and local persistence."""

import base64
import io
import json
import zipfile

import pytest
from PIL import Image

from mycat import ai_char, char_catalog


def png_bytes(size=(40, 60), color=(200, 100, 80, 255)):
    output = io.BytesIO()
    Image.new("RGBA", size, color).save(output, "PNG")
    return output.getvalue()


def test_slugify_is_safe_and_namespaced():
    assert ai_char.slugify("Jennie Gatita!") == "custom-jennie-gatita"
    with pytest.raises(ai_char.AICharError):
        ai_char.slugify("✨")


def test_prepare_references_accepts_one_to_three_and_resizes(tmp_path):
    paths = []
    for index in range(3):
        path = tmp_path / f"photo-{index}.jpg"
        Image.new("RGB", (2000, 1000), (index, 20, 30)).save(path, "JPEG")
        paths.append(path)
    prepared = ai_char.prepare_references(paths)
    assert len(prepared) == 3
    with Image.open(io.BytesIO(prepared[0][1])) as image:
        assert max(image.size) == ai_char.MAX_REFERENCE_EDGE
    with pytest.raises(ai_char.AICharError):
        ai_char.prepare_references([])
    with pytest.raises(ai_char.AICharError):
        ai_char.prepare_references(paths + [paths[0]])


def test_build_prompt_adds_optional_visual_details():
    prompt = ai_char.build_prompt("Add round glasses and red LOVE lettering on the blouse.")
    assert "round glasses" in prompt
    assert "red LOVE lettering" in prompt
    assert "transparent background" in prompt
    assert ai_char.build_prompt("  ") == ai_char.PROMPT
    with pytest.raises(ai_char.AICharError):
        ai_char.build_prompt("x" * (ai_char.MAX_ADDITIONAL_INSTRUCTIONS + 1))


def test_request_image_sends_all_references(monkeypatch):
    generated = png_bytes()
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps({"data": [{"b64_json": base64.b64encode(generated).decode()}]}).encode()

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(ai_char.urllib.request, "urlopen", fake_urlopen)
    result = ai_char.request_image(
        "secret",
        [("a.png", generated), ("b.png", generated)],
        additional_instructions="Add glasses and red lettering.",
    )
    assert result == generated
    body = captured["request"].data
    assert body.count(b'name="image[]"') == 2
    assert b'name="model"' in body and ai_char.MODEL.encode() in body
    assert b'name="background"' in body and b"transparent" in body
    assert b"Add glasses and red lettering." in body
    assert captured["request"].get_header("Authorization") == "Bearer secret"


def test_install_and_delete_generated_character(monkeypatch, tmp_path):
    monkeypatch.setattr(char_catalog, "user_chars_dir", lambda: tmp_path)
    char_id, path = ai_char.install_character("Mina Cat", png_bytes())
    assert char_id == "custom-mina-cat"
    assert path.exists()
    with zipfile.ZipFile(path) as archive:
        assert set(archive.namelist()) == {"static.png", "config.json"}
        assert json.loads(archive.read("config.json"))["name"] == "Mina Cat"
    assert char_catalog.ai_generated_chars() == [char_id]
    assert char_catalog.remove_installed(char_id) is True
    assert not path.exists()
    assert char_catalog.ai_generated_chars() == []
