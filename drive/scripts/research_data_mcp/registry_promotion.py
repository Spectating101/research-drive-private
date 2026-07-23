#!/usr/bin/env python3
"""Promote completed procurement jobs into research_query_registry.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from glob import glob
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.drive_first import is_drive_first
from scripts.research_data_mcp.registry_transaction import atomic_update_json
from scripts.yzu_cluster.acquisitions import registry_spec_from_materialized


class RegistryPromoter:
    def __init__(self, repo_root: Path, registry_path: Path, map_path: Path | None = None):
        self.repo_root = repo_root.resolve()
        self.registry_path = registry_path.resolve()
        map_file = map_path or self.repo_root / "config/procurement_registry_map.json"
        self.map_path = map_file
        self._map = (
            json.loads(map_file.read_text(encoding="utf-8"))
            if map_file.exists()
            else {"tasks": {}, "connectors": {}, "pipelines": {}}
        )

    def reload_map(self) -> None:
        if self.map_path.exists():
            self._map = json.loads(self.map_path.read_text(encoding="utf-8"))

    def _artifact_exists(self, local_path: str) -> bool:
        if "*" in local_path:
            if glob(str(self.repo_root / local_path)):
                return True
            # Runtime-bind fallback (front-door / SR → runtime-integration).
            import os
            runtime = os.environ.get("YZU_RUNTIME_DRIVE_ROOT", "").strip()
            if runtime:
                return bool(glob(str(Path(runtime) / local_path)))
            return False
        path = self.repo_root / local_path
        if path.exists():
            return True
        import os
        runtime = os.environ.get("YZU_RUNTIME_DRIVE_ROOT", "").strip()
        if runtime:
            return (Path(runtime) / local_path).exists()
        return False

    def _task_ids_from_job(self, job: dict[str, Any]) -> list[str]:
        plan = job.get("plan") or {}
        jt = plan.get("job_type")
        if jt == "collection_queue_task":
            tid = plan.get("task_id")
            return [tid] if tid else []
        if jt == "collection_queue_batch":
            only = plan.get("only") or plan.get("task_ids") or []
            if isinstance(only, str):
                only = [part.strip() for part in only.split(",") if part.strip()]
            return list(only)
        if jt == "http_manifest":
            materialized = (job.get("result") or {}).get("materialized") or {}
            if materialized.get("dataset_id"):
                return [str(materialized["dataset_id"])]
            cid = plan.get("connector_id")
            if cid:
                return [f"procured_{cid}" if str(cid).startswith("src_") else str(cid)]
        if jt == "scraper_run":
            jid = str(job.get("id") or "")
            return [f"scrape_{jid}"] if jid else []
        if jt == "registered_pipeline":
            pid = plan.get("pipeline_id")
            return [pid] if pid else []
        if jt == "synthesis_execute":
            materialized = (job.get("result") or {}).get("materialized") or {}
            return [str(materialized.get("dataset_id") or "")] if materialized.get("dataset_id") else []
        if jt == "huggingface_collect":
            mat = (job.get("result") or {}).get("materialized") or {}
            did = str(mat.get("registry_dataset_id") or mat.get("dataset_id") or "")
            if did:
                return [did]
            hf = str(plan.get("hf_dataset_id") or "")
            if hf:
                from scripts.hf_collect_dataset import registry_dataset_id

                return [registry_dataset_id(hf)]
        return []

    def _resolve_path(self, resolver: str, job: dict[str, Any] | None = None) -> str:
        """Map path_resolver tokens to repo-relative globs or paths."""
        if resolver == "latest_skynet_harvest_projects":
            root = self.repo_root / "stablecoin_skynet/data"
            harvest_dirs = sorted(
                (p for p in root.glob("harvest_*") if (p / "manifest.json").is_file()),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not harvest_dirs:
                return ""
            latest = harvest_dirs[0].relative_to(self.repo_root)
            return f"{latest}/projects/*.json"
        if resolver == "usdt_pilot_artifacts":
            pilot = self.repo_root / "data/usdt_catalogue/pilot"
            if not pilot.is_dir():
                return ""
            patterns = ["*.csv", "*.json", "*.jsonl", "*.manifest.json"]
            for pattern in patterns:
                if list(pilot.glob(pattern)):
                    return f"data/usdt_catalogue/pilot/{pattern}"
            return "data/usdt_catalogue/pilot/*"
        return resolver

    def _spec_from_registered_pipeline(self, pipeline_id: str, job: dict[str, Any]) -> dict[str, Any] | None:
        pipelines = self._map.get("pipelines") or {}
        spec = pipelines.get(pipeline_id)
        if not spec:
            return None
        spec = dict(spec)
        resolver = str(spec.pop("path_resolver", "") or spec.get("local_path") or "")
        local_path = spec.get("local_path") or ""
        if resolver and not local_path:
            local_path = self._resolve_path(resolver, job)
        if not local_path:
            return None
        spec["local_path"] = local_path
        if not spec.get("dataset_id"):
            spec["dataset_id"] = pipeline_id
        return spec

    def _spec_from_queue_task(self, task_id: str) -> dict[str, Any] | None:
        queue_path = self.repo_root / "config/data_collection_queue.json"
        if not queue_path.exists():
            return None
        payload = json.loads(queue_path.read_text(encoding="utf-8"))
        task = next((row for row in payload.get("tasks") or [] if row.get("id") == task_id), None)
        if not task:
            return None
        output_hint = str(task.get("output_hint") or "").strip()
        if not output_hint:
            return None
        local_path = output_hint.replace("YYYY-MM-DD", "*")
        if local_path.endswith("/"):
            local_path = f"{local_path}*"
        is_glob = "*" in local_path
        if local_path.endswith(".json") and not is_glob:
            backend = "local_json_file"
        elif local_path.endswith(".csv") and not is_glob:
            backend = "local_json_file"
        else:
            backend = "local_json_glob"
        return {
            "dataset_id": task_id,
            "name": task.get("title") or task_id,
            "backend": backend,
            "access_shape": "local_file_tree" if is_glob else "local_file",
            "analysis_readiness": "metadata_search",
            "grain": "run_snapshot",
            "local_path": local_path,
            "description": f"Auto-promoted from collection queue task `{task_id}`.",
            "capabilities": ["limit", "export_json"],
            "recommended_use": f"Query artifacts from queue task {task_id}.",
        }

    def _spec_from_http_manifest(self, job: dict[str, Any], task_id: str, campaign_id: str = "") -> dict[str, Any] | None:
        result = job.get("result") or {}
        materialized = result.get("materialized") or {}
        if materialized:
            spec = registry_spec_from_materialized(self.repo_root, job, materialized, campaign_id=campaign_id)
            if spec:
                return spec
        connectors = self._map.get("connectors") or {}
        if task_id in connectors:
            return dict(connectors[task_id])
        plan = job.get("plan") or {}
        cid = plan.get("connector_id")
        if cid and str(cid) in connectors:
            return dict(connectors[str(cid)])
        canonical = materialized.get("canonical_dir") or result.get("canonical_dir")
        if canonical and self._artifact_exists(str(canonical).rstrip("/") + "/*" if materialized.get("files") and len(materialized.get("files")) > 1 else canonical):
            pass
        return None

    def _spec_from_scraper_run(self, job: dict[str, Any], task_id: str) -> dict[str, Any] | None:
        result = job.get("result") or {}
        materialized = result.get("materialized") or {}
        if materialized:
            spec = registry_spec_from_materialized(self.repo_root, job, materialized)
            if spec:
                return spec
        plan = job.get("plan") or {}
        script_key = str(plan.get("script_key") or "")
        url = str(plan.get("url") or "")
        dest = str(plan.get("destination") or "")
        if not dest:
            dest = str(result.get("output_dir") or "")
        if not dest or not self._artifact_exists(dest):
            return None
        domain = "Generic Web"
        if "medicare.gov" in url:
            domain = "Medicare"
        elif "sec.gov" in url:
            domain = "SEC"
        elif "machinereadable.narod.ru" in url:
            domain = "Narod Russia"
        elif script_key:
            domain = script_key.replace("_", " ").title()
        return {
            "dataset_id": task_id,
            "name": domain + " - Scraped Dataset",
            "backend": "local_json_glob",
            "access_shape": "local_file_tree",
            "analysis_readiness": "metadata_search",
            "grain": "page_snapshot",
            "local_path": f"{dest.rstrip('/')}/*",
            "description": f"Scraped dataset from {url}",
            "capabilities": ["limit", "export_json"],
            "recommended_use": f"Query scraped artifacts from {dest}.",
            "source_url": url,
            "scraper_key": script_key,
        }

    def _spec_from_synthesis_execute(self, job: dict[str, Any], task_id: str, campaign_id: str = "") -> dict[str, Any] | None:
        materialized = (job.get("result") or {}).get("materialized") or {}
        if not materialized:
            return None
        return registry_spec_from_materialized(self.repo_root, job, materialized, campaign_id=campaign_id)

    def _spec_for_task(self, task_id: str, job: dict[str, Any], campaign_id: str = "") -> dict[str, Any] | None:
        jt = (job.get("plan") or {}).get("job_type")
        if jt == "http_manifest":
            return self._spec_from_http_manifest(job, task_id, campaign_id)
        if jt == "scraper_run":
            return self._spec_from_scraper_run(job, task_id)
        if jt == "synthesis_execute":
            return self._spec_from_synthesis_execute(job, task_id, campaign_id)
        tasks = self._map.get("tasks") or {}
        if task_id in tasks:
            return dict(tasks[task_id])
        if jt == "registered_pipeline":
            return self._spec_from_registered_pipeline(task_id, job)
        return self._spec_from_queue_task(task_id)

    def promote_job(self, job: dict[str, Any], campaign_id: str = "") -> list[dict[str, Any]]:
        if job.get("status") != "completed":
            return []
        self.reload_map()
        from scripts.yzu_cluster.acquisitions import prove_query_smoke

        promoted = []
        for task_id in self._task_ids_from_job(job):
            spec = self._spec_for_task(task_id, job, campaign_id)
            if not spec:
                continue
            local_path = spec.get("local_path") or spec.get("local_root")
            if local_path and not self._artifact_exists(local_path):
                continue
            smoke = prove_query_smoke(self.repo_root, spec, limit=3)
            spec["query_smoke"] = smoke
            if smoke.get("ok"):
                spec["analysis_readiness"] = "query_ready"
                spec["source_access_mode"] = spec.get("source_access_mode") or "materialized_query_ready"
            else:
                # Honest: archived/registered bytes exist, but not proven queryable yet.
                spec["analysis_readiness"] = "registered"
            entry = self._upsert_dataset(spec, task_id=task_id, job_id=job.get("id", ""), campaign_id=campaign_id)
            promoted.append(entry)
        return promoted

    def promote_datacite_collect(
        self,
        job: dict[str, Any],
        *,
        doi: str,
        campaign_id: str = "",
    ) -> list[dict[str, Any]]:
        """Promote completed DataCite jobs only after the same bounded query smoke."""
        if job.get("status") != "completed":
            return []
        promoted = self.promote_job(job, campaign_id=campaign_id)
        if promoted:
            return promoted

        plan = job.get("plan") or {}
        if not plan.get("datacite_doi") and not doi:
            return []

        doi = str(plan.get("datacite_doi") or doi)
        dest = str(plan.get("destination") or "").rstrip("/")
        fname = str(plan.get("datacite_file") or "")
        if not dest or not fname:
            return []

        file_path = f"{dest}/{fname}"
        local_path = file_path
        backend = "local_file"
        access_shape = "local_file"
        suffix = Path(fname).suffix.lower()
        if suffix == ".csv":
            backend = "local_csv_file"
        elif suffix in {".json", ".jsonl"}:
            backend = "local_json_file"
        elif suffix == ".parquet":
            backend = "local_parquet_panel"

        if not self._artifact_exists(file_path):
            glob_path = f"{dest}/*"
            if not self._artifact_exists(glob_path):
                return []
            local_path = glob_path
            backend = "local_csv_glob" if suffix == ".csv" else "local_json_glob"
            access_shape = "local_file_tree"

        slug = doi.replace("/", "_").replace(".", "_")
        dataset_id = f"datacite_{slug}"
        spec: dict[str, Any] = {
            "dataset_id": dataset_id,
            "name": str(plan.get("title") or doi)[:240],
            "backend": backend,
            "access_shape": access_shape,
            "analysis_readiness": "registered",
            "grain": "procured_snapshot",
            "local_path": local_path,
            "description": f"Procured DataCite dataset `{doi}` ({fname}).",
            "capabilities": ["limit", "export_json"],
            "recommended_use": f"Query or preview files under {local_path}",
            "domain": "datacite",
            "doi": doi,
        }
        if backend == "local_parquet_panel" and "*" not in local_path:
            panel_path = Path(local_path)
            spec["local_root"] = str(panel_path.parent)
            spec["local_file"] = panel_path.name
        if campaign_id:
            spec["lineage"] = {"campaign_id": campaign_id, "alpha_ready": True, "doi": doi}

        from scripts.yzu_cluster.acquisitions import prove_query_smoke

        smoke = prove_query_smoke(self.repo_root, spec, limit=3)
        spec["query_smoke"] = smoke
        if smoke.get("ok"):
            spec["analysis_readiness"] = "query_ready"
            spec["source_access_mode"] = "materialized_query_ready"
        entry = self._upsert_dataset(
            spec,
            task_id=dataset_id,
            job_id=str(job.get("id") or ""),
            campaign_id=campaign_id,
        )
        return [entry]

    def promote_huggingface_collect(
        self,
        job: dict[str, Any],
        *,
        hf_dataset_id: str,
        campaign_id: str = "",
    ) -> list[dict[str, Any]]:
        """Promote completed Hugging Face collect jobs into the registry."""
        if job.get("status") != "completed":
            return []
        promoted = self.promote_job(job, campaign_id=campaign_id)
        if promoted:
            return promoted

        from scripts.hf_collect_dataset import hf_slug, registry_dataset_id

        did = str(hf_dataset_id or (job.get("plan") or {}).get("hf_dataset_id") or "").strip().removeprefix("hf:")
        if not did:
            return []

        result = job.get("result") or {}
        mat = result.get("materialized") or {}
        slug = hf_slug(did)
        canonical_dir = str(mat.get("canonical_dir") or f"data_lake/procured/huggingface/{slug}")
        manifest_rel = f"{canonical_dir}/manifest.json"
        if not self._artifact_exists(manifest_rel):
            return []

        manifest = json.loads((self.repo_root / manifest_rel).read_text(encoding="utf-8"))
        primary = str(manifest.get("primary_parquet") or "")
        files = manifest.get("files") or []
        parquet_paths = [str(f.get("path") or "") for f in files if str(f.get("path") or "").endswith(".parquet")]

        dataset_id = registry_dataset_id(did)
        if primary and self._artifact_exists(primary):
            backend = "local_parquet_panel"
            access_shape = "local_derived_tables"
            local_root = str(Path(primary).parent)
            local_file = Path(primary).name
            local_path = primary
        elif parquet_paths:
            backend = "local_parquet_panel"
            access_shape = "local_derived_tables"
            local_path = parquet_paths[0]
            local_root = str(Path(local_path).parent)
            local_file = Path(local_path).name
        else:
            backend = "local_json_glob"
            access_shape = "local_file_tree"
            local_path = f"{canonical_dir}/*"
            local_root = ""
            local_file = ""

        spec: dict[str, Any] = {
            "dataset_id": dataset_id,
            "name": str(manifest.get("title") or did)[:240],
            "backend": backend,
            "access_shape": access_shape,
            "analysis_readiness": "registered",
            "grain": "hf_snapshot",
            "description": f"Procured Hugging Face dataset `{did}`.",
            "capabilities": ["limit", "export_json", "filter_date_range"],
            "recommended_use": f"Query cached HF data; handle hf:{did}",
            "domain": "huggingface",
            "partition_id": "acquired.procured",
            "source_id": "huggingface",
            "source_system": "Hugging Face",
            "source_access_mode": "materialized_registered",
            "hf_dataset_id": did,
            "handle": f"hf:{did}",
        }
        if local_path:
            spec["local_path"] = local_path
        if local_root:
            spec["local_root"] = local_root
        if local_file:
            spec["local_file"] = local_file
        if campaign_id:
            spec["lineage"] = {"campaign_id": campaign_id, "alpha_ready": False, "hf_dataset_id": did}

        from scripts.yzu_cluster.acquisitions import prove_query_smoke

        smoke = prove_query_smoke(self.repo_root, spec, limit=3)
        spec["query_smoke"] = smoke
        if smoke.get("ok"):
            spec["analysis_readiness"] = "query_ready"
            spec["source_access_mode"] = "materialized_query_ready"
        entry = self._upsert_dataset(
            spec,
            task_id=dataset_id,
            job_id=str(job.get("id") or ""),
            campaign_id=campaign_id,
        )
        entry["job_type"] = "huggingface_collect"
        return [entry]

    def _upsert_dataset(self, spec: dict[str, Any], *, task_id: str, job_id: str, campaign_id: str = "") -> dict[str, Any]:
        if not is_drive_first(self.repo_root):
            raise PermissionError("canonical registry promotion requires Drive-first verified storage")
        dataset_id = spec["dataset_id"]
        now = datetime.now(timezone.utc).isoformat()
        entry = dict(spec)
        job_type = (
            "huggingface_collect"
            if task_id.startswith("hf_")
            else "http_manifest"
            if task_id.startswith("procured_")
            else "scraper_run"
            if task_id.startswith("scrape_")
            else "synthesis_execute"
            if str(dataset_id).startswith("synthesis_")
            else "registered_pipeline"
            if (self._map.get("pipelines") or {}).get(task_id)
            else "collection_queue"
        )
        entry["procurement"] = {
            "source_task_id": task_id,
            "promoted_at": now,
            "promoted_from_job": job_id,
            "job_type": job_type,
        }
        if campaign_id:
            entry.setdefault("lineage", {})
            entry["lineage"]["campaign_id"] = campaign_id
            entry["lineage"]["alpha_ready"] = True
            entry["lineage"]["join_keys"] = spec.get("join_keys") or spec.get("grain", "")

        def mutate(registry: dict[str, Any]) -> dict[str, Any]:
            datasets = list(registry.get("datasets") or [])
            replaced = False
            stored = entry
            for index, row in enumerate(datasets):
                if row.get("dataset_id") == dataset_id:
                    merged = dict(row)
                    merged.update(entry)
                    datasets[index] = merged
                    stored = merged
                    replaced = True
                    break
            if not replaced:
                datasets.append(entry)
            registry["datasets"] = datasets
            registry["updated_at"] = now
            return {
                "dataset_id": dataset_id,
                "replaced": replaced,
                "promoted_at": now,
                "stored": stored,
            }

        result = atomic_update_json(self.registry_path, mutate)
        result.pop("stored", None)
        return result
