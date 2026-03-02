"""
pages/chatbot_page.py
Claude Sonnet 4.5 powered analytics chatbot.

- Model  : claude-sonnet-4-5 (via utils.chatbot.call_claude)
- API key: ANTHROPIC_API_KEY environment variable
- Context: anonymised aggregate dataset summary (no NPWP sent to API)
- Fallback: rule-based bot when API key is absent
"""

from __future__ import annotations

import logging

import pandas as pd
from dash import (
    Input, Output, State,
    callback, dcc, html, no_update, register_page,
)
from flask import session

from utils.data import YEARS, apply_filters, load_multi
from utils.chatbot import (
    RuleBasedChatbot, build_context, call_claude, claude_available, CLAUDE_MODEL,
)

register_page(__name__, name="Chatbot", path="/chatbot", order=2)

logger = logging.getLogger(__name__)
_FALLBACK_BOT = RuleBasedChatbot()

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

DD_STYLE = {
    "backgroundColor": CLR["surface"],
    "color": CLR["text"],
    "border": f"1px solid {CLR['border']}",
    "borderRadius": "6px",
    "fontSize": "12px",
}

INPUT_STYLE = {
    "backgroundColor": CLR["surface"],
    "color": CLR["text"],
    "border": f"1px solid {CLR['border']}",
    "borderRadius": "6px",
    "padding": "9px 12px",
    "fontSize": "13px",
    "outline": "none",
    "flex": "1",
}

# ── Layout ────────────────────────────────────────────────────────────────────

def layout():
    if not session.get("authenticated"):
        return dcc.Location(id="chatbot-redir", href="/login", refresh=True)

    api_ok = claude_available()
    api_badge = html.Span(
        "Claude aktif" if api_ok else "Fallback rule-based",
        style={
            "backgroundColor": (CLR["success"] if api_ok else CLR["warm"]) + "22",
            "color":           CLR["success"] if api_ok else CLR["warm"],
            "border":          f"1px solid {(CLR['success'] if api_ok else CLR['warm'])}44",
            "borderRadius":    "10px",
            "padding":         "2px 10px",
            "fontSize":        "11px",
            "marginLeft":      "8px",
        },
    )

    return html.Div([
        dcc.Store(id="chat-history",  storage_type="memory", data=[]),
        dcc.Store(id="chat-context",  storage_type="memory", data=""),

        html.Div([
            # Left panel
            html.Div([
                html.Div("Konteks Data", style={
                    "color": CLR["accent"], "fontSize": "10px", "fontWeight": "700",
                    "letterSpacing": "0.12em", "textTransform": "uppercase",
                    "marginBottom": "8px",
                }),
                html.Div("Pilih Tahun", style={"color": CLR["muted"], "fontSize": "10px",
                                               "marginBottom": "4px"}),
                dcc.Dropdown(
                    id="chat-dd-years",
                    options=[{"label": y, "value": y} for y in YEARS],
                    value=YEARS, multi=True, clearable=False, style=DD_STYLE,
                ),
                html.Br(),
                html.Button(
                    "Muat Konteks",
                    id="chat-btn-load",
                    style={
                        "backgroundColor": CLR["accent"], "color": "#fff",
                        "border": "none", "borderRadius": "6px",
                        "padding": "8px 16px", "fontSize": "12px",
                        "fontWeight": "600", "cursor": "pointer", "width": "100%",
                    },
                ),
                html.Div(id="chat-ctx-status",
                         style={"marginTop": "10px", "fontSize": "11px",
                                "color": CLR["muted"], "lineHeight": "1.7"}),

                html.Hr(style={"borderColor": CLR["border"], "margin": "16px 0"}),

                html.Div("Model", style={"color": CLR["muted"], "fontSize": "10px",
                                         "marginBottom": "4px"}),
                html.Div([
                    html.Code(CLAUDE_MODEL,
                              style={"color": CLR["warm"], "fontSize": "11px"}),
                    api_badge,
                ]),

                html.Br(),
                html.Div("Privasi", style={
                    "color": CLR["muted"], "fontSize": "10px", "fontWeight": "700",
                    "marginBottom": "4px",
                }),
                html.Div(
                    "Hanya statistik agregat yang dikirim ke API. "
                    "NPWP individual tidak pernah dikirim ke Anthropic.",
                    style={"fontSize": "10px", "color": CLR["border"], "lineHeight": "1.6"},
                ),
            ], style={
                "width": "240px", "minWidth": "240px",
                "padding": "16px 14px",
                "backgroundColor": CLR["card"],
                "borderRight": f"1px solid {CLR['border']}",
                "borderRadius": "10px 0 0 10px",
            }),

            # Right chat panel
            html.Div([
                html.Div([
                    html.Span("Asisten SR15",
                              style={"fontSize": "14px", "fontWeight": "700",
                                     "color": CLR["accent"]}),
                    html.Span(f" — {CLAUDE_MODEL}" if api_ok else " — Rule-Based",
                              style={"fontSize": "11px", "color": CLR["muted"]}),
                ], style={"marginBottom": "10px"}),

                html.Div(id="chat-messages", style={
                    "backgroundColor": CLR["bg"],
                    "borderRadius": "8px",
                    "padding": "12px",
                    "minHeight": "380px",
                    "maxHeight": "500px",
                    "overflowY": "auto",
                    "border": f"1px solid {CLR['border']}",
                    "fontSize": "12px",
                    "lineHeight": "1.8",
                }, children=[html.Div(
                    "Muat konteks data terlebih dahulu (klik tombol di kiri), "
                    "lalu ketik pertanyaan. Anda bisa bertanya bebas.",
                    style={"color": CLR["muted"]},
                )]),

                html.Div([
                    dcc.Input(
                        id="chat-input",
                        type="text",
                        placeholder="Ketik pertanyaan atau perintah...",
                        debounce=False,
                        n_submit=0,
                        style=INPUT_STYLE,
                    ),
                    html.Button("Kirim", id="chat-send", style={
                        "backgroundColor": CLR["accent"], "color": "#fff",
                        "border": "none", "borderRadius": "6px",
                        "padding": "9px 20px", "marginLeft": "8px",
                        "fontSize": "12px", "fontWeight": "600", "cursor": "pointer",
                    }),
                    html.Button("Bersihkan", id="chat-clear", style={
                        "backgroundColor": CLR["surface"], "color": CLR["muted"],
                        "border": f"1px solid {CLR['border']}", "borderRadius": "6px",
                        "padding": "9px 14px", "marginLeft": "6px",
                        "fontSize": "12px", "cursor": "pointer",
                    }),
                ], style={"display": "flex", "marginTop": "10px", "alignItems": "center"}),
            ], style={"flex": "1", "padding": "16px 20px", "minWidth": "0"}),
        ], style={
            "display": "flex",
            "backgroundColor": CLR["card"],
            "borderRadius": "10px",
            "border": f"1px solid {CLR['border']}",
            "maxWidth": "1060px",
        }),
    ], style={
        "backgroundColor": CLR["bg"],
        "minHeight": "100vh",
        "padding": "24px 32px",
        "fontFamily": "'Inter','Segoe UI',sans-serif",
        "color": CLR["text"],
    })


