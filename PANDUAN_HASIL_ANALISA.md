# Panduan Hasil Analisa — SR15 PIB × HS Code × KLU
**CRM Subtim Data Analyst 2026 · DJP**

> Dokumen ini menjelaskan setiap bagian pada halaman **Hasil Analisa** di dashboard SR15.
> Ditujukan bagi pengguna yang belum familiar dengan metodologi analisis risiko impor.

---

## Daftar Isi
1. [Latar Belakang & Tujuan Analisis](#1-latar-belakang--tujuan-analisis)
2. [Glosarium Istilah Kunci](#2-glosarium-istilah-kunci)
3. [File 01 — HS Code Final per Klaster](#3-file-01--hs-code-final-per-klaster)
4. [File 02 — Profil HS Code](#4-file-02--profil-hs-code)
5. [File 03 — Matriks Sinkronisasi HS-KLU](#5-file-03--matriks-sinkronisasi-hs-klu)
6. [File 04 — Rekomendasi Prioritas](#6-file-04--rekomendasi-prioritas)
7. [File 05 — Catatan Data Tambahan](#7-file-05--catatan-data-tambahan)
8. [Panduan Membaca Risk Score & Risk Flags](#8-panduan-membaca-risk-score--risk-flags)
9. [Panduan Membaca Dispersi KLU](#9-panduan-membaca-dispersi-klu)
10. [Alur Kerja yang Disarankan](#10-alur-kerja-yang-disarankan)

---

## 1. Latar Belakang & Tujuan Analisis

Analisis SR15 dirancang untuk mengidentifikasi **potensi risiko ketidakpatuhan pajak** pada kegiatan impor barang yang dilaporkan melalui Pemberitahuan Impor Barang (PIB). Pendekatan yang digunakan adalah **cross-matching** antara tiga dimensi data:

| Dimensi | Keterangan |
|---------|-----------|
| **PIB (HS Code)** | Kode barang yang dideklarasikan di bea cukai — menggambarkan "barang apa yang diimpor" |
| **KLU (Klasifikasi Lapangan Usaha)** | Kode usaha Wajib Pajak — menggambarkan "bisnis apa yang dijalankan WP" |
| **Pajak (PPN & PPh)** | Nilai pajak yang dibayarkan — sebagai proksi kepatuhan dan kewajaran ekonomi |

**Pertanyaan utama yang dijawab:**
- Apakah jenis barang yang diimpor **selaras** dengan jenis usaha yang didaftarkan?
- Apakah nilai pajak yang dibayarkan **wajar** untuk volume dan jenis barang tersebut?
- HS Code mana yang **paling berisiko** untuk menjadi prioritas pengawasan?

---

## 2. Glosarium Istilah Kunci

### Kode & Identifikasi

| Istilah | Kepanjangan | Penjelasan Singkat |
|---------|-------------|-------------------|
| **PIB** | Pemberitahuan Impor Barang | Dokumen resmi deklarasi barang impor ke DJBC |
| **HS Code** | Harmonized System Code | Kode 8-digit internasional untuk klasifikasi barang impor. Contoh: `85171300` = Telepon untuk jaringan seluler |
| **HS-4** | 4 digit pertama HS Code | Kelompok barang lebih luas. Contoh: `8517` = Pesawat telepon & peralatan komunikasi |
| **Chapter HS** | 2 digit pertama HS Code | Kategori paling luas. Contoh: Ch.85 = Elektronik & Mesin Listrik |
| **KLU** | Klasifikasi Lapangan Usaha | Kode 5-digit yang menyatakan jenis kegiatan usaha WP. Contoh: `26320` = Industri Peralatan Komunikasi Tanpa Kabel |
| **NPWP** | Nomor Pokok Wajib Pajak | Identitas unik setiap Wajib Pajak |
| **KD Kelompok** | Kode Kelompok | Kode 4-digit pengelompokan HS Code dalam sistem DJP |

### Pajak & Keuangan

| Istilah | Penjelasan |
|---------|-----------|
| **PPN** | Pajak Pertambahan Nilai — dibayarkan saat mengimpor barang (umumnya 11%) |
| **PPh** | Pajak Penghasilan — mencerminkan omzet/keuntungan usaha WP |
| **PPh/PPN Ratio** | Rasio antara PPh dan PPN. Rasio normal berkisar **0.05–2.0**. Di luar rentang ini mengindikasikan anomali |
| **PPN per NPWP** | Rata-rata PPN per importir — mengukur konsentrasi impor |

### Indikator Risiko

| Istilah | Penjelasan |
|---------|-----------|
| **Risk Score** | Skor risiko gabungan dari 0.0 sampai 1.0. Makin tinggi = makin berisiko |
| **Risk Flags** | Label teknis yang memicu kenaikan Risk Score (lihat Bagian 8) |
| **Risk Events** | Jenis potensi pelanggaran yang terindikasi (lihat Bagian 8) |
| **Dispersi KLU** | Jumlah jenis KLU yang menggunakan satu HS Code — mengukur "keragaman" pengguna barang tersebut |
| **Catch-all / Lain-lain** | HS Code dengan deskripsi sangat umum (misal: "Lain-lain") — rentan penyalahgunaan klasifikasi |

---

## 3. File 01 — HS Code Final per Klaster

**Nama file:** `01_HS_Code_Final_per_Klaster.xlsx`

### Apa isinya?
Daftar lengkap seluruh HS Code yang masuk dalam **scope analisis**, dikelompokkan per klaster industri. Ini adalah *output utama* yang menjadi basis seluruh analisis lanjutan.

### Sheet yang tersedia

| Sheet | Isi |
|-------|-----|
| **Elektronik (Ch.85)** | HS Code barang elektronik & listrik (mesin, transformator, kabel, telepon, dll.) |
| **Otomotif (Ch.87)** | HS Code kendaraan & suku cadang (truk, mobil, motor, spare part) |
| **Kimia/Farmasi (Ch.28-38)** | HS Code bahan kimia, pupuk, plastik, karet, dan farmasi |
| **Pangan (Ch.10-11)** | HS Code pangan & bahan pangan pokok (gandum, beras, tepung, dll.) |
| **Lainnya** | HS Code di luar keempat klaster di atas yang masih relevan untuk SR15 |
| **SEMUA_KLASTER** | Gabungan semua klaster dalam satu tabel — untuk analisis lintas klaster |

### Penjelasan Kolom

| Kolom | Penjelasan | Contoh |
|-------|-----------|--------|
| **HS Code (8 digit)** | Kode HS lengkap sesuai BTKI (Buku Tarif Kepabeanan Indonesia) | `85171300` |
| **KD Kelompok (4 digit)** | Kode kelompok internal DJP. `0` = belum ter-mapping | `8517` |
| **Nama Kelompok** | Deskripsi kelompok. `-` = belum ter-mapping | `Mesin & pesawat telepon` |
| **Nama Detail (NM_DETIL)** | Deskripsi rinci HS Code dari BCDE | `Telepon untuk jaringan seluler` |
| **Ada Kelompok?** | `True` = sudah ter-mapping ke KD_KELOMPOK DJP | `True/False` |
| **Catch-all / Lain-lain** | `True` = kode ini bersifat umbrella/lain-lain → potensi salah klasifikasi tinggi | `True/False` |
| **# KLU Unik** | Berapa jenis usaha berbeda yang mengimpor barang ini | `578` (sangat tinggi!) |
| **Dispersi Kategori** | Kategori dispersi KLU (A hingga G) — lihat Bagian 9 | `G - Kritis (>100)` |
| **# NPWP** | Jumlah importir unik untuk HS Code ini | `4207` |
| **# PIB** | Jumlah dokumen PIB yang tercatat | `41.157` |
| **PPN Dibayar (Rp)** | Total PPN yang dibayarkan seluruh importir untuk HS Code ini | Rp 293 M |
| **PPh Dibayar (Rp)** | Total PPh yang dibayarkan | Rp 174 M |
| **PPh/PPN Ratio** | Lihat Bagian 8 | `0.5952` |
| **Risk Score** | Skor risiko 0.0–1.0 | `0.5066` |
| **Risk Flags** | Flag teknis pemicu risiko | `DISPERSI_TINGGI \| CATCH_ALL` |
| **Risk Events** | Jenis pelanggaran yang terindikasi | `Misdeclaration` |
| **Justifikasi Scope** | Alasan HS Code ini masuk/tidaknya scope pengawasan | Teks bebas |

### Tips Penggunaan
> **Fokus pada baris dengan `Risk Score > 0.4` DAN `Catch-all? = True`** — kombinasi ini adalah indikator terkuat potensi misdeclaration. Importir dapat menggunakan kode "lain-lain" untuk mengimpor barang yang seharusnya menggunakan kode lebih spesifik dengan tarif berbeda.

---

## 4. File 02 — Profil HS Code

**Nama file:** `02_Profil_HS_Code.xlsx`

### Apa isinya?
Peringkat HS Code berdasarkan empat perspektif berbeda untuk membantu analis **memprioritaskan** objek pemeriksaan.

### Sheet yang tersedia

#### `By_Risk_Score` — Urutan berdasarkan Risiko Tertinggi
Daftar HS Code diurutkan dari **risk score tertinggi ke terendah**. Gunakan sheet ini untuk menentukan prioritas pengawasan berdasarkan profil risiko komprehensif.

#### `By_PPN_Value` — Urutan berdasarkan Nilai PPN
Daftar HS Code diurutkan dari **nilai PPN terbesar**. Sheet ini penting untuk menentukan objek pemeriksaan dengan dampak penerimaan pajak terbesar. Nilai besar + risiko tinggi = prioritas utama.

#### `By_Dispersi_KLU` — Urutan berdasarkan Keragaman Pengguna
Daftar HS Code diurutkan dari **# KLU Unik terbanyak**. HS Code dengan pengguna paling beragam menunjukkan ambiguitas klasifikasi yang tinggi — bisa jadi kode yang terlalu umum (catch-all) atau kode yang disalahgunakan lintas sektor.

#### `By_Konsentrasi` — Urutan berdasarkan Konsentrasi Importir
Daftar HS Code yang impornya **terkonsentrasi pada sedikit importir** (nilai PPN per NPWP sangat besar). Konsentrasi tinggi berarti satu atau beberapa perusahaan menguasai hampir seluruh impor barang tersebut — meningkatkan risiko transfer pricing dan pengaturan harga.

### Penjelasan Kolom Tambahan (khusus File 02)

| Kolom | Penjelasan |
|-------|-----------|
| **Rank** | Peringkat dalam sheet tersebut (1 = paling prioritas) |
| **PPN per NPWP (Rp)** | Rata-rata beban PPN per importir. Nilai sangat tinggi → konsentrasi |
| **PIB per NPWP** | Rata-rata dokumen PIB per importir. Nilai rendah + PPN besar → sedikit transaksi besar-besaran |

---

## 5. File 03 — Matriks Sinkronisasi HS-KLU

**Nama file:** `03_Matriks_Sinkronisasi_HS_KLU.xlsx`

### Apa isinya?
Tabel yang memetakan **setiap pasangan HS Code ↔ KLU** yang ditemukan dalam data — dan menilai apakah kombinasi tersebut **wajar atau anomali**.

**Logika dasarnya:** Jika seseorang mengimpor mesin elektronik (HS Ch.85) tetapi KLU-nya adalah pertanian, ada ketidakwajaran. Barang yang diimpor tidak sesuai dengan bidang usaha yang dilaporkan ke DJP.

### Sheet yang tersedia

#### `Semua_Pasangan` — Seluruh Kombinasi HS-KLU
Semua kombinasi HS Code dan KLU yang pernah tercatat dalam data PIB. Gunakan sebagai referensi lengkap.

#### `Anomali_Saja` — Hanya Pasangan Tidak Wajar
**Sheet yang paling penting untuk investigasi.** Berisi pasangan HS-KLU yang terindikasi anomali — yaitu WP yang mengimpor barang yang tidak sesuai dengan bidang usahanya.

> **Contoh anomali nyata dari data:**
> HS Code `85177939` (peralatan komunikasi tanpa kabel) diimpor oleh WP dengan KLU `26320` (Industri Peralatan Komunikasi Tanpa Kabel). Seharusnya wajar — tetapi terdeteksi anomali karena **PPh/PPN Ratio = 0.0009** (hampir nol), artinya WP memiliki PPN impor sangat besar tetapi hampir tidak membayar PPh sama sekali.

#### `Wajar_Dominan` — Pasangan dengan Status Normal
Kombinasi HS-KLU yang dianggap wajar dan dominan (mayoritas importir HS Code tersebut memiliki KLU yang relevan). Berguna sebagai **benchmark** untuk menilai kewajaran.

### Penjelasan Kolom

| Kolom | Penjelasan |
|-------|-----------|
| **Cluster** | Klaster HS Code (Elektronik, Otomotif, dst.) |
| **Share NPWP** | Proporsi importir HS Code ini yang menggunakan KLU tersebut. `0.75` = 75% importir punya KLU ini |
| **Sub-golongan KLU** | Kategori lebih luas dari KLU — membantu identifikasi sektor |
| **# KLU Unik (HS)** | Total variasi KLU yang menggunakan HS Code ini |
| **Status Sinkronisasi** | Hasil penilaian sistem: `[OK] WAJAR` atau `[!] ANOMALI` beserta alasannya |

### Kode Status Sinkronisasi

| Status | Arti |
|--------|------|
| `[OK] WAJAR - Dominan` | KLU ini adalah pengguna terbesar HS Code tersebut — wajar |
| `[!] ANOMALI - Nilai Besar` | Share NPWP kecil tapi nilai PPN besar — sedikit WP mendominasi transaksi dengan KLU tak lazim |
| `[!] ANOMALI - PPh Rendah` | PPN besar tapi PPh nyaris nol — indikasi penghindaran PPh |
| `[!] ANOMALI - Lintas Sektor` | KLU WP tidak relevan sama sekali dengan jenis barang yang diimpor |

---

## 6. File 04 — Rekomendasi Prioritas

**Nama file:** `04_Rekomendasi_Prioritas.xlsx`

### Apa isinya?
Daftar HS Code yang **paling diprioritaskan untuk tindak lanjut**, dikelompokkan berdasarkan jenis potensi pelanggaran yang terdeteksi. Ini adalah **output akhir** yang langsung dapat digunakan untuk menentukan WP mana yang perlu diperiksa.

### Sheet yang tersedia

#### `Top100_Risk_Score` — 100 HS Code Risiko Tertinggi
Gabungan semua jenis risiko. Gunakan sebagai **daftar utama** jika hanya ingin satu referensi prioritas.

---

#### `Misdeclaration` — Indikasi Salah Klasifikasi Barang

**Apa itu?** Importir mendeklarsikan barang dengan kode HS yang salah atau terlalu umum untuk menghindari bea masuk yang lebih tinggi, atau untuk menyembunyikan jenis barang sebenarnya.

**Indikator yang digunakan:**
- HS Code berjenis **Catch-all/Lain-lain** (deskripsi sangat umum)
- Dispersi KLU sangat tinggi (banyak jenis usaha berbeda mengimpor barang yang sama)
- PPh/PPN Ratio **sangat rendah** (< 0.05) — menunjukkan WP tidak produktif secara usaha

> **Contoh:** HS `10019912` (Lain-lain: Biji gandum tanpa cangkang) diimpor oleh WP dengan berbagai KLU yang tidak relevan. PPh/PPN Ratio = 0.045 — sangat rendah. Kemungkinan barang sebenarnya bukan gandum murni.

---

#### `Mispricing` — Indikasi Manipulasi Harga Impor

**Apa itu?** Importir melaporkan harga barang yang terlalu rendah (under-invoicing) sehingga PPN yang dibayar lebih kecil dari seharusnya, atau melakukan transfer pricing dengan pihak terkait di luar negeri.

**Indikator yang digunakan:**
- Jumlah importir sangat sedikit (`# NPWP` rendah) tapi nilai PPN besar
- PPN per NPWP jauh di atas rata-rata pasar
- Risk Flag **TERKONSENTRASI**

> **Contoh:** HS `27101224` (Minyak ringan) hanya diimpor oleh 8 WP, namun total PPN mencapai Rp 17,7 triliun. PPN per importir rata-rata Rp 2,2 triliun — sangat terkonsentrasi.

---

#### `API-P_Abuse` — Indikasi Penyalahgunaan API-P

**Apa itu?** API-P (Angka Pengenal Importir Produsen) hanya boleh digunakan untuk mengimpor barang yang akan digunakan sebagai **bahan baku produksi sendiri** — bukan untuk diperdagangkan. Penyalahgunaan terjadi ketika importir berAPI-P mengimpor barang yang tidak digunakan untuk produksi.

**Indikator yang digunakan:**
- HS Code berjenis Catch-all (barang terlalu umum untuk diklaim sebagai bahan baku spesifik)
- KLU WP tidak mencerminkan kegiatan produksi
- PPh/PPN Ratio rendah (bukan produsen nyata)

---

#### `Artificial_Loss` — Indikasi Kerugian Buatan

**Apa itu?** WP melaporkan pengeluaran PPh sangat besar (PPh/PPN Ratio > 2.0) yang tidak wajar untuk ukuran usahanya. Bisa jadi WP sedang mengklaim biaya impor sebagai pengurang penghasilan kena pajak secara tidak wajar.

**Indikator yang digunakan:**
- PPh/PPN Ratio **sangat tinggi** (> 2.0) — Risk Flag: `PPH_ANOMALI_TINGGI`

> **Contoh:** HS `23011000` (Tepung dari daging) — PPh/PPN Ratio = 2.85. Artinya PPh yang dibayar 2.85× lebih besar dari PPN impor. Ini tidak wajar untuk importir biasa.

---

#### `Konsentrasi_Importir` — HS Code yang Didominasi Sedikit Importir

**Apa itu?** Barang-barang strategis yang impornya dikuasai hanya oleh 1-5 perusahaan. Konsentrasi tinggi meningkatkan risiko:
- Pengaturan harga (kartel)
- Transfer pricing dengan induk perusahaan di luar negeri
- Pemanfaatan fasilitas bea masuk secara tidak tepat

---

#### `Mismatch_Lintas_Sektor` — KLU Tidak Sesuai Klaster Barang

**Apa itu?** WP yang mengimpor barang dari klaster tertentu tetapi memiliki KLU yang sama sekali tidak relevan dengan klaster tersebut.

**Contoh nyata dari data:**
| Barang Diimpor | KLU WP | Masalah |
|---------------|--------|---------|
| Gandum (Pangan Ch.10) | Industri Minyak Kelapa Sawit | Importir gandum tapi usahanya minyak sawit |
| Peralatan Elektronik (Ch.85) | Pertambangan Batu Bara | Importir elektronik tapi usahanya pertambangan |

**Kolom kunci di sheet ini:**

| Kolom | Penjelasan |
|-------|-----------|
| **Cluster HS** | Klaster yang seharusnya sesuai dengan HS Code ini |
| **Keterangan Mismatch** | Penjelasan singkat mengapa dianggap tidak wajar |

---

## 7. File 05 — Catatan Data Tambahan

**Nama file:** `05_Catatan_Data_Tambahan.xlsx`

### Sheet `Kualitas_Data`
Ringkasan statistik kualitas data yang digunakan dalam analisis — jumlah total HS Code unik, total KLU unik, dll. Berguna untuk memvalidasi kelengkapan data.

### Sheet `HS_Terkonsentrasi`
Daftar HS Code yang memiliki pola konsentrasi importir ekstrem — satu atau dua perusahaan mendominasi hampir seluruh impor suatu komoditas. Ini adalah kandidat prioritas untuk program **Joint Audit DJBC-DJP**.

| Kolom | Penjelasan |
|-------|-----------|
| **PPN per NPWP** | PPN rata-rata per importir — nilai ekstrem menunjukkan dominasi |
| **Risk Flags** | `TERKONSENTRASI` = satu/dua importir kuasai > 70% total PPN HS Code ini |

---

## 8. Panduan Membaca Risk Score & Risk Flags

### Risk Score
Skala 0.0–1.0 dihitung dari kombinasi beberapa indikator.

| Rentang | Interpretasi | Tindakan |
|---------|-------------|---------|
| `0.00–0.20` | Risiko rendah | Monitor rutin |
| `0.20–0.40` | Risiko sedang | Waspadai, masuk watchlist |
| `0.40–0.60` | Risiko tinggi | Prioritas analisis mendalam |
| `0.60–1.00` | Risiko sangat tinggi | Prioritas pemeriksaan segera |

### Risk Flags (Label Teknis)

| Flag | Kondisi Pemicu | Makna |
|------|---------------|-------|
| `DISPERSI_TINGGI` | # KLU Unik > 100 | Barang diimpor oleh sangat banyak jenis usaha berbeda → ambiguitas tinggi |
| `CATCH_ALL` | HS Code berdeskripsi "Lain-lain" | Rawan digunakan untuk menyembunyikan jenis barang sebenarnya |
| `PPH_ANOMALI_RENDAH` | PPh/PPN Ratio < 0.05 | PPh hampir nol padahal impor besar → WP tidak menghasilkan laba dari kegiatan impor ini |
| `PPH_ANOMALI_TINGGI` | PPh/PPN Ratio > 2.0 | PPh jauh lebih besar dari PPN → kemungkinan klaim biaya tidak wajar |
| `TERKONSENTRASI` | < 5 importir kuasai > 70% PPN | Monopoli/oligopoli importir — berisiko transfer pricing |

### Risk Events (Jenis Pelanggaran Terindikasi)

| Risk Event | Peraturan Terkait | Penjelasan |
|------------|-------------------|-----------|
| **Misdeclaration** | PMK Bea Masuk, BTKI | Salah klasifikasi barang saat PIB — bea masuk seharusnya lebih tinggi |
| **Mispricing** | PMK 213/2016 (Transfer Pricing) | Harga impor tidak mencerminkan arm's length price |
| **API-P Abuse** | Permendag API | Importir produsen mengimpor bukan untuk produksi sendiri |
| **Artificial Loss** | UU PPh Pasal 6 | Klaim biaya impor tidak wajar untuk memperkecil laba kena pajak |
| **Konsentrasi Importir** | KPPU, Transfer Pricing | Sedikit perusahaan menguasai komoditas strategis |

---

## 9. Panduan Membaca Dispersi KLU

**Dispersi KLU** mengukur berapa banyak jenis usaha (KLU) berbeda yang mengimpor satu jenis barang (HS Code).

| Kategori | Jumlah KLU Unik | Interpretasi | Implikasi |
|----------|----------------|-------------|-----------|
| **A - Sangat Sempit** | 1 KLU | Hanya satu jenis usaha | Barang sangat spesifik/unik |
| **B - Sempit** | 2–5 KLU | Beberapa jenis usaha serumpun | Normal untuk barang khusus |
| **C - Sedang** | 6–10 KLU | Barang digunakan lintas sektor | Perlu perhatian |
| **D - Lebar** | 11–20 KLU | Barang multiguna | Waspadai klasifikasi |
| **E - Sangat Lebar** | 21–50 KLU | Barang sangat generik | Risiko misdeclaration |
| **F - Ekstrem** | 51–100 KLU | Hampir tidak ada kekhususan | Risiko tinggi |
| **G - Kritis** | > 100 KLU | Catch-all de facto | **Prioritas investigasi** |

> **Analogi:** Bayangkan HS Code `39269099` ("Barang plastik lain-lain") diimpor oleh 578 jenis usaha berbeda — dari pabrik elektronik, rumah sakit, hingga perkebunan. Ini menunjukkan kode ini digunakan sebagai "tempat sampah" untuk mengimpor barang plastik apapun tanpa harus mencantumkan kode yang lebih spesifik.

---

## 10. Alur Kerja yang Disarankan

### Untuk AR/Pemeriksa yang Baru Menggunakan Dashboard

```
1. Buka Hasil Analisa → File 04 → Top100_Risk_Score
   └─ Identifikasi 10 HS Code dengan skor tertinggi di klaster Anda

2. Klik ke sheet spesifik (Misdeclaration / Mispricing / dll.)
   └─ Pahami jenis risiko yang paling dominan

3. Buka File 03 → Anomali_Saja
   └─ Temukan pasangan HS-KLU spesifik yang anomali untuk HS Code prioritas

4. Buka File 01 → sheet klaster Anda
   └─ Baca kolom "Justifikasi Scope" untuk konteks tambahan

5. Buka SR15 Enhanced Dashboard
   └─ Filter NM_KELOMPOK atau KD_KLU spesifik
   └─ Identifikasi NPWP individual yang perlu ditindaklanjuti
```

### Prioritas Lintas Dimensi (Untuk Kasus Paling Kuat)

Sebuah HS Code layak menjadi **prioritas pemeriksaan tertinggi** apabila memenuhi **3 atau lebih** kondisi berikut:

- [ ] Risk Score > 0.5
- [ ] Catch-all = True
- [ ] Dispersi KLU ≥ E (> 20 KLU unik)
- [ ] PPh/PPN Ratio < 0.05 atau > 2.0
- [ ] Muncul di > 2 sheet Rekomendasi Prioritas
- [ ] Nilai PPN total > Rp 1 triliun

---

*Dokumen ini diperbarui per 2026. Untuk pertanyaan metodologi, hubungi CRM Subtim Data Analyst.*
*Dashboard: http://[IP-Server]:8050 | Login: user/yauser*
