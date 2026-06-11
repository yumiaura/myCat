"""Ollama backend for PixelCat LLM chat."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict


class OllamaBackend:
    """Call the local Ollama HTTP API."""

    def __init__(self, *, url: str, model: str, timeout: float) -> None:
        self.chat_url = f"{url.rstrip('/')}/api/chat"
        self.model = model
        self.timeout = timeout

    def reply(self, user_text: str, system_prompt: str) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "stream": False,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.chat_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
            raise RuntimeError(
                f"Ollama HTTP error {exc.code}: {detail or exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Ollama connection error: {exc.reason}") from exc

        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Ollama returned invalid JSON: {exc}") from exc

        message = body.get("message", {}).get("content", "")
        text = message.strip() if isinstance(message, str) else str(message or "").strip()
        if not text:
            raise RuntimeError("Ollama response did not contain any text")
        return text


def fetch_models(base_url: str, timeout: float = 10.0) -> list:
    """Return the model names installed on an Ollama server (GET /api/tags).

    Raises RuntimeError with a human-readable reason on any failure so the
    settings dialog can show what went wrong.
    """
    tags_url = f"{base_url.rstrip('/')}/api/tags"
    request = urllib.request.Request(tags_url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
        raise RuntimeError(f"Ollama HTTP error {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot reach Ollama: {exc.reason}") from exc
    except (TimeoutError, OSError) as exc:
        raise RuntimeError(f"Cannot reach Ollama: {exc}") from exc

    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ollama returned invalid JSON: {exc}") from exc

    models = body.get("models")
    if not isinstance(models, list):
        raise RuntimeError("Ollama response did not contain a model list")
    names = [m.get("name") for m in models if isinstance(m, dict) and m.get("name")]
    if not names:
        raise RuntimeError("No models are installed on this Ollama server")
    return names


__all__ = ["OllamaBackend", "fetch_models"]
