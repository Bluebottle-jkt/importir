"""
utils/chatbot.py
Rule-based chatbot + shared Claude AI helpers for SR15 Dashboard.

Exports:
  RuleBasedChatbot  — expanded intent matching
  build_context(df) — anonymised context string for AI prompt
  call_claude(messages, context) -> str | None
"""

from __future__ import annotations

import logging
import os
import re
from abc import ABC, abstractmethod

import pandas as pd

logger = logging.getLogger(__name__)

# ── Optional anthropic import ─────────────────────────────────────────────────

_HAS_ANTHROPIC = False
try:
    import anthropic as _anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    pass

CLAUDE_MODEL = "claude-sonnet-4-5"

# ── Abstract interface ────────────────────────────────────────────────────────

class ChatbotInterface(ABC):
    @abstractmethod
    def respond(self, message: str, df: pd.DataFrame) -> str:
        ...


# ── Context builder (anonymised, safe for API) ────────────────────────────────

def build_context(df: pd.DataFrame) -> str:
    """Build anonymised dataset context. No individual NPWP identifiers sent."""
    if df.empty:
        return "Dataset kosong - tidak ada data untuk dianalisis."

    npwp_is_count = df["_npwp_is_count"].any() if "_npwp_is_count" in df.columns else True
    n_rows  = len(df)
    n_npwp  = int(df["NPWP"].sum() if npwp_is_count else df["NPWP"].nunique()) \
              if "NPWP" in df.columns else 0
    n_hs4   = df["HS4"].nunique()      if "HS4"          in df.columns else 0
    ppn_tot = df["PPN_DIBAYAR"].sum()  if "PPN_DIBAYAR"  in df.columns else 0
    pph_tot = df["PPH_DIBAYAR"].sum()  if "PPH_DIBAYAR"  in df.columns else 0
    years   = sorted(df["_year"].unique().tolist()) if "_year" in df.columns else []

    def rp(v: float) -> str:
        if abs(v) >= 1e12: return f"Rp {v/1e12:.3f} T"
        if abs(v) >= 1e9:  return f"Rp {v/1e9:.2f} M"
        return f"Rp {v:,.0f}"

    lines = [
        "=== KONTEKS DATASET SR15 (ANONIM) ===",
        f"Periode      : {', '.join(years) if years else 'N/A'}",
        f"Total baris  : {n_rows:,}",
        f"{'NPWP (jumlah agregat)' if npwp_is_count else 'NPWP unik'}: {n_npwp:,}",
        f"HS4 unik     : {n_hs4:,}",
        f"Total PPN    : {rp(ppn_tot)}",
        f"Total PPH    : {rp(pph_tot)}",
    ]
    if ppn_tot > 0:
        lines.append(f"Rasio PPH/PPN: {pph_tot/ppn_tot:.4f}")

    if "HS4" in df.columns and "PPN_DIBAYAR" in df.columns:
        top = df.groupby("HS4")["PPN_DIBAYAR"].sum().nlargest(5)
        lines.append("Top 5 HS4    : " +
                     ", ".join(f"HS{k}({rp(v)})" for k, v in top.items()))

    if "NM_KELOMPOK" in df.columns and "PPN_DIBAYAR" in df.columns:
        top = df.groupby("NM_KELOMPOK")["PPN_DIBAYAR"].sum().nlargest(5)
        lines.append("Top 5 Kelompok: " +
                     ", ".join(f"{k[:20]}({rp(v)})" for k, v in top.items()))

    if "NM_KLU" in df.columns and "PPN_DIBAYAR" in df.columns:
        top = df.groupby("NM_KLU")["PPN_DIBAYAR"].sum().nlargest(5)
        lines.append("Top 5 KLU    : " +
                     ", ".join(f"{k[:20]}({rp(v)})" for k, v in top.items()))

    if all(c in df.columns for c in ["HS4", "PPN_DIBAYAR", "PPH_DIBAYAR"]):
        agg = df.groupby("HS4").agg(ppn=("PPN_DIBAYAR","sum"), pph=("PPH_DIBAYAR","sum"))
        agg = agg[agg["ppn"] > 0].copy()
        agg["r"] = agg["pph"] / agg["ppn"]
        lines.append(f"HS4 rasio PPH/PPN < 0.05: {int((agg['r'] < 0.05).sum()):,}")

    lines.append("=== AKHIR KONTEKS ===")
    return "\n".join(lines)


