#!/usr/bin/env python3
"""Backtest IDX analyst agent vs rules — point-in-time tool analysis.

Modes:
  - deterministic (default): tool pipeline only, fast, no API cost
  - llm: multi-turn agent on sample weeks (expensive)

Outputs:
  backtests/outputs/platform/idn_analyst_backtest/latest.json
  backtests/outputs/platform/idn_analyst_backtest/latest.md
"""

from __future__ import annotations

import argparse
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

from idn_analyst_agent import run_analyst_agent  # noqa: E402
from idn_analyst_tools import AnalystDataContext, deterministic_analyst_picks, deterministic_analyst_picks_panel  # noqa: E402
from idn_eval_splits import ERA_NAMES, ERA_OOS, build_eras, slice_era  # noqa: E402
from idn_sentiment_validation_lib import prepare_liquid_weekly, summarize_returns  # noqa: E402
from run_idn_invest_trial import load_liquid_universe  # noqa: E402

OUT = REPO / "backtests/outputs/platform/idn_analyst_backtest"
BROADCAST = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610/ticker_week_country_broadcast_panel.parquet"
ENTITY = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260611/ticker_week_entity_market_panel.parquet"


def _operator_rules_picks(g: pd.DataFrame, max_picks: int = 3) -> list[str]:
    avoids = set(g.loc[g["mention_rank_pct"] >= 0.8, "yahoo_symbol"].dropna())
    cand = g[(g["mom_4w"] > 0.05) & (~g["yahoo_symbol"].isin(avoids))].dropna(subset=["mom_4w"])
    return cand.nlargest(max_picks, "mom_4w")["yahoo_symbol"].tolist()


def _week_portfolio_return(picks: list[str], g: pd.DataFrame) -> float | None:
    if not picks:
        return None
    sub = g[g["yahoo_symbol"].isin(picks)]
    if sub.empty:
        return None
    return float(sub["fwd_return_1w"].mean())


def backtest_weekly(
    df: pd.DataFrame,
    liquid: list[str],
    *,
    era: str = ERA_OOS,
    mode: str = "deterministic",
    llm_sample: int = 0,
    llm_backend: str = "auto",
) -> dict[str, Any]:
    sub = slice_era(df, era)
    weeks = sorted(sub["week_end"].dropna().unique())
    if llm_sample > 0 and mode == "llm":
        rng = np.random.default_rng(42)
        weeks = sorted(rng.choice(weeks, size=min(llm_sample, len(weeks)), replace=False))

    rows: list[dict[str, Any]] = []
    for wk in weeks:
        g = sub[sub["week_end"] == wk].copy()
        if g["fwd_return_1w"].notna().sum() < 8:
            continue
        rules = _operator_rules_picks(g)
        rules_ret = _week_portfolio_return(rules, g)
        bench_ret = float(g["fwd_return_1w"].mean())

        ctx = AnalystDataContext(liquid=liquid, as_of=pd.Timestamp(wk))
        if mode == "llm":
            agent = run_analyst_agent(
                liquid=liquid,
                as_of=str(pd.Timestamp(wk).date()),
                seed_tickers=rules,
                rules_context={"pick": rules},
                backend=llm_backend,
                max_turns=8,
            )
            picks = [p["ticker"] for p in agent.get("operator_decision", {}).get("final_picks", [])]
            analyst_mode = agent.get("mode")
        else:
            det = deterministic_analyst_picks_panel(g, seed_tickers=rules, max_picks=3)
            picks = [p["ticker"] for p in det.get("picks", [])]
            analyst_mode = det.get("mode")

        analyst_ret = _week_portfolio_return(picks, g)
        rows.append(
            {
                "week_end": str(pd.Timestamp(wk).date()),
                "rules_picks": rules,
                "rules_ret_pct": round(rules_ret * 100, 3) if rules_ret is not None else None,
                "analyst_picks": picks,
                "analyst_ret_pct": round(analyst_ret * 100, 3) if analyst_ret is not None else None,
                "bench_ret_pct": round(bench_ret * 100, 3),
                "analyst_excess_pct": round((analyst_ret - bench_ret) * 100, 3)
                if analyst_ret is not None
                else None,
                "rules_excess_pct": round((rules_ret - bench_ret) * 100, 3)
                if rules_ret is not None
                else None,
                "analyst_mode": analyst_mode,
            }
        )

    rules_ex = pd.Series([r["rules_excess_pct"] for r in rows if r["rules_excess_pct"] is not None], dtype=float) / 100
    ana_ex = pd.Series([r["analyst_excess_pct"] for r in rows if r["analyst_excess_pct"] is not None], dtype=float) / 100
    return {
        "era": era,
        "mode": mode,
        "weeks_tested": len(rows),
        "rules": summarize_returns(rules_ex) if len(rules_ex) else {},
        "analyst": summarize_returns(ana_ex) if len(ana_ex) else {},
        "rows": rows,
        "verdict": _verdict(ana_ex, rules_ex),
    }


