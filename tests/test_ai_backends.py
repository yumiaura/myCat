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


def test_make_backend_passes_prompts():
    b = ai_backends.make_backend(
        {"backend": "a1111", "a1111_url": "http://x", "selfhosted_prompt": "P", "selfhosted_negative": "N"}
    )
    assert b.prompt == "P"
    assert b.negative == "N"
    o = ai_backends.make_backend({"backend": "openai", "openai_prompt": "hello cat", "openai_negative": "dogs"}, "key")
    assert o.prompt == "hello cat"
    assert o.negative == "dogs"


def test_backends_fall_back_to_default_prompts():
    assert ai_backends.A1111Backend("http://x").prompt == ai_backends.LOCAL_PROMPT
    assert ai_backends.A1111Backend("http://x").negative == ai_backends.LOCAL_NEGATIVE
    assert ai_backends.OpenAIBackend("k").prompt == ai_backends.OPENAI_DEFAULT_PROMPT


def test_list_models_openai_is_static():
    assert ai_backends.list_models("openai") == list(ai_backends.OPENAI_MODELS)


def test_list_models_a1111(monkeypatch):
    monkeypatch.setattr(ai_backends, "http_json", lambda url, *a, **k: [{"title": "A [h]"}, {"title": "B [h]"}])
    assert ai_backends.list_models("a1111", "http://x") == ["A [h]", "B [h]"]


def test_list_models_comfyui(monkeypatch):
    obj = {"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["m1.safetensors", "m2.safetensors"]]}}}}
    monkeypatch.setattr(ai_backends, "http_json", lambda url, *a, **k: obj)
    assert ai_backends.list_models("comfyui", "http://x") == ["m1.safetensors", "m2.safetensors"]


def test_a1111_txt2img_uses_prompt_and_negative(monkeypatch):
    captured = {}
    image = png_bytes()

    def fake(url, payload=None, **kwargs):
        captured["url"], captured["payload"] = url, payload
        return {"images": [base64.b64encode(image).decode()]}

    monkeypatch.setattr(ai_backends, "http_json", fake)
    backend = ai_backends.A1111Backend(
        "http://sd", checkpoint="ck", mode="txt2img", steps=15, prompt="a red cat", negative="no dogs"
    )
    assert backend.generate([]) == image
    assert captured["url"].endswith("/sdapi/v1/txt2img")
    assert captured["payload"]["steps"] == 15
    assert captured["payload"]["prompt"] == "a red cat"
    assert captured["payload"]["negative_prompt"] == "no dogs"
    assert captured["payload"]["override_settings"]["sd_model_checkpoint"] == "ck"


def test_a1111_img2img_requires_a_photo():
    with pytest.raises(ai_char.AICharError):
        ai_backends.A1111Backend("http://sd", mode="img2img").generate([])


def test_a1111_img2img_sends_init_image(monkeypatch):
    captured = {}
    image = png_bytes()

    def fake(url, payload=None, **kwargs):
        captured["url"], captured["payload"] = url, payload
        return {"images": [base64.b64encode(image).decode()]}

    monkeypatch.setattr(ai_backends, "http_json", fake)
    ai_backends.A1111Backend("http://sd", mode="img2img").generate([("r.png", png_bytes())])
    assert captured["url"].endswith("/sdapi/v1/img2img")
    assert captured["payload"]["init_images"]


def test_openai_txt2img_sends_prompt(monkeypatch):
    image = png_bytes()
    captured = {}
    payload = {"data": [{"b64_json": base64.b64encode(image).decode()}]}

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data)
        return JsonResponse(payload)

    monkeypatch.setattr(ai_backends.urllib.request, "urlopen", fake_urlopen)
    out = ai_backends.OpenAIBackend("key", mode="txt2img", prompt="a hat cat").generate([])
    assert out == image
    assert captured["body"]["prompt"] == "a hat cat"


def test_combine_prompt_folds_negative():
    assert ai_backends.combine_prompt("a cat", "") == "a cat"
    out = ai_backends.combine_prompt("a cat", "dogs, text")
    assert "a cat" in out
    assert "must not contain" in out.lower()
    assert "dogs, text" in out


def test_openai_txt2img_folds_negative_into_prompt(monkeypatch):
    image = png_bytes()
    captured = {}
    payload = {"data": [{"b64_json": base64.b64encode(image).decode()}]}

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data)
        return JsonResponse(payload)

    monkeypatch.setattr(ai_backends.urllib.request, "urlopen", fake_urlopen)
    ai_backends.OpenAIBackend("key", mode="txt2img", prompt="a cat", negative="dogs").generate([])
    assert "a cat" in captured["body"]["prompt"]
    assert "dogs" in captured["body"]["prompt"]
    assert "must not contain" in captured["body"]["prompt"].lower()


