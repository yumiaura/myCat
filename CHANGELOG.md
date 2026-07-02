# Changelog

All notable changes to this project are documented in this file.

## Unreleased

### Added
- **Focus sessions (pomodoro).** Right-click (or tray) → "Focus 25 min": the cat keeps still while you work, a thin progress bar under it fills up, and hovering the cat shows "Focus · 17:42 left · today 4 🍅". Breaks start by themselves (5 min; a 15-min long break after every 4 sessions) and are announced by a flyby; the next focus is started deliberately. GitHub-style announcements are held for the break via the announcer's DND. Durations configurable in `config.ini` `[focus]`; sessions are recorded locally in `activity.db` for the upcoming activity log. A deadline overshot by minutes (suspend/lid close) finishes quietly instead of celebrating hours later (branch `feat/companion`).
- **Announcement queue.** All companion features (focus sessions, GitHub notifications, calendar reminders, the morning digest) deliver banners through one `Announcer`: a single flyby at a time with a pacing gap, do-not-disturb hold during focus sessions (urgent items break through), and an optional link on a banner opened by double-click or the flyby's context menu (branch `feat/companion`).
- **First-run prompt to start on login.** On the first launch (where autostart is supported and not already on), mycat asks once whether to start every login — the autostart toggle was otherwise buried in the right-click menu. The answer is remembered in `[settings] autostart_prompted` so it is never asked twice (branch `feat/persistence-hardening`).
- **Single-instance guard.** A second launch no longer spawns a second cat — it detects the running instance via a `QLockFile` and exits (a lock left by a crashed instance is reclaimed automatically) (branch `feat/persistence-hardening`).
- **Multiple chat vendors.** The LLM settings dialog (right-click → LLM…) now lets you pick a vendor — Ollama (default, local), OpenAI, Grok (xAI), Groq, DeepSeek, OpenRouter — or define a **custom** OpenAI-compatible endpoint (name + base URL + key + model). One adapter covers every OpenAI-compatible provider. API keys are hybrid: typed into the dialog (saved to config) or read from the vendor's environment variable.

### Changed
- mycat now **lives in the system tray**: closing or hiding its windows no longer quits the app — only the explicit Quit action does (when a tray is available, so the user is never left with an invisible process). Keeps the cat persistent across the session (branch `feat/persistence-hardening`).
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
