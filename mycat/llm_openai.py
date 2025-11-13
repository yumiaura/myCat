"""OpenAI backend for PixelCat LLM chat."""

from __future__ import annotations

from typing import List


class OpenAIBackend:
    """Thin wrapper over the OpenAI Chat Completions API."""

    def __init__(self, *, api_key: str, model: str) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ModuleNotFoundError(
                "The 'openai' package is required for --openai support."
            ) from exc

        self.model = model
        self._client = OpenAI(api_key=api_key)

    def reply(self, user_text: str, system_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
        )

        message = response.choices[0].message.content
        if isinstance(message, str):
            return message.strip()

        if isinstance(message, list):
            parts: List[str] = []
            for chunk in message:
                if isinstance(chunk, dict):
                    parts.append(chunk.get("text", "").strip())
            return " ".join(parts).strip()

        return str(message or "").strip()


__all__ = ["OpenAIBackend"]
