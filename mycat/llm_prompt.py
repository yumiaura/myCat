"""LLM utilities for configuration, history persistence, and prompt rendering."""

from __future__ import annotations

import configparser
import logging
import os
import re
import tempfile
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

APP_NAME = "mycat"
CFG_DIR = Path.home() / ".config" / APP_NAME
CFG_FILE = CFG_DIR / "config.ini"
HISTORY_FILE = CFG_DIR / "history.txt"
PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parent / "PROMT.j2"

DEFAULT_PROMPT_TEMPLATE = """You are a cute, affectionate talking cat belonging to a girl.
Current date and time: {{date}}.
Recent conversation (latest {{history_count}} messages):
{{history}}
Stay warm, playful, and loving when you reply."""

_ENV_LOADED = False
_PROMPT_TEMPLATE_CACHE: Optional[str] = None

HISTORY_HEADER_RE = re.compile(r"^\[(?P<timestamp>.+?)\]\s+(?P<label>REQUEST|RESPONSE):$")


@dataclass
class LLMSettings:
    """Configuration bundle for all supported LLM backends."""

    openai_api_key: Optional[str]
    openai_model: str
    ollama_url: str
    ollama_model: str
    ollama_timeout: float
    history_messages: int


def load_env_file() -> None:
    """Populate environment variables from .env-style files once per process."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True

    def apply_env(path: Path) -> None:
        try:
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "#" in line:
                    line = line.split("#", 1)[0].strip()
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if not key:
                    continue
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
            logger.debug("Loaded env values from %s", path)
        except OSError as exc:
            logger.debug("Unable to read env file %s: %s", path, exc)

    candidates: List[Path] = []
    override_path = os.environ.get("MYCAT_ENV_FILE")
    if override_path:
        candidates.append(Path(override_path).expanduser())
    candidates.append(Path.cwd() / ".env")
    candidates.append(Path(__file__).resolve().parent.parent / ".env")

    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen or not candidate.exists():
            continue
        seen.add(candidate)
        apply_env(candidate)


def load_llm_settings() -> LLMSettings:
    """Merge values from environment variables and config.ini into a single settings object."""
    settings = LLMSettings(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1"),
        ollama_timeout=float(os.getenv("OLLAMA_TIMEOUT", "60")),
        history_messages=int(os.getenv("LLM_HISTORY_MESSAGES", "10")),
    )

    parser = configparser.ConfigParser()
    if CFG_FILE.exists():
        try:
            parser.read(CFG_FILE)
        except configparser.Error as exc:
            logger.warning("Unable to parse %s: %s", CFG_FILE, exc)
            parser = None  # type: ignore[assignment]

    if parser:
        if parser.has_section("openai"):
            settings.openai_api_key = parser.get("openai", "api_key", fallback=settings.openai_api_key)
            settings.openai_model = parser.get("openai", "model", fallback=settings.openai_model)
        if parser.has_section("ollama"):
            settings.ollama_url = parser.get("ollama", "url", fallback=settings.ollama_url)
            settings.ollama_model = parser.get("ollama", "model", fallback=settings.ollama_model)
            settings.ollama_timeout = parser.getfloat("ollama", "timeout", fallback=settings.ollama_timeout)
        if parser.has_section("llm"):
            settings.history_messages = parser.getint("llm", "history_messages", fallback=settings.history_messages)

    logger.debug("LLM settings loaded: %s", settings)
    return settings


def ensure_history_file() -> Path:
    """Return a writable history file path, creating one if needed."""
    try:
        CFG_DIR.mkdir(parents=True, exist_ok=True)
        if not HISTORY_FILE.exists():
            HISTORY_FILE.touch()
        return HISTORY_FILE
    except OSError as exc:
        logger.warning("Falling back to temp history file: %s", exc)
        fallback = Path(tempfile.gettempdir()) / "mycat_history.txt"
        fallback.touch(exist_ok=True)
        return fallback


def parse_history_file(path: Path) -> List[Tuple[str, str, str]]:
    """Parse history file into structured messages."""
    entries: List[Tuple[str, str, str]] = []
    role: Optional[str] = None
    timestamp: Optional[str] = None
    buffer: List[str] = []

    def flush() -> None:
        nonlocal role, timestamp, buffer
        if role and timestamp is not None:
            entries.append((role, "\n".join(buffer).rstrip("\n"), timestamp))
        role = None
        timestamp = None
        buffer = []

    try:
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.rstrip("\n")
                match = HISTORY_HEADER_RE.match(line.strip())
                if match:
                    flush()
                    ts = match.group("timestamp").strip()
                    label = match.group("label").upper()
                    role = "user" if label == "REQUEST" else "cat"
                    timestamp = ts
                else:
                    buffer.append(line)
        flush()
    except OSError as exc:
        logger.debug("Unable to read history file %s: %s", path, exc)

    return entries


def append_history_entry(path: Path, role: str, text: str, timestamp: str) -> None:
    """Append a single message to the history file."""
    label = "REQUEST" if role == "user" else "RESPONSE"
    block = f"[{timestamp}] {label}:\n{text}\n"
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(block)
    except OSError as exc:
        logger.debug("Unable to write history entry: %s", exc)


def get_history_tail(history_path: Path, limit: int) -> List[str]:
    if limit <= 0:
        return []
    lines: deque[str] = deque(maxlen=limit)
    try:
        with history_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                lines.append(line.rstrip())
    except OSError as exc:
        logger.debug("Unable to read history tail: %s", exc)
        return []
    return list(lines)


def render_prompt(history_lines: List[str], history_limit: int) -> str:
    """Produce the final system prompt text using the stored template."""
    template = _load_prompt_template()
    history_text = "\n".join(history_lines) if history_lines else "No history available."
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    replacements = {
        "{{date}}": now,
        "{{history}}": history_text,
        "{{history_count}}": str(history_limit),
    }
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    return rendered


def _load_prompt_template() -> str:
    global _PROMPT_TEMPLATE_CACHE
    if _PROMPT_TEMPLATE_CACHE is not None:
        return _PROMPT_TEMPLATE_CACHE
    if PROMPT_TEMPLATE_PATH.exists():
        try:
            _PROMPT_TEMPLATE_CACHE = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
            logger.debug("Loaded prompt template from %s", PROMPT_TEMPLATE_PATH)
            return _PROMPT_TEMPLATE_CACHE
        except OSError as exc:
            logger.warning("Unable to read %s: %s", PROMPT_TEMPLATE_PATH, exc)
    _PROMPT_TEMPLATE_CACHE = DEFAULT_PROMPT_TEMPLATE
    return _PROMPT_TEMPLATE_CACHE


__all__ = [
    "LLMSettings",
    "APP_NAME",
    "CFG_DIR",
    "CFG_FILE",
    "HISTORY_FILE",
    "PROMPT_TEMPLATE_PATH",
    "load_env_file",
    "load_llm_settings",
    "ensure_history_file",
    "parse_history_file",
    "append_history_entry",
    "get_history_tail",
    "render_prompt",
]
