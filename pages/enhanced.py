"""
pages/enhanced.py
SR15 Enhanced Analytics Dashboard  v1.1.0

Changes from v1.0.0:
  - PPN (Rp Juta) range filter
  - NM_KLU   : multi-select autocomplete Dropdown (replaces text input)
  - NM_KELOMPOK: multi-select autocomplete Dropdown (replaces text input)
  - All filters wire through centralised apply_filters()
"""

from __future__ import annotations

import json

import dash_cytoscape as cyto
import pandas as pd
import plotly.graph_objects as go
from dash import (
    Input, Output, State,
    callback, dcc, html, register_page, no_update,
)
from flask import session

from utils.data import (
    YEARS, apply_filters_cached, agg_by_group_cached, agg_year_summary,
    load_raw, load_multi,
)
from utils.chatbot import (
    RuleBasedChatbot, build_context, call_claude, claude_available,
)

cyto.load_extra_layouts()

# ── Palette ───────────────────────────────────────────────────────────────────

CLR = {
    "bg":      "#2A385E",
    "card":    "#111827",
    "surface": "#1E293B",
    "border":  "#2A3A52",
    "accent":  "#3B82F6",
    "warm":    "#F59E0B",
    "danger":  "#EF4444",
    "success": "#10B981",
    "purple":  "#8B5CF6",
    "text":    "#F1570A",
    "muted":   "#94A3B8",
    "cyan":    "#06B6D4",
}

_AXIS = dict(gridcolor=CLR["border"], zerolinecolor=CLR["border"],
             tickfont=dict(size=10), color=CLR["muted"])
_BASE = dict(
    paper_bgcolor=CLR["bg"], plot_bgcolor=CLR["card"],
    font=dict(family="'Inter','Segoe UI',sans-serif", color=CLR["text"], size=11),
    margin=dict(l=10, r=10, t=44, b=10),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor=CLR["border"],
                borderwidth=1, font=dict(size=10)),
    hoverlabel=dict(bgcolor=CLR["surface"], bordercolor=CLR["border"],
                    font=dict(color=CLR["text"], size=11)),
)


def lo(**kw) -> dict:
    out = dict(**_BASE)
    out["xaxis"] = dict(**_AXIS)
    out["yaxis"] = dict(**_AXIS)
    for k, v in kw.items():
        if k in ("xaxis","yaxis","xaxis2","yaxis2") and isinstance(v, dict):
            out[k] = {**_AXIS, **v}
        else:
            out[k] = v
    return out


def empty_fig(msg="Tidak ada data"):
    fig = go.Figure()
    fig.add_annotation(text=msg, xref="paper", yref="paper", x=0.5, y=0.5,
                       showarrow=False, font=dict(color=CLR["muted"], size=13))
    fig.update_layout(**lo())
    return fig


# ── Style helpers ─────────────────────────────────────────────────────────────

DD_STYLE = {
    "backgroundColor": CLR["surface"], "color": CLR["text"],
    "border": f"1px solid {CLR['border']}", "borderRadius": "6px", "fontSize": "12px",
}
SL_STYLE = {"marginBottom": "10px"}


def lbl(text):
    return html.Div(text, style={
        "color": CLR["muted"], "fontSize": "10px", "fontWeight": "700",
        "letterSpacing": "0.08em", "textTransform": "uppercase",
        "marginTop": "12px", "marginBottom": "4px",
    })


def sec_hdr(text):
    return html.Div(text, style={
        "color": CLR["accent"], "fontSize": "10px", "fontWeight": "700",
        "letterSpacing": "0.12em", "textTransform": "uppercase", "marginBottom": "2px",
    })


def kpi_card(title, value, color, sub=""):
    return html.Div([
        html.Div(title, style={"fontSize":"10px","color":CLR["muted"],
                               "textTransform":"uppercase","letterSpacing":"0.05em"}),
        html.Div(value, style={"fontSize":"20px","fontWeight":"700",
                               "color":color,"lineHeight":"1.3","marginTop":"2px"}),
        html.Div(sub,   style={"fontSize":"10px","color":CLR["muted"],"marginTop":"2px"}),
    ], style={"backgroundColor":CLR["card"],"borderRadius":"8px",
              "padding":"12px 16px","borderTop":f"3px solid {color}",
              "flex":"1","minWidth":"120px"})


def gr(fig, **kw):
    return dcc.Graph(figure=fig,
        config={"displayModeBar":True,"displaylogo":False,
                "modeBarButtonsToRemove":["lasso2d","select2d"]},
        style={"borderRadius":"8px","overflow":"hidden"}, **kw)


def chip(text, color=CLR["accent"]):
    return html.Span(text, style={
        "backgroundColor": color+"22", "color": color,
        "border": f"1px solid {color}44", "borderRadius": "12px",
        "padding": "2px 10px", "fontSize": "11px",
        "marginRight": "6px", "marginBottom": "4px", "display": "inline-block",
    })


CYTO_STYLE = [
    {"selector":"node", "style":{"label":"data(label)","color":CLR["text"],
        "font-size":"9px","text-valign":"center","text-halign":"center",
        "width":"label","height":"label","padding":"6px","shape":"roundrectangle"}},
    {"selector":"node[type='npwp']", "style":{"background-color":CLR["accent"],"color":"#fff"}},
    {"selector":"node[type='hs4']",  "style":{"background-color":CLR["warm"],"color":"#000"}},
    {"selector":"node[type='klu']",  "style":{"background-color":CLR["success"],"color":"#000"}},
    {"selector":"edge", "style":{"curve-style":"bezier","target-arrow-shape":"triangle",
        "line-color":CLR["border"],"target-arrow-color":CLR["border"],"width":1,"opacity":0.7}},
    {"selector":"edge[type='hs4_klu']",
     "style":{"line-color":CLR["purple"],"target-arrow-color":CLR["purple"],"line-style":"dashed"}},
]

_BOT = RuleBasedChatbot()
_UNIQUE_CACHE: dict[tuple[tuple[str, ...], str], list[str]] = {}

# ── Render cache (tab content) ────────────────────────────────────────────────
import threading as _threading
from collections import OrderedDict as _OD

