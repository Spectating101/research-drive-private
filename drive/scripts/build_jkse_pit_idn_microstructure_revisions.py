#!/usr/bin/env python3
"""Build JKSE PIT × IDN microstructure × estimate revisions cross-lane panel.

Institutional spine (PIT membership) + regional depth (IDN FRY) + sell-side
revisions — no GDELT entity bridge required.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DEFAULT_REFINITIV_RUN = "2026-07-06-complete"
DEFAULT_OUT_DIR = REPO / "data_lake/research_panels/jkse_pit_idn"
PANEL_FILE = "jkse_pit_idn_microstructure_revisions.parquet"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_parquet(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_parquet(path)


def _jkse_pit_monthly(pit_path: Path) -> pd.DataFrame:
    pit = _read_parquet(pit_path)
    pit = pit[pit["index_ric"] == ".JKSE"].copy()
    if pit.empty:
        raise ValueError("no .JKSE rows in index_membership_pit")
    pit["as_of_date"] = pd.to_datetime(pit["as_of_date"], errors="coerce")
    pit = pit.dropna(subset=["as_of_date", "constituent_ric"])
    pit["as_of_month"] = pit["as_of_date"].dt.to_period("M").astype(str)
    pit["yahoo_symbol"] = pit["constituent_ric"].astype(str)
    pit = pit.sort_values(["constituent_ric", "as_of_date"])
    pit_month = pit.groupby(["as_of_month", "constituent_ric"], as_index=False).tail(1)
    return pit_month.reset_index(drop=True)


def _idn_monthly_features(idn_path: Path) -> pd.DataFrame:
    idn = _read_parquet(idn_path)
    idn["date"] = pd.to_datetime(idn["date"], errors="coerce")
    idn = idn.dropna(subset=["date", "yahoo_symbol"])
    idn["as_of_month"] = idn["date"].dt.to_period("M").astype(str)

    label = idn["bandar_lite_label"].astype(str)
    idn["_squeeze"] = (label == "squeeze_from_drawdown").astype(int)
    idn["_chase"] = label.isin(["chase_into_spike", "momentum_chase"]).astype(int)
    idn["_quiet_build"] = (label == "quiet_volume_build").astype(int)

    agg_spec: dict[str, Any] = {
        "return_1d": "mean",
        "return_5d": "mean",
        "vol_ratio_20d": "mean",
        "rsi14": "mean",
        "dd_60d": "mean",
        "quiet_acc_score_5d": "mean",
        "chase_score_5d": "mean",
        "cs_move_pct_rank": "mean",
        "fwd_5d": "mean",
        "_squeeze": "sum",
        "_chase": "sum",
        "_quiet_build": "sum",
        "date": "count",
    }
    agg = idn.groupby(["yahoo_symbol", "as_of_month"], as_index=False).agg(agg_spec)
    rename = {
        "return_1d": "idn_mean_return_1d",
        "return_5d": "idn_mean_return_5d",
        "vol_ratio_20d": "idn_mean_vol_ratio_20d",
        "rsi14": "idn_mean_rsi14",
        "dd_60d": "idn_mean_dd_60d",
        "quiet_acc_score_5d": "idn_mean_quiet_acc_score_5d",
        "chase_score_5d": "idn_mean_chase_score_5d",
        "cs_move_pct_rank": "idn_mean_cs_move_pct_rank",
        "fwd_5d": "idn_mean_fwd_5d",
        "_squeeze": "idn_squeeze_days",
        "_chase": "idn_chase_days",
        "_quiet_build": "idn_quiet_build_days",
        "date": "idn_trading_days",
    }
    return agg.rename(columns=rename)


def _estimate_month_end(pit_month: pd.DataFrame, est_path: Path) -> pd.DataFrame:
    est = _read_parquet(est_path)
    est["date"] = pd.to_datetime(est["date"], errors="coerce")
    est = est.dropna(subset=["date", "ric"])
    est["as_of_month"] = est["date"].dt.to_period("M").astype(str)
    est_month = est.sort_values("date").groupby(["ric", "as_of_month"], as_index=False).tail(1)
    left = pit_month.rename(columns={"constituent_ric": "ric"})
    est_key = est_month[["ric", "as_of_month", "date", "eps_mean", "revision_1m", "revision_3m", "revision_6m"]]
    merged = left.merge(est_key, on=["ric", "as_of_month"], how="left")
    rename = {
        "eps_mean": "est_eps_mean",
        "revision_1m": "est_revision_1m",
        "revision_3m": "est_revision_3m",
        "revision_6m": "est_revision_6m",
        "date": "est_obs_date",
    }
    return merged.rename(columns={k: v for k, v in rename.items() if k in merged.columns})


def build_panel(
    *,
    pit_path: Path,
    spine_path: Path,
    est_path: Path,
    idn_path: Path,
) -> pd.DataFrame:
    pit_month = _jkse_pit_monthly(pit_path)
    idn_month = _idn_monthly_features(idn_path)
    panel = _estimate_month_end(pit_month, est_path)

    spine = _read_parquet(spine_path)
    spine_id = spine[spine["country_code"] == "ID"][
        ["ric", "company_name", "trbc_sector", "trbc_industry", "market_cap", "in_jkse"]
    ].drop_duplicates(subset=["ric"])
    panel = panel.merge(
        spine_id,
        on="ric",
        how="left",
        suffixes=("", "_spine"),
    )

    panel = panel.merge(idn_month, on=["yahoo_symbol", "as_of_month"], how="left")

    panel["has_idn_features"] = panel["idn_trading_days"].notna().astype(int)
    panel["has_estimates"] = panel["est_eps_mean"].notna().astype(int)
    panel["in_spine_id"] = panel["company_name"].notna().astype(int)
    panel["index_ric"] = ".JKSE"
    panel["source"] = "derived.jkse_pit_idn_microstructure_revisions"
    panel["built_at"] = utc_now()

    front = [
        "index_ric",
        "as_of_month",
        "as_of_date",
        "ric",
        "yahoo_symbol",
        "company_name",
        "trbc_sector",
        "trbc_industry",
        "has_idn_features",
        "has_estimates",
        "in_spine_id",
    ]
    rest = [c for c in panel.columns if c not in front]
    return panel[front + rest].sort_values(["as_of_month", "ric"]).reset_index(drop=True)


def build_coverage_summary(panel: pd.DataFrame) -> dict[str, Any]:
    months = panel["as_of_month"].nunique()
    return {
        "rows": int(len(panel)),
        "months": int(months),
        "unique_rics": int(panel["ric"].nunique()),
        "unique_yahoo_symbols": int(panel["yahoo_symbol"].nunique()),
        "idn_feature_rows": int(panel["has_idn_features"].sum()),
        "estimate_rows": int(panel["has_estimates"].sum()),
        "spine_id_rows": int(panel["in_spine_id"].sum()),
        "idn_feature_rate_pct": round(100.0 * panel["has_idn_features"].mean(), 1),
        "estimate_rate_pct": round(100.0 * panel["has_estimates"].mean(), 1),
        "as_of_month_min": str(panel["as_of_month"].min()),
        "as_of_month_max": str(panel["as_of_month"].max()),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Build JKSE PIT × IDN × estimate revision panel")
    ap.add_argument("--refinitiv-run", default=DEFAULT_REFINITIV_RUN)
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--dry-run", action="store_true", help="Build in memory only; do not write parquet")
    args = ap.parse_args()

    run = args.refinitiv_run
    pit_path = REPO / f"data_lake/refinitiv_backfill/{run}/processed/index_membership_pit.parquet"
    spine_path = REPO / f"data_lake/research_panels/refinitiv/{run}/entity_market_spine.parquet"
    est_path = REPO / f"data_lake/research_panels/refinitiv/{run}/estimate_revision_panel.parquet"
    idn_path = REPO / "data_lake/research_panels/idn_fry_episode/daily_cross_section.parquet"

    panel = build_panel(
        pit_path=pit_path,
        spine_path=spine_path,
        est_path=est_path,
        idn_path=idn_path,
    )
    summary = build_coverage_summary(panel)

    manifest = {
        "generated_at": utc_now(),
        "refinitiv_run": run,
        "panel_file": PANEL_FILE,
        "inputs": {
            "pit": str(pit_path.relative_to(REPO)),
            "spine": str(spine_path.relative_to(REPO)),
            "estimates": str(est_path.relative_to(REPO)),
            "idn_daily": str(idn_path.relative_to(REPO)),
        },
        "summary": summary,
        "assumptions": [
            "JKSE PIT month-end membership defines investable IDX universe.",
            "yahoo_symbol = constituent_ric for .JK names (634/913 PIT names match IDN daily).",
            "IDN FRY features aggregated monthly proxy local informed-flow regime.",
            "Estimate revisions as-of PIT date proxy sell-side positioning (48 ID RICs with history).",
        ],
    }

    if args.dry_run:
        print(json.dumps(manifest, indent=2))
        return 0

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / PANEL_FILE
    panel.to_parquet(out_path, index=False)
    manifest["bytes"] = out_path.stat().st_size
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