# ── Claude API call ───────────────────────────────────────────────────────────

_SYS = """\
Kamu adalah asisten analitik untuk Tim Compliance Risk Management (SR15) \
Direktorat Jenderal Pajak Indonesia.

Tugasmu: membantu menganalisis data Pemberitahuan Impor Barang (PIB) \
berdasarkan HS Code, KLU, dan KPP.

Konteks dataset saat ini (anonim — TANPA NPWP individual):
{context}

Panduan:
- Jawab pertanyaan bebas tentang pola risiko, tren, distribusi, regulasi pajak impor.
- Jangan menyebutkan atau membuat-buat NPWP atau identitas wajib pajak.
- Fokus: mismatch PPH/PPN, dispersi KLU, konsentrasi importir, potensi API-P Abuse.
- Jawab dalam Bahasa Indonesia kecuali pengguna menggunakan Bahasa Inggris.
- Berikan jawaban yang ringkas, informatif, dan langsung ke inti pertanyaan.
- Kamu bisa menjawab pertanyaan umum tentang perpajakan impor, HS Code, dan analitik risiko.
"""


def call_claude(messages: list[dict], context: str) -> str | None:
    """
    Call Claude API. Returns reply string, or None if unavailable.
    messages: [{"role": "user"|"assistant", "content": "..."}]
    Returns None if API key not set or anthropic not installed.
    Returns error string if API call fails.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key or not _HAS_ANTHROPIC:
        return None

    try:
        client = _anthropic.Anthropic(api_key=api_key)
        resp   = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=_SYS.format(context=context),
            messages=messages,
        )
        return resp.content[0].text
    except _anthropic.AuthenticationError:
        logger.warning("[CHATBOT] Claude auth error")
        return "_Error: API key tidak valid._"
    except _anthropic.RateLimitError:
        return "_Error: Rate limit. Coba lagi beberapa saat._"
    except Exception as exc:
        logger.error("[CHATBOT] Claude error: %s", exc)
        return f"_Error API: {str(exc)[:150]}_"


def claude_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()) and _HAS_ANTHROPIC


# ── Rule-based helpers ────────────────────────────────────────────────────────

def _fmt_rp(v: float) -> str:
    if abs(v) >= 1e12: return f"Rp {v/1e12:.2f} T"
    if abs(v) >= 1e9:  return f"Rp {v/1e9:.2f} M"
    return f"Rp {v:,.0f}"


def _top_npwp(df: pd.DataFrame, metric: str, n: int = 10) -> str:
    if df.empty or metric not in df.columns or "NPWP" not in df.columns:
        return "_Tidak ada data._"
    if df["_npwp_is_count"].any():
        return "_Data ini menggunakan format agregat, tidak bisa menampilkan per-NPWP._"
    agg = df.groupby("NPWP")[metric].sum().sort_values(ascending=False).head(n)
    lines = [f"**Top {n} NPWP berdasarkan {metric}:**\n"]
    for i, (npwp, val) in enumerate(agg.items(), 1):
        lines.append(f"{i}. `{npwp}` — {_fmt_rp(val)}")
    return "\n".join(lines)


def _top_hs4(df: pd.DataFrame, n: int = 10) -> str:
    if df.empty or "HS4" not in df.columns:
        return "_Tidak ada data._"
    agg = df.groupby("HS4")["PPN_DIBAYAR"].sum().sort_values(ascending=False).head(n)
    lines = [f"**Top {n} HS-4 berdasarkan PPN:**\n"]
    for i, (hs4, val) in enumerate(agg.items(), 1):
        nm = df[df["HS4"] == hs4]["NM_DETIL"].mode()
        label = nm.iloc[0][:40] if len(nm) else ""
        lines.append(f"{i}. HS4 `{hs4}` {label} — {_fmt_rp(val)}")
    return "\n".join(lines)


def _top_group(df: pd.DataFrame, col: str, label: str, n: int = 10) -> str:
    if df.empty or col not in df.columns:
        return f"_Kolom {col} tidak tersedia._"
    agg = (
        df.groupby(col)
          .agg(ppn=("PPN_DIBAYAR","sum"), pph=("PPH_DIBAYAR","sum"))
          .sort_values("ppn", ascending=False)
          .head(n)
          .reset_index()
    )
    lines = [f"**Top {n} {label} berdasarkan PPN:**\n"]
    for _, row in agg.iterrows():
        lines.append(
            f"- `{str(row[col])[:40]}` — PPN {_fmt_rp(row['ppn'])}, "
            f"PPH {_fmt_rp(row['pph'])}"
        )
    return "\n".join(lines)


def _mismatch(df: pd.DataFrame) -> str:
    if df.empty or "PPN_DIBAYAR" not in df.columns:
        return "_Tidak ada data._"
    agg = (
        df.groupby("HS4")
          .agg(ppn=("PPN_DIBAYAR","sum"), pph=("PPH_DIBAYAR","sum"))
          .reset_index()
    )
    agg = agg[agg["ppn"] > 0].copy()
    agg["ratio"] = agg["pph"] / agg["ppn"]
    low = agg[agg["ratio"] < 0.05].sort_values("ppn", ascending=False).head(10)
    if low.empty:
        return "_Tidak ditemukan mismatch PPH/PPN (rasio < 0.05)._"
    lines = ["**HS4 rasio PPH/PPN < 0.05 (potensi API-P Abuse):**\n"]
    for _, row in low.iterrows():
        lines.append(
            f"- HS4 `{row['HS4']}` — PPN {_fmt_rp(row['ppn'])}, "
            f"PPH {_fmt_rp(row['pph'])}, rasio **{row['ratio']:.4f}**"
        )
    return "\n".join(lines)


def _compare_years(df: pd.DataFrame) -> str:
    if df.empty or "_year" not in df.columns:
        return "_Tidak ada data._"
    agg = (
        df.groupby("_year")
          .agg(ppn=("PPN_DIBAYAR","sum"), pph=("PPH_DIBAYAR","sum"), pib=("jml_pib","sum"))
          .reset_index()
          .sort_values("_year")
    )
    lines = ["**Perbandingan per Tahun:**\n",
             "| Tahun | PPN | PPH | PIB |",
             "|-------|-----|-----|-----|"]
    for _, row in agg.iterrows():
        lines.append(
            f"| {row['_year']} | {_fmt_rp(row['ppn'])} | "
            f"{_fmt_rp(row['pph'])} | {int(row['pib']):,} |"
        )
    return "\n".join(lines)


def _kpp_summary(df: pd.DataFrame) -> str:
    if df.empty or "KPP_CODE_3" not in df.columns:
        return "_Tidak ada data._"
    if df["_npwp_is_count"].any():
        return "_Data T1 tidak memiliki NPWP individual, KPP tidak tersedia._"
    agg = (
        df.groupby("KPP_CODE_3")["PPN_DIBAYAR"].sum()
          .sort_values(ascending=False)
          .head(10)
    )
    lines = ["**Top 10 KPP berdasarkan PPN:**\n"]
    for i, (kpp, val) in enumerate(agg.items(), 1):
        lines.append(f"{i}. KPP `{kpp}` — {_fmt_rp(val)}")
    return "\n".join(lines)


def _summary(df: pd.DataFrame) -> str:
    if df.empty:
        return "_Dataset kosong._"
    npwp_is_count = df["_npwp_is_count"].any()
    n_npwp = int(df["NPWP"].sum() if npwp_is_count else df["NPWP"].nunique())
    lines = [
        "**Ringkasan Dataset:**\n",
        f"- Baris data : **{len(df):,}**",
        f"- {'Total NPWP (agregat)' if npwp_is_count else 'NPWP unik'}: **{n_npwp:,}**",
        f"- HS4 unik   : **{df['HS4'].nunique():,}**",
        f"- Total PPN  : **{_fmt_rp(df['PPN_DIBAYAR'].sum())}**",
        f"- Total PPH  : **{_fmt_rp(df['PPH_DIBAYAR'].sum())}**",
        f"- Total PIB  : **{int(df['jml_pib'].sum()):,}**",
    ]
    if "_year" in df.columns:
        yrs = sorted(df["_year"].unique())
        lines.append(f"- Periode    : **{', '.join(yrs)}**")
    if "PPN_DIBAYAR" in df.columns and df["PPN_DIBAYAR"].sum() > 0:
        ratio = df["PPH_DIBAYAR"].sum() / df["PPN_DIBAYAR"].sum()
        lines.append(f"- Rasio PPH/PPN: **{ratio:.4f}**")
    return "\n".join(lines)


def _pib_info(df: pd.DataFrame) -> str:
    if df.empty:
        return "_Tidak ada data._"
    total_pib = int(df["jml_pib"].sum()) if "jml_pib" in df.columns else 0
    total_det = int(df["jml_detail_pib"].sum()) if "jml_detail_pib" in df.columns else 0
    lines = [
        "**Informasi PIB:**\n",
        f"- Total dokumen PIB    : **{total_pib:,}**",
        f"- Total detail PIB     : **{total_det:,}**",
    ]
    if "_year" in df.columns:
        per_year = df.groupby("_year")["jml_pib"].sum().sort_index()
        for yr, val in per_year.items():
            lines.append(f"  - {yr}: **{int(val):,}**")
    return "\n".join(lines)


_HELP_TEXT = """**Pertanyaan / Perintah yang Didukung:**

