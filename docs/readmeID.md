[EN](https://github.com/yumiaura/myCat/blob/main/README.md) | [中文](https://github.com/yumiaura/myCat/blob/main/docs/readmeCN.md) | ID

# Kucing Desktop: Aplikasi Mengambang QT 🐱

[<img src="https://raw.githubusercontent.com/yumiaura/yumiaura/refs/heads/main/images/cat.gif" width="164" alt="cat.gif"/>](https://github.com/yumiaura)

<p class="badges">
  <img src="https://img.shields.io/pypi/pyversions/mycat?color=brightgreen" alt="Python Versions">
  <a href="https://pypi.org/project/mycat/"><img src="https://img.shields.io/pypi/v/mycat?color=brightgreen" alt="PyPI Version"></a>
  <a href="https://pypi.org/project/mycat/"><img src="https://img.shields.io/pepy/dt/mycat?label=pypi%20%7C%20downloads&color=brightgreen" alt="Pepy Total Downloads"/></a>
</p>

Saya membuat animasi kucing kecil yang lucu 🐈 untuk menemani Anda di desktop Anda.

Ini adalah aplikasi Python + Qt yang ringan — tanpa batas, dan dapat diseret dengan mudah。

Saat dijalankan, kucing akan menampilkan bingkai pertama secara statis selama 5 detik, kemudian memutar animasi GIF sekali, lalu kembali ke bingkai pertama secara statis.

Jika Anda menyukainya, mungkin lain kali saya akan membagikan versi AnimeGirl~ 😉

<img width="1440" height="900" alt="screenshot" src="https://github.com/user-attachments/assets/5bc3c45b-83ef-4fcb-8977-781eaf7b045b" />

## 1. Instal Dependensi

Contoh pada Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y python3 python3-pip libxcb-cursor0
pip install PySide6 Pillow
```

## 2. Instalasi & Menjalankan

### 2.1 Dari PyPI (direkomendasikan instalasi pengguna pada Ubuntu)

```bash
# Buat dan aktifkan virtual environment (opsional tapi direkomendasikan)
python3 -m venv --system-site-packages .venv
source .venv/bin/activate

# Instal paket
python3 -m pip install mycat

# Jalankan
mycat
# Atau jalankan eksplisit:
python3 -m mycat

# Upgrade
python3 -m pip install --upgrade mycat

# Uninstall
python3 -m pip uninstall mycat
```

Catatan: Instalasi global dengan sudo tidak disarankan di lingkungan desktop.

### 2.2 Dari GitHub (clone lalu instal)

```bash
# Clone repo
git clone https://github.com/yumiaura/mycat
cd mycat

# Buat dan aktifkan virtual environment
python3 -m venv --system-site-packages .venv
source .venv/bin/activate

# Instal paket dari direktori
python3 -m pip install .

# Jalankan
mycat

# Uninstall
python3 -m pip uninstall mycat
```

### 2.3 Jalankan Tanpa Instalasi 🏃‍♂️

```bash
# Clone repo
git clone https://github.com/yumiaura/mycat
cd mycat

# Jalankan langsung (contoh menggunakan image bawaan)
python3 mycat/main.py --image images/cat.zip
```

## 3. Penggunaan & Opsi 🎮

Setelah terinstal, Anda dapat menyesuaikan kucing 🐱 lewat opsi baris perintah.

Penggunaan dasar:

```bash
# Jalankan dengan pengaturan default
mycat

# Jalankan dari sumber tanpa instalasi
python3 mycat/main.py
```

Opsi baris perintah:

--image, -i <path> 🖼️  
Gunakan arsip ZIP kustom yang berisi GIF animasi untuk mengganti kucing bawaan.

```bash
# Gunakan ZIP kustom (harus berisi satu GIF)
mycat --image ~/my-custom-cat.zip

# Contoh menggunakan file dalam repo
mycat --image images/cat.zip
```

Persyaratan ZIP: 🐾
- Harus berformat ZIP dan hanya berisi satu file GIF.  
- Bingkai pertama GIF akan digunakan sebagai gambar statis.  
- Animasi GIF diputar sekali, lalu kembali ke bingkai pertama.  
- Jika ukuran gambar lebih besar dari 300x500 piksel, akan diskalakan secara proporsional.

--pos <x> <y> 📍  
Mulai kucing pada posisi layar tertentu (mengganti posisi yang tersimpan):

```bash
# Sudut kiri atas layar
mycat --pos 0 0

# Pusat layar 1920x1080
mycat --pos 960 540

# Contoh area kanan bawah
mycat --pos 1600 900
```

Catatan: Posisi disimpan otomatis dan dipulihkan di peluncuran berikutnya.

Contoh kombinasi 🎯

```bash
# Kustom image, waktu tunggu, dan posisi
mycat --image ~/my-cat.zip --wait 3 --pos 100 100

# Animasi cepat di pojok layar
mycat --image images/girl1.zip --wait 1 --pos 1500 800

# Animasi lambat dengan ZIP kustom
mycat --image /path/to/custom.zip --wait 10 --pos 0 0
```

Kontrol 🎮
- Seret dengan tombol kiri mouse untuk memindahkan kucing.  
- Klik kanan di mana saja pada kucing untuk membuka menu konteks pilihan gambar.  
- Tutup lewat menu konteks atau tekan Ctrl+C di terminal.  
- Kucing akan mengingat posisi dan gambar yang dipilih di ~/.config/pixelcat/config.ini.

## 4. Membuat GIF Animasi & Arsip ZIP 🎬

Gunakan ImageMagick untuk membuat GIF:

```bash
# Instal ImageMagick (Debian/Ubuntu)
sudo apt install imagemagick

# Dari sprite sheet buat GIF animasi (contoh)
convert images/cat.png -crop 50%x100% +repage -set delay '200,100' -loop 0 images/cat.gif

# Kemudian bungkus ke ZIP (harus hanya ada satu GIF di ZIP)
zip images/cat.zip images/cat.gif
```

## 5. Pemecahan Masalah 🔧

Masalah umum dan solusi:

Kucing tidak muncul atau transparansi tidak berfungsi 🫥
- Di Linux, pastikan window manager Anda mendukung compositing (kebanyakan DE modern mendukung).  
- Coba jalankan dengan flag jendela yang berbeda atau periksa dukungan visual ARGB.  
- Untuk KDE Plasma, mungkin perlu mengaktifkan efek desktop.

Penggunaan CPU tinggi 💻
- Animasi default berjalan pada 60 FPS, yang mungkin berat di beberapa sistem.  
- Penggunaan CPU biasanya kecil, tetapi bergantung pada implementasi Qt di sistem Anda.

Jendela tidak tetap di atas 📌
- Beberapa window manager/DE mungkin mengganti pengaturan "always on top".  
- Coba restart sesi desktop Anda atau periksa pengaturan window manager.

Gambar kustom tidak dapat dimuat ❌
- Pastikan ZIP hanya berisi satu file GIF.  
- Periksa apakah GIF valid dan tidak rusak.  
- Verifikasi path file dan keberadaan ZIP.  
- Pastikan GIF memiliki delay frame yang sesuai agar animasi lancar.

Posisi tidak tersimpan 💾
- Periksa apakah direktori ~/.config/pixelcat/ ada dan dapat ditulis.  
- Periksa terminal untuk pesan error saat menutup aplikasi.  
- File konfigurasi seharusnya berada di ~/.config/pixelcat/config.ini.

Masalah instalasi di Windows 🪟
- Gunakan skrip run_windows.bat dari root proyek.  
- Pastikan PySide6 terinstal: `pip list | findstr PySide6`  
- Atau jalankan `python -c "import PySide6; print('PySide6 OK')"` untuk tes.

Kesalahan izin 🔒
- Di Linux, hindari sudo untuk instalasi — gunakan instalasi pengguna atau virtualenv.  
- Periksa apakah virtualenv sudah aktif: `which python3` dan `which pip` harus menunjuk ke venv.

Mencari bantuan 🤝
- Cari masalah serupa di GitHub Issues.  
- Baca CONTRIBUTING.md untuk panduan pengembangan.  
- Buat Issue baru dengan detail sistem Anda (OS, desktop environment, versi Python) dan sertakan pesan error dari terminal.

#### Lisensi

MIT License

Terima kasih sudah membaca sampai akhir! 😸🐾
