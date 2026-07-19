#!/usr/bin/env python3
"""Single wiring point for the research data library backend."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


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

DEFAULT_REGISTRY = "config/research_query_registry.json"


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
            output_id = str(materialized.get("dataset_id") or "")
            if not any(row.get("dataset_id") == output_id for row in promoted):
                raise RuntimeError("synthesis output was not promoted into the registry")
            if isinstance(result, dict):
                result["registry_promotion"] = promoted
            _stamp_registry_drive_paths(root, list(finalize.get("registry_updates") or []), plan=plan or {})
            compacted = compact_ephemeral_path(root, str(materialized["canonical_dir"]))
            if isinstance(result, dict):
                result["drive_finalize"]["compacted"] = [compacted]
            gateway.reload_registry()
            from scripts.research_data_mcp.semantic_index import invalidate_semantic_index

            invalidate_semantic_index()
            from scripts.research_data_mcp.partition_wiring import wire_promoted_to_partition

            wiring = wire_promoted_to_partition(
                root,
                promoted=promoted,
                plan=plan or {},
                search_goal=str((job.get("request") or {}).get("search_goal") or ""),
                registry_path=registry,
            )
            if isinstance(result, dict) and wiring.get("wired"):
                result["partition_wiring"] = wiring
            completed_job = dict(job)
            completed_job.update({"status": "completed", "plan": plan, "result": result})
            gateway.synthesis_thread_record_execution(str(plan.get("thread_id") or ""), completed_job)
            campaign_runner.on_job_completed(completed_job, promoted=promoted)
            return promoted
        doi = str((plan or {}).get("datacite_doi") or "")
        hf_id = str((plan or {}).get("hf_dataset_id") or "")
        if hf_id:
            promoted = promoter.promote_huggingface_collect(payload, hf_dataset_id=hf_id, campaign_id=campaign_id)
        elif doi:
            promoted = promoter.promote_datacite_collect(payload, doi=doi, campaign_id=campaign_id)
        else:
            promoted = promoter.promote_job(payload, campaign_id=campaign_id)
        if promoted:
            gateway.reload_registry()
            from scripts.research_data_mcp.semantic_index import invalidate_semantic_index

            invalidate_semantic_index()
            search_goal = ""
            if campaign_id:
                try:
                    search_goal = str(campaigns.get(campaign_id).get("goal") or "")
                except KeyError:
                    pass
            if not search_goal:
                req = job.get("request") or {}
                search_goal = str(req.get("search_goal") or req.get("goal") or req.get("message") or "")
            flywheel_result = flywheel.promote_after_collect(
                payload,
                promoted,
                campaign_id=campaign_id,
                search_goal=search_goal,
            )
            if str((plan or {}).get("job_type") or "") == "scraper_run":
                from scripts.research_data_mcp.scrape_flywheel import (
                    plan_follow_up_downloads,
                    promote_scrape_job,
                    submit_follow_up_downloads,
                )

                reg_row = None
                if promoted:
                    did = str(promoted[0].get("dataset_id") or "")
                    reg_path = root / "config/research_query_registry.json"
                    if reg_path.is_file() and did:
                        reg_doc = json.loads(reg_path.read_text(encoding="utf-8"))
                        reg_row = next(
                            (r for r in reg_doc.get("datasets") or [] if str(r.get("dataset_id")) == did),
                            None,
                        )
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
                payload = dict(payload)
                payload["scrape_flywheel"] = scrape_fw
            if flywheel_result.get("curated_added") or flywheel_result.get("locators_added"):
                payload = dict(payload)
                payload["flywheel"] = flywheel_result
            materialized = (result or {}).get("materialized") or {}
            storage = json.loads((root / "config/yzu_cluster.json").read_text(encoding="utf-8")).get("storage") or {}
            from scripts.research_data_mcp.drive_first import finalize_job_to_drive, is_drive_first

            archive_jobs: list[dict] = []
            if is_drive_first(root):
                finalize = finalize_job_to_drive(
                    root,
                    job_id=job_id,
                    plan=plan or {},
                    result=result if isinstance(result, dict) else {},
                    promoted=promoted,
                    materialized=materialized,
                    search_goal=search_goal,
                )
                if isinstance(result, dict):
                    result["drive_finalize"] = finalize
                if not finalize.get("ok"):
                    raise RuntimeError(finalize.get("error") or "GDrive partition finalize failed")
                archive_jobs = list(finalize.get("archives") or [])
            else:
                from scripts.research_data_mcp.archive_after_job import (
                    queue_archive_materialized,
                    queue_auto_archives,
                )

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
            if archive_jobs:
                if isinstance(result, dict):
                    result["gdrive_archives"] = archive_jobs
            if promoted:
                from scripts.research_data_mcp.partition_wiring import wire_promoted_to_partition

                wiring = wire_promoted_to_partition(
                    root,
                    promoted=promoted,
                    plan=plan or {},
                    search_goal=search_goal,
                    registry_path=registry,
                )
                if isinstance(result, dict) and wiring.get("wired"):
                    result["partition_wiring"] = wiring
        finished = dict(job)
        finished.update({"status": "completed", "plan": plan, "result": result})
        campaign_runner.on_job_completed(finished, promoted=promoted)
        if str((plan or {}).get("job_type") or "") == "synthesis_execute":
            thread_id = str((plan or {}).get("thread_id") or "")
            if thread_id:
                completed_job = orchestrator.store.get(job_id)
                completed_job["result"] = result if isinstance(result, dict) else {}
                gateway.synthesis_thread_record_execution(thread_id, completed_job)
        return promoted

    orchestrator.set_on_job_completed(_on_job_completed)

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