_RENDER_CACHE: "_OD[tuple, object]" = _OD()
_RENDER_CACHE_MAX = 16
_RENDER_LOCK = _threading.Lock()

register_page(__name__, name="SR15 Enhanced", path="/", redirect_from=["/enhanced"], order=1)

# ── Sidebar ───────────────────────────────────────────────────────────────────

_sidebar = html.Div([
    sec_hdr("Periode"),
    lbl("Pilih Tahun (multi)"),
    dcc.Dropdown(id="en-dd-years",
        options=[{"label":y,"value":y} for y in YEARS],
        value=["2023"], multi=True, clearable=False, style=DD_STYLE),

    html.Hr(style={"borderColor":CLR["border"],"margin":"14px 0 6px"}),
    sec_hdr("Filter Nilai"),

    lbl("Range PPH (Rp Juta)"),
    html.Div(dcc.RangeSlider(id="en-sl-pph", min=0, max=5000, step=50, value=[0,5000],
        marks={0:"0",1000:"1M",2500:"2.5M",5000:"5M"},
        updatemode="mouseup",
        tooltip={"placement":"bottom","always_visible":False}), style=SL_STYLE),

    lbl("Range PPN (Rp Juta)"),
    html.Div(dcc.RangeSlider(id="en-sl-ppn", min=0, max=10000, step=100, value=[0,10000],
        marks={0:"0",2500:"2.5M",5000:"5M",10000:"10M"},
        updatemode="mouseup",
        tooltip={"placement":"bottom","always_visible":False}), style=SL_STYLE),

    html.Hr(style={"borderColor":CLR["border"],"margin":"14px 0 6px"}),
    sec_hdr("Filter Teks (Multi-Pilih)"),

    lbl("NM_KLU"),
    dcc.Dropdown(id="en-dd-nm-klu", multi=True, clearable=True,
        placeholder="Ketik untuk mencari...", style=DD_STYLE,
        optionHeight=40),

    lbl("NM_KELOMPOK"),
    dcc.Dropdown(id="en-dd-nm-kelompok", multi=True, clearable=True,
        placeholder="Ketik untuk mencari...", style=DD_STYLE,
        optionHeight=40),

    html.Hr(style={"borderColor":CLR["border"],"margin":"14px 0 6px"}),
    sec_hdr("Filter Multi-Pilih"),

    lbl("KD_KELOMPOK"),
    dcc.Dropdown(id="en-dd-kdkel", multi=True, clearable=True,
        placeholder="Pilih satu atau lebih...", style=DD_STYLE),

    lbl("KD_DETIL"),
    dcc.Dropdown(id="en-dd-kddet", multi=True, clearable=True,
        placeholder="Pilih satu atau lebih...", style=DD_STYLE),

    lbl("NM_SUBGOL"),
    dcc.Dropdown(id="en-dd-subgol", multi=True, clearable=True,
        placeholder="Pilih satu atau lebih...", style=DD_STYLE),

    lbl("KPP (Kode 3 digit)"),
    dcc.Dropdown(id="en-dd-kpp", multi=True, clearable=True,
        placeholder="Pilih KPP...", style=DD_STYLE),

    html.Hr(style={"borderColor":CLR["border"],"margin":"14px 0 6px"}),
    sec_hdr("Tampilan"),

    lbl("Kelompokkan berdasarkan"),
    dcc.Dropdown(id="en-dd-group",
        options=[{"label":"HS-4","value":"HS4"},{"label":"KD_KLU","value":"KD_KLU"},
                 {"label":"KPP Code 3","value":"KPP_CODE_3"},
                 {"label":"KD_KELOMPOK","value":"KD_KELOMPOK"}],
        value="HS4", clearable=False, style=DD_STYLE),

    lbl("Top N"),
    html.Div(dcc.Slider(id="en-sl-topn", min=5, max=50, step=5, value=15,
        marks={5:"5",15:"15",30:"30",50:"50"},
        updatemode="mouseup",
        tooltip={"placement":"bottom","always_visible":False}), style=SL_STYLE),

    html.Br(),
    html.Button("Reset Filter", id="en-btn-reset",
        style={"backgroundColor":CLR["danger"],"color":"#fff","border":"none",
               "borderRadius":"6px","padding":"8px 14px","cursor":"pointer",
               "width":"100%","fontSize":"12px","fontWeight":"600"}),

    html.Hr(style={"borderColor":CLR["border"],"margin":"14px 0 6px"}),
    html.Div(id="en-filter-chips",
             style={"lineHeight":"1.8","minHeight":"24px"}),
    html.Div(id="en-sb-stats",
             style={"fontSize":"11px","color":CLR["muted"],"lineHeight":"2.0","marginTop":"6px"}),

], style={
    "width":"268px","minWidth":"268px","padding":"16px 14px",
    "borderRight":f"1px solid {CLR['border']}","backgroundColor":CLR["card"],
    "height":"calc(100vh - 52px)","overflowY":"auto",
    "position":"sticky","top":"52px","boxSizing":"border-box",
})

_ts  = {"color":CLR["muted"],"padding":"8px 18px","backgroundColor":CLR["card"],
        "borderBottom":"none","fontSize":"13px"}
_tss = {"color":CLR["text"],"padding":"8px 18px","backgroundColor":CLR["bg"],
        "borderTop":f"2px solid {CLR['accent']}","borderBottom":"none",
        "fontSize":"13px","fontWeight":"600"}


