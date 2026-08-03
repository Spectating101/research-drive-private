"""Generate validation job specs from the alpha idea queue."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from src.research.alpha_idea_queue import load_idea_queue


VALIDATION_STATUSES = {"feature_ready", "backtest_ready", "validated", "paper_candidate"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slug(value: str) -> str:
    value = str(value).strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    return value.strip("-") or "idea"


def _resolve(repo: Path, value: str | Path | None) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    path = Path(str(value))
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == repo.name:
        path = Path(*path.parts[1:]) if len(path.parts) > 1 else Path(".")
    return (repo / path).resolve()


def build_idea_validation_job(
    row: Mapping[str, Any],
    *,
    repo: Path,
    panel_csv: Path,
    out_root: Path,
    horizon_days: int = 21,
    top_n: int = 10,
) -> dict[str, Any]:
    repo = Path(repo).resolve()
    idea_id = str(row.get("idea_id", "") or "")
    slug = _slug(idea_id)
    status = str(row.get("status", "") or "")
    validation_artifact = str(row.get("validation_artifact", "") or "")
    artifact_path = _resolve(repo, validation_artifact)
    runnable = bool(status in VALIDATION_STATUSES and artifact_path and artifact_path.exists() and artifact_path.suffix.lower() == ".csv")
    job_dir = Path(out_root) / slug
    tearsheet_dir = job_dir / "factor_tearsheet"
    command = [
        "python",
        "scripts/investment_cockpit.py",
        "factor-tearsheet",
        "--rankings",
        str(artifact_path) if artifact_path else validation_artifact,
        "--panel",
        str(panel_csv),
        "--out-dir",
        str(tearsheet_dir),
        "--horizon-days",
        str(int(horizon_days)),
        "--top-n",
        str(int(top_n)),
    ]
    blockers: list[str] = []
    if status not in VALIDATION_STATUSES:
        blockers.append(f"status_not_validation_ready={status}")
    if not validation_artifact:
        blockers.append("missing_validation_artifact")
    elif not artifact_path or not artifact_path.exists():
        blockers.append("validation_artifact_missing")
    elif artifact_path.suffix.lower() != ".csv":
        blockers.append("validation_artifact_not_rankings_csv")

    return {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "idea_id": idea_id,
        "status": status,
        "source": str(row.get("source", "") or ""),
        "hypothesis": str(row.get("hypothesis", "") or ""),
        "universe": str(row.get("universe", "") or ""),
        "feature_recipe": str(row.get("feature_recipe", "") or ""),
        "expected_mechanism": str(row.get("expected_mechanism", "") or ""),
        "risk_of_leakage": str(row.get("risk_of_leakage", "") or ""),
        "validation_artifact": validation_artifact,
        "validation_artifact_path": str(artifact_path) if artifact_path else "",
        "runnable": runnable,
        "blockers": blockers,
        "job_dir": str(job_dir),
        "expected_outputs": {
            "summary": str(tearsheet_dir / "summary.json"),
            "ic_by_date": str(tearsheet_dir / "ic_by_date.csv"),
            "bucket_returns": str(tearsheet_dir / "bucket_returns.csv"),
            "turnover": str(tearsheet_dir / "turnover.csv"),
        },
        "command": command,
    }


def generate_idea_validation_jobs(
    *,
    queue_csv: Path,
    repo: Path,
    panel_csv: Path,
    out_root: Path,
    include_statuses: set[str] | None = None,
    horizon_days: int = 21,
    top_n: int = 10,
) -> dict[str, Any]:
    statuses = include_statuses or set(VALIDATION_STATUSES)
    repo = Path(repo).resolve()
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    queue = load_idea_queue(queue_csv)
    jobs: list[dict[str, Any]] = []
    for _, row in queue.iterrows():
        if str(row.get("status", "")) not in statuses:
            continue
        job = build_idea_validation_job(
            row.to_dict(),
            repo=repo,
            panel_csv=panel_csv,
            out_root=out_root,
            horizon_days=horizon_days,
            top_n=top_n,
        )
        job_dir = Path(job["job_dir"])
        job_dir.mkdir(parents=True, exist_ok=True)
        job_path = job_dir / "job.json"
        job_path.write_text(json.dumps(job, indent=2, sort_keys=True) + "\n")
        job["job_path"] = str(job_path)
        jobs.append(job)

    runnable = [j for j in jobs if j.get("runnable")]
    report = {
        "generated_at": _utc_now(),
        "queue_csv": str(queue_csv),
        "panel_csv": str(panel_csv),
        "out_root": str(out_root),
        "n_jobs": len(jobs),
        "n_runnable": len(runnable),
        "n_blocked": len(jobs) - len(runnable),
        "jobs": jobs,
    }
    (out_root / "jobs.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    _write_jobs_markdown(report, out_root / "jobs.md")
    return report


def _write_jobs_markdown(report: Mapping[str, Any], path: Path) -> None:
    lines = [
        "# Alpha Idea Validation Jobs",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Jobs: `{report.get('n_jobs')}`",
        f"- Runnable: `{report.get('n_runnable')}`",
        f"- Blocked: `{report.get('n_blocked')}`",
        "",
        "| Idea | Status | Runnable | Blockers |",
        "| --- | --- | --- | --- |",
    ]
    for job in report.get("jobs", []) if isinstance(report.get("jobs", []), list) else []:
        lines.append(
            f"| {job.get('idea_id')} | {job.get('status')} | {job.get('runnable')} | {', '.join(job.get('blockers', []))} |"
        )
    path.write_text("\n".join(lines) + "\n")
