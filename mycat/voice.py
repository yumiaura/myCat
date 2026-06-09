"""Local voice I/O for PixelCat.

- Speech-to-text via faster-whisper (CPU; CTranslate2 has no AMD/ROCm backend).
- Text-to-speech via Piper (CPU).
- Audio capture/playback via PipeWire (pw-record / pw-play).

Everything is local and offline. Models are loaded lazily and cached.
"""

from __future__ import annotations

import configparser
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import wave
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def _player_cmd(path: str, volume: float) -> Optional[List[str]]:
    """First available audio player, with volume where supported (portable)."""
    v = max(0.0, min(1.0, volume))
    if shutil.which("pw-play"):
        return ["pw-play", "--volume", f"{v:.2f}", path]
    if shutil.which("paplay"):
        return ["paplay", f"--volume={int(v * 65536)}", path]
    if shutil.which("ffplay"):
        return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-volume", str(int(v * 100)), path]
    if shutil.which("aplay"):
        return ["aplay", "-q", path]  # no volume control
    return None


def _recorder_cmd(path: str) -> Optional[List[str]]:
    """First available 16 kHz mono recorder writing a WAV (portable)."""
    if shutil.which("pw-record"):
        return ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", path]
    if shutil.which("parecord"):
        return ["parecord", "--rate=16000", "--channels=1", "--format=s16le", "--file-format=wav", path]
    if shutil.which("arecord"):
        return ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", path]
    return None


def audio_io_available() -> bool:
    """True if both a recorder and a player exist on this system."""
    return _recorder_cmd("x") is not None and _player_cmd("x", 1.0) is not None

# Configurable via environment.
WHISPER_MODEL = os.getenv("MYCAT_WHISPER_MODEL", "base.en")
# Speech-to-text language. "en" by default (fast, English-only base.en model).
# For other languages set MYCAT_WHISPER_MODEL=base (multilingual) and
# MYCAT_WHISPER_LANG=<code> (e.g. es, fr, de, hi), or "auto" to auto-detect.
WHISPER_LANG = os.getenv("MYCAT_WHISPER_LANG", "en")
_LANG = None if WHISPER_LANG.strip().lower() in ("", "auto") else WHISPER_LANG.strip()
VOICES_DIR = Path(
    os.getenv("MYCAT_VOICES_DIR", str(Path.home() / ".local" / "share" / "mycat-voices"))
)
DEFAULT_VOICE = os.getenv("MYCAT_PIPER_VOICE", str(VOICES_DIR / "en_US-lessac-medium.onnx"))
# Kept for backwards compatibility (older code referenced PIPER_VOICE).
PIPER_VOICE = DEFAULT_VOICE
_CFG_FILE = Path.home() / ".config" / "mycat" / "config.ini"

_whisper = None
_whisper_lock = threading.Lock()
_piper = None
_piper_lock = threading.Lock()
_current_voice: Optional[str] = None
_play_proc: Optional[subprocess.Popen] = None
_play_lock = threading.Lock()


def list_voices() -> List[Tuple[str, str]]:
    """Return [(display_name, path), ...] for every downloaded Piper voice."""
    if not VOICES_DIR.exists():
        return []
    return [(p.stem, str(p)) for p in sorted(VOICES_DIR.glob("*.onnx"))]


def _load_saved_voice() -> Optional[str]:
    try:
        parser = configparser.ConfigParser()
        parser.read(_CFG_FILE)
        if parser.has_option("voice", "name"):
            candidate = VOICES_DIR / f"{parser.get('voice', 'name')}.onnx"
            if candidate.exists():
                return str(candidate)
    except (configparser.Error, OSError) as exc:  # pragma: no cover
        logger.debug("Could not read saved voice: %s", exc)
    return None


def _save_voice(path: str) -> None:
    try:
        parser = configparser.ConfigParser()
        parser.read(_CFG_FILE)
        if not parser.has_section("voice"):
            parser.add_section("voice")
        parser.set("voice", "name", Path(path).stem)
        _CFG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CFG_FILE, "w", encoding="utf-8") as handle:
            parser.write(handle)
    except (configparser.Error, OSError) as exc:  # pragma: no cover
        logger.warning("Could not persist voice selection: %s", exc)


def get_voice() -> str:
    """Path of the currently selected voice (from config, default, or first found)."""
    global _current_voice
    if _current_voice is None:
        _current_voice = _load_saved_voice() or DEFAULT_VOICE
        if not Path(_current_voice).exists():
            voices = list_voices()
            _current_voice = voices[0][1] if voices else DEFAULT_VOICE
    return _current_voice


def set_voice(path: str, persist: bool = True) -> None:
    """Switch the active TTS voice; the next spoken line uses it."""
    global _current_voice, _piper
    with _piper_lock:
        _current_voice = path
        _piper = None  # drop cached model so the new voice loads on next use
    if persist:
        _save_voice(path)
    logger.info("Voice set to %s", Path(path).stem)


