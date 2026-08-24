#!/usr/bin/env python3
"""Value-first Refinitiv harvest runner (Jobs 1-4) for Wave 0+1 collection."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DEFAULT_ENTITLEMENT = REPO / "docs/status/generated/refinitiv_value_entitlement_map.json"

sys.path.insert(0, str(REPO / "scripts"))
from refinitiv_backfill_runner import (  # noqa: E402
    coverage_stats,
    fetch_history_batched,
    fetch_snapshot,
    utc_now,
    write_parquet,
)
from refinitiv_lseg_session import load_env, platform_session  # noqa: E402
from refinitiv_schema_normalize import normalize_panel  # noqa: E402
from refinitiv_universe_loader import load_universe_rics  # noqa: E402

SECURITY_MASTER_FIELDS = [
    "TR.CommonName",
    "TR.ISIN",
    "TR.ExchangeTicker",
    "TR.TRBCEconomicSector",
    "TR.TRBCIndustry",
    "TR.CompanyMarketCap",
    "TR.SharesOutstanding",
    "TR.FreeFloatPct",
    "TR.ExchangeCountryCode",
    "TR.Currency",
]

CORP_ACTION_FIELDS = [
    "TR.DividendExDate",
    "TR.DividendAmount",
    "TR.SplitFactor",
    "TR.CAAdjustmentFactor",
]

DEFAULT_RISK_FIELDS = [
    "TR.ShortInterestPct",
]

DEFAULT_RISK_SNAPSHOT_FIELDS = [
    "TR.Volatility30D",
    "TR.Volatility90D",
    "TR.PutCallRatio",
]

PIT_INDICES_PROVEN = [".SPX", ".JKSE"]

INDEX_CONSTITUENT_FIELDS = [
    "TR.IndexConstituentRIC",
    "TR.IndexConstituentName",
]

PIT_INDEX_RIC_MAP = {
    ".SPX": "0#.SPX",
    ".JKSE": "0#.JKSE",
    ".TWII": "0#.TWII",
    ".N225": "0#.N225",
    ".KS11": "0#.KSE",
    ".STI": "0#.STI",
}

CONSENSUS_SNAPSHOT_FIELDS = [
    "TR.EPSMean",
    "TR.RevenueMean",
    "TR.PriceTargetMean",
    "TR.PriceTargetHigh",
    "TR.PriceTargetLow",
]

ESG_SNAPSHOT_FIELDS = [
    "TR.TRESGScore",
    "TR.ESGScore",
    "TR.EnvironmentPillarScore",
    "TR.SocialPillarScore",
    "TR.GovernancePillarScore",
]


def _fundamental_response_to_df(response: Any) -> pd.DataFrame:
    if response is None:
        return pd.DataFrame()
    if isinstance(response, pd.DataFrame):
        return response.copy()
    if hasattr(response, "data") and hasattr(response.data, "df"):
        return response.data.df.copy()
    return pd.DataFrame()


def pit_indices_from_map(ent_map: dict[str, Any]) -> list[str]:
    """Return index RICs entitled for PIT membership pulls."""
    reverse = {v: k for k, v in PIT_INDEX_RIC_MAP.items()}
    entitled: list[str] = []
    for cat_id in ("B7_B8_index_constituents", "B8_asia_pit_indices"):
        cat = (ent_map.get("categories") or {}).get(cat_id) or {}
        if cat.get("status") == "fail":
            continue
        for variant in (cat.get("probe") or {}).get("variants") or []:
            if not variant.get("ok") or variant.get("variant") != "pit_0hash_sdate":
                continue
            idx = variant.get("index_ric") or reverse.get(str(variant.get("ric", "")))
            if idx and str(idx) not in entitled:
                entitled.append(str(idx))
    return entitled or list(PIT_INDICES_PROVEN)


def today_stamp() -> str:
    return date.today().isoformat()


def quarterly_pit_dates(start: str, end: str) -> list[str]:
    """Return YYYYMMDD strings on 15th of Jan/Apr/Jul/Oct within [start, end]."""
    start_d = pd.Timestamp(start)
    end_d = pd.Timestamp(end)
    months = [1, 4, 7, 10]
    out: list[str] = []
    for year in range(start_d.year, end_d.year + 1):
        for month in months:
            ts = pd.Timestamp(year=year, month=month, day=15)
            if start_d <= ts <= end_d:
                out.append(ts.strftime("%Y%m%d"))
    return out


def monthly_pit_dates(start: str, end: str) -> list[str]:
    """Return YYYYMMDD on the 15th of each month within [start, end]."""
    start_d = pd.Timestamp(start)
    end_d = pd.Timestamp(end)
    cur = pd.Timestamp(year=start_d.year, month=start_d.month, day=15)
    if cur < start_d:
        cur = cur + pd.offsets.MonthBegin(0) + pd.Timedelta(days=14)
    out: list[str] = []
    while cur <= end_d:
        if cur >= start_d:
            out.append(cur.strftime("%Y%m%d"))
        cur = cur + pd.offsets.MonthBegin(1) + pd.Timedelta(days=14)
    return out


def write_parquet_normalized(
    frame: pd.DataFrame,
    path: Path,
    *,
    panel: str,
    default_field: str | None = None,
) -> dict[str, Any]:
    norm = normalize_panel(panel, frame, default_field=default_field)
    meta = write_parquet(norm, path)
    meta["normalized"] = True
    return meta


def load_entitlement_map(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def constituent_api_from_map(ent_map: dict[str, Any]) -> dict[str, Any]:
    cat = (ent_map.get("categories") or {}).get("B7_B8_index_constituents", {})
    variants = (cat.get("probe") or {}).get("variants") or []
    pit = next((v for v in variants if v.get("ok") and v.get("variant") == "pit_0hash_sdate"), None)
    best = pit or (cat.get("probe") or {}).get("best_variant")
    if best and best.get("ok"):
        return {
            "method": best.get("method", "get_data"),
            "variant": best.get("variant"),
            "ric_pattern": best.get("ric", "0#.SPX"),
            "parameters": dict(best.get("parameters") or {}),
            "fields": INDEX_CONSTITUENT_FIELDS,
        }
    rec = ent_map.get("constituent_api_recommendation")
    if rec:
        return rec
    return {
        "method": "get_data",
        "variant": "pit_0hash_sdate",
        "ric_pattern": "0#.SPX",
        "parameters": {},
        "fields": INDEX_CONSTITUENT_FIELDS,
    }


def risk_fields_from_map(ent_map: dict[str, Any]) -> list[str]:
    cat = (ent_map.get("categories") or {}).get("A9_A11_risk", {})
    status = cat.get("status", "partial")
    if status == "fail":
        return ["TR.Volatility30D"]
    return DEFAULT_RISK_FIELDS


def fetch_index_membership_pit(
    ld: object,
    indices: list[str],
    pit_dates: list[str],
    *,
    api: dict[str, Any],
) -> pd.DataFrame:
    fields = list(api.get("fields") or INDEX_CONSTITUENT_FIELDS)
    rows: list[pd.DataFrame] = []

    for index_ric in indices:
        pit_ric = PIT_INDEX_RIC_MAP.get(index_ric, f"0#{index_ric}")
        for sdate in pit_dates:
            params = dict(api.get("parameters") or {})
            params["SDate"] = sdate
            try:
                frame = ld.get_data(universe=[pit_ric], fields=fields, parameters=params)  # type: ignore[attr-defined]
                if frame is None or frame.empty:
                    continue
                out = frame.copy()
                out.columns = [str(c) for c in out.columns]
                out["index_ric"] = index_ric
                out["pit_ric"] = pit_ric
                out["sdate"] = sdate
                out["source"] = "lseg.get_data.pit_constituents"
                out["pulled_at"] = utc_now()
                rows.append(out)
            except Exception as exc:
                err = pd.DataFrame(
                    {
                        "index_ric": [index_ric],
                        "pit_ric": [pit_ric],
                        "sdate": [sdate],
                        "error": [f"{type(exc).__name__}: {exc}"],
                        "source": ["lseg.get_data.pit_constituents"],
                        "pulled_at": [utc_now()],
                    }
                )
                rows.append(err)

    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True, sort=False)


def run_job_1(ld: object, rics: list[str], out_dir: Path) -> dict[str, Any]:
    frame = fetch_snapshot(ld, rics, SECURITY_MASTER_FIELDS, panel="security_master")
    meta = write_parquet_normalized(frame, out_dir / "refinitiv_security_master.parquet", panel="refinitiv_security_master")
    meta["job"] = "job_1"
    meta["panel"] = "security_master"
    meta["coverage"] = coverage_stats(normalize_panel("refinitiv_security_master", frame))
    meta["rics_requested"] = len(rics)
    return meta


def run_job_2(
    ld: object,
    indices: list[str],
    out_dir: Path,
    *,
    ent_map: dict[str, Any],
    start: str = "2018-01-15",
    end: str = "2026-01-15",
    frequency: str = "quarterly",
) -> dict[str, Any]:
    api = constituent_api_from_map(ent_map)
    pit_dates = monthly_pit_dates(start, end) if frequency == "monthly" else quarterly_pit_dates(start, end)
    frame = fetch_index_membership_pit(ld, indices, pit_dates, api=api)
    meta = write_parquet_normalized(frame, out_dir / "index_membership_pit.parquet", panel="index_membership_pit")
    meta["job"] = "job_2"
    meta["panel"] = "index_membership_pit"
    norm = normalize_panel("index_membership_pit", frame)
    meta["coverage"] = coverage_stats(norm, key_cols=["index_ric", "as_of_date"] if not norm.empty else None)
    meta["pit_dates"] = len(pit_dates)
    meta["pit_frequency"] = frequency
    meta["indices"] = indices
    meta["constituent_api"] = api
    return meta


def run_job_3(ld: object, rics: list[str], out_dir: Path) -> dict[str, Any]:
    frame = fetch_snapshot(ld, rics, CORP_ACTION_FIELDS, panel="corporate_actions")
    meta = write_parquet_normalized(frame, out_dir / "corporate_actions_snapshot.parquet", panel="corporate_actions_snapshot")
    meta["job"] = "job_3"
    meta["panel"] = "corporate_actions"
    meta["coverage"] = coverage_stats(normalize_panel("corporate_actions_snapshot", frame))
    meta["rics_requested"] = len(rics)

    # Event-style history for dividend fields where supported.
    hist = fetch_history_batched(
        ld,
        rics[: min(20, len(rics))],
        ["TR.DividendAmount"],
        panel="corporate_actions_events",
        batch_size=8,
        start="2018-01-01",
        end=None,
        interval="daily",
        adjustments=None,
    )
    hist_meta = write_parquet(hist, out_dir / "corporate_actions_events.parquet")
    hist_meta["job"] = "job_3_events"
    hist_meta["panel"] = "corporate_actions_events"
    hist_meta["coverage"] = coverage_stats(hist, key_cols=["ric"] if "ric" in hist.columns else None)
    meta["events_artifact"] = hist_meta
    return meta


def run_job_5(ld: object, rics: list[str], out_dir: Path, *, start: str = "2018-01-01") -> dict[str, Any]:
    """Estimate revision proxy: EPS mean daily history where entitled."""
    fields = ["TR.EPSMean"]
    frame = fetch_history_batched(
        ld,
        rics,
        fields,
        panel="estimate_revisions",
        batch_size=8,
        start=start,
        end=None,
        interval="daily",
        adjustments=None,
    )
    meta = write_parquet_normalized(
        frame,
        out_dir / "estimate_revisions_daily.parquet",
        panel="estimate_revisions_daily",
        default_field="eps_mean",
    )
    meta["job"] = "job_5"
    meta["panel"] = "estimate_revisions"
    meta["coverage"] = coverage_stats(frame, key_cols=["ric"] if "ric" in frame.columns else None)
    meta["rics_requested"] = len(rics)
    return meta


FUNDAMENTALS_SNAPSHOT_FIELDS = [
    "TR.Revenue",
    "TR.NetIncome",
    "TR.F.TotRevenue",
    "TR.TotalDebt",
    "TR.FreeCashFlow",
    "TR.BookValuePerShare",
]


def run_job_6(ld: object, rics: list[str], out_dir: Path, *, ent_map: dict[str, Any]) -> dict[str, Any]:
    """Fundamentals: PIT/history if probe recommends; else cross-section snapshot."""
    cat = (ent_map.get("categories") or {}).get("D8_pit_fundamentals") or {}
    rec = cat.get("recommended_harvest") or {}
    label = rec.get("label")
    fields = list(rec.get("fields") or FUNDAMENTALS_SNAPSHOT_FIELDS)
    frames: list[pd.DataFrame] = []

    if label and label not in {"get_data_snapshot"}:
        try:
            from lseg.data.content import fundamental_and_reference as fr  # type: ignore

            params = dict(rec.get("parameters") or {})
            if not params and label == "frq_fy":
                params = {"SDate": "0", "EDate": "-20", "FRQ": "FY"}
            elif not params and label in {"fy0", "ltm"}:
                params = {"Period": label.upper() if label == "ltm" else "FY0"}

            failed_rics: list[str] = []
            for ric in rics:
                try:
                    definition = fr.Definition(
                        universe=ric,
                        fields=fields,
                        parameters=params,
                    )
                    frame = _fundamental_response_to_df(definition.get_data())
                    if frame is not None and not frame.empty:
                        frame = frame.copy()
                        if "ric" not in frame.columns and "Instrument" in frame.columns:
                            frame["ric"] = frame["Instrument"]
                        elif "ric" not in frame.columns:
                            frame["ric"] = ric
                        frame["fundamental_method"] = label
                        frame["source"] = "lseg.fundamental_and_reference"
                        frame["pulled_at"] = utc_now()
                        frames.append(frame)
                    else:
                        failed_rics.append(ric)
                except Exception:
                    failed_rics.append(ric)

            if failed_rics:
                snap = fetch_snapshot(ld, failed_rics, fields, panel="fundamentals_snapshot")
                if not snap.empty:
                    snap = snap.copy()
                    if "Instrument" in snap.columns:
                        snap = snap.rename(columns={"Instrument": "ric"})
                    snap["fundamental_method"] = "get_data_snapshot_fallback"
                    snap["source"] = "lseg.get_data"
                    snap["pulled_at"] = utc_now()
                    frames.append(snap)
        except Exception as exc:
            err = pd.DataFrame({"ric": rics, "error": str(exc), "source": ["job_6_error"] * len(rics)})
            frames.append(err)
    else:
        frame = fetch_snapshot(ld, rics, fields, panel="fundamentals_snapshot")
        if not frame.empty:
            frame = normalize_panel("refinitiv_security_master", frame)  # ric rename only partial
            if "Instrument" in frame.columns:
                frame = frame.rename(columns={"Instrument": "ric"})
            frame["fundamental_method"] = label or "get_data_snapshot"
            frames.append(frame)

    if not frames:
        out = pd.DataFrame()
    else:
        out = pd.concat(frames, ignore_index=True, sort=False)
    meta = write_parquet(out, out_dir / "fundamentals_panel.parquet")
    meta["job"] = "job_6"
    meta["panel"] = "fundamentals"
    meta["coverage"] = coverage_stats(out)
    meta["rics_requested"] = len(rics)
    meta["fundamental_method"] = label or "get_data_snapshot"
    return meta


def run_job_4(
    ld: object,
    rics: list[str],
    out_dir: Path,
    *,
    ent_map: dict[str, Any],
    start: str = "2015-01-01",
) -> dict[str, Any]:
    """Risk tape: SI% history (EDP-proven) + vol/put-call snapshot cross-section."""
    hist_fields = risk_fields_from_map(ent_map)
    hist = fetch_history_batched(
        ld,
        rics,
        hist_fields,
        panel="risk_tape_history",
        batch_size=8,
        start=start,
        end=None,
        interval="daily",
        adjustments=None,
    )
    snap = fetch_snapshot(ld, rics, DEFAULT_RISK_SNAPSHOT_FIELDS, panel="risk_tape_snapshot")
    hist_norm = normalize_panel("vol_surface_metrics_daily", hist, default_field=hist_fields[0] if hist_fields else None)
    if not snap.empty:
        snap_long = snap.melt(id_vars=[c for c in snap.columns if c in {"Instrument", "source", "panel", "pulled_at"}], var_name="metric_raw", value_name="value")
        snap_long = snap_long.rename(columns={"Instrument": "ric"})
        snap_long["date"] = date.today().isoformat()
        snap_long["metric"] = snap_long["metric_raw"].map(lambda x: str(x))
        hist_norm = pd.concat([hist_norm, snap_long], ignore_index=True, sort=False)
    meta = write_parquet(hist_norm, out_dir / "vol_surface_metrics_daily.parquet")
    meta["job"] = "job_4"
    meta["panel"] = "risk_tape"
    meta["fields_history"] = hist_fields
    meta["fields_snapshot"] = DEFAULT_RISK_SNAPSHOT_FIELDS
    meta["coverage"] = coverage_stats(hist_norm, key_cols=["ric"] if "ric" in hist_norm.columns else None)
    meta["rics_requested"] = len(rics)
    return meta


def run_job_7(ld: object, indices: list[str], out_dir: Path) -> dict[str, Any]:
    """Current index membership snapshot for entitled indices."""
    frames: list[pd.DataFrame] = []
    errors: list[dict[str, str]] = []
    for index_ric in indices:
        try:
            frame = fetch_snapshot(ld, [index_ric], INDEX_CONSTITUENT_FIELDS, panel="index_membership_current")
            if frame.empty:
                continue
            frame = frame.copy()
            frame["index_ric"] = index_ric
            frames.append(frame)
        except Exception as exc:
            errors.append({"index_ric": index_ric, "error": f"{type(exc).__name__}: {exc}"})
    out = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    meta = write_parquet_normalized(out, out_dir / "index_membership_current.parquet", panel="index_membership_pit")
    meta["job"] = "job_7"
    meta["panel"] = "index_membership_current"
    meta["indices"] = indices
    meta["indices_ok"] = list({str(f["index_ric"].iloc[0]) for f in frames if "index_ric" in f.columns})
    meta["errors"] = errors
    meta["coverage"] = coverage_stats(out)
    return meta


def run_job_8(ld: object, rics: list[str], out_dir: Path) -> dict[str, Any]:
    """Analyst consensus snapshot (E1-E3)."""
    frame = fetch_snapshot(ld, rics, CONSENSUS_SNAPSHOT_FIELDS, panel="analyst_consensus")
    meta = write_parquet_normalized(frame, out_dir / "analyst_consensus_snapshot.parquet", panel="refinitiv_security_master")
    meta["job"] = "job_8"
    meta["panel"] = "analyst_consensus"
    meta["rics_requested"] = len(rics)
    meta["coverage"] = coverage_stats(frame)
    return meta


def run_job_9(ld: object, rics: list[str], out_dir: Path) -> dict[str, Any]:
    """ESG pillar snapshot."""
    frame = fetch_snapshot(ld, rics, ESG_SNAPSHOT_FIELDS, panel="esg_snapshot")
    meta = write_parquet_normalized(frame, out_dir / "esg_snapshot.parquet", panel="refinitiv_security_master")
    meta["job"] = "job_9"
    meta["panel"] = "esg_snapshot"
    meta["rics_requested"] = len(rics)
    meta["coverage"] = coverage_stats(frame)
    return meta


JOB_RUNNERS = {
    "job_1": "run_job_1",
    "job_2": "run_job_2",
    "job_3": "run_job_3",
    "job_4": "run_job_4",
}

WAVE_JOBS = {
    "wave0": ["job_1"],
    "wave1": ["job_2", "job_3", "job_4", "job_5", "job_6", "job_7", "job_8", "job_9"],
    "scale": ["job_2", "job_4", "job_5"],
    "fundamentals": ["job_6"],
    "snapshots": ["job_7", "job_8", "job_9"],
    "complete": ["job_1", "job_2", "job_3", "job_4", "job_5", "job_6", "job_7", "job_8", "job_9"],
    "all": ["job_1", "job_2", "job_3", "job_4", "job_5", "job_6", "job_7", "job_8", "job_9"],
}

PROFILE_DEFAULTS = {
    "trial": {
        "universe": "value_harvest_core",
        "risk_universe": "us_risk_sleeve",
        "pit_start": "2018-01-15",
        "pit_end": "2026-01-15",
        "pit_frequency": "quarterly",
    },
    "scaled": {
        "universe": "value_harvest_scaled",
        "risk_universe": "us_risk_sleeve_scaled",
        "pit_start": "2010-01-15",
        "pit_end": "2026-01-15",
        "pit_frequency": "monthly",
    },
    "complete": {
        "universe": "value_harvest_max",
        "risk_universe": "us_risk_sleeve_scaled",
        "pit_start": "2010-01-15",
        "pit_end": "2026-06-15",
        "pit_frequency": "monthly",
    },
}


def run_jobs(
    jobs: list[str],
    *,
    stamp: str,
    universe: str,
    risk_universe: str,
    entitlement_path: Path,
    pit_start: str,
    pit_end: str,
    pit_frequency: str,
) -> dict[str, Any]:
    ent_map = load_entitlement_map(entitlement_path)
    run_dir = REPO / "data_lake" / "refinitiv_backfill" / stamp
    out_dir = run_dir / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)

    harvest_rics = load_universe_rics(universe)
    risk_rics = load_universe_rics(risk_universe)
    pit_indices_all = load_universe_rics("pit_indices")
    pit_indices = pit_indices_from_map(ent_map)
    pit_indices = [i for i in pit_indices if i in pit_indices_all or i in PIT_INDEX_RIC_MAP]

    manifest: dict[str, Any] = {
        "generated_at": utc_now(),
        "stamp": stamp,
        "jobs": jobs,
        "universe": universe,
        "artifacts": [],
        "errors": [],
    }

    with platform_session() as ld:
        for job in jobs:
            try:
                if job == "job_1":
                    art = run_job_1(ld, harvest_rics, out_dir)
                elif job == "job_2":
                    art = run_job_2(
                        ld,
                        pit_indices,
                        out_dir,
                        ent_map=ent_map,
                        start=pit_start,
                        end=pit_end,
                        frequency=pit_frequency,
                    )
                elif job == "job_3":
                    art = run_job_3(ld, harvest_rics, out_dir)
                elif job == "job_4":
                    art = run_job_4(ld, risk_rics, out_dir, ent_map=ent_map)
                elif job == "job_5":
                    e4 = ((ent_map.get("categories") or {}).get("E4_estimate_revisions") or {}).get("status")
                    if e4 == "fail":
                        manifest["errors"].append({"job": job, "error": "E4_estimate_revisions not entitled; skipped"})
                        continue
                    art = run_job_5(ld, harvest_rics, out_dir)
                elif job == "job_6":
                    d8 = ((ent_map.get("categories") or {}).get("D8_pit_fundamentals") or {}).get("status")
                    if d8 == "fail":
                        manifest["errors"].append({"job": job, "error": "D8 fundamentals not entitled; skipped"})
                        continue
                    art = run_job_6(ld, harvest_rics, out_dir, ent_map=ent_map)
                elif job == "job_7":
                    art = run_job_7(ld, pit_indices, out_dir)
                elif job == "job_8":
                    e13 = ((ent_map.get("categories") or {}).get("E1_E3_consensus_snapshot") or {}).get("status")
                    if e13 == "fail":
                        manifest["errors"].append({"job": job, "error": "E1_E3 consensus not entitled; skipped"})
                        continue
                    art = run_job_8(ld, harvest_rics, out_dir)
                elif job == "job_9":
                    h1 = ((ent_map.get("categories") or {}).get("H1_esg_snapshot") or {}).get("status")
                    if h1 == "fail":
                        manifest["errors"].append({"job": job, "error": "H1 ESG not entitled; skipped"})
                        continue
                    art = run_job_9(ld, harvest_rics, out_dir)
                else:
                    raise ValueError(f"Unknown job {job!r}")
                manifest["artifacts"].append(art)
                if art.get("events_artifact"):
                    manifest["artifacts"].append(art["events_artifact"])
            except Exception as exc:
                manifest["errors"].append(
                    {
                        "job": job,
                        "error": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc(limit=5),
                    }
                )

    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    manifest["processed_dir"] = str(out_dir)
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="Refinitiv value-first harvest runner (Jobs 1-4).")
    ap.add_argument(
        "--job",
        choices=["job_0", "job_1", "job_2", "job_3", "job_4", "job_5", "job_6", "job_7", "job_8", "job_9", "wave0", "wave1", "scale", "fundamentals", "snapshots", "complete", "all"],
        default="wave1",
    )
    ap.add_argument("--env", default=".env.local")
    ap.add_argument("--universe", default=None)
    ap.add_argument("--risk-universe", default=None)
    ap.add_argument("--profile", choices=["trial", "scaled", "complete"], default="trial")
    ap.add_argument("--pit-start", default=None)
    ap.add_argument("--pit-end", default=None)
    ap.add_argument("--pit-frequency", choices=["quarterly", "monthly"], default=None)
    ap.add_argument("--stamp", default=None)
    ap.add_argument("--entitlement", default=str(DEFAULT_ENTITLEMENT))
    args = ap.parse_args()

    if args.job == "job_0":
        print("Use scripts/refinitiv_value_entitlement_probe.py for job_0.", file=sys.stderr)
        return 2

    load_env(args.env)
    stamp = args.stamp or today_stamp()
    entitlement_path = Path(args.entitlement)
    if not entitlement_path.is_absolute():
        entitlement_path = REPO / entitlement_path

    prof = PROFILE_DEFAULTS[args.profile]
    universe = args.universe or prof["universe"]
    risk_universe = args.risk_universe or prof["risk_universe"]
    pit_start = args.pit_start or prof["pit_start"]
    pit_end = args.pit_end or prof["pit_end"]
    pit_frequency = args.pit_frequency or prof["pit_frequency"]

    if args.job in WAVE_JOBS:
        jobs = WAVE_JOBS[args.job]
    else:
        jobs = [args.job]

    try:
        manifest = run_jobs(
            jobs,
            stamp=stamp,
            universe=universe,
            risk_universe=risk_universe,
            entitlement_path=entitlement_path,
            pit_start=pit_start,
            pit_end=pit_end,
            pit_frequency=pit_frequency,
        )
    except Exception as exc:
        print(f"Harvest failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1

    print(
        json.dumps(
            {
                "stamp": manifest.get("stamp"),
                "processed_dir": manifest.get("processed_dir"),
                "jobs": manifest.get("jobs"),
                "artifacts": [
                    {k: a[k] for k in ("path", "rows", "bytes", "job", "panel") if k in a}
                    for a in manifest.get("artifacts", [])
                ],
                "errors": manifest.get("errors", []),
                "manifest_path": manifest.get("manifest_path"),
            },
            indent=2,
        )
    )
    return 1 if manifest.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
