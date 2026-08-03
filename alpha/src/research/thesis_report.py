"""Thesis register reporting."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_thesis_report(path: Path, *, stale_days: int = 45) -> dict[str, Any]:
    if not Path(path).exists():
        return {
            "generated_at": _utc_now(),
            "path": str(path),
            "exists": False,
            "n_theses": 0,
            "status_counts": {},
            "stale_thesis_ids": [],
            "missing_invalidation_trigger": [],
            "missing_contradiction_checks": [],
        }
    df = pd.read_csv(path, dtype=str).fillna("")
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    updated = pd.to_datetime(df.get("updated_at", ""), errors="coerce").dt.tz_localize(None)
    stale = df.loc[(updated.notna()) & ((now - updated).dt.days > stale_days), "thesis_id"].astype(str).tolist()
    invalidation = df["invalidation_trigger"] if "invalidation_trigger" in df.columns else pd.Series("", index=df.index)
    contradiction = df["contradiction_checks"] if "contradiction_checks" in df.columns else pd.Series("", index=df.index)
    missing_invalid = df.loc[invalidation.astype(str).str.strip() == "", "thesis_id"].astype(str).tolist()
    missing_contra = df.loc[contradiction.astype(str).str.strip() == "", "thesis_id"].astype(str).tolist()
    status_counts = df["status"].value_counts().to_dict() if "status" in df.columns else {}
    return {
        "generated_at": _utc_now(),
        "path": str(path),
        "exists": True,
        "n_theses": int(len(df)),
        "status_counts": {str(k): int(v) for k, v in status_counts.items()},
        "stale_thesis_ids": stale,
        "missing_invalidation_trigger": missing_invalid,
        "missing_contradiction_checks": missing_contra,
    }


def render_thesis_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Thesis Register Report",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Path: `{report.get('path')}`",
        f"- Theses: `{report.get('n_theses', 0)}`",
        f"- Status counts: `{json.dumps(report.get('status_counts', {}), sort_keys=True)}`",
        "",
        "## Required Fixes",
        "",
    ]
    for key, label in [
        ("stale_thesis_ids", "Stale theses"),
        ("missing_invalidation_trigger", "Missing invalidation trigger"),
        ("missing_contradiction_checks", "Missing contradiction checks"),
    ]:
        vals = report.get(key, [])
        if vals:
            lines.append(f"- **{label}:** {', '.join(map(str, vals[:20]))}")
        else:
            lines.append(f"- **{label}:** none")
    return "\n".join(lines) + "\n"


def write_thesis_report(report: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jp = out_dir / "latest.json"
    mp = out_dir / "latest.md"
    jp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    mp.write_text(render_thesis_markdown(report))
    return {"json": str(jp), "markdown": str(mp)}
