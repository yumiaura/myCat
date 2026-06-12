"""Entry point for the optional LLM integration."""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass
from typing import Protocol

from PySide6 import QtWidgets

from . import llm_prompt, llm_ui, llm_vendors

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
    enabled: bool = True
    vendor: llm_vendors.Vendor | None = None


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


def vendor_is_configured() -> bool:
    """Whether a chat vendor has been chosen (config or LLM_BACKEND env)."""
    parser = llm_vendors.read_config()
    if parser.has_option("llm", "vendor"):
        return True
    env_backend = (os.getenv("LLM_BACKEND") or "").strip().lower()
    return env_backend in set(llm_vendors.builtin_vendors())


def initialize(args) -> LLMContext | None:
    """Configure the active chat vendor (Ollama by default, or any cloud vendor)."""
    llm_prompt.load_env_file()

    vendor_name: str | None = None
    if getattr(args, "openai", False):
        vendor_name = "openai"
    elif getattr(args, "ollama", False):
        vendor_name = "ollama"
    elif vendor_is_configured():
        vendor_name = llm_vendors.active_vendor_name()

    if not vendor_name:
        logger.debug("LLM chat not requested")
        return None

    vendors = llm_vendors.load_vendors()
    vendor = vendors.get(vendor_name) or vendors[llm_vendors.DEFAULT_VENDOR]
    enabled = llm_prompt.load_llm_enabled()
    settings = llm_prompt.load_llm_settings()
    logger.info("Initializing LLM vendor '%s' (kind=%s)", vendor.name, vendor.kind)
    try:
        backend = create_backend_for_vendor(vendor, settings.ollama_timeout)
    except (LLMDependencyError, ImportError, RuntimeError) as exc:
        logger.warning("LLM vendor '%s' disabled: %s", vendor.name, exc)
        return None

    logger.info("LLM vendor '%s' ready", vendor.name)
    return LLMContext(
        backend_name=vendor.name, backend=backend, settings=settings, enabled=enabled, vendor=vendor
    )


def attach(window: QtWidgets.QWidget, context: LLMContext) -> None:
    """Attach the chat UI to the PixelCat window."""
    if not context:
        return
    logger.debug("Attaching LLM UI to window %s", window)
    llm_ui.attach_chat(window, context, enabled=context.enabled)


def create_backend_for_vendor(vendor: llm_vendors.Vendor, timeout: float) -> LLMBackend:
    """Build the right backend adapter for a vendor's kind."""
    if vendor.kind == llm_vendors.KIND_OLLAMA:
        from .llm_ollama import OllamaBackend

        return OllamaBackend(url=vendor.base_url, model=vendor.model, timeout=timeout)

    if vendor.kind == llm_vendors.KIND_OPENAI:
        from .llm_openai_compat import OpenAICompatBackend

        key = vendor.resolve_key()
        if not key:
            hint = f"set ${vendor.api_key_env}" if vendor.api_key_env else "enter an API key"
            raise LLMDependencyError(f"No API key for {vendor.name} — {hint} in LLM settings")
        return OpenAICompatBackend(
            base_url=vendor.base_url, api_key=key, model=vendor.model, timeout=timeout
        )

    raise LLMDependencyError(f"Unsupported vendor kind: {vendor.kind}")


__all__ = [
    "LLMContext",
    "LLMBackend",
    "LLMDependencyError",
    "add_arguments",
    "initialize",
    "attach",
]
