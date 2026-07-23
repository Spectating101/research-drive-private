#!/usr/bin/env python3
"""Campaign-only acquisition resume/approve — not an HTTP or chat brain.

Prefer:
  - Desk: POST /library/chat (Cursor Composer + MCP)
  - MCP: research_discover_search → procurement_probe_public_source → yzu_submit_job

Used internally by campaign_runner for resume + approve_collect on existing campaigns.
"""

from __future__ import annotations

import time
from typing import Any

from scripts.research_data_mcp.domain_packs import load_domain_packs, match_domain_packs, pack_discovery_hints
from scripts.research_data_mcp.governance import ProcurementBudget, allow_auto_probe, load_governance
from scripts.research_data_mcp.magic_config import (
    is_trusted_plan,
    load_magic_config,
    should_auto_execute,
    wants_discovery,
)
from scripts.research_data_mcp.probe_analyst import ProbeAnalyst
from scripts.research_data_mcp.research_planner import ResearchPlanner, is_index_miss
from scripts.research_data_mcp.semantic_index import get_semantic_index
from scripts.research_data_mcp.storage_policy import load_storage_policy
from scripts.research_data_mcp.web_search import discover_with_catalog


class MagicProcurement:
    def __init__(self, gateway: Any, *, memory: Any = None, campaigns: Any = None) -> None:
        self.gateway = gateway
        self.repo_root = gateway.repo_root
        self.config = load_magic_config(self.repo_root)
        self.governance = load_governance(self.repo_root)
        self.planner = gateway.planner
        self.research_planner = ResearchPlanner(gateway)
        _executor = getattr(gateway.orchestrator, "executor", None)
        _procurement = getattr(_executor, "procurement", None) if _executor else None
        self.probe_analyst = ProbeAnalyst(procurement=_procurement)
        self.memory = memory
        self.campaigns = campaigns
        cache_cfg = self.config.get("cache") or {}
        self.semantic = get_semantic_index(gateway, ttl_hours=float(cache_cfg.get("semantic_ttl_hours", 168)))
        self.domain_packs = load_domain_packs(self.repo_root)

    def resume(self, campaign_id: str, *, force_execute: bool = False) -> dict[str, Any]:
        if not self.campaigns:
            raise ValueError("campaign store not configured")
        campaign = self.campaigns.get(campaign_id)
        if campaign.get("phase") in {"ready", "failed"}:
            return {"resumed": False, "campaign": campaign, "reason": "terminal"}
        return self.procure(
            campaign["goal"],
            {
                "resume": True,
                "campaign_id": campaign_id,
                "force_execute": force_execute,
                "saved_payload": campaign.get("payload") or {},
            },
        )

    def procure(self, message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        message = message.strip()
        if not message:
            raise ValueError("message is required")
        context = dict(context or {})
        budget = ProcurementBudget(self.governance)
        force_execute = bool(context.get("force_execute"))
        research_cfg = self.config.get("research") or {}
        discovery_cfg = self.config.get("discovery") or {}

        campaign = None
        datacite_resolution: dict[str, Any] | None = None
        if self.campaigns and context.get("resume") and context.get("campaign_id"):
            campaign = self.campaigns.get(str(context["campaign_id"]))
        elif self.campaigns:
            if context.get("campaign_id"):
                try:
                    campaign = self.campaigns.get(str(context["campaign_id"]))
                except KeyError:
                    campaign = self.campaigns.create(message, {"context": context})
            else:
                campaign = self.campaigns.create(message, {"context": context})

        if self.planner.wants_datacite_collect(message, context):
            try:
                datacite_resolution = self.planner.plan_datacite_collect(message, context)
            except Exception as exc:
                datacite_resolution = {"error": str(exc)}
                if context.get("doi") or context.get("add_to_collection"):
                    raise

        goal_message = message
        force_research = bool(context.get("force_research"))
        catalog_fast_plan: dict[str, Any] | None = None
        if not (datacite_resolution and datacite_resolution.get("launchable")):
            skip_catalog_fast = force_research
            if not skip_catalog_fast:
                from scripts.research_data_mcp.procurement_fast import local_search

                local = local_search(self.gateway, goal_message, limit=4)
                if local.get("index_miss") or local.get("weak_match"):
                    skip_catalog_fast = True
            if not skip_catalog_fast:
                from scripts.research_data_mcp.procurement_fast import catalog_plan_first
                catalog_fast_plan = catalog_plan_first(self.planner, goal_message, context)
        catalog_fast = bool(catalog_fast_plan and catalog_fast_plan.get("launchable"))

        phase = "index"
        discovery: dict[str, Any] = {"enabled": False, "results": []}
        research_plan: dict[str, Any] | None = None
        recommendations: list[dict[str, Any]] = []
        probes: list[dict[str, Any]] = []
        probe_jobs: list[dict[str, Any]] = []
        collect_jobs: list[dict[str, Any]] = []
        if catalog_fast:
            semantic_hits = []
            semantic_confidence = "high"
        else:
            semantic_hits = self.semantic.search(goal_message, limit=6)
            semantic_confidence = self.semantic.confidence(
                goal_message, semantic_hits[0] if semantic_hits else None
            )
        pack_hints = pack_discovery_hints(match_domain_packs(message, self.domain_packs))

        memory_hint = None
        saved = context.get("saved_payload") or {}
        if context.get("resume") and saved.get("research_plan"):
            research_plan = saved.get("research_plan")
            recommendations = list(saved.get("recommendations") or [])
            probes = []
            probe_jobs = []
            phase = str(campaign.get("phase") if campaign else "research")
        if self.memory and not context.get("force_research") and research_plan is None:
            memory_hint = self.memory.cached_verdict(message)

        t0 = time.time()
        advice = None
        if catalog_fast:
            advice = {
                "verdict": "good_fit",
                "message": f"Catalog match: {catalog_fast_plan.get('title', 'collect plan')}",
                "recommended": [],
                "not_recommended": [],
                "next_steps": [],
                "engine": "catalog",
            }
            advise_ms = 0
            index_miss = False
        elif context.get("chat_session") and not force_research:
            from scripts.research_data_mcp.procurement_fast import advice_from_local_search, local_search

            local = local_search(self.gateway, goal_message, limit=int(context.get("limit") or 6))
            advice = advice_from_local_search(local, goal_message)
            advise_ms = 0
            index_miss = advice.get("verdict") == "weak"
        else:
            if memory_hint and memory_hint.get("verdict") == "wrong_fit" and budget.use_deepseek():
                advice = {
                    "verdict": "wrong_fit",
                    "message": memory_hint.get("summary") or "Similar goal checked recently — not in local catalog.",
                    "recommended": [],
                    "not_recommended": [],
                    "next_steps": [],
                    "engine": "memory",
                    "memory_hint": memory_hint,
                }
            if advice is None and budget.use_deepseek():
                advice = self.gateway.advise_datasets(
                    message,
                    current_dataset_id=str(context.get("dataset_id") or context.get("source_id") or ""),
                    limit=int(context.get("limit") or 5),
                )
            if advice is None:
                advice = self.gateway.advise_datasets(message, limit=5)
            advice["semantic_hits"] = semantic_hits
            advice["semantic_confidence"] = semantic_confidence
            advise_ms = int((time.time() - t0) * 1000)

            index_miss = (
                is_index_miss(advice, goal_message)
                or semantic_confidence in {"none", "low"}
            )
            if (
                semantic_confidence == "high"
                and advice.get("verdict") == "good_fit"
                and not force_research
            ):
                index_miss = False

        _COLLECT_JOB_TYPES = frozenset(
            {
                "collection_queue_task",
                "collection_queue_batch",
                "http_manifest",
                "registered_pipeline",
                "harvest_shard",
                "scraper_run",
            }
        )

        if catalog_fast:
            advice["semantic_hits"] = []
            advice["semantic_confidence"] = "high"
        elif advice.get("engine") == "local_search":
            advice.setdefault("semantic_hits", semantic_hits)
            advice.setdefault("semantic_confidence", semantic_confidence)
        else:
            advice["semantic_hits"] = semantic_hits
            advice["semantic_confidence"] = semantic_confidence

        plan = None
        if datacite_resolution and datacite_resolution.get("launchable"):
            plan = datacite_resolution
            index_miss = False
            phase = "collecting"
        elif catalog_fast_plan and catalog_fast_plan.get("launchable"):
            plan = catalog_fast_plan
            index_miss = False
            phase = "collecting"
        else:
            wants_collect = force_research or self.planner.wants_procurement(message)
            plan_context = {**context, "procurement_message": message}
            catalog_plan = None
            if wants_collect:
                catalog_plan = self.planner.plan_from_catalog(
                    goal_message, advice, plan_context
                ) or self.planner.plan_from_advice(advice, message)
            if catalog_plan and catalog_plan.get("launchable"):
                job_type = str(catalog_plan.get("job_type") or "")
                if job_type in _COLLECT_JOB_TYPES:
                    plan = catalog_plan
                    index_miss = False
                    phase = "collecting"
                elif not index_miss and not force_research:
                    plan = catalog_plan
            elif not index_miss and not force_research:
                plan = self.planner.plan_from_catalog(
                    goal_message, advice, context
                ) or self.planner.plan_from_advice(advice, goal_message)

        source_plan: dict[str, Any] | None = None
        catalog_hits: dict[str, Any] | None = None

        if index_miss and research_cfg.get("enabled", True) and research_cfg.get("auto_on_index_miss", True) and research_plan is None:
            phase = "research"
            if campaign:
                self.campaigns.update(campaign["id"], phase="research")

            try:
                source_plan = self.gateway.plan_sources(
                    goal_message, limit=int(discovery_cfg.get("max_search_results") or 8)
                )
            except Exception as exc:
                source_plan = {"rows": [], "meta": {"error": str(exc)}}

            queries = [goal_message, *(pack_hints.get("search_queries") or [])]
            for q in queries[1:4]:
                try:
                    part = self.gateway.search_catalog(q=q, limit=8)
                    if catalog_hits is None:
                        catalog_hits = part
                    else:
                        catalog_hits.setdefault("rows", []).extend(part.get("rows") or [])
                except Exception:
                    pass
            if catalog_hits is None:
                catalog_hits = {"rows": []}

            tavily_live = bool(discovery_cfg.get("tavily_live_on_research", True)) and budget.use_tavily()
            discovery = discover_with_catalog(
                self.gateway,
                goal_message,
                search_queries=queries,
                max_results=int(discovery_cfg.get("max_search_results") or 8),
                tavily_live=tavily_live,
            )
            for portal in pack_hints.get("trusted_portals") or []:
                url = str(portal.get("url") or "")
                if url.startswith("http"):
                    discovery.setdefault("results", []).insert(
                        0,
                        {"title": portal.get("name", url), "url": url, "source": "domain_pack", "snippet": portal.get("access_class", "")},
                    )

            if budget.use_deepseek():
                from scripts.research_data_mcp.procurement_cache import ProcurementCache, catalog_fingerprint, goal_key

                cache_cfg = self.config.get("cache") or {}
                cache = ProcurementCache(self.repo_root)
                fp = catalog_fingerprint(self.repo_root, self.gateway.registry_path)
                plan_key = goal_key(goal_message)
                cached_plan = cache.get(
                    "research_plan",
                    plan_key,
                    fingerprint=fp,
                    ttl_hours=float(cache_cfg.get("research_plan_ttl_hours", 168)),
                )
                if cached_plan and not force_research:
                    research_plan = cached_plan
                else:
                    research_plan = self.research_planner.build(
                        goal_message,
                        advice,
                        source_plan=source_plan,
                        catalog_hits=catalog_hits,
                        discovery=discovery,
                    )
                    cache.set(
                        "research_plan",
                        plan_key,
                        research_plan,
                        fingerprint=fp,
                        ttl_hours=float(cache_cfg.get("research_plan_ttl_hours", 168)),
                    )
            else:
                research_plan = self.research_planner.build(
                    message, advice, source_plan=source_plan, catalog_hits=catalog_hits, discovery=discovery
                )

            probe_urls = list(research_plan.get("probe_urls") or [])
            if research_cfg.get("auto_probe", True):
                from scripts.research_data_mcp.scrape_plan import classify_url, plan_for_url

                direct_urls = [u for u in probe_urls if classify_url(str(u)) == "direct_http"]
                probe_only_urls = [u for u in probe_urls if classify_url(str(u)) != "direct_http"]

                for url in direct_urls[:2]:
                    dplan = plan_for_url(str(url), title=f"Collect {str(url).split('/')[-1]}")
                    dplan["local_collect"] = True
                    submitted = self.gateway.jobs.submit(
                        dplan.get("title", "Direct collect"),
                        dplan,
                        {
                            "message": goal_message,
                            "campaign_id": campaign["id"] if campaign else "",
                            "magic": True,
                        },
                        auto_approve=False,
                    )
                    job = submitted.get("job")
                    # Acquires stay pending_approval until researcher approve / approve_collect.
                    if job:
                        collect_jobs.append(job)
                        analysis = {
                            "url": url,
                            "recommended_action": "approve_collect",
                            "collect_plan": dplan,
                            "feasibility": "direct",
                            "summary": f"Direct file collect: {url}",
                        }
                        recommendations.append(analysis)

                if collect_jobs:
                    phase = "collecting"
                    if campaign:
                        self.campaigns.update(
                            campaign["id"],
                            phase=phase,
                            payload={
                                "research_plan": research_plan,
                                "recommendations": recommendations,
                                "collect_job_ids": [j.get("id") for j in collect_jobs],
                            },
                        )

                phase = "probe" if probe_only_urls and not collect_jobs else phase
                if probe_only_urls and campaign and not collect_jobs:
                    self.campaigns.update(campaign["id"], phase="probe", payload={"research_plan": research_plan})
                probe_jobs: list[dict[str, Any]] = []
                if probe_only_urls:
                    probe_jobs = self._run_probes(
                        probe_only_urls,
                        limit=int(discovery_cfg.get("probe_top_n") or 3),
                        message=goal_message,
                        context={**context, "campaign_id": campaign["id"] if campaign else ""},
                        budget=budget,
                        force_execute=force_execute,
                        discovery=discovery,
                    )

                for job in probe_jobs:
                    url = (job.get("plan") or {}).get("url", "")
                    name = (job.get("plan") or {}).get("name", url)
                    analysis = self.probe_analyst.analyze(
                        url=url,
                        name=name,
                        job=job,
                        goal=message,
                        governance=self.governance,
                    )
                    recommendations.append(analysis)
                    probes.append({"url": url, "status": job.get("status"), "job_id": job.get("id"), "analysis": analysis})

                phase = "recommend" if recommendations else phase
                if any(r.get("recommended_action") == "approve_collect" for r in recommendations):
                    phase = "awaiting_approval"
                if collect_jobs and all(str(j.get("status") or "") == "completed" for j in collect_jobs):
                    phase = "ready"
                elif collect_jobs:
                    phase = "collecting"
                if campaign:
                    self.campaigns.update(
                        campaign["id"],
                        phase=phase,
                        payload={
                            "recommendations": recommendations,
                            "probe_job_ids": [j.get("id") for j in probe_jobs],
                            "collect_job_ids": [j.get("id") for j in collect_jobs],
                        },
                    )

                if force_execute or research_cfg.get("auto_collect") or (
                    context.get("chat_session") and research_cfg.get("auto_collect_chat", False)
                ):
                    for rec in recommendations:
                        if str(rec.get("feasibility") or "") == "direct":
                            continue
                        collect_plan = rec.get("collect_plan")
                        if not collect_plan or rec.get("recommended_action") != "approve_collect":
                            continue
                        submitted = self.gateway.jobs.submit(
                            collect_plan.get("title", "Collect"),
                            collect_plan,
                            {"message": message, "campaign_id": campaign["id"] if campaign else "", "magic": True},
                            auto_approve=False,
                        )
                        if submitted.get("job"):
                            collect_jobs.append(submitted["job"])
                    if collect_jobs:
                        phase = "collecting"

                agent_cfg = self.config.get("agent") or {}
                chat_scrape = context.get("chat_session") and (
                    agent_cfg.get("auto_scrape_after_acquire", False) or research_cfg.get("auto_scrape_chat", False)
                )
                if chat_scrape and not collect_jobs:
                    seen_urls: set[str] = set()
                    for rec in recommendations:
                        feas = str(rec.get("feasibility") or "")
                        cp = rec.get("collect_plan") or {}
                        jt = str(cp.get("job_type") or "")
                        url = str(rec.get("url") or cp.get("url") or "").strip()
                        if not url.startswith("http") or url in seen_urls:
                            continue
                        if feas != "scrape" and jt != "scraper_run":
                            continue
                        seen_urls.add(url)
                        from scripts.research_data_mcp.scrape_plan import infer_scrape_mode

                        cp = dict(cp)
                        cp.setdefault("scrape_mode", infer_scrape_mode(url))
                        submitted = self.gateway.jobs.submit(
                            cp.get("title", "Spectator scrape"),
                            cp,
                            {"message": message, "campaign_id": campaign["id"] if campaign else "", "magic": True},
                            auto_approve=False,
                        )
                        job = submitted.get("job")
                        if job:
                            collect_jobs.append(job)
                            phase = "collecting"
                        break

        elif context.get("resume") and research_plan and research_cfg.get("auto_probe"):
            saved_probe_ids = [str(x) for x in (saved.get("probe_job_ids") or [])]
            for jid in saved_probe_ids:
                try:
                    probe_jobs.append(self.gateway.get_yzu_job(jid))
                except Exception:
                    pass
            pending_urls = list(research_plan.get("probe_urls") or [])
            done_urls = {(j.get("plan") or {}).get("url") for j in probe_jobs}
            pending_urls = [u for u in pending_urls if u not in done_urls]
            if pending_urls and len(probe_jobs) < int(discovery_cfg.get("probe_top_n") or 3):
                phase = "probe"
                if campaign:
                    self.campaigns.update(campaign["id"], phase="probe")
                new_jobs = self._run_probes(
                    pending_urls,
                    limit=int(discovery_cfg.get("probe_top_n") or 3) - len(probe_jobs),
                    message=message,
                    context={**context, "campaign_id": campaign["id"] if campaign else ""},
                    budget=budget,
                    force_execute=force_execute,
                    discovery=saved.get("discovery") or discovery,
                )
                for job in new_jobs:
                    url = (job.get("plan") or {}).get("url", "")
                    name = (job.get("plan") or {}).get("name", url)
                    analysis = self.probe_analyst.analyze(
                        url=url, name=name, job=job, goal=message, governance=self.governance
                    )
                    recommendations.append(analysis)
                    probes.append({"url": url, "status": job.get("status"), "job_id": job.get("id"), "analysis": analysis})
                    probe_jobs.append(job)
            elif recommendations:
                phase = str(campaign.get("phase") if campaign else "awaiting_approval")
            if campaign and probe_jobs:
                self.campaigns.update(
                    campaign["id"],
                    phase=phase,
                    payload={
                        "research_plan": research_plan,
                        "recommendations": recommendations,
                        "probe_job_ids": [j.get("id") for j in probe_jobs],
                    },
                )

        elif plan is None and (wants_discovery(message, self.config) or discovery_cfg.get("trigger_when_no_plan")):
            discovery = discover_with_catalog(self.gateway, message, max_results=5)
            probe_url = (discovery.get("results") or [{}])[0].get("url")
            if probe_url and not self.planner._extract_url(message):
                plan = {
                    "title": "Probe discovered source",
                    "job_type": "source_probe",
                    "url": probe_url,
                    "name": probe_url[:120],
                    "launchable": True,
                }

        plan_ms = 0
        job = None
        executed = False
        answer = advice.get("message", "")

        if plan and plan.get("datacite_doi"):
            answer = f"Collecting DataCite dataset {plan.get('datacite_doi')} ({plan.get('datacite_file')}) from {plan.get('datacite_repository')}."
        elif research_plan:
            answer = str(research_plan.get("summary") or answer)
            if recommendations:
                actionable = [r for r in recommendations if r.get("recommended_action") == "approve_collect"]
                blocked = [r for r in recommendations if r.get("recommended_action") == "needs_credentials"]
                answer = (
                    f"{answer} Probed {len(probe_jobs)} source(s). "
                    f"{len(actionable)} ready to collect, {len(blocked)} need credentials."
                )

        queue_tasks = self.gateway.orchestrator.queue_tasks(runnable_only=False)
        if plan:
            t1 = time.time()
            plan = self.gateway.orchestrator.validate_plan(plan)
            plan_ms = int((time.time() - t1) * 1000)
            trusted = is_trusted_plan(plan, self.config, queue_tasks=queue_tasks)
            # Client/chat auto_approve bits are advisory only — execution_policy is authoritative.
            auto_approve = bool(trusted)
            if plan.get("launchable"):
                submitted = self.gateway.jobs.submit(
                    plan.get("title", "Magic procurement"),
                    plan,
                    {"message": message, "context": context, "magic": True, "campaign_id": campaign["id"] if campaign else ""},
                    auto_approve=auto_approve,
                )
                job = submitted.get("job")
                from scripts.research_data_mcp.procurement_fast import should_sync_wait

                wait = bool(context.get("wait_for_completion")) or (
                    (force_execute or should_auto_execute(plan, self.config))
                    and should_sync_wait(plan, self.config, queue_tasks=queue_tasks)
                )
                # Only sync-wait when actually queued (never poll a pending acquire forever).
                if job and job.get("status") in {"queued", "running"} and wait:
                    executed = True
                    job = self._execute_job(job["id"])
                phase = "collecting" if job else phase

        preview = None
        if not index_miss:
            instant_hits = [row for row in advice.get("recommended") or [] if row.get("kind") == "registry_dataset"]
            if instant_hits and not self.planner.wants_collect(message):
                top = instant_hits[0]
                if str(top.get("id")) not in {"datacite_local_harvest_status", "collection_queue_status"}:
                    try:
                        preview = self.gateway.query_dataset(top["id"], {"limit": int(context.get("preview_limit") or 3)})
                        phase = "ready"
                    except Exception as exc:
                        preview = {"error": str(exc)}

        promoted: list[dict[str, Any]] = []
        if job and job.get("status") == "completed":
            promoted = self._maybe_promote(job, campaign_id=campaign["id"] if campaign else "")

        if campaign:
            prior_payload = campaign.get("payload") or {}
            if not recommendations:
                recommendations = list(prior_payload.get("recommendations") or [])
            campaign = self.campaigns.update(
                campaign["id"],
                phase=phase if phase != "created" else ("index" if not index_miss else "research"),
                status="active" if phase not in {"ready", "failed"} else phase,
                payload={
                    "advice_verdict": advice.get("verdict"),
                    "research_plan": research_plan,
                    "recommendations": recommendations,
                    "probe_job_ids": [j.get("id") for j in probe_jobs]
                    or list(prior_payload.get("probe_job_ids") or []),
                    "collect_job_ids": [j.get("id") for j in collect_jobs] + ([job["id"]] if job else []),
                    "discovery": discovery if discovery.get("results") else prior_payload.get("discovery"),
                    "doi": plan.get("datacite_doi") if plan else (context.get("doi") or ""),
                    "datacite_file": plan.get("datacite_file") if plan else "",
                },
            )

        if self.memory:
            self.memory.remember_campaign(
                goal=message,
                payload={
                    "verdict": advice.get("verdict"),
                    "phase": phase,
                    "index_miss": index_miss,
                    "advice": advice,
                    "research_plan": research_plan,
                    "probe_urls": [p.get("url") for p in probes],
                    "promoted": promoted,
                    "summary": answer[:500],
                },
            )

        return {
            "message": answer.strip(),
            "magic": True,
            "resumed": bool(context.get("resume")),
            "phase": phase,
            "index_miss": index_miss,
            "campaign_id": campaign["id"] if campaign else None,
            "campaign": campaign,
            "advice": advice,
            "semantic_hits": semantic_hits,
            "semantic_confidence": semantic_confidence,
            "domain_packs": [p.get("id") for p in match_domain_packs(message, self.domain_packs)],
            "research_plan": research_plan,
            "recommendations": recommendations,
            "source_plan": {"rows": (source_plan or {}).get("rows", [])[:8]},
            "catalog_hits": (catalog_hits or {}).get("rows", [])[:8] if catalog_hits else [],
            "discovery": discovery,
            "probes": probes,
            "probe_jobs": [{"id": j.get("id"), "status": j.get("status"), "url": (j.get("plan") or {}).get("url")} for j in probe_jobs],
            "collect_jobs": collect_jobs,
            "plan": plan,
            "datacite_resolution": datacite_resolution,
            "job": job,
            "preview": preview,
            "executed": executed or bool(probe_jobs),
            "budget": budget.snapshot(),
            "storage": load_storage_policy(self.repo_root),
            "timing_ms": {"advise": advise_ms, "plan": plan_ms, "total": advise_ms + plan_ms},
        }

    def approve_collect(self, campaign_id: str, recommendation_index: int = 0) -> dict[str, Any]:
        if not self.campaigns:
            raise ValueError("campaign store not configured")
        campaign = self.campaigns.get(campaign_id)
        recs = self._campaign_recommendations(campaign)
        if not recs:
            payload = campaign.get("payload") or {}
            for jid in payload.get("collect_job_ids") or []:
                try:
                    pending = self.gateway.get_yzu_job(str(jid))
                except Exception:
                    continue
                if pending.get("status") != "pending_approval":
                    continue
                job = self.gateway.jobs.approve(str(jid))
                self.gateway.jobs.tick()
                job = self._execute_job(job["id"]) if job else pending
                self.campaigns.update(campaign_id, phase="collecting", payload={"last_collect_job": job})
                return {"campaign": self.campaigns.get(campaign_id), "job": job}
            raise ValueError(
                "No collectible recommendations yet — wait for probes to finish or run **source this for me** again"
            )
        if recommendation_index < 0 or recommendation_index >= len(recs):
            raise IndexError("recommendation_index out of range")
        rec = recs[recommendation_index]
        plan = dict(rec.get("collect_plan") or {})
        _executor = getattr(self.gateway.orchestrator, "executor", None)
        if plan.get("job_type") == "http_manifest":
            from scripts.research_data_mcp.scrape_plan import build_http_manifest_plan_for_url, classify_url as classify_fetch_mode

            item_url = str(plan.get("url") or "")
            if not item_url and plan.get("items"):
                item_url = str((plan["items"][0] or {}).get("url") or "")
            if item_url and (
                classify_fetch_mode(item_url) == "direct_http"
                or plan.get("public_direct_url")
                or not plan.get("destination")
            ):
                base = build_http_manifest_plan_for_url(item_url, title=str(plan.get("title") or ""))
                plan = {**base, **plan}
        if _executor and plan.get("job_type") == "http_manifest":
            from scripts.yzu_cluster.acquisitions import enrich_http_manifest_plan
            from scripts.yzu_cluster.cluster_ops import prefer_local_collect

            plan = enrich_http_manifest_plan(plan, _executor.procurement, domain_packs=self.domain_packs)
            cfg = getattr(self.gateway.orchestrator, "cfg", {}) or {}
            from scripts.research_data_mcp.scrape_plan import classify_url

            if item_url and classify_url(item_url) == "direct_http":
                plan["local_collect"] = True
                plan["public_direct_url"] = True
            else:
                plan.setdefault("local_collect", prefer_local_collect(cfg))
        if not plan:
            raise ValueError("recommendation has no collect_plan")
        # Human approve path: submit as pending, then approve explicitly (never rely on auto_approve).
        submitted = self.gateway.jobs.submit(
            plan.get("title", "Campaign collect"),
            plan,
            {"campaign_id": campaign_id, "magic": True, "source": "approve_collect"},
            auto_approve=False,
        )
        job = submitted.get("job")
        if job and job.get("status") == "pending_approval":
            job = self.gateway.jobs.approve(str(job["id"]))
        if job:
            job = self._execute_job(job["id"])
        self.campaigns.update(campaign_id, phase="collecting", payload={"last_collect_job": job})
        return {"campaign": self.campaigns.get(campaign_id), "job": job}

    def _campaign_recommendations(self, campaign: dict[str, Any]) -> list[dict[str, Any]]:
        payload = campaign.get("payload") or {}
        recs = list(payload.get("recommendations") or [])
        if recs:
            return recs
        goal = str(campaign.get("goal") or "")
        rebuilt: list[dict[str, Any]] = []
        for jid in payload.get("probe_job_ids") or []:
            try:
                job = self.gateway.get_yzu_job(str(jid))
            except Exception:
                continue
            url = str((job.get("plan") or {}).get("url") or "")
            name = str((job.get("plan") or {}).get("name") or url)
            analysis = self.probe_analyst.analyze(
                url=url,
                name=name,
                job=job,
                goal=goal,
                governance=self.governance,
            )
            if analysis:
                rebuilt.append(analysis)
        return rebuilt

    def _run_probes(
        self,
        urls: list[str],
        *,
        limit: int,
        message: str,
        context: dict[str, Any],
        budget: ProcurementBudget,
        force_execute: bool,
        discovery: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        from scripts.research_data_mcp.probe_url_selection import rank_probe_urls

        raw_discovery = list((discovery or {}).get("results") or [])
        web_hits = [h for h in raw_discovery if str(h.get("source") or "") not in {"source_plan", "external_catalog"}]
        catalog_hits = [h for h in raw_discovery if str(h.get("source") or "") == "external_catalog"]
        source_hits = [h for h in raw_discovery if str(h.get("source") or "") == "source_plan"]
        ranked = rank_probe_urls(
            message,
            discovery_results=web_hits,
            catalog_rows=catalog_hits,
            source_plan_rows=source_hits,
            planner_urls=urls,
            limit=max(limit * 3, 10),
        )
        jobs: list[dict[str, Any]] = []
        seen: set[str] = set()
        for url in ranked:
            url = str(url).strip()
            if not url.startswith("http") or url in seen:
                continue
            if not allow_auto_probe(url, self.governance):
                continue
            if not budget.use_probe():
                break
            seen.add(url)
            plan = {"title": f"Probe: {url[:80]}", "job_type": "source_probe", "url": url, "name": url[:120], "launchable": True}
            submitted = self.gateway.jobs.submit(
                plan["title"],
                plan,
                {
                    "message": message,
                    "magic": True,
                    "campaign_id": str(context.get("campaign_id") or ""),
                },
                auto_approve=True,
            )
            job = submitted.get("job")
            if not job:
                continue
            if force_execute or should_auto_execute(plan, self.config):
                job = self._execute_job(job["id"])
            jobs.append(job)
            if len(jobs) >= limit:
                break
        return jobs

    def _execute_job(self, job_id: str) -> dict[str, Any]:
        execute_cfg = self.config.get("execute") or {}
        timeout = float(execute_cfg.get("wait_seconds") or 120)
        poll = float(execute_cfg.get("poll_seconds") or 2)
        tick = bool(execute_cfg.get("tick_worker", True))
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = self.gateway.get_yzu_job(job_id)
            if job.get("status") in {"completed", "failed", "cancelled"}:
                return job
            if tick:
                self.gateway.jobs.tick()
            time.sleep(poll)
        return self.gateway.get_yzu_job(job_id)

    def _maybe_promote(self, job: dict[str, Any], *, campaign_id: str = "") -> list[dict[str, Any]]:
        promoter = getattr(self.gateway.orchestrator, "registry_promoter", None)
        if promoter is None:
            from scripts.research_data_mcp.registry_promotion import RegistryPromoter

            promoter = RegistryPromoter(self.repo_root, self.gateway.registry_path)
        flywheel = getattr(self.gateway.orchestrator, "collection_flywheel", None)
        try:
            plan = job.get("plan") or {}
            doi = str(plan.get("datacite_doi") or "")
            if doi:
                promoted = promoter.promote_datacite_collect(job, doi=doi, campaign_id=campaign_id)
            else:
                promoted = promoter.promote_job(job, campaign_id=campaign_id)
            if promoted:
                self.gateway.reload_registry()
                if flywheel is not None:
                    search_goal = ""
                    if campaign_id and self.campaigns:
                        try:
                            search_goal = str(self.campaigns.get(campaign_id).get("goal") or "")
                        except KeyError:
                            pass
                    flywheel.promote_after_collect(
                        job,
                        promoted,
                        campaign_id=campaign_id,
                        search_goal=search_goal,
                    )
            return promoted
        except Exception:
            return []
