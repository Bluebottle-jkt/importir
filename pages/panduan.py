"""
pages/panduan.py
Halaman Panduan — menampilkan PANDUAN_HASIL_ANALISA.md sebagai HTML.

Path: /panduan
"""

from __future__ import annotations

import os

from dash import dcc, html, register_page

register_page(__name__, name="Panduan", path="/panduan", order=3)

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MD_PATH = os.path.join(_BASE, "PANDUAN_HASIL_ANALISA.md")

CLR = {
    "bg":      "#0B0F1A",
    "card":    "#111827",
    "surface": "#1E293B",
    "border":  "#2A3A52",
    "accent":  "#3B82F6",
    "warm":    "#F59E0B",
    "danger":  "#EF4444",
    "success": "#10B981",
    "text":    "#F1F5F9",
    "muted":   "#94A3B8",
}


def _read_md() -> str:
    try:
        with open(_MD_PATH, encoding="utf-8") as f:
            return f.read()
    except Exception as exc:
        return f"# Error\n\nTidak dapat membaca file panduan: {exc}"


def layout() -> html.Div:
    md_content = _read_md()
    return html.Div([
        html.Div([
            dcc.Markdown(
                md_content,
                dangerously_allow_html=False,
                style={
                    "color":      CLR["text"],
                    "lineHeight": "1.85",
                    "fontSize":   "13px",
                },
                className="md-panduan",
            ),
        ], style={
            "maxWidth":        "960px",
            "margin":          "0 auto",
            "backgroundColor": CLR["card"],
            "border":          f"1px solid {CLR['border']}",
            "borderRadius":    "12px",
            "padding":         "32px 40px",
        }),

        # Inline markdown styling
        html.Style("""
            .md-panduan h1 { color: #3B82F6; font-size: 22px; margin-bottom: 6px; }
            .md-panduan h2 { color: #F59E0B; font-size: 17px; margin-top: 32px; margin-bottom: 8px;
                             border-bottom: 1px solid #2A3A52; padding-bottom: 6px; }
            .md-panduan h3 { color: #10B981; font-size: 14px; margin-top: 20px; margin-bottom: 6px; }
            .md-panduan h4 { color: #8B5CF6; font-size: 13px; margin-top: 16px; margin-bottom: 4px; }
            .md-panduan p  { color: #94A3B8; margin-bottom: 10px; }
            .md-panduan a  { color: #3B82F6; }
            .md-panduan blockquote {
                border-left: 3px solid #F59E0B;
                margin: 10px 0; padding: 8px 16px;
                background: #1E293B; border-radius: 0 6px 6px 0;
                color: #F1F5F9; font-style: italic;
            }
            .md-panduan table {
                border-collapse: collapse; width: 100%;
                margin-bottom: 14px; font-size: 12px;
            }
            .md-panduan th {
                background: #1E293B; color: #F1F5F9;
                font-weight: 700; padding: 7px 12px;
                border: 1px solid #2A3A52; text-align: left;
            }
            .md-panduan td {
                padding: 6px 12px; border: 1px solid #2A3A5244;
                color: #94A3B8;
            }
            .md-panduan tr:nth-child(even) td { background: #0B0F1A; }
            .md-panduan code {
                background: #1E293B; color: #10B981;
                padding: 1px 6px; border-radius: 4px;
                font-family: 'Cascadia Code', 'Consolas', monospace;
                font-size: 11px;
            }
            .md-panduan pre  {
                background: #1E293B; padding: 14px 16px;
                border-radius: 8px; overflow-x: auto;
                border: 1px solid #2A3A52;
            }
            .md-panduan pre code { background: none; padding: 0; font-size: 12px; }
            .md-panduan hr { border-color: #2A3A52; margin: 24px 0; }
            .md-panduan ul, .md-panduan ol {
                color: #94A3B8; padding-left: 20px; margin-bottom: 10px;
            }
            .md-panduan li { margin-bottom: 4px; }
            .md-panduan strong { color: #F1F5F9; }
        """),

    ], style={
        "padding":         "24px 22px",
        "backgroundColor": CLR["bg"],
        "minHeight":       "calc(100vh - 52px)",
        "fontFamily":      "'Inter','Segoe UI',sans-serif",
    })
