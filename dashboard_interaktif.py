#!/usr/bin/env python3
"""
Dashboard Interaktif PIB x HS Code x KLU
SR Importir Umum - CRM Subtim Data Analyst 2026

Jalankan : python dashboard_interaktif.py
Akses di  : http://127.0.0.1:8050
"""

import os
from collections import Counter

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Dash, dcc, html, Input, Output

# ============================================================
# CONSTANTS
# ============================================================

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
YEARS      = ["2022", "2023", "2024", "T1"]

CLR = {
    "bg":      "#0B0F1A",
    "card":    "#111827",
    "surface": "#1E293B",
    "border":  "#2A3A52",
    "accent":  "#3B82F6",
    "warm":    "#F59E0B",
    "danger":  "#EF4444",
    "success": "#10B981",
    "purple":  "#8B5CF6",
    "text":    "#BD4205",
    "muted":   "#94A3B8",
}

CLUSTER_COLORS = {
    "Elektronik (Ch.85)":       "#3B82F6",
    "Otomotif (Ch.87)":         "#F59E0B",
    "Kimia/Farmasi (Ch.28-38)": "#10B981",
    "Pangan (Ch.10-11)":        "#8B5CF6",
    "Lainnya":                  "#94A3B8",
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

METRIC_INFO = {
    "ppn":           ("Nilai PPN",      "Rp T",  1e12, ".2f"),
    "risk_score":    ("Risk Score",     "",      1,    ".3f"),
    "n_klu":         ("Dispersi KLU",  "KLU",   1,    ",.0f"),
    "n_npwp":        ("Jumlah NPWP",   "NPWP",  1,    ",.0f"),
    "pph_ppn_ratio": ("Rasio PPh/PPN", "",      1,    ".3f"),
}

# Excel column -> internal name
COL_MAP = {
    "HS Code":          "POS_TARIF_HS",
    "Cluster":          "CLUSTER",
    "# KLU Unik":       "n_klu",
    "Dispersi":         "disp_category",
    "# NPWP":           "n_npwp",
    "PPN Total (Rp)":   "ppn",
    "PPh Total (Rp)":   "pph",
    "PPh/PPN Ratio":    "pph_ppn_ratio",
    "Risk Score":       "risk_score",
    "Risk Events":      "risk_events",
    "Risk Flags":       "risk_flags",
    "Catch-all?":       "is_lainlain",
    "Nama Detail":      "NM_DETIL",
    "Nama Kelompok":    "NM_KELOMPOK",
    "# PIB":            "n_pib",
    "PPN per NPWP (Rp)":"ppn_per_npwp",
}

# ============================================================
# DATA LOADING & CACHING
# ============================================================

_CACHE: dict = {}


def load_profil(year: str) -> pd.DataFrame:
    if year in _CACHE:
        return _CACHE[year]

    path = os.path.join(OUTPUT_DIR, year, "02_Profil_HS_Code.xlsx")
    if not os.path.exists(path):
        _CACHE[year] = pd.DataFrame()
        return _CACHE[year]

    df = pd.read_excel(path, sheet_name="By_Risk_Score", header=3)
    df.rename(columns=COL_MAP, inplace=True)

    # Numeric coercion
    for col in ["ppn","pph","n_klu","n_npwp","n_pib","risk_score","pph_ppn_ratio","ppn_per_npwp","POS_TARIF_HS"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Derive chapter
    if "POS_TARIF_HS" in df.columns:
        df["HS_CHAPTER"] = (df["POS_TARIF_HS"] // 1_000_000).astype(int)

    # Normalize cluster names (some rows may have slight differences)
    if "CLUSTER" in df.columns:
        df["CLUSTER"] = df["CLUSTER"].fillna("Lainnya").astype(str)

    _CACHE[year] = df
    return df


def filter_df(df: pd.DataFrame, cluster: str, min_ppn_b: float,
              risk_lo: float, risk_hi: float, min_disp: int) -> pd.DataFrame:
    if df.empty:
        return df
    m = pd.Series(True, index=df.index)
    if cluster != "ALL" and "CLUSTER" in df.columns:
        m &= df["CLUSTER"] == cluster
    if min_ppn_b > 0 and "ppn" in df.columns:
        m &= df["ppn"] >= min_ppn_b * 1e9
    if "risk_score" in df.columns:
        m &= df["risk_score"].between(risk_lo, risk_hi)
    if min_disp > 0 and "n_klu" in df.columns:
        m &= df["n_klu"] >= min_disp
    return df[m].copy()


# ============================================================
# PLOTLY HELPERS
# ============================================================

_AXIS = dict(gridcolor=CLR["border"], zerolinecolor=CLR["border"],
             tickfont=dict(size=10), color=CLR["muted"])

_BASE = dict(
    paper_bgcolor=CLR["bg"],
    plot_bgcolor=CLR["card"],
    font=dict(family="'Inter','Segoe UI',sans-serif", color=CLR["text"], size=11),
    margin=dict(l=10, r=10, t=44, b=10),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor=CLR["border"],
                borderwidth=1, font=dict(size=10)),
    hoverlabel=dict(bgcolor=CLR["surface"], bordercolor=CLR["border"],
                    font=dict(color=CLR["text"], size=11)),
)


def lo(**kw) -> dict:
    """Merge base layout with per-chart overrides, handling xaxis/yaxis safely."""
    out = dict(**_BASE)
    out["xaxis"] = dict(**_AXIS)
    out["yaxis"] = dict(**_AXIS)
    for k, v in kw.items():
        if k in ("xaxis", "yaxis", "xaxis2", "yaxis2") and isinstance(v, dict):
            out[k] = {**_AXIS, **v}
        else:
            out[k] = v
    return out


def empty_fig(msg: str = "Tidak ada data untuk filter ini") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, xref="paper", yref="paper", x=0.5, y=0.5,
                       showarrow=False, font=dict(color=CLR["muted"], size=13))
    fig.update_layout(**lo())
    return fig


# ============================================================
# CHART FUNCTIONS
# ============================================================

def fig_topn_bar(df: pd.DataFrame, metric: str, topn: int) -> go.Figure:
    """Horizontal bar: Top N HS codes by selected metric."""
    if df.empty or metric not in df.columns:
        return empty_fig()

    label, unit, divisor, fmt = METRIC_INFO.get(metric, (metric, "", 1, ".2f"))
    top = df.nlargest(topn, metric).sort_values(metric)

    top_val   = top[metric] / divisor
    top_label = (top["POS_TARIF_HS"].astype(int).astype(str) + "  " +
                 top.get("NM_DETIL", pd.Series(["N/A"] * len(top), index=top.index)).fillna("N/A").str[:42])
    top_color = (top["CLUSTER"].map(CLUSTER_COLORS).fillna(CLR["muted"])
                 if "CLUSTER" in top.columns else CLR["accent"])
    hover = (
        "HS: " + top["POS_TARIF_HS"].astype(int).astype(str)
        + "<br>" + label + ": " + top_val.apply(lambda v: f"{v:{fmt}}") + (" " + unit if unit else "")
        + "<br>Klaster: " + (top.get("CLUSTER", pd.Series(["N/A"]*len(top), index=top.index)).fillna("N/A"))
        + "<br>Dispersi KLU: " + top.get("n_klu", pd.Series([0]*len(top), index=top.index)).apply(lambda v: f"{int(v):,}")
        + "<br>NPWP: " + top.get("n_npwp", pd.Series([0]*len(top), index=top.index)).apply(lambda v: f"{int(v):,}")
        + "<br>Risk Score: " + top.get("risk_score", pd.Series([0]*len(top), index=top.index)).apply(lambda v: f"{v:.3f}")
    )

    fig = go.Figure(go.Bar(
        x=top_val, y=top_label, orientation="h",
        marker_color=top_color,
        hovertext=hover, hoverinfo="text",
        text=top_val.apply(lambda v: f"{v:{fmt}}"),
        textposition="outside", textfont=dict(size=9),
    ))

    # Cluster legend
    shown = set(top["CLUSTER"].tolist()) if "CLUSTER" in top.columns else set()
    for cl, col in CLUSTER_COLORS.items():
        if cl in shown:
            fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers",
                marker=dict(color=col, size=10, symbol="square"),
                name=cl, showlegend=True))

    axis_title = f"{label} ({unit})" if unit else label
    fig.update_layout(**lo(
        title=f"<b>Top {topn} HS Code — {label}</b>",
        xaxis=dict(title=axis_title),
        yaxis=dict(tickfont=dict(size=9)),
        height=max(380, topn * 30),
    ))
    return fig


