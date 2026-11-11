"""Dasbor Bisnis 2M Sembako (Streamlit).

Jalankan lokal :  streamlit run dashboard/app.py
Sumber data    :  bawaan dashboard/data/*.csv (SINTETIS). Ganti tanpa ubah kode lewat (a) unggah CSV di sidebar, atau
                  (b) variabel lingkungan / secrets DASH_ORDER_CSV dan DASH_ITEM_CSV (path atau URL CSV).
Autentikasi    :  atur DASH_JWT_SECRET untuk mewajibkan token JWT (?token=...) dari admin web; tanpa itu = MODE DEMO.
"""
import os
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import auth as A
import logic as L

AKAR = Path(__file__).resolve().parent
DATA, TEMPLATE = AKAR / "data", AKAR / "template"

st.set_page_config(page_title="Dasbor 2M Sembako", page_icon="📦", layout="wide", initial_sidebar_state="expanded")


def kirim_status(jenis, pesan=""):
    """Memberi tahu halaman induk (admin web) bahwa dasbor siap/gagal. Halaman 'app tidur' tidak pernah mengirim ini,
    sehingga admin web dapat menampilkan state galat. Lihat embed/DashboardEmbed.tsx."""
    pesan = str(pesan).replace("'", " ").replace("\n", " ")[:200]
    components.html(f"<script>try{{window.top.postMessage({{type:'2m-dashboard-{jenis}',pesan:'{pesan}'}},'*')}}catch(e){{}}</script>", height=0)


def rahasia(nama):
    v = os.environ.get(nama)
    if v:
        return v
    try:
        return st.secrets.get(nama)
    except Exception:
        return None


def rp(x):
    return "-" if x is None or pd.isna(x) else ("-" if x < 0 else "") + "Rp" + f"{abs(x):,.0f}".replace(",", ".")


def angka(x, d=0, satuan=""):
    return "-" if x is None or pd.isna(x) else f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".") + satuan


@st.cache_data(ttl=300, show_spinner="Memuat data...")
def muat_sumber(sumber_order, sumber_item):
    o, lo = L.validasi_order(L.baca_csv(sumber_order))
    if o is None:
        return None, None, lo, L.Laporan()
    if not sumber_item:
        return o, None, lo, L.Laporan()
    i, li = L.validasi_item(L.baca_csv(sumber_item), o["order_id"])
    return o, i, lo, li


@st.cache_data(show_spinner="Memeriksa berkas unggahan...")
def muat_unggahan(byte_order, byte_item):
    import io
    o, lo = L.validasi_order(L.baca_csv(io.BytesIO(byte_order)))
    if o is None:
        return None, None, lo, L.Laporan()
    if not byte_item:
        return o, None, lo, L.Laporan()
    i, li = L.validasi_item(L.baca_csv(io.BytesIO(byte_item)), o["order_id"])
    return o, i, lo, li


