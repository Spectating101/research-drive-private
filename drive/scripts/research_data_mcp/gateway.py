#!/usr/bin/env python3
"""Unified facade — delegates to search, catalog, planner, and jobs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.catalog import CatalogService
from scripts.research_data_mcp.jobs import JobService
from scripts.research_data_mcp.search import SearchService
from scripts.research_query_engine.agent import AgentOrchestrator
from scripts.research_query_engine.engine import ResearchQueryEngine
from scripts.yzu_cluster.api import YzuClusterAPI


class ResearchDataGateway:
    def __init__(
        self,
        repo_root: str | Path,
        registry_path: str | Path | None = None,
        orchestrator: Any | None = None,
        *,
        engine: ResearchQueryEngine | None = None,
        yzu_api: YzuClusterAPI | None = None,
        jobs: JobService | None = None,
    ):
        self.repo_root = Path(repo_root).resolve()
        registry = Path(registry_path) if registry_path else self.repo_root / "config/research_query_registry.json"
        if not registry.is_absolute():
            registry = (self.repo_root / registry).resolve()
        self.registry_path = registry

        self.engine = engine or ResearchQueryEngine(registry, repo_root=self.repo_root)
        self.agent = AgentOrchestrator(self.engine, orchestrator=orchestrator)
        self._yzu_api = yzu_api
        self.jobs = jobs or JobService(self.agent.orchestrator)
        self.jobs.gateway = self  # Discover refresh tick from jobs.tick()

        self.search = SearchService(self.engine, self.registry_path, self.repo_root)
        self.catalog = CatalogService(self.repo_root, self.search, self.agent.orchestrator, self.agent.procurement)
        self.agent.set_planner(None)
        self.planner = PassivePlanner(self)

    @property
    def orchestrator(self):
        return self.agent.orchestrator

    @property
    def yzu(self) -> YzuClusterAPI:
        if self._yzu_api is None:
            self._yzu_api = YzuClusterAPI(self.repo_root, agent=self.agent, orchestrator=self.orchestrator)
        return self._yzu_api

    @property
    def procurement(self):
        return self.agent.procurement

    def reload_registry(self) -> None:
        self.search.reload_registry()

    def ensure_registry_fresh(self) -> None:
        self.search.ensure_registry_fresh()


    # --- search ---
    def list_datasets(self, **kwargs: Any) -> dict[str, Any]:
        return self.search.list_datasets(**kwargs)

    def describe_dataset(self, dataset_id: str) -> dict[str, Any]:
        return self.search.describe_dataset(dataset_id)

    def query_dataset(self, dataset_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.search.query_dataset(dataset_id, params)

    def plan_sources(self, q: str, limit: int = 25) -> dict[str, Any]:
        return self.search.plan_sources(q, limit)

    def search_catalog(self, **kwargs: Any) -> dict[str, Any]:
        return self.search.search_catalog(**kwargs)

    def library_overview(self) -> dict[str, Any]:
        return self.search.library_overview()

    def ops_status(self, lane: str = "") -> dict[str, Any]:
        return self.search.ops_status(lane)

    # --- catalog ---
    def procurement_catalog(self, q: str = "", limit: int = 50) -> dict[str, Any]:
        return self.catalog.procurement_catalog(q, limit)

    def advise_datasets(self, goal: str, **kwargs: Any) -> dict[str, Any]:
        from scripts.research_data_mcp.advisor import DatasetAdvisor
        from scripts.research_data_mcp.magic_config import load_magic_config
        from scripts.research_data_mcp.procurement_cache import ProcurementCache, catalog_fingerprint, goal_key

        skip_cache = bool(kwargs.pop("skip_cache", False))
        cache_cfg = load_magic_config(self.repo_root).get("cache") or {}
        if not skip_cache:
            cache = ProcurementCache(self.repo_root)
            fp = catalog_fingerprint(self.repo_root, self.registry_path)
            key = goal_key(goal)
            hit = cache.get(
                "advisor",
                key,
                fingerprint=fp,
                ttl_hours=float(cache_cfg.get("advisor_ttl_hours", 24)),
            )
            if hit:
                out = dict(hit)
                out["from_cache"] = True
                out.setdefault("engine", "cache")
                return out
        result = DatasetAdvisor(self).advise(goal, **kwargs)
        if not skip_cache:
            cache.set(
                "advisor",
                key,
                result,
                fingerprint=fp,
                ttl_hours=float(cache_cfg.get("advisor_ttl_hours", 24)),
            )
        return result

    def procurement_chat(
        self,
        message: str,
        *,
        session_id: str | None = None,
        user_email: str | None = None,
        rail_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Multi-turn conversational procurement — search, discuss, confirm, collect."""
        return self._procurement_chat_orchestrator().chat(
            self,
            message,
            session_id=session_id,
            user_email=user_email,
            rail_context=rail_context,
        )

    def procurement_chat_stream(
        self,
        message: str,
        *,
        session_id: str | None = None,
        user_email: str | None = None,
        rail_context: dict[str, Any] | None = None,
    ):
        """NDJSON event generator for progressive UI updates."""
        return self._procurement_chat_orchestrator().chat_events(
            self,
            message,
            session_id=session_id,
            user_email=user_email,
            rail_context=rail_context,
        )

    def faculty_profile(self, *, email: str = "", slug: str = "") -> dict[str, Any]:
        from scripts.research_data_mcp.faculty_profile import (
            is_valid_yzu_email,
            normalize_email,
            profile_summary,
            resolve_profile,
        )

        email_n = normalize_email(email)
        if email_n and not is_valid_yzu_email(email_n):
            return {"found": False, "email": email_n, "slug": slug, "error": "invalid_yzu_email"}
        row = resolve_profile(email=email, slug=slug)
        if not row:
            return {"found": False, "email": email, "slug": slug}
        return {"found": True, "profile": profile_summary(row)}

    def desk_vault_brief(self, *, email: str = "") -> dict[str, Any]:
        from scripts.research_data_mcp.desk_vault_brief import build_vault_brief
        from scripts.research_data_mcp.faculty_profile import profile_summary, resolve_profile

        profile: dict[str, Any] | None = None
        row = resolve_profile(email=email) if email else None
        if row:
            profile = profile_summary(row)
        brief = build_vault_brief(self.repo_root, profile)
        return {"brief": brief, "words": len(brief.split()), "faculty": bool(profile)}

    def desk_warm_session(
        self,
        *,
        user_email: str = "",
        session_id: str = "",
        background: bool = True,
    ) -> dict[str, Any]:
        from scripts.research_data_mcp.desk_warm import warm_desk_session

        email = str(user_email or "").strip() or None
        sid = str(session_id or "").strip() or None
        return warm_desk_session(self, user_email=email, session_id=sid, background=background)

    def procurement_chat_session(self, session_id: str) -> dict[str, Any]:
        """Restore a procurement chat session (transcript + candidates)."""
        return self._procurement_chat_orchestrator().get_session(session_id)

    def _procurement_chat_orchestrator(self) -> Any:
        if not hasattr(self, "_chat_orchestrator"):
            from scripts.research_data_mcp.procurement_chat import ProcurementChatOrchestrator

            self._chat_orchestrator = ProcurementChatOrchestrator(self.repo_root)
        return self._chat_orchestrator

    def resume_campaign(self, campaign_id: str, *, force_execute: bool = False) -> dict[str, Any]:
        runner = getattr(self.jobs, "campaign_runner", None)
        if runner is not None:
            return runner.resume(campaign_id, force_execute=force_execute)
        from scripts.research_data_mcp.magic_procure import MagicProcurement

        memory = getattr(self.orchestrator, "procurement_memory", None)
        campaigns = getattr(self.orchestrator, "procurement_campaigns", None)
        return MagicProcurement(self, memory=memory, campaigns=campaigns).resume(campaign_id, force_execute=force_execute)

    def tick_campaigns(self, limit: int = 3) -> dict[str, Any]:
        runner = getattr(self.jobs, "campaign_runner", None)
        if runner is None:
            return {"advanced": []}
        return {"advanced": runner.tick(limit=limit)}

    def approve_campaign_collect(self, campaign_id: str, recommendation_index: int = 0) -> dict[str, Any]:
        from scripts.research_data_mcp.magic_procure import MagicProcurement

        memory = getattr(self.orchestrator, "procurement_memory", None)
        campaigns = getattr(self.orchestrator, "procurement_campaigns", None)
        return MagicProcurement(self, memory=memory, campaigns=campaigns).approve_collect(campaign_id, recommendation_index)

    def list_campaigns(self, limit: int = 30, status: str = "") -> dict[str, Any]:
        campaigns = getattr(self.orchestrator, "procurement_campaigns", None)
        if campaigns is None:
            return {"campaigns": []}
        return {"campaigns": campaigns.list(limit=limit, status=status)}

    def browse_drive(
        self,
        *,
        folder_id: str = "",
        scope: str = "lab",
        showcase_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        from scripts.research_data_mcp.drive_browse import build_browse_tree, list_folder_children

        datasets = self.engine.list_datasets()
        campaigns = self.list_campaigns(limit=50).get("campaigns") or []
        pins = self.list_dataset_pins(limit=100).get("pins") or []
        tree = build_browse_tree(
            datasets,
            scope=scope,
            campaigns=campaigns,
            pins=pins,
            showcase_ids=showcase_ids or [],
        )
        children = list_folder_children(tree, folder_id)
        return {
            "scope": scope,
            "folder_id": folder_id,
            "children": children,
            "tree": tree,
            "dataset_count": tree.get("dataset_count", 0),
            "folder_count": tree.get("folder_count", 0),
        }

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        campaigns = getattr(self.orchestrator, "procurement_campaigns", None)
        if campaigns is None:
            raise KeyError(campaign_id)
        return campaigns.get(campaign_id)

    def list_campaign_artifacts(self, campaign_id: str) -> dict[str, Any]:
        from scripts.research_data_mcp.campaign_artifacts import list_campaign_artifacts

        campaign = self.get_campaign(campaign_id)
        return list_campaign_artifacts(
            self.repo_root,
            campaign,
            job_get=self.jobs.get,
            registry_path=self.repo_root / "config/research_query_registry.json",
        )

    def resolve_campaign_download(self, campaign_id: str, rel_path: str) -> dict[str, Any]:
        from scripts.research_data_mcp.campaign_artifacts import resolve_campaign_download

        self.get_campaign(campaign_id)
        return resolve_campaign_download(self.repo_root, campaign_id, rel_path)

    def datacite_resolve_repository(self, doi: str, *, max_file_bytes: int = 50_000_000) -> dict[str, Any]:
        from scripts.research_data_mcp.doi_resolve_cache import resolve_doi_cached

        return resolve_doi_cached(self.repo_root, doi, max_file_bytes=max_file_bytes)

    def datacite_search_and_resolve(
        self,
        query: str,
        *,
        created: str = "",
        max_file_bytes: int = 50_000_000,
    ) -> dict[str, Any]:
        from scripts.research_data_mcp.datacite_repository import search_and_resolve

        return search_and_resolve(query, created=created, max_file_bytes=max_file_bytes)

    def collect_datacite_doi(
        self,
        doi: str,
        *,
        file_index: int = 0,
        campaign_id: str | None = None,
        auto_execute: bool = True,
        max_file_bytes: int = 50_000_000,
        license_approved: bool = False,
    ) -> dict[str, Any]:
        """Agent/MCP path: resolve DOI → collect → return campaign + artifacts."""
        from scripts.research_data_mcp.credential_gate import classify_collect_gate
        from scripts.research_data_mcp.credential_vault import has_license_approval
        from scripts.research_data_mcp.governance import classify_url

        resolved = self.datacite_resolve_repository(doi, max_file_bytes=max_file_bytes)
        gate = classify_collect_gate(
            url=str(resolved.get("landing_url") or ""),
            license_text=str(resolved.get("license") or (resolved.get("metadata") or {}).get("license") or ""),
            governance_class=classify_url(str(resolved.get("landing_url") or ""), name=str(resolved.get("title") or "")),
            repository=str(resolved.get("repository") or ""),
            doi=doi,
            repo_root=self.repo_root,
        )
        if gate.get("needs_approval") and not license_approved and not has_license_approval(self.repo_root, doi=doi):
            return {
                "blocked": True,
                "gate": gate,
                "resolved": resolved,
                "message": gate.get("blocked_reason") or "license approval required",
            }
        if not gate.get("allowed") and gate.get("blocked_reason"):
            return {"blocked": True, "gate": gate, "resolved": resolved, "message": gate["blocked_reason"]}

        from scripts.research_data_mcp.procured_dataset import try_reuse_pinned_collect

        reused = try_reuse_pinned_collect(
            self.repo_root,
            doi=doi,
            file_index=file_index,
            resolved=resolved,
            get_campaign=self.get_campaign,
        )
        if reused:
            return self._enrich_collect_result(reused, doi)

        from scripts.research_data_mcp.datacite_repository import build_http_manifest_plan
        plan = build_http_manifest_plan(resolved, file_index=file_index)
        if not plan:
            return {
                "blocked": True,
                "resolved": resolved,
                "message": "could not build DataCite collect plan",
            }
        plan = self.orchestrator.validate_plan(plan)
        if not plan.get("launchable"):
            return {
                "blocked": True,
                "resolved": resolved,
                "message": plan.get("validation_error") or "collect plan not launchable",
                "plan": plan,
            }

        from scripts.research_data_mcp.procurement_auto_approve import should_auto_approve_plan
        from scripts.research_data_mcp.procurement_equipment_bridge import submit_collect_plan

        request = {
            "doi": doi,
            "campaign_id": campaign_id or "",
            "add_to_collection": True,
            "mcp": True,
        }
        approve = bool(
            auto_execute
            and should_auto_approve_plan(plan, self.repo_root, orchestrator=self.orchestrator)
        )
        submitted = submit_collect_plan(self, plan, context=request, auto_approve=approve)
        out = {
            "plan": plan,
            "job": submitted.get("job"),
            "campaign_id": campaign_id,
            "resolved": resolved,
        }
        return self._enrich_collect_result(out, doi)

    def add_datacite_to_collection(
        self,
        doi: str,
        *,
        campaign_id: str | None = None,
        file_index: int = 0,
        auto_execute: bool = True,
    ) -> dict[str, Any]:
        """UI one-click: search result → add to collection."""
        return self.collect_datacite_doi(
            doi,
            file_index=file_index,
            campaign_id=campaign_id,
            auto_execute=auto_execute,
        )

    def unified_dataset_search(
        self,
        query: str,
        *,
        limit: int = 12,
        include_hf: bool = True,
        include_datacite: bool = True,
        resolve_datacite: bool = False,
        max_file_bytes: int = 50_000_000,
    ) -> dict[str, Any]:
        from scripts.research_data_mcp.desk_scale import get_search_cache, set_search_cache

        cache_key = {
            "limit": limit,
            "hf": int(include_hf),
            "dc": int(include_datacite),
            "resolve": int(resolve_datacite),
        }
        cached = get_search_cache("unified", query, **cache_key)
        if cached is not None:
            return cached
        from scripts.research_data_mcp.unified_search import unified_search

        out = unified_search(
            self,
            query,
            limit=limit,
            include_hf=include_hf,
            include_datacite=include_datacite,
            resolve_datacite=resolve_datacite,
            max_file_bytes=max_file_bytes,
        )
        set_search_cache("unified", query, out, **cache_key)
        return out

    @staticmethod
    def _search_row_key(row: dict[str, Any]) -> str:
        return str(
            row.get("dataset_id") or row.get("doi") or row.get("id") or row.get("title") or row.get("url") or ""
        ).strip().lower()

    def unified_search_with_profile(
        self,
        query: str,
        *,
        email: str = "",
        limit: int = 12,
        include_hf: bool = True,
        include_datacite: bool = True,
        resolve_datacite: bool = False,
        max_file_bytes: int = 50_000_000,
        skip_discover: bool = False,
        parallel_profile: bool = False,
    ) -> dict[str, Any]:
        """Full unified search; when email is set, prepend discover rows and attach faculty hints."""
        email = str(email or "").strip()
        profile_layer: dict[str, Any] = {}

        if email and parallel_profile and not skip_discover:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=2) as pool:
                f_out = pool.submit(
                    self.unified_dataset_search,
                    query,
                    limit=limit,
                    include_hf=include_hf,
                    include_datacite=include_datacite,
                    resolve_datacite=resolve_datacite,
                    max_file_bytes=max_file_bytes,
                )
                f_disc = pool.submit(self.discover_search, query, email=email, limit=limit)
                out = f_out.result()
                profile_layer = f_disc.result()
        else:
            out = self.unified_dataset_search(
                query,
                limit=limit,
                include_hf=include_hf,
                include_datacite=include_datacite,
                resolve_datacite=resolve_datacite,
                max_file_bytes=max_file_bytes,
            )
            if not email:
                out["routed_via"] = "unified_dataset_search"
                return out
            if not skip_discover:
                profile_layer = self.discover_search(query, email=email, limit=limit)
            else:
                out["discover_skipped"] = True

        if not email:
            out["routed_via"] = "unified_dataset_search"
            return out

        if skip_discover:
            out["discover_skipped"] = True

        if not skip_discover:
            out["profile_queries"] = profile_layer.get("profile_queries") or []
            out["bigquery_hints"] = profile_layer.get("bigquery_hints") or []
            if profile_layer.get("index_miss") is not None:
                out["discover_index_miss"] = bool(profile_layer.get("index_miss"))
            if profile_layer.get("weak_match") is not None:
                out["discover_weak_match"] = bool(profile_layer.get("weak_match"))

        seen = {self._search_row_key(row) for section in out.get("sections") or [] for row in section.get("rows") or []}
        discover_rows: list[dict[str, Any]] = []
        for section in profile_layer.get("sections") or []:
            for row in section.get("rows") or []:
                key = self._search_row_key(row)
                if not key or key in seen:
                    continue
                seen.add(key)
                discover_rows.append(row)

        if discover_rows:
            sections = list(out.get("sections") or [])
            sections.insert(
                0,
                {
                    "id": "discover",
                    "label": "Recommended",
                    "count": len(discover_rows),
                    "rows": discover_rows,
                },
            )
            out["sections"] = sections
            out["rows"] = discover_rows + list(out.get("rows") or [])
            out["total"] = len(out["rows"])

        if skip_discover:
            out["routed_via"] = "unified_dataset_search"
        elif discover_rows:
            out["routed_via"] = "unified_dataset_search+discover_profile"
        else:
            out["routed_via"] = "unified_dataset_search+discover_profile"
        return out

    def discover_search(
        self,
        query: str,
        *,
        email: str = "",
        limit: int = 12,
    ) -> dict[str, Any]:
        """Profile-aware discover: catalog rows + faculty context hints for Composer (not search boosts)."""
        from scripts.research_data_mcp.faculty_profile import (
            bigquery_route_hints,
            expand_datacite_queries,
            normalize_email,
            resolve_profile,
        )
        from scripts.research_data_mcp.procurement_search import smart_search

        profile = resolve_profile(email=normalize_email(email)) if email else None
        result = smart_search(self, query, limit=limit)
        candidates = list(result.get("candidates") or [])
        sections: list[dict[str, Any]] = []
        if candidates:
            from scripts.research_data_mcp.candidate_key import stamp_rows

            rows = stamp_rows(
                [
                    {
                        "kind": c.get("kind"),
                        "dataset_id": c.get("dataset_id"),
                        "doi": c.get("doi"),
                        "title": c.get("title"),
                        "url": c.get("url"),
                        "source": c.get("source") or c.get("collect_via"),
                        "score": c.get("score"),
                        "local_path": c.get("local_path"),
                        "local_ready": c.get("local_ready"),
                        "collect_via": c.get("collect_via"),
                        "procureability": c.get("procureability"),
                        "procureability_label": c.get("procureability_label"),
                        "external_id": c.get("external_id"),
                        "handle": c.get("handle"),
                        "hf_id": c.get("hf_id"),
                        "provider": c.get("provider"),
                    }
                    for c in candidates
                ]
            )
            sections.append(
                {
                    "id": "discover",
                    "label": "Recommended",
                    "rows": rows,
                }
            )
        return {
            "query": query,
            "sections": sections,
            "total": len(candidates),
            "index_miss": bool(result.get("index_miss")),
            "weak_match": bool(result.get("weak_match")),
            "sources": result.get("sources") or [],
            "judgment": result.get("judgment"),
            "profile_queries": expand_datacite_queries(query, profile) if profile else [],
            "bigquery_hints": bigquery_route_hints(profile, query) if profile else [],
        }

    def semantic_discover(self, query: str, *, limit: int = 12) -> dict[str, Any]:
        """Embedding-ranked registry evidence for natural-language research questions."""
        from scripts.research_data_mcp.semantic_index import get_semantic_index

        q = str(query or "").strip()
        if not q:
            return {"query": q, "mode": "semantic", "sections": [], "rows": [], "total": 0}
        index = get_semantic_index(self)
        from scripts.research_data_mcp.candidate_key import stamp_rows

        hits = index.semantic_search(q, limit=max(1, min(limit, 24)), kinds={"registry_dataset"})
        rows: list[dict[str, Any]] = []
        for hit in hits:
            meta = dict(hit.get("metadata") or {})
            dataset_id = str(hit.get("id") or meta.get("dataset_id") or "")
            if not dataset_id:
                continue
            rows.append(
                {
                    "kind": "local_registry",
                    "id": dataset_id,
                    "dataset_id": dataset_id,
                    "title": meta.get("title") or dataset_id,
                    "description": meta.get("description") or "",
                    "grain": meta.get("grain") or "",
                    "source": meta.get("source") or "registry",
                    "analysis_readiness": meta.get("readiness") or "",
                    "local_ready": True,
                    "semantic_score": hit.get("score"),
                    "match_type": "semantic",
                }
            )
        rows = stamp_rows(rows)
        return {
            "query": q,
            "mode": "semantic",
            "model": index._embedding_model or "sentence-transformers/all-MiniLM-L6-v2",
            "sections": [{"id": "semantic_lab", "label": "Semantic lab matches", "rows": rows}] if rows else [],
            "rows": rows,
            "total": len(rows),
            "index_miss": not rows,
        }

    def enrich_datacite_search(
        self,
        rows: list[dict[str, Any]],
        *,
        max_file_bytes: int = 50_000_000,
    ) -> dict[str, Any]:
        from scripts.research_data_mcp.unified_search import enrich_datacite_rows

        enriched = enrich_datacite_rows(self.repo_root, rows, max_file_bytes=max_file_bytes)
        return {"rows": enriched, "count": len(enriched)}

    def approve_dataset_license(
        self,
        *,
        doi: str = "",
        url: str = "",
        license_text: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        from scripts.research_data_mcp.credential_vault import approve_license

        return approve_license(self.repo_root, doi=doi, url=url, license_text=license_text, note=note)

    def list_credential_profiles(self) -> dict[str, Any]:
        from scripts.research_data_mcp.credential_vault import list_profiles

        return {"profiles": list_profiles(self.repo_root)}

    def get_dataset_card(self, ref: str) -> dict[str, Any]:
        from scripts.research_data_mcp.procured_dataset import (
            build_card_from_campaign,
            build_card_from_registry,
            parse_handle,
        )

        parsed = parse_handle(ref)
        if ref.startswith("hf:") or parsed.get("kind") == "hf":
            from scripts.research_data_mcp.hf_loader import build_hf_card

            did = parsed.get("dataset_id") or ref.removeprefix("hf:")
            return build_hf_card(did)
        if parsed.get("kind") == "campaign" or (parsed.get("kind") == "raw" and len(ref) == 12):
            cid = parsed.get("campaign_id") or ref
            campaign = self.get_campaign(cid)
            return build_card_from_campaign(
                self.repo_root,
                campaign,
                job_get=self.get_yzu_job,
                registry_path=self.registry_path,
            )
        if parsed.get("kind") == "dataset":
            return build_card_from_registry(self.repo_root, self.describe_dataset(parsed["dataset_id"]))
        if parsed.get("kind") == "doi":
            resolved = self.datacite_resolve_repository(parsed["doi"])
            from scripts.research_data_mcp.procureability import datacite_procureability

            proc = datacite_procureability(resolved)
            return {
                "id": f"procured://doi:{parsed['doi']}",
                "handle": f"doi:{parsed['doi']}",
                "title": resolved.get("title"),
                "doi": parsed["doi"],
                "source": "datacite",
                "repository": resolved.get("repository"),
                "files": resolved.get("files") or [],
                "procureability": proc,
                "status": proc.get("status"),
            }
        raise KeyError(ref)

    def open_dataset(self, handle: str, *, load: str = "auto", preview_limit: int = 5) -> dict[str, Any]:
        from scripts.research_data_mcp.procured_dataset import open_dataset as _open

        return _open(self.repo_root, handle, gateway=self, preview_limit=preview_limit, load=load)

    def pin_dataset(self, handle: str, *, campaign_id: str = "", file_path: str = "", checksum: str = "") -> dict[str, Any]:
        from scripts.research_data_mcp.procured_dataset import get_pin, make_handle, parse_handle, pin_dataset

        parsed = parse_handle(handle)
        if not handle:
            raise ValueError("handle is required")
        if parsed.get("kind") == "doi" and campaign_id:
            h = make_handle(doi=parsed["doi"], file_name=parsed.get("file", ""))
            return pin_dataset(
                self.repo_root,
                handle=h,
                campaign_id=campaign_id,
                file_path=file_path,
                checksum=checksum,
            )
        return get_pin(self.repo_root, handle) or pin_dataset(self.repo_root, handle=handle, campaign_id=campaign_id)

    def list_dataset_pins(self, *, limit: int = 50) -> dict[str, Any]:
        from scripts.research_data_mcp.procured_dataset import list_pins

        return {"pins": list_pins(self.repo_root, limit=limit)}

    def approve_safe_pending_jobs(self, *, limit: int = 200) -> dict[str, Any]:
        """Approve pending jobs that match desk auto-approve policy."""
        from scripts.research_data_mcp.procurement_auto_approve import should_auto_approve_plan

        approved: list[str] = []
        skipped = 0
        for job in self.jobs.list(limit, status="pending_approval").get("jobs") or []:
            jid = str(job.get("id") or "")
            plan = job.get("plan") or {}
            if plan.get("job_type") == "synthesis_execute":
                skipped += 1
                continue
            if not jid or not should_auto_approve_plan(plan, self.repo_root, orchestrator=self.orchestrator):
                skipped += 1
                continue
            self.jobs.approve(jid)
            approved.append(jid)
        ticked = 0
        for _ in approved[:3]:
            if self.jobs.tick():
                ticked += 1
        return {"approved": approved, "approved_count": len(approved), "skipped_count": skipped, "tick_started": ticked}

    def desk_resources(self, *, live: bool = False) -> dict[str, Any]:
        import time

        from scripts.research_data_mcp.desk_resources import build_desk_resources

        cache = getattr(self, "_desk_resources_cache", None)
        if cache is None:
            cache = {}
            setattr(self, "_desk_resources_cache", cache)
        now = time.time()
        hit = cache.get("payload")
        if hit and now - float(cache.get("ts") or 0) < 30:
            return hit
        payload = build_desk_resources(self, live=live)
        cache["payload"] = payload
        cache["ts"] = now
        return payload

    def platform_state(self) -> dict[str, Any]:
        """Neutral databank progress snapshot (drive/docs/status/generated/platform_progress.json)."""
        path = Path(self.repo_root) / "drive/docs/status/generated/platform_progress.json"
        if not path.is_file():
            path = Path(self.repo_root) / "docs/status/generated/platform_progress.json"
        if not path.is_file():
            return {"found": False, "note": "Run drive/scripts/sync_drive_platform_state.py"}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return {"found": False, "error": str(exc)}
        return {"found": True, **data}

    def source_map_audit(self, *, live: bool = False) -> dict[str, Any]:
        """Canonical registry ↔ source-system map."""
        if not live:
            for rel in (
                "drive/docs/status/generated/databank_source_map.json",
                "docs/status/generated/databank_source_map.json",
            ):
                path = Path(self.repo_root) / rel
                if path.is_file():
                    try:
                        cached = json.loads(path.read_text(encoding="utf-8"))
                        cached["found"] = True
                        cached["cache_path"] = rel
                        return cached
                    except json.JSONDecodeError:
                        pass
        from scripts.research_data_mcp.source_map import build_source_map_audit

        audit = build_source_map_audit(Path(self.repo_root))
        audit["found"] = True
        audit["live"] = True
        return audit

    def access_scope_audit(self, *, live: bool = False) -> dict[str, Any]:
        """Desk entitlements — what we CAN access vs materialized coverage."""
        if not live:
            for rel in (
                "drive/docs/status/generated/databank_access_scope.json",
                "docs/status/generated/databank_access_scope.json",
            ):
                path = Path(self.repo_root) / rel
                if path.is_file():
                    try:
                        cached = json.loads(path.read_text(encoding="utf-8"))
                        cached["found"] = True
                        cached["cache_path"] = rel
                        return cached
                    except json.JSONDecodeError:
                        pass
        from scripts.research_data_mcp.access_scope import build_access_coverage_audit

        audit = build_access_coverage_audit(Path(self.repo_root))
        audit["found"] = True
        audit["live"] = True
        return audit

    def dataset_coverage_audit(self, *, live: bool = False) -> dict[str, Any]:
        """Dataset-level coverage, collection bulk profiles, proxy/synthetic paths."""
        if not live:
            for rel in (
                "drive/docs/status/generated/databank_dataset_coverage.json",
                "docs/status/generated/databank_dataset_coverage.json",
            ):
                path = Path(self.repo_root) / rel
                if path.is_file():
                    try:
                        cached = json.loads(path.read_text(encoding="utf-8"))
                        cached["found"] = True
                        cached["cache_path"] = rel
                        return cached
                    except json.JSONDecodeError:
                        pass
        from scripts.research_data_mcp.dataset_coverage import build_dataset_coverage_audit

        audit = build_dataset_coverage_audit(Path(self.repo_root))
        audit["found"] = True
        audit["live"] = True
        return audit

    def consolidated_state(self, *, live: bool = False) -> dict[str, Any]:
        """Single Bloomberg-style desk snapshot: catalogue + entitlements + sourcing + storage."""
        if not live:
            for rel in (
                "drive/docs/status/generated/consolidated_state.json",
                "docs/status/generated/consolidated_state.json",
            ):
                path = Path(self.repo_root) / rel
                if path.is_file():
                    try:
                        cached = json.loads(path.read_text(encoding="utf-8"))
                        cached["found"] = True
                        cached["cache_path"] = rel
                        return cached
                    except json.JSONDecodeError:
                        pass
        from scripts.research_data_mcp.consolidated_state import build_consolidated_state

        audit = build_consolidated_state(self, live=live)
        audit["found"] = True
        audit["live"] = live
        return audit

    def desk_health(self, *, live: bool = False) -> dict[str, Any]:
        import os
        import shutil

        from scripts.research_data_mcp.desk_auth import access_token_required
        from scripts.research_data_mcp.desk_brain import cursor_composer_available, desk_brain_mode
        from scripts.research_data_mcp.llm_client import llm_configured as legacy_llm_configured
        from scripts.research_data_mcp.procurement_constants import (
            MCP_TOOL_ACQUIRE,
            MCP_TOOL_CORE,
            MCP_TOOL_OPS,
        )
        from scripts.research_data_mcp.tool_handlers import MCP_TOOL_NAMES

        brain = desk_brain_mode(self.repo_root)
        composer_ok = cursor_composer_available()
        stats = self.orchestrator.stats()
        out: dict[str, Any] = {
            "status": "ok",
            "service": "research_library_api",
            "desk": {
                "brain": brain,
                "composer_configured": composer_ok,
                "composer_model": os.getenv("DESK_COMPOSER_MODEL", "default"),
                "llm_configured": composer_ok,
                "legacy_llm_configured": legacy_llm_configured(),
                "jobs": stats,
                "mcp_tools": {
                    "total": len(MCP_TOOL_NAMES),
                    "core": len(MCP_TOOL_CORE),
                    "acquire": len(MCP_TOOL_ACQUIRE),
                    "ops": len(MCP_TOOL_OPS),
                },
                "serve_ui": bool(getattr(self, "_serve_ui", False)),
                "desk_token_required": bool(access_token_required()),
            },
        }
        storage = getattr(self.orchestrator, "cfg", {}).get("storage") or {}
        from scripts.research_data_mcp.storage_tiers import storage_tiers_status

        tiers = storage_tiers_status(self.repo_root)
        out["desk"]["storage_tiers"] = tiers
        out["desk"]["archive"] = {
            "quota_tb": tiers["canonical"]["quota_tb"],
            "pool_tb": tiers["canonical"]["pool_tb"],
            "label": tiers["canonical"]["label"],
            "drive_root": tiers["canonical"]["drive_root"],
            "role": tiers["canonical"]["role"],
        }
        out["desk"]["bulk_storage"] = tiers["cache"]
        if live:
            from scripts.research_data_mcp.gdrive_verify import gdrive_verify_status

            out["desk"]["gdrive"] = gdrive_verify_status(self.repo_root)
        else:
            out["desk"]["gdrive"] = {
                "rclone_installed": bool(shutil.which("rclone")),
                "drive_root": tiers["canonical"]["drive_root"],
                "ready": None,
                "probe_skipped": "non_live_fast_path",
            }
        if live:
            try:
                st = self.cluster_status(live=False)
                out["desk"]["worker_pools"] = st.get("worker_pools") or {}
                # Local staging disk is ops-only — faculty UI shows GDrive archive quota instead.
                ops_disk = (st.get("disk") or {}).get("free_gb")
                if ops_disk is not None:
                    out["desk"]["staging_disk_free_gb"] = ops_disk
            except Exception as exc:
                out["desk"]["status_error"] = str(exc)

        try:
            from scripts.yzu_cluster.partition_lanes import partition_lanes

            rows = self.engine.list_datasets()
            lanes = partition_lanes(self.repo_root)
            instant_n = sum(1 for d in rows if str(d.get("analysis_readiness")) == "instant")
            metadata_n = sum(1 for d in rows if str(d.get("analysis_readiness")) == "metadata_search")
            plat = self.platform_state()
            out["datasets"] = len(rows)
            out["cluster"] = {
                "registry_datasets": len(rows),
                "instant_datasets": instant_n,
                "metadata_datasets": metadata_n,
                "professor_partitions": len(lanes),
                "lanes_complete": sum(1 for lane in lanes if lane.get("stage") == "complete"),
                "lanes_running": sum(1 for lane in lanes if lane.get("stage") == "running"),
                "refinitiv_frozen": True,
                "platform_state": plat.get("inventory") if plat.get("found") else None,
                "source_map": plat.get("source_map_summary") if plat.get("found") else None,
                "sources": plat.get("sources") if plat.get("found") else None,
                "access_scope": plat.get("access_scope_summary") if plat.get("found") else None,
                "entitlement_matrix": plat.get("entitlement_matrix") if plat.get("found") else None,
                "priority_access_gaps": plat.get("priority_access_gaps") if plat.get("found") else None,
                "dataset_coverage": plat.get("dataset_coverage_summary") if plat.get("found") else None,
                "proxy_coverage": plat.get("proxy_coverage") if plat.get("found") else None,
                "incomplete_items": plat.get("incomplete_items") if plat.get("found") else None,
                "documentation": plat.get("documentation") if plat.get("found") else {
                    "databank_state": "drive/docs/DATABANK_STATE.md",
                    "desk_activation": "drive/docs/DESK_ACTIVATION.md",
                },
                "lanes": [
                    {
                        "id": lane.get("id"),
                        "name": lane.get("name"),
                        "subtitle": lane.get("subtitle"),
                        "stage": lane.get("stage"),
                        "domain": (lane.get("detail") or {}).get("domain"),
                        "registry_datasets": len((lane.get("detail") or {}).get("registry_dataset_ids") or []),
                        "local_present": (lane.get("detail") or {}).get("local_present"),
                    }
                    for lane in lanes
                ],
            }
        except Exception as exc:
            out["cluster_error"] = str(exc)
        try:
            from scripts.research_data_mcp.desk_scale import scale_status
            from scripts.research_data_mcp.desk_runtime import runtime_status

            out["desk"]["scale"] = scale_status()
            out["desk"]["runtime"] = runtime_status(self.repo_root)
        except Exception as exc:
            out["desk"]["scale_error"] = str(exc)[:120]

        # Ops truth: lifetime failed/cancelled are not live failures; NVMe headroom is.
        hot = (out.get("desk") or {}).get("storage_tiers", {}).get("hot") or {}
        jobs = (out.get("desk") or {}).get("jobs") or {}
        warnings: list[str] = []
        if hot.get("headroom_ok") is False:
            warnings.append(
                f"nvme_headroom: {hot.get('free_gb')} GB free < min {hot.get('required_min_gb')} GB"
            )
            out["status"] = "degraded"
        if int(jobs.get("pending_approval") or 0) > 0:
            warnings.append(f"pending_approval={jobs.get('pending_approval')}")
        failed_recent = int(jobs.get("failed_recent") or 0)
        if failed_recent > 0:
            warnings.append(f"failed_recent_{jobs.get('recent_days', 7)}d={failed_recent}")
        if warnings:
            out["desk"]["ops_warnings"] = warnings
        return out

    def huggingface_search(self, query: str, *, limit: int = 8) -> dict[str, Any]:
        from scripts.research_data_mcp import hf_catalog

        return hf_catalog.search_datasets(query, limit=limit)

    def collect_huggingface_dataset(
        self,
        dataset_id: str,
        *,
        split: str = "train",
        auto_execute: bool = True,
        max_shards: int = 2,
    ) -> dict[str, Any]:
        """Collect HF dataset to procured cache, promote registry, archive to GDrive."""
        hf_id = str(dataset_id or "").strip().removeprefix("hf:")
        if not hf_id:
            raise ValueError("dataset_id is required (org/name or hf:org/name)")

        from scripts.hf_collect_dataset import registry_dataset_id

        reg_id = registry_dataset_id(hf_id)
        existing = self.engine.datasets.get(reg_id)
        if existing and str(existing.get("analysis_readiness")) == "instant":
            from scripts.research_data_mcp.procurement_fast import local_path_has_data

            local = str(existing.get("local_path") or existing.get("local_file") or "")
            if local and local_path_has_data(self.repo_root, local):
                return {
                    "reused": True,
                    "dataset_id": reg_id,
                    "handle": f"hf:{hf_id}",
                    "message": "already in registry with local bytes",
                }

        plan = {
            "job_type": "huggingface_collect",
            "hf_dataset_id": hf_id,
            "split": split,
            "max_shards": max_shards,
            "partition_id": "acquired.procured",
            "launchable": True,
            "timeout_seconds": 3600,
        }
        submitted = self.jobs.submit(
            f"Collect HF {hf_id}",
            plan,
            {"hf_dataset_id": hf_id, "search_goal": f"huggingface {hf_id}"},
            auto_approve=True,
        )
        job = submitted.get("job") or {}
        out: dict[str, Any] = {"plan": plan, "job": job, "hf_dataset_id": hf_id}
        if auto_execute and job.get("id"):
            finished = self.orchestrator.execute_job(job["id"])
            out["job"] = finished
            promo = (finished.get("result") or {}).get("registry_promotion") or []
            out["registry_promotion"] = promo
            if promo:
                self.reload_registry()
        return out

    def _enrich_collect_result(self, out: dict[str, Any], doi: str) -> dict[str, Any]:
        """Attach dataset card, pin, and registry promotion after successful DataCite collect."""
        from scripts.research_data_mcp.procured_dataset import build_card_from_campaign, make_handle, pin_dataset

        cid = out.get("campaign_id")
        plan = out.get("plan") or {}
        job = out.get("job") or {}
        if cid and job.get("status") == "completed":
            try:
                campaign = self.get_campaign(cid)
                card = build_card_from_campaign(
                    self.repo_root,
                    campaign,
                    job_get=self.get_yzu_job,
                    registry_path=self.registry_path,
                )
                out["dataset_card"] = card
                file_name = str(plan.get("datacite_file") or "")
                primary = card.get("primary_file") or {}
                pin_dataset(
                    self.repo_root,
                    handle=make_handle(doi=doi, file_name=file_name),
                    campaign_id=cid,
                    file_path=str(primary.get("path") or ""),
                    checksum=str(primary.get("checksum") or plan.get("datacite_checksum") or ""),
                    metadata={"title": card.get("title")},
                )
            except Exception as exc:
                out["dataset_card_error"] = str(exc)

            promoter = getattr(self.orchestrator, "registry_promoter", None)
            if promoter is not None:
                job_id = str(job.get("id") or "")
                full_job = job
                if job_id and not job.get("result"):
                    try:
                        full_job = self.get_yzu_job(job_id)
                    except Exception:
                        full_job = job
                try:
                    promoted = promoter.promote_datacite_collect(
                        {
                            "id": full_job.get("id") or job_id,
                            "status": "completed",
                            "plan": full_job.get("plan") or plan,
                            "result": full_job.get("result") or out.get("result") or {},
                        },
                        doi=doi,
                        campaign_id=str(cid or ""),
                    )
                    if promoted:
                        self.reload_registry()
                        from scripts.research_data_mcp.semantic_index import invalidate_semantic_index

                        invalidate_semantic_index()
                        flywheel = getattr(self.orchestrator, "collection_flywheel", None)
                        if flywheel is not None:
                            search_goal = ""
                            campaigns = getattr(self.orchestrator, "procurement_campaigns", None)
                            if cid and campaigns:
                                try:
                                    search_goal = str(campaigns.get(str(cid)).get("goal") or "")
                                except KeyError:
                                    pass
                            fw = flywheel.promote_after_collect(
                                {
                                    "id": full_job.get("id") or job_id,
                                    "status": "completed",
                                    "plan": full_job.get("plan") or plan,
                                    "result": full_job.get("result") or out.get("result") or {},
                                },
                                promoted,
                                campaign_id=str(cid or ""),
                                search_goal=search_goal,
                            )
                            if fw.get("curated_added") or fw.get("locators_added"):
                                out["flywheel"] = fw
                        out["registry_promotion"] = promoted
                except Exception as exc:
                    out["registry_promotion_error"] = str(exc)
        return out

    # --- cluster status ---
    def cluster_status(self, *, live: bool = False) -> dict[str, Any]:
        return self.yzu.status(live=live)

    def list_acquisitions(self, *, live: bool = False) -> dict[str, Any]:
        return {"acquisitions": self.yzu.acquisitions(live=live)}

    def cluster_components(self) -> dict[str, Any]:
        return self.orchestrator.components()

    def list_queue_tasks(self, *, runnable_only: bool = True) -> dict[str, Any]:
        return {"tasks": self.orchestrator.queue_tasks(runnable_only=runnable_only)}

    def list_schedules(self) -> list[dict[str, Any]]:
        return self.orchestrator.schedules()

    # --- synthesis research threads (durable construction state) ---
    def _synthesis_thread_store(self):
        from scripts.research_data_mcp.synthesis_thread_store import (
            SynthesisThreadStore,
            default_synthesis_thread_db,
        )

        store = getattr(self, "_synthesis_threads_store", None)
        if store is None:
            store = SynthesisThreadStore(default_synthesis_thread_db(self.repo_root))
            self._synthesis_threads_store = store
        return store

    # --- Discover collection intents (durable sourcing decisions) ---
    def _discover_intent_store(self):
        from scripts.research_data_mcp.discover_intent_store import DiscoverIntentStore, discover_intent_store_path

        store = getattr(self, "_discover_intents_store", None)
        if store is None:
            store = DiscoverIntentStore(discover_intent_store_path(self.repo_root))
            self._discover_intents_store = store
        return store

    def discover_intent_create(self, *, research_need: str, title: str = "", candidate: dict | None = None, session_id: str = "", user_email: str = "") -> dict:
        return self._discover_intent_store().create(research_need=research_need, title=title, candidate=candidate, session_id=session_id, user_email=user_email)

    def _discover_intent_with_job(self, intent: dict) -> dict:
        item = dict(intent)
        state = dict(item.get("state") or {})
        collection = dict(state.get("collection") or {})
        job_id = str(collection.get("job_id") or "")
        if job_id:
            job = self.jobs.get(job_id)
            result = job.get("result") or {}
            promotion = result.get("registry_promotion") or []
            registered_id = str(job.get("registered_dataset_id") or result.get("registered_dataset_id") or next((row.get("dataset_id") for row in promotion if row.get("dataset_id")), "") or "")
            collection["status"] = str(job.get("status") or collection.get("status") or "unknown")
            if registered_id:
                collection["registered_dataset_id"] = registered_id
            state["collection"] = collection
            item["job"] = job
        item["state"] = state
        return item

    def discover_intent_list(self, *, limit: int = 30, session_id: str = "") -> dict:
        rows = self._discover_intent_store().list(limit=limit, session_id=session_id)
        return {"intents": [self._discover_intent_with_job(row) for row in rows], "total": len(rows)}

    def discover_intent_get(self, intent_id: str) -> dict:
        return self._discover_intent_with_job(self._discover_intent_store().get(intent_id))

    def discover_intent_set_proposal(self, intent_id: str, proposal: dict) -> dict:
        return self._discover_intent_store().set_proposal(intent_id, proposal)

    def discover_intent_review(self, intent_id: str, *, decision: str, proposal_id: str, proposal_hash: str) -> dict:
        return self._discover_intent_store().review_proposal(intent_id, decision=decision, proposal_id=proposal_id, proposal_hash=proposal_hash)

    def discover_intent_select_route(self, intent_id: str, route_id: str) -> dict:
        return self._discover_intent_store().select_route(intent_id, route_id)

    def discover_intent_submit_collection(self, intent_id: str, *, limit: int = 200) -> dict:
        store = self._discover_intent_store()
        intent = store.get(intent_id)
        state = intent.get("state") or {}
        selected_id = str(state.get("selected_route_id") or "")
        route = next((row for row in state.get("routes") or [] if row.get("id") == selected_id), None)
        if not route:
            raise ValueError("select a reviewed acquisition route before collection")
        connector_id = str(route.get("connector_id") or "")
        if not connector_id:
            raise ValueError("selected route cannot be collected until it has a verified connector")
        from scripts.research_data_mcp.discover_collect_plan import resolve_discover_collect_plan

        plan = dict(
            resolve_discover_collect_plan(
                self.procurement,
                self.repo_root,
                connector_id=connector_id,
                source_id=str((state.get("candidate") or {}).get("source_id") or intent.get("source_id") or ""),
                limit=min(max(int(limit), 1), 2000),
                title=str(intent.get("title") or ""),
                url=str(route.get("url") or route.get("source_url") or ""),
                candidate_key=str(route.get("candidate_key") or (state.get("candidate") or {}).get("candidate_key") or ""),
            )
        )
        plan.update({"discover_intent_id": intent_id, "candidate_key": route.get("candidate_key") or (state.get("candidate") or {}).get("candidate_key") or "", "destination": route.get("destination") or plan.get("destination") or "", "refresh_strategy": route.get("refresh") or ""})
        submitted = self.jobs.submit(plan.get("title") or intent.get("title") or "Discover collection", plan, {"source": "discover_intent", "discover_intent_id": intent_id, "research_need": intent.get("research_need") or "", "route_id": selected_id, "connector_id": connector_id}, auto_approve=False)
        job = submitted.get("job") or {}
        linked = store.link_job(intent_id, job)
        return {"intent": self._discover_intent_with_job(linked), "job": job}

    # --- Discover Explore: sources, preview, refresh subscriptions, history ---
    def _discover_refresh_store(self):
        from scripts.research_data_mcp.discover_refresh_store import (
            DiscoverRefreshStore,
            discover_refresh_store_path,
        )

        store = getattr(self, "_discover_refresh_subscriptions_store", None)
        if store is None:
            store = DiscoverRefreshStore(discover_refresh_store_path(self.repo_root))
            self._discover_refresh_subscriptions_store = store
        return store

    def discover_source_search(
        self,
        query: str = "",
        *,
        limit: int = 24,
        live: bool = False,
        semantic: bool = False,
        prefer: str = "",
        prefer_embeddings: bool = True,
    ) -> dict[str, Any]:
        from scripts.research_data_mcp.discover_source_search import search_discover_sources

        return search_discover_sources(
            self.repo_root,
            query,
            limit=limit,
            live=live,
            semantic=semantic,
            prefer=prefer,
            prefer_embeddings=prefer_embeddings,
        )

    def discover_source_preview(
        self,
        *,
        source_id: str = "",
        connector_id: str = "",
        candidate_key: str = "",
        url: str = "",
        doi: str = "",
        dataset_id: str = "",
        name: str = "",
        limit: int = 5,
    ) -> dict[str, Any]:
        from scripts.research_data_mcp.discover_source_preview import preview_discover_source

        return preview_discover_source(
            self,
            source_id=source_id,
            connector_id=connector_id,
            candidate_key_value=candidate_key,
            url=url,
            doi=doi,
            dataset_id=dataset_id,
            name=name,
            limit=limit,
        )

    def discover_refresh_create(
        self,
        *,
        cadence: str = "manual",
        destination: str = "",
        intent_id: str = "",
        source_id: str = "",
        connector_id: str = "",
        candidate_key: str = "",
        enabled: bool = True,
        requested_schedule: str = "",
        schedule_note: str = "",
        timezone: str = "",
        schedule_spec: dict | None = None,
    ) -> dict[str, Any]:
        return self._discover_refresh_store().create(
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
            schedule_spec=schedule_spec,
        )

    def discover_refresh_list(self, *, limit: int = 50, intent_id: str = "", status: str = "") -> dict[str, Any]:
        rows = self._discover_refresh_store().list(limit=limit, intent_id=intent_id, status=status)
        return {"subscriptions": rows, "total": len(rows)}

    def discover_refresh_get(self, subscription_id: str) -> dict[str, Any]:
        return self._discover_refresh_store().get(subscription_id)

    def discover_refresh_pause(self, subscription_id: str) -> dict[str, Any]:
        return self._discover_refresh_store().pause(subscription_id)

    def discover_refresh_resume(self, subscription_id: str) -> dict[str, Any]:
        return self._discover_refresh_store().resume(subscription_id)

    def discover_refresh_stop(self, subscription_id: str) -> dict[str, Any]:
        return self._discover_refresh_store().stop(subscription_id)

    def discover_refresh_tick(
        self,
        *,
        limit: int = 10,
        force_subscription_id: str = "",
        force: bool = False,
        auto_approve_safe: bool = True,
    ) -> dict[str, Any]:
        from scripts.research_data_mcp.discover_refresh_runner import tick_discover_refresh

        return tick_discover_refresh(
            self,
            limit=limit,
            force_subscription_id=force_subscription_id,
            force=force,
            auto_approve_safe=auto_approve_safe,
        )

    def discover_history(
        self,
        *,
        limit: int = 50,
        kind: str = "",
        session_id: str = "",
        include_jobs: bool = True,
    ) -> dict[str, Any]:
        from scripts.research_data_mcp.discover_history import build_discover_history

        intents = self._discover_intent_store().list(limit=min(limit, 100), session_id=session_id)
        intents = [self._discover_intent_with_job(row) for row in intents]
        subscriptions = self._discover_refresh_store().list(limit=min(limit, 100))
        jobs: list[dict[str, Any]] = []
        if include_jobs:
            jobs = list((self.jobs.list(limit=min(limit * 2, 100)).get("jobs") or []))
        return build_discover_history(
            intents=intents,
            subscriptions=subscriptions,
            jobs=jobs,
            limit=limit,
            kind=kind,
            session_id=session_id,
        )

    def synthesis_thread_create(
        self,
        *,
        objective: str,
        title: str = "",
        session_id: str = "",
        conversation_id: str = "",
        required_grain: str = "",
        state: dict | None = None,
    ) -> dict:
        return self._synthesis_thread_store().create(
            objective=objective,
            title=title,
            session_id=session_id,
            conversation_id=conversation_id,
            required_grain=required_grain,
            state=state,
        )

    def synthesis_thread_list(self, *, limit: int = 30, session_id: str = "") -> dict:
        rows = self._synthesis_thread_store().list(limit=limit, session_id=session_id)
        return {"threads": rows, "total": len(rows)}

    def synthesis_thread_get(self, thread_id: str) -> dict:
        return self._synthesis_thread_store().get(thread_id)

    def synthesis_thread_apply_patch(
        self,
        thread_id: str,
        *,
        decision: str,
        operations: list | None = None,
        proposal_id: str = "",
        proposal_hash: str = "",
    ) -> dict:
        return self._synthesis_thread_store().apply_patch_decision(
            thread_id,
            decision=decision,
            operations=operations,
            proposal_id=proposal_id,
            proposal_hash=proposal_hash,
        )

    def synthesis_thread_set_proposal(self, thread_id: str, proposal: dict | None) -> dict:
        return self._synthesis_thread_store().set_proposal(thread_id, proposal)

    def synthesis_thread_propose_state(
        self,
        thread_id: str,
        *,
        proposal_id: str,
        title: str,
        summary: str,
        operations: list,
        reason: str = "",
        impact: list | None = None,
        node_id: str = "",
        execution_spec: dict | None = None,
    ) -> dict:
        """Persist a Composer proposal for explicit researcher review only."""
        proposal = {
            "id": proposal_id,
            "title": title,
            "summary": summary,
            "operations": operations,
        }
        if reason:
            proposal["reason"] = reason
        if impact is not None:
            proposal["impact"] = impact
        if node_id:
            proposal["nodeId"] = node_id
        if execution_spec is not None:
            from scripts.research_data_mcp.synthesis_executor import preflight_execution_spec

            preflight = preflight_execution_spec(Path(self.repo_root), dict(execution_spec))
            if not preflight.get("ok"):
                issues = preflight.get("issues") or []
                detail = "; ".join(
                    f"{i.get('code')}:{i.get('column') or i.get('columns') or i.get('dataset_id') or i.get('detail')}"
                    for i in issues[:6]
                )
                raise ValueError(f"execution_spec preflight failed: {detail}")
            proposal["execution_spec"] = preflight["execution_spec"]
            proposal["execution_preflight"] = {
                "ok": True,
                "warnings": preflight.get("warnings") or [],
            }
        return self._synthesis_thread_store().set_proposal(thread_id, proposal)

    def synthesis_thread_discover_handoff(self, thread_id: str) -> dict:
        handoff = self._synthesis_thread_store().discover_handoff(thread_id)
        intents = list(handoff.get("collect_intents") or [])
        enriched: list[dict] = []
        for intent in intents:
            row = dict(intent)
            if not row.get("resolvable_hint"):
                row["resolvable"] = False
                enriched.append(row)
                continue
            try:
                from scripts.research_data_mcp.discover_collect_plan import (
                    resolve_discover_collect_plan,
                )

                plan = resolve_discover_collect_plan(
                    self.procurement,
                    self.repo_root,
                    connector_id=str(row.get("connector_id") or ""),
                    source_id=str(row.get("source_id") or ""),
                    candidate_key=str(row.get("candidate_key") or ""),
                    title=str(row.get("label") or row.get("evidence_id") or ""),
                    limit=8,
                )
                row["resolvable"] = True
                row["plan_preview"] = {
                    "job_type": plan.get("job_type"),
                    "title": plan.get("title"),
                    "collect_resolution": plan.get("collect_resolution"),
                    "item_count": len(plan.get("items") or ([] if not plan.get("url") else [plan.get("url")])),
                    "public_direct_url": bool(plan.get("public_direct_url")),
                }
            except Exception as exc:  # noqa: BLE001
                row["resolvable"] = False
                row["reason"] = str(exc)[:400]
            enriched.append(row)
        handoff["collect_intents"] = enriched
        handoff["resolvable_collect_count"] = sum(1 for r in enriched if r.get("resolvable"))
        return handoff

    def synthesis_thread_collect_missing(
        self,
        thread_id: str,
        *,
        evidence_ids: list[str] | None = None,
        auto_approve_safe: bool = True,
        limit: int = 8,
    ) -> dict:
        """Submit Discover collect jobs for resolvable missing-evidence intents.

        Does not invent plans: only resolves identities already on the thread.
        """
        handoff = self.synthesis_thread_discover_handoff(thread_id)
        wanted = {str(x) for x in (evidence_ids or []) if str(x).strip()}
        submitted: list[dict] = []
        skipped: list[dict] = []
        from scripts.research_data_mcp.discover_collect_plan import resolve_discover_collect_plan
        from scripts.research_data_mcp.procurement_auto_approve import should_auto_approve_plan

        for intent in handoff.get("collect_intents") or []:
            eid = str(intent.get("evidence_id") or "")
            if wanted and eid not in wanted:
                skipped.append({"evidence_id": eid, "reason": "not_selected"})
                continue
            if not intent.get("resolvable"):
                skipped.append(
                    {
                        "evidence_id": eid,
                        "reason": intent.get("reason") or "not_resolvable",
                    }
                )
                continue
            try:
                plan = dict(
                    resolve_discover_collect_plan(
                        self.procurement,
                        self.repo_root,
                        connector_id=str(intent.get("connector_id") or ""),
                        source_id=str(intent.get("source_id") or ""),
                        candidate_key=str(intent.get("candidate_key") or ""),
                        title=str(intent.get("label") or eid),
                        limit=min(max(int(limit or 8), 1), 25),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                skipped.append({"evidence_id": eid, "reason": f"plan:{exc}"})
                continue
            plan["synthesis_thread_id"] = thread_id
            plan["discover_handoff"] = True
            approve = False
            if auto_approve_safe:
                try:
                    approve = bool(
                        should_auto_approve_plan(
                            plan, self.repo_root, orchestrator=self.orchestrator
                        )
                    )
                except Exception:  # noqa: BLE001
                    approve = False
            request = {
                "source": "synthesis_discover_handoff",
                "synthesis_thread_id": thread_id,
                "evidence_id": eid,
                "connector_id": intent.get("connector_id") or "",
                "source_id": intent.get("source_id") or "",
                "candidate_key": intent.get("candidate_key") or "",
            }
            out = self.jobs.submit(
                plan.get("title") or f"Collect missing {eid}",
                plan,
                request,
                auto_approve=approve,
            )
            job = out.get("job") if isinstance(out, dict) else None
            if not isinstance(job, dict) or not job.get("id"):
                skipped.append(
                    {
                        "evidence_id": eid,
                        "reason": (out.get("error") if isinstance(out, dict) else "submit_failed"),
                    }
                )
                continue
            submitted.append(
                {
                    "evidence_id": eid,
                    "job_id": job.get("id"),
                    "job_status": job.get("status"),
                    "auto_approved": approve,
                    "plan": plan.get("job_type") or plan.get("collect_resolution"),
                }
            )
        return {
            "thread_id": thread_id,
            "submitted": submitted,
            "skipped": skipped,
            "fake_collection": False,
            "note": "Jobs created only from resolvable missing-evidence identities.",
        }

    def synthesis_thread_materialisation(self, thread_id: str) -> dict:
        return self._synthesis_thread_store().materialisation(thread_id)

    def synthesis_thread_record_execution(self, thread_id: str, job: dict) -> dict:
        thread = self._synthesis_thread_store().get(thread_id)
        state = thread.get("state") or {}
        execution = state.get("execution") or {}
        plan = job.get("plan") or {}
        result = job.get("result") or {}
        materialized = result.get("materialized") or {}
        output_id = str(materialized.get("dataset_id") or "")
        promotion = result.get("registry_promotion") or []
        drive = result.get("drive_finalize") or {}
        if job.get("status") != "completed" or plan.get("job_type") != "synthesis_execute":
            raise ValueError("only completed synthesis execution jobs can register output")
        if plan.get("thread_id") != thread_id or execution.get("job_id") != job.get("id"):
            raise ValueError("execution job does not match the active synthesis thread revision")
        if plan.get("accepted_spec_hash") != state.get("accepted_spec_hash") or execution.get("spec_hash") != state.get("accepted_spec_hash"):
            raise ValueError("execution job does not match the accepted synthesis spec revision")
        if output_id != execution.get("output_dataset_id") or not result.get("output_manifest_id"):
            raise ValueError("execution output identity or manifest is missing")
        if not drive.get("ok") or not any(row.get("dataset_id") == output_id for row in promotion):
            raise ValueError("execution lacks verified Drive and matching registry promotion evidence")
        registry_doc = json.loads((self.repo_root / "config/research_query_registry.json").read_text(encoding="utf-8"))
        row = next((item for item in registry_doc.get("datasets") or [] if item.get("dataset_id") == output_id), None)
        if not row or not row.get("canonical_remote"):
            raise ValueError("registered output could not be read back from the registry")
        return self._synthesis_thread_store().record_execution(thread_id, job, verified=True)

    def synthesis_thread_record_execution_failure(self, thread_id: str, job_id: str, error: str) -> dict:
        return self._synthesis_thread_store().record_execution_failure(thread_id, job_id, error)

    def synthesis_thread_submit_execution(self, thread_id: str) -> dict:
        """Submit an accepted, bounded execution spec for researcher approval."""
        from scripts.research_data_mcp.synthesis_executor import validate_execution_spec

        thread = self._synthesis_thread_store().get(thread_id)
        state = thread.get("state") or {}
        spec = validate_execution_spec(dict(state.get("execution_spec") or {}))
        accepted_hash = str(state.get("accepted_spec_hash") or "")
        if not accepted_hash:
            raise ValueError("execution spec has not been accepted as a reviewed revision")
        execution = state.get("execution") or {}
        if execution.get("spec_hash") == accepted_hash and execution.get("job_id"):
            existing = self.jobs.get(str(execution["job_id"]))
            if existing.get("status") in {"pending_approval", "queued", "running", "completed"}:
                return {"job": existing, "plan": existing.get("plan") or {}, "idempotent": True}
        registry_doc = json.loads((self.repo_root / "config/research_query_registry.json").read_text(encoding="utf-8"))
        if any(row.get("dataset_id") == spec["output_dataset_id"] for row in registry_doc.get("datasets") or []):
            raise ValueError("output_dataset_id already exists; create a new versioned synthesis asset")
        plan = {
            "title": f"Synthesis: {thread.get('title') or spec['output_dataset_id']}",
            "job_type": "synthesis_execute",
            "thread_id": thread_id,
            "execution_spec": spec,
            "accepted_spec_hash": accepted_hash,
            "dataset_id": spec["output_dataset_id"],
            "partition_id": "derived.research-panels",
            "launchable": True,
        }
        submitted = self.jobs.submit(
            plan["title"],
            plan,
            {
                "thread_id": thread_id,
                "objective": thread.get("objective") or "",
                "search_goal": thread.get("objective") or "",
            },
            auto_approve=False,
        )
        job = submitted.get("job")
        if job:
            next_state = dict(state)
            next_state["execution"] = {
                "status": "pending_approval",
                "job_id": job.get("id"),
                "output_dataset_id": spec["output_dataset_id"],
                "spec_hash": accepted_hash,
            }
            self._synthesis_thread_store()._save_state(thread_id, next_state)
        return submitted

    def synthesis_thread_link_conversation(
        self,
        thread_id: str,
        *,
        session_id: str,
        conversation_id: str = "",
    ) -> dict:
        return self._synthesis_thread_store().link_conversation(
            thread_id,
            session_id=session_id,
            conversation_id=conversation_id,
        )

    # --- synthesis (multi-source join) ---
    def synthesis_list_profiles(self) -> dict[str, Any]:
        from scripts.research_data_mcp.synthesis.engine import list_synthesis_profiles

        return list_synthesis_profiles(Path(self.repo_root))

    def synthesis_get_latest(self, profile_id: str) -> dict[str, Any]:
        from scripts.research_data_mcp.synthesis.engine import get_latest_synthesis

        hit = get_latest_synthesis(Path(self.repo_root), profile_id)
        if not hit:
            return {"found": False, "profile_id": profile_id}
        return {"found": True, **hit}

    def synthesis_run(
        self,
        profile_id: str,
        *,
        preview_limit: int = 50,
        gap_limit: int = 100,
    ) -> dict[str, Any]:
        from scripts.research_data_mcp.synthesis.engine import run_synthesis

        return run_synthesis(
            Path(self.repo_root),
            profile_id,
            preview_limit=preview_limit,
            gap_limit=gap_limit,
        )

    def synthesis_pair(self, left_dataset_id: str, right_dataset_id: str) -> dict[str, Any]:
        from scripts.research_data_mcp.synthesis.engine import run_synthesis_pair

        return run_synthesis_pair(
            Path(self.repo_root),
            left_dataset_id,
            right_dataset_id,
            describe_fn=self.describe_dataset,
        )

    # --- jobs (canonical) ---
    def submit_yzu_job(
        self,
        plan: dict[str, Any],
        *,
        title: str = "Library job",
        request: dict[str, Any] | None = None,
        auto_approve: bool = False,
    ) -> dict[str, Any]:
        return self.jobs.submit(title, plan, request, auto_approve=auto_approve)

    def submit_job(self, title: str, plan: dict[str, Any], request: dict[str, Any] | None = None, *, auto_approve: bool = False) -> dict[str, Any]:
        return self.jobs.submit(title, plan, request, auto_approve=auto_approve)

    def approve_yzu_job(self, job_id: str) -> dict[str, Any]:
        """Researcher desk approve path.

        Synthesis jobs are allowed here (History / approve button). They must
        still never pass approve-safe bulk policy or Composer/agent tool wrappers.
        """
        return self.jobs.approve(job_id)

    def cancel_yzu_job(self, job_id: str) -> dict[str, Any]:
        return self.jobs.cancel(job_id)

    def get_yzu_job(self, job_id: str) -> dict[str, Any]:
        return self.jobs.get(job_id)

    def list_yzu_jobs(self, limit: int = 30, status: str = "") -> dict[str, Any]:
        return self.jobs.list(limit, status)

    def run_schedule(self, schedule_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        return self.jobs.run_schedule(schedule_id, dry_run=dry_run)

    def wait_for_job(self, job_id: str, **kwargs: Any) -> dict[str, Any]:
        import time

        timeout = float(kwargs.get("timeout_seconds", 600.0))
        poll = float(kwargs.get("poll_seconds", 2.0))
        tick_worker = bool(kwargs.get("tick_worker", True))
        deadline = time.time() + timeout
        terminal = {"completed", "failed", "cancelled"}
        while time.time() < deadline:
            job = self.get_yzu_job(job_id)
            if job.get("status") in terminal:
                return job
            if tick_worker:
                self.jobs.tick()
            else:
                time.sleep(poll)
        raise TimeoutError(f"job {job_id} did not finish within {timeout}s")

    def archive_to_gdrive(self, local_path: str, **kwargs: Any) -> dict[str, Any]:
        plan = self.jobs.archive_plan(local_path, remote_suffix=kwargs.get("remote_suffix", ""), verify=kwargs.get("verify", True))
        return self.jobs.submit(kwargs.get("title", "Archive to GDrive"), plan, auto_approve=kwargs.get("auto_approve", True))

    # legacy aliases
    list_jobs = list_yzu_jobs
    get_job = get_yzu_job
    approve_job = approve_yzu_job
    cancel_job = cancel_yzu_job

    def probe_source(self, url: str, name: str = "") -> dict[str, Any]:
        return self.procurement.probe(url, name)

    def list_connectors(self, limit: int = 50) -> dict[str, Any]:
        return {"connectors": self.procurement.store.list(min(max(limit, 1), 200))}

    def approve_connector(self, connector_id: str) -> dict[str, Any]:
        return self.procurement.store.approve(connector_id)

    def prepare_collection(self, connector_id: str, limit: int = 200) -> dict[str, Any]:
        return self.procurement.collection_plan(connector_id, limit=limit)

    def submit_collection_job(self, connector_id: str, limit: int = 200) -> dict[str, Any]:
        return self.agent.collect_connector(connector_id, limit=limit)

    def agent_status(self) -> dict[str, Any]:
        return self.agent.status()

    @staticmethod
    def parse_params_json(params_json: str) -> dict[str, Any]:
        try:
            params = json.loads(params_json or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"params_json must be valid JSON: {exc}") from exc
        if not isinstance(params, dict):
            raise ValueError("params_json must decode to a JSON object")
        return params


class PassivePlanner:
    def __init__(self, gateway: Any) -> None:
        self.gateway = gateway

    def wants_datacite_collect(self, message: str, context: dict[str, Any] | None = None) -> bool:
        ctx = context or {}
        if ctx.get("doi"):
            return True
        import re
        return bool(re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", message, re.I))

    def plan_datacite_collect(self, message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ctx = context or {}
        doi = ctx.get("doi")
        if not doi:
            import re
            m = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", message, re.I)
            doi = m.group(0) if m else ""
        if not doi:
            return {"launchable": False, "error": "No DOI found"}
        try:
            resolved = self.gateway.datacite_resolve_repository(doi)
            if resolved.get("error"):
                return {"launchable": False, "error": resolved["error"]}
            return {
                "launchable": True,
                "datacite_doi": doi,
                "url": resolved.get("landing_url") or "",
                "title": resolved.get("title") or doi,
                "items": resolved.get("files") or [],
            }
        except Exception as exc:
            return {"launchable": False, "error": str(exc)}

    def wants_procurement(self, message: str) -> bool:
        return False

    def plan_from_catalog(self, message: str, advice: Any = None, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return None

    def plan_from_advice(self, advice: Any, message: str) -> dict[str, Any] | None:
        return None

    def _extract_url(self, message: str) -> str | None:
        import re
        m = re.search(r"https?://[^\s/$.?#].[^\s]*", message, re.I)
        return m.group(0) if m else None

    def wants_collect(self, message: str) -> bool:
        return False

    def plan_immediate_collect(self, message: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
        url = self._extract_url(message)
        if url:
            return {
                "launchable": True,
                "job_type": "source_probe",
                "url": url,
                "title": f"Probe URL: {url}",
            }
        return None