def layout():
    if not session.get("authenticated"):
        return dcc.Location(id="en-redir", href="/login", refresh=True)

    return html.Div([
        dcc.Store(id="en-store-state"),

        html.Div([
            _sidebar,
            html.Div([
                dcc.Loading(
                    html.Div(id="en-kpi-row", style={
                        "display":"flex","gap":"10px","flexWrap":"wrap",
                        "padding":"14px 18px","borderBottom":f"1px solid {CLR['border']}"}),
                    type="circle", color=CLR["accent"],
                    style={"minHeight":"72px"},
                ),
                dcc.Tabs(id="en-tabs", value="tab-en-overview",
                    style={"backgroundColor":CLR["card"],"borderBottom":f"1px solid {CLR['border']}"},
                    colors={"border":CLR["border"],"primary":CLR["accent"],"background":CLR["card"]},
                    children=[
                        dcc.Tab(label="Overview & Group",    value="tab-en-overview",  style=_ts, selected_style=_tss),
                        dcc.Tab(label="Perbandingan Tahun",  value="tab-en-compare",   style=_ts, selected_style=_tss),
                        dcc.Tab(label="Relasi NPWP-HS-KLU",  value="tab-en-graph",     style=_ts, selected_style=_tss),
                        dcc.Tab(label="Chatbot (Rule-Based)", value="tab-en-chat",     style=_ts, selected_style=_tss),
                    ]),
                dcc.Loading(
                    html.Div(id="en-tab-content",
                             style={"padding":"16px 18px","overflowX":"hidden"}),
                    type="dot", color=CLR["accent"],
                    style={"minHeight":"200px"},
                ),
            ], style={"flex":"1","overflowY":"auto",
                      "height":"calc(100vh - 52px)","minWidth":"0"}),
        ], style={"display":"flex"}),
    ], style={"backgroundColor":CLR["bg"],"minHeight":"100vh",
              "fontFamily":"'Inter','Segoe UI',sans-serif","color":CLR["text"]})


# ── Populate multi-select dropdowns from loaded years ─────────────────────────

def _get_unique_values(years, col) -> list[str]:
    key = (tuple(years or YEARS), col)
    if key in _UNIQUE_CACHE:
        return _UNIQUE_CACHE[key]
    df = load_multi(list(key[0]))
    if df.empty or col not in df.columns:
        vals: list[str] = []
    else:
        vals = sorted(df[col].dropna().astype(str).str.strip().unique().tolist())
    _UNIQUE_CACHE[key] = vals
    return vals


def _unique_opts_vals(vals, max_n=300):
    if not vals:
        return []
    return [{"label": v, "value": v} for v in vals[:max_n]]


@callback(
    Output("en-dd-kdkel",  "options"),
    Output("en-dd-kddet",  "options"),
    Output("en-dd-subgol", "options"),
    Output("en-dd-kpp",    "options"),
    Input("en-dd-years",   "value"),
)
def _populate_discrete_filters(years):
    years = years or YEARS
    kpp_vals = [v for v in _get_unique_values(years, "KPP_CODE_3") if v != "N/A"]
    return (
        _unique_opts_vals(_get_unique_values(years, "KD_KELOMPOK")),
        _unique_opts_vals(_get_unique_values(years, "KD_DETIL")),
        _unique_opts_vals(_get_unique_values(years, "NM_SUBGOL")),
        _unique_opts_vals(kpp_vals),
    )


# ── NM_KLU autocomplete (server-side partial match) ──────────────────────────

@callback(
    Output("en-dd-nm-klu", "options"),
    Input("en-dd-nm-klu",  "search_value"),
    Input("en-dd-years",   "value"),
)
def _nm_klu_opts(search_val, years):
    if not search_val or len(search_val) < 2:
        return []
    years = years or YEARS
    all_vals = _get_unique_values(years, "NM_KLU")
    if not all_vals:
        return []
    sv = search_val.lower()
    filtered = [v for v in all_vals if sv in v.lower()]
    return [{"label": v, "value": v} for v in filtered[:200]]


# ── NM_KELOMPOK autocomplete ──────────────────────────────────────────────────

@callback(
    Output("en-dd-nm-kelompok", "options"),
    Input("en-dd-nm-kelompok",  "search_value"),
    Input("en-dd-years",        "value"),
)
def _nm_kelompok_opts(search_val, years):
    if not search_val or len(search_val) < 2:
        return []
    years = years or YEARS
    all_vals = _get_unique_values(years, "NM_KELOMPOK")
    if not all_vals:
        return []
    sv = search_val.lower()
    filtered = [v for v in all_vals if sv in v.lower()]
    return [{"label": v, "value": v} for v in filtered[:200]]


# ── Reset ─────────────────────────────────────────────────────────────────────

@callback(
    Output("en-sl-pph",         "value"),
    Output("en-sl-ppn",         "value"),
    Output("en-dd-nm-klu",      "value"),
    Output("en-dd-nm-kelompok", "value"),
    Output("en-dd-kdkel",       "value"),
    Output("en-dd-kddet",       "value"),
    Output("en-dd-subgol",      "value"),
    Output("en-dd-kpp",         "value"),
    Input("en-btn-reset", "n_clicks"),
    prevent_initial_call=True,
)
def _reset(_):
    return [0, 5000], [0, 10000], [], [], [], [], [], []


# ── Store + KPIs + chips + stats ──────────────────────────────────────────────

def _build_state(years, pph_range, ppn_range, nm_klu, nm_kelompok,
                 kd_kel, kd_det, nm_sub, kpp) -> dict:
    return {
        "years":       years or YEARS,
        "pph_range":   [(pph_range[0] or 0)*1e6, (pph_range[1] or 5000)*1e6]
                       if pph_range else [0, 5e9],
        "ppn_range":   [(ppn_range[0] or 0)*1e6, (ppn_range[1] or 10000)*1e6]
                       if ppn_range else [0, 1e10],
        "nm_klu":      nm_klu      or [],
        "nm_kelompok": nm_kelompok or [],
        "kd_kelompok": kd_kel  or [],
        "kd_detil":    kd_det  or [],
        "nm_subgol":   nm_sub  or [],
        "kpp":         kpp     or [],
    }


