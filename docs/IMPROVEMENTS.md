# myCat — local fixes & suggested upstream changes

Notes from installing and running myCat locally with a local LLM (Ollama + Gemma 4
E4B Q4) on Ubuntu 26.04 / Wayland. Bugs found, how they were fixed locally, and
what to propose upstream.

---

## 1. Chat dialog can't be moved — it snaps back / "moves on its own" 🐛 (code bug)

**File:** `mycat/llm_ui.py` — `ChatDialog.moveEvent` / `ChatDialog.resizeEvent`

**Problem:** Both handlers called `self.controller._position_dialog()` on *every*
move and resize event. `_position_dialog()` re-anchors the dialog to the cat
window. So:
- When the user drags the chat window, `moveEvent` fires continuously and yanks
  it back to the cat → the window can't be moved and appears to move by itself.
- When the user resizes it, `resizeEvent` repositions it → the window jumps while
  resizing.

The `_suspend_anchor` guard only protects the *programmatic* `move()` inside
`_position_dialog`; user-initiated moves are not suspended, so they always
trigger a re-anchor.

**Fix (applied):** anchor the dialog only when it first opens (already done via
`_toggle_chat` → `_position_dialog`). Then leave user moves alone, and on resize
only re-wrap the message bubbles.

```diff
     def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
         super().resizeEvent(event)
-        if not getattr(self, "_suspend_anchor", False):
-            self.controller._position_dialog()
+        # Re-wrap message bubbles to the new width, but do NOT re-anchor the
+        # dialog to the cat — re-anchoring on every resize made the window jump.
+        self._update_bubble_widths()

     def moveEvent(self, event: QtGui.QMoveEvent) -> None:
         super().moveEvent(event)
-        if not getattr(self, "_suspend_anchor", False):
-            self.controller._position_dialog()
+        # Intentionally do nothing else: the dialog is anchored to the cat once
+        # when it opens, then stays where the user drags it. Re-anchoring here
+        # snapped the window back on every move, so it could not be moved.
```

**Note / design choice:** the controller's `eventFilter` still re-anchors the
dialog when the *cat* moves, so dragging the cat brings the chat along. That is
intended and not part of the bug. If upstream prefers the chat to stay fully
independent after the user moves it, add a `self._user_moved` flag set in
`moveEvent` and skip the eventFilter re-anchor once it's true.

---

## 2. Chat dialog minimum size too large 🐛 (usability)

**File:** `mycat/llm_ui.py` (in `ChatDialog.__init__`)

**Problem:** `setMinimumSize(320, 260)` is a hard floor; on small screens / for a
compact pet UI the chat box can't be shrunk past that.

**Fix (applied):**
```diff
-        self.setMinimumSize(320, 260)
+        self.setMinimumSize(200, 150)
```
Suggest making it configurable, or at least lowering the default.

---

## 3. Window lands off-screen under native Wayland 🐛 (platform / suggest upstream)

**Files:** `mycat/main.py` (`_load_position`, `_clamp_to_screens`, position save),
and `mycat/llm_ui.py` (`_position_dialog`).

**Observed:** On a Wayland session (`QT_QPA_PLATFORM=wayland`), the cat opened
off-screen. The persisted `~/.config/mycat/config.ini` `[window]` coordinates
were nonsense — e.g. `x = 8588`, then `x = 10082, y = -7960` on a single
`4608×2592` display.

**Root cause:** Native Wayland does not let a client set or read its absolute
window position. So `self.move(x, y)` is a no-op, and reading the window geometry
back (to persist it) returns invalid global/garbage coordinates, which then get
written to `config.ini` and reloaded next launch. The existing
`_clamp_to_screens()` guard can't help, because the underlying `move()` doesn't
take effect and the read-back values are already invalid.

**Workaround (used locally):** run under XWayland, where absolute positioning
works:
```bash
QT_QPA_PLATFORM=xcb mycat --ollama
```

