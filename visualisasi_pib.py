"""
Visualisasi Dashboard PIB x HS Code x KLU
==========================================
Menghasilkan dashboard HTML interaktif (Plotly) + PNG charts (Matplotlib)
Referensi: Presentasi_Eksplorasi_PIB_HSCode_KLU_24022026.html

Penggunaan:
  python visualisasi_pib.py
  python visualisasi_pib.py --input sample_2023.xlsx --output output/
"""

import argparse
import os
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
# PALET WARNA (selaras dengan presentasi)
# ─────────────────────────────────────────────
CLR = {
    "bg":        "#0B0F1A",
    "card":      "#111827",
    "surface":   "#1E293B",
    "border":    "#2A3A52",
    "accent":    "#3B82F6",
    "warm":      "#F59E0B",
    "danger":    "#EF4444",
    "success":   "#10B981",
    "purple":    "#8B5CF6",
    "text":      "#F1F5F9",
    "muted":     "#94A3B8",
}

CLUSTER_COLORS = {
    "Elektronik (Ch.85)":       CLR["accent"],
    "Otomotif (Ch.87)":         CLR["warm"],
    "Kimia/Farmasi (Ch.28-38)": CLR["success"],
    "Pangan (Ch.10-11)":        CLR["purple"],
    "Lainnya":                  CLR["muted"],
}

DISP_COLORS = {
    "A - Tunggal (1)":          "#10B981",
    "B - Sempit (2-5)":         "#34D399",
    "C - Sedang (6-10)":        "#6EE7B7",
    "D - Lebar (11-20)":        "#FCD34D",
    "E - Sangat Lebar (21-50)": "#F59E0B",
    "F - Perhatian (51-100)":   "#F97316",
    "G - Kritis (>100)":        "#EF4444",
}

PLOTLY_LAYOUT = dict(
    paper_bgcolor=CLR["bg"],
    plot_bgcolor=CLR["card"],
    font=dict(family="DM Sans, Segoe UI, sans-serif", color=CLR["text"], size=11),
    margin=dict(l=20, r=20, t=50, b=20),
    legend=dict(bgcolor=CLR["surface"], bordercolor=CLR["border"], borderwidth=1, font=dict(size=10)),
)
# Axis defaults yang bisa di-merge per chart
_AXIS_DEF = dict(gridcolor=CLR["border"], zerolinecolor=CLR["border"], tickfont=dict(size=10))

def _layout(**overrides):
    """Merge PLOTLY_LAYOUT + axis defaults + per-chart overrides."""
    base = dict(**PLOTLY_LAYOUT)
    base.setdefault("xaxis", {})
    base.setdefault("yaxis", {})
    base["xaxis"] = {**_AXIS_DEF, **base.get("xaxis", {})}
    base["yaxis"] = {**_AXIS_DEF, **base.get("yaxis", {})}
    for k, v in overrides.items():
        if k in ("xaxis", "yaxis") and isinstance(v, dict):
            base[k] = {**_AXIS_DEF, **v}
        else:
            base[k] = v
    return base


# ─────────────────────────────────────────────
# LOAD & PREPARE (ulang pipeline analisis)
# ─────────────────────────────────────────────

CLUSTERS_DEF = {
    "Elektronik (Ch.85)":       list(range(85, 86)),
    "Otomotif (Ch.87)":         list(range(87, 88)),
    "Kimia/Farmasi (Ch.28-38)": list(range(28, 39)),
    "Pangan (Ch.10-11)":        list(range(10, 12)),
}

def assign_cluster(ch):
    for name, chapters in CLUSTERS_DEF.items():
        if ch in chapters:
            return name
    return "Lainnya"


