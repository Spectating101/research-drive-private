"""Historical backtest — selective fry best-picks vs benchmarks.

Strategies (on top-K gated picks per day):
  - trigger_hold_14d: buy trigger close, hold 14 sessions
  - incubate_d3_hold_11d: skip 3d; enter if no sink; hold 11d
  - incubate_d5_hold_9d: skip 5d; enter if no sink; hold 9d
  - trigger_exit_pop_or_14d: buy trigger; exit first pop or day 14
  - incubate_d3_exit_pop_or_14d: incubate 3d then same

Benchmarks:
  - all_t1_trigger_hold_14d: every T1 trigger (not selective)
  - random_t1_matched_n: random T1 sample matched to pick count per day
"""

from __future__ import annotations

import json
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
OUT_DIR = REPO / "backtests/outputs/idn_fry_best_pick_backtest"
TURNAROUND = REPO / "data_lake/research_panels/idn_turnaround/daily_features.parquet"

OOS_START = pd.Timestamp("2024-01-01")
TOP_K = 3
HOLD_DAYS = 14
INCUBATE_D3 = 3
INCUBATE_D5 = 5
POP_RET = 0.08
SINK_RET = -0.08
TX_COST = 15 / 10000
DEAD_MIN_TRIGGERS = 20


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z**2 / n
    c = p + z**2 / (2 * n)
    m = z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)
    return (max(0, (c - m) / d), min(1, (c + m) / d))


def _summarize_returns(rets: list[float]) -> dict[str, Any]:
    if not rets:
        return {"n": 0, "sufficient": False}
    a = np.array(rets, dtype=float)
    wins = int((a > 0).sum())
    n = int(len(a))
    lo, hi = _wilson(wins, n)
    return {
        "n": n,
        "sufficient": n >= 30,
        "mean_return_pct": round(float(a.mean()) * 100, 3),
        "median_return_pct": round(float(np.median(a)) * 100, 3),
        "win_rate_pct": round(float((a > 0).mean()) * 100, 2),
        "win_rate_wilson_95": [round(lo * 100, 2), round(hi * 100, 2)],
        "p10_return_pct": round(float(np.percentile(a, 10)) * 100, 2),
        "p90_return_pct": round(float(np.percentile(a, 90)) * 100, 2),
        "std_pct": round(float(a.std()) * 100, 3) if n > 1 else None,
    }


def _walkforward_priors(trig: pd.DataFrame) -> pd.Series:
    """Symbol pop rate from strictly prior triggers (no lookahead)."""
    trig = trig.sort_values("date")
    priors: list[float] = []
    hist: dict[str, list[int]] = {}
    for _, row in trig.iterrows():
        sym = row["yahoo_symbol"]
        past = hist.get(sym, [])
        priors.append(float(np.mean(past)) if past else np.nan)
        past.append(int(row.get("got_pop", 0)))
        hist[sym] = past
    return pd.Series(priors, index=trig.index)


def _dead_names_asof(trig: pd.DataFrame) -> dict[pd.Timestamp, set[str]]:
    """Per date: symbols with >=20 prior triggers and 0 pops."""
    trig = trig.sort_values("date")
    dead_by_date: dict[pd.Timestamp, set[str]] = {}
    hist: dict[str, list[int]] = {}
    for dt in sorted(trig["date"].unique()):
        day = trig[trig["date"] == dt]
        dead: set[str] = set()
        for sym, past in hist.items():
            if len(past) >= DEAD_MIN_TRIGGERS and sum(past) == 0:
                dead.add(sym)
        dead_by_date[pd.Timestamp(dt)] = dead
        for _, row in day.iterrows():
            sym = row["yahoo_symbol"]
            past = hist.get(sym, [])
            past.append(int(row.get("got_pop", 0)))
            hist[sym] = past
    return dead_by_date


def _sink_risk_tier(row: pd.Series) -> str:
    r5 = float(row.get("return_5d") or 0)
    vol = float(row.get("vol_ratio_20d") or 0)
    quiet = str(row.get("bandar_lite_label") or "") == "quiet_volume_build"
    vol_dd = vol >= 1.6 and r5 <= -0.04
    score = 0
    if quiet and not vol_dd:
        score += 35
    if r5 > -0.04 and vol >= 1.6:
        score += 25
    if r5 > -0.08:
        score += 10
    if score >= 40:
        return "high"
    if score >= 20:
        return "elevated"
    return "low"


