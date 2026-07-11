"""Pluggable image-generation backends for the custom-character generator.

Each backend turns the user's request into PNG bytes; the shared packaging in
:mod:`mycat.ai_char` installs that PNG as an ordinary local char. Every backend
talks to its service over plain HTTP (``urllib``), so nothing new has to be
installed.

Backends:

- **openai** — the hosted image model. ``img2img`` edits the reference photos
  (identity-preserving), ``txt2img`` generates from the prompt alone. Returns a
  transparent PNG.
- **a1111** — a self-hosted AUTOMATIC1111 Stable Diffusion WebUI (``/sdapi/v1``).
  ``txt2img`` / ``img2img``. Opaque output (the WebUI has no background remover).
- **comfyui** — a self-hosted ComfyUI server. A small built-in workflow does
  ``txt2img`` / ``img2img`` with core nodes only, so it works on any ComfyUI.
  Opaque output.

Both modes are offered for every backend, and the self-hosted backends can list
their checkpoints so the settings dialog can show a model picker.
"""

from __future__ import annotations

import base64
import configparser
import io
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from . import ai_char
from .ai_char import AICharError

APP_NAME = "mycat"
CFG_DIR = Path.home() / ".config" / APP_NAME
CFG_FILE = CFG_DIR / "config.ini"
CFG_SECTION = "generation"

BACKENDS = ("openai", "a1111", "comfyui")
MODES = ("txt2img", "img2img")

OPENAI_MODELS = ("gpt-image-1.5", "gpt-image-1")
OPENAI_GENERATIONS_URL = "https://api.openai.com/v1/images/generations"

HTTP_TIMEOUT = 300.0
POLL_TIMEOUT = 300.0
LOCAL_SIZE = (512, 768)          # SD1.5-friendly portrait for the mascot
LOCAL_STEPS = 24
LOCAL_SAMPLER = "DPM++ 2M"
LOCAL_CFG = 6.0
IMG2IMG_DENOISE = 0.62           # keep some of the photo, but become a cat

# A compact, tag-style base prompt that Stable-Diffusion checkpoints follow
# better than OpenAI's prose, plus a strong SFW negative (many local checkpoints
# lean NSFW).
LOCAL_PROMPT = (
    "masterpiece, best quality, anime, chibi, kawaii chibi kitten girl, cat ears, "
    "cat paws, cat tail, whiskers, cute big eyes, full body, standing, centered, "
    "simple plain background, soft shading"
)
LOCAL_NEGATIVE = (
    "nsfw, nude, nipples, revealing clothing, sexual, lowres, bad anatomy, "
    "bad hands, extra limbs, deformed, blurry, watermark, signature, text, "
    "cropped, out of frame"
)


# OpenAI keeps its prose default; these are just the *initial* text — the dialog
# lets the user edit each and persists their own version.
OPENAI_DEFAULT_PROMPT = ai_char.PROMPT
OPENAI_DEFAULT_NEGATIVE = (
    "nudity, sexual content, extra limbs, deformed hands, watermark, signature, unwanted text"
)


def combine_prompt(prompt: str, negative: str) -> str:
    """OpenAI's image API has no negative field, so fold the negative into the
    prompt as an explicit 'must not contain' instruction."""
    prompt = prompt.strip()
    negative = negative.strip()
    if negative:
        return f"{prompt}\n\nThe image must not contain: {negative}."
    return prompt


def http_json(url: str, payload=None, *, timeout: float = HTTP_TIMEOUT, method: str | None = None):
    """GET (no payload) or POST JSON, returning the decoded JSON response."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    request = urllib.request.Request(url, data=data, headers=headers, method=method)  # noqa: S310
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.load(response)


def service_error(prefix: str, exc: Exception) -> AICharError:
    """Turn a low-level HTTP/URL error into a readable, user-facing message."""
    if isinstance(exc, urllib.error.HTTPError):
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
            parsed = json.loads(body)
            body = parsed.get("error", {}).get("message") or parsed.get("detail") or body
        except Exception:  # noqa: BLE001 - best-effort detail extraction
            pass
        return AICharError(f"{prefix} ({exc.code}): {body[:300] or exc.reason}")
    reason = getattr(exc, "reason", None)
    if isinstance(exc, TimeoutError) or isinstance(reason, TimeoutError) or "timed out" in str(reason or exc).lower():
        return AICharError(f"{prefix}: the server didn't respond in time — it may be loading a model or out of memory.")
    if isinstance(exc, urllib.error.URLError):
        return AICharError(f"{prefix}: could not reach the server ({exc.reason}).")
    return AICharError(f"{prefix}: {exc}")


def decode_png(image_bytes: bytes, context: str) -> bytes:
    """Validate that bytes are a real image; return them unchanged."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise AICharError(f"{context} returned an invalid image.") from exc
    return image_bytes


