"""Chat vendor registry: built-in presets plus user-defined custom vendors.

A "vendor" is just an endpoint config. Two adapter *kinds* cover everything:

- ``ollama``  — local Ollama API (``/api/chat`` + ``/api/tags``), no key.
- ``openai``  — the OpenAI-compatible Chat Completions API
  (``/chat/completions`` + ``/models`` with a Bearer key). OpenAI, Grok,
  Groq, DeepSeek, OpenRouter and most other providers speak this, so a
  custom vendor is nothing more than a name + base_url (+ key + model).

API keys are hybrid: a literal key saved in config.ini wins; otherwise the
key is read from the vendor's environment variable.
"""

from __future__ import annotations

import configparser
import logging
import os
from dataclasses import dataclass, replace

from .llm_prompt import CFG_DIR, CFG_FILE

logger = logging.getLogger(__name__)

KIND_OLLAMA = "ollama"
KIND_OPENAI = "openai"

SECTION_PREFIX = "vendor:"
DEFAULT_VENDOR = "ollama"


@dataclass
class Vendor:
    name: str
    kind: str
    base_url: str
    label: str = ""
    api_key: str = ""        # literal key from config — takes priority
    api_key_env: str = ""    # env var to read the key from when api_key is empty
    model: str = ""
    builtin: bool = False

    @property
    def needs_key(self) -> bool:
        return self.kind == KIND_OPENAI

    def resolve_key(self) -> str:
        """The effective API key: the stored literal, else the env var."""
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            return os.getenv(self.api_key_env, "")
        return ""


def builtin_vendors() -> dict:
    """Fresh copies of the built-in presets (named by the provider)."""
    presets = [
        Vendor("ollama", KIND_OLLAMA, "http://localhost:11434",
               label="Ollama (local)", model="llama3.1", builtin=True),
        Vendor("openai", KIND_OPENAI, "https://api.openai.com/v1",
               label="OpenAI", api_key_env="OPENAI_API_KEY", model="gpt-4o-mini", builtin=True),
        Vendor("grok", KIND_OPENAI, "https://api.x.ai/v1",
               label="Grok (xAI)", api_key_env="XAI_API_KEY", model="grok-2-latest", builtin=True),
        Vendor("groq", KIND_OPENAI, "https://api.groq.com/openai/v1",
               label="Groq (free)", api_key_env="GROQ_API_KEY", model="llama-3.3-70b-versatile", builtin=True),
        Vendor("deepseek", KIND_OPENAI, "https://api.deepseek.com/v1",
               label="DeepSeek", api_key_env="DEEPSEEK_API_KEY", model="deepseek-chat", builtin=True),
        Vendor("openrouter", KIND_OPENAI, "https://openrouter.ai/api/v1",
               label="OpenRouter (free)", api_key_env="OPENROUTER_API_KEY", model="", builtin=True),
    ]
    return {v.name: v for v in presets}


def read_config() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    if CFG_FILE.exists():
        try:
            parser.read(CFG_FILE)
        except configparser.Error as exc:
            logger.warning("Unable to parse %s: %s", CFG_FILE, exc)
    return parser


def load_vendors() -> dict:
    """Built-in presets merged with overrides and custom vendors from config."""
    vendors = {name: replace(v) for name, v in builtin_vendors().items()}
    parser = read_config()

    # Legacy [ollama] section (url/model) -> ollama vendor, for older configs.
    if parser.has_section("ollama"):
        ollama = vendors["ollama"]
        ollama.base_url = parser.get("ollama", "url", fallback=ollama.base_url)
        ollama.model = parser.get("ollama", "model", fallback=ollama.model)

    for section in parser.sections():
        if not section.startswith(SECTION_PREFIX):
            continue
        name = section[len(SECTION_PREFIX):]
        sec = parser[section]
        vendor = vendors.get(name) or Vendor(name, KIND_OPENAI, "", label=name)
        vendor.kind = sec.get("kind", vendor.kind)
        vendor.base_url = sec.get("base_url", vendor.base_url)
        vendor.api_key = sec.get("api_key", vendor.api_key)
        vendor.api_key_env = sec.get("api_key_env", vendor.api_key_env)
        vendor.model = sec.get("model", vendor.model)
        if not vendor.label:
            vendor.label = name
        vendors[name] = vendor
    return vendors


def get_vendor(name: str) -> Vendor | None:
    return load_vendors().get(name)


def active_vendor_name() -> str:
    parser = read_config()
    if parser.has_option("llm", "vendor"):
        return parser.get("llm", "vendor")
    # Fall back to LLM_BACKEND env (openai/ollama) or the default.
    env_backend = (os.getenv("LLM_BACKEND") or "").strip().lower()
    if env_backend in (KIND_OLLAMA, "openai"):
        return env_backend if env_backend != "openai" else "openai"
    return DEFAULT_VENDOR


def active_vendor() -> Vendor:
    vendors = load_vendors()
    name = active_vendor_name()
    return vendors.get(name) or vendors[DEFAULT_VENDOR]


def save_vendor(vendor: Vendor, *, make_active: bool = True) -> None:
    """Persist a vendor to [vendor:NAME] and optionally mark it active."""
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    parser = read_config()
    section = f"{SECTION_PREFIX}{vendor.name}"
    if not parser.has_section(section):
        parser.add_section(section)
    parser.set(section, "kind", vendor.kind)
    parser.set(section, "base_url", vendor.base_url)
    parser.set(section, "model", vendor.model or "")
    # Only persist a literal key when one was entered (hybrid storage).
    if vendor.api_key:
        parser.set(section, "api_key", vendor.api_key)
    elif parser.has_option(section, "api_key"):
        parser.remove_option(section, "api_key")
    if vendor.api_key_env:
        parser.set(section, "api_key_env", vendor.api_key_env)
    if make_active:
        if not parser.has_section("llm"):
            parser.add_section("llm")
        parser.set("llm", "vendor", vendor.name)
    with open(CFG_FILE, "w") as handle:
        parser.write(handle)
    logger.info("Saved vendor %s (kind=%s, active=%s)", vendor.name, vendor.kind, make_active)


__all__ = [
    "Vendor",
    "KIND_OLLAMA",
    "KIND_OPENAI",
    "DEFAULT_VENDOR",
    "builtin_vendors",
    "load_vendors",
    "get_vendor",
    "active_vendor",
    "active_vendor_name",
    "save_vendor",
]