def _historical_rank(row: pd.Series, sym_prior: float) -> float:
    from idn_fry_best_pick_lib import T1_R5_MAX, T1_VOL_MIN

    r5 = float(row.get("return_5d") or 0)
    vol = float(row.get("vol_ratio_20d") or 0)
    score = 0.0
    if r5 <= -0.12:
        score += 45
    elif r5 <= T1_R5_MAX:
        score += 35
    if vol >= T1_VOL_MIN:
        score += min(vol, 4) * 5
    if str(row.get("trigger_cause") or "") == "drawdown_vol_spike":
        score += 15
    if sym_prior >= 0.25:
        score += 20
    elif sym_prior >= 0.15:
        score += 10
    qa = row.get("quiet_acc_score_5d")
    if qa is not None and pd.notna(qa) and float(qa) <= 1:
        score += 8
    cs = row.get("cs_move_pct_rank")
    if cs is not None and pd.notna(cs) and float(cs) <= 0.25:
        score += 5
    if _sink_risk_tier(row) == "high":
        score -= 40
    elif _sink_risk_tier(row) == "elevated":
        score -= 10
    return score


def _passes_hard_gates(row: pd.Series, *, dead: set[str], sym_prior: float) -> bool:
    from idn_fry_best_pick_lib import T1_R5_MAX, T1_VOL_MIN, evaluate_gates

    rd = {
        "yahoo_symbol": row["yahoo_symbol"],
        "name_type": "fry",
        "return_5d": row.get("return_5d"),
        "vol_ratio_20d": row.get("vol_ratio_20d"),
        "return_1d": 0.0,
        "bandar_lite_label": row.get("bandar_lite_label"),
        "pop_trigger_cause": row.get("trigger_cause"),
        "trigger_cause": row.get("trigger_cause"),
        "sink_risk_tier": _sink_risk_tier(row),
        "quiet_acc_score_5d": row.get("quiet_acc_score_5d"),
        "cs_move_pct_rank": row.get("cs_move_pct_rank"),
        "multi_year_pop_score": 1.5 if float(row.get("return_5d") or 0) <= -0.12 else 0.8,
        "symbol_pop_prior_wf": sym_prior * 100 if np.isfinite(sym_prior) else None,
    }
    gates = evaluate_gates(rd, dead_syms=dead, sym_prior=sym_prior if np.isfinite(sym_prior) else None)
    return all(g.passed for g in gates if g.hard)