@callback(
    Output("en-store-state",  "data"),
    Output("en-kpi-row",      "children"),
    Output("en-filter-chips", "children"),
    Output("en-sb-stats",     "children"),
    Input("en-dd-years",        "value"),
    Input("en-sl-pph",          "value"),
    Input("en-sl-ppn",          "value"),
    Input("en-dd-nm-klu",       "value"),
    Input("en-dd-nm-kelompok",  "value"),
    Input("en-dd-kdkel",        "value"),
    Input("en-dd-kddet",        "value"),
    Input("en-dd-subgol",       "value"),
    Input("en-dd-kpp",          "value"),
)
def _update_store(years, pph_range, ppn_range, nm_klu, nm_kelompok,
                  kd_kel, kd_det, nm_sub, kpp):
    state  = _build_state(years, pph_range, ppn_range,
                          nm_klu, nm_kelompok, kd_kel, kd_det, nm_sub, kpp)
    df_raw = load_multi(state["years"])
    df_f   = apply_filters_cached(df_raw, state)

    # Invalidate render cache for old states (keep cache small, ~4 recent states)
    state_json_new = json.dumps(state)
    with _RENDER_LOCK:
        stale = [k for k in _RENDER_CACHE if k[0] != state_json_new]
        if len(stale) > 8:
            for k in stale[:-4]:
                _RENDER_CACHE.pop(k, None)

    n_rows = len(df_f)
    npwp_is_count = df_f["_npwp_is_count"].any() if not df_f.empty else False
    n_npwp = int(df_f["NPWP"].sum() if npwp_is_count else df_f["NPWP"].nunique()) \
             if not df_f.empty else 0
    ppn    = df_f["PPN_DIBAYAR"].sum() if not df_f.empty else 0
    pph    = df_f["PPH_DIBAYAR"].sum() if not df_f.empty else 0
    n_hs4  = df_f["HS4"].nunique() if not df_f.empty else 0

    def _fmt(v):
        return f"Rp {v/1e12:.2f} T" if abs(v) >= 1e12 else f"Rp {v/1e9:.1f} M"

    kpi_lbl = "Total NPWP (hitungan)" if npwp_is_count else "NPWP Unik"
    cards = [
        kpi_card("Baris Data",  f"{n_rows:,}", CLR["accent"]),
        kpi_card(kpi_lbl,       f"{n_npwp:,}", CLR["purple"]),
        kpi_card("HS-4 Unik",   f"{n_hs4:,}",  CLR["cyan"]),
        kpi_card("Total PPN",   _fmt(ppn),      CLR["success"]),
        kpi_card("Total PPH",   _fmt(pph),      CLR["warm"]),
    ]

    # Filter chips
    chips: list = []
    if nm_klu:
        chips.append(chip(f"KLU: {len(nm_klu)}", CLR["accent"]))
    if nm_kelompok:
        chips.append(chip(f"KEL: {len(nm_kelompok)}", CLR["cyan"]))
    if kd_kel:
        chips.append(chip(f"KD_KEL: {len(kd_kel)}", CLR["warm"]))
    if kd_det:
        chips.append(chip(f"KD_DET: {len(kd_det)}", CLR["success"]))
    if nm_sub:
        chips.append(chip(f"SUBGOL: {len(nm_sub)}", CLR["purple"]))
    if kpp:
        chips.append(chip(f"KPP: {len(kpp)}", CLR["danger"]))
    if ppn_range and (ppn_range[0] > 0 or ppn_range[1] < 10000):
        chips.append(chip(f"PPN: {ppn_range[0]}-{ppn_range[1]} Jt", CLR["success"]))
    if pph_range and (pph_range[0] > 0 or pph_range[1] < 5000):
        chips.append(chip(f"PPH: {pph_range[0]}-{pph_range[1]} Jt", CLR["warm"]))
    if not chips:
        chips = [html.Span("Semua filter aktif",
                           style={"color":CLR["muted"],"fontSize":"11px"})]

    stats = html.Div([
        html.B(f"Periode: {', '.join(state['years'])}"), html.Br(),
        f"Baris: {n_rows:,}", html.Br(),
        f"{kpi_lbl}: {n_npwp:,}", html.Br(),
        f"PPN: {_fmt(ppn)}", html.Br(),
        f"PPH: {_fmt(pph)}",
    ])

    return json.dumps(state), cards, chips, stats


# ── Tab content ───────────────────────────────────────────────────────────────

@callback(
    Output("en-tab-content", "children"),
    Input("en-tabs",         "value"),
    Input("en-store-state",  "data"),
    Input("en-dd-group",     "value"),
    Input("en-sl-topn",      "value"),
    prevent_initial_call=True,
)
def _render_tab(tab, state_json, group_col, topn):
    try:
        if not state_json:
            return html.Div("Memuat data...", style={"color":CLR["muted"],"padding":"40px"})

        topn = int(topn or 15)

        # ── Render cache: skip all computation for repeated requests ──────────
        _rkey = (state_json, tab, group_col, topn)
        with _RENDER_LOCK:
            if _rkey in _RENDER_CACHE:
                _RENDER_CACHE.move_to_end(_rkey)
                return _RENDER_CACHE[_rkey]

        state  = json.loads(state_json)
        df_raw = load_multi(state["years"])
        df_f   = apply_filters_cached(df_raw, state)

        if df_f.empty:
            result = html.Div("Tidak ada data setelah filter.",
                              style={"color":CLR["muted"],"padding":"40px","textAlign":"center"})
        elif tab == "tab-en-overview":
            result = _tab_overview(df_f, group_col, topn)
        elif tab == "tab-en-compare":
            result = _tab_compare(df_f)
        elif tab == "tab-en-graph":
            result = _tab_graph(df_f, topn)
        elif tab == "tab-en-chat":
            result = _tab_chat(df_f)
        else:
            result = html.Div("Tab tidak dikenali.")

        with _RENDER_LOCK:
            _RENDER_CACHE[_rkey] = result
            if len(_RENDER_CACHE) > _RENDER_CACHE_MAX:
                _RENDER_CACHE.popitem(last=False)
        return result

    except Exception:
        import traceback
        return html.Div([
            html.B("Error rendering tab:", style={"color":CLR["danger"]}),
            html.Pre(traceback.format_exc(),
                     style={"color":CLR["muted"],"fontSize":"11px","whiteSpace":"pre-wrap",
                            "background":CLR["surface"],"padding":"12px","borderRadius":"6px",
                            "maxHeight":"400px","overflow":"auto"}),
        ], style={"padding":"20px"})


# ── Tab: Overview & Grouping ──────────────────────────────────────────────────

