"""
pages/hasil_analisa.py
Halaman Hasil Analisa — menampilkan 5 file output hasil analisa per tahun.

Path: /hasil-analisa
"""

from __future__ import annotations

import os
import traceback
from functools import lru_cache
from typing import Any

import pandas as pd
from dash import (
    Input, Output, callback, dash_table, dcc, html, register_page
)

register_page(__name__, name="Hasil Analisa", path="/hasil-analisa", order=2)

# ── Paths ─────────────────────────────────────────────────────────────────────

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUTPUT_DIR = os.path.join(_BASE, "output")

YEARS = ["2023", "2022", "2024", "T1"]

_OUTPUT_FILES = {
    "01": {
        "label": "01 · HS per Klaster",
        "file":  "01_HS_Code_Final_per_Klaster.xlsx",
        "icon":  "📂",
    },
    "02": {
        "label": "02 · Profil HS Code",
        "file":  "02_Profil_HS_Code.xlsx",
        "icon":  "📊",
    },
    "03": {
        "label": "03 · Matriks Sinkronisasi",
        "file":  "03_Matriks_Sinkronisasi_HS_KLU.xlsx",
        "icon":  "🔗",
    },
    "04": {
        "label": "04 · Rekomendasi Prioritas",
        "file":  "04_Rekomendasi_Prioritas.xlsx",
        "icon":  "🚨",
    },
    "05": {
        "label": "05 · Catatan Data",
        "file":  "05_Catatan_Data_Tambahan.xlsx",
        "icon":  "📝",
    },
}

# ── Color scheme (same as app.py) ─────────────────────────────────────────────

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
    "text":    "#F1F5F9",
    "muted":   "#94A3B8",
}

# ── Data loader (cached) ───────────────────────────────────────────────────────

@lru_cache(maxsize=40)
def _load_sheet(year: str, file_key: str, sheet: str) -> tuple[list[dict], list[dict], str]:
    """
    Returns (data, columns, error_msg).
    Uses lru_cache — called with immutable args so safe to cache.
    """
    meta = _OUTPUT_FILES.get(file_key)
    if not meta:
        return [], [], f"File key '{file_key}' tidak dikenal."

    # Try year-specific folder first, then root output dir
    path_year = os.path.join(_OUTPUT_DIR, year, meta["file"])
    path_root = os.path.join(_OUTPUT_DIR, meta["file"])
    path = path_year if os.path.exists(path_year) else path_root

    if not os.path.exists(path):
        return [], [], f"File tidak ditemukan: {path}"

    try:
        # Try header=3 first (standard for these output files)
        df = pd.read_excel(path, sheet_name=sheet, header=3)
        # Drop unnamed columns
        df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]
        # If dataframe looks empty or header looks wrong, try header=0
        if df.empty or len(df.columns) == 0:
            df = pd.read_excel(path, sheet_name=sheet, header=0)
            df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]
    except Exception as exc:
        return [], [], f"Gagal membaca sheet '{sheet}': {exc}"

    # Fill NaN for display
    df = df.fillna("")

    # Coerce all values to string/number for DataTable serialization
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype(str)

    columns = [
        {
            "name": str(c),
            "id":   str(c),
            "type": "numeric" if pd.api.types.is_numeric_dtype(df[c]) else "text",
        }
        for c in df.columns
    ]
    data = df.to_dict("records")
    return data, columns, ""


@lru_cache(maxsize=20)
def _get_sheets(year: str, file_key: str) -> list[str] | None:
    """Return sheet names for a given year+file, or None if file missing."""
    meta = _OUTPUT_FILES.get(file_key)
    if not meta:
        return None
    path_year = os.path.join(_OUTPUT_DIR, year, meta["file"])
    path_root = os.path.join(_OUTPUT_DIR, meta["file"])
    path = path_year if os.path.exists(path_year) else path_root
    if not os.path.exists(path):
        return None
    try:
        return pd.ExcelFile(path).sheet_names
    except Exception:
        return None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _tab_style(active: bool = False) -> dict:
    return {
        "padding":         "7px 18px",
        "fontSize":        "12px",
        "fontWeight":      "600",
        "cursor":          "pointer",
        "borderRadius":    "6px 6px 0 0",
        "border":          f"1px solid {CLR['border']}",
        "borderBottom":    "none",
        "backgroundColor": CLR["accent"] if active else CLR["surface"],
        "color":           "#fff"          if active else CLR["muted"],
        "marginRight":     "4px",
    }


def _card(children: Any, **extra_style) -> html.Div:
    style = {
        "backgroundColor": CLR["card"],
        "border":          f"1px solid {CLR['border']}",
        "borderRadius":    "10px",
        "padding":         "18px 20px",
        **extra_style,
    }
    return html.Div(children, style=style)


