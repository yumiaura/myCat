# Changelog

All notable changes to this project are documented in this file.

## [0.1.26] - 2026-07-22

### Added
- **Preview a generated char before saving it.** The "Generate a custom char with AI" dialog is now a compact 2×2 grid: identity + backend settings top-left, a preview (matching that block's height) top-right, prompts bottom-left (2/3 width), and reference photos bottom-right. **Generate** produces an image and shows it in the preview without saving or closing; **Save** installs the previewed char and closes (Save is disabled until there's something to save). You can regenerate as many times as you like before committing.
- **Click a generation error to copy it.** The red status line in the "Generate a custom char with AI" dialog is now clickable when it shows an error — a click copies the full message to the clipboard (handy for pasting a server's 500 into a bug report).

### Changed
- **New default self-hosted prompt/negative.** The Stable Diffusion / ComfyUI defaults are now a chibi anime girl (school uniform, full body, no shadows) with a shadow-suppressing negative prompt — the cat-specific tags (ears, paws, tail, whiskers) are gone. Existing saved prompts are untouched; click **Reset** in the dialog to load the new defaults.
- **Generated chars are scaled down to 200×300 (width first).** A generated char is now stored and shown at most 200×300 px (was 240×400, from a 600×900 frame), so it sits smaller on the desktop; the renderer only ever shrinks, so it's never enlarged. Existing saved chars are unaffected — regenerate to get the new size.
- **Background defaults to "Remove" for new generations.** A fresh setup now starts with plain-background removal so the char sits transparently on the desktop out of the box; existing saved choices are untouched.

### Fixed
- **Self-hosted generation targets SDXL resolution.** The Stable Diffusion / ComfyUI request hard-coded 512×768 (SD1.5), so modern local checkpoints (SDXL, Illustrious, Pony, NoobAI) produced mush or ran out of memory. It now generates at the 832×1216 SDXL portrait bucket (branch `fix/sdxl-size-and-a1111-errors`).
- **A1111 errors now read cleanly.** AUTOMATIC1111 returns its error as `{"error": "<type>", "errors": "<detail>"}` — a string, not OpenAI's `{"error": {"message"}}` — so the parser threw and fell back to a raw truncated JSON blob. A new `api_error_message()` understands the OpenAI, A1111 and FastAPI/ComfyUI shapes, so a 500 now surfaces the actual reason (e.g. `Stable Diffusion error (500): OutOfMemoryError: CUDA out of memory.`).

## [0.1.25] - 2026-07-22

### Fixed
- **No shutdown crash from an in-flight GitHub poll.** Quitting while a background GitHub notification poll was still running raised `RuntimeError: Signal source has been deleted` (the worker's signal emitter was freed before the poll finished). The emit is now guarded, so a poll that lands mid-shutdown is dropped quietly.
- **The update check now uses your GitHub token, so it isn't rate-limited.** It made anonymous GitHub calls (60 req/h per IP), so a shared IP could hit "rate-limited" even with a token configured. A shared `github_api.py` layer now attaches the `[github]` token (or `GITHUB_TOKEN`) to *every* GitHub request — the update check and the notifications poller both go through it (5000 req/h). The update dialog is shorter and always shows the current and latest version, then whether an update is needed.
- **The autostart entry shows "myCat", not "mycat".** The XDG autostart `.desktop` wrote `Name=mycat` while the app-menu entry wrote `Name=myCat`, so the same app showed two different names.
- **Switching char no longer half-updates the window on a bad char.** `_load_image` mutated the window's state and resized it inside the same `try` that decodes the GIF, so a decode failure left the window half-switched; it now decodes into locals first and commits only on success.

### Changed
- **Internal maintainability refactor (no behaviour change).** A single source of truth for the config path (`paths.py`) and shared config load/save plumbing (`config_store.py`) replace the per-feature copy-paste, and every single-underscore identifier across the codebase was renamed to a plain public name (house style). Also corrects stale contributor paths in `CLAUDE.md` (`chars/` and the "Chars" menu) and drops a dead `prompted` config field (branch `chore/maintainability-phase-0`).

## [0.1.24] - 2026-07-21

### Fixed
- **The Linux package icon shows the current cat.** The `.deb` / AppImage app icon shipped an old, blank-eyed cat that was clipped flat at the bottom; it's regenerated from `mycat/assets/icon.png` at 256×256 so packages match what the app draws (branch `chore/one-launcher-and-icon`).

### Changed
- **One launcher script.** `start.sh` was folded into `run.sh` (the documented launcher) and removed; `run.sh` keeps a `PYTHON` interpreter override and now auto-detects `DISPLAY` for launches that don't inherit one (tmux / ssh / detached terminal). Dev-facing (branch `chore/one-launcher-and-icon`).

## [0.1.23] - 2026-07-19

### Changed
- **The update dialog is one consistent set of buttons: Releases · Update · Close.** *Releases* always opens the releases page; *Update* downloads the new build and restarts, and is enabled only when a self-update is actually possible (Windows/macOS with a newer release) — greyed out on pip/git/deb/AppImage installs and whenever there's nothing to update. Replaces the old mix of an "Open releases" box and a separate Yes/No prompt (branch `fix/heatmap-perf-and-update-buttons`).

### Fixed
- **The Keyboard heatmap window no longer stalls typing.** While collecting, its 500 ms refresh reopened a full X connection every tick on the python-xlib path, blocking the event loop whenever keys were flowing — so typing froze and the cursor stuttered. Availability is now read once when the window opens, and the board repaints only when the tally changes (branch `fix/heatmap-perf-and-update-buttons`).

## [0.1.22] - 2026-07-19

### Added
- **Opt-in keyboard heatmap in the Activity tab.** A new **Heatmap** button next to *Save* (enabled only while the toggle is on) opens an on-screen Latin QWERTY board that colours each key on a blue→red scale — blue = 1 press, red = the most presses on a single key this session — with a matching gradient legend under the board. Collecting the counts is a separate **Heatmap** toggle in the Activity *Enable:* row, **off by default**; only aggregate per-key counts are kept, in memory, never the order/timing/text and never on disk (they reset on restart). Counting is by logical character folded onto the Latin board, so a Cyrillic layout maps to nothing and isn't shown. The toggle row now reads **Enable: Tracking / Mouse / Keyboard / Heatmap / Tooltip** (branch `feat/keyboard-heatmap`).

## [0.1.21] - 2026-07-19

### Changed
- **CONTRIBUTING documents the real test suite and lint.** The guide still said there were no automated tests; it now describes the `pytest` suite in `tests/` (headless via the offscreen Qt platform, so no display is needed) and the `ruff check .` lint that CI enforces on Python 3.10 / 3.12 (by @iderex, #106, branch `docs/contributing-tests-ruff`).

### Fixed
- **Autostart no longer breaks when the install path contains a space.** `launch_command()` returned the `shutil.which("mycat")` path unquoted, and the XDG `.desktop` `Exec=` line word-splits on spaces — so a script under a path like `/home/anna maria/.local/bin/mycat`, or a Windows profile such as `C:\Users\Anna Maria\…` in the Run key, made the entry fail to load and autostart silently did nothing. The path is now always quoted (harmless without spaces), matching the `python -m` fallback (by @iderex, #107, branch `fix/autostart-quote-path`).

## [0.1.20] - 2026-07-13

### Added
- **Optional background removal for self-hosted characters.** Output from a self-hosted a1111 / ComfyUI server is opaque; the *Generate…* dialog's self-hosted section now has a **Keep / Remove** selector that can make a corner-connected, near-uniform background transparent, leaving the character's interior detail untouched (by @ancaferro, #105).

### Changed
- **Cleaner, consistent "myCat" branding.** The system-tray icon is now the full-colour cat (was a monochrome silhouette), and the visible name reads "myCat" everywhere it is shown — the tray tooltip (was "mycat 🐱"), the window title, the update dialog, and the shop window.

### Fixed
- **GitHub private-notification options unlock as soon as a token is present.** The private inbox categories used to enable only after a successful *Test*; a saved, typed, or environment token is now enough to pick them, and a rejected token no longer re-locks them while a token value remains. The status line tells apart verified / not-verified / no-token (by @ancaferro, #104).
- **Activity 🍅 and digest flybys now use the white plane by default, like Reminder.** Before any `[reminder]` was saved they could fall back to a stale pink plane; the announcer now takes its plane look from the Reminder defaults so every banner matches (by @ancaferro, #99).
- **Windows taskbar shows the real myCat icon instead of a 😽 placeholder.** In the frozen exe the icon was loaded from `main.py`'s entry-script path, which drops the `mycat/` prefix, so `icon.png` was never found and the window fell back to a drawn 😽. Bundled assets are now resolved from the package root so the real icon loads; the app also sets an explicit Windows AppUserModelID for correct taskbar identity and grouping.

## [0.1.19] - 2026-07-11

### Fixed
- **The macOS app starts fast now.** It was built as a PyInstaller *onefile* `.app`, which re-extracted its whole ~50 MB archive to a temp dir on every launch (and Gatekeeper rescanned it) — so startup took ~30 s. The macOS build is now *onedir*: the files live in `Contents/` and it starts near-instantly (Windows/Linux stay onefile) (branch `fix/macos-startup-restore`).
- **A cat hidden with Close can be brought back on macOS.** macOS re-launches don't start a second process — LaunchServices just activates the running app — so the "second launch raises the cat" safety net never fired there. The cat now reappears when the app is reactivated (Dock icon / Cmd-Tab), and the tray's toggle shows its correct **Open** / **Close** label (branch `fix/macos-startup-restore`).

## [0.1.18] - 2026-07-11

### Added
- **Choose how AI characters are generated — OpenAI, or a self-hosted Stable Diffusion (AUTOMATIC1111) / ComfyUI server.** The *Generate…* dialog (right-click → *Chars → Generate…*) gained a backend picker and a **txt2img / img2img** toggle: img2img turns your reference photos into the character (identity-preserving on OpenAI), txt2img generates from the prompt alone. For the self-hosted backends you enter the server address and pick a checkpoint from a live model list; OpenAI adds a model choice (`gpt-image-1.5` / `gpt-image-1`). The **prompt and a negative prompt are editable** right in the dialog for every backend (with a **Reset to default** button); since OpenAI's image API has no negative field, its negative is folded into the prompt as a "the image must not contain: …" instruction. Every choice persists in `config.ini`. Everything talks HTTP over the standard library — no new dependency. OpenAI output is transparent; the self-hosted backends render on your own GPU (opaque) (branch `feat/generation-backends`).

### Fixed
- **The macOS app carries its real version now, and refreshes its icon on update.** The `.app` shipped with a `0.0.0` `CFBundleShortVersionString` placeholder that CI never overwrote — so macOS kept the cached (old) app icon across updates and showed `0.0.0` in *About*. CI now stamps the real version into `Info.plist` (Apple Silicon + Intel) after the build (branch `fix/gen-and-macos-version`).

## [0.1.17] - 2026-07-11

### Added
- **Create a custom cat with AI, from your own photos.** Right-click → *Chars → Create custom with AI…*, pick 1–3 reference photos of the same person plus optional visual details (glasses, colours, a bit of lettering), and OpenAI's image model turns them into a chibi cat character saved as an ordinary local char you can reuse or delete. Opt-in and privacy-conscious: no request until you click *Generate and save*, reference photos are resized in memory and never stored, and your OpenAI key can live in the OS keyring (never in the generated pack). No new required dependency — the request uses the standard library (feature by @sts19813, #89).

### Fixed
- **Windows self-update no longer hangs on a black window.** After downloading the new build, the app called `QApplication.quit()` from inside the progress dialog's modal event loop — which doesn't break it, so the process never exited, and the update swapper waited forever for the old PID to vanish (the visible `find "<pid>"` console). The app now hard-exits after launching the swapper, so the swap + relaunch always completes. The swapper also runs with a hidden console (`CREATE_NO_WINDOW`) instead of `DETACHED_PROCESS`, so no black window flashes up or lingers (branch `fix/windows-update-hang`).
- **A truncated update download can no longer install a corrupt build.** `download()` didn't verify the transfer, so a dropped connection silently wrote a half-sized exe that the swapper installed — it then died on launch with "Failed to load Python DLL". The download is now checked against `Content-Length` and retried up to 3× on truncation/network error; a cancel still aborts immediately, and a genuinely failed download surfaces an error instead of swapping in a broken build (branch `fix/windows-update-hang`).
- **The relaunch right after a Windows update no longer fails with "Failed to load Python DLL".** The swapper is a descendant of the old frozen process, so the freshly-swapped exe inherited PyInstaller's onefile bootloader vars (`_MEIPASS2` / `_PYI_*`) and looked for its DLLs in the old, already-deleted `_MEI` dir — the first auto-relaunch crashed, though a manual launch (clean environment) always worked. The swapper now clears those vars and launches the new build with a scrubbed environment, so it extracts fresh (branch `fix/windows-update-hang`).

## [0.1.16] - 2026-07-07

### Fixed
- **"Update…" no longer poses as up-to-date when the check fails.** The version check catches *every* error (offline, or GitHub's unauthenticated API rate-limiting the IP) and used to fall through to "You're on the latest version" — so a failed check looked like good news and real updates were never offered. It now tells apart three outcomes: a reached-and-newer release (offer/notify), reached-and-current ("you're up to date"), and couldn't-reach ("Couldn't check for updates right now — try again in a bit"). (branch `fix/update-check-honest-message`)

## [0.1.15] - 2026-07-07

### Changed
- **Only Windows/macOS self-update; pip / `.deb` / AppImage are just notified.** "Update…" downloads and restarts automatically only on the Windows `.exe` and macOS `.app`. On pip, source, `.deb` and AppImage it now just says an update is available with how to get it (`pip install --upgrade mycat`, `git pull`, or "download the new .deb/AppImage") plus an **Open releases** link. The "you're up to date" message also links to the releases page (branch `fix/windows-update-relaunch`).

### Fixed
- **Windows self-update relaunch (again).** The swap script runs in a detached, console-less process, where `timeout` errors out — so the wait/retry delays never actually happened and the app closed without reopening. It now uses `ping` for the delays (works with no console) and retries the swap up to 30×, with a step-by-step `%TEMP%\mycat-update.log`. Since an update runs the *currently installed* version's code, this takes effect for updates **from 0.1.15 onward** (branch `fix/windows-update-relaunch`).

## [0.1.14] - 2026-07-07

### Added
- **mycat adds itself to the Linux applications menu, always pointing at your newest install.** On launch it installs/updates a user `~/.local/share/applications/mycat.desktop` (with the cat icon referenced by absolute path, so it never shows blank). The entry records its version, so running a newer **git / pip / AppImage** build updates the launcher's command and icon to that one, while an older run never downgrades it — and the `.deb`'s system-wide entry is respected in the comparison (branch `fix/windows-update-and-messages`).

### Fixed
- **The Windows `.exe` and macOS `.app` now carry the cat app icon.** The PyInstaller spec builds a `.ico` (Windows) and `.icns` (macOS) from `mycat/assets/icon.png` at build time and embeds them, so the exe in Explorer/taskbar and the app in Finder/Dock show the cat instead of a generic icon (branch `fix/windows-update-and-messages`).
- **Windows self-update now relaunches instead of just closing.** A onefile exe stays locked by its bootloader for a moment after the app exits, so the single overwrite failed and nothing restarted; the swap batch now retries until the lock clears, then launches (logs to `%TEMP%\mycat-update.log`) (branch `fix/windows-update-and-messages`).
- **Theme-adaptive, transparent tray icon.** The app/window icon is the transparent cat head, and the tray uses a monochrome silhouette that follows the desktop colour scheme — light (`icon-w.png`) on a dark panel, dark (`icon-b.png`) on a light one — so it never vanishes into the background. It's re-asserted after the event loop starts and re-picked when the theme changes (branch `fix/windows-update-and-messages`).
- **Hiding the cat to the tray is always recoverable.** Some Linux panels (e.g. XFCE with only an SNI host — the kind that shows Telegram) don't render Qt's tray icon, so **Close** hid the cat with no way back. A second `mycat` launch now raises the running cat's window (via a per-user local socket) instead of just exiting, so the cat can always be brought back — tray icon or not (branch `fix/windows-update-and-messages`).

### Changed
- **"Update…" from a source/pip install shows the upgrade command.** `git pull` for a git checkout, otherwise `pip install --upgrade mycat` (it previously only offered a releases link) (branch `fix/windows-update-and-messages`).

## [0.1.13] - 2026-07-07

### Changed
- **Tray menu: a single Open/Close toggle, and Quit lives only in the tray.** The cat's right-click "Hide" is renamed **Close** (still tucks it into the tray). The tray entry now flips with state: **Open** when the cat is hidden, **Close** when it's on screen. **Quit** is only in the tray menu now (branch `feat/tray-open-close-menu`).

### Fixed
- **The tray icon is now actually visible.** It used the char's full frame, which shrank to a near-invisible speck at tray size; it now uses the dedicated cat-face app icon (`mycat/assets/icon.png`). The startup log also reports whether the tray was created (`Tray icon shown` / `System tray not available`) (branch `feat/tray-open-close-menu`).
- **Emoji no longer show as tofu boxes where the system has no emoji font.** On a minimal `pip install` (typically Linux without `fonts-noto-color-emoji`), the Activity dialog's 🍅 / ⌨ / 🖱 and other emoji rendered as empty squares. mycat now ships a monochrome NotoEmoji and registers it as a fallback **only when no system emoji font is present** — systems that already have one keep their colour emoji, bare ones get monochrome glyphs instead of boxes (branch `feat/bundled-emoji-fallback`).

## [0.1.12] - 2026-07-06

### Added
- **Prebuilt macOS Intel (x86_64) binary.** The release workflow now also builds `mycat-macos-x64.zip` on GitHub's Intel runner (`macos-15-intel`), alongside the existing Apple Silicon (`-macos-arm64`) and Windows builds, so Intel Macs get a native download (branches `ci/macos-intel-x64`, `fix/intel-runner-macos-15`).
- **Prebuilt Debian package (`.deb`) for Linux.** A new CI workflow wraps the PyInstaller onefile binary in a `mycat-linux-amd64.deb` (installs `/usr/bin/mycat`, a `.desktop` launcher, and a cat-head icon) and attaches it to each GitHub Release. Install with `sudo apt install ./mycat-linux-amd64.deb`; it's self-contained (bundles its own Python + Qt), depending only on common system libs like `libxcb-cursor0` (branch `ci/linux-deb`).
- **Prebuilt Linux AppImage.** A new CI workflow packs the same onefile binary into a portable `mycat-linux-x86_64.AppImage` - a single user-writable file that runs on most distros (needs FUSE) and is the format used for one-click self-updates. Attached to each GitHub Release (branch `ci/versionless-names-appimage`).
- **In-app "Update…".** A new **Update…** entry (right-click and tray menus) checks the latest GitHub release; if there's a newer one it downloads this platform's build over HTTPS and restarts into it. Fully automatic for the AppImage, Windows `.exe` and macOS `.app`; the `.deb` install upgrades via `pkexec apt-get` (one polkit prompt). Running from source/pip it doesn't touch anything - it just says a new version is out and offers to open the releases page (branch `feat/self-update`).

### Changed
- **Release asset filenames are now version-less** (`mycat-windows-x64.exe`, `mycat-macos-arm64.zip`, `mycat-macos-x64.zip`, `mycat-linux-amd64.deb`, `mycat-linux-x86_64.AppImage`), so `https://github.com/yumiaura/myCat/releases/latest/download/<name>` is a stable link that always fetches the current build - used by the README download buttons and the in-app updater (branch `ci/versionless-names-appimage`).
- **README download buttons + a "download | latest" badge.** Replaced the Option A table with per-platform **Download** buttons that link straight to the latest build - Windows, macOS (Apple Silicon), macOS (Intel), Linux `.deb`, Linux AppImage - and added a shields.io latest-release badge at the top of the README (branch `docs/readme-latest-badge`).
- **The cat's "Quit" now hides it to the system tray.** Right-click → **Hide** tucks the cat into the tray instead of quitting; bring it back with a tray double-click or the tray's new **Show**. The real **Quit** stays in the tray menu; where no system tray is available the cat menu keeps a real **Quit** (branch `docs/readme-latest-badge`).

## [0.1.11] - 2026-07-06

### Added
- **Key/click counts now work out of the box on a plain `pip install mycat` - including Linux.** The activity diary counts key presses and mouse clicks; on Windows/macOS that's `pynput`, and on **Linux** it's now a pure-Python `python-xlib` backend (X11 `XRecord`) - so a plain `pip install mycat` gives the counts with **no compiler and no `evdev`**. Only integers are ever kept (the key identity is dropped inside the callback). Off X11 (e.g. Wayland) it degrades to cursor-only. The now-redundant `basic` extra is **removed** - it only re-added `pynput`, and on Linux that dragged in `evdev` (needs a compiler) for no benefit now that counts work by default (branch `feat/linux-counts-and-startup`).
- **Version line + update check at startup.** mycat logs its version on launch, and a background, fail-silent check asks GitHub for the latest release; if a newer one exists it logs `Update available: mycat X (you have Y) - <releases url>`. Nothing is ever downloaded or installed; skipped for source/dev builds (branch `feat/linux-counts-and-startup`).
- **Announcer now logs launches and holds, so a "why didn't my banner show?" is traceable.** A successful flyby take-off used to log nothing, so a queued announcement (GitHub star, digest) that was still waiting behind an on-screen flyby or the pacing gap looked identical in the log to one that flew. It now logs `Flyby launched: … (N still queued)` on take-off and `Announcement held (<reason>): …` while the queue drains (branch `feat/linux-counts-and-startup`).

### Changed
- **Focus mode never suppresses anything - it is not do-not-disturb.** A focus session used to turn on a do-not-disturb hold that queued up GitHub/digest banners until the next break, with "urgent" banners (calendar, rest nudges) allowed to jump ahead. That whole mechanism is **removed**: every announcement is always shown, in FIFO order, and the shared queue now only paces flybys so they don't overlap. No banner is ever held back by a focus run (branch `feat/linux-counts-and-startup`).
- **Activity dialog: "Enable Activity" → "Enable Tracking"; Tracking / Mouse / Keyboard are now three independent toggles.** "Enable Tracking" controls only the cat's **eyes** - on, the pupils follow the cursor; off (or when the cursor is on another monitor) the cat looks at its own nose. **Mouse** and **Keyboard** are the diary count tracks and stay independently clickable (no more greying-out), and turning Tracking off no longer stops recording (branch `feat/linux-counts-and-startup`).
- **Reminder dialog now shows how long is left, and Save/Reset behave predictably.** Reopening the reminder no longer looks "reset": the status line shows a short `Reminder in 10 min. (14:32)` for the pending reminder (the saved settings were always kept - now it's visible and ticks down). **Save** shows that same line immediately (no "Saved…" flashing then swapping to a countdown a few seconds later). **Reset** fully clears the schedule and restores the form to defaults, including the message text (`Do you feed mycat?`) (branch `feat/linux-counts-and-startup`).

### Fixed
- **All four reminder planes now ship in the exe/.app, not just the pip wheel.** The four selectable plane sprites (`plane1`–`plane4`) are tracked in git and already bundled in `pip install mycat` via package-data, but the PyInstaller spec only copied the single legacy `plane.png` - so the prebuilt Windows/macOS builds had an empty plane picker. The spec now bundles `mycat/assets/planes/*.png` too (branch `feat/linux-counts-and-startup`).

## [0.1.10] - 2026-07-06

### Fixed
- **`pip install mycat` no longer fails to build on Linux.** 0.1.9 made `pynput` a hard dependency to turn on the key/click counts, but on Linux `pynput` pulls `evdev` - a C extension with no wheel - so the install died compiling it on machines without a compiler and Python headers (`fatal error: Python.h`). `pynput` is now a base dependency only on **Windows/macOS**, where it installs cleanly and the counts work out of the box (including the prebuilt exe). On **Linux** it is opt-in: `pip install mycat[basic]`.

### Changed
- **Docs.** Moved the "make your own cat" guide out of README into a step-by-step Quick start in `docs/CHARS.md`; README now links to it and stays focused on install options and CLI keys (branch `docs/chars-guide`).

## [0.1.9] - 2026-07-06

### Changed
- **New defaults for fresh installs.** The reminder plane now defaults to **white** (was pink), the default reminder message is **"Do you feed mycat?"** (was "Reminder!"), and the Activity **Enable Tooltip** toggle starts **off** (was on). Existing configs keep whatever they already saved (branch `feat/default-tweaks`).

### Fixed
- **Keyboard and mouse-click counts now work on `pip install` and the prebuilt exe.** The Activity diary counts key presses and clicks via `pynput`, but it was an *optional* extra (`mycat[basic]`) - so a plain `pip install mycat` and the bundled Windows/macOS executables shipped without it, and the counts silently stayed at zero (only the cursor path was recorded). `pynput` is now a base dependency, so the counts work out of the box; the PyInstaller `pynput` hook bundles the platform backend into the exe. It still degrades to cursor-only where global hooks can't run - Wayland, or macOS without Input Monitoring permission (branch `chore/release-0.1.9`).

## [0.1.8] - 2026-07-06

### Added
- **Reset - recenter the cat.** Right-click (and the system-tray menu) now have a **Reset** entry, placed just above **Autostart**, that moves the cat back to the bottom-right of the primary screen - a rescue for when it wanders off-screen or gets lost across multiple monitors. Restores the position-reset action originally added in #52 that was dropped during the 0.1.7 companion rework (branch `feat/reset-position`).

### Changed
- **The cat now blinks in the plane cockpit and sits deeper in it.** On the banner flyby (plane1) the cat is sunk further into the fuselage so only the top of the head peeks out instead of the whole head sticking up, and its eyes blink on a slow cycle using the char's closed-eyes frame (the same frames the demo GIF uses) - GIF chars with no blink frame just stay awake. Tuning: `CAT_SINK_FRAC`, `BLINK_PERIOD_S`, `BLINK_DUR_S` in `reminder_ui.py` (branch `feat/flyby-cat-sink-blink`).

### Fixed
- **The prebuilt Windows/macOS executables now actually launch.** The frozen build crashed at startup with `ModuleNotFoundError: No module named 'mycat.llm'`: the exe entry runs as `__main__`, so `main.py` pulls its submodules in dynamically (`importlib.import_module("mycat.llm")`), which PyInstaller's static analysis never bundled. The spec now bundles the whole `mycat` package via `collect_submodules('mycat')` (with the source tree added to `sys.path` so it works whether or not the package is pip-installed). It also fixes bundled chars: the folder was renamed `images/` → `chars/`, but the spec still shipped `mycat/images/`, so the exe launched with no cats - it now bundles `mycat/chars/` (both names supported for older tags). Verified with a real PyInstaller build (branch `fix/frozen-exe-imports`).

## [0.1.7] - 2026-07-02

### Added
- **Activity timeline in the Activity dialog.** A per-minute heat strip of the day: grey where nothing was tracked, green where you were at rest, and red - deeper the busier - where you were active, so the work→rest→next-period rhythm is visible at a glance (hover for the time). The strip always spans the **full day** (midnight→midnight); past-but-untracked minutes are white, the still-to-come future is grey, and a prominent blue "now" marker (a line with a triangle) shows how far along we are. The live current row shows the **elapsed time** of the period in its Duration cell. The live **Current row is labelled by phase** - ▶ Focus / ▶ Rest / ▶ Big break during a pomodoro, or ▶ Active (no timer) when you're active with no timer running (dropping the earlier Work/Working overlap). The dialog is larger and the checkboxes now read "Track my activity" / "…count keys + clicks too" with the detail in tooltips (branch `feat/companion`).
- **Automatic focus - earn a 🍅 from your activity, no timer or button.** The cat watches your input: a continuous stretch of work (pauses under 5 min are merged) that reaches **25 minutes earns one 🍅**, and a banner flies - "🍅 earned - time to rest" (it re-fires every 25 min of unbroken work, but the stretch still counts as a single 🍅). A stretch that ended before 25 min is a **🍌**; anything under 5 min isn't a session. The cat's hover tooltip tracks the live run ("Focus · 12:34 · 🍅 2 · ⌨ keys · 🖱 clicks / path · % active"); do-not-disturb holds non-urgent banners while you work and releases them when you rest. Thresholds live in `[focus] focus_minutes` / `min_banana_minutes` (branch `feat/companion`).
- **Morning digest.** The first time the cat sees you after 05:00 it flies yesterday's numbers past: "Yesterday: 🖱 2.1 km · ⌨ 13,402 · 🍅 6 · best focus 52 min". Delivered once per day (the date is remembered across restarts), silently skipped when yesterday has no story, and queued politely behind an early focus session (branch `feat/companion`).
- **Activity diary (local-only).** Right-click → Activity…: the cat keeps a private log of your day - cursor distance (10 Hz `QCursor` polling, no hooks or permissions) and keystroke/click *counts* via pynput - the key identity is discarded inside the hook, only integers are stored. Minute buckets live in `activity.db` next to the focus sessions; nothing ever leaves the computer. The dialog shows an honest interval log correlated with pomodoro ("09:05–09:30 🍅 at the computer throughout ✓", "09:30–09:35 ☕ rested properly - away from the computer ✓", "14:00–15:30 💻 at the computer outside pomodoro") plus day totals (cursor km via screen DPI, keys, 🍅, best focus). Configurable retention (90 days default), a delete-everything button, and an off switch (branch `feat/companion`).
- **Calendar reminders (opt-in).** Right-click → Calendar…: paste the secret ICS URL (Google's "Secret address in iCal format", Apple/Outlook private links, `webcal://` accepted) and the cat announces events ~10 min ahead (configurable). Recurring events are expanded properly (new optional extra `mycat[calendar]`: `icalendar` + `recurring-ical-events`); all-day events are skipped. Calendar banners are the only ones urgent enough to fly through an active focus session. Zero network requests until enabled; the URL is treated as a secret in the owner-only config (branch `feat/companion`).
- **GitHub notifications (opt-in), per-category.** Right-click → GitHub…: pick with checkboxes exactly which GitHub things ping the cat, split into two groups. **Public** (needs only your username, no token): *Star on my repo*, *Fork of my repo*, *New follower*, *My stars & follows* - double-click a banner to open it. **Inbox** (needs a token): *Mentions*, *Assigned to me*, *Review requested*, *CI status*, *Issue activity*, *PR activity*; these checkboxes stay greyed out until you paste a token and press **Test**, which verifies it, auto-fills your username from `/user`, and unlocks them. The token field is optional and sits below the account fields (empty → `$GITHUB_TOKEN`). Behind the scenes three independent sources are polled on their own cadences and merged: the private `/notifications` inbox (filtered by `reason` + `subject.type`), each account's public `events/public` (your own stars/follows, plus any *other* accounts you "also follow"), and a new **inbound poller** - per-repo `/repos/{owner}/{repo}/events` + a `/users/{me}/followers` diff - because stars/forks/follows on *your* stuff appear in neither the inbox nor the events feed. Conditional requests (ETag/`If-Modified-Since`, a free 304) keep the anonymous 60 req/h budget happy, the inbound poller is capped and paced (8 repos / 30 min tokenless, more with a token) with 403 rate-limit backoff, every source baselines silently on startup, and zero network requests happen until enabled. The client talks to `api.github.com` directly (no mycat server involved); legacy `reasons`/`username` config keys are migrated (branch `feat/companion`).
- **Announcement queue.** All companion features (focus sessions, GitHub notifications, calendar reminders, the morning digest) deliver banners through one `Announcer`: a single flyby at a time with a pacing gap, do-not-disturb hold during focus sessions (urgent items break through), and an optional link on a banner opened by double-click or the flyby's context menu (branch `feat/companion`).
- **First-run prompt to start on login.** On the first launch (where autostart is supported and not already on), mycat asks once whether to start every login - the autostart toggle was otherwise buried in the right-click menu. The answer is remembered in `[settings] autostart_prompted` so it is never asked twice (branch `feat/persistence-hardening`).
- **Single-instance guard.** A second launch no longer spawns a second cat - it detects the running instance via a `QLockFile` and exits (a lock left by a crashed instance is reclaimed automatically) (branch `feat/persistence-hardening`).
- **Live-cat demo (dev prototype).** `demo/live_cat_demo.py` - a standalone prototype of roadmap vertical B ("the cat feels alive"): the existing sprite is animated purely with code (breathing, blink, play hops, sleep, stress jitter) and system load is shown as the cat's *mood* rather than a number. Not wired into the shipped app; run with `python demo/live_cat_demo.py` (branch `demo/live-cat-prototype`).
- **Multiple chat vendors.** The LLM settings dialog (right-click → LLM…) now lets you pick a vendor - Ollama (default, local), OpenAI, Grok (xAI), Groq, DeepSeek, OpenRouter - or define a **custom** OpenAI-compatible endpoint (name + base URL + key + model). One adapter covers every OpenAI-compatible provider. API keys are hybrid: typed into the dialog (saved to config) or read from the vendor's environment variable.
- **`classic` char.** The pre-char-pack GIF cat stays bundled as `chars/classic.zip` - pick "classic" in the Chars menu to get the old look back; the interactive eyes-tracking `cat` is the default (branch `feat/companion`).
- **Interactive char packs.** A char is a folder or `.zip` with `static`/`blink` frames, L/R pupil sprites, optional body GIFs, and a `config.json`. The cat tracks the cursor with synchronous pupils, blinks, reacts to clicks, and runs an asset-gated state machine (idle / yawn / sleep / hungry-on-low-battery) - each behaviour active only if its assets exist. Fits a `max_width`×`max_height` box; crisp edges on X11 without a compositor. Bundled `cat` char; format spec in `docs/CHARS.md`.

### Changed
- **Settings dialogs keep open on Save and say what they saved.** Pressing Save persists and applies without closing the window in *every* dialog (the Reminder and LLM dialogs still closed on Save) and the status line now reports exactly what was stored - e.g. GitHub: "Saved (on): yumiaura · 4 public + 0 inbox options · no token.", Reminder: 'Saved: "drink water" · in 20 min · pink plane.', Activity: "Saved: activity on · mouse ✓ · keyboard ✓, keep 90 days." Close is the only button that dismisses a dialog (branch `feat/companion`).
- **GitHub defaults are public-first.** A fresh setup checks all four **Public options** (they need only your username) and leaves the token-only **Private options** unchecked and greyed until a token is verified - previously the private review/mention/assign boxes were checked-but-greyed with no token, which read as "on without a token". Group titles are now "Public options" / "Private options (token required)" (branch `feat/companion`).
- **The Activity dialog is a compact activity-run table.** Each row is a work stretch: the **Session** column merges the icon and start time (🍅 earned / 🍌 fell short / ▶ the live current run), then **Duration** (`M:SS`, or `H:MM:SS` past an hour), **⌨ Keys**, a combined **🖱 / ⤳** cell (clicks / cursor path, like the tooltip), and **Active %**. Columns are even width; the keyboard/mouse glyphs are monochrome and the cursor path is a `⤳` symbol. The **TOTAL** is a pinned, borderless row under the table - always visible, aligned to the columns - showing earned 🍅, total active time, keys, clicks / metres, and the overall active %. The status line above the table reads **"Current: …"** (branch `feat/companion`).
- **Save-status polish** across the settings dialogs: the Calendar "Saved …" line is now green like the others, the Reminder dialog's status sits above its buttons, and the Activity dialog's Save/Export feedback has its own line above the buttons. The Activity delete button is shortened to "Delete all…" (branch `feat/companion`).
- Menu entries reordered in both the context and tray menus: **LLM, Calendar, Reminder, GitHub, Activity**, then the focus action (branch `feat/companion`).
- **The activity diary is now on by default** (was opt-in with a first-run prompt; the prompt is gone). The guarantees are unchanged - counters never content, everything local, retention limit, delete-everything button - and it can still be switched off in right-click → Activity…. Where global hooks can't work (Wayland, missing macOS permission, or the extra not installed) the collector degrades to cursor-distance-only (branch `feat/companion`).
- **Keystroke/click counting is now an optional extra, `mycat[basic]`** (`pynput`). The base install already records cursor path; installing the extra adds the key/click *counts*. When `pynput` is absent the diary degrades cleanly to cursor-only and the Activity dialog shows a one-line hint pointing at `pip install mycat[basic]` (branch `feat/companion`).
- **Toggle the cat's hover tooltip.** A fourth "Enable Tooltip" checkbox in the Activity dialog turns the live focus/activity tooltip (shown when you hover the cat) on or off - saved to `[focus] tooltip_enabled`, applied immediately. Off clears the tooltip so hovering shows nothing. Delete-all moved down beside Export CSV to make room (branch `feat/companion`).
- **Set the Pomodoro goal from the Activity dialog.** A new "Pomodoro goal" minutes selector (default 25) sets how long a run must last to earn a 🍅 - saved to `[focus] focus_minutes`, applied live, and the table re-grades against it on Save. The day-picker row is retidied: **Show** comes first, then **History** (renamed from "Keep history for") and the goal (branch `feat/companion`).
- **Click and key counting switch independently.** The single "Enable Activity" toggle now has two nested sub-toggles - **Enable Mouse** (click count) and **Enable Keyboard** (key count) - greyed out while Activity is off, each starting/stopping its own hook. The tier-1 cursor path always records while Activity is on (the cat's eyes track the cursor regardless), so only the two *counts* are switchable (branch `feat/companion`).
- mycat now **lives in the system tray**: closing or hiding its windows no longer quits the app - only the explicit Quit action does (when a tray is available, so the user is never left with an invisible process). Keeps the cat persistent across the session (branch `feat/persistence-hardening`).
- Renamed "skin" → "char" across the UI, code, docs, and shop wire-contract; the bundled directory moved `images/` → `chars/`.
- The reminder settings dialog is now **non-modal**, so the flyby launched by its **Test** button can be grabbed and dragged while the dialog stays open (a modal dialog grabbed all input, leaving the test plane unclickable). Reopening while already open just raises the existing dialog (branch `fix/reminder-dialog-nonmodal`).
- The OpenAI/cloud backend is now a dependency-free `urllib` client (no `openai` package required) that supports any `base_url`.
- Renamed the "Start on login" item to "Autostart" in the context and tray menus (branch `chore/autostart-label`).
- Skins are now decoded straight from the packaged ZIP bytes into an in-memory `QBuffer`-backed `QMovie`; nothing is written to `/tmp/mycat` anymore (branch `feat/in-memory-skins`). The animation restart and skin-switch paths recreate the movie from the held GIF bytes, so no temp files are touched at any point.

### Fixed
- **Recorded activity could be lost across restarts.** The database ran in WAL mode and its data lived in a side journal that was never checkpointed into the main file, so an abrupt exit could drop whole sessions. It now uses a durable rollback journal with `synchronous=FULL` (every commit lands in the `.db` file immediately), and the current minute is flushed on a clean Quit.
- **The Activity totals didn't add up.** The table now lists the day's periods with exactly three labels - **Focus**, **Break**, **Other** (activity without a running timer, shown as individual periods rather than a confusing lump) - and the **TOTAL row is the sum of the rows above** by construction, so it always reconciles.
- **The live "current period" reset when the app was closed and reopened.** It was computed from in-memory state (a run start that began as empty on each launch), so a restart lost the accumulated period stats. It is now reconstructed from the recorded minutes in the database, so closing and reopening continues the same period (branch `feat/companion`).

### Removed
- **The manual pomodoro.** The "Focus 25 min" / "Stop focus" / "Skip break" menu actions (context menu and tray), the progress bar under the cat, and the fixed break countdowns are gone - focus is now derived automatically from activity (see *Automatic focus* above). The `focus_session` table is no longer written; 🍅/🍌 are computed from the recorded activity runs (branch `feat/companion`).
- `/tmp/mycat` temp-file extraction and the `TEMP_DIR` / `STATIC_PNG_PATH` / `ANIMATION_GIF_PATH` globals plus `get_temp_dir()` (branch `feat/in-memory-skins`).

## 0.1.6

### Added
- **Reminder** - a cat-on-a-plane banner that flies across the top of the screen at a chosen time (one-shot or daily). Configure it via right-click → Reminder….
- **Ollama settings menu** (right-click → Ollama…) - set host/port, fetch and pick a model, run a timed connection test, and enable/save the backend live (no file editing or restart). The LLM-enabled state now persists across restarts.
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