def fig_dispersi_dist(df: pd.DataFrame) -> go.Figure:
    """Bar + line: HS count and PPN by dispersi category (dual-axis)."""
    if df.empty or "disp_category" not in df.columns:
        return empty_fig()

    cat_order = list(DISP_COLORS.keys())
    cnt = df.groupby("disp_category")["POS_TARIF_HS"].count().reindex(cat_order, fill_value=0)
    ppn = df.groupby("disp_category")["ppn"].sum().reindex(cat_order, fill_value=0) / 1e12

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=cnt.index, y=cnt.values,
        marker_color=[DISP_COLORS.get(c, CLR["muted"]) for c in cnt.index],
        name="Jumlah HS", hovertemplate="%{x}<br>HS: %{y:,}<extra></extra>",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=ppn.index, y=ppn.values, mode="lines+markers",
        marker_color=CLR["warm"], line=dict(color=CLR["warm"], width=2),
        name="PPN (T)", hovertemplate="%{x}<br>PPN: Rp %{y:.2f} T<extra></extra>",
    ), secondary_y=True)

    short = [c.split(" - ")[-1].split("(")[0].strip() for c in cnt.index]
    fig.update_xaxes(tickvals=list(cnt.index), ticktext=short,
                     tickangle=-30, tickfont=dict(size=9),
                     gridcolor=CLR["border"], zerolinecolor=CLR["border"])
    fig.update_yaxes(title_text="Jumlah HS", secondary_y=False,
                     gridcolor=CLR["border"], zerolinecolor=CLR["border"])
    fig.update_yaxes(title_text="PPN (Rp T)", secondary_y=True,
                     gridcolor="rgba(0,0,0,0)", zerolinecolor=CLR["border"])
    fig.update_layout(**lo(title="<b>Distribusi Dispersi KLU</b>", height=320, bargap=0.3))
    return fig