**Suggested upstream fixes (any of):**
- Detect Wayland (`QtGui.QGuiApplication.platformName() == "wayland"`) and **skip
  persisting/restoring window position** (let the compositor place the window).
- Validate coordinates before writing them to `config.ini` (reject values outside
  the union of screen geometries instead of saving garbage).
- Document the `QT_QPA_PLATFORM=xcb` workaround in the README for Wayland users,
  alongside the existing `libxcb-cursor0` note.

---

## 4. New feature: local voice chat 🎤🔊 (optional, propose upstream)

Adds talk-to-your-cat: speak into the mic, the cat answers out loud — fully
local/offline, no cloud.

**New file:** `mycat/voice.py`
- **STT:** `faster-whisper` (`base.en`, CPU, int8). *CTranslate2 has no AMD/ROCm
  backend*, so STT runs on CPU; it's ~0.7 s for a short clip, so this is fine.
- **TTS:** `piper-tts` (OHF-Voice), voice `en_US-lessac-medium`. CPU, ~1 s/utterance.
- **Audio:** PipeWire `pw-record` (16 kHz mono capture) and `pw-play`
  (`--volume` for the level). No PortAudio/sounddevice dependency.
- Models load lazily + are cached; `prewarm()` loads them in a background thread.

**UI wiring:** `mycat/llm_ui.py` (`ChatDialog`)
- 🎤 **mic button** in the input row: click to record, click again → transcribe
  (off-thread) → fill the input and auto-send.
- 🔊 **mute toggle** + **volume slider** (0–100%) row under the input; controls
  the cat's TTS playback volume. Slider to 0 mutes.
- **Voice picker** dropdown: lists every `*.onnx` voice in `MYCAT_VOICES_DIR`
  (`~/.local/share/mycat-voices`); switching speaks a sample and persists the
  choice to `config.ini` `[voice] name`. Add/remove voices by dropping files in
  that folder (`python -m piper.download_voices <name> --data-dir <dir>`).
- Cat replies are spoken in `_on_ai_success` via a background `_SpeakWorker`
  (never blocks the UI thread). Transcription runs in a `_TranscribeWorker`.
- All voice controls are disabled gracefully if `voice.available()` is False
  (deps or voice model missing), so the text chat is unaffected.

**New dependencies (only needed for voice):** `faster-whisper`, `piper-tts`.
Setup: `pip install faster-whisper piper-tts` then
`python -m piper.download_voices en_US-lessac-medium --data-dir ~/.local/share/mycat-voices`.
Overridable via env: `MYCAT_WHISPER_MODEL`, `MYCAT_PIPER_VOICE`.

Suggested upstream packaging: make voice an optional extra,
`pip install mycat[voice]`, so the base app stays lightweight.

---

## 5. Streaming, stop, image input, clean output, decluttered UI (feature batch)

**Files:** `mycat/llm_ollama.py`, `mycat/llm_ui.py`, `mycat/voice.py`, `PROMPT.j2`.

- **Streaming replies + Stop button.** `OllamaBackend.stream_reply()` posts
  `stream:true` and yields content chunks; a `threading.Event` aborts mid-stream.
  The Send button turns into a red ■ Stop while generating; clicking it stops the
  text *and* any in-progress TTS (`voice.stop_speaking()`). Replies now render
  token-by-token in a live bubble.
- **Thinking disabled.** Gemma 4 streams `thinking` tokens by default; requests
  now send `"think": false` for fast, direct answers.
- **No asterisks.** `llm_ui._strip_markup()` removes `*` (markdown emphasis and
  `*action*` text) from both the displayed reply and the TTS input; a matching
  guideline was added to `PROMPT.j2` and appended to the system prompt.
- **Image input (vision).** 📎 button attaches an image; it's base64-encoded into
  the Ollama `images` field. Gemma 4 E4B reports the `vision` capability, so it
  answers about the picture. (It also reports `audio` — a future enhancement.)
