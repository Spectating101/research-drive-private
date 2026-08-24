#!/usr/bin/env python3
"""Run phased Refinitiv/LSEG historical backfill from config/refinitiv_harvest_plan.json."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = REPO / "config/refinitiv_harvest_plan.json"

sys.path.insert(0, str(REPO / "scripts"))
from fetch_accessible_market_universes import load_universes  # noqa: E402
from refinitiv_lseg_session import load_env, platform_session  # noqa: E402

PHASE_ALIASES = {
    "p1": "p1_idx_core",
    "p2": "p2_global_backbone",
    "p3": "p3_risk_derivatives",
    "p4": "p4_analyst",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_stamp() -> str:
    return date.today().isoformat()


def load_plan(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_phase_key(phase: str) -> str:
    key = PHASE_ALIASES.get(phase, phase)
    if key not in {v for v in PHASE_ALIASES.values()}:
        raise ValueError(f"Unknown phase {phase!r}; expected p1|p2|p3|p4|all")
    return key


def phase_rics(plan: dict[str, Any], phase_key: str) -> list[str]:
    phase = plan["phases"][phase_key]
    rics: list[str] = []
    if phase.get("universe_id"):
        universes_path = REPO / plan.get("universes_config", "config/markets/asia_yfinance_universes.json")
        for uni in load_universes(universes_path, only={phase["universe_id"]}):
            rics.extend(uni.tickers)
    rics.extend(str(x) for x in phase.get("rics", []))
    rics.extend(str(x) for x in phase.get("extra_rics", []))
    return _dedupe(rics)


def _dedupe(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        t = item.strip()
        if not t or t in seen:
            continue
        out.append(t)
        seen.add(t)
    return out


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _normalize_frame(frame: pd.DataFrame | None, *, source: str, panel: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    out.columns = [str(c) for c in out.columns]
    out["source"] = source
    out["panel"] = panel
    out["pulled_at"] = utc_now()
    return out


def _history_to_long(frame: pd.DataFrame, *, default_field: str | None = None) -> pd.DataFrame:
    """Convert LSEG wide get_history frame (Date × RIC/field) to tidy rows."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    wide = frame.copy()
    wide.index = pd.to_datetime(wide.index, errors="coerce")
    wide = wide.loc[wide.index.notna()]
    wide.index.name = "date"

    if isinstance(wide.columns, pd.MultiIndex):
        long = wide.stack(level=[0, 1], future_stack=True).rename("value").reset_index()
        long.columns = ["date", "ric", "field", "value"]
    else:
        long = wide.reset_index().melt(id_vars=["date"], var_name="ric", value_name="value")
        long["field"] = default_field

    long["date"] = pd.to_datetime(long["date"], errors="coerce").dt.date.astype(str)
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    long = long.dropna(subset=["date"])
    return long.sort_values(["ric", "date", "field"]).reset_index(drop=True)


def fetch_snapshot(ld: object, rics: list[str], fields: list[str], *, panel: str) -> pd.DataFrame:
    if not rics or not fields:
        return pd.DataFrame()
    frame = ld.get_data(universe=rics, fields=fields)  # type: ignore[attr-defined]
    return _normalize_frame(frame, source="lseg.get_data", panel=panel)


