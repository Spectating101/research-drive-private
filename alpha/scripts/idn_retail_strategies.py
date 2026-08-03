"""IDX retail / influencer TA strategies — definitions, signals, event studies.

Canonical playbook for replication research. Each rule maps retail jargon to
testable boolean conditions on daily OHLCV.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

try:
    from api.intelligence.technical_indicators import TechnicalIndicators
except ModuleNotFoundError:
    import sys
    from pathlib import Path as _P
    _root = _P(__file__).resolve().parents[2]
    for _p in (_root / "alpha", _root):
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
    from api.intelligence.technical_indicators import TechnicalIndicators

INDEX = "^JKSE"
BANKS = ["BBCA.JK", "BBRI.JK", "BMRI.JK"]  # replication labels only; live scopes use data-driven sets


@dataclass
class RetailStrategy:
    id: str
    retail_jargon: str
    description: str
    hold_days: int = 10
    max_slots: int = 5
    symbols_scope: str = "universe"  # universe | banks | bbca | compounders
    tags: list[str] = field(default_factory=list)


# Playbook catalog — what IDX influencers / brokers / YouTube TA actually teach
PLAYBOOK: list[RetailStrategy] = [
    RetailStrategy(
        "compounder_support_rsi",
        "Support + RSI oversold (blue chip)",
        "Liquid compounder within 2% of 60d low AND RSI(14)<35 (data-classified)",
        hold_days=20,
        max_slots=5,
        symbols_scope="compounders",
        tags=["support", "rsi", "blue_chip"],
    ),
    RetailStrategy(
        "bbca_support_rsi",
        "Support + RSI oversold (BBCA)",
        "BBCA within 2% of 60d low AND RSI(14)<35",
        hold_days=20,
        max_slots=1,
        symbols_scope="bbca",
        tags=["support", "rsi", "blue_chip"],
    ),
    RetailStrategy(
        "bbca_support_only",
        "Support saja (BBCA at 60d low)",
        "BBCA within 2% of 60d low (no RSI filter)",
        hold_days=20,
        max_slots=1,
        symbols_scope="bbca",
        tags=["support"],
    ),
    RetailStrategy(
        "bbca_rsi_oversold",
        "RSI oversold BBCA",
        "BBCA RSI(14)<30 only",
        hold_days=10,
        max_slots=1,
        symbols_scope="bbca",
        tags=["rsi"],
    ),
    RetailStrategy(
        "banks_rsi_oversold",
        "RSI oversold bank saham",
        "Any bank BBCA/BBRI/BMRI RSI<30",
        hold_days=10,
        max_slots=3,
        symbols_scope="banks",
        tags=["rsi", "banks"],
    ),
    RetailStrategy(
        "ihsg_support_banks",
        "IHSG support → beli bank",
        "IHSG within 3% of 60d low → hold equal banks 20d",
        hold_days=20,
        max_slots=3,
        symbols_scope="banks",
        tags=["support", "index", "banks"],
    ),
    RetailStrategy(
        "ihsg_washout_banks",
        "IHSG washout (drawdown)",
        "IHSG down >10% from 63d high AND bounce <8% → banks",
        hold_days=20,
        max_slots=3,
        symbols_scope="banks",
        tags=["regime", "banks"],
    ),
    RetailStrategy(
        "bluechip_support",
        "Support blue chip",
        "Data-classified compounder within 2% of 40d low",
        hold_days=10,
        max_slots=5,
        symbols_scope="compounders",
        tags=["support"],
    ),
    RetailStrategy(
        "ma20_golden_cross",
        "Golden cross MA20",
        "Close crosses above SMA20 after 5d below",
        hold_days=10,
        tags=["ma", "breakout"],
    ),
    RetailStrategy(
        "ma50_golden_cross",
        "Golden cross MA50",
        "Close crosses above SMA50 after 10d below",
        hold_days=15,
        tags=["ma"],
    ),
    RetailStrategy(
        "ma20_death_cross_avoid",
        "Death cross (fade long)",
        "Close crosses below SMA20 — go cash vs benchmark",
        hold_days=5,
        tags=["ma", "risk_off"],
    ),
    RetailStrategy(
        "rsi30_bounce",
        "RSI oversold bounce",
        "Any liquid name RSI(14)<30",
        hold_days=5,
        tags=["rsi"],
    ),
    RetailStrategy(
        "bollinger_lower",
        "Sentuh Bollinger bawah",
        "Close <= lower Bollinger(20,2)",
        hold_days=5,
        tags=["bollinger", "support"],
    ),
    RetailStrategy(
        "fib_618_pullback",
        "Fibonacci 61.8% retracement",
        "Price within 2% of 61.8% retrace from 40d swing high/low",
        hold_days=10,
        tags=["fibonacci"],
    ),
    RetailStrategy(
        "breakout_20d_high",
        "Break resistance / breakout",
        "Close > 20d high AND volume > 1.5x 20d avg",
        hold_days=5,
        tags=["breakout", "resistance"],
    ),
    RetailStrategy(
        "volume_akumulasi",
        "Akumulasi (volume kering lalu naik)",
        "5d avg vol < 0.7x 20d avg AND today vol > 1.8x 20d avg after 5d drawdown",
        hold_days=5,
        tags=["volume", "bandar"],
    ),
    RetailStrategy(
        "drawdown_dip_volume",
        "Buy the dip + volume (bandar lite)",
        "5d return <= -8% AND volume >= 1.4x 20d avg",
        hold_days=5,
        tags=["dip", "volume"],
    ),
]


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    return TechnicalIndicators.calculate_rsi(close, period)


def scope_symbols(
    scope: str,
    universe: list[str],
    *,
    compounders: frozenset[str],
    liquid_core: list[str],
) -> list[str]:
    if scope == "bbca":
        return ["BBCA.JK"]
    if scope == "banks":
        return [s for s in liquid_core if s in universe]
    if scope == "compounders":
        return [s for s in universe if s in compounders]
    return universe


def build_all_signals(
    close: pd.DataFrame,
    vol: pd.DataFrame,
    universe: list[str],
    *,
    lookback_days: int | None = None,
) -> dict[str, dict[pd.Timestamp, list[str]]]:
    """Single pass — all playbook signals.

    lookback_days: if set, only scan the last N rows (position sheet needs ~hold window).
    """
    from idn_name_type_lib import compounder_set_from_snapshot, ensure_full_universe_snapshot, liquid_core_from_snapshot

    snap = ensure_full_universe_snapshot()
    compounder_set = compounder_set_from_snapshot(snap)
    liquid_core = liquid_core_from_snapshot(snap)

    out: dict[str, dict[pd.Timestamp, list[str]]] = {s.id: {} for s in PLAYBOOK}
    idx = close[INDEX] if INDEX in close.columns else None

    # Precompute RSI / Bollinger once per symbol (was recomputed inside day loop — hung weekly sheet)
    rsi_cache: dict[str, pd.Series] = {
        sym: rsi(close[sym]) for sym in universe if sym in close.columns
    }
    bb_cache: dict[str, dict[str, pd.Series]] = {
        sym: TechnicalIndicators.calculate_bollinger_bands(close[sym], period=20)
        for sym in universe
        if sym in close.columns
    }

    dates = list(close.index[63:])
    if lookback_days is not None and lookback_days > 0:
        dates = dates[-int(lookback_days) :]

    for dt in dates:
        day: dict[str, list[str]] = {s.id: [] for s in PLAYBOOK}

        # index-level rules
        if idx is not None and dt in idx.index:
            iloc = idx.index.get_loc(dt)
            last_i = float(idx.loc[dt])
            low60 = float(idx.iloc[iloc - 60 : iloc + 1].min())
            high63 = float(idx.iloc[iloc - 63 : iloc + 1].max())
            low20 = float(idx.iloc[iloc - 20 : iloc + 1].min())
            dd63 = last_i / high63 - 1.0 if high63 > 0 else 0.0
            bounce20 = last_i / low20 - 1.0 if low20 > 0 else 0.0
            if low60 > 0 and last_i <= low60 * 1.03:
                day["ihsg_support_banks"].extend(liquid_core)
            if dd63 <= -0.10 and bounce20 < 0.08:
                day["ihsg_washout_banks"].extend(liquid_core)

        for sym in universe:
            if sym not in close.columns:
                continue
            loc = close.index.get_loc(dt)
            if loc < 63:
                continue
            px = close[sym]
            last = float(px.loc[dt])
            r14 = rsi_cache.get(sym)
            if r14 is None or dt not in r14.index or not np.isfinite(r14.loc[dt]):
                continue
            rsi_v = float(r14.loc[dt])
            low40 = float(px.iloc[loc - 40 : loc + 1].min())
            low60 = float(px.iloc[loc - 60 : loc + 1].min())
            high40 = float(px.iloc[loc - 40 : loc + 1].max())
            high20 = float(px.iloc[loc - 20 : loc].max()) if loc >= 20 else np.nan
            sma20 = float(px.iloc[loc - 19 : loc + 1].mean())
            sma50 = float(px.iloc[loc - 49 : loc + 1].mean()) if loc >= 49 else np.nan
            ret5 = float(px.loc[dt] / px.iloc[loc - 5] - 1.0) if loc >= 5 else 0.0

            vt = float(vol.loc[dt, sym]) if sym in vol.columns else np.nan
            v20 = vol[sym].iloc[loc - 20 : loc] if sym in vol.columns else pd.Series(dtype=float)
            v5 = vol[sym].iloc[loc - 5 : loc] if sym in vol.columns else pd.Series(dtype=float)
            vavg = float(v20.mean()) if len(v20) else np.nan
            v5avg = float(v5.mean()) if len(v5) else np.nan

            bb = bb_cache.get(sym) or {}
            bb_lower = bb.get("lower")
            bb_low = float(bb_lower.loc[dt]) if bb_lower is not None and dt in bb_lower.index else np.nan

            prev_below20 = loc >= 25 and all(
                float(px.loc[close.index[loc - k]]) < float(px.iloc[loc - 19 - k : loc - k + 1].mean())
                for k in range(1, 6)
            )
            prev_below50 = loc >= 60 and all(
                float(px.loc[close.index[loc - k]]) < float(px.iloc[loc - 49 - k : loc - k + 1].mean())
                for k in range(1, 11)
            )
            prev_above20 = loc >= 25 and float(px.loc[close.index[loc - 1]]) > float(
                px.iloc[loc - 20 : loc].mean()
            )

            if sym in compounder_set and low60 > 0 and last <= low60 * 1.02 and rsi_v < 35:
                day["compounder_support_rsi"].append(sym)

            if sym == "BBCA.JK":
                if low60 > 0 and last <= low60 * 1.02 and rsi_v < 35:
                    day["bbca_support_rsi"].append(sym)
                if low60 > 0 and last <= low60 * 1.02:
                    day["bbca_support_only"].append(sym)
                if rsi_v < 30:
                    day["bbca_rsi_oversold"].append(sym)

            if sym in compounder_set and rsi_v < 30:
                day["banks_rsi_oversold"].append(sym)

            if sym in compounder_set and low40 > 0 and last <= low40 * 1.02:
                day["bluechip_support"].append(sym)

            if prev_below20 and last > sma20:
                day["ma20_golden_cross"].append(sym)
            if np.isfinite(sma50) and prev_below50 and last > sma50:
                day["ma50_golden_cross"].append(sym)
            if prev_above20 and last < sma20:
                day["ma20_death_cross_avoid"].append(sym)

            if rsi_v < 30:
                day["rsi30_bounce"].append(sym)

            if np.isfinite(bb_low) and last <= bb_low * 1.01:
                day["bollinger_lower"].append(sym)

            if high40 > low40:
                fib = low40 + 0.618 * (high40 - low40)
                if fib > 0 and abs(last / fib - 1.0) <= 0.02:
                    day["fib_618_pullback"].append(sym)

            if np.isfinite(high20) and last > high20 and np.isfinite(vt) and np.isfinite(vavg) and vt >= 1.5 * vavg:
                day["breakout_20d_high"].append(sym)

            if (
                ret5 <= -0.05
                and np.isfinite(v5avg)
                and np.isfinite(vavg)
                and v5avg < 0.7 * vavg
                and np.isfinite(vt)
                and vt >= 1.8 * vavg
            ):
                day["volume_akumulasi"].append(sym)

            if ret5 <= -0.08 and np.isfinite(vt) and np.isfinite(vavg) and vt >= 1.4 * vavg:
                day["drawdown_dip_volume"].append(sym)

        for k, v in day.items():
            if v:
                out[k][dt] = sorted(set(v))

    return out


def event_study(
    signals: dict[pd.Timestamp, list[str]],
    close: pd.DataFrame,
    hold_days_list: tuple[int, ...] = (5, 10, 20),
    oos_start: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Per-signal forward returns."""
    rows = []
    for dt, syms in signals.items():
        loc = close.index.get_loc(dt)
        for sym in syms:
            if sym not in close.columns:
                continue
            entry = float(close.loc[dt, sym])
            if not np.isfinite(entry) or entry <= 0:
                continue
            rec: dict[str, Any] = {"date": str(dt.date()), "symbol": sym}
            for h in hold_days_list:
                if loc + h < len(close.index):
                    exit_px = float(close.iloc[loc + h][sym])
                    rec[f"fwd_{h}d_pct"] = round((exit_px / entry - 1) * 100, 2)
            if oos_start is not None:
                rec["oos"] = dt >= oos_start
            rows.append(rec)

    if not rows:
        return {"n": 0, "by_horizon": {}}

    df = pd.DataFrame(rows)
    by_h: dict[str, Any] = {}
    for h in hold_days_list:
        col = f"fwd_{h}d_pct"
        if col not in df.columns:
            continue
        for label, sub in [
            ("all", df),
            ("oos", df[df["oos"]] if "oos" in df.columns else df.iloc[0:0]),
            ("is", df[~df["oos"]] if "oos" in df.columns else df.iloc[0:0]),
        ]:
            if label == "oos" and oos_start is None:
                continue
            if label in ("oos", "is") and "oos" not in df.columns:
                continue
            s = sub[col].dropna()
            if s.empty:
                continue
            tstat = float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))) if len(s) > 2 and s.std(ddof=1) > 0 else None
            by_h[f"{label}_{h}d"] = {
                "n": int(len(s)),
                "mean_pct": round(float(s.mean()), 2),
                "median_pct": round(float(s.median()), 2),
                "hit_rate_pct": round(float((s > 0).mean() * 100), 1),
                "tstat": round(tstat, 2) if tstat is not None else None,
            }
    return {"n": len(df), "by_horizon": by_h, "sample": rows[:5]}


def replication_verdict(
    portfolio_oos: dict,
    event_oos: dict,
    *,
    min_n: int = 25,
) -> str:
    """replicate | conditional | reject"""
    h5 = event_oos.get("by_horizon", {}).get("oos_5d") or event_oos.get("by_horizon", {}).get("all_5d") or {}
    n = h5.get("n", event_oos.get("n", 0))
    if n < min_n:
        return "insufficient_sample"
    term = portfolio_oos.get("terminal_x")
    sharpe = portfolio_oos.get("sharpe")
    mean5 = h5.get("mean_pct", 0)
    hit5 = h5.get("hit_rate_pct", 0)
    tstat = h5.get("tstat")

    if term is not None and sharpe is not None and term >= 1.05 and sharpe >= 0.25 and mean5 > 0 and hit5 >= 52:
        return "replicate"
    if (term is not None and term >= 1.0 and sharpe is not None and sharpe >= 0) or (mean5 > 0 and hit5 >= 50):
        return "conditional"
    return "reject"
