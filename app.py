"""
app.py
SR15 Analytics — Multi-page Dash entrypoint  v1.1.0

Run:
    python app.py
    python app.py --port 8080
    PORT=8080 python app.py

Access:
    Local : http://127.0.0.1:8050
    LAN   : http://<HOST-IP>:8050   (printed at startup)

Auth:
    user  / yauser       — view dashboards
    admin / admin        — + admin panel (set ADMIN_USERNAME / ADMIN_PASSWORD in prod)
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import socket
import threading

from dash import Dash, html, dcc, page_container, Input, Output
from flask import request, Response, redirect, session

import auth

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Version ───────────────────────────────────────────────────────────────────

VERSION = "v1.1.0"

CHANGELOG: list[tuple[str, str, list[str]]] = [
    ("v1.1.0", "2026-02-26", [
        "Session-based auth with Admin / User roles",
        "PPN (Rp Juta) range filter on Enhanced page",
        "Multi-select autocomplete for NM_KLU and NM_KELOMPOK",
        "Admin panel: download source ZIP, upload patch ZIP, Git pull",
        "Claude Sonnet 4.5 chatbot page (ANTHROPIC_API_KEY required)",
        "Version log and copyright label",
    ]),
    ("v1.0.0", "2026-02-26", [
        "Multi-page Dash architecture (Pages API)",
        "SR15 Enhanced page with Cytoscape graph",
        "Rule-based chatbot (tab in Enhanced page)",
        "Flask-Caching; LAN access on 0.0.0.0",
    ]),
]

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_PORT = int(os.environ.get("PORT", 8050))
HOST = "0.0.0.0"

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

# ── App ───────────────────────────────────────────────────────────────────────

app = Dash(
    __name__,
    use_pages=True,
    pages_folder="pages",
    title=f"SR15 Analytics {VERSION}",
    suppress_callback_exceptions=True,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)

# Flask secret key (CHANGE IN PRODUCTION via SECRET_KEY env var)
_secret = os.environ.get("SECRET_KEY", "sr15-change-me-in-production-2026")
if _secret == "sr15-change-me-in-production-2026":
    logger.warning("[APP] SECRET_KEY is default. Set SECRET_KEY env var in production!")
app.server.secret_key = _secret

app.server.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

# ── Flask-Caching ─────────────────────────────────────────────────────────────

from flask_caching import Cache  # noqa: E402

cache = Cache(app.server, config={
    "CACHE_TYPE":            "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 600,
})

# ── Login page HTML ───────────────────────────────────────────────────────────

_LOGIN_HTML = """\
<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SR15 Analytics - Login</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:#0B0F1A;color:#94A3B8;font-family:'Segoe UI',sans-serif;
          display:flex;align-items:center;justify-content:center;min-height:100vh}}
    .card{{background:#111827;border:1px solid #2A3A52;border-radius:12px;
           padding:40px 44px;width:360px;box-shadow:0 8px 32px #00000055}}
    h1{{color:#BD4205;font-size:19px;font-weight:700;margin-bottom:4px}}
    .sub{{font-size:11px;color:#4B5563;margin-bottom:28px;line-height:1.5}}
    label{{display:block;font-size:10px;font-weight:700;letter-spacing:.08em;
           text-transform:uppercase;margin-bottom:5px;color:#94A3B8}}
    input[type=text],input[type=password]{{
           width:100%;background:#1E293B;color:#E2E8F0;
           border:1px solid #2A3A52;border-radius:6px;
           padding:9px 12px;font-size:13px;outline:none;margin-bottom:14px}}
    input:focus{{border-color:#3B82F6}}
    .btn{{width:100%;background:#3B82F6;color:#fff;border:none;border-radius:6px;
          padding:11px;font-size:13px;font-weight:600;cursor:pointer;margin-top:6px}}
    .btn:hover{{background:#2563EB}}
    .btn-guest{{width:100%;background:transparent;color:#10B981;border:1px solid #10B98155;
               border-radius:6px;padding:10px;font-size:12px;font-weight:600;
               cursor:pointer;margin-top:8px;text-align:center;display:block;
               text-decoration:none}}
    .btn-guest:hover{{background:#10B98115;border-color:#10B981}}
    .divider{{display:flex;align-items:center;gap:8px;margin:14px 0 6px;
             color:#2A3A52;font-size:10px}}
    .divider::before,.divider::after{{content:"";flex:1;border-top:1px solid #2A3A52}}
    .err{{color:#EF4444;font-size:12px;margin-bottom:14px;background:#EF444420;
          padding:8px 12px;border-radius:6px;border-left:3px solid #EF4444}}
    .ver{{font-size:10px;color:#1E293B;text-align:center;margin-top:18px}}
    .copy{{position:fixed;bottom:8px;left:12px;font-size:10px;color:#1E293B}}
  </style>
</head>
<body>
  <div class="card">
    <h1>SR15 Analytics</h1>
    <div class="sub">PIB x HS Code x KLU<br>CRM Subtim Data Analyst 2026</div>
    {error_block}
    <form method="POST" action="/do_login">
      <label>Username</label>
      <input type="text" name="username" autocomplete="username" autofocus required>
      <label>Password</label>
      <input type="password" name="password" autocomplete="current-password" required>
      <button class="btn" type="submit">Masuk</button>
    </form>
    <div class="divider">atau</div>
    <a href="/guest-login" class="btn-guest">Masuk sebagai Tamu (view only)</a>
    <div class="ver">{version}</div>
  </div>
  <div class="copy">&copy; nuwishnu</div>
</body>
</html>"""

# ── Flask auth routes ─────────────────────────────────────────────────────────

@app.server.route("/login", methods=["GET"])
def login_page():
    if session.get("authenticated"):
        return redirect("/")
    error = request.args.get("error", "")
    error_block = f'<div class="err">{error}</div>' if error else ""
    html_str = _LOGIN_HTML.format(error_block=error_block, version=VERSION)
    return html_str, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.server.route("/do_login", methods=["POST"])
def do_login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = auth.check_credentials(username, password)
    if role:
        session.clear()
        session["authenticated"] = True
        session["user"] = username
        session["role"] = role
        logger.info("[AUTH] Login: user=%s role=%s ip=%s",
                    username, role, request.remote_addr)
        return redirect("/")
    logger.warning("[AUTH] Failed login: user=%s ip=%s", username, request.remote_addr)
    return redirect("/login?error=Username+atau+password+salah")


@app.server.route("/guest-login")
def guest_login():
    """Auto-login as read-only 'user' role — for DGT_GUEST network access."""
    if session.get("authenticated"):
        return redirect("/")
    session.clear()
    session["authenticated"] = True
    session["user"] = "tamu"
    session["role"] = "user"
    logger.info("[AUTH] Guest login from ip=%s", request.remote_addr)
    return redirect("/")


@app.server.route("/do_logout")
def do_logout():
    user = session.get("user", "?")
    session.clear()
    logger.info("[AUTH] Logout: user=%s ip=%s", user, request.remote_addr)
    return redirect("/login")


# ── Auth enforcement (before_request) ────────────────────────────────────────

_EXEMPT = ("/login", "/do_login", "/do_logout", "/guest-login")
_EXEMPT_PREFIX = ("/_dash-component-suites/", "/assets/", "/_favicon")


@app.server.before_request
def require_auth():
    path = request.path
    if path in _EXEMPT:
        return
    if any(path.startswith(p) for p in _EXEMPT_PREFIX):
        return
    if not session.get("authenticated"):
        if path.startswith("/_dash-"):
            return Response(
                json.dumps({"status": "unauthenticated"}),
                401, {"Content-Type": "application/json"},
            )
        return redirect("/login")


# ── Nav bar (dynamic, reads session) ─────────────────────────────────────────

_NL = {  # nav link style
    "color": CLR["muted"],
    "textDecoration": "none",
    "padding": "4px 12px",
    "borderRadius": "5px",
    "fontSize": "12px",
    "fontWeight": "500",
}


def _nav_link(label, href, color=None):
    style = {**_NL, **({"color": color} if color else {})}
    return dcc.Link(label, href=href, style=style)


# ── App layout ────────────────────────────────────────────────────────────────

app.layout = html.Div([
    # Nav location trigger (fires on every Dash client-side navigation)
    dcc.Location(id="nav-loc", refresh=False),

    # Dynamic nav bar
    html.Div(id="nav-bar"),

    # Page content
    page_container,

    # Copyright — fixed bottom-left, non-blocking
    html.Div(
        "\u00a9 nuwishnu",
        style={
            "position": "fixed",
            "bottom": "8px",
            "left": "12px",
            "fontSize": "10px",
            "color": CLR["muted"],
            "zIndex": "9999",
            "pointerEvents": "none",
            "userSelect": "none",
            "opacity": "0.5",
        },
    ),
], style={
    "backgroundColor": CLR["bg"],
    "minHeight": "100vh",
    "fontFamily": "'Inter','Segoe UI',sans-serif",
    "color": CLR["text"],
})


@app.callback(
    Output("nav-bar", "children"),
    Input("nav-loc", "pathname"),
)
def render_nav(_pathname):
    user = auth.current_user()
    role = auth.current_role()

    # Page links
    links = [
        _nav_link("SR15 Enhanced",  "/",              CLR["accent"]),
        _nav_link("Hasil Analisa",  "/hasil-analisa", CLR["warm"]),
        _nav_link("Panduan",        "/panduan",        CLR["purple"]),
        _nav_link("Chatbot",        "/chatbot",        CLR["success"]),
    ]
    if role == "admin":
        links.append(_nav_link("Admin", "/admin", CLR["danger"]))

    # Version tooltip (title attribute)
    changelog_tip = " | ".join(
        f"{v} ({d}): {'; '.join(items[:2])}"
        for v, d, items in CHANGELOG[:2]
    )

    right = html.Div([
        html.Span(
            f"{user}",
            style={"color": CLR["muted"], "fontSize": "11px", "marginRight": "6px"},
        ),
        html.Span(
            f"[{role}]",
            style={
                "backgroundColor": (CLR["danger"] if role == "admin" else CLR["surface"]) + "33",
                "color":           CLR["danger"] if role == "admin" else CLR["muted"],
                "border":          f"1px solid {(CLR['danger'] if role == 'admin' else CLR['border'])}55",
                "borderRadius":    "10px",
                "padding":         "1px 8px",
                "fontSize":        "10px",
                "marginRight":     "12px",
            },
        ),
        html.A(
            "Keluar",
            href="/do_logout",
            style={
                "backgroundColor": CLR["danger"] + "22",
                "color":           CLR["danger"],
                "border":          f"1px solid {CLR['danger']}55",
                "borderRadius":    "6px",
                "padding":         "4px 12px",
                "fontSize":        "11px",
                "fontWeight":      "600",
                "textDecoration":  "none",
                "cursor":          "pointer",
            },
        ),
        html.Span(
            VERSION,
            title=changelog_tip,
            style={
                "color": CLR["muted"], "fontSize": "10px",
                "marginLeft": "14px", "cursor": "help",
                "opacity": "0.5",
            },
        ),
    ], style={"display": "flex", "alignItems": "center"})

    return html.Div([
        html.Div([
            html.Span("PIB \u00d7 HS Code \u00d7 KLU",
                      style={"fontSize": "16px", "fontWeight": "700"}),
            html.Span("  SR Importir Umum \u2014 CRM Subtim Data Analyst 2026",
                      style={"fontSize": "11px", "color": CLR["muted"], "marginLeft": "10px"}),
        ]),
        html.Div(links + [right],
                 style={"display": "flex", "alignItems": "center", "gap": "2px"}),
    ], style={
        "display": "flex", "justifyContent": "space-between", "alignItems": "center",
        "padding": "10px 22px",
        "backgroundColor": CLR["card"],
        "borderBottom": f"1px solid {CLR['border']}",
        "position": "sticky", "top": "0", "zIndex": "300",
        "height": "52px", "boxSizing": "border-box",
        "fontFamily": "'Inter','Segoe UI',sans-serif",
    })


# ── LAN IP ────────────────────────────────────────────────────────────────────

def _get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ── Entry point ───────────────────────────────────────────────────────────────

def _parse_args() -> int:
    p = argparse.ArgumentParser(description="SR15 Analytics Dashboard")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    args, _ = p.parse_known_args()
    return args.port


if __name__ == "__main__":
    port   = _parse_args()
    lan_ip = _get_lan_ip()

    logger.info("Starting SR15 Analytics %s", VERSION)

    print()
    print("=" * 64)
    print(f"  SR15 Analytics {VERSION} - PIB x HS Code x KLU")
    print(f"  CRM Subtim Data Analyst 2026")
    print("=" * 64)
    print(f"  Lokal  : http://127.0.0.1:{port}")
    print(f"  LAN    : http://{lan_ip}:{port}")
    print()
    print("  Login: user/yauser  |  admin/<ADMIN_PASSWORD>")
    print()
    print("  Pages:")
    print(f"    /              - SR15 Enhanced")
    print(f"    /hasil-analisa - Hasil Analisa (5 file output)")
    print(f"    /chatbot       - Chatbot (Claude AI jika ANTHROPIC_API_KEY diset)")
    print(f"    /admin         - Admin Panel  [admin only]")
    print()
    print("  Tekan Ctrl+C untuk berhenti.")
    print()

    try:
        import os as _os
        from utils.data import _FILE_MAP, INPUT_DIR
        for yr, fname in _FILE_MAP.items():
            fpath = _os.path.join(INPUT_DIR, fname)
            if _os.path.exists(fpath):
                mb = _os.path.getsize(fpath) / 1_048_576
                print(f"  [{yr}]  {fname[:50]}... ({mb:.1f} MB)")
            else:
                print(f"  [{yr}]  TIDAK DITEMUKAN: {fname}")
        print()
    except Exception as exc:
        logger.warning("File check gagal: %s", exc)

    # ── Preload default year (2023) + pre-warm filter cache ───────────────────
    try:
        from utils.data import load_raw, load_multi, apply_filters_cached
        print("  Memuat data 2023 (default)...", end=" ", flush=True)
        _df0 = load_raw("2023")
        print(f"{len(_df0):,} baris siap.", flush=True)

        # Pre-warm load_multi cache
        print("  Pre-warming filter cache...", end=" ", flush=True)
        _dfm = load_multi(["2023"])
        _default_state = {
            "years":       ["2023"],
            "pph_range":   [0, 5e9],
            "ppn_range":   [0, 1e10],
            "nm_klu":      [],
            "nm_kelompok": [],
            "kd_kelompok": [],
            "kd_detil":    [],
            "nm_subgol":   [],
            "kpp":         [],
        }
        apply_filters_cached(_dfm, _default_state)
        print("selesai.")
        print()
    except Exception as exc:
        logger.warning("[STARTUP] Gagal preload: %s", exc)

    # ── Preload remaining years in background ──────────────────────────────────
    def _preload_rest():
        from utils.data import load_raw, YEARS as _YEARS
        for yr in [y for y in _YEARS if y != "2023"]:
            try:
                df = load_raw(yr)
                logger.info("[PRELOAD] %s: %d rows cached", yr, len(df))
            except Exception as exc:
                logger.warning("[PRELOAD] %s failed: %s", yr, exc)

    threading.Thread(target=_preload_rest, daemon=True, name="data-preload").start()

    app.run(debug=False, host=HOST, port=port, threaded=True)
