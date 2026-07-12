"""Generate a persistent myCat character from 1-3 reference photos.

Only the generated PNG is stored in the final char pack.  Reference photos are
resized in memory before upload and are never copied into myCat's data folder.
"""

from __future__ import annotations

from collections import deque
import base64
import hashlib
import io
import json
import os
import re
import unicodedata
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from . import char_catalog

API_URL = "https://api.openai.com/v1/images/edits"
MODEL = "gpt-image-1.5"
MAX_REFERENCES = 3
MAX_REFERENCE_EDGE = 1536
MAX_ADDITIONAL_INSTRUCTIONS = 2000
TIMEOUT_SECONDS = 180.0
SECRET_NAME = "openai_image_api_key"

PROMPT = """Create one original desktop companion character inspired by the same person in the reference photos.
Transform their recognizable hair, colors, outfit details, and overall vibe into a cute chibi kitten girl: clearly a
small feline character with cat ears, paws, tail, whiskers, and a compact full body. Preserve identity cues without
making a photorealistic portrait. Polished kawaii digital illustration, expressive friendly pose, clean silhouette,
soft shading, centered, full character fully visible, no crop, no props, no scenery, no frame, no logo. Do not add
writing unless the user's additional visual instructions explicitly request it.
Isolate the character on a truly transparent background with clean alpha edges. This will be a small always-on-top
desktop mascot, so prioritize readability at thumbnail size."""


class AICharError(RuntimeError):
    """A user-facing generation or packaging error."""


def slugify(name: str) -> str:
    """Return a conservative char id that is safe as a file name."""
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    if not slug:
        raise AICharError("Enter a name containing at least one letter or number.")
    return f"custom-{slug[:48]}"


def _reference_png(path: Path) -> bytes:
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (OSError, UnidentifiedImageError) as exc:
        raise AICharError(f"Cannot read image: {path.name}") from exc
    image.thumbnail((MAX_REFERENCE_EDGE, MAX_REFERENCE_EDGE), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, "PNG", optimize=True)
    return output.getvalue()


def prepare_references(paths: list[Path]) -> list[tuple[str, bytes]]:
    if not 1 <= len(paths) <= MAX_REFERENCES:
        raise AICharError("Choose between 1 and 3 reference images.")
    return [(f"reference-{index}.png", _reference_png(Path(path))) for index, path in enumerate(paths, 1)]


def build_prompt(additional_instructions: str = "") -> str:
    """Append optional visual direction without weakening pack requirements."""
    details = additional_instructions.strip()
    if len(details) > MAX_ADDITIONAL_INSTRUCTIONS:
        raise AICharError(f"Additional details must be {MAX_ADDITIONAL_INSTRUCTIONS} characters or fewer.")
    if not details:
        return PROMPT
    return (
        f"{PROMPT}\n\n"
        "Additional visual instructions from the user (apply these carefully while preserving the transparent "
        "background, full-body composition, and chibi kitten design):\n"
        f"{details}"
    )


def _multipart(fields: dict[str, str], images: list[tuple[str, bytes]]) -> tuple[bytes, str]:
    boundary = f"mycat-{uuid.uuid4().hex}"
    body = io.BytesIO()

    def write(value: bytes) -> None:
        body.write(value)
        body.write(b"\r\n")

    for name, value in fields.items():
        write(f"--{boundary}".encode())
        write(f'Content-Disposition: form-data; name="{name}"'.encode())
        write(b"")
        write(value.encode("utf-8"))
    for filename, data in images:
        write(f"--{boundary}".encode())
        write(f'Content-Disposition: form-data; name="image[]"; filename="{filename}"'.encode())
        write(b"Content-Type: image/png")
        write(b"")
        write(data)
    body.write(f"--{boundary}--\r\n".encode())
    return body.getvalue(), f"multipart/form-data; boundary={boundary}"


