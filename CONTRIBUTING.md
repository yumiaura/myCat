# myCat — for contributors 🐱

Hi — and thank you for being here. myCat is a tiny desktop pet, and its little
characters (the "skins") are the whole point of it. This is a short, friendly
guide for anyone who'd like to add one or help out.

## 🎨 Make your own skin (step by step)

Good news: a skin is tiny. Under the hood it's just **one animated GIF inside a
`.zip`** — no JSON, no code, nothing to compile.

### 1. How a skin works

- The **ZIP's filename is the name shown in the menu** — `redcat.zip` appears as
  **redcat**.
- Inside the ZIP there's a single animated **`.gif`**.
- The GIF's **first frame is the resting pose** myCat shows while idle (for about
  5 seconds, or `--wait` seconds). Then the GIF plays through once and settles
  back on that first frame.
- Keep it within **300×500 px** — anything larger is scaled down automatically
  (the aspect ratio is preserved).
- Use a **transparent background**, so the cat sits on your desktop instead of
  inside a box.

### 2. Draw your frames

Draw your character as a few frames of animation — PNGs with a transparent
background work best. Frame 1 is the calm idle pose; the rest are the little
animation that plays now and then (a blink, a stretch, a wave… up to you).

### 3. Build the animated GIF

Any tool that exports an animated GIF works — GIMP, Aseprite, [ezgif.com](https://ezgif.com),
or ImageMagick from the terminal:

```bash
# From separate frames (frame1 = the idle pose):
convert -delay 12 -loop 0 frame1.png frame2.png frame3.png redcat.gif

# …or from a 2-frame sprite sheet (left half = idle, right half = action):
convert sheet.png -crop 50%x100% +repage -set delay '200,100' -loop 0 redcat.gif
```

`-delay` is in hundredths of a second per frame; `-loop 0` is fine — myCat
handles the "play once, then rest" behaviour itself.

### 4. Package it as a ZIP

The zip's name becomes the menu name, so name it nicely:

```bash
zip redcat.zip redcat.gif
```

### 5. Try it right away

- **Launch with it:** `mycat --image /path/to/redcat.zip`
- **Install it for keeps:** drop `redcat.zip` into your personal chars folder and
  it shows up in the right-click **Chars** menu instantly — no restart:
  - **Linux:** `~/.local/share/mycat/chars/` (or `$XDG_DATA_HOME/mycat/chars/`)
  - **macOS:** `~/Library/Application Support/mycat/chars/`
  - **Windows:** `%LOCALAPPDATA%\mycat\chars\`

### 6. Share it with everyone (optional)

Want it bundled with myCat for everyone? Put `redcat.zip` into `mycat/chars/`
and open a pull request. ⚠️ Please only share art **you drew yourself** — see
**Artwork & licensing** below.

### If something looks off

- **A black box around the cat** → the GIF needs a transparent background. (On
  Linux/X11 a compositor helps; without one, myCat clips the window to the cat's
  outline.)
- **It doesn't move** → make sure it's a real multi-frame animated GIF, not a
  single still image.
- **It's huge** → that's fine, it gets scaled down to fit 300×500.

### ✅ Quick recap

1. Draw your frames — **first frame = idle pose**, transparent background, ≤300×500.
2. Export them as one **animated GIF**.
3. `zip myname.zip myname.gif` — the **zip name is the menu name**.
4. Test it: `mycat --image myname.zip`, or drop the zip in your chars folder.
5. To contribute it: put it in `mycat/chars/` and open a PR — **only your own art.**

## 🐞 Hit a problem? Open an Issue

If something doesn't work, or you have an idea:
- Check existing [Issues](../../issues) to see if it's already being discussed.
- If not, open a new issue using our issue templates:
  - 🐛 **Bug Report**
  - 💡 **Feature Request**
  - 🎨 **Skin / Character Submission**
- Include your OS, installation method, steps to reproduce, and terminal logs (run with `--debug`).

## 🛠 Local Development Setup

### 1. Prerequisites
- **Python 3.10+**
- Git
- On Linux, Qt offscreen/X11 needs system libraries:
  ```bash
  sudo apt-get install -y libegl1 libgl1 libxkbcommon0 libdbus-1-3
  ```

### 2. Fork & Clone
```bash
# Fork the repository on GitHub, then clone your fork:
git clone https://github.com/<your-username>/myCatop.git
cd myCatop

# Add upstream remote
git remote add upstream https://github.com/sushantguri/myCatop.git
```

### 3. Virtual Environment & Dependencies
```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate

# Install in editable mode with development extras
pip install --upgrade pip
pip install -e ".[calendar,secure]"
pip install ruff pytest pytest-forked pytest-timeout pre-commit

# (Optional) Install pre-commit git hooks
pre-commit install
```

### 4. Running the App
```bash
./run.sh                  # On macOS / Linux
# or:
python -m mycat
```

### 5. Code Quality & Testing
Before committing or opening a PR, ensure code formatting and tests pass:

```bash
# Format and lint
ruff format .
ruff check .

# Run test suite
QT_QPA_PLATFORM=offscreen python -m pytest -q --forked --timeout=60 --timeout-method=thread
```

> **Why `--forked`?** Qt's offscreen platform can be unstable when many tests share a single process. Each test runs in its own process, and `--timeout-method=thread` bounds hangs.

If you work with an AI assistant, notes about this codebase live in [CLAUDE.md](CLAUDE.md).

## 🔀 Branching & Pull Requests

1. **Create a branch** for your work:
   ```bash
   git checkout -b feature/my-cool-feature
   # or: git checkout -b fix/window-drag-issue
   ```
2. **Make your changes** cleanly with descriptive commit messages.
3. **Run linter and tests** to ensure no regressions.
4. **Push to your fork** and open a Pull Request against `main`.
5. Fill out the **Pull Request Template** describing what changed and why.

## 💛 About artwork & licensing

I'm genuinely happy every single time someone shares an animation — thank you!

Because of licensing and repository size, **we can only accept artwork that you drew yourself.** If a character wasn't made by you personally, we won't be able to merge it — not because it isn't lovely, but because we must respect original artists' copyright.

All code and skins in this repository are licensed under the terms in [LICENSE](LICENSE).

## 🤝 Code of Conduct

We are committed to providing a friendly, safe, and welcoming environment for all. Please review our [Code of Conduct](CODE_OF_CONDUCT.md) before participating.

## 🔒 Security

To report sensitive security vulnerabilities, please refer to our [Security Policy](SECURITY.md) and report via GitHub Security Advisories.

Thank you for contributing to myCat! 🐾