def available() -> bool:
    """True if at least one TTS voice exists and both backends import."""
    if not list_voices() and not Path(DEFAULT_VOICE).exists():
        logger.warning("No Piper voices found in %s; voice disabled", VOICES_DIR)
        return False
    try:
        import faster_whisper  # noqa: F401
        import piper  # noqa: F401
    except Exception as exc:  # pragma: no cover
        logger.warning("Voice backends unavailable: %s", exc)
        return False
    if not audio_io_available():
        logger.warning("No audio player/recorder found; voice disabled")
        return False
    return True


def _get_whisper():
    global _whisper
    with _whisper_lock:
        if _whisper is None:
            from faster_whisper import WhisperModel

            logger.info("Loading whisper model '%s' (CPU)", WHISPER_MODEL)
            _whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        return _whisper


def _get_piper():
    global _piper
    with _piper_lock:
        if _piper is None:
            from piper import PiperVoice

            path = get_voice()
            logger.info("Loading piper voice %s", path)
            _piper = PiperVoice.load(path)
        return _piper


def prewarm() -> None:
    """Load both models in the background so the first use isn't slow."""
    def _run() -> None:
        try:
            _get_piper()
            _get_whisper()
            logger.info("Voice models pre-warmed")
        except Exception as exc:  # pragma: no cover
            logger.warning("Voice prewarm failed: %s", exc)

    threading.Thread(target=_run, daemon=True).start()


class Recorder:
    """Toggle microphone recording to a temp WAV via pw-record (16 kHz mono)."""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._path: Optional[str] = None

    @property
    def active(self) -> bool:
        return self._proc is not None

    @property
    def path(self) -> Optional[str]:
        return self._path

    def start(self) -> None:
        if self._proc is not None:
            return
        cmd = _recorder_cmd("")
        if cmd is None:
            logger.warning("No audio recorder found (pw-record/parecord/arecord); mic disabled")
            return
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="mycat_rec_")
        os.close(fd)
        self._path = path
        cmd[-1] = path
        self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.debug("Recording to %s via %s", path, cmd[0])

    def stop(self) -> Optional[str]:
        """Stop recording and return the WAV path (or None if not recording)."""
        if self._proc is None:
            return None
        self._proc.terminate()
        try:
            self._proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        self._proc = None
        return self._path


def transcribe(wav_path: str, cleanup: bool = True) -> str:
    """Transcribe a WAV file to text (English)."""
    model = _get_whisper()
    segments, _ = model.transcribe(wav_path, language=_LANG)
    text = "".join(segment.text for segment in segments).strip()
    logger.info("Transcribed: %s", text)
    if cleanup:
        try:
            os.remove(wav_path)
        except OSError:
            pass
    return text


def transcribe_partial(wav_path: str) -> str:
    """Transcribe whatever audio has been captured so far (for live display).

    Reads the raw 16 kHz mono s16 PCM out of a still-growing WAV (whose header
    length fields aren't final yet) and feeds it to whisper as a float array.
    """
    import numpy as np

    try:
        with open(wav_path, "rb") as handle:
            raw = handle.read()
    except OSError:
        return ""
    if len(raw) <= 44:  # only the WAV header so far
        return ""
    pcm = raw[44:]
    if len(pcm) % 2:
        pcm = pcm[:-1]
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if samples.size < 1600:  # < 0.1 s of audio
        return ""
    model = _get_whisper()
    segments, _ = model.transcribe(samples, language=_LANG)
    return "".join(segment.text for segment in segments).strip()


def speak(text: str, volume: float = 1.0) -> None:
    """Synthesize `text` with Piper and play it at `volume` (0.0-1.0). Blocking.

    Playback can be interrupted with stop_speaking().
    """
    global _play_proc
    text = text.strip()
    if not text or volume <= 0.0:
        return
    piper_voice = _get_piper()
    fd, path = tempfile.mkstemp(suffix=".wav", prefix="mycat_tts_")
    os.close(fd)
    try:
        with wave.open(path, "wb") as wav_file:
            piper_voice.synthesize_wav(text, wav_file)
        cmd = _player_cmd(path, volume)
        if cmd is None:
            logger.warning("No audio player found (pw-play/paplay/ffplay/aplay); TTS muted")
            return
        with _play_lock:
            _play_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc = _play_proc
        proc.wait()
        with _play_lock:
            if _play_proc is proc:
                _play_proc = None
    except Exception as exc:  # pragma: no cover
        logger.warning("TTS failed: %s", exc)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def stop_speaking() -> None:
    """Interrupt any in-progress TTS playback."""
    global _play_proc
    with _play_lock:
        if _play_proc is not None and _play_proc.poll() is None:
            _play_proc.terminate()
        _play_proc = None


def is_speaking() -> bool:
    """True while audio is actively playing (not during synthesis)."""
    with _play_lock:
        return _play_proc is not None and _play_proc.poll() is None


__all__ = [
    "available",
    "prewarm",
    "Recorder",
    "transcribe",
    "transcribe_partial",
    "speak",
    "stop_speaking",
    "list_voices",
    "get_voice",
    "set_voice",
    "VOICES_DIR",
    "PIPER_VOICE",
    "WHISPER_MODEL",
]
