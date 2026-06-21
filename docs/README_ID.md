[EN](https://github.com/yumiaura/myCat/blob/main/README.md) | [RU](https://github.com/yumiaura/myCat/blob/main/docs/README_RU.md) | [中文](https://github.com/yumiaura/myCat/blob/main/docs/README_CN.md) | ID

# Kucing Desktop: Aplikasi Mengambang QT 🐱

[<img src="https://raw.githubusercontent.com/yumiaura/yumiaura/refs/heads/main/images/cat.gif" width="164" alt="cat.gif"/>](https://github.com/yumiaura)

<p class="badges">
  <img src="https://img.shields.io/pypi/pyversions/mycat?color=brightgreen" alt="Python Versions">
  <a href="https://pypi.org/project/mycat/"><img src="https://img.shields.io/pypi/v/mycat?color=brightgreen" alt="PyPI Version"></a>
  <a href="https://pypi.org/project/mycat/"><img src="https://img.shields.io/pepy/dt/mycat?label=pypi%20%7C%20downloads&color=brightgreen" alt="Pepy Total Downloads"/></a>
</p>

Saya membuat animasi kucing kecil yang lucu 🐈 untuk menemani desktop Anda.<br>
Aplikasi Python + Qt yang ringan — tanpa bingkai, dan mudah diseret.<br>
Menampilkan bingkai pertama statis selama 5 detik, lalu memutar animasi GIF sekali, kemudian kembali ke bingkai statis.<br>
Jika Anda menyukainya, mungkin lain kali saya akan membagikan versi [AnimeGirl](https://github.com/yumiaura/mycat/discussions/1)~ 😉

## 🚀 Mulai cepat

Pilih cara yang paling mudah — kucing berjalan di **Windows, macOS, dan Linux**.

### Opsi A — biner siap pakai (tanpa Python)

Unduh build untuk OS Anda dari **[rilis terbaru](https://github.com/yumiaura/myCat/releases/latest)**, lalu jalankan:

| OS | File | Cara menjalankan |
| --- | --- | --- |
| **Windows** | `mycat-<versi>-windows-x64.exe` | klik dua kali |
| **macOS** | `mycat-<versi>-macos-arm64.zip` | ekstrak, lalu buka `mycat.app` |

> Build untuk setiap rilis ada di halaman **[Releases](https://github.com/yumiaura/myCat/releases)**.

### Opsi B — pip (Windows / macOS / Linux, Python ≥ 3.10)

```bash
pip install mycat
mycat
```

Di **Linux** instal juga plugin platform Qt sekali:

```bash
sudo apt install -y libxcb-cursor0
```

Perbarui atau hapus nanti dengan `pip install -U mycat` / `pip uninstall mycat`.

### Opsi C — dari sumber

```bash
git clone https://github.com/yumiaura/myCat
cd myCat
pip install .
mycat                 # atau tanpa instal: python3 mycat/main.py
```

## ✨ Fitur

- **Overlay animasi** 🐱 — kucing tanpa bingkai, selalu di atas, bisa diseret. Klik kanan untuk menu (ganti char, keluar).
- **Pengingat** 🛩️ — atur pesan dan waktu (sekali atau harian), dan kucing terbang dengan pesawat berspanduk melintasi atas layar. Klik kanan → *Reminder…* untuk pesan, arah, pesawat, dan warna.
- **Obrolan (Ollama)** 💬 — mengobrol dengan kucing lewat **model [Ollama](https://ollama.com) lokal**, tanpa akun atau kunci API (lihat di bawah).

## 💬 Mengobrol dengan kucing (Ollama)

Kucing bisa mengobrol memakai model yang dijalankan secara lokal oleh [Ollama](https://ollama.com) — semuanya tetap di mesin Anda, tanpa kunci API.

1. Instal [Ollama](https://ollama.com) dan tarik sebuah model:
   ```bash
   ollama pull llama3.1
   ```
2. Jalankan **mycat**, lalu klik kanan kucing → **Ollama…**
3. Atur host/port (default `localhost:11434`), klik **Load models**, pilih satu, tekan **Test**, lalu **Save** dan centang **LLM enabled**.
4. Klik kanan → **Chat** untuk mulai mengobrol. 🐾

## 🎮 Penggunaan & opsi

Jalankan `mycat` (atau `python3 mycat/main.py` dari sumber) dan sesuaikan dengan opsi baris perintah.

**`--image, -i <path>`** 🖼️ — gunakan ZIP kustom (berisi satu GIF) sebagai pengganti kucing default:

```bash
mycat --image ~/my-custom-cat.zip
```

ZIP **char** harus berisi tepat satu `.gif`: bingkai pertamanya menjadi pose statis, lalu GIF diputar sekali dan kembali ke bingkai itu. Gambar lebih besar dari 300×500 diperkecil otomatis.

**`--pos <x> <y>`** 📍 — mulai di posisi layar tertentu (jika tidak, kucing muncul di kanan-bawah dan mengingat posisi terakhir):

```bash
mycat --pos 960 540        # tengah layar 1920x1080
```

**`--wait <detik>`** ⏱️ — berapa lama menahan bingkai pertama statis sebelum animasi.

**`--debug`** 🐞 — log per-bingkai yang rinci.

### Kontrol

- **Seret kiri** untuk memindahkan kucing.
- **Klik kanan** untuk menu (Chars, Reminder…, Ollama…, Chat, Quit).
- **Keluar** dari menu atau dengan Ctrl+C di terminal.

Kucing mengingat posisi dan char di `~/.config/mycat/config.ini`.

## 🎬 Buat GIF kucing sendiri

```bash
# Instal ImageMagick
sudo apt install imagemagick

# Bangun GIF animasi dari sprite sheet
convert cat.png -crop 50%x100% +repage -set delay '200,100' -loop 0 cat.gif

# Kemas sebagai ZIP char
zip cat.zip cat.gif
```

Letakkan ZIP hasilnya di samping yang lain dan pilih dari menu **Chars** klik-kanan.

## 🐳 Docker

Jalankan kucing dalam kontainer dengan penerusan GUI ke server X host Anda.

**Prasyarat:** Docker, dan server X di host (Xorg di Linux, VcXsrv di Windows, XQuartz di macOS).

```bash
# Linux
xhost +local:docker
docker compose up --build

# Windows (VcXsrv berjalan, klien jaringan diizinkan)
docker compose -f docker-compose.windows.yml up

# macOS (XQuartz berjalan, klien jaringan diizinkan)
docker compose -f docker-compose.mac.yml up
```

## 🔧 Pemecahan masalah

**Kucing muncul dalam kotak hitam / transparansi tidak bekerja** 🫥
- Transparansi X11 membutuhkan compositor. Tanpa compositor, mycat memotong jendela mengikuti garis kucing, jadi ini jarang terjadi; jika masih ada kotak, aktifkan display compositing (XFCE: *Window Manager Tweaks → Compositor*) atau jalankan compositor seperti `picom`.

**Jendela tidak di atas / tidak muncul di taskbar** 📌
- Beberapa window manager menimpa "selalu di atas" — mulai ulang sesi desktop atau periksa pengaturan WM.

**Char kustom tidak dimuat** ❌
- ZIP harus berisi tepat satu `.gif` yang valid. Periksa path dan pastikan file tidak rusak.

**Posisi tidak tersimpan** 💾
- Pastikan `~/.config/mycat/` ada dan dapat ditulis; file konfigurasi `~/.config/mycat/config.ini`.

**Masalah Windows / peluncuran** 🪟
- Instalasi pip membutuhkan Python ≥ 3.10 (`python --version`), atau gunakan `.exe` siap pakai.
- Dari repo Anda juga bisa memakai `run.bat` (Windows) atau `run.sh` (Linux/macOS).
- Verifikasi PySide6: `python -c "import PySide6; print('PySide6 OK')"`.

**Galat izin** 🔒
- Di Linux utamakan instalasi pengguna daripada `sudo` (`pip install --user mycat`).

### 🤝 Mendapatkan bantuan

- Cari masalah serupa di [GitHub Issues](https://github.com/yumiaura/myCat/issues).
- Baca [CONTRIBUTING.md](../CONTRIBUTING.md) untuk setup pengembangan.
- Buat issue baru dengan OS, lingkungan desktop, versi Python, dan pesan galat dari terminal.

### Lisensi

[MIT License](../LICENSE.txt)

Terima kasih sudah membaca sampai akhir! 😸🐾