def request_image(
    api_key: str,
    references: list[tuple[str, bytes]],
    *,
    quality: str = "low",
    model: str = MODEL,
    prompt: str | None = None,
    additional_instructions: str = "",
) -> bytes:
    if not api_key.strip():
        raise AICharError("Enter an OpenAI API key or set OPENAI_API_KEY.")
    if quality not in {"low", "medium"}:
        raise AICharError("Unsupported image quality.")
    body, content_type = _multipart(
        {
            "model": model,
            "prompt": prompt if prompt is not None else build_prompt(additional_instructions),
            "size": "1024x1536",
            "quality": quality,
            "background": "transparent",
            "output_format": "png",
            "input_fidelity": "high",
        },
        references,
    )
    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={"Authorization": f"Bearer {api_key.strip()}", "Content-Type": content_type},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc.reason)
        try:
            parsed = json.loads(detail)
            detail = parsed.get("error", {}).get("message") or detail
        except (json.JSONDecodeError, AttributeError):
            pass
        raise AICharError(f"OpenAI error ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise AICharError(f"Could not reach OpenAI: {exc.reason}") from exc
    except (TimeoutError, OSError) as exc:
        raise AICharError(f"Image generation failed: {exc}") from exc

    try:
        payload = json.loads(raw)
        encoded = payload["data"][0]["b64_json"]
        result = base64.b64decode(encoded, validate=True)
        with Image.open(io.BytesIO(result)) as image:
            image.verify()
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError, UnidentifiedImageError) as exc:
        raise AICharError("OpenAI returned an invalid image response.") from exc
    return result


def _normalized_character_png(image_bytes: bytes) -> bytes:
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = source.convert("RGBA")
    alpha_box = image.getchannel("A").getbbox()
    if alpha_box:
        image = image.crop(alpha_box)
    image.thumbnail((600, 900), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, "PNG", optimize=True)
    return output.getvalue()


def remove_plain_background(image_bytes: bytes, *, tolerance: int = 48) -> bytes:
    """Make a corner-connected, near-uniform background transparent.

    This conservative post-processing option is for locally generated mascots
    on a simple background. Only pixels connected to an image corner and close
    to that corner's colour are removed; interior detail is left untouched.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as source:
            image = source.convert("RGBA")
    except (OSError, UnidentifiedImageError) as exc:
        raise AICharError("Cannot remove the background from an invalid image.") from exc

    width, height = image.size
    if not width or not height:
        return image_bytes
    pixels = image.load()
    visited: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int, tuple[int, int, int]]] = deque()
    for x, y in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        if (x, y) not in visited:
            visited.add((x, y))
            queue.append((x, y, pixels[x, y][:3]))

    limit = tolerance * tolerance * 3
    while queue:
        x, y, background = queue.popleft()
        red, green, blue, alpha = pixels[x, y]
        distance = sum((value - reference) ** 2 for value, reference in zip((red, green, blue), background))
        if alpha == 0 or distance > limit:
            continue
        pixels[x, y] = (red, green, blue, 0)
        for next_x, next_y in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= next_x < width and 0 <= next_y < height and (next_x, next_y) not in visited:
                visited.add((next_x, next_y))
                queue.append((next_x, next_y, background))

    output = io.BytesIO()
    image.save(output, "PNG", optimize=True)
    return output.getvalue()


def install_character(display_name: str, image_bytes: bytes) -> tuple[str, Path]:
    char_id = slugify(display_name)
    destination = char_catalog.ensure_user_chars_dir() / f"{char_id}.zip"
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    config = {
        "name": display_name.strip(),
        "max_width": 240,
        "max_height": 400,
        "blink": {"enabled": False},
    }
    png = _normalized_character_png(image_bytes)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("static.png", png)
            archive.writestr("config.json", json.dumps(config, ensure_ascii=False, indent=2))
        os.replace(temporary, destination)
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
        raise AICharError(f"Could not save the character: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    char_catalog.record_installed(
        char_id,
        version="1",
        source="openai:image",
        sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
        size_bytes=destination.stat().st_size,
    )
    return char_id, destination


def generate_character(
    display_name: str,
    reference_paths: list[Path],
    api_key: str | None = None,
    *,
    quality: str = "low",
    additional_instructions: str = "",
) -> tuple[str, Path]:
    references = prepare_references(reference_paths)
    generated = request_image(
        api_key or os.getenv("OPENAI_API_KEY", ""),
        references,
        quality=quality,
        additional_instructions=additional_instructions,
    )
    return install_character(display_name, generated)


__all__ = [
    "AICharError",
    "MAX_REFERENCES",
    "MAX_ADDITIONAL_INSTRUCTIONS",
    "MODEL",
    "SECRET_NAME",
    "generate_character",
    "build_prompt",
    "install_character",
    "prepare_references",
    "remove_plain_background",
    "request_image",
    "slugify",
]