def fig_cluster_donut(df: pd.DataFrame) -> go.Figure:
    """Side-by-side donut: PPN share and HS count share per cluster."""
    if df.empty or "CLUSTER" not in df.columns:
        return empty_fig()

    agg = df.groupby("CLUSTER").agg(ppn=("ppn","sum"), n=("POS_TARIF_HS","count")).reset_index()
    colors = [CLUSTER_COLORS.get(c, CLR["muted"]) for c in agg["CLUSTER"]]

    fig = make_subplots(1, 2, specs=[[{"type":"pie"}, {"type":"pie"}]],
                        subplot_titles=["PPN Share", "HS Code Count"])
    fig.add_trace(go.Pie(
        labels=agg["CLUSTER"], values=agg["ppn"]/1e12,
        hole=0.52, marker_colors=colors, textinfo="percent",
        hovertemplate="%{label}<br>Rp %{value:.2f} T (%{percent})<extra></extra>",
    ), 1, 1)
    fig.add_trace(go.Pie(
        labels=agg["CLUSTER"], values=agg["n"],
        hole=0.52, marker_colors=colors, textinfo="percent",
        hovertemplate="%{label}<br>%{value:,} HS (%{percent})<extra></extra>",
    ), 1, 2)
    fig.update_layout(**lo(title="<b>Komposisi per Klaster</b>", height=320,
                           showlegend=False))
    return fig


def fig_scatter(df: pd.DataFrame) -> go.Figure:
    """Log-log scatter: PPN vs dispersi KLU, size = n_npwp, color = cluster."""
    if df.empty or "ppn" not in df.columns or "n_klu" not in df.columns:
        return empty_fig()

    sub = df[(df["ppn"] > 0) & (df["n_klu"] > 0)].copy()
    if sub.empty:
        return empty_fig()

    fig = go.Figure()
    for cl, col in CLUSTER_COLORS.items():
        s = sub[sub["CLUSTER"] == cl] if "CLUSTER" in sub.columns else pd.DataFrame()
        if s.empty:
            continue
        sz = np.sqrt(s["n_npwp"].clip(1)) * 3.5 if "n_npwp" in s.columns else 8
        hover = (
            "HS: " + s["POS_TARIF_HS"].astype(int).astype(str)
            + "<br>PPN: Rp " + (s["ppn"]/1e9).apply(lambda v: f"{v:,.1f}") + " M"
            + "<br>Dispersi KLU: " + s["n_klu"].apply(lambda v: f"{int(v):,}")
            + "<br>NPWP: " + s["n_npwp"].apply(lambda v: f"{int(v):,}")
            + "<br>Risk Score: " + s["risk_score"].apply(lambda v: f"{v:.3f}")
        )
        fig.add_trace(go.Scatter(
            x=s["n_klu"], y=s["ppn"]/1e9,
            mode="markers", name=cl,
            marker=dict(color=col, size=sz, opacity=0.55,
                        line=dict(color="rgba(0,0,0,0.25)", width=0.5)),
            hovertext=hover, hoverinfo="text",
        ))

    fig.add_vline(x=100, line_dash="dot", line_color=CLR["danger"], opacity=0.65,
                  annotation_text="Threshold 100 KLU", annotation_font_color=CLR["danger"])
    fig.update_layout(**lo(
        title="<b>Scatter: Nilai PPN vs Dispersi KLU</b><br>"
              "<sup>Ukuran titik = jumlah NPWP importir</sup>",
        xaxis=dict(type="log", title="Dispersi KLU (log)"),
        yaxis=dict(type="log", title="Total PPN (Rp Miliar, log)"),
        height=420,
    ))
    return fig


