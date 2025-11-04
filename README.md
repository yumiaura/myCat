EN | [CN](https://github.com/yumiaura/myCat/blob/main/docs/readmeCN.md) | [ID](https://github.com/yumiaura/myCat/blob/main/docs/readmeID.md)

## Desktop Cat: QT Overlay 🐱

[<img src="https://raw.githubusercontent.com/yumiaura/yumiaura/refs/heads/main/images/cat.gif" width="164" alt="cat.gif"/>](https://github.com/yumiaura)

<p class="badges">
  <img src="https://img.shields.io/pypi/pyversions/mycat?color=brightgreen" alt="Python Versions">
  <a href="https://pypi.org/project/mycat/"><img src="https://img.shields.io/pypi/v/mycat?color=brightgreen" alt="PyPI Version"></a>
  <a href="https://pypi.org/project/mycat/"><img src="https://img.shields.io/pepy/dt/mycat?label=pypi%20%7C%20downloads&color=brightgreen" alt="Pepy Total Downloads"/></a>
</p>

I made a cute little animated cat 🐈 for your desktop.<br>
It's a lightweight Python + QT app — no borders, and you can drag it around easily.<br>
Shows static first frame for 5 seconds, then plays GIF animation once, then loops back to static.<br>
If you like it, maybe I'll share an [AnimeGirl](https://github.com/yumiaura/mycat/discussions/1) version next time~ 😉<br>

<img width="1440" height="900" alt="image" src="https://github.com/user-attachments/assets/5bc3c45b-83ef-4fcb-8977-781eaf7b045b" />

### 1. Install Dependencies
```bash
sudo apt update
sudo apt install -y python3 python3-pip libxcb-cursor0
pip install PySide6 Pillow
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

### 2.3 Run without installation 🏃‍♂️
```bash
# Clone repository
git clone https://github.com/yumiaura/mycat
cd mycat
python3 mycat/main.py --image images/cat.zip
```

### 3. Usage & Options 🎮

After installation, you can customize the cat 🐱 with various command-line options:

#### Basic Usage
```bash
# Run with default settings
mycat

# Run from source without installation
python3 mycat/main.py
```

#### Command-Line Options

**--image, -i** `<path>` 🖼️
Use a custom ZIP archive containing GIF animation instead of the default cat.

```bash
# Use your own cat ZIP archive
mycat --image ~/my-custom-cat.zip

# Example with full path
mycat --image images/cat.zip
```

**ZIP Archive Requirements:** 🐾
- ZIP format containing exactly one GIF file
- First frame of GIF is used as static image
- GIF animation plays once, then returns to first frame
- Images are automatically scaled if larger than 300x500 pixels

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

**Note:** Position is saved automatically and restored on next launch.

#### Combined Examples 🎯

```bash
# Custom cat with specific wait time and position
mycat --image ~/my-cat.zip --wait 3 --pos 100 100

# Quick animation start in corner
mycat --image images/girl1.zip --wait 1 --pos 1500 800

# Slow animation start with custom ZIP
mycat --image /path/to/custom.zip --wait 10 --pos 0 0
```

#### Controls 🎮
- **Drag** with left mouse button to move the cat 🐱
- **Right-click** anywhere on the cat for context menu with image selection
- **Close** via context menu or Ctrl+C in terminal

The cat remembers its position and selected image between sessions in `~/.config/pixelcat/config.ini`.

### 4. Create animated GIF and ZIP archive 🎬

```bash
# Install ImageMagick for GIF creation
sudo apt install imagemagick

# Create animated GIF from sprite sheet
convert images/cat.png -crop 50%x100% +repage -set delay '200,100' -loop 0 images/cat.gif

# Create ZIP archive for the application
zip images/cat.zip images/cat.gif
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

**Custom image doesn't load** ❌
- Ensure your ZIP archive contains exactly one GIF file
- Check that the GIF file is valid and not corrupted
- Verify the file path is correct and the ZIP file exists
- Make sure the GIF has proper frame delays for smooth animation

**Position not saving** 💾
- Check that `~/.config/pixelcat/` directory exists and is writable
- Look for error messages in the terminal when closing the application
- The config file should be at `~/.config/pixelcat/config.ini`

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