- **Live transcription.** While recording, a 1.5 s timer transcribes the partial
  capture (`voice.transcribe_partial()` reads the growing WAV's PCM into a numpy
  array for whisper) and shows interim words in the input box; the final pass
  auto-sends.
- **Decluttered layout.** Input bar is now `⚙ 📎 🎤 [field] Send`. Voice picker,
  volume, and Export/Import moved into a collapsible ⚙ settings panel. Rounded
  bubbles, accent Send button, "You"/"Cat" headers.

---

## 6. Selectable personalities: Cat + loyal Dog (feature)

**New files:** `mycat/personas.py`, `mycat/PROMPT_dog.j2`, `mycat/images/dog.zip`,
`tools/make_dog.py`. **Touched:** `mycat/llm_prompt.py`, `mycat/llm_ui.py`, `mycat/main.py`.

- `personas.py` is the single source of truth: each persona maps a key to a
  `{label, image, template, voice}`. Choice persists to `config.ini` `[persona]`.
- **Cat** = existing gruff/sarcastic prompt (`PROMPT.j2`). **Dog** = new
  `PROMPT_dog.j2`: loyal, warm, supportive companion that still answers
  accurately and signs off "Woof!".
- `llm_prompt._load_prompt_template()` now loads the active persona's template
  (no cross-persona caching, so switching applies on the next message).
- Right-click → **Personality → Cat / Dog** switches the prompt, the on-screen
  name label (`MessageBubble` header via `personas.label()`), the image/animation,
  and the preferred TTS voice together (`main.PixelCatWindow._switch_persona`).
- **Dog art** is generated by `tools/make_dog.py` with Pillow: a supersampled
  cartoon golden puppy, 8-frame animation (wagging tail + a blink). Regenerate or
  swap `images/dog.zip` (must contain `animation.gif`) to restyle.

---

## Runtime / configuration notes (not bugs)

### Local LLM via Ollama + Gemma 4 E4B (Q4)
The app already ships an Ollama backend (`mycat --ollama`). Defaults
(`mycat/llm_prompt.py`): `OLLAMA_URL=http://127.0.0.1:11434`,
`OLLAMA_MODEL=llama3.1`. To use Gemma 4 E4B Q4, set in
`~/.config/mycat/config.ini`:
```ini
[ollama]
url = http://127.0.0.1:11434
model = gemma4:e4b-it-q4_K_M   ; Gemma 4 E4B, Q4_K_M quant (~9.6 GB)
timeout = 120
```
`ollama pull gemma4:e4b` (defaults to the q4_K_M build). On an AMD RX 9070 XT
(16 GB, ROCm) it loads 100% on GPU. Suggestion: mention a tested small local
model (e.g. `gemma4:e4b`) in the README instead of only `llama3.1`.

### Python 3.14
Installs fine — PySide6 6.11.1 ships abi3 (`cp310-abi3`) wheels that load on 3.14.
`pyproject.toml` `requires-python = ">=3.10"` is accurate.

---

## Summary of files changed locally
| File | Change | Type |
|------|--------|------|
| `mycat/llm_ui.py` | `moveEvent`/`resizeEvent` no longer re-anchor the dialog | bug fix (propose upstream) |
| `mycat/llm_ui.py` | chat dialog `setMinimumSize(320,260)` → `(200,150)` | usability (propose upstream) |
| `mycat/voice.py` (new) | local STT (faster-whisper) + TTS (Piper) helpers | new feature (propose upstream) |
| `mycat/llm_ui.py` | mic button, TTS on reply, mute + volume slider | new feature (propose upstream) |
| `~/.config/mycat/config.ini` | Ollama URL/model/timeout for Gemma 4 | local config only |
| run command | `QT_QPA_PLATFORM=xcb` for Wayland | workaround (document upstream) |
