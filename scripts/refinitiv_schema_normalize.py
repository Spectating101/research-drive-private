#!/usr/bin/env python3
"""Normalize Refinitiv harvest parquets to canonical join-friendly schemas."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

FIELD_CANONICAL = {
    "Volatility - 30 days": "volatility_30d",
    "Volatility - 90 days": "volatility_90d",
    "Put Call Ratio": "put_call_ratio",
    "Short Interest Pct": "short_interest_pct",
    "Earnings Per Share - Mean": "eps_mean",
    "TR.Volatility30D": "volatility_30d",
    "TR.Volatility90D": "volatility_90d",
    "TR.PutCallRatio": "put_call_ratio",
    "TR.ShortInterestPct": "short_interest_pct",
    "TR.EPSMean": "eps_mean",
    "Adjustment Factor": "adjustment_factor",
}


def _snake(s: str) -> str:
    s = re.sub(r"[^\w]+", "_", str(s).strip().lower())
    return re.sub(r"_+", "_", s).strip("_")


def normalize_security_master(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    rename = {
        "Instrument": "ric",
        "Company Common Name": "company_name",
        "ISIN": "isin",
        "Exchange Ticker": "exchange_ticker",
        "TRBC Economic Sector Name": "trbc_sector",
        "TRBC Industry Name": "trbc_industry",
        "Company Market Cap": "market_cap",
        "Outstanding Shares": "shares_outstanding",
        "Free Float (Percent)": "free_float_pct",
        "Exchange Country Code": "country_code",
    }
    out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})
    if "ric" not in out.columns and "Instrument" in out.columns:
        out["ric"] = out["Instrument"]
    return out


def normalize_index_membership_pit(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    if "constituent_ric" not in out.columns:
        out["constituent_ric"] = pd.NA
    if "Constituent RIC" in out.columns:
        out["constituent_ric"] = out["constituent_ric"].fillna(out["Constituent RIC"])
    if "Instrument" in out.columns:
        out["constituent_ric"] = out["constituent_ric"].fillna(out["Instrument"])
    if "constituent_name" not in out.columns and "Constituent Name" in out.columns:
        out["constituent_name"] = out["Constituent Name"]
    if "as_of_date" not in out.columns:
        if "sdate" in out.columns:
            out["as_of_date"] = pd.to_datetime(out["sdate"], format="%Y%m%d", errors="coerce").dt.strftime(
                "%Y-%m-%d"
            )
        elif "SDate" in out.columns:
            out["as_of_date"] = pd.to_datetime(out["SDate"], errors="coerce").dt.strftime("%Y-%m-%d")
    if "queried_index" not in out.columns and "index_ric" in out.columns:
        out["queried_index"] = out["index_ric"]
    keep = [
        c
        for c in [
            "index_ric",
            "queried_index",
            "pit_ric",
            "as_of_date",
            "constituent_ric",
            "constituent_name",
            "source",
            "pulled_at",
            "error",
        ]
        if c in out.columns
    ]
    return out[keep].drop_duplicates(subset=[c for c in ["index_ric", "as_of_date", "constituent_ric"] if c in keep])


def normalize_corporate_actions_snapshot(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    if "ric" not in out.columns and "Instrument" in out.columns:
        out["ric"] = out["Instrument"]
    if "adjustment_factor" not in out.columns and "Adjustment Factor" in out.columns:
        out["adjustment_factor"] = out["Adjustment Factor"]
    for col in ["TR.DividendExDate", "TR.DividendAmount", "TR.SplitFactor"]:
        if col in out.columns:
            out[_snake(col)] = out[col]
    keep = [c for c in ["ric", "adjustment_factor", "source", "panel", "pulled_at"] if c in out.columns]
    return out[keep]


def normalize_long_history(
    frame: pd.DataFrame,
    *,
    default_field: str | None = None,
) -> pd.DataFrame:
    """Fix wide-melt history panels (ric/field swap) and canonical field names."""
    if frame.empty:
        return frame
    out = frame.copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")

    # Melt bug: single-field history leaves RIC in `field`, ric null.
    if out["ric"].isna().all() if "ric" in out.columns else False:
        if "field" in out.columns:
            maybe_ric = out["field"].astype(str).str.match(r"^[A-Z0-9].*(\.[A-Z]{1,2}|=)$", na=False)
            if maybe_ric.mean() > 0.5:
                out["ric"] = out["field"]
                out["field"] = default_field or "eps_mean"

    if "field" in out.columns:
        out["metric"] = out["field"].map(lambda x: FIELD_CANONICAL.get(str(x), _snake(str(x))))

    cols = [c for c in ["date", "ric", "metric", "field", "value", "source", "panel", "pulled_at", "error"] if c in out.columns]
    out = out[cols]
    key = [c for c in ["date", "ric", "metric"] if c in out.columns]
    if key:
        out = out.drop_duplicates(subset=key, keep="last")
    return out


def normalize_panel(name: str, frame: pd.DataFrame, **kwargs: Any) -> pd.DataFrame:
    if name == "refinitiv_security_master":
        return normalize_security_master(frame)
    if name == "index_membership_pit":
        return normalize_index_membership_pit(frame)
    if name == "corporate_actions_snapshot":
        return normalize_corporate_actions_snapshot(frame)
    if name in {"vol_surface_metrics_daily", "estimate_revisions_daily"}:
        return normalize_long_history(frame, default_field=kwargs.get("default_field"))
    return frame
