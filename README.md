## Desktop Cat: QT Overlay (XFCE4)

[<img src="https://raw.githubusercontent.com/yumiaura/yumiaura/refs/heads/main/images/cat.gif" width="164" alt="cat.gif"/>](https://github.com/yumiaura)

I made a cute little animated cat for your desktop.<br>
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
### 2.3 Run without installation
```bash
# Clone repository
git clone https://github.com/yumiaura/mycat
python3 mycat/main.py  --image images/cat.png
```

### 3. Create animated GIF from sprite sheet
```bash
sudo apt install imagemagick
convert images/cat.png -crop 50%x100% +repage -set delay '200,100' -loop 0 images/cat.gif
```

Thank you for reading to the end 😄

