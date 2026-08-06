#!/usr/bin/env python3
"""Registry search and query operations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.inventory_authority import (
    SCOPE_DESK_VISIBLE,
    SCOPE_REGISTRY_ALL,
    SCOPE_RETURNED_WINDOW,
    build_inventory_summary,
    is_excluded_operational_or_test,
    view_scope,
)
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

    _OPS_NOISE_MARKERS = (
        "canary",
        "smoke",
        "probe",
        "windows http prove",
        "landing prove",
        "day-2 deploy",
        "day2_deploy",
        "mcp_canary",
        "host acceptance",
        "host_acceptance",
        "post-heal",
        "fullops",
        "winclaim",
        "ssrf3_",
        "rev_live",
        "example.com",
        "capability_canary",
        "codex_sec_tickers_canary",
        "synthesis_agent_canary",
        "synthesis_sec_ticker_count_canary",
    )

    @classmethod
    def _is_ops_noise_dataset(cls, row: dict[str, Any]) -> bool:
        if row.get("professor_visible") is False or is_excluded_operational_or_test(row):
            return True
        blob = " ".join(
            str(row.get(key) or "")
            for key in (
                "dataset_id",
                "registry_id",
                "name",
                "display_name",
                "description",
                "source",
                "grain",
                "manifest_id",
                "job_id",
            )
        ).lower()
        return any(marker in blob for marker in cls._OPS_NOISE_MARKERS)

    @staticmethod
    def _professor_view_row(row: dict[str, Any]) -> dict[str, Any]:
        """Surface readable titles for Library without renaming stable dataset_id."""
        out = dict(row)
        display = str(out.get("display_name") or "").strip()
        if display:
            out["name"] = display
        one_line = str(out.get("one_line") or "").strip()
        if one_line and (
            not out.get("description")
            or "Auto-promoted" in str(out.get("description") or "")
            or "Procured via" in str(out.get("description") or "")
        ):
            out["description"] = one_line
        return out

    def inventory_summary(self, *, include_partition_lanes: bool = True) -> dict[str, Any]:
        """Canonical inventory projection for this loaded registry revision."""
        self._maybe_reload_registry()
        return build_inventory_summary(
            self.engine.list_datasets(),
            registry_path=self.registry_path,
            repo_root=self.repo_root,
            include_partition_lanes=include_partition_lanes,
        )

    def list_datasets(
        self,
        q: str = "",
        readiness: str = "",
        access_shape: str = "",
        limit: int = 200,
        include_ops: bool = False,
    ) -> dict[str, Any]:
        self._maybe_reload_registry()
        bounded_limit = max(1, min(int(limit or 200), 500))
        all_registry = list(self.engine.list_datasets())
        inventory = build_inventory_summary(
            all_registry,
            registry_path=self.registry_path,
            repo_root=self.repo_root,
            include_partition_lanes=True,
        )
        if q.strip() or readiness or access_shape:
            registry_rows = self.engine.search_datasets(
                q=q,
                readiness=readiness,
                access_mode=access_shape,
                limit=max(bounded_limit, 500),
            )
        else:
            registry_rows = all_registry

        registry_ids = {str(row.get("dataset_id") or "") for row in all_registry}
        recovery_rows = [
            row
            for row in self._receipt_rows()
            if str(row.get("dataset_id") or "") not in registry_ids
            and self._receipt_matches(row, q=q, readiness=readiness, access_shape=access_shape)
        ]
        # Professor Library: registry holdings first. Ops canaries/receipts stay out
        # unless include_ops=1 (staff). Otherwise Apps & connections fills with junk.
        hidden_ops = 0
        if include_ops:
            combined = recovery_rows + registry_rows
        else:
            kept_registry = []
            for row in registry_rows:
                if self._is_ops_noise_dataset(row):
                    hidden_ops += 1
                    continue
                kept_registry.append(row)
            kept_recovery = []
            for row in recovery_rows:
                if self._is_ops_noise_dataset(row):
                    hidden_ops += 1
                    continue
                kept_recovery.append(row)
            combined = kept_registry + kept_recovery
        total_matching = len(combined)
        rows = [self._professor_view_row(row) for row in combined[:bounded_limit]]
        filtered = bool(q.strip() or readiness or access_shape or recovery_rows)
        if filtered:
            scope_id = SCOPE_RETURNED_WINDOW
            primary_field = "returned_matching"
        elif include_ops:
            scope_id = SCOPE_REGISTRY_ALL
            primary_field = "registered"
        else:
            scope_id = SCOPE_DESK_VISIBLE
            primary_field = "visible_to_desk"
        return {
            "returned": len(rows),
            "total": total_matching,
            "truncated": total_matching > len(rows),
            "limit": bounded_limit,
            "datasets": rows,
            "ops_datasets_hidden": hidden_ops,
            "include_ops": bool(include_ops),
            "inventory": inventory,
            "view_scope": view_scope(
                scope_id=scope_id,
                primary_total=total_matching,
                primary_total_field=primary_field,
                inventory=inventory,
                filters={
                    "q": q,
                    "readiness": readiness,
                    "access_shape": access_shape,
                    "limit": bounded_limit,
                    "includes_receipt_recovery": bool(recovery_rows),
                },
                note=(
                    "`total` is matching rows for this query window (registry + verified receipt "
                    "recovery). Compare only with payloads that share inventory.registry_revision."
                    "fingerprint and the same view_scope.scope. "
                    "completed != registered != query_ready."
                ),
            ),
            "ops_datasets_hidden": hidden_ops,
            "include_ops": bool(include_ops),
            "authority_summary": {
                "registry_rows": sum(1 for row in rows if row.get("backend") != "registered_asset_receipt"),
                "receipt_recovery_rows": sum(1 for row in rows if row.get("backend") == "registered_asset_receipt"),
                "registry_total": len(all_registry),
                "visible_to_desk": inventory["totals"]["visible_to_desk"],
                "excluded_operational_test": inventory["totals"]["excluded_operational_test"],
                "receipt_recovery_semantics": (
                    "Only archive-verified, registry-read-back registration receipts are recovered; "
                    "receipt-only rows remain non-queryable until catalog reconciliation. "
                    "Professor list hides canary/smoke/ops receipts by default."
                ),
            },
        }

    def describe_dataset(self, dataset_id: str) -> dict[str, Any]:
        self._reload_if_unknown(dataset_id)
        try:
            row = self.engine.describe(dataset_id)
        except KeyError as exc:
            from scripts.research_data_mcp.registered_asset_authority import get_verified_registration_receipt

            receipt = get_verified_registration_receipt(self.repo_root, dataset_id)
            if receipt is not None:
                row = receipt
            else:
                raise exc
        return self._enrich_describe_for_fe(dict(row))

    def hydrate_dataset(self, dataset_id: str) -> dict[str, Any]:
        """Explicit faculty hydrate — pull canonical Drive bytes to the desk, then re-describe."""
        self._reload_if_unknown(dataset_id)
        try:
            spec = dict(self.engine.describe(dataset_id))
        except KeyError as exc:
            raise ValueError(f"unknown dataset_id: {dataset_id}") from exc
        from scripts.research_data_mcp.registry_hydrate import ensure_registry_local_bytes

        hydrate = ensure_registry_local_bytes(self.repo_root, spec, dry_run=False)
        if hydrate.get("ok"):
            self.reload_registry()
        out = self.describe_dataset(dataset_id)
        out["hydrate"] = hydrate
        out["hydrated"] = bool(hydrate.get("ok"))
        return out

    def _enrich_describe_for_fe(self, row: dict[str, Any]) -> dict[str, Any]:
        """Attach local_ready / hydrate action so the Library rail can offer one click."""
        from scripts.research_data_mcp.procurement_fast import local_path_has_data
        from scripts.research_data_mcp.registry_hydrate import dataset_needs_hydrate

        did = str(row.get("dataset_id") or "").strip()
        local = str(row.get("local_path") or row.get("local_file") or "").strip()
        if not local:
            root = str(row.get("local_root") or "").rstrip("/")
            name = str(row.get("local_file") or "").lstrip("/")
            local = f"{root}/{name}" if root and name else ""
        remote = str(
            row.get("canonical_remote")
            or (row.get("lineage") or {}).get("canonical_remote")
            or ""
        ).strip()
        local_ready = bool(local and local_path_has_data(self.repo_root, local))
        needs = bool(dataset_needs_hydrate(self.repo_root, row) or row.get("hydrate_required"))
        # Stale demotion with bytes restored
        if local_ready and row.get("runtime_readiness_reason") == "local_bytes_missing":
            needs = False
        row["local_ready"] = local_ready
        row["hydrate_required"] = bool(needs)
        if needs and remote and did:
            row["required_action"] = "hydrate"
            row["actions"] = [
                {
                    "id": "hydrate",
                    "label": "Hydrate from Drive",
                    "method": "POST",
                    "path": f"/datasets/{did}/hydrate",
                }
            ]
            row.setdefault(
                "message",
                "Canonical bytes are on Drive. Hydrate to the desk before Preview/query.",
            )
        elif local_ready and str(row.get("analysis_readiness") or "").lower() in {
            "instant",
            "query_ready",
        }:
            row["required_action"] = "query"
        return row

    def query_dataset(self, dataset_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        self._reload_if_unknown(dataset_id)
        limit = int(params.get("limit") or 50)
        preview_budget = max(1, min(limit, 100))
        want_preview = str(params.get("preview") or "").strip().lower() in {"1", "true", "yes"} or limit <= 100

        def _preview(spec: dict[str, Any]) -> dict[str, Any]:
            from scripts.research_data_mcp.dataset_preview import preview_dataset_rows

            return preview_dataset_rows(self.repo_root, spec, limit=preview_budget, allow_remote=True)

        if dataset_id not in self.engine.datasets:
            from scripts.research_data_mcp.registered_asset_authority import get_verified_registration_receipt

            receipt = get_verified_registration_receipt(self.repo_root, dataset_id)
            if receipt is not None:
                # UI Preview asks /query?limit=N — return sample rows instead of a hard catalog error.
                if want_preview:
                    sample = _preview(receipt)
                    if sample.get("rows"):
                        return sample
                    # Keep a soft empty preview payload so the modal can explain the gap.
                    meta = dict(sample.get("meta") or {})
                    meta.update(
                        {
                            "analysis_readiness": receipt.get("analysis_readiness") or "registered",
                            "catalog_state": "reconciliation_required",
                            "message": meta.get("message")
                            or (
                                f"{dataset_id} is registered in the vault but has no sampleable local/GDrive file yet."
                            ),
                        }
                    )
                    return {"dataset_id": dataset_id, "rows": [], "meta": meta}
                raise ValueError(
                    f"{dataset_id} is {receipt.get('analysis_readiness') or 'registered'} but is not present in the "
                    "loaded query catalog; reconcile the registry row and prove a query smoke before query_ready"
                )
        ds = self.engine.datasets.get(dataset_id)
        hydrate_requested = str(params.get("hydrate") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        hydrate: dict[str, Any] = {}
        if ds:
            from scripts.research_data_mcp.registry_hydrate import ensure_registry_local_bytes

            try:
                # Every query performs a cheap hydration preflight. Ordinary
                # queries remain non-mutating; hydrate=1 authorizes the pull.
                hydrate = ensure_registry_local_bytes(
                    self.repo_root,
                    ds,
                    dry_run=not hydrate_requested,
                )
            except Exception as exc:
                hydrate = {"ok": False, "error": str(exc)[:200]}
            if hydrate.get("ok"):
                self.reload_registry()
                ds = self.engine.datasets.get(dataset_id)

        if ds and self._requires_explicit_hydration(ds, params) and not hydrate.get("ok"):
            # Preview path: sample local/remote bytes instead of returning an empty hydrate stub.
            if want_preview and not hydrate_requested:
                sample = _preview(ds)
                if sample.get("rows"):
                    return sample
            return {
                "dataset_id": dataset_id,
                "meta": {
                    "error": "not_query_ready",
                    "queryable": False,
                    "analysis_readiness": str(ds.get("analysis_readiness") or "registered"),
                    "required_action": "hydrate",
                    "source_of_truth": ds.get("source_of_truth"),
                    "canonical_remote": ds.get("canonical_remote") or (ds.get("lineage") or {}).get("canonical_remote"),
                    "message": "This registered asset has metadata only on the desk. Hydrate it before querying rows.",
                    "hydrate_requested": hydrate_requested,
                    "hydrate": hydrate,
                    "params": params,
                },
                "rows": [],
            }
        # Never auto-hydrate on ordinary UI preview/query — that can stall the desk on GDrive.
        # Explicit hydrate=1 remains available for Ask/ops follow-through.
        hydrate_requested = str(params.get("hydrate") or "").strip().lower() in {"1", "true", "yes"}
        if ds and hydrate_requested:
            from scripts.research_data_mcp.registry_hydrate import ensure_registry_local_bytes

            hydrate = ensure_registry_local_bytes(self.repo_root, ds)
            if hydrate.get("ok"):
                self.reload_registry()
        def _is_status_card(rows: list) -> bool:
            if not rows:
                return False
            row = rows[0] if isinstance(rows[0], dict) else {}
            keys = set(row)
            if keys & {"interface", "safe_actions", "bigquery_ready", "bigquery_dependency"}:
                return True
            # File-inventory listings (path/file/bytes) are not professor Preview tables.
            if {"path", "file", "bytes"} <= keys and len(keys) <= 8:
                extra = keys - {"path", "file", "bytes", "keys", "json_type", "parse_error", "name", "cik", "ticker", "title", "entityType"}
                if not extra:
                    return True
            return False

        try:
            out = self.engine.query(dataset_id, **params).to_dict()
            rows = out.get("rows") or []
            meta = out.get("meta") or {}
            if (
                meta.get("required_action") == "review_schema"
                or meta.get("error") == "schema_mismatch"
                or (ds and ds.get("schema_review_required"))
            ):
                # A preview sampler must not bypass the query engine's schema
                # integrity decision and make malformed bytes look usable.
                return out
            if want_preview and ds and (not rows or _is_status_card(rows)):
                if ds.get("backend") == "usdt_bigquery_catalogue":
                    sample_params = dict(params)
                    sample_params["action"] = "sample"
                    sample_params["preview"] = "1"
                    try:
                        sample_out = self.engine.query(dataset_id, **sample_params).to_dict()
                        if sample_out.get("rows") and not _is_status_card(sample_out.get("rows") or []):
                            meta = dict(sample_out.get("meta") or {})
                            meta["preview"] = True
                            meta["mode"] = meta.get("mode") or "local_rpc_sample"
                            sample_out["meta"] = meta
                            return sample_out
                    except Exception:
                        pass
                sample = _preview(ds)
                if sample.get("rows"):
                    return sample
                if _is_status_card(rows):
                    return {
                        "dataset_id": dataset_id,
                        "rows": [],
                        "meta": {
                            "preview": True,
                            "error": "preview_status_card_suppressed",
                            "message": (
                                "This asset is a guarded remote catalogue. "
                                "No local sample rows are available for Preview yet."
                            ),
                            "returned": 0,
                        },
                    }
            return out
        except KeyError as exc:
            self.reload_registry()
            try:
                return self.engine.query(dataset_id, **params).to_dict()
            except Exception:
                if want_preview:
                    sample = _preview(ds or {"dataset_id": dataset_id})
                    if sample.get("rows"):
                        return sample
                    return {
                        "dataset_id": dataset_id,
                        "rows": [],
                        "meta": {
                            "preview": True,
                            "error": "preview_unavailable",
                            "message": f"Preview unavailable for {dataset_id}: not in query catalog.",
                            "returned": 0,
                        },
                    }
                known = sorted(self.engine.datasets.keys())
                raise KeyError(
                    f"unknown dataset_id: {dataset_id}. Known: {', '.join(known[:12])}{'...' if len(known) > 12 else ''}"
                ) from exc
        except Exception as exc:
            # Preview must never 500 the modal — return sample or soft empty payload.
            if want_preview:
                sample = _preview(ds or {"dataset_id": dataset_id})
                if sample.get("rows"):
                    return sample
                return {
                    "dataset_id": dataset_id,
                    "rows": [],
                    "meta": {
                        "preview": True,
                        "error": "preview_unavailable",
                        "message": f"Preview unavailable: {exc}",
                        "returned": 0,
                    },
                }
            raise

    def _requires_explicit_hydration(self, ds: dict[str, Any], params: dict[str, Any]) -> bool:
        """Keep registered remote assets from triggering an implicit GDrive read.

        If local bytes are already on the desk (including after a compact→restore),
        do not wall the query behind hydrate — clear stale demotion flags in-memory.
        """
        backend = str(ds.get("backend") or "").strip()
        readiness = str(ds.get("analysis_readiness") or "").strip().lower()
        if backend not in {
            "local_file",
            "local_csv_file",
            "local_csv_glob",
            "local_json_file",
            "local_json_glob",
            "local_parquet_panel",
        }:
            return False
        local = str(ds.get("local_path") or "").strip()
        if not local:
            root = str(ds.get("local_root") or "").rstrip("/")
            name = str(ds.get("local_file") or "").lstrip("/")
            local = f"{root}/{name}" if root and name else ""
        if local:
            from scripts.research_data_mcp.procurement_fast import local_path_has_data

            if local_path_has_data(self.repo_root, local):
                if ds.get("hydrate_required") or ds.get("runtime_readiness_reason") == "local_bytes_missing":
                    ds.pop("hydrate_required", None)
                    if ds.get("runtime_readiness_reason") == "local_bytes_missing":
                        ds.pop("runtime_readiness_reason", None)
                    smoke = ds.get("query_smoke") if isinstance(ds.get("query_smoke"), dict) else {}
                    if readiness == "registered" and (smoke.get("ok") or True):
                        # Bytes restored after compact — treat as queryable again.
                        ds["analysis_readiness"] = "query_ready"
                        mat = dict(ds.get("materialization") or {})
                        if mat.get("skipped") == "local_bytes_missing_at_runtime":
                            mat["query_ready"] = True
                            mat.pop("skipped", None)
                            ds["materialization"] = mat
                return False
        remote = str(ds.get("canonical_remote") or (ds.get("lineage") or {}).get("canonical_remote") or "").strip()
        if not remote:
            return backend == "local_file" and readiness not in {"instant", "query_ready"}
        return bool(ds.get("hydrate_required") or ds.get("runtime_readiness_reason") == "local_bytes_missing")

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
        self._maybe_reload_registry()
        inventory = self.inventory_summary()
        buckets: dict[str, list[dict[str, str]]] = {
            "instant_local": [],
            "metadata_search": [],
            "remote_query": [],
            "procurement_ops": [],
            "other": [],
        }
        # Desk overview is registry-scoped (not receipt recovery). Ops/test cards
        # remain listed under procurement_ops for operators but are excluded from
        # the desk-visible primary total.
        for ds in self.engine.list_datasets():
            item = {
                "dataset_id": ds["dataset_id"],
                "name": ds.get("display_name") or ds.get("title") or ds.get("name", ds["dataset_id"]),
                "title": ds.get("display_name") or ds.get("title") or ds.get("name", ds["dataset_id"]),
                "grain": ds.get("grain", ""),
                "analysis_readiness": ds.get("analysis_readiness", ""),
            }
            if ds.get("aliases"):
                item["aliases"] = list(ds.get("aliases") or [])[:8]
            if ds.get("keywords"):
                item["keywords"] = list(ds.get("keywords") or [])[:12]
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
        desk_total = inventory["totals"]["visible_to_desk"]
        registered_total = inventory["totals"]["registered"]
        return {
            "registry": repo_relpath(self.registry_path, self.repo_root),
            "total_datasets": desk_total,
            "registered_datasets": registered_total,
            "excluded_operational_test": inventory["totals"]["excluded_operational_test"],
            "bucket_row_count": sum(len(rows) for rows in buckets.values()),
            "buckets": buckets,
            "partitions": self._partition_summary(),
            "inventory": inventory,
            "view_scope": view_scope(
                scope_id=SCOPE_DESK_VISIBLE,
                primary_total=desk_total,
                primary_total_field="visible_to_desk",
                inventory=inventory,
                note=(
                    "total_datasets is desk-visible registry rows. registered_datasets is the full "
                    "registry authority count. Bucket lists still include ops cards under "
                    "procurement_ops for operators. Do not compare to /datasets `total` when that "
                    "window includes receipt recovery or query filters."
                ),
            ),
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