# ── DataTable factory ──────────────────────────────────────────────────────────

_DT_STYLE_TABLE = {
    "overflowX":  "auto",
    "overflowY":  "auto",
    "maxHeight":  "62vh",
    "borderRadius": "6px",
}

_DT_STYLE_HEADER = {
    "backgroundColor": CLR["surface"],
    "color":           CLR["text"],
    "fontWeight":      "700",
    "fontSize":        "11px",
    "border":          f"1px solid {CLR['border']}",
    "whiteSpace":      "normal",
    "height":          "auto",
}

_DT_STYLE_CELL = {
    "backgroundColor": CLR["card"],
    "color":           CLR["muted"],
    "fontSize":        "12px",
    "border":          f"1px solid {CLR['border']}22",
    "padding":         "6px 10px",
    "maxWidth":        "300px",
    "overflow":        "hidden",
    "textOverflow":    "ellipsis",
}

_DT_STYLE_DATA_ODD = {
    "backgroundColor": CLR["bg"],
}

_DT_FILTER_STYLE = {
    "backgroundColor": CLR["surface"],
    "color":           CLR["text"],
    "fontSize":        "11px",
    "border":          f"1px solid {CLR['border']}",
}


def _make_table(data: list[dict], columns: list[dict], tbl_id: str) -> dash_table.DataTable:
    return dash_table.DataTable(
        id=tbl_id,
        data=data,
        columns=columns,
        page_size=25,
        sort_action="native",
        filter_action="native",
        filter_query="",
        style_table=_DT_STYLE_TABLE,
        style_header=_DT_STYLE_HEADER,
        style_cell=_DT_STYLE_CELL,
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": CLR["bg"]},
            {"if": {"filter_query": '{Risk Score} > 0.7'},
             "backgroundColor": "#EF444415", "color": CLR["danger"]},
        ],
        style_filter=_DT_FILTER_STYLE,
        tooltip_data=[
            {
                col["id"]: {"value": str(row.get(col["id"], "")), "type": "markdown"}
                for col in columns
            }
            for row in data[:200]
        ] if data else [],
        tooltip_delay=400,
        tooltip_duration=None,
    )


# ── Page Layout ────────────────────────────────────────────────────────────────

def layout() -> html.Div:
    return html.Div([
        # ── Page header ───────────────────────────────────────────────────────
        _card(
            html.Div([
                html.Div([
                    html.H2(
                        "Hasil Analisa",
                        style={"margin": "0", "fontSize": "18px",
                               "fontWeight": "700", "color": CLR["text"]},
                    ),
                    html.Span(
                        "5 file output hasil analisis PIB × HS Code × KLU",
                        style={"fontSize": "12px", "color": CLR["muted"],
                               "marginLeft": "12px"},
                    ),
                ], style={"display": "flex", "alignItems": "center"}),

                # Year dropdown
                html.Div([
                    html.Label("Tahun Analisa:",
                               style={"fontSize": "11px", "color": CLR["muted"],
                                      "marginRight": "8px", "fontWeight": "600"}),
                    dcc.Dropdown(
                        id="ha-dd-year",
                        options=[{"label": y, "value": y} for y in YEARS],
                        value="2023",
                        clearable=False,
                        style={"width": "100px", "fontSize": "13px"},
                    ),
                ], style={"display": "flex", "alignItems": "center"}),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "center"}),
            marginBottom="12px",
        ),

        # ── File tabs ─────────────────────────────────────────────────────────
        dcc.Tabs(
            id="ha-file-tabs",
            value="02",
            children=[
                dcc.Tab(
                    label=f"{meta['icon']} {meta['label']}",
                    value=fk,
                    style={"backgroundColor": CLR["surface"],
                           "color": CLR["muted"], "fontSize": "12px",
                           "fontWeight": "600", "padding": "8px 16px",
                           "border": f"1px solid {CLR['border']}"},
                    selected_style={"backgroundColor": CLR["accent"],
                                    "color": "#fff", "fontSize": "12px",
                                    "fontWeight": "700", "padding": "8px 16px",
                                    "border": f"1px solid {CLR['accent']}"},
                )
                for fk, meta in _OUTPUT_FILES.items()
            ],
            style={"marginBottom": "0"},
            colors={"border": CLR["border"], "primary": CLR["accent"],
                    "background": CLR["surface"]},
        ),

        # ── Tab content (sheet sub-tabs + table) ──────────────────────────────
        dcc.Loading(
            html.Div(id="ha-tab-content",
                     style={"backgroundColor": CLR["card"],
                            "border": f"1px solid {CLR['border']}",
                            "borderTop": "none",
                            "borderRadius": "0 0 10px 10px",
                            "padding": "16px"}),
            type="dot", color=CLR["accent"],
            style={"minHeight": "120px"},
        ),
    ], style={
        "padding":          "16px 22px",
        "backgroundColor":  CLR["bg"],
        "minHeight":        "calc(100vh - 52px)",
        "fontFamily":       "'Inter','Segoe UI',sans-serif",
    })


