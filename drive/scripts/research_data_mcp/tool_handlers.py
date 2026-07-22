#!/usr/bin/env python3
"""Shared tool handlers — single implementation for MCP tools and HTTP extension routes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.research_data_mcp import bigquery_client, datacite_client
from scripts.research_data_mcp.procurement_constants import (
    MCP_TOOL_ACQUIRE,
    MCP_TOOL_CORE,
    MCP_TOOL_LEGACY_NOTE,
    MCP_TOOL_OPS,
    COMPOSER_EXTERNAL_TOOLS_NOTE,
)

if TYPE_CHECKING:
    from scripts.research_data_mcp.bootstrap import ResearchLibraryStack

# Protocol adapter surface — tiered in procurement_constants (full toolbox ≠ this list).
MCP_TOOL_NAMES: list[str] = list(dict.fromkeys([*MCP_TOOL_CORE, *MCP_TOOL_ACQUIRE, *MCP_TOOL_OPS]))


class ResearchToolHandlers:
    """Gateway + extension tools. MCP and HTTP both call these methods."""

    def __init__(self, stack: ResearchLibraryStack) -> None:
        self.stack = stack
        self.gateway = stack.gateway

    def research_library_overview(self) -> dict[str, Any]:
        """Summarize registered datasets by readiness bucket and recommended agent flow."""
        return self.gateway.library_overview()

    def research_list_datasets(
        self,
        q: str = "",
        readiness: str = "",
        access_shape: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        """List or search registered research datasets."""
        return self.gateway.list_datasets(q=q, readiness=readiness, access_shape=access_shape, limit=min(max(limit, 1), 200))

    def research_describe_dataset(self, dataset_id: str) -> dict[str, Any]:
        """Describe one registered dataset (includes access_tier for Composer)."""
        row = self.gateway.describe_dataset(dataset_id)
        from scripts.research_data_mcp.registry_access import access_tier, access_tier_note, local_data_ready

        tier = access_tier(row, repo_root=Path(self.gateway.repo_root))
        return {
            **row,
            "access_tier": tier,
            "access_tier_note": access_tier_note(tier),
            "local_ready": local_data_ready(row, Path(self.gateway.repo_root)),
        }



    def research_analyze_dataset(
        self,
        handle: str,
        question: str = "",
        row_cap: int = 2000,
    ) -> dict[str, Any]:
        """Bounded analysis on collected bytes — column stats + optional LLM interpretation."""
        from scripts.research_data_mcp.composer_followthrough_analysis import run_bounded_analyze

        return run_bounded_analyze(
            self,
            query=question,
            handle=handle,
            row_cap=min(max(int(row_cap), 10), 10_000),
        )

    def research_synthesis_list_profiles(self) -> dict[str, Any]:
        """List configured multi-source synthesis profiles and latest run summaries."""
        return self.gateway.synthesis_list_profiles()

    def research_synthesis_run(
        self,
        profile_id: str,
        preview_limit: int = 50,
        gap_limit: int = 100,
    ) -> dict[str, Any]:
        """Run a synthesis profile (e.g. skynet_etherscan_stablecoin) and write artifacts under data_lake/synthesis/."""
        return self.gateway.synthesis_run(
            profile_id,
            preview_limit=min(max(int(preview_limit), 1), 200),
            gap_limit=min(max(int(gap_limit), 1), 500),
        )

    def research_synthesis_pair(self, left_dataset_id: str, right_dataset_id: str) -> dict[str, Any]:
        """Compare two registry datasets for join-key overlap and synthesis viability (metadata + recommendations)."""
        return self.gateway.synthesis_pair(left_dataset_id, right_dataset_id)

    def research_synthesis_propose_state(
        self,
        thread_id: str,
        proposal_id: str,
        title: str,
        summary: str,
        operations: list[dict[str, Any]],
        reason: str = "",
        impact: list[str] | None = None,
        node_id: str = "",
        execution_spec: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Propose a validated Synthesis-state change for researcher review; never applies it."""
        thread = self.gateway.synthesis_thread_propose_state(
            thread_id,
            proposal_id=proposal_id,
            title=title,
            summary=summary,
            operations=operations,
            reason=reason,
            impact=impact,
            node_id=node_id,
            execution_spec=execution_spec,
        )
        return {
            "thread_id": thread.get("id"),
            "synthesis_proposal": (thread.get("state") or {}).get("proposal"),
            "review_required": True,
            "execution_recorded": False,
            "execution_preflight": ((thread.get("state") or {}).get("proposal") or {}).get("execution_preflight"),
        }

    def research_synthesis_preflight_spec(self, execution_spec: dict[str, Any]) -> dict[str, Any]:
        """Dry-run validate an execution_spec (datasets/transforms/columns). Never executes."""
        from scripts.research_data_mcp.synthesis_executor import preflight_execution_spec

        return preflight_execution_spec(self.gateway.repo_root, dict(execution_spec or {}))

    def research_synthesis_discover_handoff(self, thread_id: str) -> dict[str, Any]:
        """Return held/missing evidence + resolvable collect_intents. Never submits jobs."""
        handoff = self.gateway.synthesis_thread_discover_handoff(thread_id)
        handoff["review_required"] = True
        handoff["agent_may_collect"] = True
        handoff["agent_may_approve_synthesis"] = False
        return handoff

    def research_synthesis_collect_missing(
        self,
        thread_id: str,
        evidence_ids: list[str] | None = None,
        auto_approve_safe: bool = True,
        limit: int = 8,
    ) -> dict[str, Any]:
        """Submit Discover collect jobs for resolvable missing-evidence intents only."""
        return self.gateway.synthesis_thread_collect_missing(
            thread_id,
            evidence_ids=list(evidence_ids or []),
            auto_approve_safe=bool(auto_approve_safe),
            limit=int(limit or 8),
        )

    def research_synthesis_materialisation(self, thread_id: str) -> dict[str, Any]:
        """Honest materialisation view for a synthesis thread (never invents output)."""
        return self.gateway.synthesis_thread_materialisation(thread_id)

    def research_synthesis_submit_execution(self, thread_id: str) -> dict[str, Any]:
        """Queue accepted execution_spec as pending_approval. Agent cannot approve it."""
        out = self.gateway.synthesis_thread_submit_execution(thread_id)
        job = out.get("job") if isinstance(out, dict) else None
        return {
            **(out if isinstance(out, dict) else {"result": out}),
            "review_required": True,
            "agent_may_approve_synthesis": False,
            "note": "Submitted for researcher desk approval only — Composer cannot approve synthesis_execute.",
            "job_id": (job or {}).get("id") if isinstance(job, dict) else None,
            "job_status": (job or {}).get("status") if isinstance(job, dict) else None,
        }

    def research_discover_create_intent(
        self, research_need: str, title: str = "", candidate: dict[str, Any] | None = None, session_id: str = ""
    ) -> dict[str, Any]:
        """Create a durable Discover sourcing intent; this never starts collection."""
        return self.gateway.discover_intent_create(research_need=research_need, title=title, candidate=candidate, session_id=session_id)

    def research_discover_get_intent(self, intent_id: str) -> dict[str, Any]:
        """Read a Discover sourcing intent and its current reviewed route state."""
        return self.gateway.discover_intent_get(intent_id)

    def research_discover_propose_intent(self, intent_id: str, proposal: dict[str, Any]) -> dict[str, Any]:
        """Persist candidate acquisition routes for explicit researcher review; never collect."""
        return self.gateway.discover_intent_set_proposal(intent_id, proposal)

    def research_discover_source_search(
        self,
        query: str = "",
        limit: int = 24,
        live: bool = False,
        semantic: bool = False,
    ) -> dict[str, Any]:
        """Explore known external sources/providers/connectors — not registry holdings.

        Returns source_id / access_mode / connector_id rows (Discover Explore catalog).
        """
        return self.gateway.discover_source_search(
            query,
            limit=min(max(int(limit), 1), 100),
            live=bool(live),
            semantic=bool(semantic),
        )

    def research_discover_source_preview(
        self,
        source_id: str = "",
        connector_id: str = "",
        candidate_key: str = "",
        url: str = "",
        doi: str = "",
        dataset_id: str = "",
        name: str = "",
        limit: int = 5,
    ) -> dict[str, Any]:
        """Bounded source preview (ready/schema_only/access_required/failed)."""
        return self.gateway.discover_source_preview(
            source_id=source_id,
            connector_id=connector_id,
            candidate_key=candidate_key,
            url=url,
            doi=doi,
            dataset_id=dataset_id,
            name=name,
            limit=limit,
        )

    def research_discover_history(self, limit: int = 50, kind: str = "", session_id: str = "") -> dict[str, Any]:
        """Researcher-facing Discover history (intents, subscriptions, linked runs)."""
        return self.gateway.discover_history(limit=limit, kind=kind, session_id=session_id)

    def research_discover_create_refresh_subscription(
        self,
        cadence: str = "manual",
        destination: str = "",
        intent_id: str = "",
        source_id: str = "",
        connector_id: str = "",
        candidate_key: str = "",
        enabled: bool = True,
        requested_schedule: str = "",
        schedule_note: str = "",
        timezone: str = "Asia/Taipei",
        cron: str = "",
    ) -> dict[str, Any]:
        """Register a Discover refresh subscription in History.

        Cadence is one of manual|daily|weekly|monthly. For "every Monday 10:00",
        pass cadence=weekly + requested_schedule (faculty wording). Optional
        timezone/cron populate schedule_spec. When cron is present the Discover
        refresh runner arms next_run_at (execution_mode=scheduled).
        """
        explicit = {"timezone": timezone, "cron": cron, "requested_schedule": requested_schedule} if cron else None
        return self.gateway.discover_refresh_create(
            cadence=cadence,
            destination=destination,
            intent_id=intent_id,
            source_id=source_id,
            connector_id=connector_id,
            candidate_key=candidate_key,
            enabled=enabled,
            requested_schedule=requested_schedule,
            schedule_note=schedule_note,
            timezone=timezone,
            schedule_spec=explicit,
        )

    def research_discover_pause_refresh_subscription(self, subscription_id: str) -> dict[str, Any]:
        """Pause a Discover refresh subscription (History remains)."""
        return self.gateway.discover_refresh_pause(subscription_id)

    def research_discover_resume_refresh_subscription(self, subscription_id: str) -> dict[str, Any]:
        """Resume a paused Discover refresh subscription."""
        return self.gateway.discover_refresh_resume(subscription_id)

    def research_discover_stop_refresh_subscription(self, subscription_id: str) -> dict[str, Any]:
        """Stop a Discover refresh subscription permanently."""
        return self.gateway.discover_refresh_stop(subscription_id)

    def research_discover_tick_refresh_subscriptions(
        self,
        limit: int = 10,
        force_subscription_id: str = "",
        force: bool = False,
        auto_approve_safe: bool = True,
    ) -> dict[str, Any]:
        """Fire due Discover refresh subscriptions (or force one) into collection jobs."""
        return self.gateway.discover_refresh_tick(
            limit=limit,
            force_subscription_id=force_subscription_id,
            force=force,
            auto_approve_safe=auto_approve_safe,
        )

    def research_collection_hydrate(
        self,
        partition_id: str = "",
        shard: str = "",
        scope: str = "auto",
        sync: bool = True,
        message: str = "",
    ) -> dict[str, Any]:
        """Hydrate a vault partition or DataCite shard from canonical Drive to local desk."""
        from scripts.research_data_mcp.collection_hydrate import build_hydrate_plan, execute_hydrate
        from scripts.research_data_mcp.composer_followthrough_analysis import try_sync_hydrate_partition

        repo_root = Path(self.gateway.repo_root).resolve()
        if sync and partition_id:
            return try_sync_hydrate_partition(
                self,
                partition_id=partition_id,
                message=message or partition_id,
            )
        plan = build_hydrate_plan(
            repo_root,
            partition_id=partition_id,
            shard=shard,
            scope=scope,
            message=message,
        )
        if plan.get("skip_reason"):
            return {"skipped": True, "reason": plan["skip_reason"], "plan": plan}
        if sync:
            try:
                result = execute_hydrate(repo_root, plan)
                return {"plan": plan, "result": result}
            except Exception as exc:  # noqa: BLE001
                return {"plan": plan, "error": str(exc)[:400]}
        return {"plan": plan, "launchable": bool(plan.get("launchable"))}

    def research_quant_brief(
        self,
        country: str = "IDN",
        mode: str = "summary",
        evidence_pack: str = "",
        llm: str = "skip",
    ) -> dict[str, Any]:
        """Quant-AI bridge — fused panel summary, walk-forward evidence, or LLM decision brief."""
        from scripts.research_data_mcp.quant_ai_bridge import run_quant_brief

        return run_quant_brief(
            Path(self.gateway.repo_root),
            country=country,
            mode=mode,
            evidence_pack=evidence_pack,
            llm=llm,
        )

    def research_web_discover(
        self,
        query: str,
        max_results: int = 5,
        tavily_live: bool = True,
    ) -> dict[str, Any]:
        """Open-web discovery (Tavily, Zenodo, OpenAlex, DuckDuckGo) — use after local index_miss."""
        from scripts.research_data_mcp.web_search import discover_sources

        return discover_sources(
            self.gateway.repo_root,
            query,
            max_results=min(max(max_results, 1), 12),
            tavily_live=tavily_live,
        )

    def research_query_dataset(self, dataset_id: str, params_json: str = "{}") -> dict[str, Any]:
        """Query a registered dataset. Pass filters as JSON."""
        return self.gateway.query_dataset(dataset_id, self.gateway.parse_params_json(params_json))

    def research_plan_sources(self, q: str, limit: int = 25) -> dict[str, Any]:
        """Turn a research question into ranked source/dataset candidates."""
        return self.gateway.plan_sources(q, limit=min(max(limit, 1), 100))

    def research_search_catalog(
        self,
        q: str = "",
        source: str = "",
        domain: str = "",
        promotion_tier: str = "",
        limit: int = 25,
    ) -> dict[str, Any]:
        """Search the curated external dataset metadata index."""
        return self.gateway.search_catalog(q=q, source=source, domain=domain, promotion_tier=promotion_tier, limit=limit)

    def research_ops_status(self, lane: str = "") -> dict[str, Any]:
        """Combined collection-queue and DataCite harvest lane status."""
        return self.gateway.ops_status(lane=lane)

    def collection_queue_status(self) -> dict[str, Any]:
        """Status of the local data collection queue."""
        return self.gateway.query_dataset("collection_queue_status")

    def collection_status(self) -> dict[str, Any]:
        """Inventory summary: what we have on disk vs canonical Drive (from collection_dictionary)."""
        if os.getenv("RESEARCH_MCP_VAULT_PRIMED", "").strip().lower() in {"1", "true", "yes"}:
            return {
                "blocked": True,
                "reason": "vault_brief_preloaded",
                "message": (
                    "Vault inventory is already loaded in this chat. Answer from that context; "
                    "use research_query_dataset or research_describe_dataset for one dataset."
                ),
            }
        from scripts.research_data_mcp.collection_hydrate import collection_status_summary

        return collection_status_summary(self.gateway.repo_root)

    def datacite_local_harvest_status(self, lane: str = "") -> dict[str, Any]:
        """Checkpoint status for local DataCite harvest lanes."""
        return self.gateway.query_dataset("datacite_local_harvest_status", {"lane": lane} if lane else {})

    def research_procurement_catalog(self, q: str = "", limit: int = 50) -> dict[str, Any]:
        """Browse procureable assets: registry, queue tasks, pipelines, connectors."""
        return self.gateway.procurement_catalog(q=q, limit=min(max(limit, 1), 200))

    def research_advise_datasets(
        self,
        goal: str,
        current_dataset_id: str = "",
        current_task_id: str = "",
        limit: int = 5,
    ) -> dict[str, Any]:
        """Librarian guidance on dataset fit and alternatives."""
        return self.gateway.advise_datasets(
            goal,
            current_dataset_id=current_dataset_id,
            current_task_id=current_task_id,
            limit=min(max(limit, 1), 10),
        )



    def yzu_cluster_status(self, live: bool = False) -> dict[str, Any]:
        """YZU cluster health: disk, progress, job queue stats."""
        return self.gateway.cluster_status(live=live)

    def yzu_list_acquisitions(self, live: bool = False) -> dict[str, Any]:
        """Live acquisition tiles."""
        return self.gateway.list_acquisitions(live=live)

    def yzu_cluster_components(self) -> dict[str, Any]:
        """Wired worker pools, pipelines, job types, schedules."""
        return self.gateway.cluster_components()

    def yzu_list_queue_tasks(self, runnable_only: bool = True) -> dict[str, Any]:
        """Collection queue tasks from config/data_collection_queue.json."""
        return self.gateway.list_queue_tasks(runnable_only=runnable_only)

    def yzu_submit_job(self, plan_json: str, title: str = "MCP job", auto_approve: bool = False) -> dict[str, Any]:
        """Submit a YZU orchestrator job (pending only — Composer cannot auto-approve execution)."""
        plan = self.gateway.parse_params_json(plan_json)
        if auto_approve:
            raise PermissionError("Collection/schedule execution approval requires researcher confirmation in the desk UI")
        return self.gateway.submit_yzu_job(plan, title=title, auto_approve=False)

    def yzu_approve_job(self, job_id: str) -> dict[str, Any]:
        """Disabled for Composer: collection approval requires researcher confirmation in the desk UI."""
        raise PermissionError("Collection approval requires researcher confirmation in the desk UI")

    def yzu_run_schedule(self, schedule_id: str) -> dict[str, Any]:
        """Disabled for Composer: schedule execution requires researcher confirmation in the desk UI."""
        raise PermissionError("Schedule execution requires researcher confirmation in the desk UI")

    def yzu_cancel_job(self, job_id: str) -> dict[str, Any]:
        """Cancel a pending or queued YZU job."""
        return self.gateway.cancel_yzu_job(job_id)

    def yzu_get_job(self, job_id: str) -> dict[str, Any]:
        """Get one YZU job with plan, result, and events."""
        return self.gateway.get_yzu_job(job_id)

    def yzu_list_jobs(self, limit: int = 30, status: str = "") -> dict[str, Any]:
        """List YZU orchestrator jobs."""
        return self.gateway.list_yzu_jobs(limit=limit, status=status)

    def yzu_archive_to_gdrive(
        self,
        local_path: str,
        remote_suffix: str = "",
        verify: bool = True,
        auto_approve: bool = False,
    ) -> dict[str, Any]:
        """Prepare a GDrive archive job; researcher approval remains outside MCP."""
        if auto_approve:
            raise PermissionError("Archive approval requires researcher confirmation in the desk UI")
        return self.gateway.archive_to_gdrive(
            local_path,
            remote_suffix=remote_suffix,
            verify=verify,
            auto_approve=False,
        )

    def procurement_probe_public_source(self, url: str, name: str = "") -> dict[str, Any]:
        """Inspect a public source and save a connector candidate."""
        return self.gateway.probe_source(url, name)

    def procurement_list_connectors(self, limit: int = 50) -> dict[str, Any]:
        """List saved procurement connectors."""
        return self.gateway.list_connectors(limit)

    def procurement_approve_connector(self, connector_id: str) -> dict[str, Any]:
        """Disabled for Composer: connector approval requires researcher confirmation in the desk UI."""
        raise PermissionError("Connector approval requires researcher confirmation in the desk UI")

    def procurement_prepare_collection(self, connector_id: str, limit: int = 200) -> dict[str, Any]:
        """Create a collection plan from an approved connector (plan only)."""
        return self.gateway.prepare_collection(connector_id, limit=min(max(limit, 1), 2000))

    def procurement_submit_collection_job(self, connector_id: str, limit: int = 200) -> dict[str, Any]:
        """Create a pending collection job from an approved connector."""
        return self.gateway.submit_collection_job(connector_id, limit=min(max(limit, 1), 2000))

    def procurement_list_jobs(self, limit: int = 30) -> dict[str, Any]:
        """List procurement/collection jobs."""
        return self.gateway.list_jobs(limit)

    def procurement_get_job(self, job_id: str) -> dict[str, Any]:
        """Get one procurement job."""
        return self.gateway.get_job(job_id)

    def procurement_approve_job(self, job_id: str) -> dict[str, Any]:
        """Disabled for Composer: collection approval requires researcher confirmation in the desk UI."""
        raise PermissionError("Collection approval requires researcher confirmation in the desk UI")

    def procurement_cancel_job(self, job_id: str) -> dict[str, Any]:
        """Cancel a pending or queued collection job."""
        return self.gateway.cancel_job(job_id)

    def datacite_search(self, query: str = "", created: str = "", cursor: str = "1", page_size: int = 25) -> dict[str, Any]:
        """Search DataCite dataset metadata with bounded cursor pagination."""
        return datacite_client.search(query=query, created=created, cursor=cursor, page_size=page_size)

    def datacite_get(self, doi: str) -> dict[str, Any]:
        """Get one DataCite record by DOI."""
        return datacite_client.get_doi(doi)

    def datacite_resolve_repository(
        self,
        doi: str,
        max_file_bytes: int = 50_000_000,
    ) -> dict[str, Any]:
        """Resolve a DataCite DOI to downloadable repository files (Zenodo, etc.)."""
        return self.gateway.datacite_resolve_repository(doi, max_file_bytes=max_file_bytes)

    def datacite_search_and_resolve(
        self,
        query: str,
        created: str = "",
        max_file_bytes: int = 50_000_000,
    ) -> dict[str, Any]:
        """Search DataCite and resolve the first hit to repository download URLs."""
        return self.gateway.datacite_search_and_resolve(
            query,
            created=created,
            max_file_bytes=max_file_bytes,
        )

    def datacite_collect_doi(
        self,
        doi: str,
        file_index: int = 0,
        campaign_id: str = "",
        auto_execute: bool = True,
        max_file_bytes: int = 50_000_000,
    ) -> dict[str, Any]:
        """Agent path: resolve DOI, collect files via http_manifest, return campaign + artifacts."""
        return self.gateway.collect_datacite_doi(
            doi,
            file_index=file_index,
            campaign_id=campaign_id or None,
            auto_execute=auto_execute,
            max_file_bytes=max_file_bytes,
        )

    def research_discover_search(
        self,
        query: str,
        email: str = "",
        limit: int = 12,
        live: bool = False,
        include_lab: bool = True,
    ) -> dict[str, Any]:
        """Discover Explore catalog first (source_id / access_mode), optional lab registry supplement.

        Prefer this (or research_discover_source_search) when faculty mean Discover sources.
        Use research_unified_search for vault / HF / DataCite holdings.
        """
        lim = min(max(int(limit), 1), 100)
        catalog = self.gateway.discover_source_search(
            query,
            limit=lim,
            live=bool(live),
        )
        source_rows = list(catalog.get("results") or [])
        sections: list[dict] = []
        if source_rows:
            sections.append(
                {
                    "id": "discover_sources",
                    "label": "Discover catalog",
                    "rows": source_rows,
                }
            )
        lab_total = 0
        if include_lab and len(source_rows) < max(3, lim // 2):
            lab = self.gateway.discover_search(query, email=email, limit=lim)
            for sec in lab.get("sections") or []:
                if not isinstance(sec, dict):
                    continue
                rows = list(sec.get("rows") or [])
                if not rows:
                    continue
                lab_total += len(rows)
                sections.append(
                    {
                        "id": "lab_registry",
                        "label": "Lab registry (supplement)",
                        "rows": rows,
                    }
                )
        return {
            "query": query,
            "result_kind": "discover_sources",
            "search_mode": catalog.get("search_mode") or ("live" if live else "catalog"),
            "sections": sections,
            "results": source_rows,
            "catalog_total": len(source_rows),
            "lab_total": lab_total,
            "total": len(source_rows) + lab_total,
            "index_miss": not source_rows and lab_total == 0,
        }

    def research_faculty_profile(self, email: str = "", slug: str = "") -> dict[str, Any]:
        """Faculty research profile — stacks, scopes, starter prompts for procurement routing."""
        return self.gateway.faculty_profile(email=email, slug=slug)

    def research_mcp_stack_status(self) -> dict[str, Any]:
        """Audit procurement MCP toolbox health — registry, query plane, tool tiers, cluster."""
        from scripts.research_data_mcp.mcp_stack_audit import audit_stack

        return audit_stack(self.gateway)

    def research_platform_consolidated(self, live: bool = False) -> dict[str, Any]:
        """Desk capability snapshot — catalogue, entitlements, instant readiness, sourcing gaps.

        Call before recommending collection when licensed US/institutional data may be pending.
        Use live=true for on-disk path probe; default uses cached audit (faster).
        """
        from scripts.research_data_mcp.consolidated_state import composer_procurement_snapshot

        full = self.gateway.consolidated_state(live=bool(live))
        return composer_procurement_snapshot(full)

    def research_unified_search(
        self,
        query: str,
        limit: int = 12,
        email: str = "",
        include_hf: bool = True,
        include_datacite: bool = True,
        resolve_datacite: bool = True,
        max_file_bytes: int = 50_000_000,
    ) -> dict[str, Any]:
        """Unified search across local registry, catalog, DataCite, and Hugging Face.

        When email is set, merges profile-aware discover rows and faculty hints.
        """
        return self.gateway.unified_search_with_profile(
            query,
            email=str(email or "").strip(),
            limit=limit,
            include_hf=include_hf,
            include_datacite=include_datacite,
            resolve_datacite=resolve_datacite,
            max_file_bytes=max_file_bytes,
        )

    def research_dataset_card(self, ref: str) -> dict[str, Any]:
        """HF-style dataset card for a campaign, registry id, or DOI handle."""
        return self.gateway.get_dataset_card(ref)

    def research_open_dataset(self, handle: str, load: str = "auto", preview_limit: int = 5) -> dict[str, Any]:
        """Open a procured dataset — paths, preview, optional pandas sample."""
        return self.gateway.open_dataset(handle, load=load, preview_limit=preview_limit)

    def research_list_pins(self, limit: int = 50) -> dict[str, Any]:
        """List pinned dataset handles with checksums."""
        return self.gateway.list_dataset_pins(limit=limit)

    def research_pin_dataset(
        self,
        handle: str,
        campaign_id: str = "",
        file_path: str = "",
        checksum: str = "",
    ) -> dict[str, Any]:
        """Pin a dataset handle to a campaign and file path."""
        return self.gateway.pin_dataset(handle, campaign_id=campaign_id, file_path=file_path, checksum=checksum)

    def research_procure_chat(self, message: str, session_id: str = "", user_email: str = "") -> dict[str, Any]:
        """Multi-turn library chat: search, procure, preview, analyze (bounded samples), status."""
        email = str(user_email or "").strip() or None
        return self.gateway.procurement_chat(message, session_id=session_id or None, user_email=email)

    def research_procure_chat_session(self, session_id: str) -> dict[str, Any]:
        """Load procurement chat session history and candidate state."""
        return self.gateway.procurement_chat_session(session_id)

    def research_procure_resume_campaign(self, campaign_id: str, force_execute: bool = False) -> dict[str, Any]:
        """Resume a stalled magic-procure campaign (probe → collect phases)."""
        return self.gateway.resume_campaign(campaign_id, force_execute=force_execute)

    def research_procure_campaign_artifacts(self, campaign_id: str) -> dict[str, Any]:
        """List downloadable artifacts for a completed procurement campaign."""
        return self.gateway.list_campaign_artifacts(campaign_id)

    def research_procure_approve_collect(self, campaign_id: str, recommendation_index: int = 0) -> dict[str, Any]:
        """Disabled for Composer: collection approval requires researcher confirmation in the desk UI."""
        raise PermissionError("Collection approval requires researcher confirmation in the desk UI")

    def huggingface_search(self, query: str, limit: int = 8) -> dict[str, Any]:
        """Cross-reference Hugging Face Hub datasets (load via HF, not byte proxy)."""
        return self.gateway.huggingface_search(query, limit=limit)

    def huggingface_collect_dataset(
        self,
        dataset_id: str,
        split: str = "train",
        auto_execute: bool = False,
    ) -> dict[str, Any]:
        """Prepare an HF collection job; approval and execution remain in the desk UI."""
        return self.gateway.collect_huggingface_dataset(
            dataset_id,
            split=split,
            auto_execute=False,
        )

    def datacite_scope(self, created: str) -> dict[str, Any]:
        """Count DataCite dataset records for a year scope."""
        return datacite_client.scope(created)

    def datacite_backfill_spec(self, created: str, workers: int = 1) -> dict[str, Any]:
        """Prepare a DataCite backfill specification (does not execute)."""
        return datacite_client.backfill_spec(created, workers=workers)

    def bigquery_status(self, project: str = "", location: str = "US") -> dict[str, Any]:
        """Report BigQuery dependency and credential readiness."""
        return bigquery_client.status(project=project, location=location)

    def bigquery_list_datasets(self, project: str = "", location: str = "US", limit: int = 100) -> dict[str, Any]:
        """List datasets visible to the configured BigQuery identity."""
        return bigquery_client.list_datasets(project=project, location=location, limit=limit)

    def bigquery_list_tables(self, dataset: str, project: str = "", location: str = "US", limit: int = 100) -> dict[str, Any]:
        """List tables in one BigQuery dataset."""
        return bigquery_client.list_tables(dataset, project=project, location=location, limit=limit)

    def bigquery_table_schema(self, table: str, project: str = "", location: str = "US") -> dict[str, Any]:
        """Inspect BigQuery table metadata and schema without reading rows."""
        return bigquery_client.table_schema(table, project=project, location=location)

    def bigquery_dry_run(
        self,
        sql: str,
        project: str = "",
        location: str = "US",
        max_bytes_billed: int = bigquery_client.DEFAULT_MAX_BYTES,
    ) -> dict[str, Any]:
        """Estimate bytes for a read-only SQL query without executing it."""
        return bigquery_client.dry_run_query(sql, project=project, location=location, max_bytes_billed=max_bytes_billed)

    def bigquery_read_query(
        self,
        sql: str,
        project: str = "",
        location: str = "US",
        max_bytes_billed: int = bigquery_client.DEFAULT_MAX_BYTES,
        max_rows: int = 1000,
        confirm: str = "",
    ) -> dict[str, Any]:
        """Execute bounded read-only BigQuery SQL after dry-run and explicit confirmation."""
        return bigquery_client.read_query(
            sql,
            project=project,
            location=location,
            max_bytes_billed=max_bytes_billed,
            max_rows=max_rows,
            confirm=confirm,
        )

    def tool_catalog(self) -> dict[str, Any]:
        """List registered MCP/HTTP extension tools by tier."""
        return {
            "mcp_definition": "data procurement toolbox (protocol adapter is one plug)",
            "orchestrator": "Composer (Cursor) — not research_procure_chat or legacy LLM helpers",
            "tools": MCP_TOOL_NAMES,
            "count": len(MCP_TOOL_NAMES),
            "tiers": {
                "core": list(MCP_TOOL_CORE),
                "acquire": list(MCP_TOOL_ACQUIRE),
                "ops": list(MCP_TOOL_OPS),
            },
            "start_here": "research_platform_consolidated",
            "playbook": (
                "1. research_platform_consolidated — desk snapshot (instant vs pending, entitlement gaps)\n"
                "2. research_discover_search / research_discover_source_search — Discover Explore catalog (source_id)\n   research_unified_search — vault + DataCite + HuggingFace\n"
                "3. research_describe_dataset + research_query_dataset when access_tier is query_instant (auto-hydrates GDrive)\n"
                "4. If miss: datacite_collect_doi or huggingface_collect_dataset → vault + registry flywheel\n"
                "5. Else: research_web_discover → procurement_probe_public_source → yzu_submit_job"
            ),
            "prefer": [
                "research_platform_consolidated() at session start or before licensed-data collects",
                "research_discover_search(query) or research_discover_source_search(query) for Discover Explore sources (source_id/access_mode)",
                "research_unified_search(query) for vault / HF / DataCite holdings",
                "research_query_dataset when access_tier is query_instant (hydrates from GDrive if needed)",
                "huggingface_collect_dataset(org/name) after HF search hit — same flywheel as datacite_collect_doi",
                "datacite_collect_doi(doi) for DOI procured datasets",
                "research_web_discover after index_miss",
                "procurement_probe_public_source → yzu_submit_job(plan)",
            ],
            "legacy_note": MCP_TOOL_LEGACY_NOTE,
            "composer_external": COMPOSER_EXTERNAL_TOOLS_NOTE,
        }
