"""
utils/data.py
Shared raw-data loader for SR15 Enhanced Dashboard.

Raw files (input/):
  2022-2024: NPWP (individual), KD_KLU, THN_PAJAK, POS_TARIF_HS,
             jml_pib, jml_detail_pib, PPN_DIBAYAR, PPH_DIBAYAR,
             KD_KELOMPOK, NM_KELOMPOK, KD_DETIL, NM_DETIL, NM_KLU, NM_SUBGOL
  T1       : jml_npwp (count) instead of NPWP — same other columns

Derived columns added at load time:
  HS4         = str(int(POS_TARIF_HS))[:4]
  KPP_CODE_3  = NPWP.zfill(15)[9:12]  (N/A for T1 count format)
  _year       = year tag
  _npwp_is_count = bool flag
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from typing import Any

import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(BASE_DIR, "input")

_FILE_MAP: dict[str, str] = {
    "2022": "CRM_LEVEL5_SR15_2026_EKSPLORASI_POPULASI_PIB_DETAIL_RESUME_PER_WP_2022.xlsx",
    "2023": "CRM_LEVEL5_SR15_2026_EKSPLORASI_POPULASI_PIB_DETAIL_RESUME_PER_WP_2023.xlsx",
    "2024": "CRM_LEVEL5_SR15_2026_EKSPLORASI_POPULASI_PIB_DETAIL_RESUME_PER_WP_2024.xlsx",
    "T1":   "CRM_LEVEL5_SR15_2026_EKSPLORASI_POPULASI_PIB_DETAIL_RESUME_T1.xlsx",
}

YEARS = list(_FILE_MAP.keys())

_NUM_COLS = [
    "POS_TARIF_HS", "jml_pib", "jml_detail_pib",
    "PPN_DIBAYAR",  "PPH_DIBAYAR",
]

# ── Raw loader ────────────────────────────────────────────────────────────────

_RAW_CACHE: dict[str, pd.DataFrame] = {}
_YEAR_LOCKS: dict[str, threading.Lock] = {year: threading.Lock() for year in _FILE_MAP}
_MULTI_CACHE: "OrderedDict[tuple[str, ...], pd.DataFrame]" = OrderedDict()
_MULTI_CACHE_MAX = 3
_FILTER_CACHE: "OrderedDict[tuple, pd.DataFrame]" = OrderedDict()
_FILTER_CACHE_MAX = 12
_FILTER_LOCK = threading.Lock()


def _detect_sheet(xl: pd.ExcelFile) -> str:
    for sh in xl.sheet_names:
        if "POS_TARIF_HS" in xl.parse(sh, header=0, nrows=0).columns.tolist():
            return sh
    return xl.sheet_names[0]


def load_raw(year: str) -> pd.DataFrame:
    """Load and normalise raw input file for *year*. Thread-safe: only one load per year."""
    if year in _RAW_CACHE:
        return _RAW_CACHE[year]

    with _YEAR_LOCKS.get(year, threading.Lock()):
        # Double-check after acquiring lock (another thread may have loaded it)
        if year in _RAW_CACHE:
            return _RAW_CACHE[year]

        fname = _FILE_MAP.get(year)
        if not fname:
            _RAW_CACHE[year] = pd.DataFrame()
            return _RAW_CACHE[year]

        path = os.path.join(INPUT_DIR, fname)
        if not os.path.exists(path):
            _RAW_CACHE[year] = pd.DataFrame()
            return _RAW_CACHE[year]

        xl    = pd.ExcelFile(path)
        sheet = _detect_sheet(xl)
        df    = xl.parse(sheet, header=0)

        # Drop unnamed index column
        df = df.loc[:, ~df.columns.str.startswith("Unnamed")]

        # Normalise NPWP
        if "jml_npwp" in df.columns and "NPWP" not in df.columns:
            df["NPWP"]           = df["jml_npwp"].fillna(0).astype(int)
            df["_npwp_is_count"] = True
        else:
            df["NPWP"]           = df["NPWP"].astype(str).str.strip()
            df["_npwp_is_count"] = False

        # Numeric coercion
        for col in _NUM_COLS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # Derive HS4
        df["HS4"] = df["POS_TARIF_HS"].apply(
            lambda v: str(int(v))[:4] if v and v > 0 else "0000"
        )

        # Derive Chapter (int) and Cluster (string) — computed once at load time
        def _to_chapter(hs4_str: str):
            digits = "".join(c for c in str(hs4_str) if c.isdigit())
            return int(digits[:2]) if len(digits) >= 2 else None

        def _to_cluster(ch) -> str:
            if ch is None:
                return "Lainnya"
            ch = int(ch)
            if ch == 85:              return "Elektronik"
            if ch == 87:              return "Otomotif"
            if 28 <= ch <= 38:        return "Kimia/Farmasi"
            if 10 <= ch <= 11:        return "Pangan"
            return "Lainnya"

        df["Chapter"] = df["HS4"].apply(_to_chapter)
        df["Cluster"] = df["Chapter"].apply(_to_cluster)

        # Derive KPP_CODE_3
        if not df["_npwp_is_count"].any():
            df["KPP_CODE_3"] = df["NPWP"].str.zfill(15).str[9:12]
        else:
            df["KPP_CODE_3"] = "N/A"

        df["_year"] = year

        # String cleanup — empty/NaN → "(Tidak Terkategori)"
        _STR_COLS = ["NM_KLU","NM_KELOMPOK","NM_DETIL","NM_SUBGOL",
                     "KD_KELOMPOK","KD_DETIL","KD_KLU"]
        for col in _STR_COLS:
            if col in df.columns:
                df[col] = (
                    df[col]
                    .fillna("(Tidak Terkategori)")
                    .astype(str)
                    .str.strip()
                    .replace("", "(Tidak Terkategori)")
                )

        # ── Convert to Categorical — 5-10× faster isin/groupby/nunique ──────────
        _CAT_COLS = ["NM_KLU","NM_KELOMPOK","NM_DETIL","NM_SUBGOL",
                     "KD_KELOMPOK","KD_DETIL","KD_KLU",
                     "HS4","KPP_CODE_3","_year","Cluster"]
        for col in _CAT_COLS:
            if col in df.columns:
                df[col] = df[col].astype("category")

        # Convert NPWP to category for faster nunique in groupby
        if not df["_npwp_is_count"].any():
            df["NPWP"] = df["NPWP"].astype("category")

        _RAW_CACHE[year] = df
    return df


def load_multi(years: list[str]) -> pd.DataFrame:
    """Concatenate raw frames for multiple years (small LRU cache)."""
    years = list(years or [])
    key = tuple(years)
    if key in _MULTI_CACHE:
        _MULTI_CACHE.move_to_end(key)
        return _MULTI_CACHE[key]

    frames: list[pd.DataFrame] = []
    for y in years:
        df = load_raw(y)
        if not df.empty:
            frames.append(df)

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    _MULTI_CACHE[key] = out
    if len(_MULTI_CACHE) > _MULTI_CACHE_MAX:
        _MULTI_CACHE.popitem(last=False)
    return out


# ── apply_filters ─────────────────────────────────────────────────────────────

def apply_filters(df: pd.DataFrame, state: dict[str, Any]) -> pd.DataFrame:
    """
    Centralised filter.  All state keys are optional.

    state keys:
        pph_range   : [min, max] in rupiah
        ppn_range   : [min, max] in rupiah          ← NEW in v1.1.0
        nm_klu      : list[str]  — exact matches (multi-select); empty = no filter
        nm_kelompok : list[str]  — exact matches (multi-select); empty = no filter
        kd_kelompok : list[str]
        kd_detil    : list[str]
        nm_subgol   : list[str]
        kpp         : list[str]   "ALL" or KPP_CODE_3 values
        hs4         : list[str]
        kd_klu      : list[str]
    """
    if df.empty:
        return df

    m = pd.Series(True, index=df.index)

    # ── PPH range ──────────────────────────────────────────────────────────────
    pph_range = state.get("pph_range")
    if pph_range and len(pph_range) == 2 and "PPH_DIBAYAR" in df.columns:
        lo, hi = float(pph_range[0]), float(pph_range[1])
        if lo > 0 or hi < 5e9:          # skip if full range (0 → 5B)
            m &= df["PPH_DIBAYAR"].between(lo, hi)

    # ── PPN range ──────────────────────────────────────────────────────────────
    ppn_range = state.get("ppn_range")
    if ppn_range and len(ppn_range) == 2 and "PPN_DIBAYAR" in df.columns:
        lo, hi = float(ppn_range[0]), float(ppn_range[1])
        if lo > 0 or hi < 1e10:         # skip if full range (0 → 10B)
            m &= df["PPN_DIBAYAR"].between(lo, hi)

    # ── NM_KLU (list — multi-select) ──────────────────────────────────────────
    nm_klu = state.get("nm_klu")
    if nm_klu and "NM_KLU" in df.columns:
        if isinstance(nm_klu, str):
            # Legacy text-contains support (backward compat)
            m &= df["NM_KLU"].str.contains(nm_klu, case=False, na=False, regex=False)
        elif nm_klu:  # non-empty list
            m &= df["NM_KLU"].isin(nm_klu)

    # ── NM_KELOMPOK (list — multi-select) ─────────────────────────────────────
    nm_kelompok = state.get("nm_kelompok")
    if nm_kelompok and "NM_KELOMPOK" in df.columns:
        if isinstance(nm_kelompok, str):
            m &= df["NM_KELOMPOK"].str.contains(nm_kelompok, case=False, na=False, regex=False)
        elif nm_kelompok:
            m &= df["NM_KELOMPOK"].isin(nm_kelompok)

    # ── Discrete multi-selects ─────────────────────────────────────────────────
    for state_key, col_name in [("kd_kelompok", "KD_KELOMPOK"),
                                 ("kd_detil",    "KD_DETIL"),
                                 ("nm_subgol",   "NM_SUBGOL")]:
        vals = state.get(state_key)
        if vals and col_name in df.columns:
            m &= df[col_name].isin(vals)

    # ── KPP ───────────────────────────────────────────────────────────────────
    kpp_vals = state.get("kpp")
    if kpp_vals and "ALL" not in kpp_vals and "KPP_CODE_3" in df.columns:
        m &= df["KPP_CODE_3"].isin(kpp_vals)

    # ── HS4 ───────────────────────────────────────────────────────────────────
    hs4_vals = state.get("hs4")
    if hs4_vals and "HS4" in df.columns:
        m &= df["HS4"].isin(hs4_vals)

    # ── KD_KLU ────────────────────────────────────────────────────────────────
    kd_klu_vals = state.get("kd_klu")
    if kd_klu_vals and "KD_KLU" in df.columns:
        m &= df["KD_KLU"].isin(kd_klu_vals)

    # If no rows were filtered out, return the original (callers are read-only)
    if m.all():
        return df
    # df[m] already produces a new DataFrame for boolean index — .copy() is redundant
    return df[m]


def apply_filters_cached(df: pd.DataFrame, state: dict[str, Any]) -> pd.DataFrame:
    """Cached wrapper for apply_filters — avoids re-filtering same data/state."""
    import hashlib, json as _json
    state_hash = hashlib.md5(
        _json.dumps(state, sort_keys=True, default=str).encode()
    ).hexdigest()
    key = (id(df), state_hash)
    with _FILTER_LOCK:
        if key in _FILTER_CACHE:
            _FILTER_CACHE.move_to_end(key)
            return _FILTER_CACHE[key]
    result = apply_filters(df, state)
    with _FILTER_LOCK:
        _FILTER_CACHE[key] = result
        if len(_FILTER_CACHE) > _FILTER_CACHE_MAX:
            _FILTER_CACHE.popitem(last=False)
    return result


# ── Aggregation helpers ───────────────────────────────────────────────────────

def agg_year_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-year KPI summary."""
    if df.empty:
        return pd.DataFrame()
    rows = []
    for yr, grp in df.groupby("_year", observed=True):
        npwp_is_count = grp["_npwp_is_count"].any()
        n_npwp = int(grp["NPWP"].sum() if npwp_is_count else grp["NPWP"].nunique())
        rows.append({
            "Tahun":      yr,
            "NPWP":       n_npwp,
            "PIB":        int(grp["jml_pib"].sum()),
            "PPN (Rp M)": grp["PPN_DIBAYAR"].sum() / 1e6,
            "PPH (Rp M)": grp["PPH_DIBAYAR"].sum() / 1e6,
        })
    return pd.DataFrame(rows)


