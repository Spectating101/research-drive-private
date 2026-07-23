"""Match tradable universe to OOS-stable winner patterns (not named tickers)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)

BIG_WINNER_JSON = REPO / "backtests/outputs/idn_big_winner_reverse/latest.json"
TURNAROUND_PANEL = REPO / "data_lake/research_panels/idn_turnaround/daily_features.parquet"

FRY_EVENT_FEATURES = frozenset(
    {
        "is_ara_day",
        "chase_score_5d",
    }
)
FRY_EVENT_LABELS = frozenset(
    {
        "chase_into_spike",
        "momentum_chase",
    }
)
RETAIL_TILT_HINTS = frozenset(
    {
        "dd_60d",
        "rsi14",
        "squeeze_from_drawdown",
        "quiet_volume_build",
        "ihsg_regime",
        "near_support",
        "return_5d",
        "vol_ratio_20d",
    }
)


@dataclass(frozen=True)
class PatternRule:
    pattern: str
    feature: str
    sleeve: str  # retail_tilt | fry_event | neutral
    oos_lift: float
    oos_mean_reward_20d_pct: float | None
    match: Callable[[dict[str, Any]], bool]


def _coerce(val: Any) -> Any:
    if isinstance(val, (bool, np.bool_)):
        return int(val)
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating, float)):
        if not np.isfinite(val):
            return None
        if float(val).is_integer():
            return int(val)
        return float(val)
    return val


def pattern_matches_row(pattern: str, row: dict[str, Any]) -> bool:
    """Evaluate a mined pattern string against one feature row."""
    if "==" in pattern:
        feat, raw = pattern.split("==", 1)
        got = _coerce(row.get(feat.strip()))
        want = _coerce(raw.strip())
        return got == want

    if ":x<" in pattern and "<=x<" not in pattern and ":x>=" not in pattern:
        feat, bound = pattern.split(":x<", 1)
        val = row.get(feat.strip())
        if val is None or (isinstance(val, float) and not np.isfinite(val)):
            return False
        return float(val) < float(bound)

    if ":x>=" in pattern:
        feat, bound = pattern.split(":x>=", 1)
        val = row.get(feat.strip())
        if val is None or (isinstance(val, float) and not np.isfinite(val)):
            return False
        return float(val) >= float(bound)

    m = re.match(r"^([^:]+):([^<]+)<=x<(.+)$", pattern)
    if m:
        feat, lo, hi = m.group(1), float(m.group(2)), float(m.group(3))
        val = row.get(feat)
        if val is None or (isinstance(val, float) and not np.isfinite(val)):
            return False
        v = float(val)
        return lo <= v < hi

    if "=" in pattern:
        feat, raw = pattern.split("=", 1)
        return str(row.get(feat.strip(), "")) == raw.strip()

    return False


def _classify_sleeve(pattern: str, feature: str, value: str) -> str:
    if feature == "name_type" and value == "fry":
        return "fry_event"
    if feature == "bandar_lite_label" and value in FRY_EVENT_LABELS:
        return "fry_event"
    if feature in FRY_EVENT_FEATURES:
        if "x>=" in pattern or "==1" in pattern:
            return "fry_event"
    if any(h in pattern for h in RETAIL_TILT_HINTS):
        if feature == "return_5d" and "x>=" in pattern:
            return "neutral"
        if feature == "pos_52w_range" and "x>=" in pattern:
            return "neutral"
        return "retail_tilt"
    if feature == "near_support_40d" and "==0" in pattern:
        return "neutral"
    if feature == "rsi14" and "x>=" in pattern:
        return "neutral"
    return "neutral"


def load_pattern_catalog(
    *,
    min_oos_lift: float = 1.15,
    sleeve: str | None = "retail_tilt",
    report: dict[str, Any] | None = None,
) -> list[PatternRule]:
    """Stable OOS patterns from big-winner reverse study."""
    if report is None:
        if not BIG_WINNER_JSON.exists():
            return []
        import json

        try:
            report = json.loads(BIG_WINNER_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    patterns = (report.get("patterns") or {}).get("ranked_stable") or []
    rules: list[PatternRule] = []
    for p in patterns:
        oos_lift = float(p.get("oos_lift") or 0.0)
        if oos_lift < min_oos_lift:
            continue
        pat = str(p["pattern"])
        feat = str(p.get("feature", ""))
        val = str(p.get("value", ""))
        sl = _classify_sleeve(pat, feat, val)
        if sleeve and sl != sleeve:
            continue
        rules.append(
            PatternRule(
                pattern=pat,
                feature=feat,
                sleeve=sl,
                oos_lift=oos_lift,
                oos_mean_reward_20d_pct=p.get("oos_mean_reward_20d_pct"),
                match=lambda row, _pat=pat: pattern_matches_row(_pat, row),
            )
        )
    return rules


def load_fry_event_catalog(**kwargs: Any) -> list[PatternRule]:
    return load_pattern_catalog(sleeve="fry_event", **kwargs)


def _row_dict(row: pd.Series) -> dict[str, Any]:
    return {k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()}


def score_row(
    row: dict[str, Any],
    catalog: list[PatternRule],
    *,
    min_matches: int = 1,
) -> tuple[float, list[str]]:
    matched: list[str] = []
    score = 0.0
    for rule in catalog:
        if rule.match(row):
            matched.append(rule.pattern)
            score += math.log(max(rule.oos_lift, 1.01))
    if len(matched) < min_matches:
        return 0.0, []
    return score, matched


def load_cross_section(
    as_of: pd.Timestamp,
    symbols: list[str],
    close: pd.DataFrame,
    vol: pd.DataFrame,
) -> pd.DataFrame:
    """Feature snapshot per symbol on as_of (turnaround panel + on-the-fly fill)."""
    as_of = pd.Timestamp(as_of).normalize()
    sym_set = set(symbols)
    cols = [
        "date",
        "yahoo_symbol",
        "name_type",
        "rsi14",
        "dd_60d",
        "pos_52w_range",
        "vol_ratio_20d",
        "return_5d",
        "quiet_acc_score_5d",
        "chase_score_5d",
        "bandar_lite_label",
        "ihsg_regime",
        "near_support_40d",
        "near_support_60d",
        "is_ara_day",
        "in_index_event_window",
        "moon_phase_bucket",
    ]

    snap = pd.DataFrame()
    if TURNAROUND_PANEL.exists():
        raw = pd.read_parquet(TURNAROUND_PANEL)
        raw["date"] = pd.to_datetime(raw["date"]).dt.normalize()
        sub = raw[raw["yahoo_symbol"].isin(sym_set)]
        if not sub.empty:
            day = sub[sub["date"] == as_of]
            if day.empty:
                day = (
                    sub[sub["date"] <= as_of]
                    .sort_values("date")
                    .groupby("yahoo_symbol", as_index=False)
                    .tail(1)
                )
            use_cols = [c for c in cols if c in day.columns]
            snap = day[use_cols].copy()

    have = set(snap["yahoo_symbol"]) if not snap.empty else set()
    missing = [s for s in symbols if s not in have and s in close.columns]
    if missing:
        from idn_name_type_lib import ensure_full_universe_snapshot, name_type_map
        from idn_turnaround_lib import IHSG_REGIME, build_symbol_features

        nt_map = name_type_map(ensure_full_universe_snapshot())
        if IHSG_REGIME.exists():
            tape = pd.read_parquet(IHSG_REGIME)
            tape.index = pd.to_datetime(tape.index)
        else:
            from idn_regime_lib import fetch_and_cache

            tape, _ = fetch_and_cache()
        ihsg = tape.rename(columns=lambda c: f"ihsg_{c}" if c != "label" else "ihsg_regime")

        built: list[dict[str, Any]] = []
        for sym in missing:
            c = close[sym].dropna()
            if c.empty or as_of not in c.index:
                idx = c.index[c.index <= as_of]
                if idx.empty:
                    continue
                dt = idx[-1]
            else:
                dt = as_of
            feat = build_symbol_features(close[sym], vol[sym], ihsg)
            if dt not in feat.index:
                continue
            row = feat.loc[dt].to_dict()
            row["date"] = dt
            row["yahoo_symbol"] = sym
            row["name_type"] = nt_map.get(sym, "standard")
            built.append(row)
        if built:
            extra = pd.DataFrame(built)
            snap = pd.concat([snap, extra], ignore_index=True) if not snap.empty else extra

    if snap.empty:
        return snap
    return snap.drop_duplicates(subset=["yahoo_symbol"], keep="last").reset_index(drop=True)


def rank_symbols_by_winner_patterns(
    close: pd.DataFrame,
    vol: pd.DataFrame,
    as_of: pd.Timestamp | str,
    symbols: list[str],
    *,
    max_n: int = 12,
    min_oos_lift: float = 1.15,
    min_pattern_matches: int = 1,
    sleeve: str = "retail_tilt",
) -> list[dict[str, Any]]:
    """Rank symbols by how well they match stable winner patterns today."""
    as_of = pd.Timestamp(as_of)
    catalog = load_pattern_catalog(min_oos_lift=min_oos_lift, sleeve=sleeve)
    if not catalog:
        return []

    snap = load_cross_section(as_of, symbols, close, vol)
    if snap.empty:
        return []

    ranked: list[dict[str, Any]] = []
    for _, row in snap.iterrows():
        rd = _row_dict(row)
        score, matched = score_row(rd, catalog, min_matches=min_pattern_matches)
        if score <= 0:
            continue
        ranked.append(
            {
                "yahoo_symbol": str(rd["yahoo_symbol"]),
                "pattern_score": round(score, 4),
                "matched_patterns": matched,
                "name_type": rd.get("name_type"),
                "ihsg_regime": rd.get("ihsg_regime"),
                "bandar_lite_label": rd.get("bandar_lite_label"),
                "dd_60d": rd.get("dd_60d"),
                "rsi14": rd.get("rsi14"),
            }
        )

    ranked.sort(key=lambda x: (-x["pattern_score"], x["yahoo_symbol"]))
    return ranked[: max(max_n * 3, max_n)]


def anti_pattern_avoid_symbols(
    close: pd.DataFrame,
    vol: pd.DataFrame,
    as_of: pd.Timestamp | str,
    symbols: list[str],
    *,
    min_anti_score: float = 2.0,
) -> set[str]:
    """Names that look like chase traps without washout support."""
    as_of = pd.Timestamp(as_of)
    fry_catalog = load_fry_event_catalog(min_oos_lift=1.5)
    retail_catalog = load_pattern_catalog(min_oos_lift=1.15, sleeve="retail_tilt")
    if not fry_catalog:
        return set()

    snap = load_cross_section(as_of, symbols, close, vol)
    avoid: set[str] = set()
    for _, row in snap.iterrows():
        rd = _row_dict(row)
        fry_score, fry_hits = score_row(rd, fry_catalog, min_matches=0)
        retail_score, _ = score_row(rd, retail_catalog, min_matches=0)
        dd = rd.get("dd_60d")
        deep_dd = dd is not None and np.isfinite(dd) and float(dd) < -0.15
        if fry_score >= min_anti_score and retail_score < 1.0 and not deep_dd:
            avoid.add(str(rd["yahoo_symbol"]))
        elif len(fry_hits) >= 2 and retail_score < 0.5:
            avoid.add(str(rd["yahoo_symbol"]))
    return avoid


def pattern_rationale(matches: list[str], *, max_parts: int = 3) -> str:
    short = []
    for p in matches[:max_parts]:
        if "=" in p:
            short.append(p.split("=", 1)[-1][:24])
        elif ":x" in p:
            short.append(p.split(":", 1)[-1][:24])
        else:
            short.append(p[:24])
    return "+".join(short) if short else "profile_match"
