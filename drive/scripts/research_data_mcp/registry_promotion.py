#!/usr/bin/env python3
"""Promote completed procurement jobs into research_query_registry.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from glob import glob
from pathlib import Path
from typing import Any

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
            return bool(glob(str(self.repo_root / local_path)))
        return (self.repo_root / local_path).exists()

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
        jid = str(job.get("id") or "")
        if not jid:
            return None
        rel = f"data_lake/spectator_engine/scrapes/{jid}/manifest.json"
        catalog_dir = f"data_lake/spectator_engine/scrapes/{jid}"
        if self._artifact_exists(rel):
            local_path = catalog_dir
            grain = "catalog_harvest"
            backend = "local_json_glob"
            access_shape = "local_file_tree"
        elif self._artifact_exists(f"{catalog_dir}/extract.json"):
            rel = f"{catalog_dir}/extract.json"
            local_path = rel
            grain = "scrape_snapshot"
            backend = "local_json_file"
            access_shape = "local_file"
        else:
            return None
        plan = job.get("plan") or {}
        url = str(plan.get("url") or "")
        title = str(job.get("title") or plan.get("title") or f"Web scrape {jid[:8]}")
        return {
            "dataset_id": task_id,
            "name": title[:240],
            "backend": backend,
            "access_shape": access_shape,
            "analysis_readiness": "metadata_search",
            "grain": grain,
            "local_path": local_path if grain == "catalog_harvest" else rel,
            "description": f"Auto-promoted from scraper_run `{jid}` ({url[:120]}).",
            "capabilities": ["limit", "export_json"],
            "recommended_use": f"Open scrape extract via handle scrape:{jid}",
            "domain": "web_scrape",
        }

    def promote_job(self, job: dict[str, Any], *, campaign_id: str = "") -> list[dict[str, Any]]:
        if job.get("status") != "completed":
            return []
        promoted: list[dict[str, Any]] = []
        tasks = self._map.get("tasks") or {}
        for task_id in self._task_ids_from_job(job):
            plan = job.get("plan") or {}
            if plan.get("job_type") == "http_manifest":
                spec = self._spec_from_http_manifest(job, task_id, campaign_id=campaign_id)
            elif plan.get("job_type") == "scraper_run":
                spec = self._spec_from_scraper_run(job, task_id)
            elif plan.get("job_type") == "registered_pipeline":
                spec = self._spec_from_registered_pipeline(task_id, job)
            elif plan.get("job_type") == "synthesis_execute":
                spec = self._spec_from_http_manifest(job, task_id, campaign_id=campaign_id)
            else:
                spec = tasks.get(task_id) or self._spec_from_queue_task(task_id)
            if not spec:
                continue
            plan = job.get("plan") or {}
            pid = str(plan.get("partition_id") or "").strip()
            if pid:
                spec["partition_id"] = pid
            local_path = str(spec.get("local_path", ""))
            if local_path and not self._artifact_exists(local_path):
                continue
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
        """Promote completed DataCite http_manifest jobs; fallback to procured file path."""
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
        readiness = "metadata_search"
        suffix = Path(fname).suffix.lower()
        if suffix == ".csv":
            backend = "local_csv_file"
            readiness = "instant"
        elif suffix in {".json", ".jsonl"}:
            backend = "local_json_file"
        elif suffix == ".parquet":
            backend = "local_parquet_file"
            readiness = "instant"

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
            "analysis_readiness": readiness,
            "grain": "procured_snapshot",
            "local_path": local_path,
            "description": f"Procured DataCite dataset `{doi}` ({fname}).",
            "capabilities": ["limit", "export_json"],
            "recommended_use": f"Query or preview files under {local_path}",
            "domain": "datacite",
            "doi": doi,
        }
        if campaign_id:
            spec["lineage"] = {"campaign_id": campaign_id, "alpha_ready": True, "doi": doi}
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
            readiness = "instant"
            local_root = str(Path(primary).parent)
            local_file = Path(primary).name
            local_path = primary
        elif parquet_paths:
            backend = "local_parquet_panel"
            access_shape = "local_derived_tables"
            readiness = "instant"
            local_path = parquet_paths[0]
            local_root = str(Path(local_path).parent)
            local_file = Path(local_path).name
        else:
            backend = "local_json_glob"
            access_shape = "local_file_tree"
            readiness = "metadata_search"
            local_path = f"{canonical_dir}/*"
            local_root = ""
            local_file = ""

        spec: dict[str, Any] = {
            "dataset_id": dataset_id,
            "name": str(manifest.get("title") or did)[:240],
            "backend": backend,
            "access_shape": access_shape,
            "analysis_readiness": readiness,
            "grain": "hf_snapshot",
            "description": f"Procured Hugging Face dataset `{did}`.",
            "capabilities": ["limit", "export_json", "filter_date_range"],
            "recommended_use": f"Query cached HF data; handle hf:{did}",
            "domain": "huggingface",
            "partition_id": "acquired.procured",
            "source_id": "huggingface",
            "source_system": "Hugging Face",
            "source_access_mode": "materialized_instant" if readiness == "instant" else "materialized_bulk",
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

        entry = self._upsert_dataset(
            spec,
            task_id=dataset_id,
            job_id=str(job.get("id") or ""),
            campaign_id=campaign_id,
        )
        entry["job_type"] = "huggingface_collect"
        return [entry]

    def _upsert_dataset(self, spec: dict[str, Any], *, task_id: str, job_id: str, campaign_id: str = "") -> dict[str, Any]:
        registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        datasets = list(registry.get("datasets") or [])
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
        replaced = False
        for index, row in enumerate(datasets):
            if row.get("dataset_id") == dataset_id:
                merged = dict(row)
                merged.update(entry)
                datasets[index] = merged
                entry = merged
                replaced = True
                break
        if not replaced:
            datasets.append(entry)
        registry["datasets"] = datasets
        registry["updated_at"] = now
        self.registry_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return {"dataset_id": dataset_id, "replaced": replaced, "promoted_at": now}
