## Desktop Cat for XFCE4 (GTK Overlay)

<img src="https://raw.githubusercontent.com/yumiaura/yumiaura/refs/heads/main/images/cat.gif" width="164"  alt="cat.gif"/>

I made a cute little animated cat for your desktop.<br>
It’s a lightweight Python + GTK app — no borders, and you can drag it around easily.<br>
If you like it, maybe I’ll share an anime-girl version next time~ 😉<br>

### Install Dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-gdkpixbuf-2.0
```

### Run

```bash
python3 main.py
```
### Run with custom image

```bash
python3 main.py --image images/cat.png
```

### Create animated GIF from sprite sheet

```bash
sudo apt install imagemagick
convert images/cat.png -crop 50%x100% +repage -set delay '200,100' -loop 0 images/cat.gif
```

