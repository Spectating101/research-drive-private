#!/usr/bin/env python3
"""Procurement catalog — registry + queue + pipelines + connectors."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.storage_policy import load_storage_policy
from scripts.research_query_engine.procurement import ProcurementWorkbench
from scripts.yzu_cluster.orchestrator import YzuOrchestrator


class CatalogService:
    def __init__(
        self,
        repo_root: Path,
        search: SearchService,
        orchestrator: YzuOrchestrator,
        procurement: ProcurementWorkbench,
    ) -> None:
        self.repo_root = repo_root
        self.search = search
        self.orchestrator = orchestrator
        self.procurement = procurement

    def procurement_catalog(self, q: str = "", limit: int = 50) -> dict[str, Any]:
        from scripts.research_data_mcp.catalog_index import ProcurementCatalogIndex
        from scripts.research_data_mcp.inventory_authority import SCOPE_RETURNED_WINDOW, view_scope

        listed = self.search.list_datasets(q=q, limit=limit)
        registry_rows = listed["datasets"]
        inventory = listed.get("inventory") or self.search.inventory_summary()
        queue_tasks = self.orchestrator.queue_tasks(runnable_only=False)
        if q.strip():
            tokens = set(re.findall(r"[a-z][a-z0-9_]{2,}", q.lower()))
            queue_tasks = [
                t
                for t in queue_tasks
                if any(tok in f"{t.get('id', '')} {t.get('title', '')} {t.get('output_hint', '')}".lower() for tok in tokens)
            ]
        pipelines = [
            {"id": pid, "label": meta.get("label", pid), "pool": meta.get("pool", "optiplex")}
            for pid, meta in self.orchestrator.executor.pipelines().items()
        ]
        cat = ProcurementCatalogIndex(self.repo_root, self.orchestrator)
        spectator_scripts = cat.spectator_scripts()
        probe_connectors = self.procurement.store.list(min(limit, 50))
        from scripts.research_data_mcp.source_map import load_desk_connectors

        desk_connectors = []
        for cid, src in load_desk_connectors(self.repo_root).items():
            collect = src.get("collect_via") or []
            if isinstance(collect, str):
                collect = [collect]
            desk_connectors.append(
                {
                    "id": cid,
                    "status": "desk_source",
                    "kind": "desk_source",
                    "name": src.get("label") or cid,
                    "source_url": src.get("endpoint") or "",
                    "collect_via": collect,
                    "routes": src.get("routes"),
                    "show_on_resources": bool(src.get("show_on_resources", True)),
                }
            )
        storage = load_storage_policy(self.repo_root)
        registered_total = inventory["totals"]["registered"]
        return {
            "summary": {
                # Authority totals — never derive registry_datasets from the truncated window.
                "registry_datasets": registered_total,
                "visible_to_desk": inventory["totals"]["visible_to_desk"],
                "excluded_operational_test": inventory["totals"]["excluded_operational_test"],
                "returned_registry_rows": len(registry_rows),
                "queue_tasks": len(queue_tasks),
                "runnable_queue_tasks": sum(1 for t in queue_tasks if t.get("runnable")),
                "pipelines": len(pipelines),
                "spectator_scripts": len(spectator_scripts),
                "connectors": len(probe_connectors),
                "desk_sources": len(desk_connectors),
                "gdrive_root": storage.get("gdrive_root", ""),
                "local_staging": storage.get("local_staging", "data_lake"),
                "canonical_archive": storage.get("canonical_archive", ""),
                "auto_archive_procured": storage.get("auto_archive_procured", False),
                "storage_policy": storage.get("policy_note", ""),
            },
            "inventory": inventory,
            "view_scope": view_scope(
                scope_id=SCOPE_RETURNED_WINDOW if q.strip() else listed.get("view_scope", {}).get("scope") or "registry_all",
                primary_total=registered_total if not q.strip() else listed.get("total", len(registry_rows)),
                primary_total_field="registered" if not q.strip() else "returned_matching",
                inventory=inventory,
                filters={"q": q, "limit": limit},
                note=(
                    "summary.registry_datasets is inventory.totals.registered (full authority). "
                    "summary.returned_registry_rows is the truncated window for this request."
                ),
            ),
            "registry": registry_rows,
            "queue_tasks": queue_tasks[:limit],
            "pipelines": pipelines,
            "spectator_scripts": spectator_scripts,
            "desk_sources": desk_connectors[:limit],
            "connectors": [
                {
                    "id": row.get("id"),
                    "status": row.get("status"),
                    "kind": "probe_candidate",
                    "name": row.get("name"),
                    "source_url": row.get("source_url"),
                    "product_note": "Saved URL probe — not a curated desk source",
                }
                for row in probe_connectors
            ],
        }
