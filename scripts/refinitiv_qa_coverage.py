#!/usr/bin/env python3
"""QA coverage reports for Refinitiv harvest parquets (pre-scale gate)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(REPO / "scripts"))
from refinitiv_schema_normalize import normalize_panel  # noqa: E402

PANEL_SPECS: dict[str, dict[str, Any]] = {
    "refinitiv_security_master.parquet": {
        "panel": "refinitiv_security_master",
        "primary_key": ["ric"],
        "required_cols": ["ric"],
    },
    "index_membership_pit.parquet": {
        "panel": "index_membership_pit",
        "primary_key": ["index_ric", "as_of_date", "constituent_ric"],
        "required_cols": ["index_ric", "as_of_date", "constituent_ric"],
    },
    "corporate_actions_snapshot.parquet": {
        "panel": "corporate_actions_snapshot",
        "primary_key": ["ric"],
        "required_cols": ["ric"],
    },
    "vol_surface_metrics_daily.parquet": {
        "panel": "vol_surface_metrics_daily",
        "primary_key": ["ric", "date", "metric"],
        "required_cols": ["ric", "date", "metric", "value"],
        "default_field": None,
    },
    "estimate_revisions_daily.parquet": {
        "panel": "estimate_revisions_daily",
        "primary_key": ["ric", "date", "metric"],
        "required_cols": ["ric", "date", "metric", "value"],
        "default_field": "eps_mean",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def null_rate(frame: pd.DataFrame) -> dict[str, float]:
    out: dict[str, float] = {}
    for col in frame.columns:
        out[str(col)] = round(float(frame[col].isna().mean()) * 100.0, 2)
    return out


def duplicate_key_count(frame: pd.DataFrame, keys: list[str]) -> int:
    present = [k for k in keys if k in frame.columns]
    if not present or frame.empty:
        return 0
    return int(frame.duplicated(subset=present, keep=False).sum())


def coverage_by_year(frame: pd.DataFrame, date_col: str, value_col: str) -> dict[str, dict[str, Any]]:
    if date_col not in frame.columns or value_col not in frame.columns:
        return {}
    tmp = frame.copy()
    tmp["_year"] = pd.to_datetime(tmp[date_col], errors="coerce").dt.year
    rows: dict[str, dict[str, Any]] = {}
    for year, grp in tmp.groupby("_year", dropna=True):
        rows[str(int(year))] = {
            "rows": int(len(grp)),
            "non_null_value": int(grp[value_col].notna().sum()),
            "non_null_pct": round(float(grp[value_col].notna().mean()) * 100.0, 2),
        }
    return rows


def coverage_by_ric(frame: pd.DataFrame, ric_col: str, value_col: str, *, top: int = 10) -> dict[str, Any]:
    if ric_col not in frame.columns or value_col not in frame.columns:
        return {}
    grp = frame.groupby(ric_col)[value_col].agg(["count", lambda s: int(s.notna().sum())])
    grp.columns = ["rows", "non_null"]
    grp["non_null_pct"] = (grp["non_null"] / grp["rows"].clip(lower=1) * 100).round(2)
    sparse = grp.sort_values("non_null_pct").head(top)
    dense = grp.sort_values("non_null_pct", ascending=False).head(top)
    return {
        "sparse_head": sparse.reset_index().to_dict(orient="records"),
        "dense_head": dense.reset_index().to_dict(orient="records"),
        "rics_with_any_value": int((grp["non_null"] > 0).sum()),
        "rics_total": int(len(grp)),
    }


def qa_panel(path: Path, spec: dict[str, Any], *, normalize: bool) -> dict[str, Any]:
    raw = pd.read_parquet(path)
    panel_name = spec["panel"]
    kwargs = {}
    if spec.get("default_field"):
        kwargs["default_field"] = spec["default_field"]
    frame = normalize_panel(panel_name, raw, **kwargs) if normalize else raw

    pk = spec["primary_key"]
    report: dict[str, Any] = {
        "file": str(path),
        "panel": panel_name,
        "normalized": normalize,
        "row_count": int(len(frame)),
        "columns": list(frame.columns),
        "null_rate_pct": null_rate(frame),
        "duplicate_primary_key_rows": duplicate_key_count(frame, pk),
        "primary_key_unique": duplicate_key_count(frame, pk) == 0,
    }

    if "ric" in frame.columns:
        report["unique_rics"] = int(frame["ric"].nunique())
    if "constituent_ric" in frame.columns:
        report["unique_constituents"] = int(frame["constituent_ric"].nunique())
    if "index_ric" in frame.columns:
        report["unique_indices"] = frame["index_ric"].dropna().unique().tolist() if len(frame) else []
    if "as_of_date" in frame.columns:
        report["as_of_date_range"] = {
            "min": str(frame["as_of_date"].min()),
            "max": str(frame["as_of_date"].max()),
            "unique_dates": int(frame["as_of_date"].nunique()),
        }
    if "date" in frame.columns:
        dts = pd.to_datetime(frame["date"], errors="coerce").dropna()
        if not dts.empty:
            report["date_range"] = {"min": str(dts.min().date()), "max": str(dts.max().date())}

    if "value" in frame.columns and "metric" in frame.columns:
        for metric in frame["metric"].dropna().unique():
            sub = frame[frame["metric"] == metric]
            report[f"metric_{metric}"] = {
                "non_null_count": int(sub["value"].notna().sum()),
                "non_null_pct": round(float(sub["value"].notna().mean()) * 100.0, 2),
                "by_year": coverage_by_year(sub, "date", "value"),
                "by_ric": coverage_by_ric(sub, "ric", "value"),
            }

    if "company_name" in frame.columns:
        report["sample_rows"] = frame.head(3).to_dict(orient="records")
    elif "constituent_ric" in frame.columns:
        sample = frame.dropna(subset=["constituent_ric"]).head(3)
        report["sample_rows"] = sample.to_dict(orient="records")

    # Gate hints
    gates: list[str] = []
    if not report.get("primary_key_unique", True):
        gates.append("FAIL: duplicate primary keys")
    if panel_name == "vol_surface_metrics_daily":
        v30 = report.get("metric_volatility_30d", {})
        if v30.get("non_null_pct", 0) < 5:
            gates.append("WARN: volatility_30d mostly empty on EDP history — desktop/Eikon path may be required")
        si = report.get("metric_short_interest_pct", {})
        if si.get("non_null_pct", 0) > 10:
            gates.append("PASS: short_interest_pct partially populated")
    if panel_name == "index_membership_pit":
        if report.get("unique_constituents", 0) > 100:
            gates.append("PASS: PIT constituent spine populated")
    report["qa_gates"] = gates
    return report


def write_normalized(processed_dir: Path, out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for fname, spec in PANEL_SPECS.items():
        src = processed_dir / fname
        if not src.exists():
            continue
        raw = pd.read_parquet(src)
        kwargs = {}
        if spec.get("default_field"):
            kwargs["default_field"] = spec["default_field"]
        norm = normalize_panel(spec["panel"], raw, **kwargs)
        dest = out_dir / fname
        norm.to_parquet(dest, index=False)
        written.append(str(dest))
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description="Refinitiv parquet QA + optional normalization")
    ap.add_argument("--run-dir", required=True, help="e.g. data_lake/refinitiv_backfill/2026-07-06-value-v2")
    ap.add_argument("--normalize", action="store_true", help="Write normalized/ copies")
    ap.add_argument("--freeze", action="store_true", help="Write VALIDATED.json marker")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = REPO / run_dir
    processed = run_dir / "processed"
    qa_dir = run_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    reports: dict[str, Any] = {"generated_at": utc_now(), "run_dir": str(run_dir), "panels": {}}
    blockers: list[str] = []

    for fname, spec in PANEL_SPECS.items():
        path = processed / fname
        if not path.exists():
            reports["panels"][fname] = {"missing": True}
            continue
        raw_report = qa_panel(path, spec, normalize=False)
        norm_report = qa_panel(path, spec, normalize=True)
        reports["panels"][fname] = {"raw": raw_report, "normalized": norm_report}
        for gate in norm_report.get("qa_gates", []):
            if gate.startswith("FAIL"):
                blockers.append(f"{fname}: {gate}")

    if args.normalize:
        norm_dir = processed / "normalized"
        reports["normalized_files"] = write_normalized(processed, norm_dir)

    out_json = qa_dir / "coverage_report.json"
    out_md = qa_dir / "coverage_report.md"
    out_json.write_text(json.dumps(reports, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = ["# Refinitiv QA coverage report", "", f"Generated: {reports['generated_at']}", ""]
    for fname, payload in reports["panels"].items():
        if payload.get("missing"):
            lines.append(f"## {fname}\n\n- MISSING\n")
            continue
        nr = payload["normalized"]
        lines.append(f"## {fname}")
        lines.append(f"- Rows: {nr.get('row_count')}")
        lines.append(f"- PK unique: {nr.get('primary_key_unique')}")
        if nr.get("date_range"):
            lines.append(f"- Dates: {nr['date_range']}")
        if nr.get("as_of_date_range"):
            lines.append(f"- As-of dates: {nr['as_of_date_range']}")
        for gate in nr.get("qa_gates", []):
            lines.append(f"- {gate}")
        lines.append("")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if args.freeze:
        validated = {
            "validated_at": utc_now(),
            "run_dir": str(run_dir),
            "stamp": run_dir.name,
            "qa_report": str(out_json),
            "blockers": blockers,
            "approved_for_scaling": len(blockers) == 0,
            "notes": [
                "First validated Refinitiv value harvest (Wave 0+1).",
                "Use processed/normalized/ for joins after --normalize.",
            ],
        }
        (run_dir / "VALIDATED.json").write_text(json.dumps(validated, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"qa_json": str(out_json), "blockers": blockers, "approved": len(blockers) == 0}, indent=2))
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
