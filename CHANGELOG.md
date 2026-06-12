# Changelog

All notable changes to this project are documented in this file.

## Unreleased

### Changed
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
