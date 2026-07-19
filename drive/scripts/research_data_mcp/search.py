#!/usr/bin/env python3
"""Registry search and query operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.research_query_engine.engine import ResearchQueryEngine


class SearchService:
    def __init__(self, engine: ResearchQueryEngine, registry_path: Path, repo_root: Path) -> None:
        self.engine = engine
        self.registry_path = registry_path
        self.repo_root = repo_root
        self._registry_mtime: float | None = None
        self._maybe_reload_registry()

    def _registry_mtime_on_disk(self) -> float | None:
        try:
            return self.registry_path.stat().st_mtime
        except OSError:
            return None

    def _maybe_reload_registry(self) -> None:
        mtime = self._registry_mtime_on_disk()
        if mtime is None:
            return
        if self._registry_mtime is None or mtime != self._registry_mtime:
            self.reload_registry()
            self._registry_mtime = mtime

    def ensure_registry_fresh(self) -> None:
        self._maybe_reload_registry()

    def reload_registry(self) -> None:
        self.engine.registry = __import__("json").loads(self.registry_path.read_text(encoding="utf-8"))
        self.engine.datasets = {d["dataset_id"]: d for d in self.engine.registry.get("datasets", [])}
        self._registry_mtime = self._registry_mtime_on_disk()

    def _reload_if_unknown(self, dataset_id: str) -> None:
        if dataset_id not in self.engine.datasets:
            self.reload_registry()

    def list_datasets(self, q: str = "", readiness: str = "", access_shape: str = "", limit: int = 50) -> dict[str, Any]:
        self._maybe_reload_registry()
        if q.strip() or readiness or access_shape:
            rows = self.engine.search_datasets(q=q, readiness=readiness, access_mode=access_shape, limit=limit)
        else:
            rows = self.engine.list_datasets()[:limit]
        return {"returned": len(rows), "datasets": rows}

    def describe_dataset(self, dataset_id: str) -> dict[str, Any]:
        self._reload_if_unknown(dataset_id)
        return self.engine.describe(dataset_id)

    def query_dataset(self, dataset_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        self._reload_if_unknown(dataset_id)
        ds = self.engine.datasets.get(dataset_id)
        if ds:
            from scripts.research_data_mcp.registry_hydrate import ensure_registry_local_bytes

            hydrate = ensure_registry_local_bytes(self.repo_root, ds)
            if hydrate.get("ok"):
                self.reload_registry()
        try:
            return self.engine.query(dataset_id, **params).to_dict()
        except KeyError as exc:
            self.reload_registry()
            try:
                return self.engine.query(dataset_id, **params).to_dict()
            except KeyError:
                known = sorted(self.engine.datasets.keys())
                raise KeyError(
                    f"unknown dataset_id: {dataset_id}. Known: {', '.join(known[:12])}{'...' if len(known) > 12 else ''}"
                ) from exc

    def plan_sources(self, q: str, limit: int = 25) -> dict[str, Any]:
        if not q.strip():
            raise ValueError("q is required — describe the research question or construct")
        return self.engine.query("research_source_plan", q=q.strip(), limit=limit).to_dict()

    def search_catalog(
        self,
        q: str = "",
        source: str = "",
        domain: str = "",
        promotion_tier: str = "",
        limit: int = 25,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if q.strip():
            params["q"] = q.strip()
        if source.strip():
            params["source"] = source.strip()
        if domain.strip():
            params["domain"] = domain.strip()
        if promotion_tier.strip():
            params["promotion_tier"] = promotion_tier.strip()
        dataset_id = "external_dataset_catalog_curated"
        if dataset_id not in self.engine.datasets:
            dataset_id = "external_dataset_catalog"
        return self.query_dataset(dataset_id, params)

    def library_overview(self) -> dict[str, Any]:
        buckets: dict[str, list[dict[str, str]]] = {
            "instant_local": [],
            "metadata_search": [],
            "remote_query": [],
            "procurement_ops": [],
            "other": [],
        }
        for ds in self.engine.list_datasets():
            item = {
                "dataset_id": ds["dataset_id"],
                "name": ds.get("name", ds["dataset_id"]),
                "grain": ds.get("grain", ""),
                "analysis_readiness": ds.get("analysis_readiness", ""),
            }
            readiness = str(ds.get("analysis_readiness", ""))
            backend = str(ds.get("backend", ""))
            if readiness == "instant":
                buckets["instant_local"].append(item)
            elif readiness in {"metadata_search", "procurement_planning"}:
                buckets["metadata_search"].append(item)
            elif backend.endswith("_api") or "bigquery" in backend or readiness.startswith("dry_run"):
                buckets["remote_query"].append(item)
            elif backend.endswith("_status") or ds.get("access_shape") == "ops_status":
                buckets["procurement_ops"].append(item)
            else:
                buckets["other"].append(item)
        return {
            "registry": str(self.registry_path.relative_to(self.repo_root)),
            "total_datasets": len(self.engine.list_datasets()),
            "buckets": buckets,
            "partitions": self._partition_summary(),
            "recommended_flow": [
                "GET /library/catalog or /library/overview",
                "POST /library/advise before downloading",
                "GET /query/{dataset_id} on instant hits",
                "POST /library/jobs then POST /library/jobs/{id}/approve",
            ],
        }

    def _partition_summary(self) -> dict[str, Any]:
        from scripts.yzu_cluster.partition_lanes import partition_lanes

        lanes = partition_lanes(self.repo_root)
        return {
            "total": len(lanes),
            "complete": sum(1 for lane in lanes if lane.get("stage") == "complete"),
            "lanes": lanes,
        }

    def ops_status(self, lane: str = "") -> dict[str, Any]:
        queue = self.query_dataset("collection_queue_status")
        harvest = self.query_dataset("datacite_local_harvest_status", {"lane": lane} if lane else {})
        return {
            "collection_queue": queue["rows"][0] if queue.get("rows") else queue,
            "datacite_harvest": harvest["rows"][0] if harvest.get("rows") else harvest,
        }
