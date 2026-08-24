#!/usr/bin/env python3
"""Run first-pass diagnostics on an Asia news/market panel.

The goal is not to declare an edge from a tiny sample. The goal is to produce a
repeatable, low-friction readout whenever new GDELT windows finish: coverage,
signal/outcome correlations, and top-minus-bottom tercile spreads.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[1]
DEFAULT_PANEL_ROOT = REPO / "data_lake/research_panels/asia_news_market"

SIGNAL_COLUMNS = [
    "mean_tone_weighted",
    "market_relevant_share",
    "broad_context_share",
    "financial_stress_per_1k_rows",
    "geopolitical_security_per_1k_rows",
    "governance_corruption_per_1k_rows",
    "health_per_1k_rows",
    "macro_policy_per_1k_rows",
    "natural_environment_per_1k_rows",
    "political_instability_per_1k_rows",
    "trade_supply_chain_per_1k_rows",
]

OUTCOME_COLUMNS = [
    "fwd_return_1w",
    "fwd_return_2w",
    "fwd_return_4w",
    "fwd_vol_4w",
]


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel-dir", type=Path, required=True)
    ap.add_argument("--panel-file", default="asia_country_week_news_market_primary_panel.parquet")
    ap.add_argument("--out-dir", type=Path, default=None)
    return ap.parse_args()


def corr_t_stat(r: float, n: int) -> float:
    if n <= 2 or not np.isfinite(r) or abs(r) >= 1:
        return float("nan")
    return float(r * math.sqrt((n - 2) / (1 - r * r)))


def load_panel(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)
    df["week_end"] = pd.to_datetime(df["week_end"], errors="coerce")
    for col in SIGNAL_COLUMNS + OUTCOME_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def correlations(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for signal in SIGNAL_COLUMNS:
        if signal not in df.columns:
            continue
        for outcome in OUTCOME_COLUMNS:
            if outcome not in df.columns:
                continue
            sub = df[[signal, outcome]].replace([np.inf, -np.inf], np.nan).dropna()
            n = int(len(sub))
            if n < 5 or sub[signal].nunique() < 3 or sub[outcome].nunique() < 3:
                pearson = float("nan")
                spearman = float("nan")
            else:
                pearson = float(sub[signal].corr(sub[outcome], method="pearson"))
                spearman = float(sub[signal].corr(sub[outcome], method="spearman"))
            rows.append(
                {
                    "signal": signal,
                    "outcome": outcome,
                    "n": n,
                    "pearson": pearson,
                    "pearson_t": corr_t_stat(pearson, n),
                    "spearman": spearman,
                    "spearman_t": corr_t_stat(spearman, n),
                }
            )
    return pd.DataFrame(rows).sort_values(["outcome", "spearman"], ascending=[True, False]).reset_index(drop=True)


def tercile_spreads(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for signal in SIGNAL_COLUMNS:
        if signal not in df.columns:
            continue
        for outcome in OUTCOME_COLUMNS:
            if outcome not in df.columns:
                continue
            weekly_rows = []
            for week, group in df.groupby("week_end"):
                sub = group[[signal, outcome]].replace([np.inf, -np.inf], np.nan).dropna()
                if len(sub) < 6 or sub[signal].nunique() < 3:
                    continue
                ranks = sub[signal].rank(method="first")
                try:
                    bucket = pd.qcut(ranks, 3, labels=["bottom", "middle", "top"])
                except ValueError:
                    continue
                tmp = sub.assign(bucket=bucket)
                means = tmp.groupby("bucket", observed=False)[outcome].mean()
                if "top" not in means or "bottom" not in means:
                    continue
                weekly_rows.append(
                    {
                        "week_end": week,
                        "top_minus_bottom": float(means["top"] - means["bottom"]),
                        "top_mean": float(means["top"]),
                        "bottom_mean": float(means["bottom"]),
                    }
                )
            if not weekly_rows:
                continue
            w = pd.DataFrame(weekly_rows)
            spread = float(w["top_minus_bottom"].mean())
            spread_std = float(w["top_minus_bottom"].std(ddof=1)) if len(w) > 1 else float("nan")
            t_stat = float(spread / (spread_std / math.sqrt(len(w)))) if len(w) > 1 and spread_std > 0 else float("nan")
            rows.append(
                {
                    "signal": signal,
                    "outcome": outcome,
                    "weeks": int(len(w)),
                    "mean_top_minus_bottom": spread,
                    "spread_t": t_stat,
                    "mean_top": float(w["top_mean"].mean()),
                    "mean_bottom": float(w["bottom_mean"].mean()),
                }
            )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["outcome", "mean_top_minus_bottom"], ascending=[True, False]).reset_index(drop=True)


def main() -> int:
    args = parse_args()
    panel_path = args.panel_dir / args.panel_file
    out_dir = args.out_dir or (args.panel_dir / "diagnostics")
    out_dir.mkdir(parents=True, exist_ok=True)

    df = load_panel(panel_path)
    corr = correlations(df)
    spreads = tercile_spreads(df)
    coverage = (
        df.groupby(["country_iso3", "instrument", "proxy_type"], as_index=False)
        .agg(
            weeks=("week_end", "nunique"),
            date_min=("week_end", "min"),
            date_max=("week_end", "max"),
            news_rows=("news_rows", "sum"),
            fwd_return_1w_nonnull=("fwd_return_1w", lambda s: int(s.notna().sum())),
            fwd_return_4w_nonnull=("fwd_return_4w", lambda s: int(s.notna().sum())),
        )
        .sort_values(["country_iso3", "instrument"])
    )

    corr.to_csv(out_dir / "signal_correlations.csv", index=False)
    spreads.to_csv(out_dir / "tercile_spreads.csv", index=False)
    coverage.to_csv(out_dir / "coverage.csv", index=False)
    summary = {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "panel": str(panel_path),
        "rows": int(len(df)),
        "countries": sorted(df["country_iso3"].dropna().unique().tolist()),
        "date_min": str(df["week_end"].min().date()) if df["week_end"].notna().any() else "",
        "date_max": str(df["week_end"].max().date()) if df["week_end"].notna().any() else "",
        "correlation_rows": int(len(corr)),
        "tercile_spread_rows": int(len(spreads)),
        "warning": "Treat samples under 52 weeks as pipeline diagnostics, not investment evidence.",
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
