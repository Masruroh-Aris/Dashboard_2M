# Dasbor Bisnis 2M Sembako (Streamlit)
*Side Quest DS · Owner: Ida, Dian · Embed: Alga, Zoel · Data: **SINTETIS_SIMULASI** (harga/HPP SKU adalah angka ilustrasi)*

## Status terhadap acceptance criteria
| Kriteria | Status | Bukti dan batasan |
|---|---|---|
| ≥4 indikator bisnis dengan filter | ✅ kode siap | 6 indikator; filter cabang, periode, kategori, SKU. Logika data **27/27 uji lolos**; alur `app.py` **20/20 skenario lolos pada STUB Streamlit**. **Belum dijalankan di Streamlit asli** (tidak terpasang di lingkungan pembuat). |
| Data dapat diperbarui tanpa ubah kode | ✅ kode siap | Unggah CSV di sidebar, atau `DASH_ORDER_CSV`/`DASH_ITEM_CSV` (path/URL). Validasi dan penolakan unggahan salah teruji (logika + stub). |
| Dasbor terbuka dari dalam admin web | ⏳ **belum** | Komponen `embed/DashboardEmbed.tsx` siap dan lolos **9/9 uji di Chromium** terhadap dasbor palsu; **belum di-deploy dan belum dipasang** di admin web. |

**Langkah pertama yang wajib dilakukan manusia:** jalankan `streamlit run dashboard/app.py` sekali dan klik semua filter. Uji stub tidak menggantikan itu.

## Indikator dan filter
| Indikator | Definisi |
|---|---|
| Total order, tren harian | jumlah order per hari |
| Order gagal (%) | pelanggan tidak ada saat kurir tiba |
| ETA rata-rata | `tiba_at − ditugaskan_at` |
| Kantong 2M per order, % order rugi | `ongkir_diterima − bayar_kurir − biaya_cabang`; indikator titik impas ongkir |
| Omzet barang, margin kotor, 10 SKU teratas | dari berkas item (butuh HPP untuk margin) |
Filter: **cabang** (multi), **periode**, **kategori**, **SKU**. Filter SKU berarti: order yang memuat minimal satu SKU terpilih; omzet hanya dari SKU terpilih. Biaya cabang per antaran (Rp666,67) adalah asumsi tim yang bisa diubah di sidebar.

## Menjalankan
```bash
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
python dashboard/test_logic.py        # uji logika (butuh paket proyek lengkap)
python dashboard/test_app_stub.py     # uji alur app.py dengan Streamlit tiruan
```

## Memperbarui data tanpa ubah kode
1. **Unggah:** sidebar → "Unggah CSV". Template: `dashboard/template/`. Unggahan hanya berlaku di sesi itu; berkas salah ditolak dengan pesan dan data sebelumnya tetap dipakai.
2. **Sumber tersambung:** atur `DASH_ORDER_CSV` dan `DASH_ITEM_CSV` (path atau URL) di Secrets/environment; cache 5 menit.

Kolom **order** wajib: `order_id, ditugaskan_at, tiba_at, kembali_at, cabang_id, status_order, jarak_rute_km, ongkir_diterima_rp, bayar_kurir_rp` (opsional `jumlah_item, sumber_data`). Waktu berformat `YYYY-MM-DD HH:MM:SS` (format lain ditolak karena dd/mm vs mm/dd ambigu). `status_order`: `berhasil` / `gagal_pelanggan_tidak_ada`. Kolom **item** wajib: `order_id, sku_id, qty, harga_satuan_rp` (opsional `hpp_satuan_rp, sku_nama, kategori`).

## Deploy (Streamlit Community Cloud)
1. Dorong repo ke GitHub (**jangan** menaruh data asli di repo publik). 2. Buat app baru, *main file* `dashboard/app.py`, letakkan `requirements.txt` di folder yang sama. 3. Isi **Secrets**: `DASH_JWT_SECRET` (acak, ≥32 karakter) dan, bila perlu, `DASH_ORDER_CSV`/`DASH_ITEM_CSV`. 4. Salin `dashboard/.streamlit/config.toml` ke akar repo bila pengaturannya tidak terbaca.

## Embed di admin web
```html
<iframe src="https://NAMA-APP.streamlit.app/?embed=true&token=JWT" title="Dasbor 2M"></iframe>
```
Pakai komponen `embed/DashboardEmbed.tsx` (state memuat/siap/galat, Coba lagi, buka di tab baru) dan contoh token di `embed/contoh_penggunaan.md`. Dasbor mengirim `postMessage` (`2m-dashboard-siap`/`-galat`) ke halaman induk; tanpa sinyal dalam batas waktu, admin web menampilkan state galat.

### Risiko hibernasi (dari laporan pengguna di forum Streamlit, bukan dokumentasi resmi)
Aplikasi di Community Cloud dilaporkan tidur setelah sekitar 12 jam tanpa kunjungan, dan **tombol "bangunkan" dilaporkan tidak berfungsi di dalam iframe**. Konsekuensi: pagi hari, dasbor bisa tampak mati di admin web. Pilihan: (a) terima dan andalkan state galat + "Buka di tab baru"; (b) jadwalkan commit kosong berkala (saran di forum; ada laporan tetap tertidur); (c) host di tempat lain. Putuskan sebelum demo.

## Keamanan (wajib dibaca)
- Tanpa `DASH_JWT_SECRET`, dasbor berjalan **MODE DEMO tanpa autentikasi**; hanya aman untuk data sintetis.
- Dengan secret, dasbor menuntut JWT HS256 berumur pendek dari backend admin web. **Cabang dibatasi dari klaim `branch_id` di token**, bukan dari pilihan pengguna (teruji: branch_admin C03 hanya melihat C03 walau mencoba memilih cabang lain). Tanpa ini, URL dasbor melewati RBAC admin web.
- `branch_id` di token harus sama dengan nilai `cabang_id` di data. Token di URL tercatat di riwayat/log; karena itu umurnya pendek.

## Yang diuji dan yang tidak
| Diuji | Tidak diuji |
|---|---|
| KPI vs hitungan independen dari log bersih; semua kombinasi filter; validasi unggahan kotor; auth (kedaluwarsa, tanda tangan salah, `alg=none`, peran) | Perilaku nyata Streamlit (widget, cache, tata letak, performa di Cloud) |
| Alur `app.py` penuh pada stub (demo, filter, unggah, auth) | Embed ke admin web sungguhan; hibernasi sungguhan |
| Komponen embed di Chromium vs halaman palsu | Sinyal `postMessage` dari iframe komponen Streamlit asli (asal pesan bisa `null`; komponen menerima keduanya) |