def fig_violin(df: pd.DataFrame) -> go.Figure:
    """Violin: PPh/PPN ratio distribution per cluster."""
    if df.empty or "pph_ppn_ratio" not in df.columns or "CLUSTER" not in df.columns:
        return empty_fig()

    sub = df[(df["pph_ppn_ratio"] > 0) & (df["pph_ppn_ratio"] < 5)].copy()
    if sub.empty:
        return empty_fig()

    fig = go.Figure()
    for cl, col in CLUSTER_COLORS.items():
        s = sub[sub["CLUSTER"] == cl]
        if s.empty:
            continue
        fig.add_trace(go.Violin(
            y=s["pph_ppn_ratio"], name=cl, line_color=col,
            fillcolor=col, opacity=0.45,
            box_visible=True, meanline_visible=True,
            hoverinfo="y+name",
        ))

    fig.add_hline(y=2.0, line_dash="dot", line_color=CLR["danger"], opacity=0.7,
                  annotation_text="Artificial Loss >2.0", annotation_font_color=CLR["danger"])
    fig.add_hline(y=0.05, line_dash="dot", line_color=CLR["warm"], opacity=0.7,
                  annotation_text="API-P Abuse <0.05", annotation_font_color=CLR["warm"])
    fig.update_layout(**lo(
        title="<b>Distribusi Rasio PPh/PPN per Klaster</b>",
        yaxis=dict(title="PPh / PPN Ratio"),
        height=380, violinmode="group",
    ))
    return fig


def fig_heatmap(df: pd.DataFrame) -> go.Figure:
    """Heatmap: chapter HS × risk metrics (normalized 0-1)."""
    if df.empty or "HS_CHAPTER" not in df.columns:
        return empty_fig()

    ch = df.groupby("HS_CHAPTER").agg(
        n_hs      =("POS_TARIF_HS", "count"),
        avg_klu   =("n_klu",        "mean"),
        max_klu   =("n_klu",        "max"),
        avg_score =("risk_score",   "mean"),
        pph_med   =("pph_ppn_ratio","median"),
    ).reset_index()
    ch = ch[ch["n_hs"] >= 3].sort_values("avg_score", ascending=False).head(30)
    if ch.empty:
        return empty_fig()

    metrics = {"Avg KLU": "avg_klu", "Max KLU": "max_klu",
               "Avg Risk": "avg_score", "PPh/PPN Median": "pph_med"}
    z = []
    for col in metrics.values():
        s = ch[col]
        z.append(((s - s.min()) / (s.max() - s.min() + 1e-9)).round(3).tolist())

    fig = go.Figure(go.Heatmap(
        z=z,
        x=[f"Ch.{int(c)}" for c in ch["HS_CHAPTER"]],
        y=list(metrics.keys()),
        colorscale=[[0, CLR["surface"]], [0.5, CLR["warm"]], [1, CLR["danger"]]],
        colorbar=dict(title=dict(text="Score", font=dict(color=CLR["text"])),
                      tickfont=dict(color=CLR["text"])),
        hovertemplate="Chapter: %{x}<br>Metrik: %{y}<br>Score: %{z:.3f}<extra></extra>",
    ))
    fig.update_layout(**lo(
        title="<b>Heatmap Risiko per Chapter HS</b><br>"
              "<sup>Top 30 chapter — skor dinormalisasi 0-1</sup>",
        xaxis=dict(tickangle=-45, tickfont=dict(size=9)),
        yaxis=dict(tickfont=dict(size=10)),
        height=260,
    ))
    return fig