**Analisis Nilai:**
- `top hs4` / `hs code terbesar` — top HS-4 berdasarkan PPN
- `top kelompok` — top kelompok impor
- `top klu` — top Klasifikasi Lapangan Usaha
- `top kpp` — distribusi PPN per KPP
- `top npwp ppn` / `top npwp pph` — top importir (data individu)

**Risiko & Kepatuhan:**
- `mismatch` / `rasio rendah` / `api-p` — HS4 dengan PPH/PPN rendah
- `risiko` / `potensi` — identifikasi potensi ketidakpatuhan

**Tren & Ringkasan:**
- `bandingkan tahun` / `tren` — perbandingan antar periode
- `summary` / `ringkasan` / `total` — ringkasan dataset
- `pib` / `dokumen` — informasi jumlah PIB

**Pertanyaan Bebas:** ketik pertanyaan dalam bahasa alami (mis: "HS code apa yang paling banyak mismatch?")

> Untuk analisis mendalam dengan Claude AI, gunakan halaman **/chatbot**"""


class RuleBasedChatbot(ChatbotInterface):
    """
    Expanded intent matching. Handles free-form questions with contextual fallback.
    """

    _INTENTS = [
        # NPWP
        (r"top\s*npwp\s*(ppn|pvp|pv|pajak\s*pertambahan)",  "top_npwp_ppn"),
        (r"top\s*npwp\s*(pph|poh|ph|pajak\s*penghasilan)",   "top_npwp_pph"),
        (r"importir\s*terbesar",                              "top_npwp_ppn"),
        # HS
        (r"top\s*hs|hs\s*code\s*terbesar|hs\s*terbesar|komoditas\s*terbesar", "top_hs4"),
        (r"ppn\s*(ter)?tinggi|ppn\s*terbesar|paling\s*besar\s*ppn",           "top_hs4"),
        # Groups
        (r"top\s*kel(ompok)?|kelompok\s*terbesar",           "top_kelompok"),
        (r"top\s*klu|klu\s*terbesar|sektor\s*terbesar",      "top_klu"),
        (r"top\s*sub(gol)?|subgolongan\s*terbesar",          "top_subgol"),
        # Risk
        (r"mismatch|api.?p|abuse|rasio\s*rendah|rasio\s*rendah", "mismatch"),
        (r"risiko|potensi|ketidakpatuhan|fraud",              "mismatch"),
        (r"pph\s*(ter)?rendah|pph\s*kecil",                  "mismatch"),
        # Time
        (r"bandingt?|compare|bandingkan|tren|trend",          "compare_years"),
        (r"(per\s*)?tahun|periode|year|waktu",                "compare_years"),
        # KPP
        (r"kpp|kantor\s*pelayanan",                           "kpp"),
        # Summary
        (r"summar|ringkas|overview|rekapitulasi",             "summary"),
        (r"total\s*(ppn|pph|pib|data|baris|npwp)",           "summary"),
        (r"berapa\s*(total|jumlah|banyak)|jumlah\s*total",    "summary"),
        (r"dataset|data\s*saat\s*ini|kondisi\s*data",         "summary"),
        # PIB
        (r"pib|dokumen\s*pib|pemberitahuan\s*impor",          "pib_info"),
        # Help
        (r"help|bantuan|panduan|\?$",                         "help"),
    ]

    def respond(self, message: str, df: pd.DataFrame) -> str:
        msg = message.lower().strip()
        if not msg:
            return "_Ketik `help` untuk melihat panduan._"

        for pattern, intent in self._INTENTS:
            if re.search(pattern, msg):
                return self._dispatch(intent, df)

        return self._contextual_fallback(message, df)

    def _dispatch(self, intent: str, df: pd.DataFrame) -> str:
        dispatch_map = {
            "top_npwp_ppn":  lambda: _top_npwp(df, "PPN_DIBAYAR"),
            "top_npwp_pph":  lambda: _top_npwp(df, "PPH_DIBAYAR"),
            "top_hs4":       lambda: _top_hs4(df),
            "top_kelompok":  lambda: _top_group(df, "NM_KELOMPOK", "Kelompok"),
            "top_klu":       lambda: _top_group(df, "NM_KLU", "KLU"),
            "top_subgol":    lambda: _top_group(df, "NM_SUBGOL", "Subgolongan"),
            "mismatch":      lambda: _mismatch(df),
            "compare_years": lambda: _compare_years(df),
            "kpp":           lambda: _kpp_summary(df),
            "summary":       lambda: _summary(df),
            "pib_info":      lambda: _pib_info(df),
            "help":          lambda: _HELP_TEXT,
        }
        fn = dispatch_map.get(intent)
        return fn() if fn else _HELP_TEXT

    def _contextual_fallback(self, message: str, df: pd.DataFrame) -> str:
        msg = message.lower()

        # Specific HS4 code lookup
        hs_match = re.search(r'\b(\d{4,8})\b', message)
        if hs_match and "HS4" in df.columns:
            code = hs_match.group(1)[:4]
            sub = df[df["HS4"] == code]
            if not sub.empty:
                ppn = sub["PPN_DIBAYAR"].sum()
                pph = sub["PPH_DIBAYAR"].sum()
                pib = int(sub["jml_pib"].sum())
                nm  = sub["NM_DETIL"].mode()
                label = nm.iloc[0][:60] if len(nm) else ""
                ratio = pph/ppn if ppn > 0 else 0
                return (
                    f"**HS4 `{code}` — {label}**\n\n"
                    f"- PPN       : {_fmt_rp(ppn)}\n"
                    f"- PPH       : {_fmt_rp(pph)}\n"
                    f"- PIB       : {pib:,}\n"
                    f"- Rasio PPH/PPN: {ratio:.4f}"
                    + (" ⚠️ rendah" if ratio < 0.05 else "")
                )

        # Natural language PPN/PPH questions
        if any(w in msg for w in ["tertinggi","terbesar","terbanyak","paling besar"]):
            if "pph" in msg:
                return _top_npwp(df, "PPH_DIBAYAR")
            if "ppn" in msg or "pajak" in msg:
                return _top_hs4(df)

        # Distribution questions
        if any(w in msg for w in ["distribusi","sebaran","komposisi"]):
            if "klu" in msg:
                return _top_group(df, "NM_KLU", "KLU")
            if "kelompok" in msg:
                return _top_group(df, "NM_KELOMPOK", "Kelompok")
            return _summary(df)

        return (
            f"_Pertanyaan tidak dikenali: **{message[:60]}**_\n\n"
            + _HELP_TEXT
        )