def load_and_prepare(path: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    print(f"[1/3] Memuat data: {path}")
    ext = Path(path).suffix.lower()
    df = pd.read_excel(path) if ext in (".xlsx", ".xls") else pd.read_csv(path)

    df["POS_TARIF_HS"] = pd.to_numeric(df["POS_TARIF_HS"], errors="coerce").fillna(0).astype("int64")
    df["KD_KELOMPOK"]  = pd.to_numeric(df["KD_KELOMPOK"],  errors="coerce").fillna(0).astype("int64")
    df["PPN_DIBAYAR"]  = pd.to_numeric(df["PPN_DIBAYAR"],  errors="coerce").fillna(0)
    df["PPH_DIBAYAR"]  = pd.to_numeric(df["PPH_DIBAYAR"],  errors="coerce").fillna(0)
    df["jml_pib"]      = pd.to_numeric(df["jml_pib"],      errors="coerce").fillna(0)
    df["HS_CHAPTER"]   = (df["POS_TARIF_HS"] // 1_000_000).astype(int)
    df["CLUSTER"]      = df["HS_CHAPTER"].apply(assign_cluster)
    df["IS_LAINLAIN"]  = df["NM_DETIL"].str.contains("Lain-lain", na=False)

    print(f"    -> {len(df):,} baris | {df['POS_TARIF_HS'].nunique():,} HS | {df['KD_KLU'].nunique():,} KLU")

    # HS profile
    print("[2/3] Membangun agregasi...")
    hs = df.groupby("POS_TARIF_HS").agg(
        CLUSTER        =("CLUSTER",      "first"),
        HS_CHAPTER     =("HS_CHAPTER",   "first"),
        NM_DETIL       =("NM_DETIL",     "first"),
        NM_KELOMPOK    =("NM_KELOMPOK",  "first"),
        n_klu          =("KD_KLU",       "nunique"),
        n_npwp         =("NPWP",         "nunique"),
        n_pib          =("jml_pib",      "sum"),
        ppn            =("PPN_DIBAYAR",  "sum"),
        pph            =("PPH_DIBAYAR",  "sum"),
        is_lainlain    =("IS_LAINLAIN",  "any"),
        has_kelompok   =("KD_KELOMPOK",  lambda x: (x != 0).any()),
    ).reset_index()

    hs["pph_ppn_ratio"] = np.where(hs["ppn"] > 0, hs["pph"] / hs["ppn"], 0).round(4)
    hs["ppn_per_npwp"]  = (hs["ppn"] / hs["n_npwp"].clip(1)).round(0)

    def disp_cat(n):
        if n == 1:   return "A - Tunggal (1)"
        if n <= 5:   return "B - Sempit (2-5)"
        if n <= 10:  return "C - Sedang (6-10)"
        if n <= 20:  return "D - Lebar (11-20)"
        if n <= 50:  return "E - Sangat Lebar (21-50)"
        if n <= 100: return "F - Perhatian (51-100)"
        return "G - Kritis (>100)"
    hs["disp_cat"] = hs["n_klu"].apply(disp_cat)

    _mx_klu = hs["n_klu"].max(); _mx_ppn = hs["ppn"].max(); _mx_npwp = hs["n_npwp"].max()
    hs["risk_score"] = (
        (hs["n_klu"]  / _mx_klu ).clip(0, 1) * 0.25 +
        (hs["ppn"]    / _mx_ppn ).clip(0, 1) * 0.40 +
        (1 - (hs["n_npwp"] / _mx_npwp).clip(0, 1)) * 0.10 +
        hs["is_lainlain"].astype(float) * 0.25
    ).round(4)

    # KLU pairs for anomali
    pairs = df.groupby(["POS_TARIF_HS","KD_KLU"]).agg(
        NM_KLU  =("NM_KLU",      "first"),
        NM_DETIL=("NM_DETIL",    "first"),
        n_npwp  =("NPWP",        "nunique"),
        ppn     =("PPN_DIBAYAR", "sum"),
        CLUSTER =("CLUSTER",     "first"),
    ).reset_index()
    tot = pairs.groupby("POS_TARIF_HS")["n_npwp"].transform("sum")
    mx  = pairs.groupby("POS_TARIF_HS")["n_npwp"].transform("max")
    pairs["share"] = pairs["n_npwp"] / tot.clip(1)
    pairs["is_dom"] = pairs["n_npwp"] == mx

    return df, hs, pairs


# ─────────────────────────────────────────────
# PLOTLY CHARTS
# ─────────────────────────────────────────────

def fig_kpi(df, hs):
    """KPI summary cards sebagai tabel."""
    total_ppn  = df["PPN_DIBAYAR"].sum()
    total_pph  = df["PPH_DIBAYAR"].sum()
    n_hs       = df["POS_TARIF_HS"].nunique()
    n_klu      = df["KD_KLU"].nunique()
    n_npwp     = df["NPWP"].nunique()
    n_pib      = int(df["jml_pib"].sum())
    lainlain_p = df["IS_LAINLAIN"].mean() * 100
    nan_kel_p  = (df["KD_KELOMPOK"] == 0).mean() * 100
    n_kritis   = (hs["n_klu"] > 100).sum()

    labels = ["Total Baris", "HS Code Unik", "KLU Unik", "NPWP Importir",
              "Dokumen PIB", "Total PPN", "Total PPh",
              "Catch-all 'Lain-lain'", "Tanpa KD_KELOMPOK", "HS Kritis (>100 KLU)"]
    vals   = [f"{len(df):,}", f"{n_hs:,}", f"{n_klu:,}", f"{n_npwp:,}",
              f"{n_pib:,}", f"Rp {total_ppn/1e12:.2f} T", f"Rp {total_pph/1e12:.2f} T",
              f"{lainlain_p:.1f}%", f"{nan_kel_p:.1f}%", f"{n_kritis:,}"]
    colors = [CLR["muted"]]*5 + [CLR["accent"], CLR["success"],
              CLR["danger"], CLR["warm"], CLR["danger"]]

    fig = go.Figure(go.Table(
        columnwidth=[200, 200],
        header=dict(
            values=["<b>Metrik</b>", "<b>Nilai</b>"],
            fill_color=CLR["surface"],
            font=dict(color=CLR["text"], size=12),
            line_color=CLR["border"],
            align="left",
            height=32,
        ),
        cells=dict(
            values=[labels, vals],
            fill_color=[[CLR["card"]]*len(labels), [CLR["card"]]*len(labels)],
            font=dict(color=[CLR["muted"], colors], size=11),
            line_color=CLR["border"],
            align=["left", "right"],
            height=28,
        ),
    ))
    fig.update_layout(title="<b>Ringkasan Data 2023</b>", **_layout(), height=380)
    return fig


def fig_dispersi_bar(hs):
    """Bar chart distribusi dispersi KLU per HS."""
    dist = hs.groupby("disp_cat").agg(
        n_hs=("POS_TARIF_HS", "count"),
        ppn =("ppn", "sum"),
    ).reset_index()

    cat_order = list(DISP_COLORS.keys())
    dist["disp_cat"] = pd.Categorical(dist["disp_cat"], categories=cat_order, ordered=True)
    dist = dist.sort_values("disp_cat")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(go.Bar(
        x=dist["disp_cat"],
        y=dist["n_hs"],
        name="# HS Code",
        marker_color=[DISP_COLORS.get(c, CLR["muted"]) for c in dist["disp_cat"]],
        text=dist["n_hs"].apply(lambda x: f"{x:,}"),
        textposition="outside",
        textfont=dict(size=10, color=CLR["text"]),
    ), secondary_y=False)

    fig.add_trace(go.Scatter(
        x=dist["disp_cat"],
        y=dist["ppn"] / 1e12,
        name="PPN (Triliun)",
        mode="lines+markers",
        line=dict(color=CLR["warm"], width=2),
        marker=dict(size=8, color=CLR["warm"]),
    ), secondary_y=True)

    fig.update_layout(
        title="<b>Distribusi Dispersi KLU per HS Code</b><br><sup>Makin ke kanan = makin berisiko (banyak sektor berbeda impor barang yang sama)</sup>",
        **_layout(), height=420,
        bargap=0.3,
    )
    fig.update_yaxes(title_text="Jumlah HS Code", secondary_y=False,
                     gridcolor=CLR["border"], color=CLR["text"])
    fig.update_yaxes(title_text="Total PPN (Rp Triliun)", secondary_y=True,
                     gridcolor="rgba(0,0,0,0)", color=CLR["warm"])
    return fig


def fig_top_hs_ppn(hs, n=20):
    """Horizontal bar - Top N HS by PPN."""
    top = hs.nlargest(n, "ppn").sort_values("ppn")
    top["label"] = top["POS_TARIF_HS"].astype(str) + " | " + top["NM_DETIL"].fillna("N/A").str[:35]
    top["color"] = top["CLUSTER"].map(CLUSTER_COLORS).fillna(CLR["muted"])
    top["hover"] = (
        "HS: " + top["POS_TARIF_HS"].astype(str) +
        "<br>Cluster: " + top["CLUSTER"] +
        "<br>NPWP: " + top["n_npwp"].apply(lambda x: f"{x:,}") +
        "<br>KLU unik: " + top["n_klu"].apply(lambda x: f"{x:,}") +
        "<br>PPN: Rp " + top["ppn"].apply(lambda x: f"{x/1e9:,.1f} M") +
        "<br>PPh/PPN: " + top["pph_ppn_ratio"].apply(lambda x: f"{x:.3f}")
    )

    fig = go.Figure(go.Bar(
        x=top["ppn"] / 1e12,
        y=top["label"],
        orientation="h",
        marker_color=top["color"],
        hovertext=top["hover"],
        hoverinfo="text",
        text=top["ppn"].apply(lambda x: f"Rp {x/1e9:,.0f} M"),
        textposition="outside",
        textfont=dict(size=9),
    ))
    fig.update_layout(
        title=f"<b>Top {n} HS Code berdasarkan Nilai PPN</b><br><sup>Warna = klaster | Hover untuk detail</sup>",
        xaxis_title="Total PPN (Rp Triliun)",
        **_layout(yaxis=dict(tickfont=dict(size=9), gridcolor=CLR["border"])),
        height=max(400, n * 28),
    )

    # Legend klaster
    for cl, col in CLUSTER_COLORS.items():
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(color=col, size=10, symbol="square"),
            name=cl, showlegend=True,
        ))
    return fig