def fig_risk_events(df: pd.DataFrame) -> go.Figure:
    """Horizontal bar: count of HS codes per risk event type."""
    if df.empty or "risk_events" not in df.columns:
        return empty_fig()

    events: list = []
    for evts in df["risk_events"].dropna():
        for e in str(evts).split("|"):
            e = e.strip()
            if e and e != "-":
                events.append(e)
    if not events:
        return empty_fig("Tidak ada risk events pada filter ini")

    cnt = Counter(events)
    ev_df = pd.DataFrame(cnt.items(), columns=["event", "count"]).sort_values("count")

    evt_col = {
        "Misdeclaration":       CLR["danger"],
        "Mispricing":           CLR["warm"],
        "API-P Abuse":          CLR["accent"],
        "Artificial Loss":      "#F97316",
        "Konsentrasi Importir": CLR["success"],
    }
    fig = go.Figure(go.Bar(
        x=ev_df["count"], y=ev_df["event"], orientation="h",
        marker_color=[evt_col.get(e, CLR["muted"]) for e in ev_df["event"]],
        hovertemplate="%{y}: %{x:,} HS Code<extra></extra>",
        text=ev_df["count"].apply(lambda v: f"{v:,}"),
        textposition="outside",
    ))
    fig.update_layout(**lo(
        title="<b>Distribusi Risk Events</b><br>"
              "<sup>Jumlah HS Code yang terkategorisasi tiap jenis risiko</sup>",
        xaxis=dict(title="Jumlah HS Code"),
        yaxis=dict(tickfont=dict(size=11)),
        height=300,
    ))
    return fig


def fig_risk_bar(df: pd.DataFrame, topn: int) -> go.Figure:
    """Horizontal bar: Top N HS by risk score, colored by gradient."""
    if df.empty or "risk_score" not in df.columns:
        return empty_fig()

    top = df.nlargest(topn, "risk_score").sort_values("risk_score")
    label = (top["POS_TARIF_HS"].astype(int).astype(str) + "  " +
             top.get("NM_DETIL", pd.Series(["N/A"]*len(top), index=top.index)).fillna("N/A").str[:40])
    hover = (
        "HS: " + top["POS_TARIF_HS"].astype(int).astype(str)
        + "<br>Risk Score: " + top["risk_score"].apply(lambda v: f"{v:.4f}")
        + "<br>PPN: Rp " + (top["ppn"]/1e9).apply(lambda v: f"{v:,.1f}") + " M"
        + "<br>Dispersi: " + top["n_klu"].apply(lambda v: f"{int(v):,}") + " KLU"
        + "<br>Events: " + top.get("risk_events", pd.Series(["N/A"]*len(top), index=top.index)).fillna("N/A")
        + "<br>Flags: " + top.get("risk_flags", pd.Series(["N/A"]*len(top), index=top.index)).fillna("N/A")
    )
    fig = go.Figure(go.Bar(
        x=top["risk_score"], y=label, orientation="h",
        marker=dict(
            color=top["risk_score"],
            colorscale=[[0, "#1E3A5F"], [0.4, CLR["warm"]], [1, CLR["danger"]]],
            cmin=0, cmax=1,
            colorbar=dict(title=dict(text="Risk", font=dict(color=CLR["text"])),
                          tickfont=dict(color=CLR["text"])),
        ),
        hovertext=hover, hoverinfo="text",
        text=top["risk_score"].apply(lambda v: f"{v:.3f}"),
        textposition="outside",
    ))
    fig.update_layout(**lo(
        title=f"<b>Top {topn} HS Code — Risk Score Gabungan</b><br>"
              "<sup>Skor = Dispersi KLU (25%) + Nilai PPN (40%) + Konsentrasi NPWP (10%) + Catch-all (25%)</sup>",
        xaxis=dict(title="Risk Score [0-1]"),
        yaxis=dict(tickfont=dict(size=9)),
        height=max(400, topn * 30),
    ))
    return fig


# ============================================================
# LAYOUT HELPERS
# ============================================================

DD_STYLE = {
    "backgroundColor": CLR["surface"],
    "color": CLR["text"],
    "border": f"1px solid {CLR['border']}",
    "borderRadius": "6px",
}

SL_STYLE = {"marginBottom": "10px"}


def lbl(text: str) -> html.Div:
    return html.Div(text, style={
        "color": CLR["muted"], "fontSize": "10px", "fontWeight": "700",
        "letterSpacing": "0.08em", "textTransform": "uppercase",
        "marginTop": "14px", "marginBottom": "5px",
    })


def section_header(text: str) -> html.Div:
    return html.Div(text, style={
        "color": CLR["accent"], "fontSize": "10px", "fontWeight": "700",
        "letterSpacing": "0.12em", "textTransform": "uppercase",
        "marginBottom": "2px",
    })


