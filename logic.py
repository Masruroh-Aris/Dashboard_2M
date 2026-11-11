"""Logika data dasbor 2M Sembako (murni pandas, TANPA Streamlit) agar bisa diuji penuh di luar UI.

Alur: baca CSV -> validasi + bersihkan (laporan galat/peringatan) -> filter -> KPI/seri untuk grafik.
Kontrak kolom unggahan ada di README dasbor.
"""
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

ORDER_WAJIB = ["order_id", "ditugaskan_at", "tiba_at", "kembali_at", "cabang_id", "status_order", "jarak_rute_km", "ongkir_diterima_rp", "bayar_kurir_rp"]
ITEM_WAJIB = ["order_id", "sku_id", "qty", "harga_satuan_rp"]
KELAS_JARAK = ["0-2 km", "2-4 km", ">4 km"]
BATAS_JARAK_KM = 50
GAGAL = "gagal_pelanggan_tidak_ada"
BIAYA_CABANG_DEFAULT = 10000 / 15      # overhead harian cabang / throughput (asumsi tim, tingkat D)


class ErrorData(Exception):
    pass


@dataclass
class Laporan:
    galat: list = field(default_factory=list)
    peringatan: list = field(default_factory=list)
    info: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.galat


def baca_csv(sumber):
    """sumber: path, URL, atau objek file (mis. hasil st.file_uploader)."""
    try:
        d = pd.read_csv(sumber, sep=None, engine="python", encoding="utf-8-sig")
    except Exception as e:
        raise ErrorData(f"Berkas tidak bisa dibaca sebagai CSV: {e}")
    d.columns = [str(c).strip().lower() for c in d.columns]
    return d


