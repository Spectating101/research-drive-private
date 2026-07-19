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
        registry_rows = self.search.list_datasets(q=q, limit=limit)["datasets"]
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
        from scripts.research_data_mcp.catalog_index import ProcurementCatalogIndex

        cat = ProcurementCatalogIndex(self.repo_root, self.orchestrator)
        spectator_scripts = cat.spectator_scripts()
        connectors = self.procurement.store.list(min(limit, 50))
        storage = load_storage_policy(self.repo_root)
        return {
            "summary": {
                "registry_datasets": len(registry_rows),
                "queue_tasks": len(queue_tasks),
                "runnable_queue_tasks": sum(1 for t in queue_tasks if t.get("runnable")),
                "pipelines": len(pipelines),
                "spectator_scripts": len(spectator_scripts),
                "connectors": len(connectors),
                "gdrive_root": storage.get("gdrive_root", ""),
                "local_staging": storage.get("local_staging", "data_lake"),
                "canonical_archive": storage.get("canonical_archive", ""),
                "auto_archive_procured": storage.get("auto_archive_procured", False),
                "storage_policy": storage.get("policy_note", ""),
            },
            "registry": registry_rows,
            "queue_tasks": queue_tasks[:limit],
            "pipelines": pipelines,
            "spectator_scripts": spectator_scripts,
            "connectors": [
                {
                    "id": row.get("id"),
                    "status": row.get("status"),
                    "name": row.get("name"),
                    "source_url": row.get("source_url"),
                }
                for row in connectors
            ],
        }