# ── Callbacks ─────────────────────────────────────────────────────────────────

@callback(
    Output("chat-context",    "data"),
    Output("chat-ctx-status", "children"),
    Input("chat-btn-load",    "n_clicks"),
    State("chat-dd-years",    "value"),
    prevent_initial_call=True,
)
def load_context(_, years):
    df  = load_multi(years or YEARS)
    ctx = build_context(df)
    n   = len(df)
    yrs = sorted(df["_year"].unique().tolist()) if not df.empty else []
    status = html.Div([
        html.Div(f"Dimuat: {n:,} baris"),
        html.Div(f"Periode: {', '.join(yrs)}"),
        html.Div("Konteks siap.", style={"color": CLR["success"], "fontWeight": "600"}),
    ])
    return ctx, status


@callback(
    Output("chat-messages", "children"),
    Output("chat-history",  "data"),
    Output("chat-input",    "value"),
    Input("chat-send",   "n_clicks"),
    Input("chat-input",  "n_submit"),
    State("chat-input",  "value"),
    State("chat-history","data"),
    State("chat-context","data"),
    prevent_initial_call=True,
)
def send_message(n_clicks, n_submit, user_msg, history, context):
    if not user_msg or not user_msg.strip():
        return no_update, no_update, no_update

    history  = history or []
    user_msg = user_msg.strip()

    api_msgs = [{"role": m["role"], "content": m["content"]} for m in history]
    api_msgs.append({"role": "user", "content": user_msg})

    if context:
        reply = call_claude(api_msgs, context)
        if reply is None:
            # No API key — use rule-based
            reply = _FALLBACK_BOT.respond(user_msg, pd.DataFrame())
    else:
        reply = (
            "_Konteks belum dimuat. Klik **Muat Konteks** terlebih dahulu._\n\n"
            + _FALLBACK_BOT.respond(user_msg, pd.DataFrame())
        )

    history.append({"role": "user",      "content": user_msg})
    history.append({"role": "assistant", "content": reply})
    return _render_bubbles(history), history, ""


@callback(
    Output("chat-messages", "children", allow_duplicate=True),
    Output("chat-history",  "data",     allow_duplicate=True),
    Input("chat-clear", "n_clicks"),
    prevent_initial_call=True,
)
def clear_chat(_):
    return [html.Div("Percakapan dibersihkan.", style={"color": CLR["muted"]})], []


def _render_bubbles(history: list[dict]) -> list:
    bubbles = []
    for msg in history:
        is_user = msg["role"] == "user"
        bubbles.append(html.Div([
            html.Span(
                "Anda: " if is_user else "Asisten: ",
                style={"fontWeight": "700",
                       "color": CLR["accent"] if is_user else CLR["success"]},
            ),
            html.Span(msg["content"]),
        ], style={
            "backgroundColor": CLR["surface"] if is_user else CLR["card"],
            "padding": "8px 12px",
            "borderRadius": "6px",
            "marginBottom": "8px",
            "borderLeft": f"3px solid {CLR['accent'] if is_user else CLR['success']}",
            "whiteSpace": "pre-wrap",
            "wordBreak": "break-word",
        }))
    return bubbles
