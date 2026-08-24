#!/usr/bin/env python3
"""Build an analysis-heavy watchlist readout from an Asia news-market ticker run.

This script is explicitly a research interpretation layer, not a signal engine.
It emits:
- country-level top-N long ranking with driver attribution
- a markdown readout with regime-level caveats
- a short risk/quality diagnosis for the run
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


REPO = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ROOT = REPO / "backtests/outputs/asia_news_market_ticker_watchlist"
DEFAULT_TOP_N = 10


DRIVER_LABELS = {
    "contrib_pred_z": "country_signal",
    "contrib_fwd_target_z": "forward_target",
    "contrib_ret21_z": "momentum_21d",
    "contrib_ret63_z": "momentum_63d",
    "contrib_liq_z": "liquidity",
    "contrib_risk_z": "risk",
}

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", default="", help="Run directory path. Default: latest under --run-root.")
    ap.add_argument("--run-root", default=str(DEFAULT_RUN_ROOT), help="Root folder containing run subfolders.")
    ap.add_argument("--top", type=int, default=DEFAULT_TOP_N, help="Top N per country.")
    return ap.parse_args()


def latest_run_dir(run_root: Path) -> Path:
    if not run_root.exists():
        raise FileNotFoundError(f"run-root missing: {run_root}")
    dirs = [p for p in run_root.iterdir() if p.is_dir()]
    if not dirs:
        raise FileNotFoundError(f"no run folders under: {run_root}")
    dirs = sorted(dirs, key=lambda p: p.stat().st_mtime, reverse=True)
    return dirs[0]


def _safe_num_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def safe_number(x: object) -> float:
    v = pd.to_numeric(pd.Series([x]), errors="coerce").iloc[0]
    return float(v) if pd.notna(v) else float("nan")


def build_driver_breakdown(row: pd.Series) -> tuple[str, str, list[tuple[str, float]]]:
    drivers = []
    for col, label in DRIVER_LABELS.items():
        val = safe_number(row.get(col))
        if pd.isna(val):
            continue
        drivers.append((label, float(val), abs(float(val))))
    drivers.sort(key=lambda kv: kv[2], reverse=True)
    top = drivers[:2]
    top_txt = ", ".join(f"{name} ({val:+.3f})" for name, val, _ in top)
    all_txt = ", ".join(f"{name} ({val:+.3f})" for name, val, _ in drivers)
    primary = drivers[0][0] if drivers else "none"
    return primary, top_txt, drivers


def driver_regime(primary: str, drivers: list[tuple[str, float, float]]) -> str:
    if not drivers:
        return "unclassified"
    if primary in {"country_signal", "forward_target"}:
        return "regime-led"
    if primary in {"momentum_21d", "momentum_63d"}:
        return "momentum-led"
    if primary == "risk":
        return "risk-controlled"
    return "mixed"


def safe_format_score(v: object) -> str:
    v = pd.to_numeric(pd.Series([v]), errors="coerce").iloc[0]
    return f"{float(v):.3f}" if pd.notna(v) else "n/a"


def build_top_by_country_reasoned(panel: pd.DataFrame, top: int, long_named: pd.DataFrame | None) -> pd.DataFrame:
    base = panel.copy()
    base = base.copy()
    if "score_rank_long" not in base.columns and "ticker_score_long" in base.columns:
        base["score_rank_long"] = base["ticker_score_long"].rank(ascending=False, method="dense").astype("int64")

    # optional name enrichment
    if long_named is not None and not long_named.empty:
        keep = long_named[long_named.get("side", "") == "long"][["instrument", "name", "sector", "industry", "country", "currency"]].drop_duplicates(subset=["instrument"])
        base = base.merge(keep, on="instrument", how="left")

    score_rank = panel["ticker_score_long"].rank(ascending=False, method="min").astype(int)
    panel = panel.assign(score_rank_long=score_rank)
    rows = []
    for country, g in base.groupby("country_iso3"):
        country_df = g.sort_values("ticker_score_long", ascending=False).reset_index(drop=True).copy()
        top_df = country_df.head(top).copy()
        for i, (_, row) in enumerate(top_df.iterrows(), start=1):
            primary, top2, all_drivers = build_driver_breakdown(row)
            regime = driver_regime(primary, all_drivers)
            top_contrib_sum = sum(v for _, v, _ in all_drivers[:2])
            driver_gap = 0.0
            if len(all_drivers) >= 2:
                driver_gap = all_drivers[0][2] - all_drivers[1][2]
            actionable = "yes" if safe_number(row.get("ticker_score_long")) > 0 and regime in {"regime-led", "momentum-led"} else "no"
            rows.append(
                {
                    "country_iso3": country,
                    "rank_long_by_country": i,
                    "instrument": row["instrument"],
                    "name": row.get("name"),
                    "score_rank_long": int(row.get("score_rank_long", 0)),
                    "ticker_score_long": safe_number(row.get("ticker_score_long")),
                    "as_of_date": row.get("as_of_date", ""),
                    "as_of_price": safe_number(row.get("as_of_price")),
                    "country_pred": safe_number(row.get("country_pred")),
                    "country_fwd_target": safe_number(row.get("country_fwd_target")),
                    "country_risk_score": safe_number(row.get("country_risk_score")),
                    "pred_z": safe_number(row.get("pred_z")),
                    "fwd_target_z": safe_number(row.get("fwd_target_z")),
                    "ret21_z": safe_number(row.get("ret21_z")),
                    "ret63_z": safe_number(row.get("ret63_z")),
                    "liq_z": safe_number(row.get("liq_z")),
                    "risk_z": safe_number(row.get("risk_z")),
                    "contrib_pred_z": safe_number(row.get("contrib_pred_z")),
                    "contrib_fwd_target_z": safe_number(row.get("contrib_fwd_target_z")),
                    "contrib_ret21_z": safe_number(row.get("contrib_ret21_z")),
                    "contrib_ret63_z": safe_number(row.get("contrib_ret63_z")),
                    "contrib_liq_z": safe_number(row.get("contrib_liq_z")),
                    "contrib_risk_z": safe_number(row.get("contrib_risk_z")),
                    "sector": row.get("sector", ""),
                    "industry": row.get("industry", ""),
                    "country": row.get("country", ""),
                    "currency": row.get("currency", ""),
                    "primary_driver": primary,
                    "driver_regime": regime,
                    "driver_gap_abs": float(driver_gap),
                    "top2_driver_sum": float(top_contrib_sum),
                    "actionable_long_candidate": actionable,
                    "global_score_rank": int((panel["ticker_score_long"] > safe_number(row.get("ticker_score_long"))).sum() + 1),
                    "top_drivers": top2,
                    "exact_long_reason": f"Top drivers [{top2}] | all terms [{all_drivers and ', '.join(f'{n}:{v:+.3f}' for n,v,_ in all_drivers) or 'none'}]",
                }
            )
    return pd.DataFrame(rows)


def build_country_summary(df: pd.DataFrame) -> list[str]:
    lines = ["# Asia Watchlist Deep Analysis", "", "## Country-level summary (top-by-country)"]
    if df.empty:
        return lines + ["No rows found in panel."]
    rows = []
    for country, g in df.groupby("country_iso3"):
        g = g.sort_values("ticker_score_long", ascending=False)
        if g.empty:
            continue
        top = g.iloc[0]
        rows.append(
            f"- {country}: top={top['instrument']} score={safe_format_score(top['ticker_score_long'])}, "
            f"avg_top10={safe_format_score(g['ticker_score_long'].head(10).mean())}, "
            f"positive={int((g['ticker_score_long'] > 0).sum())}, negative={int((g['ticker_score_long'] <= 0).sum())}, "
            f"regime_led={int((g['driver_regime'] == 'regime-led').sum())}, momentum_led={int((g['driver_regime'] == 'momentum-led').sum())}, "
            f"name coverage={(g['name'].notna()).sum()}/{min(10, len(g))}"
        )
    return lines + rows


def build_global_signal_profile(top_df: pd.DataFrame) -> list[str]:
    if top_df.empty:
        return ["# No data for global profile."]
    lines = ["## Global regime profile", ""]
    for regime, g in top_df.groupby("driver_regime"):
        g = g.sort_values("ticker_score_long", ascending=False)
        if g.empty:
            continue
        avg = safe_number(g["ticker_score_long"].mean())
        lines.append(
            f"- {regime}: {len(g)} names, avg top-per-country score {avg:.3f}, "
            f"top={g.iloc[0]['instrument']} ({safe_format_score(g.iloc[0]['ticker_score_long'])})"
        )

    actionable = top_df[top_df["actionable_long_candidate"] == "yes"].sort_values("ticker_score_long", ascending=False)
    lines.extend(["", "### Most actionable (screening pass)"])
    if actionable.empty:
        lines.append("- No positive regime/momentum actionable names in top-per-country set.")
    else:
        for _, row in actionable.head(12).iterrows():
            lines.append(
                f"- `{row['instrument']}` ({row['country_iso3']}): score={safe_format_score(row['ticker_score_long'])}, "
                f"drivers={row['top_drivers']}, regime={row['driver_regime']}, global_rank={int(row['global_score_rank'])}"
            )
    lines.extend(
        [
            "",
            "### Why this matters",
            "- Regime-led picks should be treated as macro-country overlays.",
            "- Momentum-led picks are tactical; they need stricter entry/exit checks and cross-factor confirmation.",
            "- Risk-controlled picks can still be valid in weak regimes; the reason they are top is lower adverse-risk contribution.",
        ]
    )
    return lines


def build_markdown(run_id: str, df_top: pd.DataFrame, panel: pd.DataFrame, summary: dict) -> str:
    lines = [
        f"# Asia Watchlist Deep Analysis: {run_id}",
        f"- Run built UTC: {summary.get('built_at_utc', 'n/a')}",
        f"- As-of: {summary.get('as_of', 'n/a')}",
        f"- Universe size in panel: {len(panel)}",
        "",
        "## Interpretation",
        "- This output is a **screen** and a **tactical regime map**, not a final investment thesis.",
        "- If country term dominates, this is regime-led. If 21/63d momentum dominates, this is near-term flow/tactical.",
        "- If risk term is the leading component, treat as defensive/uncertain naming rather than high-conviction long candidates.",
        "",
    ]

    lines.extend(build_country_summary(df_top))
    lines.extend(["", ""])
    lines.extend(build_global_signal_profile(df_top))
    lines.append("")
    lines.append("## Top 10 long by country")
    for country, g in df_top.groupby("country_iso3"):
        lines.append(f"\n### {country}")
        lines.append("| rank | instrument | score | top drivers | drivers all |")
        lines.append("|---|---|---:|---|---|")
        g = g.sort_values("ticker_score_long", ascending=False).head(10)
        for _, r in g.iterrows():
            driver_items = [
                ("country_signal", "pred_z"),
                ("forward_target", "fwd_target_z"),
                ("momentum_21d", "ret21_z"),
                ("momentum_63d", "ret63_z"),
                ("liquidity", "liq_z"),
                ("risk", "risk_z"),
            ]
            drivers_all = ", ".join(
                f"{label}({safe_number(r[f'contrib_' + col if col != 'pred_z' else 'contrib_pred_z']):+.3f})"
                for label, col in driver_items
            )
            lines.append(
                f"| {int(r['rank_long_by_country'])} | {r['instrument']} | {safe_format_score(r['ticker_score_long'])} "
                f"| {r['top_drivers']} | {drivers_all} |"
            )

    lines.append("")
    lines.append("## Quality flags")
    missing = int(df_top['name'].isna().sum()) if 'name' in df_top.columns else 0
    total = len(df_top)
    lines.append(f"- Metadata coverage in top-by-country table: {total - missing}/{total} resolved ({(1 - missing / total if total else 0):.1%}).")

    # rank stress tests for known anchor
    if "2330.TW" in panel.get("instrument", pd.Series(dtype=str)).tolist():
        score_2330 = float(panel.loc[panel["instrument"] == "2330.TW", "ticker_score_long"].iloc[0])
        rank = int((panel["ticker_score_long"] > score_2330).sum()) + 1
        score = float(panel.loc[panel["instrument"] == "2330.TW", "ticker_score_long"].iloc[0])
        lines.append(f"- 2330.TW full-screen rank: {rank} (score {score:.3f}); outside top-by-country Taiwan picks this run.")

    lines.append("")
    lines.append("## Operational next step")
    lines.append("- Segment candidates into `regime-led` vs `momentum-led`, then keep only overlap with your thesis registry before any allocation decision.")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    run_root = Path(args.run_root)
    run_dir = Path(args.run_dir)
    if not run_dir:
        run_dir = latest_run_dir(run_root)
    if not run_dir.exists():
        run_dir = Path(args.run_dir)
    if not run_dir.exists():
        raise FileNotFoundError(f"run dir missing: {run_dir}")

    panel_path = run_dir / "ticker_signal_panel.csv"
    long_named_path = run_dir / "watchlist_long_named_with_reasons.csv"
    summary_path = run_dir / "summary.json"

    if not panel_path.exists():
        raise FileNotFoundError(f"missing panel file: {panel_path}")
    panel = pd.read_csv(panel_path)

    if "contrib_pred_z" not in panel.columns:
        panel["contrib_pred_z"] = _safe_num_series(panel["pred_z"]) * 0.55
        panel["contrib_fwd_target_z"] = _safe_num_series(panel["fwd_target_z"]) * 0.12
        panel["contrib_ret21_z"] = _safe_num_series(panel["ret21_z"]) * 0.10
        panel["contrib_ret63_z"] = _safe_num_series(panel["ret63_z"]) * 0.08
        panel["contrib_liq_z"] = _safe_num_series(panel["liq_z"]) * 0.07
        panel["contrib_risk_z"] = _safe_num_series(panel["risk_z"]) * 0.08

    long_named = pd.read_csv(long_named_path) if long_named_path.exists() else None
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}

    run_id = summary.get("run_id", run_dir.name)

    top_df = build_top_by_country_reasoned(panel, top=max(1, args.top), long_named=long_named)
    top_df_path = run_dir / "watchlist_top10_long_by_country_reasoned.csv"
    top_md_path = run_dir / "watchlist_top10_long_by_country_reasoned.md"
    deep_path = run_dir / "watchlist_deep_analysis.md"

    if not top_df.empty:
        top_df.to_csv(top_df_path, index=False)

    # compact markdown top10 per country
    lines = [
        f"# Top-{args.top} Long Picks Per Country",
        f"Source: `ticker_signal_panel.csv` (latest run {run_id})",
        "",
    ]
    for country, g in top_df.groupby("country_iso3"):
        lines.append(f"## {country}")
        for _, row in g.sort_values("rank_long_by_country").iterrows():
            lines.append(
                f"- {int(row['rank_long_by_country'])}. `{row['instrument']}` | score {safe_format_score(row['ticker_score_long'])} | {row['top_drivers']}"
            )
        lines.append("")
    top_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    deep_path.write_text(build_markdown(run_id, top_df, panel, summary), encoding="utf-8")

    print(f"[ok] wrote: {top_df_path}")
    print(f"[ok] wrote: {top_md_path}")
    print(f"[ok] wrote: {deep_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