def _select_picks_for_day(
    day: pd.DataFrame,
    priors: pd.Series,
    dead: set[str],
    top_k: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for idx, row in day.iterrows():
        sp = float(priors.loc[idx]) if idx in priors.index and pd.notna(priors.loc[idx]) else float("nan")
        if not _passes_hard_gates(row, dead=dead, sym_prior=sp):
            continue
        rows.append(
            {
                "idx": idx,
                "rank_score": _historical_rank(row, sp if np.isfinite(sp) else 0.0),
                "sym_prior": sp,
            }
        )
    if not rows:
        return pd.DataFrame()
    pick_df = pd.DataFrame(rows).sort_values("rank_score", ascending=False).head(top_k)
    return day.loc[pick_df["idx"]]


def _path_panel(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {sym: g.reset_index(drop=True) for sym, g in panel.groupby("yahoo_symbol")}


def _simulate(
    sym: str,
    t0: pd.Timestamp,
    paths: dict[str, pd.DataFrame],
    *,
    strategy: str,
    max_days: int = HOLD_DAYS,
) -> dict[str, Any] | None:
    g = paths.get(sym)
    if g is None:
        return None
    g = g[g["date"] >= t0].head(max_days + 6).reset_index(drop=True)
    if len(g) < 2:
        return None

    close = g["close"].to_numpy(dtype=float)
    rets = g["return_1d"].to_numpy(dtype=float)

    def ret_ei(ei: int, xi: int) -> float | None:
        if ei < 0 or xi >= len(close) or ei >= xi:
            return None
        c0, c1 = close[ei], close[xi]
        if not np.isfinite(c0) or not np.isfinite(c1) or c0 <= 0:
            return None
        return float(c1 / c0 - 1.0 - TX_COST)

    def first_sink_before(pop_start: int, end: int) -> int | None:
        for i in range(pop_start, min(end, len(rets))):
            if np.isfinite(rets[i]) and rets[i] <= SINK_RET:
                return i
        return None

    def first_pop_from(start: int, end: int) -> int | None:
        for i in range(start, min(end, len(rets))):
            if np.isfinite(rets[i]) and rets[i] >= POP_RET:
                return i
        return None

    incubate = 0
    if strategy.startswith("incubate_d3"):
        incubate = INCUBATE_D3
    elif strategy.startswith("incubate_d5"):
        incubate = INCUBATE_D5

    if incubate > 0:
        if len(rets) <= incubate:
            return None
        if first_sink_before(1, incubate + 1) is not None:
            return {"skipped": True, "reason": "sink_during_incubation"}
        entry_i = incubate
    else:
        entry_i = 0

    exit_pop = "exit_pop" in strategy
    hold_after = max_days - entry_i
    if exit_pop:
        pi = first_pop_from(entry_i + 1, entry_i + max_days + 1)
        exit_i = entry_i + pi if pi is not None else min(entry_i + max_days, len(close) - 1)
    else:
        exit_i = min(entry_i + hold_after, len(close) - 1)

    r = ret_ei(entry_i, exit_i)
    if r is None:
        return None

    pop_hit = first_pop_from(entry_i + 1, entry_i + max_days + 1)
    sink_hit = first_sink_before(entry_i + 1, entry_i + max_days + 1)

    return {
        "return": r,
        "entry_lag": entry_i,
        "hold_days": exit_i - entry_i,
        "pop_within_window": pop_hit is not None,
        "sink_after_entry": sink_hit is not None,
        "skipped": False,
    }


def _run_strategy(
    picks: pd.DataFrame,
    paths: dict[str, pd.DataFrame],
    strategy: str,
) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    for _, row in picks.iterrows():
        out = _simulate(row["yahoo_symbol"], pd.Timestamp(row["date"]), paths, strategy=strategy)
        if out is None:
            continue
        if out.get("skipped"):
            trades.append({**out, "date": row["date"], "yahoo_symbol": row["yahoo_symbol"]})
            continue
        trades.append(
            {
                "date": row["date"],
                "yahoo_symbol": row["yahoo_symbol"],
                "year": pd.Timestamp(row["date"]).year,
                "era": "oos" if pd.Timestamp(row["date"]) >= OOS_START else "ins",
                "got_pop_episode": int(row.get("got_pop", 0)),
                "strategy": strategy,
                **out,
            }
        )
    return trades


def build_best_pick_backtest(*, top_k: int = TOP_K) -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    trig = pd.read_parquet(FRY_DIR / "trigger_enriched.parquet")
    trig["date"] = pd.to_datetime(trig["date"])
    trig = trig.sort_values("date").reset_index(drop=True)
    trig["sym_prior_wf"] = _walkforward_priors(trig)
    dead_map = _dead_names_asof(trig)

    syms = set(trig["yahoo_symbol"].unique())
    panel = pd.read_parquet(TURNAROUND, columns=["date", "yahoo_symbol", "close", "return_1d"])
    panel["date"] = pd.to_datetime(panel["date"])
    panel = panel[panel["yahoo_symbol"].isin(syms)].sort_values(["yahoo_symbol", "date"])
    paths = _path_panel(panel)

    strategies = [
        "pick_trigger_hold_14d",
        "pick_incubate_d3_hold_11d",
        "pick_incubate_d5_hold_9d",
        "pick_trigger_exit_pop_or_14d",
        "pick_incubate_d3_exit_pop_or_14d",
        "bench_all_t1_hold_14d",
        "bench_random_t1_hold_14d",
    ]

    all_picks: list[pd.DataFrame] = []
    all_t1_by_day: dict[pd.Timestamp, pd.DataFrame] = {}

    for dt, day in trig.groupby("date"):
        dt = pd.Timestamp(dt)
        dead = dead_map.get(dt, set())
        t1 = day[(day["return_5d"] <= -0.08) & (day["vol_ratio_20d"] >= 1.6)]
        all_t1_by_day[dt] = t1
        picks = _select_picks_for_day(day, trig["sym_prior_wf"], dead, top_k)
        if not picks.empty:
            all_picks.append(picks)

    picks_df = pd.concat(all_picks, ignore_index=True) if all_picks else pd.DataFrame()
    rng = np.random.default_rng(42)

    results: dict[str, Any] = {
        "meta": {
            "n_trigger_days": int(trig["date"].nunique()),
            "n_all_triggers": int(len(trig)),
            "n_best_pick_trades": int(len(picks_df)),
            "avg_picks_per_day": round(len(picks_df) / max(trig["date"].nunique(), 1), 3),
            "top_k": top_k,
            "oos_start": str(OOS_START.date()),
            "date_min": str(trig["date"].min().date()),
            "date_max": str(trig["date"].max().date()),
        },
        "strategies": {},
        "yearly": {},
        "reliability": {},
    }

    pick_strats = [s for s in strategies if s.startswith("pick_")]
    for strat in strategies:
        if strat == "bench_all_t1_hold_14d":
            bench = pd.concat([g for g in all_t1_by_day.values() if len(g)], ignore_index=True)
            trades = _run_strategy(bench, paths, "pick_trigger_hold_14d")
        elif strat == "bench_random_t1_hold_14d":
            rand_rows = []
            for dt, t1 in all_t1_by_day.items():
                n = min(len(_select_picks_for_day(
                    trig[trig["date"] == dt], trig["sym_prior_wf"], dead_map.get(pd.Timestamp(dt), set()), top_k
                )), len(t1))
                if n > 0 and len(t1) > 0:
                    idx = rng.choice(len(t1), size=min(n, len(t1)), replace=False)
                    rand_rows.append(t1.iloc[idx])
            bench = pd.concat(rand_rows, ignore_index=True) if rand_rows else pd.DataFrame()
            trades = _run_strategy(bench, paths, "pick_trigger_hold_14d")
        else:
            core = strat.replace("pick_", "")
            trades = _run_strategy(picks_df, paths, core)

        executed = [t for t in trades if not t.get("skipped")]
        skipped = [t for t in trades if t.get("skipped")]
        rets = [t["return"] for t in executed]
        pop_rate = float(np.mean([t.get("pop_within_window") for t in executed])) if executed else 0.0

        results["strategies"][strat] = {
            **_summarize_returns(rets),
            "n_skipped_incubation_sink": len(skipped),
            "pop_within_window_pct": round(pop_rate * 100, 2),
            "episode_got_pop_rate_pct": round(float(np.mean([t.get("got_pop_episode", 0) for t in executed])) * 100, 2)
            if executed
            else None,
        }

        by_year: dict[str, Any] = {}
        for yr, grp in pd.DataFrame(executed).groupby("year") if executed else []:
            by_year[str(int(yr))] = _summarize_returns(grp["return"].tolist())
        results["yearly"][strat] = by_year

    # Reliability vs benchmarks
    pick14 = results["strategies"].get("pick_trigger_hold_14d", {})
    bench14 = results["strategies"].get("bench_all_t1_hold_14d", {})
    incub3 = results["strategies"].get("pick_incubate_d3_hold_11d", {})
    results["reliability"] = {
        "selective_vs_all_t1_mean_lift_pct": round(
            (pick14.get("mean_return_pct") or 0) - (bench14.get("mean_return_pct") or 0), 3
        ),
        "selective_vs_all_t1_median_lift_pct": round(
            (pick14.get("median_return_pct") or 0) - (bench14.get("median_return_pct") or 0), 3
        ),
        "incubate_d3_vs_trigger_mean_lift_pct": round(
            (incub3.get("mean_return_pct") or 0) - (pick14.get("mean_return_pct") or 0), 3
        ),
        "pick_pop_capture_pct": pick14.get("pop_within_window_pct"),
        "all_t1_pop_capture_pct": results["strategies"].get("bench_all_t1_hold_14d", {}).get("pop_within_window_pct"),
        "verdict": _reliability_verdict(results),
        "interpretation": _interpretation(results),
    }

    (OUT_DIR / "latest.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


def _reliability_verdict(results: dict[str, Any]) -> str:
    pick = results["strategies"].get("pick_trigger_hold_14d", {})
    bench = results["strategies"].get("bench_all_t1_hold_14d", {})
    incub = results["strategies"].get("pick_incubate_d3_hold_11d", {})
    if pick.get("n", 0) < 50:
        return "insufficient_trades"
    mean_lift = (pick.get("mean_return_pct") or 0) - (bench.get("mean_return_pct") or 0)
    med_pick = pick.get("median_return_pct") or -999
    med_bench = bench.get("median_return_pct") or -999
    if med_pick > 0 and mean_lift > 0.5:
        return "selective_beats_broad_moderate"
    if med_pick > med_bench and pick.get("pop_within_window_pct", 0) > bench.get("pop_within_window_pct", 0):
        return "selective_better_pop_capture_flat_pnl"
    if incub.get("median_return_pct", -999) > med_pick:
        return "incubation_helps_timing_not_enough_for_positive_ev"
    return "not_reliable_for_hold_strategy"


def _interpretation(results: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    meta = results["meta"]
    s = results["strategies"]
    p = s.get("pick_trigger_hold_14d", {})
    b = s.get("bench_all_t1_hold_14d", {})
    i3 = s.get("pick_incubate_d3_hold_11d", {})
    lines.append(
        f"Best-pick selective: {meta['n_best_pick_trades']} trades "
        f"({meta['avg_picks_per_day']:.2f}/day) vs {b.get('n', 0)} all-T1."
    )
    lines.append(
        f"Pick hold-14d: mean {p.get('mean_return_pct')}% med {p.get('median_return_pct')}% "
        f"win {p.get('win_rate_pct')}% pop-window {p.get('pop_within_window_pct')}%."
    )
    lines.append(
        f"All-T1 bench: mean {b.get('mean_return_pct')}% med {b.get('median_return_pct')}% "
        f"win {b.get('win_rate_pct')}%."
    )
    if i3.get("n"):
        lines.append(
            f"Incubate-3d: mean {i3.get('mean_return_pct')}% med {i3.get('median_return_pct')}% "
            f"skipped {i3.get('n_skipped_incubation_sink')} sink-before-entry."
        )
    lines.append("Episode got_pop rate on picks vs selective pop-within-window — see strategy block.")
    return lines