def fetch_history_batched(
    ld: object,
    rics: list[str],
    fields: list[str],
    *,
    panel: str,
    batch_size: int,
    start: str,
    end: str | None,
    interval: str,
    adjustments: str | None,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    end_date = end or date.today().isoformat()
    for batch in _chunks(rics, batch_size):
        kwargs: dict[str, Any] = {
            "universe": batch,
            "fields": fields,
            "start": start,
            "end": end_date,
            "interval": interval,
        }
        if adjustments:
            kwargs["adjustments"] = adjustments
        try:
            frame = ld.get_history(**kwargs)  # type: ignore[attr-defined]
            long = _history_to_long(frame, default_field=fields[0] if len(fields) == 1 else None)
            if not long.empty:
                long["source"] = "lseg.get_history"
                long["panel"] = panel
                long["pulled_at"] = utc_now()
                frames.append(long)
        except Exception as exc:
            err = pd.DataFrame(
                {
                    "ric": batch,
                    "error": f"{type(exc).__name__}: {exc}",
                    "source": "lseg.get_history",
                    "panel": panel,
                    "pulled_at": utc_now(),
                }
            )
            frames.append(err)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def coverage_stats(frame: pd.DataFrame, *, key_cols: list[str] | None = None) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {"rows": 0, "cols": 0, "missing_pct": {}, "date_range": None}
    stats: dict[str, Any] = {
        "rows": int(len(frame)),
        "cols": int(len(frame.columns)),
        "columns": [str(c) for c in frame.columns],
    }
    miss = {}
    for col in frame.columns:
        if col in {"source", "panel", "pulled_at", "error"}:
            continue
        miss[str(col)] = round(float(frame[col].isna().mean()) * 100.0, 2)
    stats["missing_pct"] = miss
    date_col = next((c for c in frame.columns if str(c).lower() in {"date", "datetime"}), None)
    if date_col is not None:
        try:
            dates = pd.to_datetime(frame[date_col], errors="coerce").dropna()
            if not dates.empty:
                stats["date_range"] = {
                    "min": str(dates.min().date()),
                    "max": str(dates.max().date()),
                }
        except Exception:
            stats["date_range"] = None
    if key_cols:
        stats["unique_keys"] = {k: int(frame[k].nunique()) for k in key_cols if k in frame.columns}
    return stats


def write_parquet(frame: pd.DataFrame, path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if frame.empty:
        path.write_bytes(b"")
        return {"path": str(path), "rows": 0, "bytes": 0, "empty": True}
    frame.to_parquet(path, index=False)
    size = path.stat().st_size
    return {"path": str(path), "rows": int(len(frame)), "bytes": size, "empty": False}


def run_p1(ld: object, plan: dict[str, Any], out_dir: Path) -> list[dict[str, Any]]:
    phase = plan["phases"]["p1_idx_core"]
    rics = phase_rics(plan, "p1_idx_core")
    artifacts: list[dict[str, Any]] = []

    for snap_key in ("metadata_snapshot", "fundamentals_snapshot", "analyst_snapshot"):
        snap = phase[snap_key]
        panel = snap_key.replace("_snapshot", "")
        frame = fetch_snapshot(ld, rics, list(snap["fields"]), panel=panel)
        meta = write_parquet(frame, out_dir / snap["output"])
        meta["panel"] = panel
        meta["coverage"] = coverage_stats(frame)
        artifacts.append(meta)

    hist = phase["daily_history"]
    hist_frame = fetch_history_batched(
        ld,
        rics,
        list(hist["fields"]),
        panel="idx_daily",
        batch_size=int(hist.get("batch_size", 8)),
        start=str(hist.get("start", "2015-01-01")),
        end=hist.get("end"),
        interval=str(hist.get("interval", "daily")),
        adjustments=hist.get("adjustments"),
    )
    meta = write_parquet(hist_frame, out_dir / hist["output"])
    meta["panel"] = "idx_daily"
    meta["coverage"] = coverage_stats(hist_frame, key_cols=["ric"] if "ric" in hist_frame.columns else None)
    meta["rics_requested"] = len(rics)
    artifacts.append(meta)
    return artifacts


def run_p2(ld: object, plan: dict[str, Any], out_dir: Path) -> list[dict[str, Any]]:
    phase = plan["phases"]["p2_global_backbone"]
    rics = phase_rics(plan, "p2_global_backbone")
    hist = phase["daily_history"]
    frame = fetch_history_batched(
        ld,
        rics,
        list(hist["fields"]),
        panel="global_daily",
        batch_size=int(hist.get("batch_size", 8)),
        start=str(hist.get("start", "2010-01-01")),
        end=hist.get("end"),
        interval=str(hist.get("interval", "daily")),
        adjustments=hist.get("adjustments"),
    )
    meta = write_parquet(frame, out_dir / hist["output"])
    meta["panel"] = "global_daily"
    meta["coverage"] = coverage_stats(frame)
    meta["rics_requested"] = len(rics)
    return [meta]


def run_p3(ld: object, plan: dict[str, Any], out_dir: Path) -> list[dict[str, Any]]:
    phase = plan["phases"]["p3_risk_derivatives"]
    rics = phase_rics(plan, "p3_risk_derivatives")
    snap = phase["snapshot"]
    frame = fetch_snapshot(ld, rics, list(snap["fields"]), panel="risk_derivatives")
    meta = write_parquet(frame, out_dir / snap["output"])
    meta["panel"] = "risk_derivatives"
    meta["coverage"] = coverage_stats(frame)
    meta["rics_requested"] = len(rics)
    return [meta]


def run_p4(ld: object, plan: dict[str, Any], out_dir: Path) -> list[dict[str, Any]]:
    phase = plan["phases"]["p4_analyst"]
    rics = phase_rics(plan, "p4_analyst")
    snap = phase["snapshot"]
    frame = fetch_snapshot(ld, rics, list(snap["fields"]), panel="analyst")
    meta = write_parquet(frame, out_dir / snap["output"])
    meta["panel"] = "analyst"
    meta["coverage"] = coverage_stats(frame)
    meta["rics_requested"] = len(rics)
    return [meta]


RUNNERS = {
    "p1_idx_core": run_p1,
    "p2_global_backbone": run_p2,
    "p3_risk_derivatives": run_p3,
    "p4_analyst": run_p4,
}


def write_coverage_report(run_dir: Path, manifest: dict[str, Any]) -> Path:
    lines = [
        "# Refinitiv backfill coverage report",
        "",
        f"- Generated: {manifest.get('generated_at')}",
        f"- Stamp: {manifest.get('stamp')}",
        f"- Phases: {', '.join(manifest.get('phases', []))}",
        "",
    ]
    for art in manifest.get("artifacts", []):
        lines.append(f"## {art.get('panel', art.get('path'))}")
        lines.append(f"- Path: `{art.get('path')}`")
        lines.append(f"- Rows: {art.get('rows', 0)}")
        lines.append(f"- Bytes: {art.get('bytes', 0)}")
        cov = art.get("coverage") or {}
        if cov.get("date_range"):
            dr = cov["date_range"]
            lines.append(f"- Date range: {dr.get('min')} → {dr.get('max')}")
        miss = cov.get("missing_pct") or {}
        if miss:
            top = sorted(miss.items(), key=lambda kv: kv[1], reverse=True)[:8]
            lines.append("- Missing % (top fields): " + ", ".join(f"{k}={v}%" for k, v in top))
        lines.append("")
    path = run_dir / "coverage_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_phases(plan: dict[str, Any], phases: list[str], stamp: str | None) -> dict[str, Any]:
    run_stamp = stamp or today_stamp()
    run_dir = REPO / "data_lake" / "refinitiv_backfill" / run_stamp
    out_dir = run_dir / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "generated_at": utc_now(),
        "stamp": run_stamp,
        "phases": phases,
        "artifacts": [],
        "errors": [],
    }

    with platform_session() as ld:
        for phase_key in phases:
            runner = RUNNERS[phase_key]
            try:
                artifacts = runner(ld, plan, out_dir)
                manifest["artifacts"].extend(artifacts)
            except Exception as exc:
                manifest["errors"].append(
                    {
                        "phase": phase_key,
                        "error": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc(limit=5),
                    }
                )

    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report_path = write_coverage_report(run_dir, manifest)
    manifest["manifest_path"] = str(manifest_path)
    manifest["coverage_report_path"] = str(report_path)
    manifest["processed_dir"] = str(out_dir)
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="Refinitiv/LSEG phased backfill runner")
    ap.add_argument("--phase", choices=["p1", "p2", "p3", "p4", "all"], default="p1")
    ap.add_argument("--plan", default=str(DEFAULT_PLAN))
    ap.add_argument("--env", default=".env.local")
    ap.add_argument("--stamp", default=None, help="Output folder stamp (default: today UTC date)")
    args = ap.parse_args()

    load_env(args.env)
    plan_path = Path(args.plan)
    if not plan_path.is_absolute():
        plan_path = REPO / plan_path
    plan = load_plan(plan_path)

    if args.phase == "all":
        phase_keys = list(RUNNERS.keys())
    else:
        phase_keys = [resolve_phase_key(args.phase)]

    try:
        manifest = run_phases(plan, phase_keys, args.stamp)
    except Exception as exc:
        print(f"Backfill failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1

    print(json.dumps(
        {
            "stamp": manifest.get("stamp"),
            "processed_dir": manifest.get("processed_dir"),
            "artifacts": [
                {k: a[k] for k in ("path", "rows", "bytes", "panel") if k in a}
                for a in manifest.get("artifacts", [])
            ],
            "errors": manifest.get("errors", []),
            "manifest_path": manifest.get("manifest_path"),
            "coverage_report_path": manifest.get("coverage_report_path"),
        },
        indent=2,
    ))
    return 1 if manifest.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
