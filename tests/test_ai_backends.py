"""Pluggable generation backends: model listing, request shaping, settings."""

import base64
import io
import json

import pytest
from PIL import Image

from mycat import ai_backends, ai_char


def png_bytes(color=(200, 100, 80, 255)):
    buf = io.BytesIO()
    Image.new("RGBA", (20, 30), color).save(buf, "PNG")
    return buf.getvalue()


class JsonResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class RawResponse:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.data


def test_make_backend_kinds():
    assert isinstance(ai_backends.make_backend({"backend": "openai"}, "k"), ai_backends.OpenAIBackend)
    assert isinstance(ai_backends.make_backend({"backend": "a1111", "a1111_url": "http://x"}), ai_backends.A1111Backend)
    assert isinstance(
        ai_backends.make_backend({"backend": "comfyui", "comfyui_url": "http://x"}), ai_backends.ComfyUIBackend
    )
    with pytest.raises(ai_char.AICharError):
        ai_backends.make_backend({"backend": "nope"})


def test_local_prompt_appends_details():
    assert "chibi" in ai_backends.local_prompt("")
    assert "round glasses" in ai_backends.local_prompt("round glasses")


def test_list_models_openai_is_static():
    assert ai_backends.list_models("openai") == list(ai_backends.OPENAI_MODELS)


def test_list_models_a1111(monkeypatch):
    monkeypatch.setattr(ai_backends, "http_json", lambda url, *a, **k: [{"title": "A [h]"}, {"title": "B [h]"}])
    assert ai_backends.list_models("a1111", "http://x") == ["A [h]", "B [h]"]


def test_list_models_comfyui(monkeypatch):
    obj = {"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["m1.safetensors", "m2.safetensors"]]}}}}
    monkeypatch.setattr(ai_backends, "http_json", lambda url, *a, **k: obj)
    assert ai_backends.list_models("comfyui", "http://x") == ["m1.safetensors", "m2.safetensors"]


def test_a1111_txt2img_shapes_request(monkeypatch):
    captured = {}
    image = png_bytes()

    def fake(url, payload=None, **kwargs):
        captured["url"], captured["payload"] = url, payload
        return {"images": [base64.b64encode(image).decode()]}

    monkeypatch.setattr(ai_backends, "http_json", fake)
    out = ai_backends.A1111Backend("http://sd", checkpoint="ck", mode="txt2img", steps=15).generate([], "red hoodie")
    assert out == image
    assert captured["url"].endswith("/sdapi/v1/txt2img")
    assert captured["payload"]["steps"] == 15
    assert captured["payload"]["override_settings"]["sd_model_checkpoint"] == "ck"
    assert "red hoodie" in captured["payload"]["prompt"]


def test_a1111_img2img_requires_a_photo():
    with pytest.raises(ai_char.AICharError):
        ai_backends.A1111Backend("http://sd", mode="img2img").generate([], "x")


def test_a1111_img2img_sends_init_image(monkeypatch):
    captured = {}
    image = png_bytes()

    def fake(url, payload=None, **kwargs):
        captured["url"], captured["payload"] = url, payload
        return {"images": [base64.b64encode(image).decode()]}

    monkeypatch.setattr(ai_backends, "http_json", fake)
    ai_backends.A1111Backend("http://sd", mode="img2img").generate([("r.png", png_bytes())], "x")
    assert captured["url"].endswith("/sdapi/v1/img2img")
    assert captured["payload"]["init_images"]


def test_openai_txt2img_calls_generations(monkeypatch):
    image = png_bytes()
    payload = {"data": [{"b64_json": base64.b64encode(image).decode()}]}
    monkeypatch.setattr(ai_backends.urllib.request, "urlopen", lambda req, timeout: JsonResponse(payload))
    assert ai_backends.OpenAIBackend("key", mode="txt2img").generate([], "hat") == image


def test_openai_img2img_delegates_to_request_image(monkeypatch):
    image = png_bytes()
    seen = {}

    def fake_request_image(api_key, references, **kwargs):
        seen.update(kwargs)
        return image

    monkeypatch.setattr(ai_char, "request_image", fake_request_image)
    out = ai_backends.OpenAIBackend("key", model="gpt-image-1", mode="img2img").generate([("r.png", png_bytes())], "x")
    assert out == image
    assert seen["model"] == "gpt-image-1"


def test_openai_txt2img_needs_key():
    with pytest.raises(ai_char.AICharError):
        ai_backends.OpenAIBackend("", mode="txt2img").generate([], "x")


def test_comfyui_txt2img_submits_and_fetches(monkeypatch):
    image = png_bytes()

    def fake_http(url, payload=None, **kwargs):
        if url.endswith("/prompt"):
            return {"prompt_id": "pid"}
        if "/history/" in url:
            return {"pid": {"status": {"status_str": "success"},
                            "outputs": {"9": {"images": [{"filename": "f.png", "subfolder": "", "type": "output"}]}}}}
        return {}

    monkeypatch.setattr(ai_backends, "http_json", fake_http)
    monkeypatch.setattr(ai_backends.urllib.request, "urlopen", lambda url, timeout: RawResponse(image))
    assert ai_backends.ComfyUIBackend("http://cu", mode="txt2img").generate([], "x") == image


def test_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_backends, "CFG_DIR", tmp_path)
    monkeypatch.setattr(ai_backends, "CFG_FILE", tmp_path / "config.ini")
    settings = dict(ai_backends.GENERATION_DEFAULTS)
    settings.update(backend="comfyui", comfyui_url="http://c", comfyui_checkpoint="sd15.safetensors")
    ai_backends.save_generation_settings(settings)
    loaded = ai_backends.load_generation_settings()
    assert loaded["backend"] == "comfyui"
    assert loaded["comfyui_url"] == "http://c"
