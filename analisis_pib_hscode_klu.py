"""
Mesin Analisis PIB x HS Code x KLU
===================================
Referensi: Presentasi_Eksplorasi_PIB_HSCode_KLU_24022026.html
Tim: Subtim Data Analyst CRM - Specific Risk Importir Umum 2026

Output (Slide 9 Deliverables):
  01_HS_Code_Final_per_Klaster.xlsx   - Daftar HS Code per klaster + justifikasi
  02_Profil_HS_Code.xlsx              - Profil ringkasan per HS Code
  03_Matriks_Sinkronisasi_HS_KLU.xlsx - Kombinasi wajar vs anomali
  04_Rekomendasi_Prioritas.xlsx       - HS Code prioritas per risk event
  05_Catatan_Data_Tambahan.xlsx       - Kebutuhan data lanjutan

Penggunaan:
  python analisis_pib_hscode_klu.py
  python analisis_pib_hscode_klu.py --input sample_2023.xlsx --output output/
"""

import argparse
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------
# KONFIGURASI KLASTER
# ---------------------------------------------
CLUSTERS = {
    "Elektronik (Ch.85)":       {"chapters": list(range(85, 86)), "color": "4472C4"},
    "Otomotif (Ch.87)":         {"chapters": list(range(87, 88)), "color": "ED7D31"},
    "Kimia/Farmasi (Ch.28-38)": {"chapters": list(range(28, 39)), "color": "70AD47"},
    "Pangan (Ch.10-11)":        {"chapters": list(range(10, 12)), "color": "9370DB"},
}

# ---------------------------------------------
# KONFIGURASI RISK EVENT
# ---------------------------------------------
RISK_EVENTS = [
    "Misdeclaration",
    "Mispricing",
    "API-P Abuse",
    "Artificial Loss",
    "Konsentrasi Importir",
]

# Threshold
DISPERSION_HIGH  = 100   # KLU unik per HS -> flag merah
DISPERSION_MED   = 50    # KLU unik per HS -> flag kuning
CONCENTRATION_N  = 10    # NPWP <= ini = terkonsentrasi
PPH_PPN_HIGH     = 2.0   # ratio PPh/PPN > ini = anomali tinggi
PPH_PPN_LOW      = 0.05  # ratio PPh/PPN < ini = anomali rendah
PPN_MATERIAL     = 1e9   # Rp 1 Miliar - ambang batas materialitas


# =============================================
# HELPER FUNCTIONS
# =============================================

def assign_cluster(chapter: int) -> str:
    for name, cfg in CLUSTERS.items():
        if chapter in cfg["chapters"]:
            return name
    return "Lainnya"


def rp_miliar(val: float) -> str:
    """Format angka ke Rp Miliar."""
    return f"Rp {val/1e9:,.2f} M"


def fmt_pct(val: float) -> str:
    return f"{val*100:.1f}%"


def risk_flag(row) -> str:
    flags = []
    if row.get("n_klu", 0) > DISPERSION_HIGH:
        flags.append("DISPERSI_TINGGI")
    if row.get("n_npwp", 999) <= CONCENTRATION_N:
        flags.append("TERKONSENTRASI")
    if row.get("pph_ppn_ratio", 0) > PPH_PPN_HIGH:
        flags.append("PPH_ANOMALI_TINGGI")
    if 0 < row.get("pph_ppn_ratio", 1) < PPH_PPN_LOW and row.get("ppn", 0) > PPN_MATERIAL:
        flags.append("PPH_ANOMALI_RENDAH")
    if row.get("is_lainlain", False):
        flags.append("CATCH_ALL")
    return " | ".join(flags) if flags else "-"


def risk_event_classify(row) -> list:
    events = []
    if row.get("n_klu", 0) > DISPERSION_MED or row.get("is_lainlain", False):
        events.append("Misdeclaration")
    if row.get("n_npwp", 999) <= CONCENTRATION_N and row.get("ppn", 0) > PPN_MATERIAL * 10:
        events.append("Mispricing")
    if row.get("pph_ppn_ratio", 0) > PPH_PPN_HIGH:
        events.append("Artificial Loss")
    if 0 < row.get("pph_ppn_ratio", 1) < PPH_PPN_LOW and row.get("ppn", 0) > PPN_MATERIAL:
        events.append("API-P Abuse")
    if row.get("n_npwp", 999) <= CONCENTRATION_N:
        events.append("Konsentrasi Importir")
    return events if events else ["-"]


def score_risk(row) -> float:
    """Skor risiko gabungan [0-1]."""
    max_klu = row.get("_max_klu", 500)
    max_ppn = row.get("_max_ppn", 1e13)
    max_npwp = row.get("_max_npwp", 5000)

    s_disp  = min(row.get("n_klu",  0) / max_klu,  1.0) * 0.25
    s_value = min(row.get("ppn",    0) / max_ppn,  1.0) * 0.40
    s_conc  = (1 - min(row.get("n_npwp", max_npwp) / max_npwp, 1.0)) * 0.10
    s_lain  = 0.25 if row.get("is_lainlain", False) else 0.0
    return round(s_disp + s_value + s_conc + s_lain, 4)


# =============================================
# LOAD & PREPARE DATA
# =============================================

