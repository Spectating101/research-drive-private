#!/usr/bin/env python3
"""Backfill reproducibility receipts for already-promoted Library assets.

The migration is intentionally conservative: it only follows a durable job id
already recorded on the registry row and only copies facts found on that job.
It never derives URLs from provider names or generic source-map metadata.

Dry-run is the default. Pass ``--apply`` on the deployed desk after reviewing
the report to persist the enriched registry document.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from scripts.research_data_mcp.library_provenance import stamp_spec_with_job_provenance
from scripts.research_data_mcp.registry_transaction import atomic_update_json
from scripts.yzu_cluster.jobs import YzuJobStore


def _job_id(row: dict[str, Any]) -> str:
    procurement = row.get("procurement") if isinstance(row.get("procurement"), dict) else {}
    for value in (
        procurement.get("promoted_from_job"),
        procurement.get("job_id"),
        row.get("promoted_from_job"),
        row.get("source_job_id"),
        row.get("job_id"),
    ):
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return ""


def _receipt_signature(row: dict[str, Any]) -> tuple[str, ...]:
    procurement = row.get("procurement") if isinstance(row.get("procurement"), dict) else {}
    return tuple(
        str(value or "").strip()
        for value in (
            row.get("source_url"),
            row.get("collection_method"),
            row.get("collection_script"),
            row.get("collection_command"),
            row.get("source_route"),
            row.get("fetched_at"),
            row.get("content_sha256"),
            procurement.get("source_url"),
            procurement.get("collect_via"),
            procurement.get("script"),
            procurement.get("command"),
            procurement.get("route"),
        )
    )


def backfill_registry_document(
    registry: dict[str, Any],
    job_lookup: Callable[[str], dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return an enriched copy plus an auditable migration report."""
    out = deepcopy(registry)
    rows = list(out.get("datasets") or [])
    changed_ids: list[str] = []
    missing_job_id: list[str] = []
    job_not_found: list[str] = []

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        dataset_id = str(row.get("dataset_id") or f"row-{index}")
        job_id = _job_id(row)
        if not job_id:
            missing_job_id.append(dataset_id)
            continue
        try:
            job = job_lookup(job_id)
        except (KeyError, LookupError):
            job_not_found.append(dataset_id)
            continue
        before = _receipt_signature(row)
        stamped = stamp_spec_with_job_provenance(row, job)
        after = _receipt_signature(stamped)
        if after != before:
            rows[index] = stamped
            changed_ids.append(dataset_id)

    out["datasets"] = rows
    report = {
        "datasets": len(rows),
        "changed": len(changed_ids),
        "changed_dataset_ids": changed_ids,
        "missing_recorded_job_id": len(missing_job_id),
        "missing_recorded_job_id_dataset_ids": missing_job_id,
        "recorded_job_not_found": len(job_not_found),
        "recorded_job_not_found_dataset_ids": job_not_found,
        "semantics": "Only facts recorded on a linked execution job are copied; existing registry authority wins.",
    }
    return out, report


def _paths(repo_root: Path) -> tuple[Path, Path]:
    config_path = repo_root / "config/yzu_cluster.json"
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    registry_path = repo_root / "config/research_query_registry.json"
    jobs_root = repo_root / str((cfg.get("controller") or {}).get("jobs_root") or "data_lake/yzu_cluster/jobs")
    return registry_path, jobs_root / "jobs.sqlite3"


def run(repo_root: Path, *, apply: bool = False) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    registry_path, jobs_path = _paths(repo_root)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    store = YzuJobStore(jobs_path)
    enriched, report = backfill_registry_document(registry, store.get)
    report["registry_path"] = str(registry_path)
    report["jobs_path"] = str(jobs_path)
    report["applied"] = False

    if apply and report["changed"]:
        def mutate(current: dict[str, Any]) -> None:
            current.clear()
            current.update(deepcopy(enriched))

        atomic_update_json(registry_path, mutate)
        report["applied"] = True
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--apply", action="store_true", help="Persist the backfill; default is report-only dry-run")
    args = parser.parse_args()
    report = run(Path(args.repo_root), apply=args.apply)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
