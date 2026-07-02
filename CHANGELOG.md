# Changelog

All notable changes to this project are documented in this file.

## Unreleased

### Added
- **Morning digest.** The first time the cat sees you after 05:00 it flies yesterday's numbers past: "Yesterday: 🖱 2.1 km · ⌨ 13,402 · 🍅 6 · best focus 52 min". Delivered once per day (the date is remembered across restarts), silently skipped when yesterday has no story, and queued politely behind an early focus session (branch `feat/companion`).
- **Activity diary (opt-in, local-only).** Right-click → Activity…: the cat keeps a private log of your day — cursor distance (10 Hz `QCursor` polling, no hooks or permissions) and, with a separate opt-in (`mycat[activity]`, pynput), keystroke/click *counts* — the key identity is discarded inside the hook, only integers are stored. Minute buckets live in `activity.db` next to the focus sessions; nothing ever leaves the computer. The dialog shows an honest interval log correlated with pomodoro ("09:05–09:30 🍅 at the computer throughout ✓", "09:30–09:35 ☕ rested properly — away from the computer ✓", "14:00–15:30 💻 at the computer outside pomodoro") plus day totals (cursor km via screen DPI, keys, 🍅, best focus). Configurable retention (90 days default), a delete-everything button, and a one-time first-run prompt — input monitoring is off until the user consciously agrees (branch `feat/companion`).
- **Calendar reminders (opt-in).** Right-click → Calendar…: paste the secret ICS URL (Google's "Secret address in iCal format", Apple/Outlook private links, `webcal://` accepted) and the cat announces events ~10 min ahead (configurable). Recurring events are expanded properly (new optional extra `mycat[calendar]`: `icalendar` + `recurring-ical-events`); all-day events are skipped. Calendar banners are the only ones urgent enough to fly through an active focus session. Zero network requests until enabled; the URL is treated as a secret in the owner-only config (branch `feat/companion`).
- **GitHub notifications (opt-in).** Right-click → GitHub…: paste a fine-grained PAT (read-only *Notifications* permission; empty field falls back to `$GITHUB_TOKEN`) and the cat flies a banner for review requests, mentions, assignments and (optionally) CI activity — double-click opens the PR. The client polls `api.github.com` directly (BYO-token, no mycat server involved), honours `X-Poll-Interval`/`If-Modified-Since`, baselines silently on startup so old unread items don't flood the screen, and makes zero network requests until enabled. Non-urgent banners are held during focus sessions (branch `feat/companion`).
- **Focus sessions (pomodoro).** Right-click (or tray) → "Focus 25 min": the cat keeps still while you work, a thin progress bar under it fills up, and hovering the cat shows "Focus · 17:42 left · today 4 🍅". Breaks start by themselves (5 min; a 15-min long break after every 4 sessions) and are announced by a flyby; the next focus is started deliberately. GitHub-style announcements are held for the break via the announcer's DND. Durations configurable in `config.ini` `[focus]`; sessions are recorded locally in `activity.db` for the upcoming activity log. A deadline overshot by minutes (suspend/lid close) finishes quietly instead of celebrating hours later (branch `feat/companion`).
- **Announcement queue.** All companion features (focus sessions, GitHub notifications, calendar reminders, the morning digest) deliver banners through one `Announcer`: a single flyby at a time with a pacing gap, do-not-disturb hold during focus sessions (urgent items break through), and an optional link on a banner opened by double-click or the flyby's context menu (branch `feat/companion`).
- **First-run prompt to start on login.** On the first launch (where autostart is supported and not already on), mycat asks once whether to start every login — the autostart toggle was otherwise buried in the right-click menu. The answer is remembered in `[settings] autostart_prompted` so it is never asked twice (branch `feat/persistence-hardening`).
- **Single-instance guard.** A second launch no longer spawns a second cat — it detects the running instance via a `QLockFile` and exits (a lock left by a crashed instance is reclaimed automatically) (branch `feat/persistence-hardening`).
- **Multiple chat vendors.** The LLM settings dialog (right-click → LLM…) now lets you pick a vendor — Ollama (default, local), OpenAI, Grok (xAI), Groq, DeepSeek, OpenRouter — or define a **custom** OpenAI-compatible endpoint (name + base URL + key + model). One adapter covers every OpenAI-compatible provider. API keys are hybrid: typed into the dialog (saved to config) or read from the vendor's environment variable.
- **Interactive char packs.** A char is a folder or `.zip` with `static`/`blink` frames, L/R pupil sprites, optional body GIFs, and a `config.json`. The cat tracks the cursor with synchronous pupils, blinks, reacts to clicks, and runs an asset-gated state machine (idle / yawn / sleep / hungry-on-low-battery) — each behaviour active only if its assets exist. Fits a `max_width`×`max_height` box; crisp edges on X11 without a compositor. Bundled `cat` char; format spec in `docs/CHARS.md`.

### Changed
- mycat now **lives in the system tray**: closing or hiding its windows no longer quits the app — only the explicit Quit action does (when a tray is available, so the user is never left with an invisible process). Keeps the cat persistent across the session (branch `feat/persistence-hardening`).
- Renamed "skin" → "char" across the UI, code, docs, and shop wire-contract; the bundled directory moved `images/` → `chars/`.
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