def utama():
    # ---------------- autentikasi (opsional tapi WAJIB sebelum data asli)
    secret, klaim = rahasia("DASH_JWT_SECRET"), None
    if secret:
        try:
            klaim = A.verifikasi(st.query_params.get("token"), secret)
        except A.ErrorAuth as e:
            st.error(f"Akses ditolak: {e}")
            kirim_status("galat", str(e))
            st.stop()
    else:
        st.warning("MODE DEMO: tanpa autentikasi. Hanya untuk data sintetis. Atur DASH_JWT_SECRET sebelum memakai data asli.")

    # ---------------- sumber data
    src_o = rahasia("DASH_ORDER_CSV") or str(DATA / "order_contoh.csv")
    src_i = rahasia("DASH_ITEM_CSV") or str(DATA / "item_contoh.csv")
    o, i, lo, li = muat_sumber(src_o, src_i)
    sumber_label = "bawaan/terkoneksi"
    with st.sidebar:
        st.header("Perbarui data")
        with st.expander("Unggah CSV (tanpa ubah kode)", expanded=False):
            up_o = st.file_uploader("CSV order (wajib)", type="csv", key="up_o")
            up_i = st.file_uploader("CSV item/SKU (opsional)", type="csv", key="up_i")
            for nama, f in (("template_order.csv", TEMPLATE / "template_order.csv"), ("template_item.csv", TEMPLATE / "template_item.csv")):
                if f.exists():
                    st.download_button(f"Unduh {nama}", f.read_bytes(), file_name=nama, mime="text/csv", key="dl_" + nama)
            if up_o is not None:
                try:
                    o2, i2, lo2, li2 = muat_unggahan(up_o.getvalue(), up_i.getvalue() if up_i is not None else None)
                except L.ErrorData as e:      # berkas rusak/bukan CSV: tolak unggahan, jangan jatuhkan seluruh dasbor
                    o2, i2, lo2, li2 = None, None, L.Laporan(galat=[str(e)]), L.Laporan()
                if o2 is None or not lo2.ok or not li2.ok:
                    for g in lo2.galat + li2.galat:
                        st.error(g)
                    st.warning("Unggahan ditolak; dasbor tetap memakai data sebelumnya.")
                else:
                    o, i, lo, li, sumber_label = o2, i2, lo2, li2, "unggahan Anda (hanya sesi ini)"
                    st.success("Unggahan diterima.")
        if o is None:
            st.error("Data order tidak bisa dimuat.")
        st.header("Filter")

    if o is None:
        for g in lo.galat:
            st.error(g)
        kirim_status("galat", "data tidak bisa dimuat")
        st.stop()

    # ---------------- filter (cabang dibatasi token, bukan input pengguna)
    semua = sorted(o["cabang_id"].unique())
    boleh = A.cabang_diizinkan(klaim, semua)
    if not boleh:
        st.error("Tidak ada cabang yang dapat Anda lihat pada data ini.")
        kirim_status("galat", "tidak ada cabang")
        st.stop()
    with st.sidebar:
        if klaim is not None and klaim["role"] == "branch_admin":
            st.markdown(f"Cabang: **{boleh[0]}**")
            pilih_cabang = boleh
        else:
            pilih_cabang = st.multiselect("Cabang", boleh, default=boleh) or boleh
        tmin, tmax = o["tanggal"].min().date(), o["tanggal"].max().date()
        rentang = st.date_input("Periode", value=(tmin, tmax), min_value=tmin, max_value=tmax)
        a, b = (rentang[0], rentang[-1]) if isinstance(rentang, (tuple, list)) and len(rentang) else (tmin, tmax)
        pilih_sku = []
        if i is not None:
            kat = st.multiselect("Kategori", sorted(i["kategori"].unique()))
            sk = i[i["kategori"].isin(kat)] if kat else i
            peta = {f"{r.sku_id} - {r.sku_nama}": r.sku_id for r in sk[["sku_id", "sku_nama"]].drop_duplicates().sort_values("sku_id").itertuples()}
            pilih_sku = [peta[x] for x in st.multiselect("SKU (kosong = semua)", list(peta))]
        st.header("Asumsi")
        biaya = st.number_input("Biaya cabang per antaran (Rp)", value=float(round(L.BIAYA_CABANG_DEFAULT, 2)), min_value=0.0, step=50.0,
                                help="Overhead harian cabang dibagi throughput. Asumsi tim (tingkat D), bukan data aktual.")

    of, i_f = L.filter_data(o, i, pilih_cabang, a, b, pilih_sku)

    st.title("Dasbor Bisnis 2M Sembako")
    if L.apakah_sintetis(o):
        st.warning("DATA SINTETIS / CONTOH: angka di bawah bukan transaksi nyata dan tidak boleh dipakai sebagai dasar keputusan bisnis.")
    st.caption(f"Sumber data: {sumber_label} · {len(o):,} order dimuat".replace(",", ".")
               + (" · filter SKU: order yang memuat minimal satu SKU terpilih; omzet hanya dari SKU terpilih" if pilih_sku else ""))
    if len(of) == 0:
        st.info("Tidak ada data untuk kombinasi filter ini. Ubah cabang, periode, atau SKU.")
        kirim_status("siap")
        st.stop()

    k = L.hitung_kpi(of, i_f, biaya)
    c = st.columns(6)
    c[0].metric("Total order", angka(k["n_order"]))
    c[1].metric("Order gagal", angka(k["persen_gagal"], 1, "%"), help="Pelanggan tidak ada saat kurir tiba")
    c[2].metric("ETA rata-rata", angka(k["eta_rata"], 1, " mnt"), help="Penugasan sampai kurir tiba")
    c[3].metric("Kantong 2M / order", rp(k["kantong_rata"]), help="Ongkir diterima - bayar kurir - biaya cabang. Negatif = 2M menombok")
    c[4].metric("Order rugi", angka(k["persen_rugi"], 1, "%"), help="Porsi order dengan kantong 2M negatif")
    c[5].metric("Omzet barang", rp(k["omzet"]) if k["omzet"] is not None else "-", help="Butuh berkas item/SKU")
    if k["margin_persen"] is not None:
        st.caption(f"Margin kotor barang: {angka(k['margin_persen'], 1, '%')} · Nilai per order: {rp(k['nilai_per_order'])}")

    t1, t2, t3, t4, t5 = st.tabs(["Ringkasan", "Operasional", "Keuangan 2M", "SKU", "Data"])
    with t1:
        tr = L.tren_harian(of)
        st.subheader("Order per hari")
        st.line_chart(tr.set_index("tanggal")[["order", "gagal"]])
        st.subheader("Ringkasan per cabang")
        st.dataframe(L.per_cabang(of, biaya), use_container_width=True, hide_index=True)
    with t2:
        pc = L.per_cabang(of, biaya).set_index("cabang_id")
        x1, x2 = st.columns(2)
        x1.subheader("ETA rata-rata per cabang (menit)")
        x1.bar_chart(pc["eta_rata_menit"])
        x2.subheader("Order gagal per cabang (%)")
        x2.bar_chart(pc["persen_gagal"])
        st.subheader("Sebaran jarak")
        st.bar_chart(of["kelas_jarak"].value_counts().reindex(L.KELAS_JARAK).fillna(0))
    with t3:
        kj = L.kantong_per_kelas_jarak(of, biaya)
        st.subheader("Kantong 2M rata-rata per kelas jarak (Rp)")
        st.bar_chart(kj.set_index("kelas_jarak")["kantong_rata_rp"])
        st.dataframe(kj, use_container_width=True, hide_index=True)
        st.caption("Model biaya tim menaksir titik impas sekitar 2,14 km pada skema upah dan ongkir saat ini (lihat laporan analisis).")
    with t4:
        if i_f is None:
            st.info("Unggah berkas item/SKU untuk melihat SKU, omzet, dan margin.")
        else:
            ts = L.top_sku(i_f, 10)
            st.subheader("10 SKU teratas menurut omzet")
            st.bar_chart(ts.set_index("sku_nama")["omzet_rp"])
            st.dataframe(ts, use_container_width=True, hide_index=True)
    with t5:
        st.subheader("Laporan validasi data")
        for pesan in lo.info + li.info:
            st.write("• " + pesan)
        for pesan in lo.peringatan + li.peringatan:
            st.warning(pesan)
        st.subheader("Order terfilter (maks 500 baris)")
        kolom = ["order_id", "tanggal", "cabang_id", "status_order", "jarak_rute_km", "eta_menit", "ongkir_diterima_rp", "bayar_kurir_rp"]
        st.dataframe(of[kolom].head(500), use_container_width=True, hide_index=True)
        st.download_button("Unduh order terfilter (CSV)", of[kolom].to_csv(index=False).encode("utf-8"), file_name="order_terfilter.csv", mime="text/csv")
    kirim_status("siap")


try:
    utama()
except Exception as e:  # noqa: BLE001  - state galat yang ramah; StopException (st.stop) bukan Exception sehingga tidak tertangkap
    st.error(f"Dasbor gagal dimuat: {e}")
    kirim_status("galat", e)