def _tab_overview(df, group_col, topn):
    sp = html.Div(style={"height":"14px"})
    gc = group_col if group_col in df.columns else "HS4"
    agg = agg_by_group_cached(df, gc, topn)

    # ── Build hover name lookup for the group column ──────────────────────────
    _NM_MAP = {          # group_col → which name column to look up
        "HS4":       "NM_KELOMPOK",
        "KD_DETIL":  "NM_DETIL",
        "KD_KLU":    "NM_KLU",
        "KD_KELOMPOK": "NM_KELOMPOK",
    }
    hover_names = None
    if not agg.empty:
        if gc in ("NM_KLU","NM_KELOMPOK","NM_SUBGOL","NM_DETIL"):
            hover_names = agg[gc].astype(str)          # name IS the axis label
        elif gc in _NM_MAP and _NM_MAP[gc] in df.columns:
            nm_col = _NM_MAP[gc]
            # Use first() instead of mode() — 10x faster, good enough for labels
            nm_map = df.groupby(gc, observed=True)[nm_col].first()
            hover_names = agg[gc].map(nm_map).fillna("").astype(str)

    # ── Bar chart ─────────────────────────────────────────────────────────────
    fig_bar = empty_fig()
    if not agg.empty:
        hover_tmpl = (
            f"%{{y}}<br><i>%{{customdata}}</i><br>PPN: Rp %{{x:.2f}} M"
            f"<br>PPH: Rp %{{customdata2:.2f}} M<extra></extra>"
            if hover_names is not None
            else f"%{{y}}<br>PPN: Rp %{{x:.2f}} M<extra></extra>"
        )
        bar_kw = dict(
            x=agg["PPN_DIBAYAR"]/1e9,
            y=agg[gc].astype(str),
            orientation="h",
            marker_color=CLR["accent"],
            text=(agg["PPN_DIBAYAR"]/1e9).apply(lambda v: f"{v:.1f}"),
            textposition="outside",
            hovertemplate=hover_tmpl,
        )
        if hover_names is not None:
            bar_kw["customdata"] = list(zip(
                hover_names.str[:60].tolist(),
                (agg["PPH_DIBAYAR"]/1e9).tolist(),
            ))
            bar_kw["hovertemplate"] = (
                f"%{{y}}<br><i>%{{customdata[0]}}</i>"
                f"<br>PPN: Rp %{{x:.2f}} M"
                f"<br>PPH: Rp %{{customdata[1]:.2f}} M<extra></extra>"
            )
        fig_bar = go.Figure(go.Bar(**bar_kw))
        fig_bar.update_layout(**lo(
            title=f"<b>Top {topn} {gc} berdasarkan PPN</b>",
            xaxis=dict(title="PPN (Rp Miliar)"),
            yaxis=dict(tickfont=dict(size=9)),
            height=max(350, topn*28),
        ))

    # ── Donut PPN + Donut PPH ─────────────────────────────────────────────────
    DONUT_COLS = [CLR["accent"],CLR["warm"],CLR["success"],CLR["purple"],
                  CLR["danger"],CLR["cyan"],"#F97316","#94A3B8"]
    fig_donut_ppn = empty_fig("Tidak ada data NM_SUBGOL")
    fig_donut_pph = empty_fig("Tidak ada data NM_SUBGOL")
    if "NM_SUBGOL" in df.columns:
        # Single groupby for both PPN and PPH → half the computation
        sub_both = (df.groupby("NM_SUBGOL", observed=True)[["PPN_DIBAYAR","PPH_DIBAYAR"]]
                      .sum().reset_index())
        sub_ppn = sub_both.nlargest(8, "PPN_DIBAYAR")
        sub_pph = sub_both.nlargest(8, "PPH_DIBAYAR")
        if not sub_ppn.empty:
            fig_donut_ppn = go.Figure(go.Pie(
                labels=sub_ppn["NM_SUBGOL"].str[:35],
                values=sub_ppn["PPN_DIBAYAR"]/1e9,
                hole=0.5, marker_colors=DONUT_COLS[:len(sub_ppn)],
                hovertemplate="%{label}<br>PPN: Rp %{value:.2f} M<extra></extra>",
                textinfo="percent",
            ))
            fig_donut_ppn.update_layout(**lo(
                title="<b>Komposisi PPN per Subgolongan</b>", height=350,
            ))
        if not sub_pph.empty:
            fig_donut_pph = go.Figure(go.Pie(
                labels=sub_pph["NM_SUBGOL"].str[:35],
                values=sub_pph["PPH_DIBAYAR"]/1e9,
                hole=0.5, marker_colors=DONUT_COLS[:len(sub_pph)],
                hovertemplate="%{label}<br>PPH: Rp %{value:.2f} M<extra></extra>",
                textinfo="percent",
            ))
            fig_donut_pph.update_layout(**lo(
                title="<b>Komposisi PPH per Subgolongan</b>", height=350,
            ))

    # ── Scatter PPN vs PPH ────────────────────────────────────────────────────
    fig_scat = empty_fig()
    if not agg.empty and "PPH_DIBAYAR" in agg.columns:
        scat_labels = agg[gc].astype(str).str[:10]
        scat_names  = hover_names.str[:40] if hover_names is not None else scat_labels
        fig_scat = go.Figure(go.Scatter(
            x=agg["PPN_DIBAYAR"]/1e9, y=agg["PPH_DIBAYAR"]/1e9,
            mode="markers+text",
            text=scat_labels,
            customdata=list(zip(
                scat_names.tolist(),
                (agg["PPN_DIBAYAR"]/1e9).tolist(),
                (agg["PPH_DIBAYAR"]/1e9).tolist(),
            )),
            textposition="top center", textfont=dict(size=8),
            marker=dict(size=12, color=agg["PPN_DIBAYAR"],
                colorscale=[[0,CLR["surface"]],[0.5,CLR["accent"]],[1,CLR["danger"]]],
                showscale=True,
                colorbar=dict(title=dict(text="PPN",font=dict(color=CLR["text"])),
                              tickfont=dict(color=CLR["text"]))),
            hovertemplate=(
                "<b>%{text}</b><br><i>%{customdata[0]}</i>"
                "<br>PPN: Rp %{customdata[1]:.2f} M"
                "<br>PPH: Rp %{customdata[2]:.2f} M<extra></extra>"
            ),
        ))
        fig_scat.update_layout(**lo(
            title=f"<b>PPN vs PPH per {gc}</b>",
            xaxis=dict(title="PPN (Rp Miliar)"),
            yaxis=dict(title="PPH (Rp Miliar)"),
            height=380,
        ))

    return html.Div([
        gr(fig_bar), sp,
        html.Div([
            html.Div(gr(fig_donut_ppn), style={"flex":"1","minWidth":"0"}),
            html.Div(gr(fig_donut_pph), style={"flex":"1","minWidth":"0"}),
            html.Div(gr(fig_scat),      style={"flex":"1","minWidth":"0"}),
        ], style={"display":"flex","gap":"14px"}),
    ])


