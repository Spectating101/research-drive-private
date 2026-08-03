"""Thesis gate checks for candidate manifests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    obj = json.loads(Path(path).read_text())
    return obj if isinstance(obj, dict) else {}


def _requires_thesis(manifest: dict[str, Any]) -> bool:
    params = manifest.get("params", {}) if isinstance(manifest, dict) else {}
    status = str(manifest.get("status", ""))
    if str(params.get("requires_thesis", "")).lower() in {"1", "true", "yes"}:
        return True
    if status in {"paper_candidate", "deployable_sleeve"} and params.get("thesis_id"):
        return True
    return False


def check_manifest_thesis(manifest_path: Path, thesis_register: Path) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    params = manifest.get("params", {})
    thesis_id = str(params.get("thesis_id", "") or "")
    requires = _requires_thesis(manifest)
    reasons: list[str] = []
    thesis_row: dict[str, Any] | None = None

    if requires and not thesis_id:
        reasons.append("missing_thesis_id")
    if thesis_id:
        if not Path(thesis_register).exists():
            reasons.append("thesis_register_missing")
        else:
            df = pd.read_csv(thesis_register, dtype=str).fillna("")
            hit = df[df["thesis_id"].astype(str) == thesis_id] if "thesis_id" in df.columns else pd.DataFrame()
            if hit.empty:
                reasons.append("thesis_id_not_found")
            else:
                thesis_row = hit.iloc[-1].to_dict()
                if not str(thesis_row.get("invalidation_trigger", "")).strip():
                    reasons.append("missing_invalidation_trigger")
                if not str(thesis_row.get("contradiction_checks", "")).strip():
                    reasons.append("missing_contradiction_checks")

    return {
        "manifest_path": str(manifest_path),
        "run_id": manifest.get("run_id"),
        "strategy": manifest.get("strategy"),
        "status": manifest.get("status"),
        "requires_thesis": requires,
        "thesis_id": thesis_id,
        "passed": not reasons,
        "reasons": reasons,
        "thesis": thesis_row,
    }


def thesis_gate_report(registry_csv: Path, thesis_register: Path) -> dict[str, Any]:
    rows = []
    if Path(registry_csv).exists():
        reg = pd.read_csv(registry_csv)
        for _, row in reg.iterrows():
            path = Path(str(row.get("manifest_path", "")))
            if path.exists():
                rows.append(check_manifest_thesis(path, thesis_register))
    failing = [r for r in rows if not r["passed"]]
    return {
        "generated_at": _utc_now(),
        "registry_csv": str(registry_csv),
        "thesis_register": str(thesis_register),
        "n_manifests": len(rows),
        "n_failing": len(failing),
        "passed": not failing,
        "results": rows,
    }


def render_thesis_gate_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Thesis Gate Report",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Manifests: `{report.get('n_manifests')}`",
        f"- Failing: `{report.get('n_failing')}`",
        f"- Passed: `{report.get('passed')}`",
        "",
        "## Results",
        "",
        "| Run | Status | Requires Thesis | Thesis ID | Passed | Reasons |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.get("results", []):
        lines.append(
            f"| {row.get('run_id')} | {row.get('status')} | {row.get('requires_thesis')} | "
            f"{row.get('thesis_id')} | {row.get('passed')} | {', '.join(row.get('reasons', []))} |"
        )
    return "\n".join(lines) + "\n"


def write_thesis_gate_report(report: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jp = out_dir / "latest.json"
    mp = out_dir / "latest.md"
    jp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    mp.write_text(render_thesis_gate_markdown(report))
    return {"json": str(jp), "markdown": str(mp)}
