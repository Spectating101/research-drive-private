#!/usr/bin/env python3
"""Reverse-engineer monthly (4w) predictors from the full research panel.

Unlike the monthly horse-race (pre-built rules), this scans *all* numeric
panel features, ranks OOS predictors, and emits a composite indicator recipe.

Outputs:
  backtests/outputs/idn_monthly_pattern_discovery/latest.json
  backtests/outputs/idn_monthly_pattern_discovery/latest.md

Example:
  python scripts/run_idn_monthly_pattern_discovery.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO / "scripts"))

from idn_eval_splits import ERA_NAMES, ERA_OOS, slice_era, split_meta, time_cutoff  # noqa: E402
from idn_pattern_mining_lib import (  # noqa: E402
    backtest_composite,
    build_composite_score,
    discover_numeric_features,
    indicator_recipe,
    scan_all_features,
    select_oos_components,
    test_feature,
)
from idn_sentiment_validation_lib import summarize_returns  # noqa: E402
from idn_signal_discovery_tools import DiscoveryContext  # noqa: E402
from run_idn_invest_trial import load_liquid_universe  # noqa: E402

OUT = REPO / "backtests/outputs/idn_monthly_pattern_discovery"
TARGET = "fwd_return_4w"
HORIZON = "4w (~20 trading days)"


def render_md(report: dict[str, Any]) -> str:
    ind = report.get("indicator", {})
    lines = [
        "# IDX monthly pattern discovery (reverse engineered)",
        "",
        f"**Generated:** {report['generated_utc']}",
        f"**Target:** `{TARGET}` | **Horizon:** {HORIZON}",
        f"**Features scanned:** {report['n_features_scanned']} (not hand-picked 7)",
        "",
        "## Honest scope",
        "",
        "- Horse-race scripts test **pre-built rules** (fade top3, mom chase, regime).",
        "- **This** scans the panel, ranks predictors, builds a **composite z-score indicator**.",
        "- Retail TA events are separate (binary triggers) — not in this scan.",
        "",
        "## OOS holdout top discovered predictors",
        "",
        "| Rank | Feature | Direction | Spread 4w | t-stat | Weeks |",
        "|------|---------|-----------|-----------|--------|-------|",
    ]
    for i, r in enumerate(report.get("oos_top", [])[:15], 1):
        lines.append(
            f"| {i} | `{r['signal']}` | {r['direction']} | "
            f"{r.get('spread_pct', 0):+.2f}% | {r.get('spread_t')} | {r.get('weeks')} |"
        )
    lines.extend(["", "## Composite indicator (built from discovery)", ""])
    lines.append(f"**ID:** `{ind.get('indicator_id')}`")
    lines.append(f"**Entry:** {ind.get('entry')} | **Hold:** {ind.get('hold_days')}d")
    lines.extend(["", "**Components:**"])
    for c in ind.get("components", []):
        lines.append(f"- {c.get('human')} (OOS t={c.get('oos_spread_t')})")
    bt = report.get("composite_backtest", {})
    lines.extend(
        [
            "",
            "## Composite backtest (top-3 weekly, 4w forward)",
            "",
            f"- **Full:** pick mean {bt.get('full_pick_mean_pct'):+.2f}% | "
            f"excess {bt.get('full_excess_mean_pct'):+.2f}% | t_excess={bt.get('full_excess_t')}",
            f"- **OOS holdout:** pick mean {bt.get('oos_pick_mean_pct'):+.2f}% | "
            f"excess {bt.get('oos_excess_mean_pct'):+.2f}% | t_excess={bt.get('oos_excess_t')}",
            "",
            "## vs naive fade_1w_top3 (pre-built rule)",
            "",
            f"- Pre-built fade excess OOS: {report.get('naive_fade_oos_excess_pct')}% (for comparison only)",
        ]
    )
    return "\n".join(lines)


def _portfolio_stats(pf: pd.DataFrame) -> dict[str, Any]:
    if pf.empty:
        return {}
    ex = pf["excess_ret"] * 100
    pick = pf["pick_ret"] * 100
    sd = float(ex.std(ddof=1)) if len(ex) > 1 else 0.0
    return {
        "pick_mean_pct": round(float(pick.mean()), 3),
        "excess_mean_pct": round(float(ex.mean()), 3),
        "excess_t": round(float(ex.mean() / (sd / (len(ex) ** 0.5) + 1e-12)), 3) if sd > 0 else None,
        "weeks": len(pf),
    }


def main() -> int:
    from idn_panel_lib import load_research_universe

    liquid = load_research_universe(mode="tradable")
    ctx = DiscoveryContext(liquid=liquid)
    df = ctx.panel
    features = discover_numeric_features(df)
    scans: dict[str, list[dict[str, Any]]] = {}
    for era in ERA_NAMES:
        scans[era] = scan_all_features(df, features, target=TARGET, era=era)

    components = select_oos_components(scans, max_components=3, min_oos_t=1.5)
    if not components:
        top = scans.get(ERA_OOS, [])[:1]
        if top:
            components = [
                {
                    "signal": top[0]["signal"],
                    "direction": top[0]["direction"],
                    "weight": 1.0,
                    "oos_spread_pct": top[0].get("spread_pct"),
                    "oos_spread_t": top[0].get("spread_t"),
                }
            ]

    scored = build_composite_score(df, components)
    pf_full = backtest_composite(scored, target=TARGET)
    oos_cut = time_cutoff(df["week_end"])
    pf_oos = pf_full[pf_full["week_end"] >= oos_cut] if not pf_full.empty else pf_full

    # naive pre-built fade for comparison
    from idn_monthly_horse_race_lib import portfolio_4w_returns

    naive = portfolio_4w_returns(df, lambda g: g.nsmallest(3, "return_1w"))
    naive_oos = naive[naive["week_end"] >= oos_cut] if not naive.empty else naive
    naive_oos_ex = round(float(naive_oos["excess_ret"].mean() * 100), 3) if not naive_oos.empty else None

    indicator = indicator_recipe(components, target=TARGET, horizon=HORIZON)
    for c, comp in zip(indicator["components"], components):
        c["oos_spread_t"] = comp.get("oos_spread_t")

    full_bt = _portfolio_stats(pf_full)
    oos_bt = _portfolio_stats(pf_oos)

    report: dict[str, Any] = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "target": TARGET,
        "horizon": HORIZON,
        "n_features_scanned": len(features),
        "features_scanned": features,
        "scans": scans,
        "split": split_meta(df),
        "oos_top": scans.get(ERA_OOS, [])[:20],
        "selected_components": components,
        "indicator": indicator,
        "composite_backtest": {
            "full_pick_mean_pct": full_bt.get("pick_mean_pct"),
            "full_excess_mean_pct": full_bt.get("excess_mean_pct"),
            "full_excess_t": full_bt.get("excess_t"),
            "oos_pick_mean_pct": oos_bt.get("pick_mean_pct"),
            "oos_excess_mean_pct": oos_bt.get("excess_mean_pct"),
            "oos_excess_t": oos_bt.get("excess_t"),
            "full_summary": summarize_returns(pf_full["excess_ret"]) if not pf_full.empty else {},
            "oos_summary": summarize_returns(pf_oos["excess_ret"]) if not pf_oos.empty else {},
        },
        "naive_fade_oos_excess_pct": naive_oos_ex,
        "methodology": {
            "step1": "Enumerate numeric panel features (exclude targets/leakage)",
            "step2": "Quintile spread + IC per feature long and fade, per era",
            "step3": "Select OOS holdout winners with t>=1.5, direction stable vs train",
            "step4": "Composite = weighted cross-sectional z-scores; long top 3 weekly",
            "not_done": ["nonlinear combos", "ML", "transaction costs", "full 110-col entity panel merge"],
        },
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (OUT / "latest.md").write_text(render_md(report), encoding="utf-8")
    print(json.dumps({"ok": True, "indicator": indicator["indicator_id"], "components": components, "out": str(OUT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