# ── Tab: Multi-year Comparison ────────────────────────────────────────────────

def _tab_compare(df):
    sp   = html.Div(style={"height":"14px"})
    summ = agg_year_summary(df)
    if summ.empty:
        return html.Div("Tidak ada data multi-tahun.",
                        style={"color":CLR["muted"],"padding":"40px"})

    note = None
    if len(summ) < 2:
        note = html.Div(
            "Pilih minimal 2 tahun di sidebar untuk melihat grafik tren.",
            style={"color":CLR["warm"],"fontSize":"12px","padding":"8px 12px",
                   "backgroundColor":CLR["surface"],"borderRadius":"6px",
                   "border":f"1px solid {CLR['warm']}44","marginBottom":"12px"})

    # Chart 1: PPN + PPH trend (plain Figure, no secondary_y)
    fig_trend = go.Figure()
    fig_trend.add_trace(go.Scatter(
        x=summ["Tahun"], y=summ["PPN (Rp M)"], mode="lines+markers+text",
        name="PPN (Rp Juta)", line=dict(color=CLR["success"],width=2),
        marker=dict(size=9, color=CLR["success"]),
        text=summ["PPN (Rp M)"].apply(lambda v: f"{v:,.0f}"),
        textposition="top center", textfont=dict(size=9, color=CLR["success"]),
        hovertemplate="%{x}<br>PPN: Rp %{y:,.2f} Juta<extra></extra>",
    ))
    fig_trend.add_trace(go.Scatter(
        x=summ["Tahun"], y=summ["PPH (Rp M)"], mode="lines+markers+text",
        name="PPH (Rp Juta)", line=dict(color=CLR["warm"],width=2),
        marker=dict(size=9, color=CLR["warm"]),
        text=summ["PPH (Rp M)"].apply(lambda v: f"{v:,.0f}"),
        textposition="bottom center", textfont=dict(size=9, color=CLR["warm"]),
        hovertemplate="%{x}<br>PPH: Rp %{y:,.2f} Juta<extra></extra>",
    ))
    fig_trend.update_layout(**lo(
        title="<b>Tren PPN dan PPH per Periode</b>",
        yaxis=dict(title="Nilai (Rp Juta)"),
        height=320,
    ))

    # Chart 2: PIB bar
    fig_pib = go.Figure(go.Bar(
        x=summ["Tahun"], y=summ["PIB"],
        marker_color=[CLR["accent"],CLR["success"],CLR["warm"],CLR["purple"]][:len(summ)],
        text=summ["PIB"].apply(lambda v: f"{v:,}"), textposition="outside",
        textfont=dict(size=9),
        hovertemplate="%{x}<br>PIB: %{y:,}<extra></extra>",
    ))
    fig_pib.update_layout(**lo(
        title="<b>Jumlah PIB per Periode</b>",
        yaxis=dict(title="Jumlah Dokumen PIB"),
        height=280,
    ))

    # Chart 3: NPWP bar
    fig_npwp = go.Figure(go.Bar(
        x=summ["Tahun"], y=summ["NPWP"],
        marker_color=[CLR["purple"],CLR["cyan"],CLR["accent"],CLR["success"]][:len(summ)],
        text=summ["NPWP"].apply(lambda v: f"{v:,}"), textposition="outside",
        textfont=dict(size=9),
        hovertemplate="%{x}<br>NPWP: %{y:,}<extra></extra>",
    ))
    fig_npwp.update_layout(**lo(
        title="<b>Jumlah NPWP per Periode</b>",
        yaxis=dict(title="NPWP"),
        height=280,
    ))

    # Table
    tbl_header = dict(
        values=["<b>"+c+"</b>" for c in summ.columns],
        fill_color=CLR["surface"], font=dict(color=CLR["text"],size=11),
        align="center", line_color=CLR["border"])
    tbl_cells = dict(
        values=[
            summ["Tahun"],
            summ["NPWP"].apply(lambda v: f"{v:,}"),
            summ["PIB"].apply(lambda v: f"{v:,}"),
            summ["PPN (Rp M)"].apply(lambda v: f"{v:,.1f}"),
            summ["PPH (Rp M)"].apply(lambda v: f"{v:,.1f}"),
        ],
        fill_color=CLR["card"], font=dict(color=CLR["muted"],size=11),
        align="center", line_color=CLR["border"])
    fig_tbl = go.Figure(go.Table(header=tbl_header, cells=tbl_cells))
    fig_tbl.update_layout(**lo(
        title="<b>Tabel Perbandingan Per Periode</b>",
        height=200, margin=dict(l=10,r=10,t=44,b=10)))

    children = []
    if note:
        children.append(note)
    children += [
        gr(fig_trend), sp,
        html.Div([
            html.Div(gr(fig_pib),  style={"flex":"1","minWidth":"0"}),
            html.Div(gr(fig_npwp), style={"flex":"1","minWidth":"0"}),
        ], style={"display":"flex","gap":"14px"}), sp,
        gr(fig_tbl),
    ]
    return html.Div(children)


# ── Tab: Graph (Cytoscape) ────────────────────────────────────────────────────

