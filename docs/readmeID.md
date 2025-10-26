[EN](../README.md) | [中文](readmeCN.md) | ID
# Kucing Desktop: Overlay QT 🐱

[<img src="https://raw.githubusercontent.com/yumiaura/yumiaura/refs/heads/main/images/cat.gif" width="164" alt="cat.gif"/>](https://github.com/yumiaura)

Saya membuat kucing animasi kecil yang lucu 🐈 untuk desktop Anda.  
Ini adalah aplikasi Python + Qt yang ringan — tanpa bingkai jendela, dan mudah untuk diseret.  
Jika Anda menyukainya, mungkin lain kali saya akan membagikan versi [Gadis Anime](https://github.com/yumiaura/mycat/discussions/1)~ 😉

![screenshot](https://github.com/user-attachments/assets/5bc3c45b-83ef-4fcb-8977-781eaf7b045b)

---

## Daftar Isi
- [Fitur](#fitur)
- [Dependensi & Instalasi](#dependensi--instalasi)
  - [Dependensi Sistem](#dependensi-sistem)
  - [Instal dari PyPI (Direkomendasikan)](#instal-dari-pypi-direkomendasikan)
  - [Instal dari GitHub](#instal-dari-github)
  - [Jalankan tanpa instalasi](#jalankan-tanpa-instalasi)
- [Penggunaan & Opsi Baris Perintah](#penggunaan--opsi-baris-perintah)
- [Kontrol](#kontrol)
- [Menyimpan Posisi](#menyimpan-posisi)
- [Buat GIF dari Sprite Sheet](#buat-gif-dari-sprite-sheet)
- [Pemecahan Masalah](#pemecahan-masalah)
- [Mendapatkan Bantuan](#mendapatkan-bantuan)
- [Lisensi](#lisensi)

---

## Fitur
- Animasi kucing ringan sebagai overlay desktop  
- Jendela tanpa bingkai, dapat diseret bebas  
- Dukungan sprite kustom (2 frame berdampingan: mata terbuka & tertutup)  
- Konfigurasi ukuran, posisi, dan interval kedipan via argumen atau variabel lingkungan  
- Menyimpan posisi terakhir di konfigurasi pengguna

---

## Dependensi & Instalasi

### Dependensi Sistem
Di sistem berbasis Debian/Ubuntu:
```bash
sudo apt update
sudo apt install -y python3 python3-pip
```
Instal binding Qt:
```bash
pip install PySide6
```

### Instal dari PyPI (Direkomendasikan)
Disarankan menggunakan virtual environment:
```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python3 -m pip install mycat

# Jalankan
mycat
# atau
python3 -m mycat

# Upgrade
python3 -m pip install --upgrade mycat

# Uninstall
python3 -m pip uninstall mycat
```

Instalasi sistem (tidak disarankan di desktop):
```bash
sudo python3 -m pip install mycat
```

### Instal dari GitHub
```bash
git clone https://github.com/yumiaura/mycat
cd mycat
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python3 -m pip install .

# Jalankan
mycat

# Uninstall
python3 -m pip uninstall mycat
```

### Jalankan tanpa instalasi 🏃‍♂️
```bash
git clone https://github.com/yumiaura/mycat
python3 mycat/main.py --image images/cat.png
```

---

## Penggunaan & Opsi Baris Perintah 🎮

### Contoh dasar
```bash
# Jalankan dengan pengaturan default
mycat

# Jalankan dari kode sumber tanpa instalasi
python3 mycat/main.py
```

### Opsi umum
--image, -i <path> 🖼️  
Gunakan sprite kustom menggantikan kucing bawaan.
```bash
mycat --image ~/my-custom-cat.png
mycat --image /home/user/Desktop/nyan-cat.png
```
Persyaratan sprite:
- PNG dengan tepat 2 frame berdampingan (kiri: mata terbuka, kanan: mata tertutup)  
- Kedua frame memiliki tinggi yang sama

--size, -s <pixels> 📏  
Lebar tiap frame (ukuran kucing).
```bash
mycat --size 80   # kecil
mycat --size 320  # besar
mycat --size 40   # sangat kecil
```
Anda juga bisa set melalui variabel lingkungan:
```bash
export CAT_SIZE=200
```

--pos <x> <y> 📍  
Mulai kucing di posisi layar tertentu (menimpa posisi yang tersimpan).
```bash
mycat --pos 0 0        # pojok kiri atas
mycat --pos 960 540    # tengah layar 1920x1080
mycat --pos 1600 900   # area kanan bawah
```

--open <seconds> ⏰  
Berapa lama mata tetap terbuka antara kedipan.
```bash
mycat --open 2    # terbuka 2 detik
mycat --open 10   # terbuka 10 detik
mycat --open 0.5  # terbuka 0.5 detik
```

--closed <seconds> 😴  
Berapa lama mata tetap tertutup saat berkedip.
```bash
mycat --closed 0.2
mycat --closed 2
```

### Contoh kombinasi 🎯
```bash
mycat --image ~/my-cat.png --size 200 --pos 100 100
mycat --size 100 --open 2 --closed 0.3
mycat --size 400 --open 8 --closed 1.5 --pos 1500 800
```

---

## Kontrol 🎮
- Seret: tahan tombol kiri mouse untuk memindahkan kucing  
- Klik kanan: buka menu konteks di mana saja pada kucing  
- Tutup: melalui menu konteks atau Ctrl+C di terminal

---

## Menyimpan Posisi
Posisi terakhir disimpan di:
```
~/.config/pixelcat/config.json
```
Jika posisi tidak tersimpan, periksa apakah direktori tersebut ada dan dapat ditulisi.

---

## Buat GIF dari Sprite Sheet 🎬
Dengan ImageMagick:
```bash
sudo apt install imagemagick
convert images/cat.png -crop 50%x100% +repage -set delay '200,100' -loop 0 images/cat.gif
```

---

## Pemecahan Masalah 🔧

Masalah umum dan solusi:

- Kucing tidak muncul atau transparansi tidak bekerja 🫥  
  - Pastikan Anda menggunakan window manager dengan compositing (kebanyakan DE modern menyediakannya)  
  - Coba jalankan dengan flag jendela berbeda atau cek dukungan visual ARGB  
  - Pada KDE Plasma, aktifkan efek desktop jika perlu

- Penggunaan CPU tinggi 💻  
  - Animasi default berjalan pada 60 FPS — pada beberapa sistem ini bisa berat  
  - Penggunaan umumnya kecil, tergantung implementasi Qt di sistem Anda

- Jendela tidak selalu di atas 📌  
  - Beberapa window manager/DE dapat menggantikan pengaturan "selalu di atas"  
  - Coba restart sesi desktop atau periksa pengaturan window manager

- Sprite kustom gagal dimuat ❌  
  - Pastikan PNG memiliki tepat 2 frame berdampingan dan tinggi frame sama  
  - Verifikasi path file dan integritas file

- Posisi tidak tersimpan 💾  
  - Pastikan `~/.config/pixelcat/` ada dan bisa ditulisi  
  - Periksa pesan error di terminal saat menutup aplikasi

- Masalah instalasi di Windows 🪟  
  - Gunakan `run_windows.bat` dari root proyek  
  - Cek PySide6: `pip list | findstr PySide6`  
  - Tes: `python -c "import PySide6; print('PySide6 OK')"`

- Error izin 🔒  
  - Hindari penggunaan `sudo` untuk instalasi di Linux — pakai instalasi pengguna atau virtualenv  
  - Pastikan virtualenv aktif: `which python3` dan `which pip`

---

## Mendapatkan Bantuan 🤝
- Periksa Issues di GitHub untuk masalah serupa  
- Baca CONTRIBUTING.md untuk panduan pengembangan  
- Buat issue baru dengan informasi sistem (OS, DE, versi Python) dan sertakan output error dari terminal

---

## Lisensi
Lisensi MIT

Terima kasih telah membaca! 😸🐾
