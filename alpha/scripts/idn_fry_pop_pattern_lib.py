"""Live fry pop scoring from multi-year trigger + huge-winner pattern catalog."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
FRY_DIR = REPO / "data_lake/research_panels/idn_fry_episode"

from idn_fry_trigger_anatomy_lib import classify_trigger_cause
from idn_winner_pattern_lib import load_cross_section, pattern_matches_row


def load_fry_pop_catalog() -> dict[str, Any]:
    path = FRY_DIR / "fry_pop_pattern_catalog.json"
    if not path.exists():
        return {}
    import json

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _row_dict(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    return {k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()}


def _composite_match(pattern: str, row: dict[str, Any]) -> bool:
    if pattern == "drawdown_vol_spike":
        vol = row.get("vol_ratio_20d")
        r5 = row.get("return_5d")
        return (
            vol is not None
            and r5 is not None
            and np.isfinite(vol)
            and np.isfinite(r5)
            and float(vol) >= 1.6
            and float(r5) <= -0.04
        )
    if pattern == "deep_dd_vol_spike":
        vol = row.get("vol_ratio_20d")
        r5 = row.get("return_5d")
        return (
            vol is not None
            and r5 is not None
            and np.isfinite(vol)
            and np.isfinite(r5)
            and float(vol) >= 1.6
            and float(r5) <= -0.12
        )
    if pattern.startswith("trigger_cause="):
        cause = pattern.split("=", 1)[1]
        return classify_trigger_cause(pd.Series(row)) == cause
    return pattern_matches_row(pattern, row)


def score_fry_pop_row(row: dict[str, Any], catalog: dict[str, Any] | None = None) -> tuple[float, list[str], str]:
    """Return pop_score, matched_patterns, trigger_cause for one fry symbol-day."""
    cat = catalog or load_fry_pop_catalog()
    patterns = cat.get("scoring_patterns") or []
    rd = _row_dict(row)
    if rd.get("name_type") != "fry":
        return 0.0, [], "not_fry"

    r1 = rd.get("return_1d")
    if r1 is not None and np.isfinite(r1) and float(r1) >= 0.08:
        return 0.0, [], "already_popped"

    matched: list[str] = []
    score = 0.0
    for p in patterns:
        pat = str(p["pattern"])
        if _composite_match(pat, rd):
            matched.append(pat)
            score += float(p.get("weight") or math.log(max(p.get("pop_lift") or p.get("oos_lift") or 1.01, 1.01)))

    cause = classify_trigger_cause(pd.Series(rd))
    if not matched and cause in ("drawdown_vol_spike", "quiet_accumulation", "both_quiet_and_vol_dd"):
        score += 0.3 if cause == "drawdown_vol_spike" else 0.1

    return round(score, 4), matched, cause


def pop_probability_tier(score: float, *, matched: list[str]) -> str:
    if score >= 2.0 or "deep_dd_vol_spike" in matched:
        return "high"
    if score >= 1.2 or "drawdown_vol_spike" in matched:
        return "elevated"
    if score >= 0.5:
        return "monitor"
    return "low"


def rank_fry_pop_candidates(
    close: pd.DataFrame,
    vol: pd.DataFrame,
    as_of: pd.Timestamp | str,
    symbols: list[str] | None = None,
    *,
    max_n: int = 30,
    catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Rank fry names by multi-year pop pattern score on as_of."""
    as_of = pd.Timestamp(as_of)
    cat = catalog or load_fry_pop_catalog()
    sym_list = symbols or list(close.columns)
    snap = load_cross_section(as_of, sym_list, close, vol)
    if snap.empty:
        return []

    ranked: list[dict[str, Any]] = []
    for _, row in snap.iterrows():
        rd = _row_dict(row)
        if rd.get("name_type") != "fry":
            continue
        score, matched, cause = score_fry_pop_row(rd, cat)
        if score <= 0 and cause == "other":
            continue
        r5 = rd.get("return_5d")
        vol_r = rd.get("vol_ratio_20d")
        ranked.append(
            {
                "yahoo_symbol": str(rd["yahoo_symbol"]),
                "pop_score": score,
                "pop_tier": pop_probability_tier(score, matched=matched),
                "trigger_cause": cause,
                "matched_patterns": matched,
                "return_5d_pct": round(float(r5) * 100, 2) if r5 is not None and np.isfinite(r5) else None,
                "vol_ratio_20d": round(float(vol_r), 2) if vol_r is not None and np.isfinite(vol_r) else None,
                "dd_60d_pct": round(float(rd.get("dd_60d", 0)) * 100, 1) if rd.get("dd_60d") is not None else None,
                "bandar_lite_label": rd.get("bandar_lite_label"),
                "ihsg_regime": rd.get("ihsg_regime"),
            }
        )

    ranked.sort(key=lambda x: (-x["pop_score"], x["yahoo_symbol"]))
    return ranked[:max_n]


def fry_pop_monitor_payload(
    close: pd.DataFrame,
    vol: pd.DataFrame,
    as_of: pd.Timestamp | str,
    symbols: list[str] | None = None,
    *,
    max_n: int = 20,
) -> list[dict[str, Any]]:
    """Watchlist rows compatible with position sheet fry_watch_only."""
    ranked = rank_fry_pop_candidates(close, vol, as_of, symbols, max_n=max_n)
    out: list[dict[str, Any]] = []
    for r in ranked:
        if r["pop_tier"] == "low":
            continue
        out.append(
            {
                "yahoo_symbol": r["yahoo_symbol"],
                "tier": r["pop_tier"],
                "return_5d_pct": r.get("return_5d_pct"),
                "vol_ratio_20d": r.get("vol_ratio_20d"),
                "score": int(min(100, round(r["pop_score"] * 35))),
                "trigger_cause": r["trigger_cause"],
                "matched_patterns": r.get("matched_patterns", [])[:4],
                "note": "pop_pattern_monitor — wait ARA day, 0% weight",
            }
        )
    return out