def _tab_graph(df, topn):
    controls = html.Div([
        html.Div([
            html.Span("Seed NPWP:", style={"color":CLR["muted"],"fontSize":"11px","marginRight":"6px"}),
            dcc.Dropdown(id="en-graph-seed", options=[], value=None, clearable=True,
                         style={**DD_STYLE,"width":"220px"}),
        ], style={"display":"flex","alignItems":"center","gap":"8px","flexWrap":"wrap"}),
        html.Div([
            html.Span("Depth:", style={"color":CLR["muted"],"fontSize":"11px","marginRight":"6px"}),
            dcc.Dropdown(id="en-graph-depth",
                options=[{"label":"1","value":1},{"label":"2","value":2}],
                value=1, clearable=False, style={**DD_STYLE,"width":"80px"}),
            html.Span("Top N:", style={"color":CLR["muted"],"fontSize":"11px",
                                       "marginLeft":"12px","marginRight":"6px"}),
            dcc.Dropdown(id="en-graph-topn",
                options=[{"label":str(n),"value":n} for n in [20,50,100,200]],
                value=50, clearable=False, style={**DD_STYLE,"width":"80px"}),
            dcc.Checklist(id="en-graph-hs4klu",
                options=[{"label":" Tampilkan edge HS4-KLU","value":"show"}],
                value=[],
                style={"color":CLR["muted"],"fontSize":"11px","marginLeft":"16px",
                       "display":"inline-flex","alignItems":"center"}),
        ], style={"display":"flex","alignItems":"center","gap":"4px",
                  "flexWrap":"wrap","marginTop":"8px"}),
    ], style={"backgroundColor":CLR["card"],"padding":"10px 14px","borderRadius":"8px",
              "marginBottom":"10px","border":f"1px solid {CLR['border']}"})

    return html.Div([
        controls,
        cyto.Cytoscape(id="en-cyto",
            layout={"name":"cose","animate":True},
            style={"width":"100%","height":"520px","backgroundColor":CLR["bg"],
                   "borderRadius":"8px","border":f"1px solid {CLR['border']}"},
            elements=[], stylesheet=CYTO_STYLE, responsive=True),
        html.Div(id="en-cyto-info",
            style={"backgroundColor":CLR["card"],"padding":"10px 14px",
                   "borderRadius":"8px","marginTop":"10px","fontSize":"11px",
                   "color":CLR["muted"],"border":f"1px solid {CLR['border']}",
                   "minHeight":"40px"}),
    ])


@callback(
    Output("en-graph-seed", "options"),
    Input("en-store-state", "data"),
    prevent_initial_call=True,
)
def _seed_opts(state_json):
    if not state_json:
        return []
    state  = json.loads(state_json)
    df_raw = load_multi(state["years"])
    df_f   = apply_filters_cached(df_raw, state)
    if df_f.empty or df_f["_npwp_is_count"].any():
        return []
    top = df_f.groupby("NPWP")["PPN_DIBAYAR"].sum().nlargest(50)
    return [{"label":f"{k} (PPN {v/1e9:.1f}M)","value":k} for k,v in top.items()]


@callback(
    Output("en-cyto", "elements"),
    Input("en-store-state",  "data"),
    Input("en-graph-seed",   "value"),
    Input("en-graph-depth",  "value"),
    Input("en-graph-topn",   "value"),
    Input("en-graph-hs4klu", "value"),
    prevent_initial_call=True,
)
def _build_graph(state_json, seed, depth, g_topn, show_hs4klu):
    if not state_json:
        return []
    state  = json.loads(state_json)
    df_raw = load_multi(state["years"])
    df_f   = apply_filters_cached(df_raw, state)
    if df_f.empty:
        return []

    npwp_is_count = df_f["_npwp_is_count"].any()
    g_topn        = int(g_topn or 50)
    show_links    = show_hs4klu and "show" in (show_hs4klu or [])

    if seed and not npwp_is_count:
        sub = df_f[df_f["NPWP"] == seed]
    elif not npwp_is_count:
        top_npwp = df_f.groupby("NPWP")["PPN_DIBAYAR"].sum().nlargest(g_topn).index
        sub = df_f[df_f["NPWP"].isin(top_npwp)]
    else:
        top_hs4 = df_f.groupby("HS4")["PPN_DIBAYAR"].sum().nlargest(g_topn).index
        sub = df_f[df_f["HS4"].isin(top_hs4)]

    nodes: dict = {}
    edges: list = []
    seen:  set  = set()

    def add_n(nid, label, ntype):
        if nid not in nodes:
            nodes[nid] = {"data": {"id": nid, "label": label, "type": ntype}}

    def add_e(src, tgt, etype="default"):
        k = (src, tgt)
        if k not in seen:
            seen.add(k)
            edges.append({"data": {"source": src, "target": tgt, "type": etype}})

    if not npwp_is_count:
        # Deduplicate before iterating — reduces rows from 10K-50K to ~500-2000
        cols = ["NPWP", "HS4", "KD_KLU"]
        combos = sub[cols].drop_duplicates()
        for row in combos.itertuples(index=False):
            ni = f"npwp_{row.NPWP}"
            hi = f"hs4_{row.HS4}"
            ki = f"klu_{row.KD_KLU}"
            add_n(ni, str(row.NPWP)[-6:], "npwp")
            add_n(hi, f"HS {row.HS4}", "hs4")
            add_n(ki, str(row.KD_KLU)[:8], "klu")
            add_e(ni, hi, "npwp_hs4")
            if depth == 2:
                add_e(ni, ki, "npwp_klu")
            if show_links:
                add_e(hi, ki, "hs4_klu")
    else:
        combos = sub[["HS4", "KD_KLU"]].drop_duplicates()
        for row in combos.itertuples(index=False):
            hi = f"hs4_{row.HS4}"
            ki = f"klu_{row.KD_KLU}"
            add_n(hi, f"HS {row.HS4}", "hs4")
            add_n(ki, str(row.KD_KLU)[:8], "klu")
            if show_links:
                add_e(hi, ki, "hs4_klu")

    return list(nodes.values()) + edges


