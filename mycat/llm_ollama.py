"""Ollama backend for PixelCat LLM chat."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Iterator, List, Optional


class OllamaBackend:
    """Call the local Ollama HTTP API."""

    def __init__(self, *, url: str, model: str, timeout: float) -> None:
        self.chat_url = f"{url.rstrip('/')}/api/chat"
        self.model = model
        self.timeout = timeout

    def _build_payload(
        self,
        user_text: str,
        system_prompt: str,
        images: Optional[List[str]],
        stream: bool,
    ) -> Dict[str, Any]:
        user_message: Dict[str, Any] = {"role": "user", "content": user_text}
        if images:
            # Ollama expects raw base64-encoded image bytes (no data URI prefix).
            user_message["images"] = images
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                user_message,
            ],
            "stream": stream,
            # Gemma 4 has "thinking" on by default; turn it off for fast, direct
            # cat replies (no hidden reasoning tokens before the answer).
            "think": False,
        }

    def reply(
        self,
        user_text: str,
        system_prompt: str,
        images: Optional[List[str]] = None,
    ) -> str:
        payload = self._build_payload(user_text, system_prompt, images, stream=False)
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

    def stream_reply(
        self,
        user_text: str,
        system_prompt: str,
        images: Optional[List[str]] = None,
        stop_event=None,
    ) -> Iterator[str]:
        """Yield reply text chunks as they arrive. Stops early if stop_event is set."""
        payload = self._build_payload(user_text, system_prompt, images, stream=True)
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.chat_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            response = urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
            raise RuntimeError(
                f"Ollama HTTP error {exc.code}: {detail or exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Ollama connection error: {exc.reason}") from exc

        try:
            for raw_line in response:
                if stop_event is not None and stop_event.is_set():
                    break
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                chunk = obj.get("message", {}).get("content", "")
                if chunk:
                    yield chunk
                if obj.get("done"):
                    break
        finally:
            response.close()


__all__ = ["OllamaBackend"]
