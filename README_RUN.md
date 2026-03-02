# SR15 Analytics — Panduan Menjalankan

## Dev Mode (debug, auto-reload)

```bash
python app.py
# atau
python app.py --port 8080
```

---

## Production Mode (Gunicorn / LAN)

### 1. Install Gunicorn

```bash
pip install gunicorn
```

> **Windows native**: Gunicorn tidak berjalan di Windows tanpa WSL.
> Alternatif native Windows: gunakan **Waitress**:
> ```bash
> pip install waitress
> waitress-serve --host=0.0.0.0 --port=8050 app:server
> ```

### 2. Cek IP LAN

**Windows:**
```powershell
ipconfig
# Cari "IPv4 Address" pada adapter WiFi / Ethernet
# Contoh: 192.168.1.105
```

**Linux / WSL:**
```bash
ip addr show | grep "inet "
# atau
hostname -I
```

### 3. Jalankan Server

**Linux / WSL:**
```bash
export ENV=prod
export SECRET_KEY="isi-secret-key-aman"
gunicorn app:server -c gunicorn.conf.py
```

atau:
```bash
bash run_prod_linux.sh
```

**Windows (PowerShell):**
```powershell
.\run_prod_windows.ps1
```

### 4. Buka Firewall Port 8050

**Windows Firewall:**
```powershell
New-NetFirewallRule -DisplayName "SR15 Analytics" -Direction Inbound `
  -Protocol TCP -LocalPort 8050 -Action Allow
```

**Linux (ufw):**
```bash
sudo ufw allow 8050/tcp
```

### 5. Akses dari Device Lain di WiFi yang Sama

```
http://192.168.1.105:8050
     ^^^^^^^^^^^^^^^^
     Ganti dengan IP laptop dari langkah 2
```

> **Syarat**: Semua device harus terhubung ke **WiFi yang sama**.
> Hotspot HP atau SSID berbeda tidak akan bisa mengakses.

---

## Konfigurasi Gunicorn (`gunicorn.conf.py`)

| Parameter | Nilai | Keterangan |
|---|---|---|
| `workers` | 6 | 2 × cores + 1 (sesuaikan dengan CPU) |
| `threads` | 4 | Thread per worker |
| `timeout` | 180 | Maks waktu proses 1 request (detik) |
| `preload_app` | True | Load data sekali di master, hemat RAM |
| `max_requests` | 2000 | Restart worker setelah N request |

### Tradeoff `preload_app = True`
- **Pro**: Data di-cache sekali, semua worker share memori → hemat RAM ~60%
- **Kontra**: Setelah update kode, harus restart Gunicorn manual (tidak auto-reload)

---

## Environment Variables

| Variabel | Default | Keterangan |
|---|---|---|
| `ENV` | `""` | Set `prod` untuk aktifkan preload saat startup |
| `SECRET_KEY` | default (TIDAK AMAN) | Wajib diset di production |
| `PORT` | `8050` | Override port dev mode |
| `ANTHROPIC_API_KEY` | `""` | Untuk chatbot Claude AI |
| `ADMIN_USERNAME` | `admin` | Username admin |
| `ADMIN_PASSWORD` | `admin` | Password admin — **wajib diganti** |

---

## Menghentikan Server

```bash
# Cari PID
lsof -i :8050   # Linux
netstat -ano | findstr 8050   # Windows

# Kill
kill -9 <PID>   # Linux
taskkill /F /PID <PID>   # Windows
```
