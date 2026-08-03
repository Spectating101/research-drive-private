#!/usr/bin/env python3
"""Empirical validation — IDX public sentiment + operator signal reliability.

Tests (honest scope):
  1. Historical weekly panel: attention fade, momentum, trending-proxy (prior-week chase)
  2. Operator rules weekly portfolio vs liquid equal-weight
  3. Retail playbook event studies (BBCA support+RSI, banks)
  4. Live RapidAPI cross-check: API RSI vs local RSI
  5. Sentiment snapshot forward test (when multi-day history exists)

Outputs:
  backtests/outputs/platform/idn_sentiment_validation/latest.json
  backtests/outputs/platform/idn_sentiment_validation/latest.md

Note: RapidAPI trending/followers history starts accumulating from first collector run.
      Until >=8 weeks of snapshots, trending uses *prior-week return rank* as proxy.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime
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
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from idn_eval_splits import ERA_NAMES, ERA_OOS, ERA_TRAIN, build_eras, min_weeks_for_era, split_meta, time_cutoff  # noqa: E402
from idn_sentiment_validation_lib import (  # noqa: E402
    portfolio_weekly_returns,
    prepare_liquid_weekly,
    quintile_spread,
    summarize_returns,
    verdict_from_stats,
    weekly_rank_ic,
    slice_era,
)
from idn_spike_explainer import fetch_history  # noqa: E402
from run_idn_invest_trial import load_liquid_universe  # noqa: E402

OUT = REPO / "backtests/outputs/platform/idn_sentiment_validation"
BROADCAST = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610/ticker_week_country_broadcast_panel.parquet"
ENTITY = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260611/ticker_week_entity_market_panel.parquet"
SENTIMENT_PANEL = REPO / "data_lake/sentiment/idn_public_sentiment_panel.parquet"
TRENDING_HIST = REPO / "data_lake/sentiment/idn_rapidapi_trending_history.parquet"
INDEX = "^JKSE"


def _operator_pick_fn(g: pd.DataFrame) -> pd.DataFrame:
    avoids = set(g.loc[g["mention_rank_pct"] >= 0.8, "yahoo_symbol"].dropna())
    cand = g[(g["mom_4w"] > 0.05) & (~g["yahoo_symbol"].isin(avoids))].dropna(subset=["mom_4w"])
    return cand.nlargest(3, "mom_4w")


def _fade_headline_pick_fn(g: pd.DataFrame) -> pd.DataFrame:
    """Long LOW mention names with positive mom (contrarian attention)."""
    cand = g[(g["mention_rank_pct"] <= 0.4) & (g["mom_4w"] > 0.05)].dropna(subset=["mom_4w", "mention_rank_pct"])
    return cand.nlargest(3, "mom_4w")


def _trending_proxy_pick_fn(g: pd.DataFrame) -> pd.DataFrame:
    """Prior-week winners (simulates app trending chase)."""
    return g[g["trending_proxy_rank"] >= 0.9].dropna(subset=["prior_return_1w"])


def validate_historical_weekly(df: pd.DataFrame) -> dict[str, Any]:
    signals = [
        ("mom_4w_long", "mom_4w", "fwd_return_1w", True, "Long top quintile 4w momentum"),
        ("mom_4w_long_4w", "mom_4w", "fwd_return_4w", True, "Long top quintile mom → 4w fwd"),
        ("mention_fade", "entity_mention_rows", "fwd_return_1w", False, "Fade top mention (long bottom quintile)"),
        ("trending_proxy_chase", "prior_return_1w", "fwd_return_1w", True, "Chase prior-week winners (trending proxy)"),
        ("quiet_momentum", "mom_4w", "fwd_return_1w", True, "Mom leaders NOT in top mention quintile"),
    ]
    rows: list[dict[str, Any]] = []
    holdout_weeks = int(slice_era(df, ERA_OOS)["week_end"].nunique()) if len(df) else 0
    for era_name in ERA_NAMES:
        sub = slice_era(df, era_name)
        for name, sig, tgt, long_top, desc in signals:
            if sig not in sub.columns or sub[sig].notna().sum() < 100:
                continue
            if name == "quiet_momentum":
                qs = quintile_spread(
                    sub[sub["mention_rank_pct"] < 0.8],
                    "mom_4w",
                    tgt,
                    long_top=True,
                )
                ic = weekly_rank_ic(sub[sub["mention_rank_pct"] < 0.8], "mom_4w", tgt)
            elif name == "mention_fade":
                qs = quintile_spread(sub, sig, tgt, long_top=False)
                ic = weekly_rank_ic(sub, sig, tgt)
            else:
                qs = quintile_spread(sub, sig, tgt, long_top=long_top)
                ic = weekly_rank_ic(sub, sig, tgt)

            port = None
            if name == "mom_4w_long":
                pf = portfolio_weekly_returns(sub, _operator_pick_fn)
                port = summarize_returns(pf["pick_ret"]) if not pf.empty else {}
            elif name == "trending_proxy_chase":
                pf = portfolio_weekly_returns(sub, _trending_proxy_pick_fn, max_picks=5)
                port = summarize_returns(pf["pick_ret"]) if not pf.empty else {}

            rows.append(
                {
                    "signal": name,
                    "description": desc,
                    "era": era_name,
                    "entity_weeks_holdout": holdout_weeks if era_name == ERA_OOS else None,
                    "ic": ic,
                    "quintile_spread": qs,
                    "operator_portfolio": port,
                    "verdict": verdict_from_stats(
                        tstat=qs.get("tstat"),
                        weeks=qs.get("weeks", 0),
                        mean_spread_pct=qs.get("mean_spread_pct"),
                        sharpe=(port or {}).get("sharpe_weekly"),
                        min_weeks=min_weeks_for_era(era_name),
                    ),
                }
            )
    return {"tests": rows}


def validate_operator_rules(df: pd.DataFrame) -> dict[str, Any]:
    by_era: dict[str, Any] = {}
    for era_name in ERA_NAMES:
        sub = slice_era(df, era_name)
        pf = portfolio_weekly_returns(sub, _operator_pick_fn)
        if pf.empty:
            continue
        pick = summarize_returns(pf["pick_ret"])
        bench = summarize_returns(pf["bench_ret"])
        ex = summarize_returns(pf["excess_ret"])
        by_era[era_name] = {
            "picks": pick,
            "liquid_eq": bench,
            "excess": ex,
            "sample_weeks": pf.tail(5).to_dict(orient="records"),
            "verdict": (
                "conditional"
                if (ex.get("sharpe_weekly") or 0) >= 0.5 and (ex.get("mean_weekly_pct") or 0) > 0
                else "unreliable"
                if ex.get("weeks", 0) >= min_weeks_for_era(era_name)
                else "insufficient_sample"
            ),
        }
    return by_era


def validate_retail_playbook(liquid: list[str]) -> dict[str, Any]:
    from idn_retail_strategies import PLAYBOOK, build_all_signals, event_study

    end = datetime.now(UTC).date().isoformat()
    close, vol = fetch_history(liquid + [INDEX], "2019-01-01", end)
    if close.empty:
        return {"available": False}
    signals = build_all_signals(close, vol, liquid)
    oos = time_cutoff(close.index)
    out: dict[str, Any] = {}
    for strat in PLAYBOOK:
        if strat.id not in {"bbca_support_rsi", "banks_rsi_oversold", "bluechip_support", "rsi30_bounce"}:
            continue
        flat: dict[pd.Timestamp, list[str]] = {}
        for dt, syms in signals.get(strat.id, {}).items():
            if syms:
                flat[dt] = syms
        es = event_study(flat, close, hold_days_list=(5, 10, 20), oos_start=oos)
        out[strat.id] = {
            "jargon": strat.retail_jargon,
            "event_study": es,
            "verdict": "reliable"
            if (es.get("by_horizon", {}).get("oos_5d", {}).get("tstat") or 0) >= 1.5
            and (es.get("by_horizon", {}).get("oos_5d", {}).get("mean_pct") or 0) > 0
            else "conditional"
            if es.get("n", 0) >= 20
            else "insufficient_sample",
        }
    return {"available": True, "strategies": out}


def validate_api_rsi(liquid: list[str], sample: int = 8) -> dict[str, Any]:
    from idn_rapidapi_idx import get, slim_technical

    syms = ["BBCA", "BBRI", "BMRI", "BUMI", "TPIA", "UNVR", "MAPI", "ISAT"][:sample]
    end = datetime.now(UTC).date().isoformat()
    close, _ = fetch_history([f"{s}.JK" for s in syms], "2025-01-01", end)
    rows = []
    for s in syms:
        sym = f"{s}.JK"
        if sym not in close.columns:
            continue
        px = close[sym].dropna()
        ret = px.pct_change()
        delta = ret.iloc[-14:]
        up = delta.clip(lower=0).mean()
        down = (-delta.clip(upper=0)).mean()
        local_rsi = 100 - 100 / (1 + up / down) if down and down > 0 else None
        api = slim_technical(get(f"/api/analysis/technical/{s}", cache_ttl_sec=86400))
        api_rsi = (api or {}).get("rsi")
        diff = abs(local_rsi - api_rsi) if local_rsi and api_rsi else None
        rows.append(
            {
                "symbol": sym,
                "local_rsi": round(local_rsi, 2) if local_rsi else None,
                "api_rsi": api_rsi,
                "abs_diff": round(diff, 2) if diff is not None else None,
            }
        )
    diffs = [r["abs_diff"] for r in rows if r["abs_diff"] is not None]
    return {
        "n": len(rows),
        "mean_abs_rsi_diff": round(float(np.mean(diffs)), 2) if diffs else None,
        "max_abs_rsi_diff": round(float(np.max(diffs)), 2) if diffs else None,
        "reliable": bool(diffs) and float(np.mean(diffs)) < 8.0,
        "rows": rows,
        "note": "Live cross-check only — confirms API technical layer matches yfinance RSI.",
    }


def validate_sentiment_snapshots() -> dict[str, Any]:
    if not SENTIMENT_PANEL.exists():
        return {"available": False, "reason": "no_panel"}
    df = pd.read_parquet(SENTIMENT_PANEL)
    if df.empty or "collected_at_utc" not in df.columns:
        return {"available": False, "reason": "empty"}
    df["snapshot_date"] = pd.to_datetime(df["collected_at_utc"]).dt.date.astype(str)
    n_days = df["snapshot_date"].nunique()
    out = {"available": True, "snapshot_days": int(n_days), "rows": int(len(df))}
    if n_days < 2:
        out["verdict"] = "accumulating"
        out["note"] = "Need >=2 daily snapshots for forward event study. Run collector daily."
        return out
    # forward test placeholder when history grows
    out["verdict"] = "pending_history"
    return out


def validate_trending_history(liquid: list[str] | None = None) -> dict[str, Any]:
    if not TRENDING_HIST.exists():
        return {"available": False, "rows": 0, "note": "Run idn_social_sentiment_collector daily to build history."}
    h = pd.read_parquet(TRENDING_HIST)
    out: dict[str, Any] = {
        "available": True,
        "rows": int(len(h)),
        "snapshot_days": int(h["snapshot_date"].nunique()) if "snapshot_date" in h.columns else 0,
        "symbols": int(h["yahoo_symbol"].nunique()) if "yahoo_symbol" in h.columns else 0,
    }
    days = out["snapshot_days"]
    if days < 2:
        out["forward_test"] = {"verdict": "accumulating", "note": f"Need >=2 snapshot days (have {days})"}
        return out

    try:
        from idn_spike_explainer import fetch_history

        liquid = liquid or []
        h = h.copy()
        h["snapshot_date"] = pd.to_datetime(h["snapshot_date"])
        dates = sorted(h["snapshot_date"].unique())
        syms = sorted(h["yahoo_symbol"].dropna().unique().tolist())
        if not syms:
            out["forward_test"] = {"verdict": "insufficient_sample"}
            return out
        start = str(dates[0].date())
        end = datetime.now(UTC).date().isoformat()
        close, _ = fetch_history(syms, start, end)
        if close.empty:
            out["forward_test"] = {"verdict": "no_prices"}
            return out
        daily_ret = close.pct_change()
        spreads: list[float] = []
        for i in range(1, len(dates)):
            d0, d1 = dates[i - 1], dates[i]
            top = h[h["snapshot_date"] == d0].nsmallest(5, "trending_rank")["yahoo_symbol"].tolist()
            top = [s for s in top if s in daily_ret.columns]
            if not top:
                continue
            day_ret = daily_ret.loc[daily_ret.index >= d1]
            if day_ret.empty:
                continue
            row = day_ret.iloc[0]
            spreads.append(float(row[top].mean() - row.mean()))
        if len(spreads) < 2:
            out["forward_test"] = {"verdict": "accumulating", "days": days, "spreads": len(spreads)}
            return out
        a = np.array(spreads) * 100
        mu = float(a.mean())
        sd = float(a.std(ddof=1))
        t = mu / (sd / math.sqrt(len(a)) + 1e-12) if sd > 0 else None
        out["forward_test"] = {
            "verdict": "conditional" if t and abs(t) >= 1.0 else "unreliable",
            "mean_top5_minus_eq_pct": round(mu, 3),
            "tstat": round(t, 3) if t is not None else None,
            "days": int(len(a)),
            "note": "Top-5 trending (prior snapshot) vs cross-section next day.",
        }
    except Exception as exc:
        out["forward_test"] = {"verdict": "error", "error": str(exc)}
    return out


def overall_verdict(results: dict[str, Any]) -> dict[str, Any]:
    by_signal: dict[str, str] = {}
    rank = {"reliable": 3, "conditional": 2, "insufficient_sample": 1, "unreliable": 0}
    for block in results.get("historical_weekly", {}).get("tests", []):
        if block.get("era") != "full":
            continue
        name = block["signal"]
        v = block.get("verdict", "unknown")
        if rank.get(v, -1) > rank.get(by_signal.get(name, ""), -1):
            by_signal[name] = v

    reliable = [k for k, v in by_signal.items() if v == "reliable"]
    conditional = [k for k, v in by_signal.items() if v == "conditional"]
    unreliable = [k for k, v in by_signal.items() if v == "unreliable"]
    insufficient = [k for k, v in by_signal.items() if v == "insufficient_sample"]

    op = results.get("operator_rules", {}).get("full", {})
    retail = results.get("retail_playbook", {}).get("strategies", {})

    summary = {
        "reliable_signals": reliable,
        "conditional_signals": conditional,
        "unreliable_signals": unreliable,
        "insufficient_sample": insufficient,
        "operator_rules_full_verdict": op.get("verdict"),
        "retail_bbca_verdict": retail.get("bbca_support_rsi", {}).get("verdict"),
        "rapidapi_rsi_crosscheck": results.get("api_rsi_crosscheck", {}).get("reliable"),
        "honest_limits": [
            "RapidAPI trending/followers: forward collection only (no vendor history).",
            "Entity mention fade: check train vs holdout; entity layer may be thin in recent weeks.",
            "Trending-proxy chase tests whether 'hot last week' persists — expect mean reversion.",
            "LLM operator layer not backtested here — only quant rules + sentiment inputs.",
        ],
    }
    return summary


def write_md(results: dict[str, Any]) -> str:
    ov = results.get("overall", {})
    lines = [
        "# IDX sentiment & operator signal validation",
        f"- built: {results.get('built_at_utc')}",
        "",
        "## Overall",
        f"- Reliable: {', '.join(ov.get('reliable_signals', [])) or 'none'}",
        f"- Conditional: {', '.join(ov.get('conditional_signals', [])) or 'none'}",
        f"- Unreliable: {', '.join(ov.get('unreliable_signals', [])) or 'none'}",
        f"- Operator rules (full sample): **{ov.get('operator_rules_full_verdict')}**",
        f"- BBCA retail rule: **{ov.get('retail_bbca_verdict')}**",
        f"- API RSI cross-check: **{ov.get('rapidapi_rsi_crosscheck')}**",
        "",
        "## Honest limits",
    ]
    for x in ov.get("honest_limits", []):
        lines.append(f"- {x}")
    lines.append("")
    lines.append("## Historical weekly signals")
    for t in results.get("historical_weekly", {}).get("tests", []):
        qs = t.get("quintile_spread", {})
        ic = t.get("ic", {})
        lines.append(
            f"- **{t['signal']}** ({t['era']}): verdict={t['verdict']} | "
            f"IC t={ic.get('tstat')} | Q5-Q1 spread={qs.get('mean_spread_pct')}%/wk (t={qs.get('tstat')}, n={qs.get('weeks')})"
        )
    lines.append("")
    lines.append("## Operator rules portfolio")
    for era, block in results.get("operator_rules", {}).items():
        ex = block.get("excess", {})
        lines.append(
            f"- **{era}**: excess weekly {ex.get('mean_weekly_pct')}% | Sharpe {ex.get('sharpe_weekly')} | "
            f"terminal {ex.get('terminal_x')}x | verdict={block.get('verdict')}"
        )
    lines.append("")
    lines.append("## Retail playbook event studies")
    retail = results.get("retail_playbook", {})
    if retail.get("skipped"):
        lines.append("- skipped")
    elif retail.get("available"):
        for sid, block in (retail.get("strategies") or {}).items():
            bh = (block.get("event_study") or {}).get("by_horizon") or {}
            oos5 = bh.get("oos_5d", {})
            lines.append(
                f"- **{sid}** ({block.get('jargon')}): verdict={block.get('verdict')} | "
                f"OOS 5d {oos5.get('mean_pct')}% (t={oos5.get('tstat')}, n={oos5.get('n')})"
            )
    else:
        lines.append("- not available")
    lines.append("")
    snap = results.get("sentiment_snapshots") or {}
    trend = results.get("trending_history") or {}
    lines.append("## Data accumulation")
    lines.append(f"- Sentiment snapshots: {snap.get('snapshot_days', 0)} days ({snap.get('verdict', 'n/a')})")
    lines.append(f"- Trending history rows: {trend.get('rows', 0)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-retail", action="store_true", help="Skip slow retail playbook event study.")
    ap.add_argument("--skip-api-rsi", action="store_true", help="Skip live RapidAPI RSI cross-check.")
    args = ap.parse_args()

    liquid = load_liquid_universe()
    df = prepare_liquid_weekly(BROADCAST, ENTITY, liquid)

    results: dict[str, Any] = {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "liquid_names": len(liquid),
        "weekly_rows": int(len(df)),
        "week_span": [str(df["week_end"].min().date()), str(df["week_end"].max().date())],
        "split": split_meta(df),
        "entity_weeks_holdout": int(slice_era(df, ERA_OOS)["week_end"].nunique()),
    }
    results["historical_weekly"] = validate_historical_weekly(df)
    results["operator_rules"] = validate_operator_rules(df)
    results["retail_playbook"] = (
        {"skipped": True} if args.skip_retail else validate_retail_playbook(liquid)
    )
    results["api_rsi_crosscheck"] = (
        {"skipped": True} if args.skip_api_rsi else validate_api_rsi(liquid)
    )
    results["sentiment_snapshots"] = validate_sentiment_snapshots()
    results["trending_history"] = validate_trending_history(liquid)
    results["overall"] = overall_verdict(results)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8")
    (OUT / "latest.md").write_text(write_md(results), encoding="utf-8")
    print(json.dumps(results["overall"], indent=2))
    print(f"\nWrote {OUT / 'latest.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
