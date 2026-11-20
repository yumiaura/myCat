"""Tests for the Ollama HTTP backend and the model-list helper (urllib mocked)."""

import json
import urllib.error
import urllib.request

import pytest

from mycat import llm_ollama


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


def test_fetch_models_parses_names(monkeypatch):
    body = json.dumps({"models": [{"name": "qwen3:8b"}, {"name": "llama3.1"}]}).encode()
    monkeypatch.setattr(urllib.request, "urlopen", opener_returning(body))
    assert llm_ollama.fetch_models("http://host:11434") == ["qwen3:8b", "llama3.1"]


def test_fetch_models_strips_trailing_slash(monkeypatch):
    seen = {}

    def opener(request, timeout=None):
        seen["url"] = request.full_url
        return FakeResponse(json.dumps({"models": [{"name": "m"}]}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", opener)
    llm_ollama.fetch_models("http://host:11434/")
    assert seen["url"] == "http://host:11434/api/tags"


def test_fetch_models_empty_raises(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", opener_returning(json.dumps({"models": []}).encode()))
    with pytest.raises(RuntimeError, match="No models"):
        llm_ollama.fetch_models("http://host:11434")


def test_fetch_models_connection_error(monkeypatch):
    def boom(request, timeout=None):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(RuntimeError, match="Cannot reach Ollama"):
        llm_ollama.fetch_models("http://host:11434")


def test_fetch_models_bad_json(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", opener_returning(b"not json"))
    with pytest.raises(RuntimeError, match="invalid JSON"):
        llm_ollama.fetch_models("http://host:11434")


def test_reply_parses_and_strips(monkeypatch):
    body = json.dumps({"message": {"content": "  Hello  "}}).encode()
    monkeypatch.setattr(urllib.request, "urlopen", opener_returning(body))
    backend = llm_ollama.OllamaBackend(url="http://host:11434", model="m", timeout=5)
    assert backend.reply("hi", "system") == "Hello"


def test_reply_empty_raises(monkeypatch):
    body = json.dumps({"message": {"content": "   "}}).encode()
    monkeypatch.setattr(urllib.request, "urlopen", opener_returning(body))
    backend = llm_ollama.OllamaBackend(url="http://host:11434", model="m", timeout=5)
    with pytest.raises(RuntimeError, match="did not contain any text"):
        backend.reply("hi", "system")


def recording_opener(seen: dict, payload: bytes):
    def opener(request, timeout=None):
        seen["headers"] = {key.lower(): value for key, value in request.header_items()}
        return FakeResponse(payload)

    return opener


def test_reply_sends_bearer_key_when_set(monkeypatch):
    seen = {}
    body = json.dumps({"message": {"content": "Hi"}}).encode()
    monkeypatch.setattr(urllib.request, "urlopen", recording_opener(seen, body))
    backend = llm_ollama.OllamaBackend(url="http://gw:11435", model="m", timeout=5, api_key="secret")
    backend.reply("hi", "system")
    assert seen["headers"]["authorization"] == "Bearer secret"


def test_reply_sends_no_authorization_without_key(monkeypatch):
    seen = {}
    body = json.dumps({"message": {"content": "Hi"}}).encode()
    monkeypatch.setattr(urllib.request, "urlopen", recording_opener(seen, body))
    llm_ollama.OllamaBackend(url="http://host:11434", model="m", timeout=5).reply("hi", "system")
    assert "authorization" not in seen["headers"]


def test_fetch_models_sends_bearer_key_when_set(monkeypatch):
    seen = {}
    body = json.dumps({"models": [{"name": "qwen3:8b"}]}).encode()
    monkeypatch.setattr(urllib.request, "urlopen", recording_opener(seen, body))
    assert llm_ollama.fetch_models("http://gw:11435", 5, "secret") == ["qwen3:8b"]
    assert seen["headers"]["authorization"] == "Bearer secret"
