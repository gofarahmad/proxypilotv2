
# Proxy Pilot - Modem Management System

Ini adalah aplikasi Next.js yang dirancang untuk mengelola, memonitor, dan memanfaatkan beberapa modem USB sebagai proxy yang dapat dirotasi. Aplikasi ini menyediakan antarmuka web untuk mengontrol modem, proxy, rotasi IP, dan banyak lagi.

## Fitur Utama

- **Deteksi Modem Hibrida:** Secara otomatis mendeteksi modem USB baik yang beroperasi dalam mode serial (ppp) maupun mode ethernet (RNDIS/NCM).
- **Manajemen Proxy (3proxy):** Membuat, memulai, menghentikan, dan me-restart instance 3proxy untuk setiap modem secara dinamis.
- **Konfigurasi Otomatis:** Secara otomatis menghasilkan port, username, dan password untuk setiap proxy.
- **Rotasi IP:** Kemampuan untuk merotasi alamat IP modem dengan satu klik (memerlukan ModemManager).
- **Auto-Rotate:** Jadwalkan rotasi IP otomatis untuk setiap modem.
- **Kontrol Modem (Opsional):** Kirim perintah SMS dan USSD langsung dari antarmuka web (memerlukan ModemManager).
- **Manajemen Tunnel:** Lihat dan kelola tunnel Ngrok/Cloudflare dari UI.
- **AI-Powered Rebinding:** Gunakan AI untuk mendeteksi perubahan IP dan mengikat ulang proxy secara otomatis.

---

## Dasar yang Diperlukan

Sebelum memulai instalasi, pastikan Anda memiliki prasyarat berikut:

### 1. Perangkat Lunak (di Server Ubuntu)

Aplikasi ini bergantung pada beberapa perangkat lunak sistem kunci untuk berfungsi. Anda perlu menginstalnya di server Ubuntu Anda.

- **`Node.js` & `npm`:** Untuk menjalankan aplikasi antarmuka web (Next.js).
- **`Python3` & `pip`:** Untuk menjalankan skrip backend (`backend_controller.py`) yang mengelola semua operasi.
- **`3proxy`:** Server proxy ringan yang kita gunakan untuk membuat proxy untuk setiap modem.
- **`git`:** Untuk mengunduh (clone) kode proyek ini ke server Anda.
- **`Netplan`:** Utilitas konfigurasi jaringan default Ubuntu (biasanya sudah terinstal).
- **`ModemManager` & `usb-modeswitch` (Opsional tapi Direkomendasikan):** Layanan sistem Linux yang dibutuhkan untuk fitur-fitur lanjutan seperti rotasi IP, kirim SMS, dan USSD. Deteksi modem dasar akan tetap berfungsi tanpanya.
- **`nginx` (Opsional tapi Direkomendasikan):** Diperlukan jika Anda ingin mengakses aplikasi tanpa nomor port.
- **`cloudflared` (Opsional):** Diperlukan jika Anda ingin menggunakan fitur Cloudflare Tunnel.

### 2. Pengetahuan & Kemampuan

- **Dasar Command Line Linux:** Anda harus nyaman menggunakan terminal untuk mengikuti panduan instalasi.
- **Pemahaman Jaringan Dasar:** Mengetahui apa itu alamat IP, port, dan DHCP akan sangat membantu.

Kabar baiknya, setelah instalasi selesai, sebagian besar tugas kompleks dikelola melalui antarmuka web yang mudah digunakan.

---

## Panduan Instalasi di Ubuntu 22.04.5 LTS

Berikut adalah langkah-langkah untuk menginstal dan menjalankan aplikasi ini di server Ubuntu 22.04.5 LTS yang baru.

### Langkah 1: Persiapan Awal & Dependensi Sistem

Pertama, perbarui sistem Anda dan instal semua perangkat lunak yang diperlukan.

```bash
# Perbarui daftar paket dan upgrade sistem
sudo apt update && sudo apt upgrade -y

# Instal dependensi sistem yang penting
# 3proxy: Server proxy yang akan kita gunakan
# python3 & pip: Untuk menjalankan skrip backend
# git: Untuk mengkloning repositori
# nginx: Untuk reverse proxy (opsional)
# modemmanager & usb-modeswitch: Opsional untuk fitur lanjutan tapi sangat direkomendasikan
sudo apt install -y 3proxy python3 python3-pip git nginx modemmanager usb-modeswitch
```

### Langkah 2: Instalasi Node.js

Kami merekomendasikan menggunakan `nvm` (Node Version Manager) untuk menginstal Node.js, karena memberikan fleksibilitas.

```bash
# Unduh dan jalankan skrip instalasi nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash

# Muat nvm ke sesi shell Anda saat ini
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"

# Instal Node.js versi LTS (Long Term Support)
nvm install --lts

# Verifikasi instalasi Node.js dan npm
node -v
npm -v
```

