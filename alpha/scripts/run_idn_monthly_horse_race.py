#!/usr/bin/env python3
"""Horse-race IDX strategies at monthly (~4w) horizon — wins, not year-holds.

Outputs:
  backtests/outputs/idn_monthly_horse_race/latest.json
  backtests/outputs/idn_monthly_horse_race/latest.md

Example:
  python scripts/run_idn_monthly_horse_race.py
"""

from __future__ import annotations

import json
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
sys.path.insert(0, str(REPO / "scripts"))

from idn_eval_splits import ERA_FULL, ERA_OOS, build_eras, split_meta  # noqa: E402
from idn_monthly_horse_race_lib import (  # noqa: E402
    build_playbook,
    ensure_fwd_4w,
    era_filter,
    hybrid_monthly_rotation,
    portfolio_4w_returns,
    quintile_spread_4w,
    rank_strategies,
    regime_timed_returns,
    retail_event_stats_from_validation,
    score_series,
)
from idn_regime_lib import bank_equal_weight_series, fetch_and_cache  # noqa: E402
from idn_sentiment_validation_lib import prepare_liquid_weekly  # noqa: E402
from run_idn_invest_trial import load_liquid_universe  # noqa: E402

OUT = REPO / "backtests/outputs/idn_monthly_horse_race"
BROADCAST = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610/ticker_week_country_broadcast_panel.parquet"
ENTITY = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260611/ticker_week_entity_market_panel.parquet"
VALIDATION = REPO / "backtests/outputs/platform/idn_sentiment_validation/latest.json"


def _era_scores(series: pd.Series) -> dict[str, Any]:
    frame = pd.DataFrame({"date": pd.to_datetime(series.index)})
    out: dict[str, Any] = {}
    for era_name, start, end in build_eras(frame, time_col="date"):
        idx = era_filter(series.index, start, end)
        sub = series.reindex(idx).dropna()
        stats = score_series(sub * 100)
        out[era_name] = stats
    return out


def _strategy_row(
    name: str,
    category: str,
    series: pd.Series,
    *,
    description: str = "",
) -> dict[str, Any]:
    eras = _era_scores(series)
    full = eras.get("full", {})
    return {
        "name": name,
        "category": category,
        "description": description,
        "horizon": "4w (~20 trading days)",
        "eras": eras,
        "full_mean_pct": full.get("mean_pct"),
        "full_tstat": full.get("tstat"),
        "oos_holdout_mean_pct": (eras.get(ERA_OOS) or {}).get("mean_pct"),
        "oos_holdout_tstat": (eras.get(ERA_OOS) or {}).get("tstat"),
    }