def _angka(s, rupiah=False):
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce")
    t = s.astype(str).str.strip().str.replace(r"(?i)rp\.?|\s", "", regex=True)
    if rupiah:   # '7.500' atau '1.250.000' = pemisah ribuan gaya Indonesia
        t = t.where(~t.str.match(r"^\d{1,3}(\.\d{3})+(,\d+)?$"), t.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    t = t.str.replace(",", ".", regex=False)
    return pd.to_numeric(t, errors="coerce")


def _waktu(s):
    return pd.to_datetime(s, errors="coerce", format="ISO8601")


def validasi_order(df):
    lap = Laporan()
    d = df.copy(); d.columns = [str(c).strip().lower() for c in d.columns]
    hilang = [c for c in ORDER_WAJIB if c not in d.columns]
    if hilang:
        lap.galat.append("Kolom wajib tidak ada: " + ", ".join(hilang)); return None, lap
    n0 = len(d)
    d["order_id"] = d["order_id"].astype(str).str.strip()
    dup = int(d["order_id"].duplicated().sum())
    if dup:
        d = d.drop_duplicates("order_id"); lap.peringatan.append(f"{dup} baris order_id ganda dibuang (yang pertama dipertahankan).")
    for c in ["ditugaskan_at", "tiba_at", "kembali_at"]:
        d[c] = _waktu(d[c])
    bad = int(d["ditugaskan_at"].isna().sum())
    if bad:
        lap.peringatan.append(f"{bad} baris dibuang: ditugaskan_at kosong atau bukan format YYYY-MM-DD HH:MM:SS."); d = d[d["ditugaskan_at"].notna()]
    nt = int(d[["tiba_at", "kembali_at"]].isna().any(axis=1).sum())
    if nt:
        lap.peringatan.append(f"{nt} baris tanpa tiba_at/kembali_at yang valid: dikeluarkan dari hitungan waktu saja.")
    d["jarak_rute_km"] = _angka(d["jarak_rute_km"])
    for c in ["ongkir_diterima_rp", "bayar_kurir_rp"]:
        d[c] = _angka(d[c], rupiah=True)
        k = int(d[c].isna().sum())
        if k: lap.peringatan.append(f"{k} baris {c} kosong/tidak terbaca: dikeluarkan dari hitungan uang.")
    luar = (d["jarak_rute_km"] <= 0) | (d["jarak_rute_km"] > BATAS_JARAK_KM) | d["jarak_rute_km"].isna()
    if luar.any():
        lap.peringatan.append(f"{int(luar.sum())} baris jarak_rute_km tidak valid (kosong, <=0, atau >{BATAS_JARAK_KM} km): jarak dikosongkan."); d.loc[luar, "jarak_rute_km"] = np.nan
    s = d["status_order"].astype(str).str.strip().str.lower()
    nonkanon = int((~s.isin(["berhasil", GAGAL])).sum())
    if nonkanon: lap.peringatan.append(f"{nonkanon} baris status_order memakai label tidak baku; yang mengandung 'gagal' dihitung gagal, sisanya berhasil.")
    d["status_order"] = np.where(s.str.contains("gagal"), GAGAL, "berhasil"); d["gagal"] = (d["status_order"] == GAGAL).astype(int)
    d["cabang_id"] = d["cabang_id"].astype(str).str.strip().str.upper()
    d["tanggal"] = d["ditugaskan_at"].dt.normalize()
    d["eta_menit"] = (d["tiba_at"] - d["ditugaskan_at"]).dt.total_seconds() / 60
    d["waktu_antaran_menit"] = (d["kembali_at"] - d["ditugaskan_at"]).dt.total_seconds() / 60
    neg = int(((d["eta_menit"] < 0) | (d["waktu_antaran_menit"] < 0)).sum())
    if neg:
        lap.peringatan.append(f"{neg} baris urutan waktu salah (tiba/kembali sebelum penugasan): waktu dikosongkan.")
        m = (d["eta_menit"] < 0) | (d["waktu_antaran_menit"] < 0); d.loc[m, ["eta_menit", "waktu_antaran_menit"]] = np.nan
    d["kelas_jarak"] = pd.cut(d["jarak_rute_km"], [0, 2, 4, np.inf], labels=KELAS_JARAK).astype(object)
    if "sumber_data" not in d.columns:
        d["sumber_data"] = "TIDAK_DIKETAHUI"; lap.info.append("Kolom sumber_data tidak ada; label 'data sintetis' tidak bisa ditampilkan otomatis.")
    if len(d) == 0:
        lap.galat.append("Tidak ada baris order yang valid setelah pembersihan."); return None, lap
    lap.info.append(f"{len(d):,} order valid dari {n0:,} baris; periode {d['tanggal'].min().date()} s.d. {d['tanggal'].max().date()}; {d['cabang_id'].nunique()} cabang.".replace(",", "."))
    return d.reset_index(drop=True), lap


def validasi_item(df, order_ids):
    lap = Laporan()
    d = df.copy(); d.columns = [str(c).strip().lower() for c in d.columns]
    hilang = [c for c in ITEM_WAJIB if c not in d.columns]
    if hilang:
        lap.galat.append("Kolom wajib tidak ada pada berkas item: " + ", ".join(hilang)); return None, lap
    d["order_id"] = d["order_id"].astype(str).str.strip(); d["sku_id"] = d["sku_id"].astype(str).str.strip()
    d["qty"] = _angka(d["qty"]); d["harga_satuan_rp"] = _angka(d["harga_satuan_rp"], rupiah=True)
    bad = int((d["qty"].isna() | (d["qty"] <= 0) | d["harga_satuan_rp"].isna() | (d["harga_satuan_rp"] < 0)).sum())
    if bad:
        lap.peringatan.append(f"{bad} baris item dibuang: qty atau harga kosong/tidak valid."); d = d[~(d["qty"].isna() | (d["qty"] <= 0) | d["harga_satuan_rp"].isna() | (d["harga_satuan_rp"] < 0))]
    yatim = ~d["order_id"].isin(set(order_ids))
    if yatim.any():
        lap.peringatan.append(f"{int(yatim.sum())} baris item merujuk order_id yang tidak ada di berkas order: dibuang."); d = d[~yatim]
    if "hpp_satuan_rp" in d.columns:
        d["hpp_satuan_rp"] = _angka(d["hpp_satuan_rp"], rupiah=True)
    else:
        d["hpp_satuan_rp"] = np.nan; lap.info.append("Kolom hpp_satuan_rp tidak ada: margin tidak dihitung.")
    d["sku_nama"] = d["sku_nama"].astype(str) if "sku_nama" in d.columns else d["sku_id"]
    d["kategori"] = d["kategori"].astype(str) if "kategori" in d.columns else "Tidak dikategorikan"
    d["omzet_rp"] = d["qty"] * d["harga_satuan_rp"]; d["hpp_rp"] = d["qty"] * d["hpp_satuan_rp"]
    if len(d) == 0:
        lap.galat.append("Tidak ada baris item yang valid."); return None, lap
    lap.info.append(f"{len(d):,} baris item valid, {d['sku_id'].nunique()} SKU.".replace(",", "."))
    return d.reset_index(drop=True), lap


def apakah_sintetis(orders):
    return bool(orders["sumber_data"].astype(str).str.upper().str.contains("SINTETIS|CONTOH|DUMMY").any())


def filter_data(orders, items, cabang, tgl_awal, tgl_akhir, sku_ids=None):
    """Filter. Bila sku_ids diisi: order = yang memuat MINIMAL SATU SKU terpilih; item = hanya baris SKU terpilih."""
    o = orders
    if cabang is not None:
        o = o[o["cabang_id"].isin(list(cabang))]
    o = o[(o["tanggal"] >= pd.Timestamp(tgl_awal)) & (o["tanggal"] <= pd.Timestamp(tgl_akhir))]
    i = None
    if items is not None:
        if sku_ids:
            ids = set(items.loc[items["sku_id"].isin(list(sku_ids)), "order_id"])
            o = o[o["order_id"].isin(ids)]
        i = items[items["order_id"].isin(set(o["order_id"]))]
        if sku_ids:
            i = i[i["sku_id"].isin(list(sku_ids))]
    return o, i


def tambah_kantong(o, biaya_cabang):
    return o.assign(kantong_2m_rp=o["ongkir_diterima_rp"] - o["bayar_kurir_rp"] - biaya_cabang)


def hitung_kpi(o, i, biaya_cabang=BIAYA_CABANG_DEFAULT):
    k = dict(n_order=int(len(o)), persen_gagal=None, eta_rata=None, eta_median=None, kantong_rata=None, kantong_total=None, persen_rugi=None,
             jarak_rata=None, omzet=None, hpp=None, margin_persen=None, nilai_per_order=None)
    if len(o) == 0:
        return k
    q = tambah_kantong(o, biaya_cabang)["kantong_2m_rp"].dropna()
    k["persen_gagal"] = float(o["gagal"].mean() * 100)
    k["eta_rata"] = None if o["eta_menit"].dropna().empty else float(o["eta_menit"].mean()); k["eta_median"] = None if o["eta_menit"].dropna().empty else float(o["eta_menit"].median())
    k["jarak_rata"] = None if o["jarak_rute_km"].dropna().empty else float(o["jarak_rute_km"].mean())
    if len(q):
        k["kantong_rata"] = float(q.mean()); k["kantong_total"] = float(q.sum()); k["persen_rugi"] = float((q < 0).mean() * 100)
    if i is not None and len(i):
        k["omzet"] = float(i["omzet_rp"].sum()); k["nilai_per_order"] = float(i["omzet_rp"].sum() / i["order_id"].nunique())
        if i["hpp_rp"].notna().all() and k["omzet"] > 0:
            k["hpp"] = float(i["hpp_rp"].sum()); k["margin_persen"] = float((k["omzet"] - k["hpp"]) / k["omzet"] * 100)
    return k


def tren_harian(o):
    if len(o) == 0:
        return pd.DataFrame(columns=["tanggal", "order", "gagal"])
    t = o.groupby("tanggal").agg(order=("order_id", "count"), gagal=("gagal", "sum"))
    return t.reindex(pd.date_range(t.index.min(), t.index.max(), freq="D"), fill_value=0).rename_axis("tanggal").reset_index()


def per_cabang(o, biaya_cabang=BIAYA_CABANG_DEFAULT):
    if len(o) == 0:
        return pd.DataFrame(columns=["cabang_id", "order", "persen_gagal", "eta_rata_menit", "kantong_rata_rp", "persen_rugi"])
    q = tambah_kantong(o, biaya_cabang); q["rugi"] = (q["kantong_2m_rp"] < 0).astype(float)
    r = q.groupby("cabang_id").agg(order=("order_id", "count"), persen_gagal=("gagal", "mean"), eta_rata_menit=("eta_menit", "mean"),
                                   kantong_rata_rp=("kantong_2m_rp", "mean"), persen_rugi=("rugi", "mean")).reset_index()
    r["persen_gagal"] *= 100; r["persen_rugi"] *= 100
    return r.round(2)


def kantong_per_kelas_jarak(o, biaya_cabang=BIAYA_CABANG_DEFAULT):
    q = tambah_kantong(o, biaya_cabang); q["rugi"] = (q["kantong_2m_rp"] < 0).astype(float)
    r = q.groupby("kelas_jarak").agg(order=("order_id", "count"), kantong_rata_rp=("kantong_2m_rp", "mean"), persen_rugi=("rugi", "mean")).reindex(KELAS_JARAK)
    r["persen_rugi"] *= 100
    return r.reset_index().round(2)


def top_sku(i, n=10):
    if i is None or len(i) == 0:
        return pd.DataFrame(columns=["sku_id", "sku_nama", "kategori", "qty", "omzet_rp", "margin_persen"])
    g = i.groupby(["sku_id", "sku_nama", "kategori"]).agg(qty=("qty", "sum"), omzet_rp=("omzet_rp", "sum"), hpp_rp=("hpp_rp", "sum")).reset_index()
    g["margin_persen"] = np.where(g["hpp_rp"].notna() & (g["omzet_rp"] > 0), (g["omzet_rp"] - g["hpp_rp"]) / g["omzet_rp"] * 100, np.nan)
    return g.drop(columns="hpp_rp").sort_values("omzet_rp", ascending=False).head(n).round(2).reset_index(drop=True)