def kpi_card(title: str, value: str, color: str, sub: str = "") -> html.Div:
    return html.Div([
        html.Div(title, style={"fontSize": "10px", "color": CLR["muted"],
                               "textTransform": "uppercase", "letterSpacing": "0.05em"}),
        html.Div(value, style={"fontSize": "21px", "fontWeight": "700",
                               "color": color, "lineHeight": "1.3", "marginTop": "2px"}),
        html.Div(sub, style={"fontSize": "10px", "color": CLR["muted"], "marginTop": "2px"}),
    ], style={
        "backgroundColor": CLR["card"],
        "borderRadius": "8px",
        "padding": "14px 18px",
        "borderTop": f"3px solid {color}",
        "flex": "1",
        "minWidth": "130px",
    })


def graph(fig: go.Figure) -> dcc.Graph:
    return dcc.Graph(
        figure=fig,
        config={"displayModeBar": True, "displaylogo": False,
                "modeBarButtonsToRemove": ["lasso2d", "select2d"]},
        style={"borderRadius": "8px", "overflow": "hidden"},
    )


def row2(left: html.Div, right: html.Div) -> html.Div:
    return html.Div([
        html.Div(left,  style={"flex": "1", "minWidth": "0"}),
        html.Div(right, style={"flex": "1", "minWidth": "0"}),
    ], style={"display": "flex", "gap": "14px"})


# ============================================================
# APP INSTANCE
# ============================================================

app = Dash(__name__, title="Dashboard PIB × HS Code × KLU")
app.config.suppress_callback_exceptions = True

# ── Sidebar ──────────────────────────────────────────────────
_sidebar = html.Div([
    section_header("Data"),

    lbl("Tahun / Periode"),
    dcc.Dropdown(
        id="dd-year",
        options=[{"label": y, "value": y} for y in YEARS],
        value="2023", clearable=False, style=DD_STYLE,
    ),

    lbl("Klaster"),
    dcc.Dropdown(id="dd-cluster", value="ALL", clearable=False, style=DD_STYLE),

    lbl("Metrik Utama"),
    dcc.Dropdown(
        id="dd-metric",
        options=[
            {"label": "Nilai PPN",      "value": "ppn"},
            {"label": "Risk Score",     "value": "risk_score"},
            {"label": "Dispersi KLU",  "value": "n_klu"},
            {"label": "Jumlah NPWP",   "value": "n_npwp"},
            {"label": "Rasio PPh/PPN", "value": "pph_ppn_ratio"},
        ],
        value="ppn", clearable=False, style=DD_STYLE,
    ),

    html.Hr(style={"borderColor": CLR["border"], "margin": "18px 0 8px"}),
    section_header("Filter"),

    lbl("Top N HS Code"),
    html.Div(dcc.Slider(id="sl-topn", min=5, max=50, step=5, value=20,
               marks={5:"5", 10:"10", 20:"20", 30:"30", 50:"50"},
               tooltip={"placement":"bottom","always_visible":False}),
             style=SL_STYLE),

    lbl("Minimum PPN (Rp Miliar)"),
    html.Div(dcc.Slider(id="sl-ppn", min=0, max=500, step=10, value=0,
               marks={0:"0", 100:"100M", 250:"250M", 500:"500M"},
               tooltip={"placement":"bottom","always_visible":True}),
             style=SL_STYLE),

    lbl("Risk Score Range"),
    html.Div(dcc.RangeSlider(id="sl-risk", min=0, max=1, step=0.05, value=[0, 1],
                    marks={0:"0", 0.25:"0.25", 0.5:"0.5", 0.75:"0.75", 1:"1"},
                    tooltip={"placement":"bottom","always_visible":False}),
             style=SL_STYLE),

    lbl("Minimum Dispersi KLU"),
    dcc.Dropdown(
        id="dd-disp",
        options=[
            {"label": "Semua KLU",  "value": 0},
            {"label": "> 5 KLU",    "value": 5},
            {"label": "> 10 KLU",   "value": 10},
            {"label": "> 50 KLU",   "value": 50},
            {"label": "> 100 KLU",  "value": 100},
        ],
        value=0, clearable=False, style=DD_STYLE,
    ),

    html.Hr(style={"borderColor": CLR["border"], "margin": "18px 0 10px"}),
    html.Div(id="sb-stats", style={
        "fontSize": "11px", "color": CLR["muted"], "lineHeight": "2.0",
    }),
], style={
    "width": "268px", "minWidth": "268px",
    "padding": "18px 14px",
    "borderRight": f"1px solid {CLR['border']}",
    "backgroundColor": CLR["card"],
    "height": "calc(100vh - 57px)",
    "overflowY": "auto",
    "position": "sticky", "top": "57px",
    "boxSizing": "border-box",
})

