"""Tools for reverse-engineering IDX price-movement signals from historical panels."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from idn_eval_splits import (
    ERA_NAMES,
    ERA_OOS,
    ERA_TRAIN,
    build_eras,
    era_bounds,
    min_weeks_for_era,
    slice_era,
    time_cutoff,
)
from idn_sentiment_validation_lib import (
    portfolio_weekly_returns,
    prepare_liquid_weekly,
    quintile_spread,
    summarize_returns,
    verdict_from_stats,
    weekly_rank_ic,
)

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
BROADCAST = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610/ticker_week_country_broadcast_panel.parquet"
ENTITY = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260611/ticker_week_entity_market_panel.parquet"

CANDIDATE_SIGNALS = (
    "mom_4w",
    "return_1w",
    "prior_return_1w",
    "trending_proxy_rank",
    "entity_mention_rows",
    "mention_rank_pct",
    "mean_tone_avg",
)

TARGETS = ("fwd_return_1w", "fwd_return_4w")


@lru_cache(maxsize=4)
def _load_panel(liquid_key: tuple[str, ...]) -> pd.DataFrame:
    from run_idn_invest_trial import load_liquid_universe

    liquid = list(liquid_key) if liquid_key else load_liquid_universe()
    df = prepare_liquid_weekly(BROADCAST, ENTITY, liquid)
    if "fwd_return_4w" not in df.columns:
        df = df.sort_values(["yahoo_symbol", "week_end"])
        df["fwd_return_4w"] = (
            df.groupby("yahoo_symbol")["return_1w"]
            .rolling(4, min_periods=2)
            .sum()
            .reset_index(level=0, drop=True)
            .shift(-4)
        )
    mkt = df.groupby("week_end", sort=False)["return_1w"].mean()
    mkt_4w = mkt.rolling(4, min_periods=2).sum().shift(1)
    df["mkt_return_1w"] = df["week_end"].map(mkt)
    df["mkt_mom_4w"] = df["week_end"].map(mkt_4w)
    return df


class DiscoveryContext:
    def __init__(self, liquid: list[str] | None = None) -> None:
        from run_idn_invest_trial import load_liquid_universe

        self.liquid = liquid or load_liquid_universe()
        self.panel = _load_panel(tuple(sorted(self.liquid)))


def tool_list_features(ctx: DiscoveryContext) -> dict[str, Any]:
    df = ctx.panel
    rows = []
    for col in sorted(set(CANDIDATE_SIGNALS) | set(df.columns)):
        if col in ("yahoo_symbol", "week_end", "country_iso3"):
            continue
        if col not in df.columns:
            continue
        nonnull = int(df[col].notna().sum())
        if nonnull < 50:
            continue
        rows.append(
            {
                "feature": col,
                "nonnull_rows": nonnull,
                "weeks": int(df.loc[df[col].notna(), "week_end"].nunique()),
                "is_target": col in TARGETS,
            }
        )
    return {"ok": True, "features": rows, "targets": list(TARGETS), "eras": list(ERA_NAMES)}


def tool_test_signal(
    ctx: DiscoveryContext,
    *,
    signal: str,
    target: str = "fwd_return_1w",
    long_top: bool = True,
    era: str = "full",
    include_portfolio: bool = True,
) -> dict[str, Any]:
    df = slice_era(ctx.panel, era)
    if signal not in df.columns:
        return {"ok": False, "error": f"unknown_signal:{signal}"}
    if target not in df.columns:
        return {"ok": False, "error": f"unknown_target:{target}"}
    ic = weekly_rank_ic(df, signal, target)
    qs = quintile_spread(df, signal, target, long_top=long_top)
    port: dict[str, Any] = {}
    if include_portfolio:

        def pick_fn(g: pd.DataFrame) -> pd.DataFrame:
            return g.nlargest(3, signal)

        pf = portfolio_weekly_returns(df, pick_fn)
        port = summarize_returns(pf["excess_ret"]) if not pf.empty else {}
    return {
        "ok": True,
        "signal": signal,
        "target": target,
        "era": era,
        "long_top": long_top,
        "ic": ic,
        "quintile_spread": qs,
        "top3_excess": port,
        "verdict": verdict_from_stats(
            tstat=qs.get("tstat"),
            weeks=qs.get("weeks", 0),
            mean_spread_pct=qs.get("mean_spread_pct"),
            sharpe=port.get("sharpe_weekly"),
            min_weeks=min_weeks_for_era(era),
        ),
    }


def tool_horse_race(
    ctx: DiscoveryContext,
    *,
    signals: list[str] | None = None,
    target: str = "fwd_return_1w",
    era: str = "full",
    long_top: bool = True,
) -> dict[str, Any]:
    sigs = signals or list(CANDIDATE_SIGNALS)
    rows = []
    for s in sigs:
        r = tool_test_signal(ctx, signal=s, target=target, long_top=long_top, era=era)
        if not r.get("ok"):
            continue
        rows.append(
            {
                "signal": s,
                "ic_t": r["ic"].get("tstat"),
                "spread_pct": r["quintile_spread"].get("mean_spread_pct"),
                "spread_t": r["quintile_spread"].get("tstat"),
                "top3_sharpe": (r.get("top3_excess") or {}).get("sharpe_weekly"),
                "verdict": r.get("verdict"),
            }
        )
    rows.sort(key=lambda x: (-(x.get("spread_t") or -999), -(x.get("ic_t") or -999)))
    return {"ok": True, "era": era, "target": target, "ranking": rows}


def tool_scan_candidates(
    ctx: DiscoveryContext,
    *,
    target: str = "fwd_return_1w",
    era: str = "full",
) -> dict[str, Any]:
    """Scan all known signals long-top and short-top (fade)."""
    rows = []
    for s in CANDIDATE_SIGNALS:
        for long_top, label in ((True, "long_top"), (False, "fade")):
            if s in ("entity_mention_rows", "mention_rank_pct", "trending_proxy_rank") and long_top:
                continue
            r = tool_test_signal(ctx, signal=s, target=target, long_top=long_top, era=era, include_portfolio=False)
            if not r.get("ok"):
                continue
            rows.append(
                {
                    "signal": s,
                    "direction": label,
                    "ic_t": r["ic"].get("tstat"),
                    "spread_pct": r["quintile_spread"].get("mean_spread_pct"),
                    "spread_t": r["quintile_spread"].get("tstat"),
                    "verdict": r.get("verdict"),
                }
            )
    rows.sort(key=lambda x: -(x.get("spread_t") or -999))
    return {"ok": True, "era": era, "target": target, "candidates": rows[:15]}


def tool_oos_stability(
    ctx: DiscoveryContext,
    *,
    signal: str,
    target: str = "fwd_return_1w",
    long_top: bool = True,
) -> dict[str, Any]:
    """IS vs OOS breakdown — key for reverse-engineering real edges."""
    out = {}
    for era_name, _, _ in build_eras(ctx.panel):
        out[era_name] = tool_test_signal(ctx, signal=signal, target=target, long_top=long_top, era=era_name)
    is_spread = (out.get(ERA_TRAIN) or {}).get("quintile_spread", {}).get("mean_spread_pct")
    oos_spread = (out.get(ERA_OOS) or {}).get("quintile_spread", {}).get("mean_spread_pct")
    stable = (
        is_spread is not None
        and oos_spread is not None
        and is_spread > 0
        and oos_spread > 0
        and (out.get(ERA_OOS) or {}).get("quintile_spread", {}).get("tstat", 0) or 0 > 0.5
    )
    return {
        "ok": True,
        "signal": signal,
        "long_top": long_top,
        "by_era": {k: {"verdict": v.get("verdict"), "spread_pct": v.get("quintile_spread", {}).get("mean_spread_pct")} for k, v in out.items()},
        "oos_stable": stable,
        "note": "True if positive spread in both train and oos_holdout",
    }


def tool_test_retail_strategy(ctx: DiscoveryContext, *, strategy_id: str, era: str = "full") -> dict[str, Any]:
    from idn_retail_strategies import PLAYBOOK, build_all_signals, event_study

    start, end = era_bounds(ctx.panel, era)
    start = start or str(ctx.panel["week_end"].min().date())
    end = end or str(ctx.panel["week_end"].max().date())
    from idn_spike_explainer import fetch_history

    close, vol = fetch_history(ctx.liquid + ["^JKSE"], start, end)
    if close.empty:
        return {"ok": False, "error": "no_prices"}
    signals = build_all_signals(close, vol, ctx.liquid)
    strat = next((s for s in PLAYBOOK if s.id == strategy_id), None)
    if not strat:
        return {"ok": False, "error": f"unknown_strategy:{strategy_id}"}
    flat = {dt: syms for dt, syms in signals.get(strat.id, {}).items() if syms}
    oos_start = time_cutoff(ctx.panel["week_end"]) if era == ERA_OOS else pd.Timestamp(start)
    es = event_study(flat, close, hold_days_list=(5, 10, 20), oos_start=pd.Timestamp(oos_start))
    return {
        "ok": True,
        "strategy_id": strategy_id,
        "jargon": strat.retail_jargon,
        "era": era,
        "event_study": es,
        "verdict": "reliable"
        if (es.get("by_horizon", {}).get("oos_5d", {}).get("tstat") or 0) >= 1.5
        else "conditional",
    }


def tool_list_retail_strategies(ctx: DiscoveryContext) -> dict[str, Any]:
    from idn_retail_strategies import PLAYBOOK

    return {
        "ok": True,
        "strategies": [{"id": s.id, "jargon": s.retail_jargon, "hold_days": s.hold_days} for s in PLAYBOOK],
    }


DISCOVERY_TOOL_SPECS: list[dict[str, Any]] = [
    {"name": "list_features", "description": "Available panel features and coverage.", "parameters": {"type": "object", "properties": {}}},
    {"name": "scan_candidates", "description": "Scan all candidate signals for predictive power.", "parameters": {"type": "object", "properties": {"target": {"type": "string"}, "era": {"type": "string"}}}},
    {"name": "horse_race", "description": "Rank signals head-to-head on IC and quintile spread.", "parameters": {"type": "object", "properties": {"signals": {"type": "array"}, "target": {"type": "string"}, "era": {"type": "string"}}}},
    {"name": "test_signal", "description": "Full test of one signal: IC, quintile spread, top-3 portfolio.", "parameters": {"type": "object", "properties": {"signal": {"type": "string"}, "target": {"type": "string"}, "long_top": {"type": "boolean"}, "era": {"type": "string"}}, "required": ["signal"]}},
    {"name": "oos_stability", "description": "IS vs OOS stability for a signal across eras.", "parameters": {"type": "object", "properties": {"signal": {"type": "string"}, "long_top": {"type": "boolean"}}, "required": ["signal"]}},
    {"name": "list_retail_strategies", "description": "Catalog of retail TA rules to event-study.", "parameters": {"type": "object", "properties": {}}},
    {"name": "test_retail_strategy", "description": "Event-study a retail playbook rule.", "parameters": {"type": "object", "properties": {"strategy_id": {"type": "string"}, "era": {"type": "string"}}, "required": ["strategy_id"]}},
]

_DISCOVERY_FNS = {
    "list_features": lambda ctx, **kw: tool_list_features(ctx),
    "scan_candidates": lambda ctx, **kw: tool_scan_candidates(ctx, **kw),
    "horse_race": lambda ctx, **kw: tool_horse_race(ctx, **kw),
    "test_signal": lambda ctx, **kw: tool_test_signal(ctx, **kw),
    "oos_stability": lambda ctx, **kw: tool_oos_stability(ctx, **kw),
    "list_retail_strategies": lambda ctx, **kw: tool_list_retail_strategies(ctx),
    "test_retail_strategy": lambda ctx, **kw: tool_test_retail_strategy(ctx, **kw),
}


def execute_discovery_tool(ctx: DiscoveryContext, name: str, args: dict[str, Any]) -> dict[str, Any]:
    fn = _DISCOVERY_FNS.get(name)
    if not fn:
        return {"ok": False, "error": f"unknown_tool:{name}"}
    try:
        return fn(ctx, **(args or {}))
    except Exception as exc:
        return {"ok": False, "error": str(exc), "tool": name}


def deterministic_discovery_scan(ctx: DiscoveryContext, *, include_retail: bool = False) -> dict[str, Any]:
    """Fast full scan without LLM — baseline reverse-engineering report."""
    report: dict[str, Any] = {
        "mode": "deterministic_scan",
        "features": tool_list_features(ctx),
        "scans": {},
        "oos_checks": [],
        "retail": [],
    }
    for era in ERA_NAMES:
        report["scans"][era] = tool_scan_candidates(ctx, era=era)
    top_signals = list(dict.fromkeys(
        c["signal"] for c in report["scans"]["full"].get("candidates", [])[:5]
    ))
    for sig in top_signals:
        direction = next(
            (c["direction"] for c in report["scans"]["full"]["candidates"] if c["signal"] == sig),
            "long_top",
        )
        report["oos_checks"].append(
            tool_oos_stability(ctx, signal=sig, long_top=(direction == "long_top"))
        )
    if include_retail:
        for sid in ("bbca_support_rsi", "bluechip_support", "banks_rsi_oversold"):
            report["retail"].append(tool_test_retail_strategy(ctx, strategy_id=sid, era="full"))
    else:
        report["retail"] = [
            {"strategy_id": "bbca_support_rsi", "verdict": "see_validation_suite", "note": "run with --include-retail"},
            {"strategy_id": "bluechip_support", "verdict": "see_validation_suite"},
        ]
    report["best_candidates"] = _rank_best(report)
    return report


def _rank_best(report: dict[str, Any]) -> dict[str, Any]:
    cands = (report.get("scans") or {}).get(ERA_OOS, {}).get("candidates", [])
    stable = [x for x in report.get("oos_checks", []) if x.get("oos_stable")]
    return {
        "oos_top": cands[:5],
        "oos_stable_signals": [s.get("signal") for s in stable],
        "retail_reliable": [
            r["strategy_id"] for r in report.get("retail", []) if r.get("verdict") == "reliable"
        ],
    }


def discovery_tools_prompt() -> str:
    return json.dumps(DISCOVERY_TOOL_SPECS, indent=2)