def fig_cluster_donut(hs):
    """Donut chart komposisi PPN per klaster."""
    cl_agg = hs.groupby("CLUSTER").agg(ppn=("ppn","sum"), n_hs=("POS_TARIF_HS","count")).reset_index()
    cl_agg = cl_agg.sort_values("ppn", ascending=False)
    colors = [CLUSTER_COLORS.get(c, CLR["muted"]) for c in cl_agg["CLUSTER"]]

    fig = make_subplots(rows=1, cols=2,
                        specs=[[{"type":"pie"}, {"type":"pie"}]],
                        subplot_titles=["Komposisi PPN", "Komposisi HS Code"])

    fig.add_trace(go.Pie(
        labels=cl_agg["CLUSTER"], values=cl_agg["ppn"]/1e12,
        hole=0.55, marker_colors=colors,
        textinfo="label+percent", textfont_size=10,
        hovertemplate="<b>%{label}</b><br>PPN: Rp %{value:.2f} T<br>Share: %{percent}<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Pie(
        labels=cl_agg["CLUSTER"], values=cl_agg["n_hs"],
        hole=0.55, marker_colors=colors,
        textinfo="label+percent", textfont_size=10,
        hovertemplate="<b>%{label}</b><br>HS Code: %{value:,}<br>Share: %{percent}<extra></extra>",
    ), row=1, col=2)

    fig.update_layout(
        title="<b>Komposisi per Klaster</b>",
        **_layout(), height=400,
        showlegend=False,
    )
    return fig


def fig_scatter_risk(hs):
    """Scatter: PPN vs Dispersi KLU, ukuran = NPWP, warna = cluster."""
    sub = hs[hs["ppn"] > 1e8].copy()
    sub["ppn_M"]  = (sub["ppn"] / 1e9).round(1)
    sub["hover"] = (
        "HS: " + sub["POS_TARIF_HS"].astype(str) +
        "<br>" + sub["NM_DETIL"].fillna("N/A").str[:40] +
        "<br>Cluster: " + sub["CLUSTER"] +
        "<br>Dispersi: " + sub["n_klu"].astype(str) + " KLU" +
        "<br>NPWP: " + sub["n_npwp"].apply(lambda x: f"{x:,}") +
        "<br>PPN: Rp " + sub["ppn_M"].apply(lambda x: f"{x:,.1f} M") +
        "<br>Risk Score: " + sub["risk_score"].astype(str)
    )

    fig = go.Figure()
    for cl, col in CLUSTER_COLORS.items():
        mask = sub["CLUSTER"] == cl
        s = sub[mask]
        if len(s) == 0:
            continue
        fig.add_trace(go.Scatter(
            x=s["n_klu"],
            y=s["ppn"] / 1e9,
            mode="markers",
            name=cl,
            marker=dict(
                color=col,
                size=np.clip(np.log1p(s["n_npwp"]) * 4, 5, 30),
                opacity=0.7,
                line=dict(width=0.5, color="rgba(255,255,255,0.3)"),
            ),
            hovertext=s["hover"],
            hoverinfo="text",
        ))

    # Garis threshold dispersi
    fig.add_vline(x=50,  line_dash="dash", line_color=CLR["warm"],
                  annotation_text="Threshold 50 KLU", annotation_font_color=CLR["warm"])
    fig.add_vline(x=100, line_dash="dash", line_color=CLR["danger"],
                  annotation_text="Threshold 100 KLU", annotation_font_color=CLR["danger"])

    fig.update_layout(
        title="<b>Scatter: Nilai PPN vs Dispersi KLU</b><br>"
              "<sup>Ukuran titik = jumlah NPWP | Hover untuk detail</sup>",
        xaxis_title="Jumlah KLU Unik per HS Code (Dispersi)",
        yaxis_title="Total PPN (Rp Miliar)",
        **_layout(
            xaxis=dict(type="log", gridcolor=CLR["border"]),
            yaxis=dict(type="log", gridcolor=CLR["border"]),
        ),
        height=500,
    )
    return fig


