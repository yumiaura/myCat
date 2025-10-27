## Desktop Cat: QT Overlay 🐱

[<img src="https://raw.githubusercontent.com/yumiaura/yumiaura/refs/heads/main/images/cat.gif" width="164" alt="cat.gif"/>](https://github.com/yumiaura)

I made a cute little animated cat 🐈 for your desktop.<br>
It’s a lightweight Python + QT app — no borders, and you can drag it around easily.<br>
If you like it, maybe I’ll share an [AnimeGirl](https://github.com/yumiaura/mycat/discussions/1) version next time~ 😉<br>

<img width="1440" height="900" alt="image" src="https://github.com/user-attachments/assets/5bc3c45b-83ef-4fcb-8977-781eaf7b045b" />

### 1. Install Dependencies
```bash
sudo apt update
sudo apt install -y python3 python3-pip
pip install PySide6
```

### 2.1 Install from PyPI
```bash
# user install (recommended on Ubuntu)
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python3 -m pip install mycat
# or system-wide (not recommended on Ubuntu desktop)
# sudo python3 -m pip install mycat
# Run
mycat
# or explicitly:
python3 -m mycat
# Upgrade
python3 -m pip install --upgrade mycat
# Uninstall
python3 -m pip uninstall mycat
```

### 2.2 Download from GitHub and install
```bash
# Install
git clone https://github.com/yumiaura/mycat
cd mycat
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python3 -m pip install .
# Run
mycat
# Uninstall
python3 -m pip uninstall mycat
```
### 2.3 Install with uv
```bash
# Install
git clone https://github.com/yumiaura/mycat
cd mycat
uv sync
# Run
mycat
# Uninstall
uv pip uninstall mycat
```

### 2.4 Run without installation 🏃‍♂️
```bash
# Clone repository
git clone https://github.com/yumiaura/mycat
python3 mycat/main.py  --image images/cat.png
```

### 3. Usage & Options 🎮

After installation, you can customize the cat 🐱 with various command-line options:

#### Basic Usage
```bash
# Run with default settings
mycat

# Run from source without installation
python3 mycat/main.py
# or u can use uv
uv mycat/main.py
```

#### Command-Line Options

**--image, -i** `<path>` 🖼️
Use a custom sprite instead of the default cat.

```bash
# Use your own cat sprite
mycat --image ~/my-custom-cat.png

# Example with full path
mycat --image /home/user/Desktop/nyan-cat.png
```

**Sprite Requirements:** 🐾
- PNG format with exactly 2 frames side-by-side
- Left frame: eyes open
- Right frame: eyes closed
- Both frames should have the same height

**--size, -s** `<pixels>` 📏
Set the width of each animation frame (cat size).

```bash
# Small cat (80px wide)
mycat --size 80

# Large cat (320px wide)
mycat --size 320

# Tiny cat (40px wide)
mycat --size 40
```

**Environment Variable:** You can also set `CAT_SIZE=200` to avoid using the flag every time.

**--pos** `<x> <y>` 📍
Start the cat at a specific screen position (overrides saved position).

```bash
# Top-left corner
mycat --pos 0 0

# Center of 1920x1080 screen
mycat --pos 960 540

# Bottom-right area
mycat --pos 1600 900
```

**--open** `<seconds>` ⏰
Set how long the cat keeps eyes open between blinks.

```bash
# Fast blinking (2 seconds open)
mycat --open 2

# Very slow blinking (10 seconds open)
mycat --open 10

# Quick blinks (0.5 seconds open)
mycat --open 0.5
```

**--closed** `<seconds>` 😴
Set how long the cat keeps eyes closed during blinks.

```bash
# Quick blink (0.2 seconds closed)
mycat --closed 0.2

# Long blink (2 seconds closed)
mycat --closed 2
```

#### Combined Examples 🎯

```bash
# Custom cat with specific size and position
mycat --image ~/my-cat.png --size 200 --pos 100 100

# Fast-blinking small cat
mycat --size 100 --open 2 --closed 0.3

# Large sleepy cat in corner
mycat --size 400 --open 8 --closed 1.5 --pos 1500 800
```

#### Controls 🎮
- **Drag** with left mouse button to move the cat 🐱
- **Right-click** anywhere on the cat for context menu
- **Close** via context menu or Ctrl+C in terminal

The cat remembers its position between sessions in `~/.config/pixelcat/config.json`.

### 4. Create animated GIF from sprite sheet 🎬

```bash
sudo apt install imagemagick
convert images/cat.png -crop 50%x100% +repage -set delay '200,100' -loop 0 images/cat.gif
```

### 5. Troubleshooting 🔧

#### Common Issues

**Cat doesn't appear or transparency doesn't work** 🫥
- On Linux, ensure you're using a compositing window manager (most modern desktop environments support this)
- Try running with different window flags or check if your system supports ARGB visuals
- For KDE Plasma, you may need to enable desktop effects

**High CPU usage** 💻
- The animation runs at 60 FPS by default, which can be intensive on some systems
- The CPU usage is usually minimal but depends on your system's Qt implementation

**Window doesn't stay on top** 📌
- Some window managers or desktop environments may override the "always on top" setting
- Try restarting your desktop session or check window manager settings

**Custom sprite doesn't load** ❌
- Ensure your PNG has exactly 2 frames side-by-side (left: eyes open, right: eyes closed)
- Check that both frames have identical heights
- Verify the file path is correct and the file isn't corrupted

**Position not saving** 💾
- Check that `~/.config/pixelcat/` directory exists and is writable
- Look for error messages in the terminal when closing the application
- The config file should be at `~/.config/pixelcat/config.json`

**Installation issues on Windows** 🪟
- Make sure you're using the `run_windows.bat` script from the project root
- Check that PySide6 installed correctly: `pip list | findstr PySide6`
- Try running `python -c "import PySide6; print('PySide6 OK')"` to test

**Permission errors** 🔒
- On Linux, avoid using `sudo` for installation - use user installs instead
- Check that virtual environment activation worked: `which python3` and `which pip`

#### Getting Help 🤝
- Check the [GitHub Issues](https://github.com/yumiaura/mycat/issues) for similar problems
- Read [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines
- Create a new issue with your system details (OS, desktop environment, Python version)
- Include any error messages from the terminal

#### License
[MIT License](LICENSE.txt)

Thank you for reading to the end! 😸🐾
