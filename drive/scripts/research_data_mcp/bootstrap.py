#!/usr/bin/env python3
"""Single wiring point for the research data library backend."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


from scripts.research_data_mcp.campaign_runner import CampaignRunner
from scripts.research_data_mcp.campaign_store import CampaignStore
from scripts.research_data_mcp.gateway import ResearchDataGateway
from scripts.research_data_mcp.jobs import JobService
from scripts.research_data_mcp.procurement_memory import ProcurementMemory
from scripts.research_data_mcp.collection_flywheel import CollectionFlywheel
from scripts.research_data_mcp.registry_promotion import RegistryPromoter
from scripts.research_data_mcp.tool_handlers import ResearchToolHandlers
from scripts.research_query_engine.engine import ResearchQueryEngine
from scripts.yzu_cluster.api import YzuClusterAPI
from scripts.yzu_cluster.orchestrator import YzuOrchestrator
from sharpe_kernel.paths import repo_root_from_file
from scripts.yzu_cluster.acquisitions import repo_relpath

DEFAULT_REGISTRY = "config/research_query_registry.json"


def _valid_materialization_manifest(
    repo_root: Path,
    result: dict[str, Any] | None,
    materialized: dict[str, Any] | None,
    dataset_id: str,
) -> str | None:
    """Return a manifest ID only when a local manifest proves this exact output.

    Registry promotion is a Library authority mutation, not a convenience marker
    for a completed worker process. Both generic collection and Synthesis must
    present the same manifest identity that runtime registration later consumes.
    """

    result = result or {}
    materialized = materialized or {}
    manifest_id = str(
        result.get("output_manifest_id")
        or result.get("manifest_id")
        or materialized.get("manifest_id")
        or ""
    ).strip()
    raw_path = str(result.get("manifest_path") or materialized.get("manifest_path") or "").strip()
    if not (manifest_id and raw_path and dataset_id):
        return None
    path = Path(raw_path)
    path = path if path.is_absolute() else repo_root / path
    try:
        path = path.resolve()
    except OSError:
        return None
    # Runtime binds (data_lake/procured → YZU_RUNTIME_DRIVE_ROOT) resolve outside
    # the checkout; accept any path that repo_relpath can map back.
    try:
        repo_relpath(path, repo_root)
    except Exception:
        return None
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    output = document.get("output") if isinstance(document.get("output"), dict) else {}
    documented_id = str(output.get("dataset_id") or document.get("dataset_id") or "").strip()
    if document.get("manifest_id") != manifest_id or documented_id != dataset_id:
        return None
    return manifest_id


@dataclass
class ResearchLibraryStack:
    """All backend components sharing one orchestrator + job store."""

    repo_root: Path
    registry_path: Path
    engine: ResearchQueryEngine
    orchestrator: YzuOrchestrator
    jobs: JobService
    gateway: ResearchDataGateway
    yzu_api: YzuClusterAPI
    memory: ProcurementMemory
    campaigns: CampaignStore
    campaign_runner: CampaignRunner
    tools: ResearchToolHandlers = field(repr=False, init=False)

    @property
    def agent(self):
        return self.gateway.agent


def create_stack(
    repo_root: str | Path | None = None,
    registry_path: str | Path | None = None,
) -> ResearchLibraryStack:
    root = Path(repo_root or repo_root_from_file(__file__)).resolve()
    from scripts.research_data_mcp.env_loader import load_procurement_env

    load_procurement_env(root)
    registry = Path(registry_path) if registry_path else root / DEFAULT_REGISTRY
    if not registry.is_absolute():
        registry = (root / registry).resolve()

    engine = ResearchQueryEngine(registry, repo_root=root)
    promoter = RegistryPromoter(root, registry)
    flywheel = CollectionFlywheel(root, registry)
    memory = ProcurementMemory(root / "data_lake/procurement_memory/memory.sqlite3")
    campaigns = CampaignStore(root / "data_lake/procurement_memory/campaigns.sqlite3")
    orchestrator = YzuOrchestrator(root, engine=engine)
    orchestrator.registry_promoter = promoter
    orchestrator.collection_flywheel = flywheel
    orchestrator.procurement_memory = memory
    orchestrator.procurement_campaigns = campaigns
    jobs = JobService(orchestrator)
    yzu_api = YzuClusterAPI(root, orchestrator=orchestrator)
    gateway = ResearchDataGateway(
        root,
        registry,
        orchestrator=orchestrator,
        engine=engine,
        yzu_api=yzu_api,
        jobs=jobs,
    )
    yzu_api.agent = gateway.agent
    yzu_api.orchestrator = orchestrator
    campaign_runner = CampaignRunner(gateway, campaigns, memory=memory)
    jobs.set_campaign_runner(campaign_runner)

    def _registration_evidence(result: dict[str, Any] | None, dataset_id: str) -> dict[str, Any] | None:
        """Return proof only after archive and canonical registry read-back agree."""

        if not isinstance(result, dict) or not dataset_id:
            return None
        drive = result.get("drive_finalize") if isinstance(result.get("drive_finalize"), dict) else {}
        manifest_id = str(result.get("output_manifest_id") or result.get("manifest_id") or "")
        promotion = result.get("registry_promotion") or []
        promoted = any(isinstance(row, dict) and row.get("dataset_id") == dataset_id for row in promotion)
        archive = next(
            (
                row
                for row in drive.get("archives") or []
                if isinstance(row, dict) and row.get("ok") and row.get("dataset_id") == dataset_id
            ),
            None,
        )
        if not (drive.get("ok") and manifest_id and promoted and archive and archive.get("remote_path")):
            return None
        document = json.loads(registry.read_text(encoding="utf-8"))
        registry_row = next(
            (row for row in document.get("datasets") or [] if row.get("dataset_id") == dataset_id),
            None,
        )
        remote_path = str((registry_row or {}).get("canonical_remote") or "")
        if not registry_row or remote_path != str(archive.get("remote_path") or ""):
            return None
        readiness = str(registry_row.get("analysis_readiness") or "registered")
        # Instant / query_ready local cards are desk-usable; do not collapse them to
        # a mere "registered" receipt that History will treat as not queryable.
        if readiness in {"instant", "query_ready"}:
            readiness = "query_ready"
        elif readiness not in {"registered", "query_ready"}:
            readiness = "registered"
        execution_spec = result.get("execution_spec") if isinstance(result.get("execution_spec"), dict) else {}
        return {
            "dataset_id": dataset_id,
            # The canonical registry has dataset_id as its durable row identity.
            "registry_id": dataset_id,
            "revision_id": registry_row.get("revision_id"),
            "manifest_id": manifest_id,
            "vault_path": remote_path,
            "archive_verified": True,
            "registry_readback": True,
            "readiness": readiness,
            "title": registry_row.get("name"),
            "source": registry_row.get("source") or registry_row.get("procurement"),
            "lineage_inputs": [execution_spec["input_dataset_id"]] if execution_spec.get("input_dataset_id") else [],
            "rows": result.get("rows"),
            "grain": registry_row.get("grain"),
            "coverage": registry_row.get("coverage"),
        }

    def _on_job_completed(job_id: str, plan: dict, result: dict | None) -> list[dict]:
        job = orchestrator.store.get(job_id)
        campaign_id = str((job.get("request") or {}).get("campaign_id") or "")
        payload = {
            "id": job_id,
            "status": "completed",
            "plan": plan,
            "result": result,
            "request": job.get("request"),
        }
        # Synthesis has a stricter completion contract than procurement: a derived
        # asset is not Library-visible until its Drive copy verifies successfully.
        if str((plan or {}).get("job_type") or "") == "synthesis_execute":
            from scripts.research_data_mcp.drive_first import (
                _stamp_registry_drive_paths,
                compact_ephemeral_path,
                finalize_job_to_drive,
                is_drive_first,
            )

            materialized = (result or {}).get("materialized") or {}
            if not materialized.get("canonical_dir"):
                raise RuntimeError("synthesis execution did not return a materialized output")
            output_id = str(materialized.get("dataset_id") or "")
            manifest_id = _valid_materialization_manifest(root, result, materialized, output_id)
            if not manifest_id:
                raise RuntimeError("synthesis execution did not return a valid output manifest")
            if isinstance(result, dict):
                result["output_manifest_id"] = manifest_id
            if is_drive_first(root):
                finalize = finalize_job_to_drive(
                    root,
                    job_id=job_id,
                    plan=plan or {},
                    result=result if isinstance(result, dict) else {},
                    materialized=materialized,
                    search_goal=str((job.get("request") or {}).get("search_goal") or ""),
                    compact=False,
                )
                if isinstance(result, dict):
                    result["drive_finalize"] = finalize
                if not finalize.get("ok"):
                    raise RuntimeError(finalize.get("error") or "GDrive synthesis archive failed")
            else:
                raise RuntimeError("synthesis execution requires Drive-first verified storage")

            payload["result"] = result
            promoted = promoter.promote_job(payload, campaign_id=campaign_id)
            if not any(row.get("dataset_id") == output_id for row in promoted):
                raise RuntimeError("synthesis output was not promoted into the registry")
            if isinstance(result, dict):
                result["registry_promotion"] = promoted
            _stamp_registry_drive_paths(root, list(finalize.get("registry_updates") or []), plan=plan or {})
            if isinstance(result, dict):
                evidence = _registration_evidence(result, output_id)
                if evidence:
                    result["registration_evidence"] = evidence
            compacted = compact_ephemeral_path(root, str(materialized["canonical_dir"]))
            if isinstance(result, dict):
                result["drive_finalize"]["compacted"] = [compacted]
            return promoted
        doi = str((plan or {}).get("datacite_doi") or "")
        hf_id = str((plan or {}).get("hf_dataset_id") or "")
        search_goal = ""
        if campaign_id:
            try:
                search_goal = str(campaigns.get(campaign_id).get("goal") or "")
            except KeyError:
                pass
        if not search_goal:
            req = job.get("request") or {}
            search_goal = str(req.get("search_goal") or req.get("goal") or req.get("message") or "")

        materialized = (result or {}).get("materialized") or {}
        storage = json.loads((root / "config/yzu_cluster.json").read_text(encoding="utf-8")).get("storage") or {}
        from scripts.research_data_mcp.drive_first import (
            _stamp_registry_drive_paths,
            compact_finalized_archives,
            finalize_job_to_drive,
            is_drive_first,
        )

        # Generic collection previously promoted into the registry and only then
        # attempted archival.  A Drive failure therefore left a false Library
        # asset behind.  Keep staging intact through archive verification and
        # promote only after the archive proof exists.
        job_type = str((plan or {}).get("job_type") or "")
        archive_required = bool(materialized.get("canonical_dir")) or job_type == "scraper_run"
        drive_finalize: dict[str, Any] | None = None
        if is_drive_first(root) and archive_required:
            drive_finalize = finalize_job_to_drive(
                root,
                job_id=job_id,
                plan=plan or {},
                result=result if isinstance(result, dict) else {},
                materialized=materialized,
                search_goal=search_goal,
                compact=False,
                stamp_registry=False,
            )
            if isinstance(result, dict):
                result["drive_finalize"] = drive_finalize
            if not drive_finalize.get("ok"):
                raise RuntimeError(drive_finalize.get("error") or "GDrive partition finalize failed")
            if drive_finalize.get("skipped"):
                raise RuntimeError("Drive-first collection produced no archive targets")

        # Metadata/probe work can complete without materialising a Library asset.
        # In Drive-first mode, a collection with no archivable output remains a
        # completed job, not a promoted dataset.
        output_id = str(materialized.get("dataset_id") or "")
        manifest_id = _valid_materialization_manifest(root, result, materialized, output_id) if output_id else None
        if output_id and not manifest_id:
            # Archive proof without an output manifest is still not canonical
            # Library evidence. Leave the job completed and recoverable.
            promoted = []
        elif is_drive_first(root) and not archive_required:
            promoted = []
        elif hf_id:
            promoted = promoter.promote_huggingface_collect(payload, hf_dataset_id=hf_id, campaign_id=campaign_id)
        elif doi:
            promoted = promoter.promote_datacite_collect(payload, doi=doi, campaign_id=campaign_id)
        else:
            promoted = promoter.promote_job(payload, campaign_id=campaign_id)
        if promoted:
            if isinstance(result, dict):
                result["registry_promotion"] = promoted
                if manifest_id:
                    result["output_manifest_id"] = manifest_id
            if drive_finalize is not None:
                archived_ids = {
                    str(row.get("dataset_id") or "")
                    for row in drive_finalize.get("registry_updates") or []
                    if row.get("dataset_id")
                }
                promoted_ids = {str(row.get("dataset_id") or "") for row in promoted if row.get("dataset_id")}
                expected_id = str(materialized.get("dataset_id") or "")
                if expected_id and expected_id not in promoted_ids:
                    raise RuntimeError("verified output was not promoted under its declared dataset identity")
                if archived_ids and not archived_ids.intersection(promoted_ids):
                    raise RuntimeError("registry promotion does not match the verified archive identity")
                _stamp_registry_drive_paths(
                    root,
                    list(drive_finalize.get("registry_updates") or []),
                    plan=plan or {},
                )
                if isinstance(result, dict) and expected_id:
                    evidence = _registration_evidence(result, expected_id)
                    if evidence:
                        result["registration_evidence"] = evidence
                compacted = compact_finalized_archives(root, drive_finalize, plan=plan or {})
                if isinstance(result, dict):
                    result["drive_finalize"]["compacted"] = compacted
        return promoted

    orchestrator.set_on_job_completed(_on_job_completed)

    def _on_job_post_completed(
        job_id: str,
        plan: dict,
        result: dict | None,
        runtime_state: dict | None,
    ) -> None:
        """Run non-authoritative follow-ups after lifecycle registration.

        Search indexing, flywheel work, campaign updates, and Synthesis thread
        presentation are valuable, but none can invalidate archive + registry
        proof that already created a registered research asset.
        """

        job = orchestrator.store.get(job_id)
        campaign_id = str((job.get("request") or {}).get("campaign_id") or "")
        payload = {
            "id": job_id,
            "status": "completed",
            "plan": plan,
            "result": result,
            "request": job.get("request"),
        }
        promoted = list((result or {}).get("registry_promotion") or [])
        search_goal = str((job.get("request") or {}).get("search_goal") or "")
        if not search_goal and campaign_id:
            try:
                search_goal = str(campaigns.get(campaign_id).get("goal") or "")
            except KeyError:
                pass

        if promoted:
            gateway.reload_registry()
            from scripts.research_data_mcp.semantic_index import invalidate_semantic_index
            from scripts.research_data_mcp.partition_wiring import wire_promoted_to_partition

            invalidate_semantic_index()
            flywheel_result = flywheel.promote_after_collect(
                payload,
                promoted,
                campaign_id=campaign_id,
                search_goal=search_goal,
            )
            wiring = wire_promoted_to_partition(
                root,
                promoted=promoted,
                plan=plan or {},
                search_goal=search_goal,
                registry_path=registry,
            )
            if isinstance(result, dict):
                if wiring.get("wired"):
                    result["partition_wiring"] = wiring
                if flywheel_result.get("curated_added") or flywheel_result.get("locators_added"):
                    result["flywheel"] = flywheel_result

            if str((plan or {}).get("job_type") or "") == "scraper_run":
                from scripts.research_data_mcp.scrape_flywheel import (
                    plan_follow_up_downloads,
                    promote_scrape_job,
                    submit_follow_up_downloads,
                )

                did = str(promoted[0].get("dataset_id") or "")
                reg_doc = json.loads(registry.read_text(encoding="utf-8")) if registry.is_file() else {}
                reg_row = next((row for row in reg_doc.get("datasets") or [] if str(row.get("dataset_id")) == did), None)
                scrape_fw = promote_scrape_job(
                    root,
                    payload,
                    registry_row=reg_row,
                    search_goal=search_goal,
                    follow_downloads=False,
                )
                follow_plans = scrape_fw.get("follow_up_jobs") or []
                if not follow_plans:
                    from scripts.research_data_mcp.scrape_flywheel import load_extract

                    extract = load_extract(root, payload, reg_row)
                    if extract:
                        follow_plans = plan_follow_up_downloads(root, payload, extract, search_goal=search_goal)
                scrape_fw["follow_up_submitted"] = submit_follow_up_downloads(gateway, payload, follow_plans)
                if isinstance(result, dict):
                    result["scrape_flywheel"] = scrape_fw

        # Non Drive-first operation remains a legacy compatibility path. It can
        # enqueue archival work but never upgrades the runtime to registered.
        materialized = (result or {}).get("materialized") or {}
        if not (result or {}).get("drive_finalize"):
            storage = json.loads((root / "config/yzu_cluster.json").read_text(encoding="utf-8")).get("storage") or {}
            from scripts.research_data_mcp.archive_after_job import queue_archive_materialized, queue_auto_archives

            archive_jobs: list[dict] = []
            if materialized.get("canonical_dir"):
                mat_job = queue_archive_materialized(
                    repo_root=root,
                    jobs=jobs,
                    job_id=job_id,
                    materialized=materialized,
                    storage=storage,
                    campaign_id=campaign_id,
                    plan=plan or {},
                )
                if mat_job:
                    archive_jobs.append({"materialized": True, "archive_job": mat_job})
            elif promoted:
                archive_jobs = queue_auto_archives(
                    repo_root=root,
                    jobs=jobs,
                    job_id=job_id,
                    plan=plan,
                    promoted=promoted,
                    registry_path=registry,
                    storage=storage,
                    campaign_id=campaign_id,
                )
            if archive_jobs and isinstance(result, dict):
                result["gdrive_archives"] = archive_jobs

        finished = orchestrator.store.get(job_id)
        finished.update({"status": "completed", "plan": plan, "result": result or {}})
        campaign_runner.on_job_completed(finished, promoted=promoted)
        if str((plan or {}).get("job_type") or "") == "synthesis_execute":
            thread_id = str((plan or {}).get("thread_id") or "")
            if thread_id and isinstance(runtime_state, dict) and runtime_state.get("status") == "registered":
                gateway.synthesis_thread_record_execution(thread_id, orchestrator.get_job(job_id))

    orchestrator.set_on_job_post_completed(_on_job_post_completed)

    def _on_job_failed(job_id: str, plan: dict, error: str) -> None:
        if str((plan or {}).get("job_type") or "") != "synthesis_execute":
            return
        thread_id = str((plan or {}).get("thread_id") or "")
        if thread_id:
            gateway.synthesis_thread_record_execution_failure(thread_id, job_id, error)

    orchestrator.set_on_job_failed(_on_job_failed)
    stack = ResearchLibraryStack(
        repo_root=root,
        registry_path=registry,
        engine=gateway.engine,
        orchestrator=orchestrator,
        jobs=jobs,
        gateway=gateway,
        yzu_api=yzu_api,
        memory=memory,
        campaigns=campaigns,
        campaign_runner=campaign_runner,
    )
    stack.tools = ResearchToolHandlers(stack)
    from scripts.research_data_mcp.desk_runtime import prepare_desk_indexes

    stack.gateway._desk_index_meta = prepare_desk_indexes(root)
    return stack
