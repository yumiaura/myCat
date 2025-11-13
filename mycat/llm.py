"""Entry point for the optional LLM integration."""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from typing import Optional, Protocol

from PySide6 import QtWidgets

from . import llm_prompt, llm_ui

logger = logging.getLogger(__name__)


class LLMBackend(Protocol):
    def reply(self, user_text: str, system_prompt: str) -> str:
        """Return assistant response for the given user text."""


@dataclass
class LLMContext:
    """Bundled backend instance together with its resolved settings."""

    backend_name: str
    backend: LLMBackend
    settings: llm_prompt.LLMSettings


class LLMDependencyError(RuntimeError):
    """Raised when required backend dependencies or credentials are missing."""


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add LLM-specific flags to the CLI parser."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--openai",
        action="store_true",
        help="Enable chat responses via the OpenAI API (uses OPENAI_* values from .env or config.ini).",
    )
    group.add_argument(
        "--ollama",
        action="store_true",
        help="Enable chat responses via a local Ollama server (uses OLLAMA_* values from .env or config.ini).",
    )


def initialize(args) -> Optional[LLMContext]:
    """Configure the selected backend (OpenAI or Ollama)."""
    backend_name: Optional[str] = None
    if getattr(args, "openai", False):
        backend_name = "openai"
    elif getattr(args, "ollama", False):
        backend_name = "ollama"

    if not backend_name:
        logger.debug("LLM backend not requested")
        return None

    llm_prompt.load_env_file()
    settings = llm_prompt.load_llm_settings()
    logger.info("Initializing LLM backend '%s'", backend_name)
    try:
        backend = create_backend(backend_name, settings)
    except (LLMDependencyError, ImportError, RuntimeError) as exc:
        logger.warning("LLM backend '%s' disabled: %s", backend_name, exc)
        return None

    logger.info("LLM backend '%s' ready", backend_name)
    return LLMContext(backend_name=backend_name, backend=backend, settings=settings)


def attach(window: QtWidgets.QWidget, context: LLMContext) -> None:
    """Attach the chat UI to the PixelCat window."""
    if not context:
        return
    logger.debug("Attaching LLM UI to window %s", window)
    llm_ui.attach_chat(window, context)


def create_backend(name: str, settings: llm_prompt.LLMSettings) -> LLMBackend:
    normalized = name.strip().lower()
    if normalized == "openai":
        try:
            from .llm_openai import OpenAIBackend
        except ModuleNotFoundError as exc:
            raise LLMDependencyError(exc) from exc
        if not settings.openai_api_key:
            raise LLMDependencyError("OPENAI_API_KEY is not configured in .env or config.ini")
        logger.debug("Creating OpenAI backend with model %s", settings.openai_model)
        return OpenAIBackend(api_key=settings.openai_api_key, model=settings.openai_model)

    if normalized == "ollama":
        from .llm_ollama import OllamaBackend

        logger.debug(
            "Creating Ollama backend url=%s model=%s timeout=%s",
            settings.ollama_url,
            settings.ollama_model,
            settings.ollama_timeout,
        )
        return OllamaBackend(
            url=settings.ollama_url,
            model=settings.ollama_model,
            timeout=settings.ollama_timeout,
        )

    raise LLMDependencyError(f"Unsupported LLM backend: {name}")


__all__ = [
    "LLMContext",
    "LLMBackend",
    "LLMDependencyError",
    "add_arguments",
    "initialize",
    "attach",
]
