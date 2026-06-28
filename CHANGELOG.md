# Changelog

All notable changes to this project are documented in this file.

## Unreleased

### Added
- **Live-cat demo (dev prototype).** `demo/live_cat_demo.py` — a standalone prototype of roadmap vertical B ("the cat feels alive"): the existing sprite is animated purely with code (breathing, blink, play hops, sleep, stress jitter) and system load is shown as the cat's *mood* rather than a number. Not wired into the shipped app; run with `python demo/live_cat_demo.py` (branch `demo/live-cat-prototype`).
- **Multiple chat vendors.** The LLM settings dialog (right-click → LLM…) now lets you pick a vendor — Ollama (default, local), OpenAI, Grok (xAI), Groq, DeepSeek, OpenRouter — or define a **custom** OpenAI-compatible endpoint (name + base URL + key + model). One adapter covers every OpenAI-compatible provider. API keys are hybrid: typed into the dialog (saved to config) or read from the vendor's environment variable.

### Changed
- The reminder settings dialog is now **non-modal**, so the flyby launched by its **Test** button can be grabbed and dragged while the dialog stays open (a modal dialog grabbed all input, leaving the test plane unclickable). Reopening while already open just raises the existing dialog (branch `fix/reminder-dialog-nonmodal`).
- The OpenAI/cloud backend is now a dependency-free `urllib` client (no `openai` package required) that supports any `base_url`.
- Renamed the "Start on login" item to "Autostart" in the context and tray menus (branch `chore/autostart-label`).
- Skins are now decoded straight from the packaged ZIP bytes into an in-memory `QBuffer`-backed `QMovie`; nothing is written to `/tmp/mycat` anymore (branch `feat/in-memory-skins`). The animation restart and skin-switch paths recreate the movie from the held GIF bytes, so no temp files are touched at any point.

### Removed
- `/tmp/mycat` temp-file extraction and the `TEMP_DIR` / `STATIC_PNG_PATH` / `ANIMATION_GIF_PATH` globals plus `get_temp_dir()` (branch `feat/in-memory-skins`).

## 0.1.6

### Added
- **Reminder** — a cat-on-a-plane banner that flies across the top of the screen at a chosen time (one-shot or daily). Configure it via right-click → Reminder….
- **Ollama settings menu** (right-click → Ollama…) — set host/port, fetch and pick a model, run a timed connection test, and enable/save the backend live (no file editing or restart). The LLM-enabled state now persists across restarts.
- `run.sh` / `run.bat` minimal launchers in the repo root that pass CLI flags through to `mycat` (branch `fix/headless-x11-overlay`).
- `--debug` flag to surface the verbose per-frame animation logging.
- `MYCAT_SHAPE_MASK=1/0` environment override to force or disable the no-compositor shape-mask fallback.

### Fixed
- Transparent overlay rendered as a solid black box on X11 without a compositor; it now falls back to clipping the window to the image silhouette via `setMask` (#38).
- Window spawned off-screen / in the top-left corner on headless/VNC X servers where Qt reports a 0×0 screen; screen size is now resolved via libX11 (`XDisplayWidth/Height`) and the window defaults to the bottom-right corner (#38).
- Right-click context menu never appeared on those sessions; a virtual RANDR monitor is registered at startup when none is active, so Qt sees the real screen and can position popups (#38).

### Changed
- Repeating per-frame animation log lines moved from INFO to DEBUG.

### Removed
- `run_windows.bat` (replaced by the minimal `run.bat`).