### Langkah 3: Konfigurasi 3proxy & Izin

Aplikasi ini perlu menulis file konfigurasi untuk 3proxy. Kita perlu membuat direktori dan mengatur izin.

```bash
# Buat direktori untuk file konfigurasi 3proxy dinamis kita
sudo mkdir -p /etc/3proxy/conf

# Ganti 'your_user' dengan username Anda saat ini (misalnya, 'ubuntu' atau 'root').
# Jalankan `whoami` untuk melihat username Anda.
# Ini memberikan kepemilikan kepada pengguna yang akan menjalankan aplikasi.
sudo chown -R $(whoami):$(whoami) /etc/3proxy
```

### Langkah 4: Membuat Layanan 3proxy Dinamis (`systemd`)

Kita akan membuat template layanan `systemd` agar kita bisa memulai instance 3proxy untuk setiap modem (misalnya, `3proxy@ppp0.service`).

1.  **Buat file layanan baru:**
    ```bash
    sudo nano /etc/systemd/system/3proxy@.service
    ```

2.  **Salin dan tempel konten berikut ke dalam file tersebut:**
    ```ini
    [Unit]
    Description=3proxy service for interface %i
    After=network.target

    [Service]
    Type=simple
    ExecStart=/usr/bin/3proxy /etc/3proxy/conf/%i.cfg
    ExecStop=/bin/kill $MAINPID
    Restart=on-failure
    RestartSec=5

    [Install]
    WantedBy=multi-user.target
    ```

3.  Simpan file dan keluar dari editor (`Ctrl+X`, lalu `Y`, lalu `Enter`).

4.  **Reload daemon systemd** untuk mengenali layanan baru:
    ```bash
    sudo systemctl daemon-reload
    ```
Layanan ini **tidak akan dimulai secara otomatis**. Aplikasi Proxy Pilot akan memulai dan menghentikannya sesuai kebutuhan melalui UI.

### Langkah 5: Mengkloning dan Menyiapkan Aplikasi

Sekarang kita akan mengunduh kode aplikasi dan menginstal dependensinya.

```bash
# Klone repositori proyek dari GitHub
git clone https://github.com/your-username/your-repo-name.git
cd your-repo-name

# Instal semua dependensi Node.js
npm install
```

### Langkah 6 (Opsional tapi Penting): Konfigurasi Jaringan Otomatis (Netplan)

Langkah ini sangat penting jika modem Anda berperilaku seperti adaptor Ethernet (nama antarmuka seperti `enx...`, `usb...`) dan tidak mendapatkan IP secara otomatis saat dicolokkan.

1.  **Buat file konfigurasi Netplan baru:**
    ```bash
    sudo nano /etc/netplan/99-usb-modems.yaml
    ```

2.  **Salin dan tempel konten berikut.** Ini memberitahu sistem untuk secara otomatis meminta alamat IP (DHCP) untuk semua antarmuka USB yang umum.
    ```yaml
    network:
      version: 2
      renderer: NetworkManager
      ethernets:
        usb-modems:
          match:
            name: "enx* or usb* or wwan*"
          dhcp4: true
    ```

3.  **Terapkan konfigurasi baru:**
    ```bash
    sudo netplan apply
    ```
Sekarang, setiap kali Anda mencolokkan modem USB, sistem akan secara otomatis mencoba mendapatkan alamat IP untuknya.

### Langkah 7: Konfigurasi NGINX (Reverse Proxy) - Opsional

Langkah ini akan memungkinkan Anda mengakses UI melalui `http://<IP_SERVER_ANDA>` tanpa mengetikkan port `:9002`.

1.  **Buat file konfigurasi NGINX baru:**
    ```bash
    sudo nano /etc/nginx/sites-available/proxypilot
    ```

2.  **Salin dan tempel konten berikut.** Konfigurasi ini memberitahu NGINX untuk meneruskan permintaan ke aplikasi Next.js Anda yang berjalan di port 9002.
    ```nginx
    server {
        listen 80;
        server_name _; # Ganti dengan domain Anda jika ada

        location / {
            proxy_pass http://localhost:9002;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }
    ```

3.  **Aktifkan konfigurasi ini** dengan membuat symbolic link:
    ```bash
    sudo ln -s /etc/nginx/sites-available/proxypilot /etc/nginx/sites-enabled/
    ```

4.  **Hapus konfigurasi default** jika ada untuk menghindari konflik:
    ```bash
    sudo rm /etc/nginx/sites-enabled/default
    ```

5.  **Tes konfigurasi NGINX** dan restart layanan:
    ```bash
    sudo nginx -t
    sudo systemctl restart nginx
    ```

### Langkah 8: Menjalankan Aplikasi