def load_data(path: str) -> pd.DataFrame:
    print(f"[1/6] Memuat data: {path}")
    ext = Path(path).suffix.lower()
    if ext in (".xlsx", ".xls"):
        # Auto-detect sheet yang berisi kolom POS_TARIF_HS
        xl = pd.ExcelFile(path)
        sheet = xl.sheet_names[0]
        for sh in xl.sheet_names:
            cols = xl.parse(sh, header=0, nrows=1).columns.tolist()
            if "POS_TARIF_HS" in cols:
                sheet = sh
                break
        df = pd.read_excel(path, sheet_name=sheet)
    elif ext == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError(f"Format file tidak didukung: {ext}")

    # Normalisasi tipe
    df["POS_TARIF_HS"] = pd.to_numeric(df["POS_TARIF_HS"], errors="coerce").fillna(0).astype("int64")
    df["KD_KELOMPOK"]  = pd.to_numeric(df["KD_KELOMPOK"],  errors="coerce").fillna(0).astype("int64")
    df["KD_KLU"]       = pd.to_numeric(df["KD_KLU"],       errors="coerce")
    df["PPN_DIBAYAR"]  = pd.to_numeric(df["PPN_DIBAYAR"],  errors="coerce").fillna(0)
    df["PPH_DIBAYAR"]  = pd.to_numeric(df["PPH_DIBAYAR"],  errors="coerce").fillna(0)
    df["jml_pib"]      = pd.to_numeric(df["jml_pib"],      errors="coerce").fillna(0)

    # Derivasi
    df["HS_CHAPTER"] = (df["POS_TARIF_HS"] // 1_000_000).astype(int)
    df["CLUSTER"]    = df["HS_CHAPTER"].apply(assign_cluster)
    df["IS_LAINLAIN"] = df["NM_DETIL"].str.contains("Lain-lain", na=False)
    df["HAS_KELOMPOK"] = df["KD_KELOMPOK"] != 0

    # Normalisasi NPWP: dukung format jml_npwp (count) dan NPWP (identifier)
    if "jml_npwp" in df.columns and "NPWP" not in df.columns:
        df["NPWP"] = df["jml_npwp"]   # simpan count; flag untuk agg
        df["_npwp_is_count"] = True
    else:
        df["_npwp_is_count"] = False

    npwp_display = int(df["jml_npwp"].sum()) if df["_npwp_is_count"].any() else df["NPWP"].nunique()
    print(f"    -> {len(df):,} baris | {df['POS_TARIF_HS'].nunique():,} HS | {df['KD_KLU'].nunique():,} KLU | {npwp_display:,} NPWP")
    return df


# =============================================
# AGREGASI UTAMA
# =============================================

def build_hs_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Profil ringkasan per HS Code (semua dimensi)."""
    print("[2/6] Membangun profil per HS Code...")

    # Aggregasi dasar
    npwp_agg = "sum" if df["_npwp_is_count"].any() else "nunique"
    agg = df.groupby("POS_TARIF_HS").agg(
        CLUSTER      =("CLUSTER",    "first"),
        HS_CHAPTER   =("HS_CHAPTER", "first"),
        KD_KELOMPOK  =("KD_KELOMPOK","first"),
        NM_KELOMPOK  =("NM_KELOMPOK","first"),
        KD_DETIL     =("KD_DETIL",   "first"),
        NM_DETIL     =("NM_DETIL",   "first"),
        n_klu        =("KD_KLU",     "nunique"),
        n_npwp       =("NPWP",       npwp_agg),
        n_pib        =("jml_pib",    "sum"),
        ppn          =("PPN_DIBAYAR","sum"),
        pph          =("PPH_DIBAYAR","sum"),
        is_lainlain  =("IS_LAINLAIN","any"),
        has_kelompok =("HAS_KELOMPOK","any"),
    ).reset_index()

    # Turunan
    agg["pph_ppn_ratio"]  = np.where(agg["ppn"] > 0, agg["pph"] / agg["ppn"], 0).round(4)
    agg["ppn_per_npwp"]   = (agg["ppn"] / agg["n_npwp"].clip(1)).round(0)
    agg["pib_per_npwp"]   = (agg["n_pib"] / agg["n_npwp"].clip(1)).round(2)

    # Dispersi kategori
    def disp_cat(n):
        if n == 1:   return "A - Tunggal (1)"
        if n <= 5:   return "B - Sempit (2-5)"
        if n <= 10:  return "C - Sedang (6-10)"
        if n <= 20:  return "D - Lebar (11-20)"
        if n <= 50:  return "E - Sangat Lebar (21-50)"
        if n <= 100: return "F - Perhatian (51-100)"
        return "G - Kritis (>100)"
    agg["disp_category"] = agg["n_klu"].apply(disp_cat)

    # Flag risiko
    agg["risk_flags"] = agg.apply(risk_flag, axis=1)

    # Skor risiko
    _max_klu  = agg["n_klu"].max()
    _max_ppn  = agg["ppn"].max()
    _max_npwp = agg["n_npwp"].max()
    agg["_max_klu"]  = _max_klu
    agg["_max_ppn"]  = _max_ppn
    agg["_max_npwp"] = _max_npwp
    agg["risk_score"] = agg.apply(score_risk, axis=1)
    agg.drop(columns=["_max_klu","_max_ppn","_max_npwp"], inplace=True)

    # Risk event
    agg["risk_events"] = agg.apply(lambda r: " | ".join(risk_event_classify(r)), axis=1)

    return agg.sort_values("risk_score", ascending=False).reset_index(drop=True)


def build_klu_matrix(df: pd.DataFrame, hs_profile: pd.DataFrame) -> pd.DataFrame:
    """Matriks kombinasi HS x KLU per pasangan."""
    print("[3/6] Membangun matriks sinkronisasi HS x KLU...")

    npwp_agg = "sum" if df["_npwp_is_count"].any() else "nunique"
    pairs = df.groupby(["POS_TARIF_HS","KD_KLU"]).agg(
        NM_KLU   =("NM_KLU",       "first"),
        NM_SUBGOL=("NM_SUBGOL",    "first"),
        NM_DETIL =("NM_DETIL",     "first"),
        n_npwp   =("NPWP",         npwp_agg),
        n_pib    =("jml_pib",      "sum"),
        ppn      =("PPN_DIBAYAR",  "sum"),
        pph      =("PPH_DIBAYAR",  "sum"),
    ).reset_index()

    # Total NPWP per HS
    hs_total_npwp = pairs.groupby("POS_TARIF_HS")["n_npwp"].transform("sum")
    hs_max_npwp   = pairs.groupby("POS_TARIF_HS")["n_npwp"].transform("max")
    pairs["share_npwp"]   = (pairs["n_npwp"] / hs_total_npwp.clip(1)).round(4)
    pairs["is_dominant"]  = pairs["n_npwp"] == hs_max_npwp

    # Merge cluster info
    hs_meta = hs_profile[["POS_TARIF_HS","CLUSTER","NM_KELOMPOK","n_klu","risk_score","disp_category"]].copy()
    pairs = pairs.merge(hs_meta, on="POS_TARIF_HS", how="left")

    # Label sinkronisasi
    def sync_label(row):
        if row["is_dominant"]:
            return "[OK] WAJAR - Dominan"
        if row["share_npwp"] >= 0.10:
            return "[OK] WAJAR - Signifikan"
        if row["share_npwp"] >= 0.03:
            return "~ MINOR - Perlu Review"
        if row["ppn"] >= PPN_MATERIAL * 5:
            return "[!] ANOMALI - Nilai Besar"
        return "[!] ANOMALI - Outlier"

    pairs["sinkronisasi"] = pairs.apply(sync_label, axis=1)
    pairs["pph_ppn_ratio"] = np.where(pairs["ppn"] > 0, pairs["pph"] / pairs["ppn"], 0).round(4)

    return pairs.sort_values(["POS_TARIF_HS","n_npwp"], ascending=[True, False]).reset_index(drop=True)


def build_cross_sector(df: pd.DataFrame) -> pd.DataFrame:
    """Mismatch lintas sektor: WP dengan KLU tak wajar untuk HS yang diimpor."""
    print("[4/6] Mendeteksi mismatch lintas sektor...")

    SECTOR_KEYWORDS = {
        "Elektronik (Ch.85)":       ["tambang","pertambangan","batu bara","nikel","tembaga","bauksit","minyak bumi","migas",
                                      "makanan","minuman","bumbu","kuliner","restoran","pariwisata","hiburan"],
        "Otomotif (Ch.87)":         ["makanan","minuman","pangan","pertanian","peternakan","perkebunan",
                                      "pariwisata","perhotelan","hiburan"],
        "Kimia/Farmasi (Ch.28-38)": ["pariwisata","perhotelan","hiburan","taman hiburan",
                                      "peternakan sapi","perikanan tangkap"],
        "Pangan (Ch.10-11)":        ["tambang","pertambangan","nikel","batu bara","minyak","migas",
                                      "tekstil","elektronik","konstruksi"],
    }

    rows = []
    for cluster, kws in SECTOR_KEYWORDS.items():
        mask_cl  = df["CLUSTER"] == cluster
        mask_klu = df["NM_KLU"].str.lower().str.contains("|".join(kws), na=False)
        sub = df[mask_cl & mask_klu].copy()
        if len(sub) == 0:
            continue
        npwp_agg = "sum" if df["_npwp_is_count"].any() else "nunique"
        grp = sub.groupby(["POS_TARIF_HS","KD_KLU","NM_KLU","NM_DETIL"]).agg(
            n_npwp=("NPWP", npwp_agg),
            n_pib =("jml_pib","sum"),
            ppn   =("PPN_DIBAYAR","sum"),
            pph   =("PPH_DIBAYAR","sum"),
        ).reset_index()
        grp["CLUSTER"]  = cluster
        grp["MISMATCH"] = "KLU tidak wajar untuk klaster ini"
        rows.append(grp)

    if not rows:
        return pd.DataFrame()

    result = pd.concat(rows, ignore_index=True)
    result["pph_ppn_ratio"] = np.where(result["ppn"] > 0, result["pph"] / result["ppn"], 0).round(4)
    return result.sort_values("ppn", ascending=False).reset_index(drop=True)


# =============================================
# EXCEL WRITER HELPERS
# =============================================

def make_writer(path: str):
    return pd.ExcelWriter(path, engine="xlsxwriter")


def add_header(ws, wb, title: str, subtitle: str = ""):
    fmt_title = wb.add_format({
        "bold": True, "font_size": 14, "font_color": "#FFFFFF",
        "bg_color": "#1E3A5F", "valign": "vcenter", "align": "left",
        "border": 0, "indent": 1,
    })
    fmt_sub = wb.add_format({
        "italic": True, "font_size": 9, "font_color": "#555555",
        "align": "left", "indent": 1,
    })
    ws.set_row(0, 28)
    ws.write(0, 0, title, fmt_title)
    if subtitle:
        ws.set_row(1, 16)
        ws.write(1, 0, subtitle, fmt_sub)
    return 3 if subtitle else 2


def col_formats(wb) -> dict:
    """Kumpulan format sel yang sering dipakai."""
    return {
        "header": wb.add_format({
            "bold": True, "font_size": 9, "font_color": "#FFFFFF",
            "bg_color": "#2F5597", "border": 1, "border_color": "#FFFFFF",
            "align": "center", "valign": "vcenter", "text_wrap": True,
        }),
        "header_orange": wb.add_format({
            "bold": True, "font_size": 9, "font_color": "#FFFFFF",
            "bg_color": "#C55A11", "border": 1, "border_color": "#FFFFFF",
            "align": "center", "valign": "vcenter", "text_wrap": True,
        }),
        "header_green": wb.add_format({
            "bold": True, "font_size": 9, "font_color": "#FFFFFF",
            "bg_color": "#375623", "border": 1, "border_color": "#FFFFFF",
            "align": "center", "valign": "vcenter", "text_wrap": True,
        }),
        "text": wb.add_format({"font_size": 9, "border": 1, "border_color": "#D9D9D9", "valign": "vcenter"}),
        "mono": wb.add_format({"font_size": 9, "border": 1, "border_color": "#D9D9D9", "font_name": "Consolas", "valign": "vcenter"}),
        "num":  wb.add_format({"font_size": 9, "border": 1, "border_color": "#D9D9D9", "num_format": "#,##0", "align": "right", "valign": "vcenter"}),
        "rp":   wb.add_format({"font_size": 9, "border": 1, "border_color": "#D9D9D9", "num_format": '"Rp "#,##0', "align": "right", "valign": "vcenter"}),
        "pct":  wb.add_format({"font_size": 9, "border": 1, "border_color": "#D9D9D9", "num_format": "0.0%", "align": "right", "valign": "vcenter"}),
        "dec2": wb.add_format({"font_size": 9, "border": 1, "border_color": "#D9D9D9", "num_format": "0.0000", "align": "right", "valign": "vcenter"}),
        "flag_red":    wb.add_format({"font_size": 9, "border": 1, "bg_color": "#FFE0E0", "font_color": "#C00000", "bold": True, "valign": "vcenter"}),
        "flag_yellow": wb.add_format({"font_size": 9, "border": 1, "bg_color": "#FFF2CC", "font_color": "#7F6000", "bold": True, "valign": "vcenter"}),
        "flag_green":  wb.add_format({"font_size": 9, "border": 1, "bg_color": "#E2EFDA", "font_color": "#375623", "valign": "vcenter"}),
        "row_alt":     wb.add_format({"font_size": 9, "border": 1, "border_color": "#D9D9D9", "bg_color": "#F2F2F2", "valign": "vcenter"}),
    }


def write_df_to_sheet(ws, wb, df: pd.DataFrame, col_cfg: list, start_row: int = 2, fmt_dict: dict = None):
    """
    col_cfg: list of dict dengan kunci:
      name, width, fmt_key, header_fmt_key (opsional)
    """
    if fmt_dict is None:
        fmt_dict = col_formats(wb)

    hdr_fmt = fmt_dict["header"]
    ws.set_row(start_row, 28)
    for ci, cfg in enumerate(col_cfg):
        h_fmt = fmt_dict.get(cfg.get("header_fmt_key", "header"), hdr_fmt)
        ws.write(start_row, ci, cfg["name"], h_fmt)
        ws.set_column(ci, ci, cfg["width"])

    for ri, (_, row) in enumerate(df.iterrows()):
        excel_row = start_row + 1 + ri
        ws.set_row(excel_row, 15)
        col_val = list(col_cfg[i]["col"] for i in range(len(col_cfg)))
        for ci, cfg in enumerate(col_cfg):
            val = row[cfg["col"]] if cfg["col"] in row.index else ""
            # Format selection
            fmt_key = cfg.get("fmt_key", "text")
            # Conditional formats
            if fmt_key == "risk_flag":
                if "KRITIS" in str(val) or "DISPERSI_TINGGI" in str(val) or "PPH_ANOMALI_TINGGI" in str(val):
                    fmt = fmt_dict["flag_red"]
                elif val and val != "-":
                    fmt = fmt_dict["flag_yellow"]
                else:
                    fmt = fmt_dict["flag_green"]
            elif fmt_key == "sync":
                if "ANOMALI" in str(val):
                    fmt = fmt_dict["flag_red"]
                elif "MINOR" in str(val):
                    fmt = fmt_dict["flag_yellow"]
                else:
                    fmt = fmt_dict["flag_green"]
            elif fmt_key == "disp":
                if "Kritis" in str(val):
                    fmt = fmt_dict["flag_red"]
                elif "Perhatian" in str(val) or "Sangat Lebar" in str(val):
                    fmt = fmt_dict["flag_yellow"]
                else:
                    fmt = fmt_dict["flag_green"]
            else:
                fmt = fmt_dict.get(fmt_key, fmt_dict["text"])

            if pd.isna(val):
                ws.write(excel_row, ci, "-", fmt)
            elif fmt_key in ("num", "rp", "pct", "dec2"):
                ws.write_number(excel_row, ci, float(val) if val != "" else 0, fmt)
            else:
                ws.write(excel_row, ci, str(val) if val != "" else "-", fmt)


# =============================================
# OUTPUT 01 - HS CODE FINAL PER KLASTER
# =============================================

def write_01_hs_final(df: pd.DataFrame, hs_profile: pd.DataFrame, out_dir: str):
    path = os.path.join(out_dir, "01_HS_Code_Final_per_Klaster.xlsx")
    writer = make_writer(path)
    wb    = writer.book
    fmts  = col_formats(wb)

    col_cfg = [
        {"name": "HS Code (8 digit)",   "col": "POS_TARIF_HS",  "width": 16, "fmt_key": "mono"},
        {"name": "KD Kelompok (4 digit)","col": "KD_KELOMPOK",  "width": 14, "fmt_key": "mono"},
        {"name": "Nama Kelompok",        "col": "NM_KELOMPOK",  "width": 40, "fmt_key": "text"},
        {"name": "Nama Detail (NM_DETIL)","col":"NM_DETIL",     "width": 50, "fmt_key": "text"},
        {"name": "Ada Kelompok?",        "col": "has_kelompok", "width": 13, "fmt_key": "text"},
        {"name": "Catch-all / Lain-lain","col": "is_lainlain",  "width": 15, "fmt_key": "text"},
        {"name": "# KLU Unik",           "col": "n_klu",        "width": 11, "fmt_key": "num"},
        {"name": "Dispersi Kategori",    "col": "disp_category","width": 22, "fmt_key": "disp"},
        {"name": "# NPWP",               "col": "n_npwp",       "width": 10, "fmt_key": "num"},
        {"name": "# PIB",                "col": "n_pib",        "width": 10, "fmt_key": "num"},
        {"name": "PPN Dibayar (Rp)",     "col": "ppn",          "width": 22, "fmt_key": "rp"},
        {"name": "PPh Dibayar (Rp)",     "col": "pph",          "width": 22, "fmt_key": "rp"},
        {"name": "PPh/PPN Ratio",        "col": "pph_ppn_ratio","width": 13, "fmt_key": "dec2"},
        {"name": "Risk Score",           "col": "risk_score",   "width": 11, "fmt_key": "dec2"},
        {"name": "Risk Flags",           "col": "risk_flags",   "width": 40, "fmt_key": "risk_flag"},
        {"name": "Risk Events",          "col": "risk_events",  "width": 40, "fmt_key": "text"},
        {"name": "Justifikasi Scope",    "col": "_justifikasi", "width": 40, "fmt_key": "text"},
    ]

    # Sheet per klaster + 1 sheet ringkasan
    all_clusters = list(CLUSTERS.keys()) + ["Lainnya", "SEMUA"]

    for cluster_name in all_clusters:
        if cluster_name == "SEMUA":
            sub = hs_profile.copy()
            sheet_name = "SEMUA_KLASTER"
        else:
            sub = hs_profile[hs_profile["CLUSTER"] == cluster_name].copy()
            sheet_name = cluster_name[:31]

        # Auto-justifikasi
        def justify(row):
            parts = []
            if row.get("is_lainlain"):
                parts.append("Kode catch-all - perlu keputusan BA")
            if not row.get("has_kelompok"):
                parts.append("KD_KELOMPOK kosong - perlu investigasi DE")
            if row.get("n_klu", 0) > DISPERSION_HIGH:
                parts.append(f"Dispersi tinggi ({row['n_klu']} KLU) - perlu mapping ulang")
            if row.get("n_npwp", 999) <= CONCENTRATION_N and row.get("ppn", 0) > PPN_MATERIAL * 10:
                parts.append("Konsentrasi importir - prioritas audit")
            if not parts:
                parts.append("Masuk scope klaster berdasarkan chapter HS")
            return " | ".join(parts)

        sub["_justifikasi"] = sub.apply(justify, axis=1)
        sub = sub.sort_values("ppn", ascending=False).reset_index(drop=True)

        # Sanitize sheet name (Excel: max 31 chars, no []:*?/\)
        safe_name = sheet_name.replace("/","_").replace("\\","_").replace(":","_").replace("*","_").replace("?","_").replace("[","(").replace("]",")")[:31]
        ws = wb.add_worksheet(safe_name)
        ws.freeze_panes(3, 0)
        ws.set_zoom(85)

        total_ppn = sub["ppn"].sum()
        total_npwp = sub["n_npwp"].sum()
        subtitle = (f"Klaster: {cluster_name}  |  {len(sub):,} HS Code  |  "
                    f"Total PPN: Rp {total_ppn/1e9:,.1f} M  |  Dibuat: {datetime.now():%d %b %Y %H:%M}")
        start = add_header(ws, wb, f"[01] Daftar HS Code Final - {cluster_name}", subtitle)
        write_df_to_sheet(ws, wb, sub, col_cfg, start_row=start, fmt_dict=fmts)

        # Autofilter
        ws.autofilter(start, 0, start + len(sub), len(col_cfg) - 1)

    writer.close()
    print(f"    [OK] {path}")


# =============================================
# OUTPUT 02 - PROFIL HS CODE
# =============================================

def write_02_profil(hs_profile: pd.DataFrame, out_dir: str):
    path = os.path.join(out_dir, "02_Profil_HS_Code.xlsx")
    writer = make_writer(path)
    wb = writer.book
    fmts = col_formats(wb)

    col_cfg = [
        {"name": "Rank",             "col": "_rank",         "width":  6, "fmt_key": "num"},
        {"name": "Cluster",          "col": "CLUSTER",       "width": 20, "fmt_key": "text"},
        {"name": "HS Code",          "col": "POS_TARIF_HS",  "width": 14, "fmt_key": "mono"},
        {"name": "Nama Detail",      "col": "NM_DETIL",      "width": 50, "fmt_key": "text"},
        {"name": "Nama Kelompok",    "col": "NM_KELOMPOK",   "width": 38, "fmt_key": "text"},
        {"name": "# KLU Unik",       "col": "n_klu",         "width": 11, "fmt_key": "num"},
        {"name": "Dispersi",         "col": "disp_category", "width": 22, "fmt_key": "disp"},
        {"name": "# NPWP",           "col": "n_npwp",        "width": 10, "fmt_key": "num"},
        {"name": "PPN per NPWP (Rp)","col": "ppn_per_npwp",  "width": 20, "fmt_key": "rp"},
        {"name": "# PIB",            "col": "n_pib",         "width": 10, "fmt_key": "num"},
        {"name": "PIB per NPWP",     "col": "pib_per_npwp",  "width": 13, "fmt_key": "dec2"},
        {"name": "PPN Total (Rp)",   "col": "ppn",           "width": 22, "fmt_key": "rp"},
        {"name": "PPh Total (Rp)",   "col": "pph",           "width": 22, "fmt_key": "rp"},
        {"name": "PPh/PPN Ratio",    "col": "pph_ppn_ratio", "width": 13, "fmt_key": "dec2"},
        {"name": "Catch-all?",       "col": "is_lainlain",   "width": 12, "fmt_key": "text"},
        {"name": "Risk Score",       "col": "risk_score",    "width": 11, "fmt_key": "dec2"},
        {"name": "Risk Flags",       "col": "risk_flags",    "width": 42, "fmt_key": "risk_flag"},
        {"name": "Risk Events",      "col": "risk_events",   "width": 38, "fmt_key": "text"},
    ]

    for sheet_name, sort_col in [
        ("By_Risk_Score",  "risk_score"),
        ("By_PPN_Value",   "ppn"),
        ("By_Dispersi_KLU","n_klu"),
        ("By_Konsentrasi", "ppn_per_npwp"),
    ]:
        sub = hs_profile.sort_values(sort_col, ascending=False).reset_index(drop=True).copy()
        sub["_rank"] = sub.index + 1

        ws = wb.add_worksheet(sheet_name)
        ws.freeze_panes(3, 3)
        ws.set_zoom(80)

        subtitle = (f"Sort: {sort_col}  |  {len(sub):,} HS Code  |  "
                    f"Dibuat: {datetime.now():%d %b %Y %H:%M}")
        start = add_header(ws, wb, f"[02] Profil Ringkasan HS Code - {sheet_name}", subtitle)
        write_df_to_sheet(ws, wb, sub, col_cfg, start_row=start, fmt_dict=fmts)
        ws.autofilter(start, 0, start + len(sub), len(col_cfg) - 1)

    writer.close()
    print(f"    [OK] {path}")


# =============================================
# OUTPUT 03 - MATRIKS SINKRONISASI HS x KLU
# =============================================

def write_03_matriks(klu_matrix: pd.DataFrame, out_dir: str):
    path = os.path.join(out_dir, "03_Matriks_Sinkronisasi_HS_KLU.xlsx")
    writer = make_writer(path)
    wb = writer.book
    fmts = col_formats(wb)

    col_cfg = [
        {"name": "Cluster",          "col": "CLUSTER",      "width": 20, "fmt_key": "text"},
        {"name": "HS Code",          "col": "POS_TARIF_HS", "width": 14, "fmt_key": "mono"},
        {"name": "Nama Detail (HS)", "col": "NM_DETIL",     "width": 48, "fmt_key": "text"},
        {"name": "Nama Kelompok",    "col": "NM_KELOMPOK",  "width": 38, "fmt_key": "text"},
        {"name": "KD KLU",           "col": "KD_KLU",       "width": 10, "fmt_key": "mono"},
        {"name": "Nama KLU (WP)",    "col": "NM_KLU",       "width": 48, "fmt_key": "text"},
        {"name": "Sub-golongan KLU", "col": "NM_SUBGOL",    "width": 38, "fmt_key": "text"},
        {"name": "# NPWP",           "col": "n_npwp",       "width": 10, "fmt_key": "num"},
        {"name": "Share NPWP",       "col": "share_npwp",   "width": 12, "fmt_key": "pct"},
        {"name": "# PIB",            "col": "n_pib",        "width": 10, "fmt_key": "num"},
        {"name": "PPN (Rp)",         "col": "ppn",          "width": 22, "fmt_key": "rp"},
        {"name": "PPh (Rp)",         "col": "pph",          "width": 22, "fmt_key": "rp"},
        {"name": "PPh/PPN Ratio",    "col": "pph_ppn_ratio","width": 13, "fmt_key": "dec2"},
        {"name": "# KLU Unik (HS)",  "col": "n_klu",        "width": 14, "fmt_key": "num"},
        {"name": "Dispersi",         "col": "disp_category","width": 22, "fmt_key": "disp"},
        {"name": "Risk Score (HS)",  "col": "risk_score",   "width": 13, "fmt_key": "dec2"},
        {"name": "Status Sinkronisasi","col":"sinkronisasi","width": 24, "fmt_key": "sync"},
    ]

    # Sheet 1: Semua pasangan
    ws_all = wb.add_worksheet("Semua_Pasangan")
    ws_all.freeze_panes(3, 3)
    ws_all.set_zoom(75)
    start = add_header(ws_all, wb,
        f"[03] Matriks Sinkronisasi HS x KLU - Semua Pasangan",
        f"{len(klu_matrix):,} pasangan  |  Dibuat: {datetime.now():%d %b %Y %H:%M}")
    write_df_to_sheet(ws_all, wb, klu_matrix, col_cfg, start_row=start, fmt_dict=fmts)
    ws_all.autofilter(start, 0, start + len(klu_matrix), len(col_cfg) - 1)

    # Sheet 2: Hanya anomali
    anomali = klu_matrix[klu_matrix["sinkronisasi"].str.contains("ANOMALI")].sort_values("ppn", ascending=False)
    ws_an = wb.add_worksheet("Anomali_Saja")
    ws_an.freeze_panes(3, 3)
    ws_an.set_zoom(75)
    start = add_header(ws_an, wb,
        f"[03] Matriks Sinkronisasi - ANOMALI SAJA",
        f"{len(anomali):,} pasangan anomali  |  PPN: Rp {anomali['ppn'].sum()/1e9:,.1f} M  |  Dibuat: {datetime.now():%d %b %Y %H:%M}")
    write_df_to_sheet(ws_an, wb, anomali.reset_index(drop=True), col_cfg, start_row=start, fmt_dict=fmts)
    ws_an.autofilter(start, 0, start + len(anomali), len(col_cfg) - 1)

    # Sheet 3: Hanya wajar (dominan)
    wajar = klu_matrix[klu_matrix["sinkronisasi"].str.contains("WAJAR")].sort_values("ppn", ascending=False)
    ws_wj = wb.add_worksheet("Wajar_Dominan")
    ws_wj.freeze_panes(3, 3)
    ws_wj.set_zoom(75)
    start = add_header(ws_wj, wb,
        f"[03] Matriks Sinkronisasi - WAJAR / DOMINAN",
        f"{len(wajar):,} pasangan wajar  |  PPN: Rp {wajar['ppn'].sum()/1e9:,.1f} M  |  Dibuat: {datetime.now():%d %b %Y %H:%M}")
    write_df_to_sheet(ws_wj, wb, wajar.reset_index(drop=True), col_cfg, start_row=start, fmt_dict=fmts)
    ws_wj.autofilter(start, 0, start + len(wajar), len(col_cfg) - 1)

    writer.close()
    print(f"    [OK] {path}")


# =============================================
# OUTPUT 04 - REKOMENDASI PRIORITAS
# =============================================

def write_04_rekomendasi(hs_profile: pd.DataFrame, cross_sector: pd.DataFrame, out_dir: str):
    path = os.path.join(out_dir, "04_Rekomendasi_Prioritas.xlsx")
    writer = make_writer(path)
    wb = writer.book
    fmts = col_formats(wb)

    # -- Sheet 1: Top 100 Risk Score
    col_top = [
        {"name": "Rank",            "col": "_rank",         "width":  6, "fmt_key": "num"},
        {"name": "Cluster",         "col": "CLUSTER",       "width": 20, "fmt_key": "text"},
        {"name": "HS Code",         "col": "POS_TARIF_HS",  "width": 14, "fmt_key": "mono"},
        {"name": "Nama Detail",     "col": "NM_DETIL",      "width": 50, "fmt_key": "text"},
        {"name": "Risk Score",      "col": "risk_score",    "width": 11, "fmt_key": "dec2"},
        {"name": "Risk Events",     "col": "risk_events",   "width": 40, "fmt_key": "text"},
        {"name": "Risk Flags",      "col": "risk_flags",    "width": 40, "fmt_key": "risk_flag"},
        {"name": "# KLU Unik",      "col": "n_klu",         "width": 11, "fmt_key": "num"},
        {"name": "# NPWP",          "col": "n_npwp",        "width": 10, "fmt_key": "num"},
        {"name": "PPN (Rp)",        "col": "ppn",           "width": 22, "fmt_key": "rp"},
        {"name": "PPh/PPN Ratio",   "col": "pph_ppn_ratio", "width": 13, "fmt_key": "dec2"},
        {"name": "Dispersi",        "col": "disp_category", "width": 22, "fmt_key": "disp"},
        {"name": "Catch-all?",      "col": "is_lainlain",   "width": 12, "fmt_key": "text"},
    ]
    top100 = hs_profile.nlargest(100, "risk_score").reset_index(drop=True).copy()
    top100["_rank"] = top100.index + 1

    ws1 = wb.add_worksheet("Top100_Risk_Score")
    ws1.freeze_panes(3, 4)
    ws1.set_zoom(80)
    start = add_header(ws1, wb,
        "[04] Rekomendasi HS Code Prioritas - Top 100 Risk Score",
        f"Gabungan skor dispersi KLU (25%) + nilai PPN (40%) + konsentrasi NPWP (10%) + catch-all (25%)  |  Dibuat: {datetime.now():%d %b %Y %H:%M}")
    write_df_to_sheet(ws1, wb, top100, col_top, start_row=start, fmt_dict=fmts)
    ws1.autofilter(start, 0, start + len(top100), len(col_top) - 1)

    # -- Sheet per Risk Event
    for event in RISK_EVENTS:
        sub = hs_profile[hs_profile["risk_events"].str.contains(event, regex=False)].copy()
        sub = sub.sort_values("ppn", ascending=False).reset_index(drop=True)
        sub["_rank"] = sub.index + 1
        sname = event.replace("/","_").replace(" ","_")[:31]

        ws = wb.add_worksheet(sname)
        ws.freeze_panes(3, 4)
        ws.set_zoom(80)
        start = add_header(ws, wb,
            f"[04] Rekomendasi - {event}",
            f"{len(sub):,} HS Code  |  PPN: Rp {sub['ppn'].sum()/1e9:,.1f} M  |  Dibuat: {datetime.now():%d %b %Y %H:%M}")
        write_df_to_sheet(ws, wb, sub, col_top, start_row=start, fmt_dict=fmts)
        ws.autofilter(start, 0, start + len(sub), len(col_top) - 1)

    # -- Sheet Mismatch Lintas Sektor
    if cross_sector is not None and len(cross_sector) > 0:
        col_cross = [
            {"name": "Cluster HS",      "col": "CLUSTER",      "width": 20, "fmt_key": "text"},
            {"name": "HS Code",         "col": "POS_TARIF_HS", "width": 14, "fmt_key": "mono"},
            {"name": "Nama Detail",     "col": "NM_DETIL",     "width": 48, "fmt_key": "text"},
            {"name": "KD KLU",          "col": "KD_KLU",       "width": 10, "fmt_key": "mono"},
            {"name": "Nama KLU (WP)",   "col": "NM_KLU",       "width": 50, "fmt_key": "text"},
            {"name": "# NPWP",          "col": "n_npwp",       "width": 10, "fmt_key": "num"},
            {"name": "# PIB",           "col": "n_pib",        "width": 10, "fmt_key": "num"},
            {"name": "PPN (Rp)",        "col": "ppn",          "width": 22, "fmt_key": "rp"},
            {"name": "PPh/PPN Ratio",   "col": "pph_ppn_ratio","width": 13, "fmt_key": "dec2"},
            {"name": "Keterangan Mismatch","col":"MISMATCH",   "width": 38, "fmt_key": "risk_flag"},
        ]
        ws_cross = wb.add_worksheet("Mismatch_Lintas_Sektor")
        ws_cross.freeze_panes(3, 3)
        ws_cross.set_zoom(80)
        start = add_header(ws_cross, wb,
            "[04] Mismatch Lintas Sektor - KLU Tidak Wajar",
            f"{len(cross_sector):,} pasangan  |  PPN: Rp {cross_sector['ppn'].sum()/1e9:,.1f} M  |  Dibuat: {datetime.now():%d %b %Y %H:%M}")
        write_df_to_sheet(ws_cross, wb, cross_sector, col_cross, start_row=start, fmt_dict=fmts)
        ws_cross.autofilter(start, 0, start + len(cross_sector), len(col_cross) - 1)

    writer.close()
    print(f"    [OK] {path}")


# =============================================
# OUTPUT 05 - CATATAN DATA TAMBAHAN
# =============================================

def write_05_catatan(df: pd.DataFrame, hs_profile: pd.DataFrame, out_dir: str):
    path = os.path.join(out_dir, "05_Catatan_Data_Tambahan.xlsx")
    writer = make_writer(path)
    wb = writer.book
    fmts = col_formats(wb)

    total_ppn = df["PPN_DIBAYAR"].sum()
    total_baris = len(df)
    nan_kelompok = (df["KD_KELOMPOK"] == 0).sum()
    nan_detil    = df["NM_DETIL"].isnull().sum()
    lainlain     = df["IS_LAINLAIN"].sum()
    ppn_nan_kel  = df[df["KD_KELOMPOK"] == 0]["PPN_DIBAYAR"].sum()
    ppn_lainlain = df[df["IS_LAINLAIN"]]["PPN_DIBAYAR"].sum()
    high_disp    = hs_profile[hs_profile["n_klu"] > DISPERSION_HIGH]
    concentrated = hs_profile[hs_profile["n_npwp"] <= CONCENTRATION_N]

    # -- Sheet 1: Ringkasan Kualitas Data
    ws1 = wb.add_worksheet("Kualitas_Data")
    ws1.set_column(0, 0, 40)
    ws1.set_column(1, 1, 22)
    ws1.set_column(2, 2, 18)
    ws1.set_column(3, 3, 50)

    fmt_title = wb.add_format({"bold": True, "font_size": 11, "bg_color": "#1E3A5F", "font_color": "#FFFFFF", "border": 1, "indent": 1})
    fmt_label = wb.add_format({"font_size": 9, "bold": True, "border": 1, "bg_color": "#D6E4F0", "indent": 1})
    fmt_val   = wb.add_format({"font_size": 9, "border": 1, "num_format": "#,##0", "align": "right"})
    fmt_pct   = wb.add_format({"font_size": 9, "border": 1, "num_format": "0.0%", "align": "right"})
    fmt_rp    = wb.add_format({"font_size": 9, "border": 1, "num_format": '"Rp "#,##0', "align": "right"})
    fmt_note  = wb.add_format({"font_size": 9, "border": 1, "italic": True, "font_color": "#595959", "text_wrap": True, "indent": 1})

    rows_data = [
        ("RINGKASAN DATA SAMPLE",            None,             None,           None),
        ("Metrik",                           "Nilai",          "Persentase",   "Catatan / Aksi"),
        ("Total Baris Data",                 total_baris,      None,           "Jumlah baris per-NPWP x HS x KLU"),
        ("Total HS Code Unik",               df["POS_TARIF_HS"].nunique(), None, ""),
        ("Total KLU Unik",                   df["KD_KLU"].nunique(),       None, ""),
        ("Total NPWP Importir",              df["NPWP"].nunique(),         None, ""),
        ("Total Dokumen PIB",                int(df["jml_pib"].sum()),     None, ""),
        ("Total PPN Dibayar",                total_ppn,        None,           ""),
        ("Total PPh Dibayar",                df["PPH_DIBAYAR"].sum(), None,     ""),
        ("",                                 None,             None,           None),
        ("ISU KUALITAS DATA",                None,             None,           None),
        ("Baris tanpa KD_KELOMPOK",          nan_kelompok,     nan_kelompok/total_baris,   "Perlu investigasi DE: kemungkinan HS tidak ter-mapping di referensi bea cukai"),
        ("PPN di baris tanpa KD_KELOMPOK",   ppn_nan_kel,      ppn_nan_kel/total_ppn,      "Nilai material - perlu keputusan BA apakah diinclude atau exclude"),
        ("Baris NM_DETIL null",              nan_detil,        nan_detil/total_baris,       "Perlu join ke tabel referensi HS oleh DE"),
        ("Baris NM_DETIL 'Lain-lain'",       lainlain,         lainlain/total_baris,        "62%+ = dominasi kode catch-all -> risiko misdeclaration"),
        ("PPN di baris 'Lain-lain'",         ppn_lainlain,     ppn_lainlain/total_ppn,     "Prioritas pendalaman oleh Data Statistician"),
        ("",                                 None,             None,           None),
        ("KEBUTUHAN DATA TAMBAHAN DARI DE",  None,             None,           None),
        ("Data Detail per-NPWP (70 jt baris)","-",            None,           "Untuk: profil importir individu, tren per-NPWP, deteksi transfer pricing"),
        ("Data SPT Tahunan WP",              "-",              None,           "Untuk: verifikasi PPh badan, Artificial Loss, cross-check omset"),
        ("Data e-Faktur",                    "-",              None,           "Untuk: verifikasi PPN keluaran, API-P abuse detection"),
        ("Data Negara Asal (country of origin)","-",           None,           "Untuk: analisis harga wajar (arm's length), mispricing per negara"),
        ("Data NPWP Terkait (grup usaha)",   "-",              None,           "Untuk: deteksi transaksi afiliasi, transfer pricing"),
        ("Referensi HS Code terbaru (BTKI)", "-",              None,           "Untuk: mapping NM_DETIL yang null dan validasi KD_KELOMPOK"),
        ("",                                 None,             None,           None),
        ("HS CODE PRIORITAS TANPA KELOMPOK", None,             None,           None),
    ]

    for ri, (label, val, pct, note) in enumerate(rows_data):
        if label in ("RINGKASAN DATA SAMPLE","ISU KUALITAS DATA","KEBUTUHAN DATA TAMBAHAN DARI DE","HS CODE PRIORITAS TANPA KELOMPOK"):
            ws1.merge_range(ri, 0, ri, 3, label, fmt_title)
        elif label == "Metrik":
            for ci, h in enumerate(["Metrik","Nilai","Persentase","Catatan / Aksi"]):
                ws1.write(ri, ci, h, fmt_label)
        else:
            ws1.write(ri, 0, label, fmts["text"])
            if val is None:
                ws1.write(ri, 1, "-", fmts["text"])
            elif isinstance(val, str):
                ws1.write(ri, 1, val, fmts["text"])
            elif isinstance(val, float) and val > 1e6:
                ws1.write_number(ri, 1, val, fmt_rp)
            else:
                ws1.write_number(ri, 1, float(val) if val else 0, fmt_val)
            if pct is not None:
                ws1.write_number(ri, 2, pct, fmt_pct)
            else:
                ws1.write(ri, 2, "-", fmts["text"])
            ws1.write(ri, 3, note or "-", fmt_note)
        ws1.set_row(ri, 16)

    # Tambah daftar HS tanpa kelompok (top 20 by PPN)
    no_kel = hs_profile[hs_profile["has_kelompok"] == False].nlargest(20, "ppn")[
        ["POS_TARIF_HS","NM_DETIL","CLUSTER","n_npwp","ppn","risk_score"]
    ].reset_index(drop=True)
    base = len(rows_data)
    col_nk = [
        {"name": "HS Code",      "col": "POS_TARIF_HS","width": 14, "fmt_key": "mono"},
        {"name": "Nama Detail",  "col": "NM_DETIL",    "width": 50, "fmt_key": "text"},
        {"name": "Cluster",      "col": "CLUSTER",     "width": 20, "fmt_key": "text"},
        {"name": "# NPWP",       "col": "n_npwp",      "width": 10, "fmt_key": "num"},
        {"name": "PPN (Rp)",     "col": "ppn",         "width": 22, "fmt_key": "rp"},
        {"name": "Risk Score",   "col": "risk_score",  "width": 11, "fmt_key": "dec2"},
    ]
    write_df_to_sheet(ws1, wb, no_kel, col_nk, start_row=base, fmt_dict=fmts)

    # -- Sheet 2: HS Terkonsentrasi (<=10 NPWP, nilai besar)
    col_conc = [
        {"name": "Cluster",         "col": "CLUSTER",      "width": 20, "fmt_key": "text"},
        {"name": "HS Code",         "col": "POS_TARIF_HS", "width": 14, "fmt_key": "mono"},
        {"name": "Nama Detail",     "col": "NM_DETIL",     "width": 50, "fmt_key": "text"},
        {"name": "# NPWP",          "col": "n_npwp",       "width": 10, "fmt_key": "num"},
        {"name": "PPN Total (Rp)",  "col": "ppn",          "width": 22, "fmt_key": "rp"},
        {"name": "PPh Total (Rp)",  "col": "pph",          "width": 22, "fmt_key": "rp"},
        {"name": "PPN per NPWP",    "col": "ppn_per_npwp", "width": 20, "fmt_key": "rp"},
        {"name": "PPh/PPN Ratio",   "col": "pph_ppn_ratio","width": 13, "fmt_key": "dec2"},
        {"name": "Risk Score",      "col": "risk_score",   "width": 11, "fmt_key": "dec2"},
        {"name": "Risk Flags",      "col": "risk_flags",   "width": 42, "fmt_key": "risk_flag"},
    ]
    conc_df = concentrated.nlargest(100, "ppn").reset_index(drop=True)
    ws2 = wb.add_worksheet("HS_Terkonsentrasi")
    ws2.freeze_panes(3, 3)
    ws2.set_zoom(80)
    start = add_header(ws2, wb,
        f"[05] HS Code Terkonsentrasi (<={CONCENTRATION_N} NPWP) - Top 100 by PPN",
        f"{len(conc_df)} HS code  |  PPN: Rp {conc_df['ppn'].sum()/1e9:,.1f} M  |  Dibuat: {datetime.now():%d %b %Y %H:%M}")
    write_df_to_sheet(ws2, wb, conc_df, col_conc, start_row=start, fmt_dict=fmts)
    ws2.autofilter(start, 0, start + len(conc_df), len(col_conc) - 1)

    writer.close()
    print(f"    [OK] {path}")


# =============================================
# MAIN
# =============================================

def main():
    parser = argparse.ArgumentParser(
        description="Mesin Analisis PIB x HS Code x KLU - SR Importir Umum 2026"
    )
    parser.add_argument("--input",  default="sample_2023.xlsx",
                        help="Path ke file input (xlsx atau csv). Default: sample_2023.xlsx")
    parser.add_argument("--output", default="output",
                        help="Folder output. Default: output/")
    args = parser.parse_args()

    input_path  = args.input
    output_dir  = args.output

    print()
    print("=" * 65)
    print("  Mesin Analisis PIB x HS Code x KLU")
    print("  SR Importir Umum - CRM Subtim Data Analyst 2026")
    print("=" * 65)
    print(f"  Input : {input_path}")
    print(f"  Output: {output_dir}/")
    print()

    # Buat folder output
    os.makedirs(output_dir, exist_ok=True)

    # Pipeline
    df          = load_data(input_path)
    hs_profile  = build_hs_profile(df)
    klu_matrix  = build_klu_matrix(df, hs_profile)
    cross_sec   = build_cross_sector(df)

    print("[5/6] Menulis file deliverable output...")
    write_01_hs_final(df, hs_profile, output_dir)
    write_02_profil(hs_profile, output_dir)
    write_03_matriks(klu_matrix, output_dir)
    write_04_rekomendasi(hs_profile, cross_sec, output_dir)
    write_05_catatan(df, hs_profile, output_dir)

    # --- Ringkasan akhir
    print()
    print("[6/6] Selesai.")
    print()
    print("-" * 65)
    print("  RINGKASAN EKSEKUSI")
    print("-" * 65)
    print(f"  Baris data        : {len(df):,}")
    print(f"  HS Code unik      : {df['POS_TARIF_HS'].nunique():,}")
    print(f"  KLU unik          : {df['KD_KLU'].nunique():,}")
    print(f"  NPWP importir     : {df['NPWP'].nunique():,}")
    print(f"  Total PPN         : Rp {df['PPN_DIBAYAR'].sum()/1e12:,.2f} Triliun")
    print(f"  Total PPh         : Rp {df['PPH_DIBAYAR'].sum()/1e12:,.2f} Triliun")
    print()
    print(f"  HS dispersi >100 KLU : {(hs_profile['n_klu']>100).sum():,} HS code")
    print(f"  HS dispersi >50 KLU  : {(hs_profile['n_klu']>50).sum():,} HS code")
    print(f"  HS terkonsentrasi    : {(hs_profile['n_npwp']<=CONCENTRATION_N).sum():,} HS code (<={CONCENTRATION_N} NPWP)")
    print(f"  Pasangan HSxKLU      : {len(klu_matrix):,}")
    print(f"  Pasangan ANOMALI     : {klu_matrix['sinkronisasi'].str.contains('ANOMALI').sum():,}")
    print(f"  Mismatch lintas sektor: {len(cross_sec):,}")
    print()
    print("  File output:")
    for fname in sorted(os.listdir(output_dir)):
        fpath = os.path.join(output_dir, fname)
        size  = os.path.getsize(fpath) / 1024
        print(f"    {fname:50s}  {size:>8.1f} KB")
    print()
    print("  Output tersimpan di:", os.path.abspath(output_dir))
    print("-" * 65)


if __name__ == "__main__":
    main()