def test_openai_img2img_delegates_to_request_image(monkeypatch):
    image = png_bytes()
    seen = {}

    def fake_request_image(api_key, references, **kwargs):
        seen.update(kwargs)
        return image

    monkeypatch.setattr(ai_char, "request_image", fake_request_image)
    out = ai_backends.OpenAIBackend("key", model="gpt-image-1", mode="img2img", prompt="P").generate(
        [("r.png", png_bytes())]
    )
    assert out == image
    assert seen["model"] == "gpt-image-1"
    assert seen["prompt"] == "P"


def test_openai_txt2img_needs_key():
    with pytest.raises(ai_char.AICharError):
        ai_backends.OpenAIBackend("", mode="txt2img").generate([])


def test_comfyui_uses_prompt_and_negative(monkeypatch):
    image = png_bytes()
    submitted = {}

    def fake_http(url, payload=None, **kwargs):
        if url.endswith("/prompt"):
            submitted["graph"] = payload["prompt"]
            return {"prompt_id": "pid"}
        if "/history/" in url:
            return {"pid": {"status": {"status_str": "success"},
                            "outputs": {"9": {"images": [{"filename": "f.png", "subfolder": "", "type": "output"}]}}}}
        return {}

    monkeypatch.setattr(ai_backends, "http_json", fake_http)
    monkeypatch.setattr(ai_backends.urllib.request, "urlopen", lambda url, timeout: RawResponse(image))
    out = ai_backends.ComfyUIBackend("http://cu", mode="txt2img", prompt="POS", negative="NEG").generate([])
    assert out == image
    assert submitted["graph"]["pos"]["inputs"]["text"] == "POS"
    assert submitted["graph"]["neg"]["inputs"]["text"] == "NEG"


def test_fresh_config_defaults_background_to_remove(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_backends, "CFG_DIR", tmp_path)
    monkeypatch.setattr(ai_backends, "CFG_FILE", tmp_path / "config.ini")  # no file yet
    loaded = ai_backends.load_generation_settings()
    assert loaded["background_removal"] == "plain"  # "Remove"


def test_api_error_message_a1111_string_error():
    # AUTOMATIC1111: `error` is a short type string, the detail lives in `errors`.
    parsed = {"error": "OutOfMemoryError", "detail": "", "errors": "CUDA out of memory."}
    assert ai_backends.api_error_message(parsed) == "OutOfMemoryError: CUDA out of memory."


def test_api_error_message_a1111_error_without_detail():
    assert ai_backends.api_error_message({"error": "RuntimeError", "errors": ""}) == "RuntimeError"


def test_api_error_message_openai_nested():
    parsed = {"error": {"message": "Invalid API key", "type": "invalid_request_error"}}
    assert ai_backends.api_error_message(parsed) == "Invalid API key"


def test_api_error_message_fastapi_detail():
    assert ai_backends.api_error_message({"detail": "Not found"}) == "Not found"


def test_api_error_message_unknown_shape():
    assert ai_backends.api_error_message({"nope": 1}) == ""
    assert ai_backends.api_error_message("plain text") == ""


def test_service_error_surfaces_a1111_500():
    body = json.dumps({"error": "OutOfMemoryError", "errors": "CUDA out of memory."}).encode()
    exc = ai_backends.urllib.error.HTTPError(
        "http://sd/sdapi/v1/txt2img", 500, "Internal Server Error", {}, io.BytesIO(body)
    )
    err = ai_backends.service_error("Stable Diffusion error", exc)
    assert str(err) == "Stable Diffusion error (500): OutOfMemoryError: CUDA out of memory."


def test_settings_roundtrip_with_prompts(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_backends, "CFG_DIR", tmp_path)
    monkeypatch.setattr(ai_backends, "CFG_FILE", tmp_path / "config.ini")
    settings = dict(ai_backends.GENERATION_DEFAULTS)  # includes the multi-line OpenAI default prompt
    settings.update(backend="comfyui", comfyui_url="http://c")
    settings.update(selfhosted_prompt="my prompt", selfhosted_negative="my neg")
    ai_backends.save_generation_settings(settings)
    loaded = ai_backends.load_generation_settings()
    assert loaded["backend"] == "comfyui"
    assert loaded["comfyui_url"] == "http://c"
    assert loaded["selfhosted_prompt"] == "my prompt"
    assert loaded["selfhosted_negative"] == "my neg"
    assert loaded["openai_prompt"] == ai_backends.OPENAI_DEFAULT_PROMPT  # multi-line value round-trips