@callback(
    Output("en-cyto-info", "children"),
    Input("en-cyto", "tapNodeData"),
)
def _node_info(data):
    if not data:
        return "Klik node untuk melihat detail."
    return html.Span([
        html.B(f"{data.get('type','').upper()}: "),
        data.get("label",""),
        html.Span(f"  (id: {data.get('id','')})",
                  style={"color":CLR["border"]}),
    ])


# ── Tab: Asisten & Chatbot ────────────────────────────────────────────────────

def _tab_chat(df):
    api_ok  = claude_available()
    mode_badge = html.Span(
        "Claude AI" if api_ok else "Rule-Based",
        style={
            "backgroundColor": (CLR["success"] if api_ok else CLR["warm"]) + "22",
            "color":           CLR["success"] if api_ok else CLR["warm"],
            "border":          f"1px solid {(CLR['success'] if api_ok else CLR['warm'])}44",
            "borderRadius":    "10px",
            "padding":         "2px 10px",
            "fontSize":        "10px",
            "marginLeft":      "8px",
        },
    )
    placeholder = (
        "Tanya apa saja tentang data impor..."
        if api_ok else
        "Ketik perintah atau pertanyaan (coba: help, top hs4, mismatch)..."
    )
    hint = (
        "Didukung Claude AI — tanya bebas dalam bahasa natural."
        if api_ok else
        "Mode rule-based aktif. Set ANTHROPIC_API_KEY untuk Claude AI. Ketik 'help' untuk panduan."
    )
    return html.Div([
        html.Div([
            html.Div([
                html.Span("Asisten SR15", style={
                    "fontSize":"13px","fontWeight":"700","color":CLR["accent"]}),
                mode_badge,
            ], style={"display":"flex","alignItems":"center","marginBottom":"4px"}),
            html.Div(hint, style={"fontSize":"11px","color":CLR["muted"],"marginBottom":"10px"}),
            html.Div(id="en-chat-messages", style={
                "backgroundColor":CLR["bg"],"borderRadius":"8px","padding":"12px",
                "minHeight":"300px","maxHeight":"420px","overflowY":"auto",
                "border":f"1px solid {CLR['border']}","fontSize":"12px","lineHeight":"1.8",
            }, children=[html.Div(
                "Selamat datang! Ketik pertanyaan atau perintah di bawah.",
                style={"color":CLR["muted"]},
            )]),
            html.Div([
                dcc.Input(id="en-chat-input", type="text",
                    placeholder=placeholder, debounce=False, n_submit=0,
                    style={"backgroundColor":CLR["surface"],"color":CLR["text"],
                           "border":f"1px solid {CLR['border']}","borderRadius":"6px",
                           "padding":"8px 12px","fontSize":"12px","flex":"1","outline":"none"}),
                html.Button("Kirim", id="en-chat-send",
                    style={"backgroundColor":CLR["accent"],"color":"#fff","border":"none",
                           "borderRadius":"6px","padding":"8px 16px","cursor":"pointer",
                           "marginLeft":"8px","fontSize":"12px","fontWeight":"600"}),
                html.Button("Reset", id="en-chat-clear",
                    style={"backgroundColor":CLR["surface"],"color":CLR["muted"],
                           "border":f"1px solid {CLR['border']}","borderRadius":"6px",
                           "padding":"8px 12px","cursor":"pointer",
                           "marginLeft":"6px","fontSize":"12px"}),
            ], style={"display":"flex","marginTop":"10px","alignItems":"center"}),
        ], style={"backgroundColor":CLR["card"],"borderRadius":"10px",
                  "padding":"16px","maxWidth":"860px"}),
        dcc.Store(id="en-chat-store", data=[]),
    ])


@callback(
    Output("en-chat-messages", "children"),
    Output("en-chat-store",    "data"),
    Output("en-chat-input",    "value"),
    Input("en-chat-send",  "n_clicks"),
    Input("en-chat-input", "n_submit"),
    State("en-chat-input", "value"),
    State("en-chat-store", "data"),
    State("en-store-state","data"),
    prevent_initial_call=True,
)
def _chat_respond(n_clicks, n_submit, user_msg, history, state_json):
    if not user_msg or not user_msg.strip():
        return no_update, no_update, no_update
    history  = history or []
    user_msg = user_msg.strip()

    if state_json:
        state  = json.loads(state_json)
        df_raw = load_multi(state["years"])
        df_ctx = apply_filters_cached(df_raw, state)
    else:
        df_ctx = pd.DataFrame()

    # Build Claude-format history
    api_msgs = [
        {"role": m["role"] if m["role"] in ("user","assistant") else "user",
         "content": m.get("content", m.get("text",""))}
        for m in history
    ]
    api_msgs.append({"role": "user", "content": user_msg})

    # Try Claude first, fallback to rule-based
    ctx   = build_context(df_ctx)
    reply = call_claude(api_msgs, ctx)
    if reply is None:
        reply = _BOT.respond(user_msg, df_ctx)

    history.append({"role": "user",      "content": user_msg})
    history.append({"role": "assistant", "content": reply})

    bubbles = []
    for msg in history:
        is_u = msg["role"] == "user"
        bubbles.append(html.Div([
            html.Span("Anda: " if is_u else "Asisten: ",
                      style={"fontWeight":"700",
                             "color":CLR["accent"] if is_u else CLR["success"]}),
            html.Span(msg.get("content", msg.get("text",""))),
        ], style={"backgroundColor":CLR["surface"] if is_u else CLR["card"],
                  "padding":"8px 12px","borderRadius":"6px","marginBottom":"6px",
                  "borderLeft":f"3px solid {CLR['accent'] if is_u else CLR['success']}",
                  "whiteSpace":"pre-wrap","wordBreak":"break-word"}))
    return bubbles, history, ""


@callback(
    Output("en-chat-messages", "children", allow_duplicate=True),
    Output("en-chat-store",    "data",     allow_duplicate=True),
    Input("en-chat-clear", "n_clicks"),
    prevent_initial_call=True,
)
def _chat_clear(_):
    return [html.Div("Percakapan direset.", style={"color":CLR["muted"]})], []