_tab_style = {"color": CLR["muted"], "padding": "8px 18px",
              "backgroundColor": CLR["card"], "borderBottom": "none",
              "fontSize": "13px"}
_tab_selected = {"color": CLR["text"], "padding": "8px 18px",
                 "backgroundColor": CLR["bg"],
                 "borderTop": f"2px solid {CLR['accent']}",
                 "borderBottom": "none", "fontSize": "13px", "fontWeight": "600"}

# ── Main layout ───────────────────────────────────────────────
app.layout = html.Div(style={
    "backgroundColor": CLR["bg"],
    "minHeight": "100vh",
    "fontFamily": "'Inter','Segoe UI',sans-serif",
    "color": CLR["text"],
}, children=[

    # Header
    html.Div([
        html.Div([
            html.Span("PIB \u00d7 HS Code \u00d7 KLU",
                      style={"fontSize": "17px", "fontWeight": "700"}),
            html.Span("  SR Importir Umum — CRM Subtim Data Analyst 2026",
                      style={"fontSize": "11px", "color": CLR["muted"], "marginLeft": "10px"}),
        ]),
        html.Div(id="hdr-info", style={"fontSize": "11px", "color": CLR["muted"],
                                        "textAlign": "right"}),
    ], style={
        "display": "flex", "justifyContent": "space-between", "alignItems": "center",
        "padding": "12px 22px",
        "backgroundColor": CLR["card"],
        "borderBottom": f"1px solid {CLR['border']}",
        "position": "sticky", "top": "0", "zIndex": "200",
        "height": "57px", "boxSizing": "border-box",
    }),

    # Body
    html.Div([
        _sidebar,

        # Main
        html.Div([
            # KPI row
            html.Div(id="kpi-row", style={
                "display": "flex", "gap": "10px", "flexWrap": "wrap",
                "padding": "14px 18px",
                "borderBottom": f"1px solid {CLR['border']}",
            }),
            # Tabs
            dcc.Tabs(id="tabs", value="tab-ov",
                     style={"backgroundColor": CLR["card"],
                            "borderBottom": f"1px solid {CLR['border']}"},
                     colors={"border": CLR["border"], "primary": CLR["accent"],
                             "background": CLR["card"]},
                     children=[
                dcc.Tab(label="Overview",           value="tab-ov",
                        style=_tab_style, selected_style=_tab_selected),
                dcc.Tab(label="Scatter & Klaster",  value="tab-sc",
                        style=_tab_style, selected_style=_tab_selected),
                dcc.Tab(label="Risiko & Chapter",   value="tab-risk",
                        style=_tab_style, selected_style=_tab_selected),
                dcc.Tab(label="Anomali & Risk Score", value="tab-anom",
                        style=_tab_style, selected_style=_tab_selected),
            ]),
            html.Div(id="tab-content",
                     style={"padding": "16px 18px", "overflowX": "hidden"}),
        ], style={"flex": "1", "overflowY": "auto",
                  "height": "calc(100vh - 57px)", "minWidth": "0"}),
    ], style={"display": "flex"}),
])


# ============================================================
# CALLBACKS
# ============================================================

@app.callback(
    Output("dd-cluster", "options"),
    Output("dd-cluster", "value"),
    Input("dd-year", "value"),
)
def update_cluster_opts(year):
    df = load_profil(year)
    opts = [{"label": "Semua Klaster", "value": "ALL"}]
    if not df.empty and "CLUSTER" in df.columns:
        for cl in sorted(df["CLUSTER"].dropna().unique()):
            opts.append({"label": cl, "value": cl})
    return opts, "ALL"


