# CLAUDE.md — notes for AI coding assistants

This file is the technical brief for an AI assistant working in this repository.
`AGENTS.md` and `GEMINI.md` point here. Humans looking for the contributor guide
(including "make your own skin") want [CONTRIBUTING.md](CONTRIBUTING.md).

## Project overview

`mycat` is a desktop pet: a frameless, always-on-top, draggable PySide6 window
showing an animated character, plus a set of opt-in companions that speak through
that character — reminders, a private activity diary, focus, GitHub notifications,
ICS calendar reminders and an LLM chat.

- Published on PyPI as `mycat`; console entry point `mycat.main:main`.
- Requires Python ≥ 3.10. Hard dependencies are only PySide6 and Pillow (plus a
  key/click counter: `pynput` off Linux, `python-xlib` on Linux).
- Prebuilt Windows/macOS binaries and a `.deb`/AppImage are built by the workflows
  in `.github/workflows/`.

## Commands

```bash
pip install -e .                   # extras: [calendar] (ICS), [secure] (OS keyring)

mycat                              # console script
python -m mycat                    # module entry (__main__.py)
python mycat/main.py               # direct script — a path shim keeps this working
./run.sh                           # Linux/macOS launcher, passes flags through

ruff check .                       # lint (line-length 120; rules C4,E,F,I,PERF,UP)
ruff format .

QT_QPA_PLATFORM=offscreen python -m pytest -q --forked --timeout=60 --timeout-method=thread
```

CLI flags: `-i/--image <zip>`, `--wait <seconds>`, `--pos X Y`, `--debug`, and the
mutually exclusive `--openai` / `--ollama` for chat.

### Tests

`tests/` holds ~35 pytest files and CI (`.github/workflows/ci.yml`, Python 3.10 and
3.12) runs ruff plus the pytest line above. Two rules make the suite survivable:

- **Never create a `QApplication` outside the `qapp` fixture in `tests/conftest.py`
  or `main()`.** Qt's offscreen platform corrupts sibling tests otherwise.
- **Keep `--forked` and `--timeout-method=thread`.** Each test runs in its own
  process; the thread timeout is what bounds a hang under `--forked`.

## Architecture

### Window and chars

- `main.py` — Qt bootstrap, CLI parsing, the GIF/char pipeline, `PixelCatWindow`
  (drag, context menu, char switching, position persistence) and the tray icon.
  It is the big file; most features are attached to the window from their own module.
- `char_pack.py` / `char_catalog.py` — a char is a `.zip` (or folder) read fully in
  memory, discovered in the bundled `mycat/chars/` and in the per-user chars dir.
  Two formats coexist: a legacy single animated GIF (first frame = idle pose) and
  the interactive pack with `config.json` (static/blink frames, pupils, anims).
  The format is documented in [docs/CHARS.md](docs/CHARS.md).
- `speech_bubble.py`, `reminder_ui.py` — the two ways the cat says something: a
  comic bubble above its head, or the flyby plane banner.
- `ui_theme.py` — one light theme shared by every dialog.

### Companions

- `announcer.py` — the single FIFO queue every companion announces through. It
  paces messages; it does not rank, delay or suppress them.
- `activity.py` / `activity_store.py` / `activity_ui.py` — the local activity diary:
  cursor distance and key/click **counts** (the key identity is discarded in the
  hook), stored per minute in SQLite. `key_heatmap*.py` draws the optional keyboard
  heatmap, `digest.py` the once-a-day summary, `focus.py` the automatic focus
  sessions earned from activity.
- `github_notify.py` + `github_api.py` + `github_ui.py`, `calendar_ics.py` +
  `calendar_ui.py`, `reminder.py` — opt-in notification sources.
- `llm*.py` — chat. `llm_vendors.py` is the vendor registry (built-in presets plus
  user-defined ones), `llm_openai_compat.py` and `llm_ollama.py` are the backends,
  both written on stdlib `urllib` — there is no third-party API client to install.
- `update_check.py` / `updater.py` — startup version banner and the in-app
  self-update of the prebuilt binaries.
- `shop_api.py` / `shop_ui.py` — the char shop client. **Unfinished and switched
  off**: the menu entry is commented out in `main.py`, so nothing calls it. Don't
  wire it up as a side effect of another change.

### Configuration and private data

- `paths.py` is the single source of truth: `config.ini` lives in
  `~/.config/mycat/` on *every* platform (existing installs depend on it).
- Data uses per-OS conventions instead: `activity_store.user_data_dir()` and
  `char_catalog.user_chars_dir()` → `%LOCALAPPDATA%\mycat`, `~/Library/Application
  Support/mycat`, `$XDG_DATA_HOME/mycat`.
- Read and write config sections through `config_store.py`, and call
  `secret_store.secure_file()` on anything private you create — `config.ini` can
  hold an API key, and `activity.db` holds the diary. `secret_store` also wraps the
  optional OS keyring, degrading to plaintext config when no backend exists.
- `.env` (project root or cwd) is loaded once per process by `llm_prompt.py`;
  `MYCAT_ENV_FILE` overrides the path. Precedence for LLM settings:
  `config.ini` > env vars > defaults.

### Interface languages

`i18n.py` scans `mycat/locale/*.json` at startup — English, Русский, 简体中文,
한국어 today. Every user-facing string goes through `i18n.tr("English source
text")`, and the English text is the catalogue key, so it must match the JSON
exactly. Don't build a message by concatenating a translated fragment with data;
translate the whole sentence with its `{placeholder}` and `.format()` it. A new
language is a new JSON file and no code change.

## Conventions

- Text I/O names its encoding (`encoding="utf-8"`); config values are free text in
  any of the four languages.
- Logging: module-level `logger = logging.getLogger(__name__)`; `main.py`
  configures the root logger at INFO and `--debug` raises it.
- `main.py` starts with a path shim so it runs both as a script and as a package
  module — preserve it when touching imports.
- `[tool.mypy] strict = true` exists in `pyproject.toml`, but no CI step runs mypy.
- Releasing is tag-driven: bump `version` in `pyproject.toml`, push a `*.*.*` tag,
  and `publish.yml` ships to PyPI while `release-binaries.yml` builds the binaries.
  Keep `CHANGELOG.md` current in the same change.
- Artwork: only characters drawn by the person contributing them can be added to
  `mycat/chars/`. See the licensing note in [CONTRIBUTING.md](CONTRIBUTING.md).