def list_models(kind: str, url: str = "") -> list[str]:
    """Model / checkpoint names the chosen backend can use, for the picker."""
    if kind == "openai":
        return list(OPENAI_MODELS)
    base = url.rstrip("/")
    if not base:
        raise AICharError("Set the server address first.")
    try:
        if kind == "a1111":
            data = http_json(f"{base}/sdapi/v1/sd-models", timeout=30)
            return [m["title"] for m in data]
        if kind == "comfyui":
            data = http_json(f"{base}/object_info/CheckpointLoaderSimple", timeout=30)
            return list(data["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0])
    except (urllib.error.URLError, OSError, KeyError, IndexError, ValueError) as exc:
        raise service_error("Could not list models", exc) from exc
    raise AICharError(f"Unknown backend {kind!r}.")


class OpenAIBackend:
    """The hosted OpenAI image model. img2img = edits (uses the photos),
    txt2img = generations (prompt only). Transparent PNG."""

    kind = "openai"

    def __init__(
        self, api_key: str, *, model: str = OPENAI_MODELS[0], quality: str = "low",
        mode: str = "img2img", prompt: str = "", negative: str = "",
    ):
        self.api_key = (api_key or "").strip()
        self.model = model
        self.quality = quality
        self.mode = mode
        self.prompt = prompt or OPENAI_DEFAULT_PROMPT
        self.negative = negative

    def generate(self, references: list[tuple[str, bytes]]) -> bytes:
        if not self.api_key:
            raise AICharError("Enter an OpenAI API key or set OPENAI_API_KEY.")
        prompt = combine_prompt(self.prompt, self.negative)
        if self.mode == "img2img":
            if not references:
                raise AICharError("Choose at least one reference photo for img2img.")
            return ai_char.request_image(
                self.api_key, references, quality=self.quality, model=self.model, prompt=prompt
            )
        payload = {
            "model": self.model,
            "prompt": prompt,
            "size": "1024x1536",
            "quality": self.quality,
            "background": "transparent",
            "output_format": "png",
            "n": 1,
        }
        request = urllib.request.Request(
            OPENAI_GENERATIONS_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:  # noqa: S310
                data = json.load(response)
            return decode_png(base64.b64decode(data["data"][0]["b64_json"], validate=True), "OpenAI")
        except (urllib.error.URLError, OSError, KeyError, IndexError, ValueError) as exc:
            raise service_error("OpenAI error", exc) from exc


class A1111Backend:
    """A self-hosted AUTOMATIC1111 Stable Diffusion WebUI. Opaque output."""

    kind = "a1111"

    def __init__(
        self, url: str, *, checkpoint: str = "", mode: str = "txt2img", steps: int = LOCAL_STEPS,
        prompt: str = "", negative: str = "",
    ):
        self.url = (url or "").rstrip("/")
        self.checkpoint = checkpoint
        self.mode = mode
        self.steps = int(steps)
        self.prompt = prompt or LOCAL_PROMPT
        self.negative = negative or LOCAL_NEGATIVE

    def generate(self, references: list[tuple[str, bytes]]) -> bytes:
        if not self.url:
            raise AICharError("Set the Stable Diffusion server address.")
        payload = {
            "prompt": self.prompt,
            "negative_prompt": self.negative,
            "steps": self.steps,
            "width": LOCAL_SIZE[0],
            "height": LOCAL_SIZE[1],
            "cfg_scale": LOCAL_CFG,
            "sampler_name": LOCAL_SAMPLER,
            "seed": random.randint(0, 2**31 - 1),
        }
        if self.checkpoint:
            payload["override_settings"] = {"sd_model_checkpoint": self.checkpoint}
            payload["override_settings_restore_afterwards"] = True
        if self.mode == "img2img":
            if not references:
                raise AICharError("Choose at least one reference photo for img2img.")
            payload["init_images"] = [base64.b64encode(references[0][1]).decode("ascii")]
            payload["denoising_strength"] = IMG2IMG_DENOISE
            endpoint = "/sdapi/v1/img2img"
        else:
            endpoint = "/sdapi/v1/txt2img"
        try:
            data = http_json(f"{self.url}{endpoint}", payload)
            return decode_png(base64.b64decode(data["images"][0]), "Stable Diffusion")
        except (urllib.error.URLError, OSError, KeyError, IndexError, ValueError) as exc:
            raise service_error("Stable Diffusion error", exc) from exc


class ComfyUIBackend:
    """A self-hosted ComfyUI server driven by a small built-in workflow (core
    nodes only, so it runs on any ComfyUI). Opaque output."""

    kind = "comfyui"

    def __init__(
        self, url: str, *, checkpoint: str = "sd15.safetensors", mode: str = "txt2img",
        steps: int = LOCAL_STEPS, prompt: str = "", negative: str = "",
    ):
        self.url = (url or "").rstrip("/")
        self.checkpoint = checkpoint
        self.mode = mode
        self.steps = int(steps)
        self.prompt = prompt or LOCAL_PROMPT
        self.negative = negative or LOCAL_NEGATIVE

    def upload_image(self, image_bytes: bytes) -> str:
        """POST a reference photo to ComfyUI's input folder; return its name."""
        boundary = f"mycat-{uuid.uuid4().hex}"
        name = f"mycat-ref-{uuid.uuid4().hex}.png"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode() + image_bytes + f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(
            f"{self.url}/upload/image",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            info = json.load(response)
        return info["name"] if not info.get("subfolder") else f"{info['subfolder']}/{info['name']}"

    def build_graph(self, reference_name: str | None) -> dict:
        seed = random.randint(0, 2**31 - 1)
        graph = {
            "ckpt": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": self.checkpoint}},
            "pos": {"class_type": "CLIPTextEncode", "inputs": {"text": self.prompt, "clip": ["ckpt", 1]}},
            "neg": {"class_type": "CLIPTextEncode", "inputs": {"text": self.negative, "clip": ["ckpt", 1]}},
            "sampler": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed, "steps": self.steps, "cfg": LOCAL_CFG, "sampler_name": "dpmpp_2m",
                    "scheduler": "normal", "denoise": 1.0, "model": ["ckpt", 0],
                    "positive": ["pos", 0], "negative": ["neg", 0], "latent_image": ["latent", 0],
                },
            },
            "decode": {"class_type": "VAEDecode", "inputs": {"samples": ["sampler", 0], "vae": ["ckpt", 2]}},
            "save": {"class_type": "SaveImage", "inputs": {"filename_prefix": "mycat", "images": ["decode", 0]}},
        }
        if reference_name is not None:
            graph["load"] = {"class_type": "LoadImage", "inputs": {"image": reference_name}}
            graph["latent"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["load", 0], "vae": ["ckpt", 2]}}
            graph["sampler"]["inputs"]["denoise"] = IMG2IMG_DENOISE
        else:
            graph["latent"] = {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": LOCAL_SIZE[0], "height": LOCAL_SIZE[1], "batch_size": 1},
            }
        return graph

    def generate(self, references: list[tuple[str, bytes]]) -> bytes:
        if not self.url:
            raise AICharError("Set the ComfyUI server address.")
        reference_name = None
        try:
            if self.mode == "img2img":
                if not references:
                    raise AICharError("Choose at least one reference photo for img2img.")
                reference_name = self.upload_image(references[0][1])
            graph = self.build_graph(reference_name)
            prompt_id = http_json(f"{self.url}/prompt", {"prompt": graph, "client_id": uuid.uuid4().hex})["prompt_id"]
            image = self.await_image(prompt_id)
            query = urllib.parse.urlencode(
                {"filename": image["filename"], "subfolder": image.get("subfolder", ""), "type": image["type"]}
            )
            with urllib.request.urlopen(f"{self.url}/view?{query}", timeout=60) as response:  # noqa: S310
                return decode_png(response.read(), "ComfyUI")
        except AICharError:
            raise
        except (urllib.error.URLError, OSError, KeyError, IndexError, ValueError) as exc:
            raise service_error("ComfyUI error", exc) from exc

    def await_image(self, prompt_id: str) -> dict:
        """Poll /history until the run finishes; return the first output image."""
        waited = 0.0
        while waited < POLL_TIMEOUT:
            history = http_json(f"{self.url}/history/{prompt_id}", timeout=30)
            entry = history.get(prompt_id)
            if entry:
                status = entry.get("status", {})
                for node in entry.get("outputs", {}).values():
                    for image in node.get("images", []):
                        return image
                if status.get("status_str") == "error":
                    raise AICharError("ComfyUI reported an error while generating (check the server).")
            time.sleep(2)
            waited += 2
        raise AICharError("ComfyUI didn't finish in time — the server may be busy or loading a model.")


GENERATION_DEFAULTS = {
    "backend": "openai",
    "mode": "img2img",
    "openai_model": OPENAI_MODELS[0],
    "quality": "low",
    "a1111_url": "",
    "a1111_checkpoint": "",
    "comfyui_url": "",
    "comfyui_checkpoint": "sd15.safetensors",
    "steps": str(LOCAL_STEPS),
    "openai_prompt": OPENAI_DEFAULT_PROMPT,
    "openai_negative": OPENAI_DEFAULT_NEGATIVE,
    "selfhosted_prompt": LOCAL_PROMPT,
    "selfhosted_negative": LOCAL_NEGATIVE,
}


def load_generation_settings() -> dict:
    """Read the [generation] section of config.ini, filled in with defaults."""
    settings = dict(GENERATION_DEFAULTS)
    parser = configparser.ConfigParser()
    if CFG_FILE.exists():
        try:
            parser.read(CFG_FILE)
        except configparser.Error:
            return settings
        if parser.has_section(CFG_SECTION):
            for key in GENERATION_DEFAULTS:
                if parser.has_option(CFG_SECTION, key):
                    settings[key] = parser.get(CFG_SECTION, key)
    return settings


def save_generation_settings(settings: dict) -> None:
    """Persist the generation settings into [generation] (other sections kept)."""
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    parser = configparser.ConfigParser()
    if CFG_FILE.exists():
        try:
            parser.read(CFG_FILE)
        except configparser.Error:
            pass
    if not parser.has_section(CFG_SECTION):
        parser.add_section(CFG_SECTION)
    for key in GENERATION_DEFAULTS:
        if settings.get(key) is not None:
            parser.set(CFG_SECTION, key, str(settings[key]))
    with open(CFG_FILE, "w") as handle:
        parser.write(handle)


def make_backend(settings: dict, api_key: str = "") -> OpenAIBackend | A1111Backend | ComfyUIBackend:
    """Build the configured backend from a settings dict."""
    kind = settings.get("backend", "openai")
    mode = settings.get("mode", "img2img" if kind == "openai" else "txt2img")
    if kind == "openai":
        return OpenAIBackend(
            api_key, model=settings.get("openai_model", OPENAI_MODELS[0]),
            quality=settings.get("quality", "low"), mode=mode,
            prompt=settings.get("openai_prompt", ""), negative=settings.get("openai_negative", ""),
        )
    selfhosted_prompt = settings.get("selfhosted_prompt", "")
    selfhosted_negative = settings.get("selfhosted_negative", "")
    if kind == "a1111":
        return A1111Backend(
            settings.get("a1111_url", ""), checkpoint=settings.get("a1111_checkpoint", ""),
            mode=mode, steps=int(settings.get("steps", LOCAL_STEPS)),
            prompt=selfhosted_prompt, negative=selfhosted_negative,
        )
    if kind == "comfyui":
        return ComfyUIBackend(
            settings.get("comfyui_url", ""), checkpoint=settings.get("comfyui_checkpoint", "sd15.safetensors"),
            mode=mode, steps=int(settings.get("steps", LOCAL_STEPS)),
            prompt=selfhosted_prompt, negative=selfhosted_negative,
        )
    raise AICharError(f"Unknown backend {kind!r}.")


__all__ = [
    "BACKENDS", "MODES", "OPENAI_MODELS", "GENERATION_DEFAULTS",
    "LOCAL_PROMPT", "LOCAL_NEGATIVE", "OPENAI_DEFAULT_PROMPT", "OPENAI_DEFAULT_NEGATIVE",
    "OpenAIBackend", "A1111Backend", "ComfyUIBackend",
    "list_models", "make_backend", "combine_prompt",
    "load_generation_settings", "save_generation_settings",
]