# ── Callbacks ─────────────────────────────────────────────────────────────────

@callback(
    Output("ha-tab-content", "children"),
    Input("ha-file-tabs",    "value"),
    Input("ha-dd-year",      "value"),
    prevent_initial_call=False,
)
def render_file_tab(file_key: str, year: str) -> Any:
    if not file_key or not year:
        return html.P("Pilih tahun dan file.", style={"color": CLR["muted"]})

    try:
        sheets = _get_sheets(year, file_key)
        if sheets is None:
            meta = _OUTPUT_FILES.get(file_key, {})
            return html.Div(
                f"File '{meta.get('file','')}' tidak ditemukan untuk tahun {year}.",
                style={"color": CLR["danger"], "fontSize": "13px", "padding": "20px"},
            )

        if not sheets:
            return html.Div("File kosong / tidak ada sheet.",
                            style={"color": CLR["muted"], "padding": "20px"})

        # Sub-tabs per sheet
        sub_tabs = dcc.Tabs(
            id="ha-sheet-tabs",
            value=sheets[0],
            children=[
                dcc.Tab(
                    label=sh,
                    value=sh,
                    style={"backgroundColor": CLR["surface"],
                           "color": CLR["muted"], "fontSize": "11px",
                           "padding": "5px 14px",
                           "border": f"1px solid {CLR['border']}"},
                    selected_style={"backgroundColor": CLR["surface"],
                                    "color": CLR["warm"], "fontSize": "11px",
                                    "fontWeight": "700", "padding": "5px 14px",
                                    "borderBottom": f"2px solid {CLR['warm']}",
                                    "border": f"1px solid {CLR['border']}"},
                )
                for sh in sheets
            ],
            colors={"border": CLR["border"], "primary": CLR["warm"],
                    "background": CLR["surface"]},
            style={"marginBottom": "12px"},
        )

        # Table for first sheet (default visible)
        data, columns, err = _load_sheet(year, file_key, sheets[0])
        if err:
            first_content: Any = html.Div(err, style={"color": CLR["danger"],
                                                       "fontSize": "12px"})
        elif not columns:
            first_content = html.Div("Sheet kosong.",
                                     style={"color": CLR["muted"]})
        else:
            row_count = len(data)
            first_content = html.Div([
                html.Div(
                    f"{row_count:,} baris  ·  {len(columns)} kolom  "
                    "· Klik header untuk sort · Isi filter di bawah header untuk filter",
                    style={"fontSize": "11px", "color": CLR["muted"],
                           "marginBottom": "8px"},
                ),
                _make_table(data, columns, "ha-data-table"),
            ])

        return html.Div([
            sub_tabs,
            html.Div(id="ha-sheet-content", children=first_content),
        ])

    except Exception:
        tb = traceback.format_exc()
        return html.Pre(tb, style={"color": CLR["danger"], "fontSize": "11px",
                                   "background": CLR["surface"], "padding": "12px",
                                   "borderRadius": "6px", "overflow": "auto"})


@callback(
    Output("ha-sheet-content", "children"),
    Input("ha-sheet-tabs",  "value"),
    Input("ha-file-tabs",   "value"),
    Input("ha-dd-year",     "value"),
    prevent_initial_call=True,
)
def render_sheet(sheet: str, file_key: str, year: str) -> Any:
    if not sheet or not file_key or not year:
        return html.P("—", style={"color": CLR["muted"]})

    try:
        data, columns, err = _load_sheet(year, file_key, sheet)
        if err:
            return html.Div(err, style={"color": CLR["danger"], "fontSize": "12px"})
        if not columns:
            return html.Div("Sheet kosong.", style={"color": CLR["muted"]})

        row_count = len(data)
        return html.Div([
            html.Div(
                f"{row_count:,} baris  ·  {len(columns)} kolom  "
                "· Klik header untuk sort · Isi filter di bawah header untuk filter",
                style={"fontSize": "11px", "color": CLR["muted"],
                       "marginBottom": "8px"},
            ),
            _make_table(data, columns, "ha-data-table"),
        ])

    except Exception:
        tb = traceback.format_exc()
        return html.Pre(tb, style={"color": CLR["danger"], "fontSize": "11px",
                                   "background": CLR["surface"], "padding": "12px",
                                   "borderRadius": "6px", "overflow": "auto"})