@app.callback(
    Output("kpi-row",  "children"),
    Output("sb-stats", "children"),
    Output("hdr-info", "children"),
    Input("dd-year",    "value"),
    Input("dd-cluster", "value"),
    Input("sl-ppn",     "value"),
    Input("sl-risk",    "value"),
    Input("dd-disp",    "value"),
)
def update_kpis(year, cluster, min_ppn, risk_range, min_disp):
    df = load_profil(year)
    if df.empty:
        return (
            [kpi_card("Status", "Tidak ada data", CLR["danger"])],
            f"Folder output/{year} tidak ditemukan.",
            f"Tahun {year}: tidak ada data",
        )

    risk_range = risk_range or [0, 1]
    df_f = filter_df(df, cluster or "ALL", float(min_ppn or 0),
                     float(risk_range[0]), float(risk_range[1]), int(min_disp or 0))

    n       = len(df_f)
    n_all   = len(df)
    ppn     = df_f["ppn"].sum() if "ppn" in df_f.columns else 0
    pph     = df_f["pph"].sum() if "pph" in df_f.columns else 0
    kritis  = int((df_f["n_klu"] > 100).sum()) if "n_klu" in df_f.columns else 0

    cards = [
        kpi_card("HS Code Terfilter", f"{n:,}", CLR["accent"],
                 f"dari {n_all:,} total ({n/max(n_all,1)*100:.1f}%)"),
        kpi_card("Total PPN", f"Rp {ppn/1e12:.2f} T", CLR["success"]),
        kpi_card("Total PPh", f"Rp {pph/1e12:.2f} T", CLR["warm"]),
        kpi_card("HS Kritis (>100 KLU)", f"{kritis:,}", CLR["danger"],
                 f"{kritis/max(n,1)*100:.1f}% dari terfilter"),
    ]

    stats = html.Div([
        html.B(f"Tahun: {year}"),
        html.Br(), f"Total HS: {n_all:,}",
        html.Br(), f"Terfilter: {n:,}",
        html.Br(), f"PPN: Rp {ppn/1e12:.2f} T",
        html.Br(), f"PPh: Rp {pph/1e12:.2f} T",
        html.Br(), f"Kritis >100 KLU: {kritis:,}",
    ])

    hdr = f"Data {year}  |  {n:,} HS Code  |  Rp {ppn/1e12:.1f} T PPN"
    return cards, stats, hdr


@app.callback(
    Output("tab-content", "children"),
    Input("tabs",       "value"),
    Input("dd-year",    "value"),
    Input("dd-cluster", "value"),
    Input("dd-metric",  "value"),
    Input("sl-topn",    "value"),
    Input("sl-ppn",     "value"),
    Input("sl-risk",    "value"),
    Input("dd-disp",    "value"),
)
def render_tab(tab, year, cluster, metric, topn, min_ppn, risk_range, min_disp):
    df = load_profil(year)
    if df.empty:
        return html.Div("Tidak ada data.", style={
            "color": CLR["muted"], "padding": "40px", "textAlign": "center"})

    risk_range = risk_range or [0, 1]
    df_f = filter_df(df, cluster or "ALL", float(min_ppn or 0),
                     float(risk_range[0]), float(risk_range[1]), int(min_disp or 0))

    if df_f.empty:
        return html.Div("Tidak ada data setelah filter — coba perlebar range filter.", style={
            "color": CLR["muted"], "padding": "40px", "textAlign": "center"})

    n = int(topn or 20)
    spacer = html.Div(style={"height": "14px"})

    if tab == "tab-ov":
        return html.Div([
            graph(fig_topn_bar(df_f, metric or "ppn", n)),
            spacer,
            row2(graph(fig_dispersi_dist(df_f)),
                 graph(fig_cluster_donut(df_f))),
        ])

    elif tab == "tab-sc":
        return html.Div([
            graph(fig_scatter(df_f)),
            spacer,
            graph(fig_violin(df_f)),
        ])

    elif tab == "tab-risk":
        return html.Div([
            graph(fig_heatmap(df_f)),
            spacer,
            graph(fig_risk_events(df_f)),
        ])

    elif tab == "tab-anom":
        return html.Div([
            graph(fig_risk_bar(df_f, n)),
        ])

    return html.Div("Tab tidak dikenali.")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    print()
    print("=" * 62)
    print("  Dashboard Interaktif PIB x HS Code x KLU")
    print("  SR Importir Umum - CRM Subtim Data Analyst 2026")
    print("=" * 62)
    print("  Preloading data semua periode...")
    for yr in YEARS:
        df_t = load_profil(yr)
        info = f"{len(df_t):,} HS codes" if not df_t.empty else "tidak tersedia"
        print(f"  [{yr}]  {info}")
    print()
    print("  Buka di browser: http://127.0.0.1:8050")
    print("  Tekan Ctrl+C untuk berhenti")
    print()
    app.run(debug=False, host="127.0.0.1", port=8050)
