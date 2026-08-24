#!/usr/bin/env python3
"""Sync YZU Cluster platform progress into drive/ (canonical desk tree).

- Mirrors databank audit scripts + docs into drive/
- Regenerates coverage JSON/MD under drive/docs/status/generated/
- Writes neutral platform_progress.json (inventory truth, not ranked advice)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DRIVE = Path(__file__).resolve().parents[1]
REPO = DRIVE.parent
if str(REPO / "kernel") not in sys.path:
    sys.path.insert(0, str(REPO / "kernel"))

from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)


def _stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


PLATFORM_SCRIPTS = [
    "build_jkse_pit_idn_microstructure_revisions.py",
    "build_pit_revision_momentum_panel.py",
    "databank_coverage_report.py",
    "databank_research_coverage.py",
    "databank_source_map.py",
    "databank_access_scope.py",
    "databank_dataset_coverage.py",
    "promote_derived_research_panels.py",
    "refinitiv_build_derived_panels.py",
    "refinitiv_promote_registry.py",
    "refinitiv_query_demo.py",
    "wire_partition_registry.py",
    "sync_materialized_registry.py",
    "sync_drive_platform_state.py",
]

PLATFORM_DOCS = [
    "DATABANK_STATE.md",
    "DESK_ACTIVATION.md",
]


def _mirror_script(name: str) -> None:
    src = ROOT / "scripts" / name
    dst = DRIVE / "scripts" / name
    if not src.is_file() and dst.is_file():
        return
    if not src.is_file():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    link = ROOT / "scripts" / name
    if link.exists() or link.is_symlink():
        if link.is_symlink() or link.samefile(dst):
            return
    if not link.exists():
        os.symlink(os.path.relpath(dst, link.parent), link)


def _mirror_docs() -> None:
    pairs = [
        (ROOT / "docs" / "DATABANK_STATE.md", DRIVE / "docs" / "DATABANK_STATE.md"),
        (DRIVE / "docs" / "DESK_ACTIVATION.md", ROOT / "docs" / "DESK_ACTIVATION.md"),
    ]
    for src, dst in pairs:
        if not src.is_file():
            continue
        if src.resolve() == dst.resolve():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _audit_env() -> dict[str, str]:
    env = os.environ.copy()
    py_path = os.pathsep.join(
        [
            str(ROOT / "kernel"),
            str(ROOT / "drive"),
            str(ROOT / "alpha"),
            str(ROOT),
        ]
    )
    env["PYTHONPATH"] = py_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def _run_audit(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    py = ROOT / ".venv/bin/python"
    if not py.is_file():
        py = Path(sys.executable)
    audit_env = _audit_env()
    subprocess.run(
        [str(py), str(ROOT / "scripts" / "databank_coverage_report.py"), "--json"],
        cwd=ROOT,
        env=audit_env,
        check=False,
    )
    cov_src = ROOT / "docs/status/generated/databank_coverage_report.json"
    if cov_src.is_file():
        shutil.copy2(cov_src, out_dir / "databank_coverage_report.json")
    subprocess.run(
        [str(py), str(ROOT / "scripts" / "databank_research_coverage.py")],
        cwd=ROOT,
        env=audit_env,
        check=False,
    )
    subprocess.run(
        [str(py), str(ROOT / "scripts" / "databank_source_map.py"), "--json"],
        cwd=ROOT,
        env=audit_env,
        check=False,
    )
    subprocess.run(
        [str(py), str(ROOT / "scripts" / "databank_access_scope.py"), "--json"],
        cwd=ROOT,
        env=audit_env,
        check=False,
    )
    subprocess.run(
        [str(py), str(ROOT / "scripts" / "databank_dataset_coverage.py"), "--json"],
        cwd=ROOT,
        env=audit_env,
        check=False,
    )
    for name in ("databank_research_coverage.json", "databank_research_coverage.md"):
        src = ROOT / "docs/status/generated" / name
        if src.is_file():
            shutil.copy2(src, out_dir / name)
    for name in ("databank_source_map.json", "databank_source_map.md"):
        src = ROOT / "docs/status/generated" / name
        if src.is_file():
            shutil.copy2(src, out_dir / name)
    for name in ("databank_access_scope.json", "databank_access_scope.md"):
        src = ROOT / "docs/status/generated" / name
        if src.is_file():
            shutil.copy2(src, out_dir / name)
    for name in ("databank_dataset_coverage.json", "databank_dataset_coverage.md"):
        src = ROOT / "docs/status/generated" / name
        if src.is_file():
            shutil.copy2(src, out_dir / name)


def _panel_manifest() -> list[dict[str, Any]]:
    panels_dir = ROOT / "data_lake/research_panels"
    if not panels_dir.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(panels_dir.rglob("manifest.json")):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        rows.append(
            {
                "manifest": str(path.relative_to(ROOT)),
                "summary": manifest.get("summary") or manifest.get("panels"),
                "generated_at": manifest.get("generated_at"),
            }
        )
    return rows


def _build_progress(
    coverage: dict[str, Any],
    research: dict[str, Any] | None,
    source_map: dict[str, Any] | None,
    access_scope: dict[str, Any] | None,
    dataset_coverage: dict[str, Any] | None,
) -> dict[str, Any]:
    instant_rows = coverage.get("instant_queryable") or []
    path_miss = [r for r in instant_rows if r.get("query_path_ok") is False]
    metadata_n = (coverage.get("readiness") or {}).get("metadata_search", 0)
    instant_n = (coverage.get("summary") or {}).get("instant_datasets", 0)

    incomplete: list[dict[str, Any]] = []
    for row in path_miss:
        incomplete.append(
            {
                "dataset_id": row.get("dataset_id"),
                "kind": "instant_path",
                "status": "broken",
                "note": row.get("path_note"),
            }
        )
    unmapped = (coverage.get("summary") or {}).get("unassigned_registry_ids", 0)
    if unmapped:
        incomplete.append(
            {
                "dataset_id": None,
                "kind": "partition_map",
                "status": "partial",
                "count": unmapped,
                "note": "Registry IDs without collection_partitions mapping",
            }
        )
    if metadata_n:
        incomplete.append(
            {
                "dataset_id": None,
                "kind": "materialization",
                "status": "metadata_only",
                "count": metadata_n,
                "note": "Searchable/procurable cards not yet instant-query panels",
            }
        )

    bridge = None
    if research:
        bridge = (research.get("headline") or {}).get("entity_bridge_pct")

    return {
        "generated_at": _stamp(),
        "principle": "Neutral inventory of what exists. Ranked next steps live in DESK_ACTIVATION.md and should be filtered through research_faculty_profile.",
        "documentation": {
            "databank_state": "drive/docs/DATABANK_STATE.md",
            "desk_activation": "drive/docs/DESK_ACTIVATION.md",
            "coverage_json": "drive/docs/status/generated/databank_coverage_report.json",
            "research_coverage_md": "drive/docs/status/generated/databank_research_coverage.md",
            "source_map_json": "drive/docs/status/generated/databank_source_map.json",
            "source_map_md": "drive/docs/status/generated/databank_source_map.md",
            "access_scope_json": "drive/docs/status/generated/databank_access_scope.json",
            "access_scope_md": "drive/docs/status/generated/databank_access_scope.md",
            "dataset_coverage_json": "drive/docs/status/generated/databank_dataset_coverage.json",
            "dataset_coverage_md": "drive/docs/status/generated/databank_dataset_coverage.md",
        },
        "inventory": coverage.get("summary") or {},
        "source_map_summary": (source_map or {}).get("summary") or {},
        "sources": (source_map or {}).get("sources") or [],
        "access_scope_summary": (access_scope or {}).get("summary") or {},
        "entitlement_matrix": (access_scope or {}).get("entitlement_matrix") or {},
        "priority_access_gaps": (access_scope or {}).get("priority_gaps") or [],
        "dataset_coverage_summary": (dataset_coverage or {}).get("summary") or {},
        "bulk_rich_collections": (dataset_coverage or {}).get("summary", {}).get("bulk_rich_thin_surface") or [],
        "proxy_coverage": (dataset_coverage or {}).get("proxy_coverage") or [],
        "readiness": coverage.get("readiness") or {},
        "disk_lanes": coverage.get("disk_lanes") or [],
        "registry_families": (research or {}).get("headline", {}).get("registry_family_counts") or {},
        "instant_families": (research or {}).get("headline", {}).get("instant_family_counts") or {},
        "entity_bridge_pct": bridge,
        "instant_query_total": instant_n,
        "instant_path_ok": sum(1 for r in instant_rows if r.get("query_path_ok") is True),
        "instant_path_miss": path_miss,
        "incomplete_items": incomplete,
        "synthesis_built": (research or {}).get("synthesis_built") or [],
        "synthesis_recipes": (research or {}).get("synthesis_recipes") or [],
        "panel_manifests": _panel_manifest(),
        "progress_log": [
            {
                "date": "2026-07-06",
                "items": [
                    "DATABANK_STATE.md — neutral equal-weight databank inventory",
                    "pit_index_revision_momentum.parquet — 6-index PIT × revisions panel",
                    "jkse_pit_idn_microstructure_revisions.parquet — regional IDN cross-lane panel",
                    "Registry 150 datasets / 41 instant-query",
                    "databank_coverage_report.py + databank_research_coverage.py audits",
                ],
            }
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync platform state into drive/")
    ap.add_argument("--skip-audit", action="store_true")
    args = ap.parse_args()

    for name in PLATFORM_SCRIPTS:
        _mirror_script(name)

    _mirror_docs()

    status_dir = DRIVE / "docs/status/generated"
    if not args.skip_audit:
        py = ROOT / ".venv/bin/python"
        if not py.is_file():
            py = Path(sys.executable)
        subprocess.run(
            [str(py), str(ROOT / "scripts" / "sync_materialized_registry.py"), "--json"],
            cwd=ROOT,
            env=_audit_env(),
            check=False,
        )
        _run_audit(status_dir)

    cov_path = status_dir / "databank_coverage_report.json"
    research_path = status_dir / "databank_research_coverage.json"
    source_path = status_dir / "databank_source_map.json"
    access_path = status_dir / "databank_access_scope.json"
    dataset_cov_path = status_dir / "databank_dataset_coverage.json"
    coverage: dict[str, Any] = {}
    research: dict[str, Any] | None = None
    source_map: dict[str, Any] | None = None
    access_scope: dict[str, Any] | None = None
    dataset_coverage: dict[str, Any] | None = None
    if cov_path.is_file():
        coverage = json.loads(cov_path.read_text(encoding="utf-8"))
    if research_path.is_file():
        research = json.loads(research_path.read_text(encoding="utf-8"))
    if source_path.is_file():
        source_map = json.loads(source_path.read_text(encoding="utf-8"))
    if access_path.is_file():
        access_scope = json.loads(access_path.read_text(encoding="utf-8"))
    if dataset_cov_path.is_file():
        dataset_coverage = json.loads(dataset_cov_path.read_text(encoding="utf-8"))

    progress = _build_progress(coverage, research, source_map, access_scope, dataset_coverage)
    out = status_dir / "platform_progress.json"
    out.write_text(json.dumps(progress, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Root copy for operators who start from repo root
    root_status = ROOT / "docs/status/generated"
    root_status.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out, root_status / "platform_progress.json")

    try:
        sys.path.insert(0, str(ROOT / "drive"))
        from scripts.research_data_mcp.bootstrap import create_stack

        gateway = create_stack(repo_root=ROOT).gateway
        consolidated = gateway.consolidated_state(live=False)
        cons_path = status_dir / "consolidated_state.json"
        cons_path.write_text(json.dumps(consolidated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        shutil.copy2(cons_path, root_status / "consolidated_state.json")
    except Exception as exc:
        print(json.dumps({"consolidated_state_error": str(exc)}, indent=2), file=sys.stderr)

    print(json.dumps({"ok": True, "platform_progress": str(out.relative_to(ROOT))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
