EN | [RU](https://github.com/yumiaura/myCat/blob/main/docs/README_RU.md) | [CN](https://github.com/yumiaura/myCat/blob/main/docs/README_CN.md) | [ID](https://github.com/yumiaura/myCat/blob/main/docs/README_ID.md)

## Desktop Cat: QT Overlay 🐱

[<img src="https://raw.githubusercontent.com/yumiaura/myCat/refs/heads/main/docs/cat.gif" width="164" alt="cat.gif"/>](https://github.com/yumiaura)

<p class="badges">
  <img src="https://img.shields.io/pypi/pyversions/mycat?color=brightgreen" alt="Python Versions">
  <a href="https://pypi.org/project/mycat/"><img src="https://img.shields.io/pypi/v/mycat?color=brightgreen" alt="PyPI Version"></a>
  <a href="https://pypi.org/project/mycat/"><img src="https://img.shields.io/pepy/dt/mycat?label=pypi%20%7C%20downloads&color=brightgreen" alt="Pepy Total Downloads"/></a>
</p>

I made a cute little animated cat 🐈 for your desktop.<br>
It's a lightweight Python + Qt app — no borders, and you can drag it around easily.<br>
Shows static first frame for 5 seconds, then plays GIF animation once, then loops back to static.<br>
If you like it, maybe I'll share an [AnimeGirl](https://github.com/yumiaura/mycat/discussions/1) version next time~ 😉<br>

<img width="640" height="360" alt="image" src="https://github.com/user-attachments/assets/332494c9-8e39-4774-a85c-808839229106" />

### LLM Chat, Reminders, GitHub Integration & Tracking Activity
<img width="280" height="200" alt="image" src="https://github.com/user-attachments/assets/9554bd7d-f06b-4acb-abb1-9c525103ac42" />
<img width="280" height="200" alt="image" src="https://github.com/user-attachments/assets/022d5d14-fa75-4940-bbaa-ea6cd2a72a77" />
<br />
<img width="280" height="200" alt="image" src="https://github.com/user-attachments/assets/0a1d078e-77f4-4f16-a09f-a94c5deff086" />
<img width="280" height="200" alt="image" src="https://github.com/user-attachments/assets/d9f4cce9-bf3c-4d64-a28e-1cac7d050a8c" />



## 🚀 Quick start

Pick whichever is easiest — the cat runs on **Windows, macOS and Linux**.

### Option A — prebuilt binary (no Python needed)

Download the build for your OS from the **[latest release](https://github.com/yumiaura/myCat/releases/latest)**, then run it:

| OS | File | How to run |
| --- | --- | --- |
| **Windows** | `mycat-<version>-windows-x64.exe` | double-click it |
| **macOS** | `mycat-<version>-macos-arm64.zip` | unzip, then open `mycat.app` |

> Builds for every release live on the **[Releases](https://github.com/yumiaura/myCat/releases)** page.

### Option B — pip (Windows / macOS / Linux, Python ≥ 3.10)

```bash
pip install mycat
mycat
```

On **Linux** also install the Qt platform plugin once:

```bash
sudo apt install -y libxcb-cursor0
```

The activity diary can **count** key presses and clicks (never *which* keys) —
it works out of the box on Windows, macOS and Linux/X11. Where global input
access isn't available (e.g. Wayland) it degrades to recording the cursor path.

Upgrade or remove later with `pip install -U mycat` / `pip uninstall mycat`.

### Option C — from source

```bash
git clone https://github.com/yumiaura/myCat
cd myCat
pip install .
mycat                 # or, without installing:  python3 mycat/main.py
```

## ✨ Features

- **Animated overlay** 🐱 — a frameless, always-on-top, draggable cat. Right-click for the menu (switch char, quit).
- **Reminder** 🛩️ — set a message and a time (one-shot or daily) and the cat flies a little banner plane across the top of your screen. Right-click → *Reminder…* to set the message, direction, plane and color.
- **Chat (Ollama)** 💬 — talk to the cat through a **local [Ollama](https://ollama.com) model**, no account or API key needed (see below).

## 💬 Chat with the cat (Ollama)

The cat can chat using a model served locally by [Ollama](https://ollama.com) — everything stays on your machine, no API key required.

1. Install [Ollama](https://ollama.com) and pull a model:
   ```bash
   ollama pull llama3.1
   ```
2. Launch **mycat**, then right-click the cat → **Ollama…**
3. Set the host/port (default `localhost:11434`), click **Load models**, pick one, hit **Test**, then **Save** and tick **LLM enabled**.
4. Right-click → **Chat** to start talking. 🐾

## 🎮 Usage & options

Run `mycat` (or `python3 mycat/main.py` from source) and customise it with command-line options.

**`--image, -i <path>`** 🖼️ — use a custom ZIP archive (containing one GIF) instead of the default cat:

```bash
mycat --image ~/my-custom-cat.zip
```

A char **ZIP** must contain exactly one `.gif`: its first frame is the static pose, then the GIF plays once and returns to that frame. Images larger than 300×500 are scaled down automatically.

**`--pos <x> <y>`** 📍 — start at a specific screen position (otherwise the cat appears bottom-right and remembers where you last dragged it):

```bash
mycat --pos 960 540        # center of a 1920x1080 screen
```

**`--wait <seconds>`** ⏱️ — how long to hold the static first frame before the animation plays.

**`--debug`** 🐞 — verbose per-frame logging.

### Controls

- **Left-drag** the cat to move it.
- **Right-click** the cat for the menu (Chars, Reminder…, Ollama…, Chat, Quit).
- **Quit** from the menu or with Ctrl+C in the terminal.

The cat remembers its position and selected char between sessions in `~/.config/mycat/config.ini`.

## 🎬 Make your own cat

A char is just an animated GIF in a `.zip` — from a quick doodle to a fully
interactive cat with cursor-tracking eyes, blinking, sleeping and click
reactions. Step-by-step guide (draw it, build the GIF, package, install & share):
**[docs/CHARS.md](docs/CHARS.md)**.

## 🐳 Docker

Run the cat in a container with GUI forwarding to your host's X server.

**Prerequisites:** Docker, and an X server on the host (Xorg on Linux, VcXsrv on Windows, XQuartz on macOS).

```bash
# Linux
xhost +local:docker
docker compose up --build

# Windows (VcXsrv running, network clients allowed)
docker compose -f docker-compose.windows.yml up

# macOS (XQuartz running, network clients allowed)
docker compose -f docker-compose.mac.yml up
```

## 🔧 Troubleshooting

**Cat appears in a black box / transparency doesn't work** 🫥
- On X11 transparency needs a compositor. mycat falls back to clipping the window to the cat's outline when none is running, so this is rare; if you still see a box, enable display compositing (XFCE: *Window Manager Tweaks → Compositor*) or run a compositor such as `picom`.

**Window doesn't stay on top / doesn't show in the taskbar** 📌
- Some window managers override "always on top" — restart the desktop session or check the WM settings.

**Custom char doesn't load** ❌
- The ZIP must contain exactly one valid `.gif`. Check the path and that the file isn't corrupted.

**Position not saving** 💾
- Make sure `~/.config/mycat/` exists and is writable; the config file is `~/.config/mycat/config.ini`.

**Windows / launch issues** 🪟
- Need Python ≥ 3.10 (`python --version`) for the pip install, or just use the prebuilt `.exe`.
- From the repo you can also launch with `run.bat` (Windows) or `run.sh` (Linux/macOS).
- Verify PySide6: `python -c "import PySide6; print('PySide6 OK')"`.

**Permission errors** 🔒
- On Linux prefer a user install over `sudo` (`pip install --user mycat`).

### 🤝 Getting help

- Search the [GitHub Issues](https://github.com/yumiaura/myCat/issues) for similar problems.
- Read [CONTRIBUTING.md](CONTRIBUTING.md) for development setup.
- Open a new issue with your OS, desktop environment, Python version and any terminal errors.

### License

[MIT License](LICENSE.txt)

Thank you for reading to the end! 😸🐾

<p class="badges">
  <a href="https://buymeacoffee.com/yumiaura"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-support-FFDD00?logo=buymeacoffee&logoColor=000" alt="Buy Me a Coffee"></a>
  <a href="https://www.patreon.com/yumiaura"><img src="https://img.shields.io/badge/Patreon-support-F96854?logo=patreon&logoColor=fff" alt="Patreon"></a>
</p>
