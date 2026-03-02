"""
pages/admin.py
Admin Panel — accessible only to users with role='admin'.

Features:
  1. Download source code as a ZIP archive.
  2. Upload a ZIP patch → saved to uploads/; manual restart required.
  3. Git pull (whitelisted command; only if .git folder exists).

Security trade-offs:
  - Download: in-memory ZIP, no disk write; safe.
  - Upload ZIP: file is saved to uploads/ without execution; safe.
    Requires a manual restart to apply changes. No RCE possible.
  - Git pull: runs ["git", "pull"] (hardcoded, not user-supplied);
    stdout is captured and displayed. No arbitrary shell execution.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import subprocess
import zipfile
from datetime import datetime

from dash import (
    Input, Output, State,
    callback, dcc, html, register_page,
)
from flask import session

register_page(__name__, name="Admin", path="/admin", order=99)

logger = logging.getLogger(__name__)

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

# ── Palette ───────────────────────────────────────────────────────────────────

CLR = {
    "bg":      "#0B0F1A",
    "card":    "#111827",
    "surface": "#1E293B",
    "border":  "#2A3A52",
    "accent":  "#3B82F6",
    "warm":    "#F59E0B",
    "danger":  "#EF4444",
    "success": "#10B981",
    "text":    "#BD4205",
    "muted":   "#94A3B8",
}

_CARD = {
    "backgroundColor": CLR["card"],
    "borderRadius": "10px",
    "padding": "20px 24px",
    "marginBottom": "16px",
    "border": f"1px solid {CLR['border']}",
}

_BTN = {
    "border": "none", "borderRadius": "6px",
    "padding": "9px 20px", "fontSize": "12px",
    "fontWeight": "600", "cursor": "pointer",
}

_PRE = {
    "backgroundColor": CLR["bg"],
    "color": CLR["muted"],
    "border": f"1px solid {CLR['border']}",
    "borderRadius": "6px",
    "padding": "12px",
    "fontSize": "11px",
    "whiteSpace": "pre-wrap",
    "wordBreak": "break-word",
    "maxHeight": "260px",
    "overflowY": "auto",
    "marginTop": "10px",
    "fontFamily": "monospace",
}


def sec(title, children):
    return html.Div([
        html.Div(title, style={
            "color": CLR["accent"], "fontSize": "10px", "fontWeight": "700",
            "letterSpacing": "0.12em", "textTransform": "uppercase",
            "marginBottom": "12px",
        }),
        *children,
    ], style=_CARD)


# ── Source ZIP builder ────────────────────────────────────────────────────────

_INCLUDE_FILES = ["app.py", "auth.py", "requirements.txt", "pyproject.toml"]
_INCLUDE_DIRS  = ["pages", "utils", "assets"]
_INCLUDE_EXT   = {".py", ".css", ".toml", ".txt", ".json", ".md"}
_SKIP_DIRS     = {"__pycache__", ".git", "uploads", "input", "output", ".venv", "venv"}


def _create_source_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in _INCLUDE_FILES:
            fpath = os.path.join(BASE_DIR, fname)
            if os.path.isfile(fpath):
                zf.write(fpath, fname)
        for dname in _INCLUDE_DIRS:
            dpath = os.path.join(BASE_DIR, dname)
            if not os.path.isdir(dpath):
                continue
            for root, dirs, files in os.walk(dpath):
                dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
                for fn in files:
                    if os.path.splitext(fn)[1] in _INCLUDE_EXT:
                        fp = os.path.join(root, fn)
                        zf.write(fp, os.path.relpath(fp, BASE_DIR))
    buf.seek(0)
    return buf.read()


# ── Layout (function → called fresh each page load, checks session) ───────────

def layout():
    if not session.get("authenticated"):
        return dcc.Location(id="admin-redir-auth", href="/login", refresh=True)
    if session.get("role") != "admin":
        return html.Div([
            html.Div("Akses ditolak. Halaman ini hanya untuk Admin.",
                     style={"color": CLR["danger"], "padding": "40px",
                            "fontSize": "14px", "textAlign": "center"}),
        ], style={"backgroundColor": CLR["bg"], "minHeight": "100vh"})

    has_git = os.path.isdir(os.path.join(BASE_DIR, ".git"))

    return html.Div([
        # Title
        html.Div([
            html.Div("Panel Admin", style={
                "fontSize": "18px", "fontWeight": "700", "color": CLR["text"],
            }),
            html.Div("Hanya pengguna dengan peran admin yang dapat mengakses halaman ini.",
                     style={"fontSize": "11px", "color": CLR["muted"], "marginTop": "4px"}),
        ], style={"marginBottom": "20px"}),

        # ── Section 1: Download Source ────────────────────────────────────────
        sec("1 — Unduh Kode Sumber", [
            html.P(
                "Mengunduh semua file .py, .css, .toml, .txt dari folder proyek "
                "sebagai arsip ZIP. Input data dan folder output tidak disertakan.",
                style={"fontSize": "12px", "color": CLR["muted"], "marginBottom": "12px"},
            ),
            html.Button(
                "Unduh source.zip",
                id="admin-btn-download",
                style={**_BTN, "backgroundColor": CLR["success"], "color": "#fff"},
            ),
            dcc.Download(id="admin-download"),
        ]),

        # ── Section 2: Upload ZIP Patch ───────────────────────────────────────
        sec("2 — Upload Patch ZIP", [
            html.P([
                "Upload file ZIP berisi patch kode. File disimpan ke folder ",
                html.Code("uploads/", style={"color": CLR["warm"]}),
                " dan TIDAK langsung dieksekusi. ",
                html.Strong("Restart server secara manual untuk menerapkan perubahan.",
                            style={"color": CLR["warm"]}),
            ], style={"fontSize": "12px", "color": CLR["muted"], "marginBottom": "12px"}),
            dcc.Upload(
                id="admin-upload",
                children=html.Div([
                    "Seret & lepas atau ",
                    html.A("klik untuk memilih file ZIP",
                           style={"color": CLR["accent"], "cursor": "pointer"}),
                ]),
                style={
                    "width": "100%", "padding": "20px",
                    "borderWidth": "1px", "borderStyle": "dashed",
                    "borderColor": CLR["border"], "borderRadius": "8px",
                    "textAlign": "center", "fontSize": "12px",
                    "color": CLR["muted"], "cursor": "pointer",
                    "backgroundColor": CLR["surface"],
                },
                accept=".zip",
                max_size=50 * 1024 * 1024,  # 50 MB
            ),
            html.Div(id="admin-upload-status", style={"marginTop": "10px", "fontSize": "12px"}),
        ]),

        # ── Section 3: Git Pull ───────────────────────────────────────────────
        sec("3 — Git Pull" + (" [tidak tersedia — .git tidak ditemukan]" if not has_git else ""), [
            html.P(
                "Menjalankan `git pull` di direktori proyek. "
                "Perintah bersifat tetap (tidak dapat diubah pengguna). "
                "Restart server secara manual setelah pull berhasil.",
                style={"fontSize": "12px", "color": CLR["muted"], "marginBottom": "12px"},
            ),
            html.Button(
                "Jalankan git pull",
                id="admin-btn-git",
                disabled=not has_git,
                style={
                    **_BTN,
                    "backgroundColor": CLR["accent"] if has_git else CLR["surface"],
                    "color": "#fff" if has_git else CLR["muted"],
                    "cursor": "pointer" if has_git else "not-allowed",
                },
            ),
            html.Div(id="admin-git-output"),
        ]),

        # ── Section 4: Changelog ──────────────────────────────────────────────
        sec("4 — Changelog", [_build_changelog()]),

    ], style={
        "backgroundColor": CLR["bg"],
        "minHeight": "100vh",
        "padding": "24px 32px",
        "fontFamily": "'Inter','Segoe UI',sans-serif",
        "color": CLR["text"],
        "maxWidth": "860px",
    })


def _build_changelog():
    try:
        from app import CHANGELOG, VERSION
    except Exception:
        return html.Div("Changelog tidak tersedia.", style={"color": CLR["muted"]})

    items = []
    for ver, date, notes in CHANGELOG:
        items.append(html.Div([
            html.Span(ver, style={"color": CLR["accent"], "fontWeight": "700",
                                  "fontSize": "13px"}),
            html.Span(f"  {date}", style={"color": CLR["muted"], "fontSize": "11px",
                                           "marginLeft": "8px"}),
            html.Ul([html.Li(n, style={"fontSize": "12px", "color": CLR["muted"],
                                        "marginBottom": "2px"}) for n in notes],
                    style={"marginTop": "4px", "paddingLeft": "18px"}),
        ], style={"marginBottom": "12px"}))
    return html.Div(items)


# ── Callbacks ─────────────────────────────────────────────────────────────────

@callback(
    Output("admin-download", "data"),
    Input("admin-btn-download", "n_clicks"),
    prevent_initial_call=True,
)
def download_source(n_clicks):
    if not session.get("role") == "admin":
        return None
    logger.info("[ADMIN] Source ZIP downloaded by %s", session.get("user"))
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    data = _create_source_zip()
    return dcc.send_bytes(data, f"sr15_source_{ts}.zip")


@callback(
    Output("admin-upload-status", "children"),
    Input("admin-upload", "contents"),
    State("admin-upload", "filename"),
    prevent_initial_call=True,
)
def save_patch(contents, filename):
    if not session.get("role") == "admin":
        return html.Span("Akses ditolak.", style={"color": CLR["danger"]})
    if not contents or not filename:
        return None
    if not filename.lower().endswith(".zip"):
        return html.Span("Hanya file .zip yang diizinkan.", style={"color": CLR["danger"]})

    _, b64 = contents.split(",", 1)
    raw    = base64.b64decode(b64)

    # Validate it's a real ZIP
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        return html.Span("File bukan ZIP yang valid.", style={"color": CLR["danger"]})

    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    outname = f"patch_{ts}_{filename}"
    outpath = os.path.join(UPLOADS_DIR, outname)
    with open(outpath, "wb") as f:
        f.write(raw)

    logger.info("[ADMIN] Patch uploaded by %s -> %s (%d bytes)",
                session.get("user"), outname, len(raw))

    return html.Div([
        html.Span("Upload berhasil: ", style={"color": CLR["success"], "fontWeight": "600"}),
        html.Code(outname, style={"color": CLR["warm"]}),
        html.Br(),
        html.Span(
            "Restart server secara manual (Ctrl+C, lalu python app.py) untuk menerapkan patch.",
            style={"color": CLR["muted"], "fontSize": "11px"},
        ),
    ])


@callback(
    Output("admin-git-output", "children"),
    Input("admin-btn-git", "n_clicks"),
    prevent_initial_call=True,
)
def git_pull(n_clicks):
    if not session.get("role") == "admin":
        return html.Span("Akses ditolak.", style={"color": CLR["danger"]})
    if not os.path.isdir(os.path.join(BASE_DIR, ".git")):
        return html.Span(".git tidak ditemukan.", style={"color": CLR["danger"]})

    logger.info("[ADMIN] git pull triggered by %s", session.get("user"))
    try:
        result = subprocess.run(
            ["git", "pull"],
            capture_output=True,
            text=True,
            cwd=BASE_DIR,
            timeout=30,
        )
        output = (result.stdout + result.stderr).strip() or "(no output)"
    except subprocess.TimeoutExpired:
        output = "Timeout: git pull melebihi 30 detik."
    except FileNotFoundError:
        output = "Error: perintah 'git' tidak ditemukan di PATH."
    except Exception as exc:
        output = f"Error: {exc}"

    color = CLR["success"] if "Already up to date" in output or "Updating" in output \
            else CLR["danger"]
    return html.Pre(output[:3000], style={**_PRE, "borderColor": color})
