"""OpenAI-compatible chat backend (stdlib urllib).

Works with any provider that speaks the OpenAI Chat Completions API —
OpenAI, Grok (xAI), Groq, DeepSeek, OpenRouter, Together, most Chinese
platforms and custom endpoints — given a base_url, an API key and a model.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class OpenAICompatBackend:
    """Call ``POST {base_url}/chat/completions`` with a Bearer key."""

    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: float) -> None:
        self.chat_url = f"{base_url.rstrip('/')}/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def headers(self) -> dict[str, str]:
        head = {"Content-Type": "application/json"}
        if self.api_key:
            head["Authorization"] = f"Bearer {self.api_key}"
        return head

    def reply(self, user_text: str, system_prompt: str) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "stream": False,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(self.chat_url, data=data, headers=self.headers(), method="POST")

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
            raise RuntimeError(f"HTTP error {exc.code}: {detail or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Connection error: {exc.reason}") from exc
        except (TimeoutError, OSError) as exc:
            raise RuntimeError(f"Connection error: {exc}") from exc

        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON from provider: {exc}") from exc

        try:
            message = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected response shape: {raw[:200]}") from exc

        text = (message or "").strip() if isinstance(message, str) else str(message or "").strip()
        if not text:
            raise RuntimeError("Provider response did not contain any text")
        return text


def fetch_models(base_url: str, api_key: str = "", timeout: float = 10.0) -> list:
    """Model ids from ``GET {base_url}/models``. Raises RuntimeError on failure."""
    url = f"{base_url.rstrip('/')}/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
        raise RuntimeError(f"HTTP error {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot reach provider: {exc.reason}") from exc
    except (TimeoutError, OSError) as exc:
        raise RuntimeError(f"Cannot reach provider: {exc}") from exc

    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Provider returned invalid JSON: {exc}") from exc

    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list):
        raise RuntimeError("Provider response did not contain a model list")
    names = [m.get("id") for m in data if isinstance(m, dict) and m.get("id")]
    if not names:
        raise RuntimeError("No models returned by the provider")
    return sorted(names)


__all__ = ["OpenAICompatBackend", "fetch_models"]