Aplikasi sekarang siap untuk dijalankan.

1.  **Untuk Mode Produksi (Direkomendasikan):**
    Ini adalah cara yang terbaik untuk penggunaan jangka panjang.
    ```bash
    # Bangun aplikasi untuk produksi
    npm run build

    # Jalankan server produksi
    npm start
    ```
    Anda bisa menggunakan manajer proses seperti `pm2` untuk menjalankan aplikasi ini secara permanen di background.

2.  **Untuk Mode Pengembangan (Development):**
    Ini berguna untuk testing dan debugging. Skrip `npm run dev` sudah dikonfigurasi untuk menerima koneksi jaringan.
    ```bash
    npm run dev
    ```

### Langkah 9: Mengakses Antarmuka Web

Setelah server aplikasi berjalan, buka browser di komputer lain di jaringan Anda dan navigasikan ke:

`http://<IP_SERVER_ANDA>:9002`

Jika Anda mengonfigurasi NGINX (Langkah 7), Anda bisa mengaksesnya tanpa port:

`http://<IP_SERVER_ANDA>`

Contoh: `http://192.168.1.10`

Anda bisa menemukan IP server Anda dengan menjalankan perintah `ip addr show` di terminal server.

---

Instalasi inti selesai! Sistem Anda sekarang harus berjalan. Colokkan modem USB Anda, buka halaman "Modem Status" di UI, dan Anda akan melihatnya muncul setelah beberapa saat. Di bawah ini adalah panduan untuk fitur-fitur opsional.

---

## (Opsional) Menggunakan Domain Kustom dengan Cloudflare Tunnel

Fitur ini memungkinkan Anda mengekspos proxy lokal Anda ke internet menggunakan domain kustom yang stabil (misalnya, `proxy1.domainanda.com`) melalui Cloudflare Tunnel. Ini lebih andal daripada Ngrok untuk penggunaan jangka panjang.

### Prasyarat

1.  **Domain di Cloudflare:** Anda harus memiliki nama domain yang dikelola melalui Cloudflare.
2.  **Instal `cloudflared`:** Jika belum, instal `cloudflared` di server Anda.
    ```bash
    sudo mkdir -p --mode=0755 /usr/share/keyrings
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
    echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared jammy main' | sudo tee /etc/apt/sources.list.d/cloudflared.list
    sudo apt update
    sudo apt install cloudflared
    ```

### Langkah-langkah Konfigurasi

1.  **Otentikasi Server Anda (Satu Kali):**
    Jalankan perintah ini di terminal server. Ia akan membuka browser dan meminta Anda untuk login ke Cloudflare dan memilih domain Anda. **Ini adalah langkah otentikasi satu kali yang aman dan tidak memerlukan API key.**
    ```bash
    cloudflared tunnel login
    ```
    Perintah ini akan membuat file sertifikat `cert.pem` di `~/.cloudflared/`, yang akan digunakan oleh aplikasi Proxy Pilot untuk mengautentikasi server Anda secara otomatis.

2.  **Buat Tunnel di Cloudflare:**
    Buka **Cloudflare Zero Trust Dashboard**. Navigasikan ke `Access -> Tunnels` dan klik "Create a tunnel".
    *   Pilih "Cloudflared" sebagai konektor.
    *   Beri nama tunnel Anda (misalnya, `proxy-pilot-server`).
    *   Setelah dibuat, Anda akan diberikan ID Tunnel (UUID). Simpan ID ini.

3.  **Arahkan Domain Kustom Anda ke Tunnel:**
    *   Masih di dasbor Cloudflare, pergi ke pengaturan DNS untuk domain Anda.
    *   Buat `CNAME` record baru.
    *   **Name:** Nama subdomain yang Anda inginkan (misalnya, `proxy1`).
    *   **Target:** ID Tunnel Anda diikuti dengan `.cfargotunnel.com`.
        Contoh: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.cfargotunnel.com`
    *   Pastikan status "Proxy" (awan oranye) **dimatikan** (abu-abu). Ini penting untuk tunnel.

4.  **Jalankan dan Gunakan dari Aplikasi Proxy Pilot:**
    *   Setelah langkah-langkah di atas selesai, kembali ke aplikasi web Proxy Pilot.
    *   Pergi ke halaman **Settings**.
    *   Di bawah "Configure New Tunnel", pilih "Cloudflare" sebagai provider.
    *   Tunnel yang baru saja Anda buat akan muncul di dropdown "Available Cloudflare Tunnels".
    *   Pilih tunnel tersebut, pilih proxy lokal yang ingin Anda hubungkan, dan klik "Create Tunnel".

Sistem sekarang akan menghubungkan proxy lokal Anda ke domain kustom Anda melalui Cloudflare, tanpa Anda perlu memasukkan API key apa pun ke dalam aplikasi.
