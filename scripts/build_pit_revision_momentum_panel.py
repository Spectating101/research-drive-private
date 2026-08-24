#!/usr/bin/env python3
"""Build multi-index PIT × estimate revision momentum panel (institutional cross-lane).

Geography-balanced flagship: all six PIT indices (.SPX, .JKSE, .TWII, .N225,
.KS11, .STI) joined to Refinitiv estimate revisions and entity spine metadata.
No regional microstructure lane required.
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
DEFAULT_OUT_DIR = REPO / "data_lake/research_panels/pit_revision_momentum"
PANEL_FILE = "pit_index_revision_momentum.parquet"

INDEX_COUNTRY = {
    ".SPX": "US",
    ".JKSE": "ID",
    ".TWII": "TW",
    ".N225": "JP",
    ".KS11": "KR",
    ".STI": "SG",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_parquet(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_parquet(path)


def _pit_monthly_all(pit_path: Path) -> pd.DataFrame:
    pit = _read_parquet(pit_path)
    pit["as_of_date"] = pd.to_datetime(pit["as_of_date"], errors="coerce")
    pit = pit.dropna(subset=["as_of_date", "constituent_ric", "index_ric"])
    pit["as_of_month"] = pit["as_of_date"].dt.to_period("M").astype(str)
    pit = pit.sort_values(["index_ric", "constituent_ric", "as_of_date"])
    pit_month = pit.groupby(["index_ric", "as_of_month", "constituent_ric"], as_index=False).tail(1)
    pit_month["index_country"] = pit_month["index_ric"].map(INDEX_COUNTRY)
    return pit_month.reset_index(drop=True)


def _estimate_month_end(pit_month: pd.DataFrame, est_path: Path) -> pd.DataFrame:
    est = _read_parquet(est_path)
    est["date"] = pd.to_datetime(est["date"], errors="coerce")
    est = est.dropna(subset=["date", "ric"])
    est["as_of_month"] = est["date"].dt.to_period("M").astype(str)
    est_month = est.sort_values("date").groupby(["ric", "as_of_month"], as_index=False).tail(1)
    left = pit_month.rename(columns={"constituent_ric": "ric"})
    est_key = est_month[
        ["ric", "as_of_month", "date", "eps_mean", "revision_1m", "revision_3m", "revision_6m"]
    ]
    merged = left.merge(est_key, on=["ric", "as_of_month"], how="left")
    rename = {
        "eps_mean": "est_eps_mean",
        "revision_1m": "est_revision_1m",
        "revision_3m": "est_revision_3m",
        "revision_6m": "est_revision_6m",
        "date": "est_obs_date",
    }
    return merged.rename(columns={k: v for k, v in rename.items() if k in merged.columns})


def build_panel(*, pit_path: Path, spine_path: Path, est_path: Path) -> pd.DataFrame:
    pit_month = _pit_monthly_all(pit_path)
    panel = _estimate_month_end(pit_month, est_path)

    spine = _read_parquet(spine_path)[
        ["ric", "company_name", "country_code", "trbc_sector", "trbc_industry", "market_cap"]
    ].drop_duplicates(subset=["ric"])
    panel = panel.merge(spine, on="ric", how="left")

    panel["has_estimates"] = panel["est_eps_mean"].notna().astype(int)
    panel["in_spine"] = panel["company_name"].notna().astype(int)
    panel["source"] = "derived.pit_index_revision_momentum"
    panel["built_at"] = utc_now()

    front = [
        "index_ric",
        "index_country",
        "as_of_month",
        "as_of_date",
        "ric",
        "company_name",
        "country_code",
        "trbc_sector",
        "has_estimates",
        "in_spine",
    ]
    rest = [c for c in panel.columns if c not in front]
    return panel[front + rest].sort_values(["index_ric", "as_of_month", "ric"]).reset_index(drop=True)


def build_coverage_summary(panel: pd.DataFrame) -> dict[str, Any]:
    by_index = (
        panel.groupby("index_ric")
        .agg(
            rows=("ric", "size"),
            unique_rics=("ric", "nunique"),
            estimate_rows=("has_estimates", "sum"),
        )
        .reset_index()
    )
    by_index["estimate_rate_pct"] = (100.0 * by_index["estimate_rows"] / by_index["rows"]).round(1)
    return {
        "rows": int(len(panel)),
        "months": int(panel["as_of_month"].nunique()),
        "indices": sorted(panel["index_ric"].unique().tolist()),
        "unique_rics": int(panel["ric"].nunique()),
        "estimate_rows": int(panel["has_estimates"].sum()),
        "estimate_rate_pct": round(100.0 * panel["has_estimates"].mean(), 2),
        "as_of_month_min": str(panel["as_of_month"].min()),
        "as_of_month_max": str(panel["as_of_month"].max()),
        "by_index": by_index.to_dict(orient="records"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Build multi-index PIT revision momentum panel")
    ap.add_argument("--refinitiv-run", default=DEFAULT_REFINITIV_RUN)
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    run = args.refinitiv_run
    pit_path = REPO / f"data_lake/refinitiv_backfill/{run}/processed/index_membership_pit.parquet"
    spine_path = REPO / f"data_lake/research_panels/refinitiv/{run}/entity_market_spine.parquet"
    est_path = REPO / f"data_lake/research_panels/refinitiv/{run}/estimate_revision_panel.parquet"

    panel = build_panel(pit_path=pit_path, spine_path=spine_path, est_path=est_path)
    summary = build_coverage_summary(panel)
    manifest = {
        "generated_at": utc_now(),
        "refinitiv_run": run,
        "panel_file": PANEL_FILE,
        "summary": summary,
        "assumptions": [
            "Month-end PIT membership defines investable universe per index.",
            "Estimate revisions at calendar month-end proxy sell-side positioning.",
            "Six-index coverage: SPX, JKSE, TWII, N225, KS11, STI.",
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
