"""Tests for the OpenAI-compatible backend and model listing (urllib mocked)."""

import json
import urllib.error
import urllib.request

import pytest

from mycat import llm_openai_compat


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self.payload


def opener_returning(payload: bytes):
    def opener(request, timeout=None):
        return FakeResponse(payload)

    return opener


def test_reply_parses_choices(monkeypatch):
    body = json.dumps({"choices": [{"message": {"content": "  Hi  "}}]}).encode()
    monkeypatch.setattr(urllib.request, "urlopen", opener_returning(body))
    backend = llm_openai_compat.OpenAICompatBackend(
        base_url="https://api.x/v1", api_key="k", model="m", timeout=5
    )
    assert backend.reply("hi", "system") == "Hi"


def test_reply_connection_error(monkeypatch):
    def boom(request, timeout=None):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    backend = llm_openai_compat.OpenAICompatBackend(
        base_url="https://api.x/v1", api_key="k", model="m", timeout=5
    )
    with pytest.raises(RuntimeError, match="Connection error"):
        backend.reply("hi", "system")


def test_reply_sends_bearer_header(monkeypatch):
    seen = {}

    def opener(request, timeout=None):
        seen["auth"] = request.headers.get("Authorization")
        return FakeResponse(json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", opener)
    backend = llm_openai_compat.OpenAICompatBackend(
        base_url="https://api.x/v1", api_key="secret", model="m", timeout=5
    )
    backend.reply("hi", "system")
    assert seen["auth"] == "Bearer secret"


def test_fetch_models_parses_data(monkeypatch):
    body = json.dumps({"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}]}).encode()
    monkeypatch.setattr(urllib.request, "urlopen", opener_returning(body))
    assert llm_openai_compat.fetch_models("https://api.x/v1", "k") == ["gpt-4o", "gpt-4o-mini"]


def test_fetch_models_empty_raises(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", opener_returning(json.dumps({"data": []}).encode()))
    with pytest.raises(RuntimeError, match="No models"):
        llm_openai_compat.fetch_models("https://api.x/v1", "k")