def fig_pph_ppn_hist(hs):
    """Distribusi PPh/PPN ratio per klaster."""
    sub = hs[(hs["pph_ppn_ratio"] > 0) & (hs["pph_ppn_ratio"] < 5)].copy()

    fig = go.Figure()
    for cl, col in CLUSTER_COLORS.items():
        mask = sub["CLUSTER"] == cl
        s = sub[mask]
        if len(s) < 5:
            continue
        fig.add_trace(go.Violin(
            x=[cl] * len(s),
            y=s["pph_ppn_ratio"],
            name=cl,
            box_visible=True,
            meanline_visible=True,
            fillcolor=col,
            line_color=CLR["text"],
            opacity=0.7,
            points=False,
        ))

    fig.add_hline(y=0.25, line_dash="dot", line_color=CLR["muted"],
                  annotation_text="Normal ~0.25", annotation_font_color=CLR["muted"])
    fig.add_hline(y=2.0,  line_dash="dash", line_color=CLR["danger"],
                  annotation_text="Anomali Tinggi >2.0", annotation_font_color=CLR["danger"])
    fig.add_hline(y=0.05, line_dash="dash", line_color=CLR["warm"],
                  annotation_text="Anomali Rendah <0.05", annotation_font_color=CLR["warm"])

    fig.update_layout(
        title="<b>Distribusi Rasio PPh/PPN per Klaster</b><br>"
              "<sup>Kotak = IQR | Garis = median | Titik outlier disembunyikan</sup>",
        xaxis_title="Klaster",
        yaxis_title="Rasio PPh / PPN",
        **_layout(), height=430,
        violinmode="group",
    )
    return fig


def fig_top_anomali(pairs, n=20):
    """Bar - Top anomali KLU outlier bernilai tinggi."""
    anomali = pairs[
        (pairs["share"] < 0.05) & (pairs["ppn"] > 2e9) & (~pairs["is_dom"])
    ].sort_values("ppn", ascending=False).head(n)

    if len(anomali) == 0:
        return None

    anomali["label"] = (
        "HS " + anomali["POS_TARIF_HS"].astype(str) +
        " x " + anomali["NM_KLU"].fillna("N/A").str[:30]
    )
    anomali["hover"] = (
        "HS: " + anomali["POS_TARIF_HS"].astype(str) +
        "<br>Barang: " + anomali["NM_DETIL"].fillna("N/A").str[:45] +
        "<br>KLU Anomali: " + anomali["NM_KLU"].fillna("N/A") +
        "<br>Share NPWP: " + anomali["share"].apply(lambda x: f"{x*100:.1f}%") +
        "<br>PPN: Rp " + anomali["ppn"].apply(lambda x: f"{x/1e9:,.1f} M") +
        "<br>Cluster: " + anomali["CLUSTER"]
    )
    anomali["color"] = anomali["CLUSTER"].map(CLUSTER_COLORS).fillna(CLR["muted"])
    anomali_sorted = anomali.sort_values("ppn")

    fig = go.Figure(go.Bar(
        x=anomali_sorted["ppn"] / 1e9,
        y=anomali_sorted["label"],
        orientation="h",
        marker_color=anomali_sorted["color"],
        hovertext=anomali_sorted["hover"],
        hoverinfo="text",
        text=anomali_sorted["ppn"].apply(lambda x: f"Rp {x/1e9:,.0f} M"),
        textposition="outside",
        textfont=dict(size=9),
    ))
    fig.update_layout(
        title=f"<b>Top {n} Anomali KLU Outlier Bernilai Tinggi</b><br>"
              "<sup>KLU dengan share NPWP <5% tapi PPN besar per HS Code | Indikasi Misdeclaration</sup>",
        xaxis_title="PPN (Rp Miliar)",
        **_layout(yaxis=dict(tickfont=dict(size=9))),
        height=max(400, n * 30),
    )
    return fig


def fig_risk_heatmap(hs):
    """Heatmap: Chapter HS vs metrik risiko."""
    ch_agg = hs.groupby("HS_CHAPTER").agg(
        n_hs        =("POS_TARIF_HS", "count"),
        avg_klu     =("n_klu", "mean"),
        max_klu     =("n_klu", "max"),
        avg_score   =("risk_score", "mean"),
        ppn_total   =("ppn", "sum"),
        lainlain_pct=("is_lainlain", "mean"),
        pph_ratio   =("pph_ppn_ratio", "median"),
    ).reset_index()
    ch_agg = ch_agg[ch_agg["n_hs"] >= 3].sort_values("avg_score", ascending=False).head(30)

    metrics = {
        "Avg KLU Disp.": "avg_klu",
        "Max KLU Disp.": "max_klu",
        "Avg Risk Score": "avg_score",
        "Lain-lain %":   "lainlain_pct",
        "PPh/PPN Ratio": "pph_ratio",
    }

    z_data = []
    for col in metrics.values():
        series = ch_agg[col]
        z_data.append(((series - series.min()) / (series.max() - series.min() + 1e-9)).round(3).tolist())

    fig = go.Figure(go.Heatmap(
        z=z_data,
        x=[f"Ch.{int(c)}" for c in ch_agg["HS_CHAPTER"]],
        y=list(metrics.keys()),
        colorscale=[[0, "#1E293B"], [0.5, "#F59E0B"], [1, "#EF4444"]],
        hoverongaps=False,
        hovertemplate="Chapter: %{x}<br>Metrik: %{y}<br>Score: %{z:.3f}<extra></extra>",
        colorbar=dict(
            title=dict(text="Normalized Score", font=dict(color=CLR["text"])),
            tickfont=dict(color=CLR["text"]),
        ),
    ))
    fig.update_layout(
        title="<b>Heatmap Risiko per Chapter HS</b><br>"
              "<sup>Top 30 chapter berdasarkan Avg Risk Score | Warna merah = risiko lebih tinggi</sup>",
        **_layout(
            xaxis=dict(tickangle=-45, tickfont=dict(size=9)),
            yaxis=dict(tickfont=dict(size=10)),
        ),
        height=320,
    )
    return fig