def _verdict(analyst: pd.Series, rules: pd.Series) -> str:
    if analyst.empty:
        return "insufficient_sample"
    a_sh = analyst.mean() / (analyst.std(ddof=1) + 1e-12) * math.sqrt(52) if len(analyst) > 1 else 0
    r_sh = rules.mean() / (rules.std(ddof=1) + 1e-12) * math.sqrt(52) if len(rules) > 1 else 0
    if a_sh > 0.5 and analyst.mean() > 0:
        return "conditional" if a_sh < 1.0 else "reliable"
    if a_sh > r_sh + 0.2:
        return "beats_rules_conditional"
    return "unreliable"


def write_md(result: dict[str, Any]) -> str:
    lines = [
        "# IDX analyst agent backtest",
        f"- built: {result.get('built_at_utc')}",
        f"- mode: {result.get('mode')}",
        f"- era: {result.get('era')}",
        f"- weeks: {result.get('weeks_tested')}",
        f"- verdict: **{result.get('verdict')}**",
        "",
        "## Excess vs liquid equal-weight (weekly)",
    ]
    for label in ("rules", "analyst"):
        s = result.get(label) or {}
        lines.append(
            f"- **{label}**: mean {s.get('mean_weekly_pct')}%/wk | Sharpe {s.get('sharpe_weekly')} | "
            f"terminal {s.get('terminal_x')}x | hit {s.get('hit_rate_pct')}%"
        )
    lines.append("")
    lines.append("## Recent weeks")
    for r in (result.get("rows") or [])[-8:]:
        lines.append(
            f"- {r['week_end']}: rules {r['rules_picks']} → {r['rules_ret_pct']}% | "
            f"analyst {r['analyst_picks']} → {r['analyst_ret_pct']}% | bench {r['bench_ret_pct']}%"
        )
    lines.append("")
    lines.append(
        "_Deterministic mode = tool pipeline (screen→analyze→score). "
        "LLM mode = agent calls same tools then decides._"
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--era", default=ERA_OOS, choices=list(ERA_NAMES))
    ap.add_argument("--mode", choices=["deterministic", "llm"], default="deterministic")
    ap.add_argument("--llm-sample", type=int, default=0, help="Sample N weeks for LLM mode (0=all, expensive)")
    ap.add_argument("--llm-backend", default="auto")
    args = ap.parse_args()

    liquid = load_liquid_universe()
    df = prepare_liquid_weekly(BROADCAST, ENTITY, liquid)
    result = backtest_weekly(
        df,
        liquid,
        era=args.era,
        mode=args.mode,
        llm_sample=args.llm_sample,
        llm_backend=args.llm_backend,
    )
    result["built_at_utc"] = datetime.now(UTC).isoformat()
    result["mode"] = args.mode

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    (OUT / "latest.md").write_text(write_md(result), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("era", "mode", "weeks_tested", "verdict", "rules", "analyst")}, indent=2))
    print(f"\nWrote {OUT / 'latest.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
