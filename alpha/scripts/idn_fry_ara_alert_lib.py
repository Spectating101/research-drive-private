"""ARA pop-day alert sleeve — separate from EOD trigger watchlist.

Trigger watch = after close, conditions met, 0% weight.
ARA alert = intraday/session spike on a watched name (or fresh deep-dd fry).

We only have daily bars — ARA is proxied by:
  - is_ara_day flag (≥24% move band)
  - return_1d ≥ 8% with chase_into_spike bandar label
  - return_1d ≥ 10% on fry name

Execution note: alert means 'pop happening now' — not 'buy at close'.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from idn_fry_episode_lib import ARA_RET_MIN, POP_RET_MIN, POP_RET_STRONG

ARA_ALERT_RET = ARA_RET_MIN
POP_DAY_RET = POP_RET_MIN
STRONG_POP_RET = POP_RET_STRONG


def classify_ara_pop_event(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    """Classify whether this symbol-day is an ARA-style pop."""
    if isinstance(row, dict):
        row = pd.Series(row)

    r = row.get("return_1d")
    if r is None and row.get("return_1d_pct") is not None:
        r = float(row["return_1d_pct"]) / 100.0
    r = float(r) if r is not None and pd.notna(r) else np.nan
    is_ara = int(row.get("is_ara_day", 0) or 0) == 1
    label = str(row.get("bandar_lite_label") or "")
    cs = row.get("cs_move_pct_rank")

    if not np.isfinite(r):
        return {"is_ara_pop": False, "ara_class": "unknown", "return_1d_pct": None}

    ret_pct = round(r * 100, 2)
    if is_ara or r >= ARA_ALERT_RET:
        ara_class = "ara_limit_hit"
    elif r >= STRONG_POP_RET:
        ara_class = "strong_pop_10pct"
    elif r >= POP_DAY_RET and label == "chase_into_spike":
        ara_class = "chase_pop_8pct"
    elif r >= POP_DAY_RET and cs is not None and pd.notna(cs) and float(cs) >= 0.90:
        ara_class = "top_decile_pop"
    else:
        return {"is_ara_pop": False, "ara_class": "none", "return_1d_pct": ret_pct}

    return {
        "is_ara_pop": True,
        "ara_class": ara_class,
        "return_1d_pct": ret_pct,
        "cs_move_pct_rank": round(float(cs), 3) if cs is not None and pd.notna(cs) else None,
        "bandar_lite_label": label or None,
        "is_ara_day": is_ara,
    }


def _t1_trigger_row(row: pd.Series) -> bool:
    r5 = row.get("return_5d")
    vol = row.get("vol_ratio_20d")
    if pd.isna(r5) or pd.isna(vol):
        return False
    return float(r5) <= -0.08 and float(vol) >= 1.6


def scan_ara_pop_alerts(
    panel: pd.DataFrame,
    *,
    as_of: pd.Timestamp | None = None,
    watch_symbols: set[str] | None = None,
    lookback_sessions: int = 30,
    min_tier_symbols: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return ARA pop alerts for as_of session.

    Fires when:
      1. Today is ARA/pop day on a fry name, AND
      2. Symbol was in watch state (T1 trigger in lookback) OR on explicit watchlist.
    """
    if panel.empty:
        return []

    panel = panel.copy()
    panel["date"] = pd.to_datetime(panel["date"])
    fry = panel[panel.get("name_type", "fry") == "fry"] if "name_type" in panel.columns else panel
    if fry.empty:
        return []

    if as_of is None:
        as_of = fry["date"].max()
    as_of = pd.Timestamp(as_of).normalize()
    today = fry[fry["date"] == as_of]
    if today.empty:
        return []

    watch = watch_symbols or set()
    tier_syms = min_tier_symbols or set()

    hist = fry[fry["date"] < as_of].sort_values(["yahoo_symbol", "date"])
    recent_trigger: dict[str, pd.Timestamp] = {}
    for sym, g in hist.groupby("yahoo_symbol"):
        g = g.tail(lookback_sessions)
        trig_rows = g[g.apply(_t1_trigger_row, axis=1)]
        if not trig_rows.empty:
            recent_trigger[sym] = pd.Timestamp(trig_rows["date"].iloc[-1])

    alerts: list[dict[str, Any]] = []
    for _, row in today.iterrows():
        sym = row["yahoo_symbol"]
        pop = classify_ara_pop_event(row)
        if not pop["is_ara_pop"]:
            continue

        on_watch = sym in watch or sym in tier_syms
        had_recent = sym in recent_trigger
        fresh_t1 = _t1_trigger_row(row)

        if not (on_watch or had_recent or fresh_t1):
            continue

        alerts.append(
            {
                "yahoo_symbol": sym,
                "as_of": str(as_of.date()),
                "ara_class": pop["ara_class"],
                "return_1d_pct": pop["return_1d_pct"],
                "cs_move_pct_rank": pop.get("cs_move_pct_rank"),
                "bandar_lite_label": pop.get("bandar_lite_label"),
                "watchlist_member": sym in watch,
                "recent_t1_trigger_date": str(recent_trigger[sym].date()) if had_recent else None,
                "fresh_t1_today": fresh_t1,
                "action": "ARA_POP_ALERT",
                "weight_pct": 0,
                "note": (
                    "Pop day detected on daily bar — intraday ARA may have halted earlier. "
                    "Not a close-entry signal; confirms watch thesis or late chase risk."
                ),
            }
        )

    alerts.sort(key=lambda x: (-(x.get("return_1d_pct") or 0), x["yahoo_symbol"]))
    return alerts


def build_ara_alert_pack(
    panel: pd.DataFrame | None = None,
    watchlist: list[dict[str, Any]] | None = None,
    *,
    as_of: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Daily ARA alert pack for actionable JSON."""
    if panel is None:
        from pathlib import Path
        import importlib.util as _ilu

        _bspec = _ilu.spec_from_file_location(
            "sr_bootstrap", Path(__file__).resolve().parent / "_repo_bootstrap.py"
        )
        _bmod = _ilu.module_from_spec(_bspec)
        _bspec.loader.exec_module(_bmod)
        repo = _bmod.repo_root_from_file(__file__)
        path = repo / "data_lake/research_panels/idn_turnaround/daily_features.parquet"
        cols = [
            "date",
            "yahoo_symbol",
            "name_type",
            "return_1d",
            "return_5d",
            "vol_ratio_20d",
            "bandar_lite_label",
            "cs_move_pct_rank",
            "is_ara_day",
        ]
        panel = pd.read_parquet(path, columns=[c for c in cols if c])
        panel["date"] = pd.to_datetime(panel["date"])

    watch = watchlist or []
    watch_syms = {w["yahoo_symbol"] for w in watch}
    tier_syms = {w["yahoo_symbol"] for w in watch if w.get("tier") in ("elevated", "high")}

    alerts = scan_ara_pop_alerts(
        panel,
        as_of=as_of,
        watch_symbols=watch_syms,
        lookback_sessions=30,
        min_tier_symbols=tier_syms,
    )

    return {
        "as_of": str((as_of or panel["date"].max()).date()),
        "n_alerts": len(alerts),
        "alerts": alerts,
        "usage": {
            "purpose": "Session pop detection on watched fry names — not auto-trade.",
            "execution": "ARA hits intraday; daily bar is lagging confirmation only.",
            "weight": "0% — alert sleeve only",
        },
    }