def fig_mismatch_bar(df):
    """Bar - Mismatch lintas sektor."""
    SECTOR_KWS = {
        "Elektronik (Ch.85)":       ["tambang","pertambangan","batu bara","nikel","minyak bumi","migas",
                                      "makanan","minuman","bumbu","pariwisata","hiburan"],
        "Otomotif (Ch.87)":         ["makanan","minuman","pangan","pertanian","peternakan",
                                      "pariwisata","perhotelan","hiburan"],
        "Kimia/Farmasi (Ch.28-38)": ["pariwisata","hiburan","taman hiburan"],
        "Pangan (Ch.10-11)":        ["tambang","pertambangan","nikel","batu bara","minyak","migas",
                                      "tekstil","konstruksi"],
    }
    rows = []
    for cl, kws in SECTOR_KWS.items():
        mask = (df["CLUSTER"] == cl) & df["NM_KLU"].str.lower().str.contains("|".join(kws), na=False)
        sub = df[mask]
        if len(sub) > 0:
            rows.append({
                "Mismatch": f"{cl}\nvs KLU Tidak Wajar",
                "cluster":  cl,
                "n_baris":  len(sub),
                "n_npwp":   sub["NPWP"].nunique(),
                "ppn":      sub["PPN_DIBAYAR"].sum(),
            })
    if not rows:
        return None

    mdf = pd.DataFrame(rows).sort_values("ppn", ascending=True)
    colors = [CLUSTER_COLORS.get(c, CLR["muted"]) for c in mdf["cluster"]]

    fig = go.Figure(go.Bar(
        x=mdf["ppn"] / 1e9,
        y=mdf["Mismatch"],
        orientation="h",
        marker_color=colors,
        text=mdf.apply(lambda r: f"Rp {r['ppn']/1e9:,.0f} M | {r['n_npwp']} NPWP", axis=1),
        textposition="outside",
        textfont=dict(size=9),
        hovertemplate="<b>%{y}</b><br>PPN: Rp %{x:,.1f} M<extra></extra>",
    ))
    fig.update_layout(
        title="<b>Mismatch Lintas Sektor: KLU Tidak Wajar</b><br>"
              "<sup>WP mengimpor barang yang tidak sesuai bidang usaha terdaftar</sup>",
        xaxis_title="Total PPN (Rp Miliar)",
        **_layout(yaxis=dict(tickfont=dict(size=9))),
        height=350,
    )
    return fig


def fig_top_riskscore(hs, n=25):
    """Bubble chart Top HS by Risk Score."""
    top = hs.nlargest(n, "risk_score").sort_values("risk_score")
    top["label"] = top["POS_TARIF_HS"].astype(str)
    top["nm_short"] = top["NM_DETIL"].fillna("N/A").str[:30]
    top["color"] = top["CLUSTER"].map(CLUSTER_COLORS).fillna(CLR["muted"])

    fig = go.Figure(go.Bar(
        x=top["risk_score"],
        y=top["label"] + " | " + top["nm_short"],
        orientation="h",
        marker=dict(
            color=top["risk_score"],
            colorscale=[[0, "#1E3A5F"], [0.4, CLR["warm"]], [1, CLR["danger"]]],
            cmin=0, cmax=1,
            colorbar=dict(title=dict(text="Risk Score", font=dict(color=CLR["text"])),
                          tickfont=dict(color=CLR["text"])),
        ),
        text=top["risk_score"].apply(lambda x: f"{x:.3f}"),
        textposition="outside",
        textfont=dict(size=9),
        hovertemplate=(
            "<b>HS %{y}</b><br>Risk Score: %{x:.4f}<extra></extra>"
        ),
    ))
    fig.update_layout(
        title=f"<b>Top {n} HS Code berdasarkan Risk Score Gabungan</b><br>"
              "<sup>Skor = Dispersi KLU (25%) + Nilai PPN (40%) + Konsentrasi NPWP (10%) + Catch-all (25%)</sup>",
        xaxis_title="Risk Score [0-1]",
        **_layout(yaxis=dict(tickfont=dict(size=9))),
        height=max(400, n * 28),
    )
    return fig


# ─────────────────────────────────────────────
# BUILD HTML DASHBOARD
# ─────────────────────────────────────────────

def build_html_dashboard(figs: dict, out_path: str, input_file: str):
    """Gabungkan semua figure menjadi 1 file HTML."""
    import plotly.io as pio

    nav_items = ""
    sections  = ""

    for i, (title, fig) in enumerate(figs.items()):
        if fig is None:
            continue
        anchor = f"chart_{i}"
        nav_items += f'<li><a href="#{anchor}">{title}</a></li>\n'
        chart_html = pio.to_html(fig, full_html=False, include_plotlyjs=False, config={"responsive": True})
        sections += f"""
        <section id="{anchor}" class="chart-section">
            <div class="chart-card">
                {chart_html}
            </div>
        </section>
        """

    ts = datetime.now().strftime("%d %b %Y %H:%M")
    html = f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dashboard Visualisasi PIB x HS Code x KLU</title>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0B0F1A; color:#F1F5F9; font-family:'DM Sans',sans-serif; }}

