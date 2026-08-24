#!/usr/bin/env python3
"""Build research-ready derived panels from frozen Refinitiv complete harvest."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DEFAULT_RUN = "2026-07-06-complete"
SOURCE_ROOT = REPO / "data_lake/refinitiv_backfill"
RESCUED_ROOT = REPO / "data_lake/refinitiv_backfill/rescued_desktop_20251215/processed"
OUT_ROOT = REPO / "data_lake/research_panels/refinitiv"
ENTITY_MAP = REPO / "data_lake/entity_mapping/global/latest/entity_master.csv"
ENTITY_MAP_FALLBACK = REPO / "data_lake/entity_mapping/asia/20260702T121054Z/asia_entity_master.csv"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def build_survivorship_universe(source_dir: Path, spine: pd.DataFrame) -> pd.DataFrame:
    pit = _read(source_dir / "index_membership_pit.parquet")
    if pit.empty:
        return pit
    pit = pit.copy()
    pit["as_of_month"] = pd.to_datetime(pit["as_of_date"], errors="coerce").dt.to_period("M").astype(str)
    merged = pit.merge(
        spine[["ric", "country_code", "trbc_sector", "trbc_industry", "company_name"]],
        left_on="constituent_ric",
        right_on="ric",
        how="left",
    )
    return merged[
        [
            "index_ric",
            "as_of_month",
            "as_of_date",
            "constituent_ric",
            "constituent_name",
            "country_code",
            "trbc_sector",
            "trbc_industry",
            "company_name",
        ]
    ].drop_duplicates()


def build_us_risk_overlay(source_dir: Path, rescued_dir: Path) -> pd.DataFrame:
    risk = _read(source_dir / "vol_surface_metrics_daily.parquet")
    if risk.empty:
        return risk
    risk = risk[risk["value"].notna()].copy()
    risk["metric"] = risk["metric"].fillna(risk.get("field"))
    si = risk[risk["metric"].astype(str).str.contains("short_interest", case=False, na=False)]
    si = si.rename(columns={"value": "short_interest_pct"})[["date", "ric", "short_interest_pct"]]

    rescued = _read(rescued_dir / "us_risk_vol_skew_daily.parquet")
    if rescued.empty:
        return si
    keep = {
        "volatility_30d",
        "volatility_90d",
        "volatility_360d",
        "impvol_put_delta25",
        "impvol_call_delta25",
        "put_call_ratio",
        "short_interest_ratio",
    }
    rescued = rescued[rescued["metric"].isin(keep)].copy()
    wide = rescued.pivot_table(index=["date", "ric"], columns="metric", values="value", aggfunc="last").reset_index()
    out = si.merge(wide, on=["date", "ric"], how="outer")
    out["source"] = "derived.refinitiv_us_risk_overlay"
    out["built_at"] = utc_now()
    return out.sort_values(["ric", "date"])


def build_estimate_revision_panel(source_dir: Path) -> pd.DataFrame:
    est = _read(source_dir / "estimate_revisions_daily.parquet")
    if est.empty:
        return est
    est = est[est["value"].notna()].copy()
    est["metric"] = est["metric"].fillna(est.get("field"))
    eps = est[est["metric"].astype(str).str.contains("eps", case=False, na=False)][["date", "ric", "value"]]
    eps = eps.rename(columns={"value": "eps_mean"})
    eps["date"] = pd.to_datetime(eps["date"], errors="coerce")
    eps = eps.dropna(subset=["date"]).sort_values(["ric", "date"])
    for months, col in [(21, "revision_1m"), (63, "revision_3m"), (126, "revision_6m")]:
        lag = eps.groupby("ric")["eps_mean"].shift(months)
        eps[col] = (eps["eps_mean"] / lag - 1.0).where(lag.notna() & (lag != 0))
    eps["date"] = eps["date"].dt.strftime("%Y-%m-%d")
    eps["source"] = "derived.refinitiv_estimate_revision_panel"
    eps["built_at"] = utc_now()
    return eps


def build_fundamental_annual_panel(source_dir: Path) -> pd.DataFrame:
    fund = _read(source_dir / "fundamentals_panel.parquet")
    if fund.empty:
        return fund
    fund = fund[fund.get("error").isna() if "error" in fund.columns else slice(None)].copy()
    rename = {
        "Revenue": "revenue",
        "Net Income Incl Extra Before Distributions": "net_income",
        "Revenue from Business Activities - Total": "revenue_business",
        "Total Debt": "total_debt",
        "Free Cash Flow": "free_cash_flow",
        "Book Value Per Share": "book_value_per_share",
    }
    out = fund.rename(columns={k: v for k, v in rename.items() if k in fund.columns})
    if "Period End Date" in out.columns:
        out["fiscal_year"] = pd.to_datetime(out["Period End Date"], errors="coerce").dt.year
    elif "Financial Period Absolute End Date" in out.columns:
        out["fiscal_year"] = pd.to_datetime(out["Financial Period Absolute End Date"], errors="coerce").dt.year
    else:
        out["fiscal_year"] = pd.NA
    out["source"] = "derived.refinitiv_fundamental_annual_panel"
    out["built_at"] = utc_now()
    keep = [c for c in ["ric", "fiscal_year", "revenue", "net_income", "revenue_business", "total_debt", "free_cash_flow", "book_value_per_share", "fundamental_method", "source", "built_at"] if c in out.columns]
    return out[keep].drop_duplicates()


def _ric_to_yahoo(ric: str) -> str:
    r = str(ric)
    if r.endswith(".O"):
        return r[:-2]
    if r.endswith(".N"):
        return r[:-2]
    return r


def build_entity_market_spine(source_dir: Path, current_dir: Path) -> pd.DataFrame:
    spine = _read(source_dir / "refinitiv_security_master.parquet")
    if spine.empty:
        return spine
    spine = spine.copy()
    spine["yahoo_symbol"] = spine["ric"].map(_ric_to_yahoo)

    if ENTITY_MAP.exists() or ENTITY_MAP_FALLBACK.exists():
        ent_path = ENTITY_MAP if ENTITY_MAP.exists() else ENTITY_MAP_FALLBACK
        ent = pd.read_csv(ent_path)
        ent = ent.rename(columns={"yahoo_symbol": "yahoo_symbol_map"})
        spine = spine.merge(ent[["yahoo_symbol_map", "entity_id", "market_country", "name"]], left_on="yahoo_symbol", right_on="yahoo_symbol_map", how="left")
        spine = spine.rename(columns={"entity_id": "gdelt_entity_id", "name": "entity_name_gdelt"})
        spine = spine.drop(columns=["yahoo_symbol_map"], errors="ignore")

    cur = _read(current_dir / "index_membership_current.parquet")
    if not cur.empty:
        flags = (
            cur.groupby(["constituent_ric", "index_ric"])
            .size()
            .unstack(fill_value=0)
            .gt(0)
            .astype(int)
            .reset_index()
            .rename(columns={"constituent_ric": "ric"})
        )
        flags.columns = [f"in_{str(c).lstrip('.').lower()}" if c != "ric" else "ric" for c in flags.columns]
        spine = spine.merge(flags, on="ric", how="left")

    spine["source"] = "derived.refinitiv_entity_market_spine"
    spine["built_at"] = utc_now()
    return spine


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=DEFAULT_RUN)
    ap.add_argument("--out-root", default=str(OUT_ROOT))
    args = ap.parse_args()

    source_dir = SOURCE_ROOT / args.run_id / "processed"
    out_dir = Path(args.out_root) / args.run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    spine = _read(source_dir / "refinitiv_security_master.parquet")
    panels = {
        "survivorship_universe_panel.parquet": build_survivorship_universe(source_dir, spine),
        "us_risk_overlay.parquet": build_us_risk_overlay(source_dir, RESCUED_ROOT),
        "estimate_revision_panel.parquet": build_estimate_revision_panel(source_dir),
        "fundamental_annual_panel.parquet": build_fundamental_annual_panel(source_dir),
        "entity_market_spine.parquet": build_entity_market_spine(source_dir, source_dir),
    }

    manifest = {"generated_at": utc_now(), "source_run_id": args.run_id, "panels": []}
    for name, frame in panels.items():
        path = out_dir / name
        frame.to_parquet(path, index=False)
        manifest["panels"].append({"file": name, "rows": int(len(frame)), "bytes": path.stat().st_size})

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
