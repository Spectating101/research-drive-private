#!/usr/bin/env python3
"""Registry search and query operations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from scripts.research_query_engine.engine import ResearchQueryEngine
from scripts.yzu_cluster.acquisitions import repo_relpath


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
        self.engine._reconcile_local_panel_readiness()
        self._registry_mtime = self._registry_mtime_on_disk()

    def _reload_if_unknown(self, dataset_id: str) -> None:
        if dataset_id not in self.engine.datasets:
            self.reload_registry()

    def _receipt_rows(self) -> list[dict[str, Any]]:
        from scripts.research_data_mcp.registered_asset_authority import list_verified_registration_receipts

        return list_verified_registration_receipts(self.repo_root)

    @staticmethod
    def _receipt_matches(row: dict[str, Any], *, q: str, readiness: str, access_shape: str) -> bool:
        if readiness and readiness not in str(row.get("analysis_readiness") or ""):
            return False
        if access_shape and access_shape != str(row.get("access_shape") or row.get("access_mode") or ""):
            return False
        query = str(q or "").strip().lower()
        if not query:
            return True
        text = " ".join(
            str(row.get(key) or "")
            for key in (
                "dataset_id",
                "registry_id",
                "name",
                "description",
                "source",
                "grain",
                "coverage",
                "manifest_id",
                "job_id",
            )
        ).lower()
        if query in text:
            return True
        tokens = [token for token in re.split(r"\W+", query) if len(token) > 2]
        return bool(tokens and any(token in text for token in tokens))

    def list_datasets(self, q: str = "", readiness: str = "", access_shape: str = "", limit: int = 50) -> dict[str, Any]:
        self._maybe_reload_registry()
        bounded_limit = max(1, min(int(limit or 50), 500))
        if q.strip() or readiness or access_shape:
            registry_rows = self.engine.search_datasets(
                q=q,
                readiness=readiness,
                access_mode=access_shape,
                limit=bounded_limit,
            )
        else:
            registry_rows = self.engine.list_datasets()[:bounded_limit]

        registry_ids = {str(row.get("dataset_id") or "") for row in self.engine.list_datasets()}
        recovery_rows = [
            row
            for row in self._receipt_rows()
            if str(row.get("dataset_id") or "") not in registry_ids
            and self._receipt_matches(row, q=q, readiness=readiness, access_shape=access_shape)
        ]
        # Recent verified registered assets lead the list so a newly registered
        # object cannot disappear behind an older 50-row registry window.
        rows = (recovery_rows + registry_rows)[:bounded_limit]
        return {
            "returned": len(rows),
            "datasets": rows,
            "authority_summary": {
                "registry_rows": sum(1 for row in rows if row.get("backend") != "registered_asset_receipt"),
                "receipt_recovery_rows": sum(1 for row in rows if row.get("backend") == "registered_asset_receipt"),
                "receipt_recovery_semantics": (
                    "Only archive-verified, registry-read-back registration receipts are recovered; "
                    "receipt-only rows remain non-queryable until catalog reconciliation."
                ),
            },
        }

    def describe_dataset(self, dataset_id: str) -> dict[str, Any]:
        self._reload_if_unknown(dataset_id)
        try:
            return self.engine.describe(dataset_id)
        except KeyError as exc:
            from scripts.research_data_mcp.registered_asset_authority import get_verified_registration_receipt

            receipt = get_verified_registration_receipt(self.repo_root, dataset_id)
            if receipt is not None:
                return receipt
            raise exc

    def query_dataset(self, dataset_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        self._reload_if_unknown(dataset_id)
        if dataset_id not in self.engine.datasets:
            from scripts.research_data_mcp.registered_asset_authority import get_verified_registration_receipt

            receipt = get_verified_registration_receipt(self.repo_root, dataset_id)
            if receipt is not None:
                raise ValueError(
                    f"{dataset_id} is {receipt.get('analysis_readiness') or 'registered'} but is not present in the "
                    "loaded query catalog; reconcile the registry row and prove a query smoke before query_ready"
                )
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
        for ds in self.list_datasets(limit=500).get("datasets") or []:
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
            "registry": repo_relpath(self.registry_path, self.repo_root),
            "total_datasets": sum(len(rows) for rows in buckets.values()),
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
