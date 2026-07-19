"""Consolidated research desk state — single Bloomberg-style capability snapshot."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _live_instant_probe(repo_root: Path) -> dict[str, Any]:
    from scripts.sync_materialized_registry import PROBE_BACKENDS, _probe_dataset
    from scripts.research_query_engine.engine import ResearchQueryEngine

    reg_path = repo_root / "config/research_query_registry.json"
    doc = json.loads(reg_path.read_text(encoding="utf-8"))
    engine = ResearchQueryEngine(reg_path, repo_root=repo_root)
    ready = 0
    miss: list[str] = []
    for ds in doc.get("datasets") or []:
        if ds.get("analysis_readiness") != "instant":
            continue
        if str(ds.get("backend") or "") not in PROBE_BACKENDS:
            ready += 1
            continue
        probe = _probe_dataset(engine, ds)
        if probe.get("query_ready"):
            ready += 1
        else:
            miss.append(str(ds.get("dataset_id")))
    total = sum(1 for d in doc.get("datasets") or [] if d.get("analysis_readiness") == "instant")
    return {
        "instant_total": total,
        "instant_query_ready": ready,
        "instant_miss": miss[:30],
        "instant_ready_pct": round(100.0 * ready / max(total, 1), 1),
    }


def build_consolidated_state(gateway, *, live: bool = False) -> dict[str, Any]:
    """Merge platform, databank, storage, and sourcing into one desk snapshot."""
    repo_root = Path(gateway.repo_root)

    platform = gateway.platform_state()
    source_map = gateway.source_map_audit(live=live)
    access = gateway.access_scope_audit(live=live)
    coverage = gateway.dataset_coverage_audit(live=live)

    from scripts.research_data_mcp.storage_tiers import storage_tiers_status

    tiers = storage_tiers_status(repo_root)
    instant = _live_instant_probe(repo_root) if live else {}

    if not instant:
        instant = {
            "instant_total": platform.get("inventory", {}).get("instant_datasets"),
            "instant_query_ready": platform.get("instant_path_ok"),
            "instant_ready_pct": round(
                100.0
                * float(platform.get("instant_path_ok") or 0)
                / max(float(platform.get("instant_query_total") or platform.get("inventory", {}).get("instant_datasets") or 1), 1),
                1,
            ),
        }

    queue = _read_json(repo_root / "config/data_collection_queue.json") or {}
    tasks = queue.get("tasks") or []
    enabled_tasks = [t for t in tasks if t.get("enabled")]

    sourcing_modes = [
        {"mode": "local_search", "status": "production", "surface": "research_discover_search, registry, semantic index"},
        {"mode": "external_discovery", "status": "production", "surface": "DataCite, HuggingFace, Tavily/DDG"},
        {"mode": "doi_collect", "status": "production", "surface": "datacite_collect, http_manifest"},
        {"mode": "hf_collect", "status": "production", "surface": "huggingface_collect_dataset → registry + GDrive"},
        {"mode": "hydrate_on_query", "status": "production", "surface": "registry_hydrate auto-pull from canonical_remote"},
        {"mode": "queue_etl", "status": "production", "surface": f"{len(enabled_tasks)} enabled collection tasks"},
        {"mode": "licensed_bulk", "status": "partial", "surface": "LSEG instant; CRSP/Compustat ingesting"},
        {"mode": "web_scrape", "status": "production", "surface": "Playwright spectator, generic_url_scrape"},
        {"mode": "gdelt_bulk", "status": "production", "surface": "news_shock_taxonomy + country panels"},
        {"mode": "gdrive_vault", "status": "production", "surface": tiers.get("canonical", {}).get("drive_root", "")},
        {"mode": "live_connectors", "status": "production", "surface": f"{platform.get('inventory', {}).get('live_source_connectors', 18)} desk connectors"},
    ]

    return {
        "generated_at": _stamp(),
        "live": live,
        "principle": "Single desk snapshot: catalogue + entitlements + coverage + sourcing + storage.",
        "headline": {
            "registry_datasets": platform.get("inventory", {}).get("registry_datasets"),
            "instant_datasets": instant.get("instant_total"),
            "instant_query_ready": instant.get("instant_query_ready"),
            "instant_ready_pct": instant.get("instant_ready_pct"),
            "metadata_search": platform.get("inventory", {}).get("metadata_search"),
            "source_systems": source_map.get("summary", {}).get("source_systems"),
            "collection_partitions": platform.get("inventory", {}).get("professor_partitions"),
            "enabled_collection_tasks": len(enabled_tasks),
            "gap_cells": (access.get("summary") or {}).get("gap_cells"),
            "bulk_rich_partitions": (coverage.get("summary") or {}).get("bulk_rich_thin_surface"),
        },
        "sourcing_capability": sourcing_modes,
        "storage": tiers,
        "entitlement_summary": access.get("summary"),
        "priority_access_gaps": (access.get("priority_gaps") or [])[:12],
        "coverage_summary": coverage.get("summary"),
        "source_map_summary": source_map.get("summary"),
        "instant_probe": instant,
        "documentation": {
            "desk_status": "docs/DESK_STATUS.md",
            "databank_state": "docs/DATABANK_STATE.md",
            "procurement_pipeline": "docs/PROCUREMENT_PIPELINE.md",
        },
    }


def composer_procurement_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    """Trim consolidated state for Composer — entitlement gaps before collect recommendations."""
    headline = dict(state.get("headline") or {})
    access = state.get("entitlement_summary") or {}
    instant = state.get("instant_probe") or {}
    gaps = state.get("priority_access_gaps") or access.get("priority_gaps") or []

    return {
        "generated_at": state.get("generated_at"),
        "live": state.get("live"),
        "headline": headline,
        "instant_query_ready": instant.get("instant_query_ready") or headline.get("instant_query_ready"),
        "instant_total": instant.get("instant_total") or headline.get("instant_datasets"),
        "instant_ready_pct": headline.get("instant_ready_pct"),
        "instant_miss_sample": (instant.get("instant_miss") or [])[:8],
        "gap_cells": access.get("gap_cells") or headline.get("gap_cells"),
        "priority_access_gaps": [
            {
                "source_id": g.get("source_id") or g.get("source"),
                "gap": g.get("gap") or g.get("label") or g.get("capability"),
                "note": g.get("note") or g.get("recommendation") or g.get("accessible"),
            }
            for g in gaps[:10]
            if isinstance(g, dict)
        ],
        "licensed_bulk_status": next(
            (m for m in (state.get("sourcing_capability") or []) if m.get("mode") == "licensed_bulk"),
            None,
        ),
        "enabled_collection_tasks": headline.get("enabled_collection_tasks"),
        "bulk_rich_partitions": (headline.get("bulk_rich_partitions") or [])[:6],
        "procurement_note": (
            "If priority_access_gaps lists CRSP/Compustat/WRDS, route via queue jobs — do not claim query-ready. "
            "Use research_discover_search for catalog hits; yzu_submit_job for licensed bulk sync."
        ),
        "documentation": state.get("documentation"),
    }