.topbar {{
    position: fixed; top:0; left:0; right:0; z-index:100;
    background:rgba(11,15,26,0.9); backdrop-filter:blur(16px);
    border-bottom:1px solid #2A3A52;
    padding:0 2rem; height:52px;
    display:flex; align-items:center; justify-content:space-between;
}}
.topbar-brand {{
    font-family:'JetBrains Mono',monospace;
    font-size:0.75rem; letter-spacing:0.1em;
    text-transform:uppercase; color:#3B82F6;
}}
.topbar-meta {{ font-size:0.75rem; color:#64748B; }}

.sidebar {{
    position:fixed; left:0; top:52px; bottom:0;
    width:220px; overflow-y:auto;
    background:#111827; border-right:1px solid #2A3A52;
    padding:1.5rem 0;
}}
.sidebar ul {{ list-style:none; }}
.sidebar li a {{
    display:block; padding:0.5rem 1.5rem;
    font-size:0.78rem; color:#94A3B8;
    text-decoration:none; border-left:2px solid transparent;
    transition:all 0.2s;
}}
.sidebar li a:hover {{
    color:#F1F5F9; border-left-color:#3B82F6;
    background:rgba(59,130,246,0.06);
}}

.main {{
    margin-left:220px; margin-top:52px;
    padding:1.5rem 2rem;
}}

.hero {{
    background:linear-gradient(135deg,rgba(59,130,246,0.08),rgba(245,158,11,0.04));
    border:1px solid #2A3A52; border-radius:12px;
    padding:2rem; margin-bottom:1.5rem;
}}
.hero h1 {{
    font-size:clamp(1.4rem,2.5vw,2rem); font-weight:700;
    background:linear-gradient(135deg,#F1F5F9,#3B82F6);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    background-clip:text; margin-bottom:0.5rem;
}}
.hero p {{ color:#94A3B8; font-size:0.9rem; }}

.chart-section {{ margin-bottom:1.5rem; }}
.chart-card {{
    background:#111827; border:1px solid #2A3A52;
    border-radius:12px; padding:0.5rem;
    box-shadow:0 4px 24px rgba(0,0,0,0.3);
}}

::-webkit-scrollbar {{ width:6px; height:6px; }}
::-webkit-scrollbar-track {{ background:#0B0F1A; }}
::-webkit-scrollbar-thumb {{ background:#2A3A52; border-radius:3px; }}
::-webkit-scrollbar-thumb:hover {{ background:#3B82F6; }}

@media (max-width:768px) {{
    .sidebar {{ display:none; }}
    .main {{ margin-left:0; padding:1rem; }}
}}
</style>
</head>
<body>

<div class="topbar">
    <div class="topbar-brand">CRM SR-15 / 2026 - Dashboard Analisis PIB</div>
    <div class="topbar-meta">Sumber: {input_file} &nbsp;|&nbsp; Dibuat: {ts}</div>
</div>

<nav class="sidebar">
    <ul>
        {nav_items}
    </ul>
</nav>

<main class="main">
    <div class="hero">
        <h1>Dashboard Visualisasi PIB x HS Code x KLU</h1>
        <p>Subtim Data Analyst CRM - Specific Risk Importir Umum 2026 &nbsp;|&nbsp;
           Sumber data: {input_file} &nbsp;|&nbsp; Dibuat: {ts}</p>
    </div>

    {sections}
</main>

</body>
</html>"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"    [OK] {out_path}")


# ─────────────────────────────────────────────
# MATPLOTLIB STATIC CHARTS (PNG)
# ─────────────────────────────────────────────

def build_static_png(df, hs, pairs, out_dir: str):
    """Satu PNG ringkasan 3x3 panel."""
    BG   = "#0B0F1A"
    CARD = "#111827"
    ACC  = "#3B82F6"
    WARM = "#F59E0B"
    DNG  = "#EF4444"
    OK   = "#10B981"
    TXT  = "#F1F5F9"
    MUT  = "#94A3B8"

    plt.rcParams.update({
        "figure.facecolor":  BG,
        "axes.facecolor":    CARD,
        "axes.edgecolor":    "#2A3A52",
        "axes.labelcolor":   MUT,
        "text.color":        TXT,
        "xtick.color":       MUT,
        "ytick.color":       MUT,
        "grid.color":        "#2A3A52",
        "grid.alpha":        0.5,
        "font.family":       "DejaVu Sans",
        "font.size":         9,
    })

    fig = plt.figure(figsize=(20, 24), facecolor=BG)
    fig.suptitle(
        "Dashboard Analisis PIB x HS Code x KLU | SR Importir Umum 2026",
        fontsize=16, fontweight="bold", color=TXT, y=0.995
    )
    gs = GridSpec(4, 3, figure=fig, hspace=0.45, wspace=0.35)

    # ── Panel 1: KPI text
    ax0 = fig.add_subplot(gs[0, 0])
    ax0.axis("off")
    ax0.set_title("Ringkasan Data 2023", color=ACC, fontweight="bold", pad=8)
    kpis = [
        ("Total Baris",      f"{len(df):,}",               TXT),
        ("HS Code Unik",     f"{df['POS_TARIF_HS'].nunique():,}", ACC),
        ("KLU Unik",         f"{df['KD_KLU'].nunique():,}",      OK),
        ("NPWP Importir",    f"{df['NPWP'].nunique():,}",         WARM),
        ("Total PPN",        f"Rp {df['PPN_DIBAYAR'].sum()/1e12:.2f} T", ACC),
        ("Total PPh",        f"Rp {df['PPH_DIBAYAR'].sum()/1e12:.2f} T", OK),
        ("Catch-all %",      f"{df['IS_LAINLAIN'].mean()*100:.1f}%",     DNG),
        ("HS Kritis >100KLU",f"{(hs['n_klu']>100).sum():,}",             DNG),
    ]
    for i, (k, v, c) in enumerate(kpis):
        y = 0.92 - i * 0.115
        ax0.text(0.02, y, k, transform=ax0.transAxes, color=MUT, fontsize=9)
        ax0.text(0.98, y, v, transform=ax0.transAxes, color=c, fontsize=10,
                 fontweight="bold", ha="right")
        ax0.plot([0, 1], [y - 0.06, y - 0.06],
                 color="#2A3A52", linewidth=0.5, transform=ax0.transAxes)

    # ── Panel 2: Distribusi dispersi
    ax1 = fig.add_subplot(gs[0, 1:])
    cat_order = list(DISP_COLORS.keys())
    dist = hs.groupby("disp_cat")["POS_TARIF_HS"].count().reindex(cat_order, fill_value=0)
    bars = ax1.bar(range(len(dist)), dist.values,
                   color=[DISP_COLORS.get(c, MUT) for c in dist.index], edgecolor="none")
    ax1.set_xticks(range(len(dist)))
    ax1.set_xticklabels([c.split("(")[0].strip() for c in dist.index], rotation=25, ha="right", fontsize=8)
    ax1.set_title("Distribusi Dispersi KLU per HS Code", color=ACC, fontweight="bold", pad=8)
    ax1.set_ylabel("Jumlah HS Code", color=MUT)
    ax1.yaxis.grid(True, alpha=0.3)
    for bar, val in zip(bars, dist.values):
        if val > 0:
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5,
                     f"{val:,}", ha="center", va="bottom", fontsize=8, color=TXT)

    # ── Panel 3: Top 15 HS by PPN
    ax2 = fig.add_subplot(gs[1, :])
    top15 = hs.nlargest(15, "ppn").sort_values("ppn")
    labels = (top15["POS_TARIF_HS"].astype(str) + " | " +
              top15["NM_DETIL"].fillna("N/A").str[:38])
    colors = [CLUSTER_COLORS.get(c, MUT) for c in top15["CLUSTER"]]
    bars2 = ax2.barh(range(len(top15)), top15["ppn"] / 1e12, color=colors, edgecolor="none")
    ax2.set_yticks(range(len(top15)))
    ax2.set_yticklabels(labels, fontsize=8)
    ax2.set_title("Top 15 HS Code berdasarkan Nilai PPN (Rp Triliun)", color=ACC, fontweight="bold", pad=8)
    ax2.set_xlabel("Total PPN (Rp Triliun)", color=MUT)
    ax2.xaxis.grid(True, alpha=0.3)
    for bar, val in zip(bars2, top15["ppn"] / 1e12):
        ax2.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height()/2,
                 f"{val:.2f}T", va="center", fontsize=8, color=TXT)
    patches = [mpatches.Patch(color=c, label=l) for l, c in CLUSTER_COLORS.items()]
    ax2.legend(handles=patches, loc="lower right", framealpha=0.3,
               facecolor=CARD, edgecolor="#2A3A52", fontsize=8)

    # ── Panel 4: Donut klaster PPN
    ax3 = fig.add_subplot(gs[2, 0])
    cl_agg = hs.groupby("CLUSTER")["ppn"].sum().sort_values(ascending=False)
    cl_colors = [CLUSTER_COLORS.get(c, MUT) for c in cl_agg.index]
    wedges, texts, autotexts = ax3.pie(
        cl_agg.values, labels=None,
        colors=cl_colors, autopct="%1.1f%%",
        startangle=90, wedgeprops=dict(width=0.55),
        textprops=dict(color=TXT, fontsize=8),
        pctdistance=0.75,
    )
    for at in autotexts:
        at.set_fontsize(8)
    ax3.set_title("Komposisi PPN per Klaster", color=ACC, fontweight="bold", pad=8)
    ax3.legend(cl_agg.index, loc="lower center", bbox_to_anchor=(0.5, -0.18),
               ncol=2, framealpha=0.3, facecolor=CARD, edgecolor="#2A3A52", fontsize=7)

    # ── Panel 5: Scatter PPN vs Dispersi (log-log)
    ax4 = fig.add_subplot(gs[2, 1])
    for cl, col in CLUSTER_COLORS.items():
        sub = hs[(hs["CLUSTER"] == cl) & (hs["ppn"] > 1e8)]
        ax4.scatter(sub["n_klu"], sub["ppn"]/1e9, c=col, s=15, alpha=0.5, label=cl)
    ax4.axvline(50,  color=WARM, linestyle="--", linewidth=1, alpha=0.7)
    ax4.axvline(100, color=DNG,  linestyle="--", linewidth=1, alpha=0.7)
    ax4.set_xscale("log"); ax4.set_yscale("log")
    ax4.set_xlabel("KLU Unik (log)", color=MUT)
    ax4.set_ylabel("PPN Rp Miliar (log)", color=MUT)
    ax4.set_title("Scatter: PPN vs Dispersi KLU", color=ACC, fontweight="bold", pad=8)
    ax4.yaxis.grid(True, alpha=0.3); ax4.xaxis.grid(True, alpha=0.3)

    # ── Panel 6: Top 15 Risk Score
    ax5 = fig.add_subplot(gs[2, 2])
    top_r = hs.nlargest(15, "risk_score").sort_values("risk_score")
    bar_colors = plt.cm.RdYlGn_r(np.linspace(0.2, 0.9, len(top_r)))
    ax5.barh(range(len(top_r)), top_r["risk_score"], color=bar_colors, edgecolor="none")
    ax5.set_yticks(range(len(top_r)))
    ax5.set_yticklabels(top_r["POS_TARIF_HS"].astype(str), fontsize=8)
    ax5.set_xlabel("Risk Score", color=MUT)
    ax5.set_title("Top 15 HS by Risk Score", color=ACC, fontweight="bold", pad=8)
    ax5.xaxis.grid(True, alpha=0.3)

    # ── Panel 7: PPh/PPN ratio per klaster (box)
    ax6 = fig.add_subplot(gs[3, 0:2])
    cluster_ratios = []
    cluster_labels = []
    cluster_colors_box = []
    for cl, col in CLUSTER_COLORS.items():
        sub = hs[(hs["CLUSTER"] == cl) & (hs["pph_ppn_ratio"] > 0) &
                 (hs["pph_ppn_ratio"] < 5)]
        if len(sub) > 5:
            cluster_ratios.append(sub["pph_ppn_ratio"].values)
            cluster_labels.append(cl.split("(")[0].strip())
            cluster_colors_box.append(col)
    if cluster_ratios:
        bp = ax6.boxplot(cluster_ratios, patch_artist=True, notch=False,
                         medianprops=dict(color="white", linewidth=2),
                         whiskerprops=dict(color=MUT), capprops=dict(color=MUT),
                         flierprops=dict(marker=".", color=MUT, alpha=0.3, markersize=3))
        for patch, col in zip(bp["boxes"], cluster_colors_box):
            patch.set_facecolor(col)
            patch.set_alpha(0.6)
        ax6.set_xticklabels(cluster_labels, fontsize=8)
        ax6.axhline(0.25, color=MUT,  linestyle=":",  linewidth=1, label="Normal ~0.25")
        ax6.axhline(2.0,  color=DNG,  linestyle="--", linewidth=1, label="Anomali >2.0")
        ax6.axhline(0.05, color=WARM, linestyle="--", linewidth=1, label="Anomali <0.05")
        ax6.legend(fontsize=8, framealpha=0.3, facecolor=CARD, edgecolor="#2A3A52")
    ax6.set_title("Distribusi Rasio PPh/PPN per Klaster", color=ACC, fontweight="bold", pad=8)
    ax6.set_ylabel("Rasio PPh/PPN", color=MUT)
    ax6.yaxis.grid(True, alpha=0.3)

    # ── Panel 8: Top anomali mismatch
    ax7 = fig.add_subplot(gs[3, 2])
    SECTOR_KWS = {
        "Elektronik (Ch.85)":       ["tambang","pertambangan","batu bara","nikel","minyak bumi","migas"],
        "Otomotif (Ch.87)":         ["makanan","minuman","pangan","pertanian"],
        "Kimia/Farmasi (Ch.28-38)": ["pariwisata","hiburan"],
        "Pangan (Ch.10-11)":        ["tambang","pertambangan","nikel","batu bara"],
    }
    mrows = []
    for cl, kws in SECTOR_KWS.items():
        mask = (df["CLUSTER"] == cl) & df["NM_KLU"].str.lower().str.contains("|".join(kws), na=False)
        ppn_val = df[mask]["PPN_DIBAYAR"].sum()
        if ppn_val > 0:
            mrows.append({"label": cl.split("(")[0].strip(), "ppn": ppn_val,
                          "color": CLUSTER_COLORS.get(cl, MUT)})
    if mrows:
        mdf = pd.DataFrame(mrows).sort_values("ppn")
        ax7.barh(range(len(mdf)), mdf["ppn"]/1e9, color=mdf["color"], edgecolor="none")
        ax7.set_yticks(range(len(mdf)))
        ax7.set_yticklabels(mdf["label"], fontsize=8)
        ax7.set_xlabel("PPN Rp Miliar", color=MUT)
        ax7.xaxis.grid(True, alpha=0.3)
    ax7.set_title("Mismatch Lintas Sektor", color=ACC, fontweight="bold", pad=8)

    # Simpan
    png_path = os.path.join(out_dir, "dashboard_visualisasi.png")
    plt.savefig(png_path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close()
    print(f"    [OK] {png_path}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Visualisasi Dashboard PIB x HS Code x KLU")
    parser.add_argument("--input",  default="sample_2023.xlsx")
    parser.add_argument("--output", default="output")
    args = parser.parse_args()

    print()
    print("=" * 65)
    print("  Visualisasi Dashboard PIB x HS Code x KLU")
    print("  SR Importir Umum - CRM Subtim Data Analyst 2026")
    print("=" * 65)

    os.makedirs(args.output, exist_ok=True)
    df, hs, pairs = load_and_prepare(args.input)

    print("[3/3] Membuat visualisasi...")

    # Kumpulkan semua figure
    figs = {}
    figs["Ringkasan Data"]           = fig_kpi(df, hs)
    figs["Distribusi Dispersi KLU"]  = fig_dispersi_bar(hs)
    figs["Top 20 HS by PPN"]         = fig_top_hs_ppn(hs, 20)
    figs["Komposisi per Klaster"]    = fig_cluster_donut(hs)
    figs["Scatter PPN vs Dispersi"]  = fig_scatter_risk(hs)
    figs["Rasio PPh/PPN"]            = fig_pph_ppn_hist(hs)
    figs["Heatmap Risiko Chapter"]   = fig_risk_heatmap(hs)
    figs["Top Anomali KLU Outlier"]  = fig_top_anomali(pairs, 20)
    figs["Mismatch Lintas Sektor"]   = fig_mismatch_bar(df)
    figs["Top 25 Risk Score"]        = fig_top_riskscore(hs, 25)

    # HTML dashboard
    html_path = os.path.join(args.output, "dashboard_visualisasi.html")
    build_html_dashboard(figs, html_path, args.input)

    # PNG static
    build_static_png(df, hs, pairs, args.output)

    print()
    print("-" * 65)
    print("  Output:")
    for f in ["dashboard_visualisasi.html", "dashboard_visualisasi.png"]:
        p = os.path.join(args.output, f)
        if os.path.exists(p):
            print(f"    {f:45s}  {os.path.getsize(p)/1024:>8.1f} KB")
    print()
    print("  Buka di browser:", os.path.abspath(html_path))
    print("-" * 65)


if __name__ == "__main__":
    main()