def _cross_section_strategies(panel: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    eras_def = build_eras(panel)

    def _port_row(name: str, cat: str, desc: str, pr: pd.DataFrame) -> None:
        if pr.empty:
            return
        eras: dict[str, Any] = {}
        for era_name, start, end in eras_def:
            idx = era_filter(pr["week_end"], start, end)
            sub = pr.loc[pr["week_end"].isin(idx)]
            eras[era_name] = score_series(sub["pick_ret"] * 100)
            eras[era_name]["excess_mean_pct"] = round(float(sub["excess_ret"].mean() * 100), 3) if len(sub) else None
        rows.append(
            {
                "name": name,
                "category": cat,
                "description": desc,
                "horizon": "4w",
                "eras": eras,
                "full_mean_pct": (eras.get(ERA_FULL) or {}).get("mean_pct"),
                "full_tstat": (eras.get(ERA_FULL) or {}).get("tstat"),
                "oos_holdout_mean_pct": (eras.get(ERA_OOS) or {}).get("mean_pct"),
                "oos_holdout_tstat": (eras.get(ERA_OOS) or {}).get("tstat"),
            }
        )

    spreads: list[dict[str, Any]] = []
    for era_name, start, end in eras_def:
        idx = era_filter(panel["week_end"], start, end)
        sub = panel.loc[panel["week_end"].isin(idx)]
        for sig_name, col, long_top in (
            ("mom4_quintile_long", "mom_4w", True),
            ("return_1w_fade_quintile", "return_1w", False),
            ("return_1w_chase_quintile", "return_1w", True),
        ):
            if col not in sub.columns:
                continue
            q = quintile_spread_4w(sub, col, long_top=long_top)
            spreads.append({"era": era_name, "signal": sig_name, **q})

    rows.append(
        {
            "name": "cross_section_spreads",
            "category": "signals",
            "description": "Top-minus-bottom quintile 4w forward spreads",
            "spreads": spreads,
        }
    )

    _port_row(
        "mom4_top3",
        "picks",
        "Long top 3 names with mom_4w > 5%",
        portfolio_4w_returns(
            panel,
            lambda g: g[g["mom_4w"] > 0.05].nlargest(3, "mom_4w"),
        ),
    )
    _port_row(
        "fade_1w_top3",
        "picks",
        "Long bottom 3 prior-week return (reversal)",
        portfolio_4w_returns(panel, lambda g: g.nsmallest(3, "return_1w")),
    )
    _port_row(
        "chase_1w_top3",
        "picks",
        "Long top 3 prior-week return",
        portfolio_4w_returns(panel, lambda g: g.nlargest(3, "return_1w")),
    )
    _port_row(
        "liquid_ew",
        "benchmark",
        "Equal-weight liquid 50 forward 4w",
        portfolio_4w_returns(panel, lambda g: g, max_picks=999).assign(
            pick_ret=lambda x: x["bench_ret"]
        ),
    )
    return rows


def render_md(report: dict[str, Any]) -> str:
    pb = report.get("playbook", {})
    lines = [
        "# IDX monthly return horse race",
        "",
        f"**Generated:** {report['generated_utc']}",
        f"**Horizon:** ~4 weeks (20 trading days) — **not** year-hold",
        "",
        "## Playbook",
        "",
    ]
    for _, text in pb.items():
        lines.append(f"- {text}")
    lines.extend(
        [
            "",
            "## IHSG calendar month baseline",
            "",
            f"- Mean: **{report['ihsg_calendar_month']['mean_pct']:+.2f}%** | "
            f"Median: **{report['ihsg_calendar_month']['median_pct']:+.2f}%** | "
            f"Hit+: **{report['ihsg_calendar_month']['hit_positive_pct']:.0f}%**",
            "",
            "## Top OOS holdout strategies (4w)",
            "",
            "| Rank | Strategy | Mean 4w | t-stat | Hit+ | Category |",
            "|------|----------|---------|--------|------|----------|",
        ]
    )
    for i, r in enumerate(report.get("ranked_oos_holdout", [])[:12], 1):
        lines.append(
            f"| {i} | {r['name']} | {r.get('mean_pct', 0):+.2f}% | "
            f"{r.get('tstat', '—')} | {r.get('hit_positive_pct', '—')}% | {r.get('category', '')} |"
        )
    lines.extend(["", "## Regime timed lanes (4w forward)", ""])
    for r in report.get("regime_lanes", []):
        oos = (r.get("eras") or {}).get(ERA_OOS, {})
        full = (r.get("eras") or {}).get(ERA_FULL, {})
        lines.append(
            f"- **{r['name']}** — full {full.get('mean_pct', 0):+.2f}% (t={full.get('tstat')}) | "
            f"holdout {oos.get('mean_pct', 0):+.2f}% (t={oos.get('tstat')}) n={oos.get('n', 0)}"
        )
    lines.extend(["", "## Retail event rules (when they fire)", ""])
    for r in report.get("retail_events", [])[:8]:
        lines.append(
            f"- **{r['strategy_id']}** ({r['horizon']}, {r['scope']}): "
            f"mean {r.get('mean_pct'):+.2f}% t={r.get('tstat')} n={r.get('n')}"
        )
    lines.extend(["", "## Cross-section 4w spreads", ""])
    for s in report.get("cross_section_spreads", []):
        if s.get("mean_spread_pct") is None:
            continue
        lines.append(
            f"- `{s['era']}` **{s['signal']}**: spread {s['mean_spread_pct']:+.2f}% "
            f"t={s.get('tstat')} weeks={s.get('weeks')}"
        )
    return "\n".join(lines)


def main() -> int:
    tape, banks = fetch_and_cache()
    ihsg = tape["close"]
    bank_ew = bank_equal_weight_series(banks)

    regime_lanes = [
        _strategy_row(
            "always_ihsg",
            "regime",
            regime_timed_returns(tape, ihsg, allow_regimes={"washout", "recovery", "neutral", "extended"}, label="always_ihsg"),
            description="Always long IHSG 4w",
        ),
        _strategy_row(
            "always_banks",
            "regime",
            regime_timed_returns(tape, bank_ew, allow_regimes={"washout", "recovery", "neutral", "extended"}, label="always_banks"),
            description="Always long bank EW 4w",
        ),
        _strategy_row(
            "washout_banks_only",
            "regime",
            regime_timed_returns(tape, bank_ew, allow_regimes={"washout"}, label="washout_banks"),
            description="Long banks only in washout label",
        ),
        _strategy_row(
            "recovery_ihsg_only",
            "regime",
            regime_timed_returns(tape, ihsg, allow_regimes={"recovery"}, label="recovery_ihsg"),
            description="Long IHSG only in recovery label",
        ),
        _strategy_row(
            "neutral_ihsg_only",
            "regime",
            regime_timed_returns(tape, ihsg, allow_regimes={"neutral"}, label="neutral_ihsg"),
            description="Long IHSG only in neutral label",
        ),
        _strategy_row(
            "hybrid_monthly",
            "regime",
            hybrid_monthly_rotation(tape, ihsg, bank_ew),
            description="Washout→banks, recovery→ihsg, neutral→half ihsg, extended→flat",
        ),
    ]

    liquid = load_liquid_universe()[:50]
    panel = ensure_fwd_4w(prepare_liquid_weekly(BROADCAST, ENTITY, liquid))
    pick_rows = _cross_section_strategies(panel)
    pick_strats = [r for r in pick_rows if r.get("eras")]

    retail = retail_event_stats_from_validation(VALIDATION)
    retail_ranked = sorted(
        [r for r in retail if r.get("scope") == "oos" and r.get("horizon") in ("20d", "10d", "5d")],
        key=lambda x: (x.get("tstat") or 0, x.get("mean_pct") or 0),
        reverse=True,
    )

    all_rankable = regime_lanes + pick_strats
    # inject retail as pseudo-strategies for ranking (event mean = expected 4w-ish hold)
    for r in retail_ranked[:6]:
        all_rankable.append(
            {
                "name": f"retail_{r['strategy_id']}_{r['horizon']}",
                "category": "retail",
                "description": r.get("jargon"),
                "eras": {
                    "full": {
                        "n": r.get("n"),
                        "mean_pct": r.get("mean_pct"),
                        "tstat": r.get("tstat"),
                        "hit_positive_pct": r.get("hit_rate_pct"),
                    },
                    ERA_OOS: {
                        "n": r.get("n"),
                        "mean_pct": r.get("mean_pct"),
                        "tstat": r.get("tstat"),
                        "hit_positive_pct": r.get("hit_rate_pct"),
                    },
                },
            }
        )

    mret = ihsg.resample("ME").last().pct_change().dropna() * 100
    ihsg_month = score_series(mret)
    ranked = rank_strategies(all_rankable, ERA_OOS)

    spreads_flat = []
    for row in pick_rows:
        if row.get("name") == "cross_section_spreads":
            spreads_flat = row.get("spreads", [])

    report: dict[str, Any] = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "horizon": "4w (~20 trading days)",
        "ihsg_calendar_month": ihsg_month,
        "playbook": build_playbook(ranked, float(ihsg_month.get("mean_pct") or 0)),
        "split": split_meta(panel),
        "ranked_oos_holdout": ranked,
        "ranked_full": rank_strategies(all_rankable, ERA_FULL),
        "regime_lanes": regime_lanes,
        "pick_strategies": pick_strats,
        "retail_events": retail_ranked,
        "cross_section_spreads": spreads_flat,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (OUT / "latest.md").write_text(render_md(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "top_oos": ranked[:3],
                "out": str(OUT / "latest.md"),
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