def agg_by_group(df: pd.DataFrame, group_col: str, top_n: int = 20) -> pd.DataFrame:
    """Aggregate PPN/PPH/PIB/NPWP by a grouping column, return top_n by PPN."""
    if df.empty or group_col not in df.columns:
        return pd.DataFrame()
    npwp_is_count = df["_npwp_is_count"].any()
    agg_dict: dict = {
        "PPN_DIBAYAR": "sum",
        "PPH_DIBAYAR": "sum",
        "jml_pib":     "sum",
        "NPWP":        "sum" if npwp_is_count else "nunique",
    }
    return (
        df.groupby(group_col, observed=True)
          .agg(agg_dict)
          .reset_index()
          .sort_values("PPN_DIBAYAR", ascending=False)
          .head(top_n)
    )


_AGG_CACHE: "OrderedDict[tuple, pd.DataFrame]" = OrderedDict()
_AGG_CACHE_MAX = 24
_AGG_LOCK = threading.Lock()


def agg_by_group_cached(df: pd.DataFrame, group_col: str, top_n: int = 20) -> pd.DataFrame:
    """Cached wrapper — same filtered df + group_col + top_n returns instantly."""
    key = (id(df), group_col, top_n)
    with _AGG_LOCK:
        if key in _AGG_CACHE:
            _AGG_CACHE.move_to_end(key)
            return _AGG_CACHE[key]
    result = agg_by_group(df, group_col, top_n)
    with _AGG_LOCK:
        _AGG_CACHE[key] = result
        if len(_AGG_CACHE) > _AGG_CACHE_MAX:
            _AGG_CACHE.popitem(last=False)
    return result
