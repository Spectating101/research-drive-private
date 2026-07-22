#!/usr/bin/env python3
"""HTTP route dispatch — thin faculty HTTP over MCP/gateway stack.

Canonical surfaces:
  /library/*     faculty desk + jobs + chat
  /library/extensions/*  same tools as MCP (devtools)
  /datasets      registry list (gateway.search)
  /yzu/*         cluster ops + POST job submit only

Composer agents should use MCP stdio tools, not duplicate HTTP paths.
"""

from __future__ import annotations

from typing import Any, Callable

from scripts.research_data_mcp.bootstrap import ResearchLibraryStack

Handler = Callable[[ResearchLibraryStack, dict[str, str], dict[str, Any], dict[str, str]], dict[str, Any]]

ROUTE_CATALOG: list[dict[str, str]] = [
    {"method": "GET", "path": "/health", "handler": "health"},
    {"method": "GET", "path": "/datasets", "handler": "datasets"},
    {"method": "GET", "path": "/datasets/{id}", "handler": "dataset_describe"},
    {"method": "GET", "path": "/query/{id}", "handler": "dataset_query"},
    {"method": "GET", "path": "/library/catalog", "handler": "library_catalog"},
    {"method": "GET", "path": "/library/search", "handler": "library_unified_search"},
    {"method": "GET", "path": "/library/discover", "handler": "library_discover"},
    {"method": "POST", "path": "/library/discover/semantic", "handler": "library_discover_semantic"},
    {"method": "GET", "path": "/library/discover/web", "handler": "library_discover_web"},
    {"method": "POST", "path": "/library/discover/probe", "handler": "library_discover_probe"},
    {"method": "POST", "path": "/library/discover/collect", "handler": "library_discover_collect"},
    {"method": "GET", "path": "/library/discover/intents", "handler": "library_discover_intents_list"},
    {"method": "POST", "path": "/library/discover/intents", "handler": "library_discover_intents_create"},
    {"method": "GET", "path": "/library/discover/intents/{intent_id}", "handler": "library_discover_intent_get"},
    {"method": "POST", "path": "/library/discover/intents/{intent_id}/proposal", "handler": "library_discover_intent_proposal"},
    {"method": "POST", "path": "/library/discover/intents/{intent_id}/review", "handler": "library_discover_intent_review"},
    {"method": "POST", "path": "/library/discover/intents/{intent_id}/route", "handler": "library_discover_intent_route"},
    {"method": "POST", "path": "/library/discover/intents/{intent_id}/submit", "handler": "library_discover_intent_submit"},
    {"method": "GET", "path": "/library/discover/sources", "handler": "library_discover_sources"},
    {"method": "POST", "path": "/library/discover/sources/preview", "handler": "library_discover_source_preview"},
    {"method": "GET", "path": "/library/discover/sources/preview", "handler": "library_discover_source_preview"},
    {"method": "GET", "path": "/library/discover/subscriptions", "handler": "library_discover_subscriptions_list"},
    {"method": "POST", "path": "/library/discover/subscriptions", "handler": "library_discover_subscriptions_create"},
    {"method": "POST", "path": "/library/discover/subscriptions/tick", "handler": "library_discover_subscriptions_tick"},
    {"method": "GET", "path": "/library/discover/subscriptions/{subscription_id}", "handler": "library_discover_subscription_get"},
    {"method": "POST", "path": "/library/discover/subscriptions/{subscription_id}/pause", "handler": "library_discover_subscription_pause"},
    {"method": "POST", "path": "/library/discover/subscriptions/{subscription_id}/resume", "handler": "library_discover_subscription_resume"},
    {"method": "POST", "path": "/library/discover/subscriptions/{subscription_id}/stop", "handler": "library_discover_subscription_stop"},
    {"method": "POST", "path": "/library/discover/subscriptions/{subscription_id}/run", "handler": "library_discover_subscription_run"},
    {"method": "GET", "path": "/library/discover/history", "handler": "library_discover_history"},
    {"method": "GET", "path": "/library/overview", "handler": "library_overview"},
    {"method": "GET", "path": "/library/partitions", "handler": "library_partitions"},
    {"method": "GET", "path": "/library/browse", "handler": "library_browse"},
    {"method": "GET", "path": "/library/ops", "handler": "library_ops"},
    {"method": "POST", "path": "/library/advise", "handler": "library_advise"},
    {"method": "GET", "path": "/library/platform/state", "handler": "library_platform_state"},
    {"method": "GET", "path": "/library/source-map", "handler": "library_source_map"},
    {"method": "GET", "path": "/library/access-scope", "handler": "library_access_scope"},
    {"method": "GET", "path": "/library/dataset-coverage", "handler": "library_dataset_coverage"},
    {"method": "GET", "path": "/library/consolidated", "handler": "library_consolidated"},
    {"method": "GET", "path": "/library/faculty/profile", "handler": "library_faculty_profile"},
    {"method": "GET", "path": "/library/synthesis/profiles", "handler": "library_synthesis_profiles"},
    {"method": "GET", "path": "/library/synthesis/threads", "handler": "library_synthesis_threads_list"},
    {"method": "POST", "path": "/library/synthesis/threads", "handler": "library_synthesis_threads_create"},
    {"method": "GET", "path": "/library/synthesis/threads/{thread_id}", "handler": "library_synthesis_thread_get"},
    {"method": "POST", "path": "/library/synthesis/threads/{thread_id}/patches", "handler": "library_synthesis_thread_patch"},
    {"method": "POST", "path": "/library/synthesis/threads/{thread_id}/proposal", "handler": "library_synthesis_thread_set_proposal"},
    {"method": "POST", "path": "/library/synthesis/threads/{thread_id}/conversation", "handler": "library_synthesis_thread_link_conversation"},
    {"method": "GET", "path": "/library/synthesis/threads/{thread_id}/discover-handoff", "handler": "library_synthesis_thread_discover_handoff"},
    {"method": "POST", "path": "/library/synthesis/threads/{thread_id}/collect-missing", "handler": "library_synthesis_thread_collect_missing"},
    {"method": "GET", "path": "/library/synthesis/threads/{thread_id}/materialisation", "handler": "library_synthesis_thread_materialisation"},
    {"method": "POST", "path": "/library/synthesis/threads/{thread_id}/execute", "handler": "library_synthesis_thread_execute"},
    {"method": "GET", "path": "/library/synthesis/{id}", "handler": "library_synthesis_get"},
    {"method": "POST", "path": "/library/synthesis/run", "handler": "library_synthesis_run"},
    {"method": "POST", "path": "/library/synthesis/pair", "handler": "library_synthesis_pair"},
    {"method": "GET", "path": "/library/desk/brief", "handler": "library_desk_brief"},
    {"method": "GET", "path": "/library/desk/resources", "handler": "library_desk_resources"},
    {"method": "POST", "path": "/library/desk/warm", "handler": "library_desk_warm"},
    {"method": "POST", "path": "/library/chat", "handler": "library_procure_chat"},
    {"method": "POST", "path": "/library/chat/stream", "handler": "library_procure_chat_stream"},
    {"method": "GET", "path": "/library/chat/{session_id}", "handler": "library_procure_chat_session"},
    {"method": "GET", "path": "/library/campaigns", "handler": "library_campaigns"},
    {"method": "GET", "path": "/library/campaigns/{id}/artifacts", "handler": "library_campaign_artifacts"},
    {"method": "GET", "path": "/library/campaigns/{id}/download", "handler": "library_campaign_download"},
    {"method": "POST", "path": "/library/datacite/resolve", "handler": "library_datacite_resolve"},
    {"method": "POST", "path": "/library/datacite/collect", "handler": "library_datacite_collect"},
    {"method": "POST", "path": "/library/datacite/enrich", "handler": "library_datacite_enrich"},
    {"method": "POST", "path": "/library/licenses/approve", "handler": "library_license_approve"},
    {"method": "GET", "path": "/library/credentials/profiles", "handler": "library_credential_profiles"},
    {"method": "POST", "path": "/library/datacite/search-resolve", "handler": "library_datacite_search_resolve"},
    {"method": "POST", "path": "/library/campaigns/{id}/add-datacite", "handler": "library_campaign_add_datacite"},
    {"method": "GET", "path": "/library/datasets/card/{ref}", "handler": "library_dataset_card"},
    {"method": "GET", "path": "/library/datasets/open", "handler": "library_dataset_open"},
    {"method": "GET", "path": "/library/pins", "handler": "library_pins_list"},
    {"method": "POST", "path": "/library/pins", "handler": "library_pins_create"},
    {"method": "GET", "path": "/library/campaigns/{id}", "handler": "library_campaign_get"},
    {"method": "POST", "path": "/library/campaigns/{id}/approve-collect", "handler": "library_campaign_approve_collect"},
    {"method": "POST", "path": "/library/campaigns/{id}/resume", "handler": "library_campaign_resume"},
    {"method": "POST", "path": "/library/jobs", "handler": "library_submit_job"},
    {"method": "POST", "path": "/library/jobs/{id}/approve", "handler": "job_approve"},
    {"method": "POST", "path": "/library/jobs/{id}/cancel", "handler": "job_cancel"},
    {"method": "POST", "path": "/library/jobs/approve-safe", "handler": "library_jobs_approve_safe"},
    {"method": "GET", "path": "/library/jobs", "handler": "job_list"},
    {"method": "GET", "path": "/library/jobs/{id}", "handler": "job_get"},
    {"method": "POST", "path": "/library/archive", "handler": "library_archive"},
    {"method": "GET", "path": "/library/extensions/tools", "handler": "extension_tool_catalog"},
    {"method": "GET", "path": "/library/extensions/datacite/search", "handler": "extension_datacite_search"},
    {"method": "GET", "path": "/library/extensions/datacite/doi/{doi}", "handler": "extension_datacite_get"},
    {"method": "GET", "path": "/library/extensions/huggingface/search", "handler": "extension_hf_search"},
    {"method": "GET", "path": "/library/extensions/bigquery/status", "handler": "extension_bigquery_status"},
    {"method": "POST", "path": "/library/extensions/bigquery/dry-run", "handler": "extension_bigquery_dry_run"},
    {"method": "GET", "path": "/yzu/status", "handler": "yzu_status"},
    {"method": "GET", "path": "/yzu/acquisitions", "handler": "yzu_acquisitions"},
    {"method": "GET", "path": "/yzu/workers", "handler": "yzu_workers"},
    {"method": "GET", "path": "/yzu/activity", "handler": "yzu_activity"},
    {"method": "GET", "path": "/yzu/components", "handler": "yzu_components"},
    {"method": "GET", "path": "/yzu/queue/tasks", "handler": "yzu_queue_tasks"},
    {"method": "GET", "path": "/yzu/schedules", "handler": "yzu_schedules"},
    {"method": "POST", "path": "/yzu/jobs", "handler": "yzu_submit_job"},
    {"method": "POST", "path": "/yzu/jobs/approve-safe", "handler": "yzu_approve_safe_jobs"},
    {"method": "POST", "path": "/yzu/jobs/{id}/cancel", "handler": "job_cancel"},
    {"method": "POST", "path": "/yzu/schedules/{id}/run", "handler": "yzu_run_schedule"},
]


def _live_flag(query: dict[str, str]) -> bool:
    return query.get("live", "").lower() in {"1", "true", "yes"}


def _query_int(query: dict[str, str], key: str, default: int) -> int:
    raw = query.get(key)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _full_flag(query: dict[str, str]) -> bool:
    return query.get("full", "").lower() in {"1", "true", "yes"}


def _compact_probe_response(out: dict[str, Any]) -> dict[str, Any]:
    """Trim probe payloads for the faculty UI; connector store keeps the full spec."""
    if not isinstance(out, dict):
        return out
    connector = out.get("connector")
    if not isinstance(connector, dict):
        return out
    spec = connector.get("spec")
    if not isinstance(spec, dict):
        return out

    sample = spec.get("sample")
    compact_sample: dict[str, Any] | None = None
    if isinstance(sample, dict):
        compact_sample = {
            key: sample.get(key)
            for key in ("format", "top_level", "estimated_sample_rows", "row_count")
            if sample.get(key) is not None
        }
        fields = sample.get("fields")
        if isinstance(fields, list):
            compact_sample["field_count"] = len(fields)
            compact_sample["fields"] = fields[:40]
            compact_sample["fields_truncated"] = len(fields) > 40
        columns = sample.get("columns")
        if isinstance(columns, list):
            compact_sample["columns"] = columns[:40]
            compact_sample["columns_truncated"] = len(columns) > 40

    files = spec.get("discovered_files")
    compact_files: list[Any] = []
    if isinstance(files, list):
        for row in files[:20]:
            if not isinstance(row, dict):
                compact_files.append(row)
                continue
            compact_files.append(
                {
                    key: row.get(key)
                    for key in ("url", "href", "title", "name", "content_type", "size", "bytes")
                    if row.get(key) is not None
                }
            )

    compact_spec = {
        key: spec.get(key)
        for key in (
            "connector_id",
            "name",
            "source_url",
            "host",
            "access_mode",
            "content_type",
            "content_length",
            "etag",
            "last_modified",
            "sample_bytes",
            "sample_truncated",
            "recommended_action",
            "http_status",
            "probed_at",
        )
        if spec.get(key) is not None
    }
    if compact_sample is not None:
        compact_spec["sample"] = compact_sample
    compact_spec["discovered_files"] = compact_files
    compact_spec["discovered_file_count"] = len(files) if isinstance(files, list) else len(compact_files)
    if isinstance(spec.get("pagination"), dict):
        compact_spec["pagination"] = spec["pagination"]

    compact_connector = {
        key: connector.get(key)
        for key in ("id", "connector_id", "created_at", "updated_at", "status", "name", "source_url")
        if connector.get(key) is not None
    }
    compact_connector.setdefault("connector_id", connector.get("id") or compact_spec.get("connector_id"))
    compact_connector["spec"] = compact_spec

    compact = dict(out)
    compact["connector"] = compact_connector
    compact["compacted"] = True
    return compact


def _match(path: str, pattern: str) -> dict[str, str] | None:
    p_parts = path.strip("/").split("/")
    pat_parts = pattern.strip("/").split("/")
    if len(p_parts) != len(pat_parts):
        return None
    params: dict[str, str] = {}
    for segment, pat in zip(p_parts, pat_parts):
        if pat.startswith("{") and pat.endswith("}"):
            params[pat[1:-1]] = segment
        elif segment != pat:
            return None
    return params


def _resolve(path: str, method: str) -> tuple[str | None, dict[str, str]]:
    for row in ROUTE_CATALOG:
        if row["method"] != method:
            continue
        params = _match(path, row["path"])
        if params is not None:
            return row["handler"], params
    return None, {}


def _handlers() -> dict[str, Handler]:
    def _activity(stack, action: str, target: str, **kwargs: Any) -> None:
        try:
            from scripts.research_data_mcp.desk_activity import record_activity

            record_activity(action, target, repo_root=stack.gateway.repo_root, **kwargs)
        except Exception:
            pass

    def health(stack, query, payload, params):
        # Soft cadence nudge — safe no-op when nothing is due / tick busy.
        try:
            stack.gateway.discover_refresh_tick(limit=3, auto_approve_safe=True)
        except Exception:  # noqa: BLE001
            pass
        return stack.gateway.desk_health(live=_live_flag(query))

    def datasets(stack, query, payload, params):
        q = str(query.get("q") or query.get("query") or "").strip()
        return stack.gateway.list_datasets(
            q=q,
            readiness=str(query.get("readiness") or "").strip(),
            access_shape=str(query.get("access_shape") or query.get("access_mode") or "").strip(),
            limit=_query_int(query, "limit", 50),
        )

    def dataset_describe(stack, query, payload, params):
        return stack.gateway.describe_dataset(params["id"])

    def dataset_query(stack, query, payload, params):
        params_out = dict(query)
        if "limit" in params_out:
            params_out["limit"] = _query_int(query, "limit", 50)
        out = stack.gateway.query_dataset(params["id"], params_out)
        _activity(
            stack,
            "query",
            params["id"],
            meta={"limit": query.get("limit"), "rows": len(out.get("rows") or []) if isinstance(out, dict) else None},
        )
        return out

    def library_catalog(stack, query, payload, params):
        return stack.gateway.procurement_catalog(q=query.get("q", ""), limit=int(query.get("limit", 50)))

    def library_unified_search(stack, query, payload, params):
        q = str(query.get("q") or query.get("query") or "")
        email = str(query.get("email") or "")
        limit = int(query.get("limit", 12))
        return stack.gateway.unified_search_with_profile(
            q,
            email=email.strip(),
            limit=limit,
            include_hf=query.get("include_hf", "1") not in {"0", "false"},
            include_datacite=query.get("include_datacite", "1") not in {"0", "false"},
            resolve_datacite=query.get("resolve_datacite", "0") in {"1", "true", "yes"},
            max_file_bytes=int(query.get("max_file_bytes") or 50_000_000),
            skip_discover=query.get("skip_discover", "0") in {"1", "true", "yes"},
        )

    def library_discover(stack, query, payload, params):
        q = str(query.get("q") or query.get("query") or "")
        out = stack.gateway.discover_search(
            q,
            email=str(query.get("email") or ""),
            limit=int(query.get("limit", 12)),
        )
        if q.strip():
            _activity(stack, "discover", q[:200], meta={"limit": query.get("limit"), "total": out.get("total")})
        return out

    def library_discover_semantic(stack, query, payload, params):
        goal = str(payload.get("query") or payload.get("goal") or payload.get("message") or "")
        out = stack.gateway.semantic_discover(goal, limit=int(payload.get("limit") or 12))
        if goal.strip():
            _activity(stack, "semantic_discover", goal[:200], meta={"total": out.get("total")})
        return out

    def library_discover_web(stack, query, payload, params):
        q = str(query.get("q") or query.get("query") or "").strip()
        if not q:
            return {"query": q, "sections": [], "total": 0, "index_miss": True}
        from scripts.research_data_mcp.candidate_key import stamp_rows
        from scripts.research_data_mcp.web_search import discover_sources

        tavily_live = query.get("tavily", "1") not in {"0", "false", "no"}
        limit = int(query.get("limit", 8))
        raw = discover_sources(
            stack.gateway.repo_root,
            q,
            max_results=min(max(limit, 1), 12),
            tavily_live=tavily_live,
        )
        rows = []
        for hit in raw.get("results") or []:
            url = str(hit.get("url") or "").strip()
            if not url:
                continue
            rows.append(
                {
                    "kind": "web_hit",
                    "title": hit.get("title") or url,
                    "url": url,
                    "source": hit.get("source") or "web",
                    "description": hit.get("snippet") or hit.get("content") or "",
                    "publisher": hit.get("source") or "web",
                }
            )
        rows = stamp_rows(rows)
        if q:
            _activity(stack, "discover", f"web:{q[:180]}", meta={"total": len(rows), "web": True})
        return {
            "query": q,
            "sections": [{"id": "web_discover", "label": "Open web", "rows": rows}] if rows else [],
            "total": len(rows),
            "index_miss": True,
            "sources_tried": raw.get("sources_tried") or [],
        }

    def library_discover_probe(stack, query, payload, params):
        url = str(payload.get("url") or "").strip()
        name = str(payload.get("name") or "").strip()
        if not url:
            return {"error": "url is required", "status": "error"}
        from scripts.research_data_mcp.candidate_key import candidate_key

        requested_key = str(payload.get("candidate_key") or "").strip()
        out = stack.gateway.probe_source(url, name)
        connector = out.get("connector") if isinstance(out, dict) else None
        cid = None
        resolved_url = url
        if isinstance(connector, dict):
            cid = connector.get("connector_id") or connector.get("id")
            spec = connector.get("spec") if isinstance(connector.get("spec"), dict) else {}
            resolved_url = (
                str(spec.get("source_url") or connector.get("source_url") or url).strip() or url
            )
        echo_key = requested_key or candidate_key(
            {
                "candidate_key": requested_key,
                "dataset_id": payload.get("dataset_id"),
                "doi": payload.get("doi"),
                "url": url,
                "resolved_url": resolved_url,
                "title": name or payload.get("title"),
                "source": payload.get("source") or payload.get("provider"),
                "provider": payload.get("provider"),
                "external_id": payload.get("external_id"),
                "kind": payload.get("kind"),
            }
        )
        if isinstance(out, dict):
            out = dict(out)
            out["candidate_key"] = echo_key or None
            out["connector_id"] = cid
            out["resolved_url"] = resolved_url
            # connector_id is the persisted probe identity — do not invent probe_id
        _activity(
            stack,
            "probe",
            url[:200],
            meta={"connector_id": cid, "candidate_key": echo_key or None},
        )
        return out if _full_flag(query) or bool(payload.get("full")) else _compact_probe_response(out)

    def library_discover_collect(stack, query, payload, params):
        cid = str(payload.get("connector_id") or "").strip()
        source_id = str(payload.get("source_id") or "").strip()
        if not cid and not source_id:
            return {"error": "connector_id or source_id is required", "status": "error"}
        from scripts.research_data_mcp.candidate_key import candidate_key
        from scripts.research_data_mcp.discover_collect_plan import resolve_discover_collect_plan
        from scripts.research_data_mcp.job_identity import enrich_job_identity

        limit = int(payload.get("limit") or 200)
        auto_approve = bool(payload.get("auto_approve"))
        try:
            plan = resolve_discover_collect_plan(
                stack.gateway.procurement,
                stack.gateway.repo_root,
                connector_id=cid,
                source_id=source_id,
                limit=limit,
                title=str(payload.get("name") or payload.get("title") or "").strip(),
                url=str(payload.get("url") or payload.get("source_url") or "").strip(),
                candidate_key=str(payload.get("candidate_key") or "").strip(),
            )
        except KeyError as exc:
            return {
                "error": "not_found",
                "message": f"No collectable plan for connector_id={cid!r} source_id={source_id!r}: {exc}",
                "status": "error",
                "connector_id": cid,
                "source_id": source_id,
            }
        # Prefer resolved procurement/catalog id for identity stamping
        cid = str(plan.get("connector_id") or plan.get("catalog_connector_id") or cid).strip()
        dest = str(payload.get("destination") or "").strip()
        if dest:
            plan["destination"] = dest

        requested_key = str(payload.get("candidate_key") or "").strip()
        # Public field is source_identity; legacy `source` still accepted and normalized.
        source_identity = str(
            payload.get("source_identity") or payload.get("source") or payload.get("provider") or ""
        ).strip()
        identity_row = {
            "candidate_key": requested_key,
            "dataset_id": payload.get("dataset_id"),
            "doi": payload.get("doi"),
            "url": payload.get("url") or payload.get("source_url"),
            "title": payload.get("name") or payload.get("title"),
            "source": source_identity,
            "provider": payload.get("provider"),
            "external_id": payload.get("external_id"),
            "kind": payload.get("kind"),
            "connector_id": cid,
        }
        ck = requested_key or candidate_key(identity_row) or None
        if ck:
            plan = dict(plan)
            plan["candidate_key"] = ck
            plan["connector_id"] = cid

        request = {
            "connector_id": cid,
            "limit": limit,
            "source": "discover_ui",
        }
        for link_key in ("discover_intent_id", "discover_subscription_id"):
            link_val = str(payload.get(link_key) or "").strip()
            if link_val:
                request[link_key] = link_val
                plan = dict(plan)
                plan[link_key] = link_val
        if ck:
            request["candidate_key"] = ck
        for field in ("dataset_id", "doi", "url", "external_id", "kind", "provider"):
            val = payload.get(field)
            if val is not None and str(val).strip():
                request[field] = val
        if source_identity:
            request["source_identity"] = source_identity

        out = stack.jobs.submit(
            plan["title"],
            plan,
            request,
            auto_approve=auto_approve,
        )
        job = out.get("job") if isinstance(out, dict) else None
        if isinstance(job, dict):
            out = dict(out)
            out["job"] = enrich_job_identity(job)
            job = out["job"]
        _activity(
            stack,
            "job_submit",
            plan.get("title") or "Discover collect",
            meta={
                "job_id": job.get("id") if isinstance(job, dict) else None,
                "connector_id": cid,
                "candidate_key": ck,
            },
        )
        return out

    def library_discover_intents_list(stack, query, payload, params):
        return stack.gateway.discover_intent_list(
            limit=_query_int(query, "limit", 30), session_id=str(query.get("session_id") or "")
        )

    def library_discover_intents_create(stack, query, payload, params):
        candidate = payload.get("candidate")
        return stack.gateway.discover_intent_create(
            research_need=str(payload.get("research_need") or payload.get("need") or payload.get("query") or ""),
            title=str(payload.get("title") or ""),
            candidate=candidate if isinstance(candidate, dict) else None,
            session_id=str(payload.get("session_id") or ""),
            user_email=str(payload.get("user_email") or payload.get("email") or ""),
        )

    def library_discover_intent_get(stack, query, payload, params):
        return stack.gateway.discover_intent_get(params["intent_id"])

    def library_discover_intent_proposal(stack, query, payload, params):
        proposal = payload.get("proposal")
        if not isinstance(proposal, dict):
            raise ValueError("proposal is required")
        return stack.gateway.discover_intent_set_proposal(params["intent_id"], proposal)

    def library_discover_intent_review(stack, query, payload, params):
        return stack.gateway.discover_intent_review(
            params["intent_id"],
            decision=str(payload.get("decision") or ""),
            proposal_id=str(payload.get("proposal_id") or ""),
            proposal_hash=str(payload.get("proposal_hash") or ""),
        )

    def library_discover_intent_route(stack, query, payload, params):
        return stack.gateway.discover_intent_select_route(params["intent_id"], str(payload.get("route_id") or ""))

    def library_discover_intent_submit(stack, query, payload, params):
        out = stack.gateway.discover_intent_submit_collection(
            params["intent_id"], limit=int(payload.get("limit") or 200)
        )
        job = out.get("job") if isinstance(out, dict) else None
        _activity(
            stack,
            "job_submit",
            "Discover reviewed collection",
            meta={"intent_id": params["intent_id"], "job_id": job.get("id") if isinstance(job, dict) else None},
        )
        return out

    def library_discover_sources(stack, query, payload, params):
        q = str(query.get("q") or query.get("query") or "")
        live = str(query.get("live") or "").strip().lower() in {"1", "true", "yes"}
        semantic = str(query.get("semantic") or query.get("mode") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "semantic",
        }
        prefer = str(query.get("prefer") or query.get("kind") or "").strip()
        out = stack.gateway.discover_source_search(
            q,
            limit=_query_int(query, "limit", 24),
            live=live,
            semantic=semantic,
            prefer=prefer,
        )
        if q.strip():
            _activity(
                stack,
                "discover_sources",
                q[:200],
                meta={"total": out.get("total"), "live": live, "semantic": semantic},
            )
        return out

    def library_discover_source_preview(stack, query, payload, params):
        body = payload if payload else {}
        # GET query params also accepted
        def _pick(key: str, default: str = "") -> str:
            return str(body.get(key) or query.get(key) or default).strip()

        out = stack.gateway.discover_source_preview(
            source_id=_pick("source_id"),
            connector_id=_pick("connector_id"),
            candidate_key=_pick("candidate_key"),
            url=_pick("url"),
            doi=_pick("doi"),
            dataset_id=_pick("dataset_id"),
            name=_pick("name") or _pick("title"),
            limit=int(body.get("limit") or query.get("limit") or 5),
        )
        target = _pick("source_id") or _pick("connector_id") or _pick("url") or _pick("doi") or _pick("dataset_id") or "preview"
        _activity(stack, "preview", target[:200], meta={"status": out.get("status")})
        return out

    def library_discover_subscriptions_list(stack, query, payload, params):
        return stack.gateway.discover_refresh_list(
            limit=_query_int(query, "limit", 50),
            intent_id=str(query.get("intent_id") or ""),
            status=str(query.get("status") or ""),
        )

    def library_discover_subscriptions_create(stack, query, payload, params):
        out = stack.gateway.discover_refresh_create(
            cadence=str(payload.get("cadence") or "manual"),
            destination=str(payload.get("destination") or ""),
            intent_id=str(payload.get("intent_id") or ""),
            source_id=str(payload.get("source_id") or ""),
            connector_id=str(payload.get("connector_id") or ""),
            candidate_key=str(payload.get("candidate_key") or ""),
            enabled=bool(payload.get("enabled", True)),
            requested_schedule=str(payload.get("requested_schedule") or ""),
            schedule_note=str(payload.get("schedule_note") or ""),
            timezone=str(payload.get("timezone") or ""),
            schedule_spec=payload.get("schedule_spec") if isinstance(payload.get("schedule_spec"), dict) else (
                {"cron": str(payload.get("cron") or ""), "timezone": str(payload.get("timezone") or ""), "requested_schedule": str(payload.get("requested_schedule") or "")}
                if payload.get("cron")
                else None
            ),
        )
        _activity(
            stack,
            "refresh_subscription",
            out.get("source_id") or out.get("connector_id") or out.get("id") or "subscription",
            meta={"subscription_id": out.get("id"), "status": out.get("status")},
        )
        return out

    def library_discover_subscription_get(stack, query, payload, params):
        return stack.gateway.discover_refresh_get(params["subscription_id"])

    def library_discover_subscription_pause(stack, query, payload, params):
        return stack.gateway.discover_refresh_pause(params["subscription_id"])

    def library_discover_subscription_resume(stack, query, payload, params):
        return stack.gateway.discover_refresh_resume(params["subscription_id"])

    def library_discover_subscription_stop(stack, query, payload, params):
        return stack.gateway.discover_refresh_stop(params["subscription_id"])

    def library_discover_subscriptions_tick(stack, query, payload, params):
        body = payload if isinstance(payload, dict) else {}
        out = stack.gateway.discover_refresh_tick(
            limit=int(body.get("limit") or query.get("limit") or 10),
            force_subscription_id=str(body.get("subscription_id") or ""),
            force=bool(body.get("force")),
            auto_approve_safe=body.get("auto_approve_safe", True) not in {False, "0", "false", "no"},
        )
        _activity(
            stack,
            "refresh_tick",
            f"fired={len(out.get('fired') or [])}",
            meta={"checked": out.get("checked"), "forced": out.get("forced")},
        )
        return out

    def library_discover_subscription_run(stack, query, payload, params):
        body = payload if isinstance(payload, dict) else {}
        out = stack.gateway.discover_refresh_tick(
            limit=1,
            force_subscription_id=params["subscription_id"],
            force=True,
            auto_approve_safe=body.get("auto_approve_safe", True) not in {False, "0", "false", "no"},
        )
        _activity(stack, "refresh_run", params["subscription_id"], meta={"fired": len(out.get("fired") or [])})
        return out

    def library_discover_history(stack, query, payload, params):
        return stack.gateway.discover_history(
            limit=_query_int(query, "limit", 50),
            kind=str(query.get("kind") or query.get("filter") or ""),
            session_id=str(query.get("session_id") or ""),
            include_jobs=query.get("include_jobs", "1") not in {"0", "false", "no"},
        )

    def library_datacite_enrich(stack, query, payload, params):
        rows = payload.get("rows") or []
        if not rows and payload.get("dois"):
            rows = [{"doi": d} for d in payload.get("dois") or []]
        return stack.gateway.enrich_datacite_search(
            rows,
            max_file_bytes=int(payload.get("max_file_bytes") or 50_000_000),
        )

    def library_license_approve(stack, query, payload, params):
        return stack.gateway.approve_dataset_license(
            doi=str(payload.get("doi") or ""),
            url=str(payload.get("url") or ""),
            license_text=str(payload.get("license") or payload.get("license_text") or ""),
            note=str(payload.get("note") or ""),
        )

    def library_credential_profiles(stack, query, payload, params):
        return stack.gateway.list_credential_profiles()

    def library_overview(stack, query, payload, params):
        return stack.gateway.library_overview()

    def library_partitions(stack, query, payload, params):
        from datetime import datetime, timezone

        overview = stack.gateway.library_overview()
        parts = overview.get("partitions") or {}
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "partitions": parts.get("lanes") or [],
            "total": parts.get("total", 0),
            "complete": parts.get("complete", 0),
        }

    def library_browse(stack, query, payload, params):
        showcase = [s for s in str(query.get("showcase", "")).split(",") if s.strip()]
        return stack.gateway.browse_drive(
            folder_id=str(query.get("folder", "") or ""),
            scope=str(query.get("scope", "lab") or "lab"),
            showcase_ids=showcase or None,
        )

    def library_ops(stack, query, payload, params):
        return stack.gateway.ops_status(lane=query.get("lane", ""))

    def library_advise(stack, query, payload, params):
        return stack.gateway.advise_datasets(
            str(payload.get("goal") or payload.get("message") or ""),
            current_dataset_id=str(payload.get("current_dataset_id") or payload.get("dataset_id") or ""),
            current_task_id=str(payload.get("current_task_id") or ""),
            limit=int(payload.get("limit", 5)),
        )

    def library_procure_chat(stack, query, payload, params):
        rail = payload.get("rail_context")
        return stack.gateway.procurement_chat(
            str(payload.get("message", "")),
            session_id=str(payload.get("session_id") or "") or None,
            user_email=str(payload.get("user_email") or payload.get("email") or "") or None,
            rail_context=rail if isinstance(rail, dict) else None,
        )

    def library_procure_chat_stream(stack, query, payload, params):
        rail = payload.get("rail_context")
        return {
            "_stream": True,
            "events": stack.gateway.procurement_chat_stream(
                str(payload.get("message", "")),
                session_id=str(payload.get("session_id") or "") or None,
                user_email=str(payload.get("user_email") or payload.get("email") or "") or None,
                rail_context=rail if isinstance(rail, dict) else None,
            ),
        }

    def library_synthesis_threads_list(stack, query, payload, params):
        return stack.gateway.synthesis_thread_list(
            limit=_query_int(query, "limit", 30),
            session_id=str(query.get("session_id") or ""),
        )

    def library_synthesis_threads_create(stack, query, payload, params):
        state = payload.get("state")
        return stack.gateway.synthesis_thread_create(
            objective=str(payload.get("objective") or ""),
            title=str(payload.get("title") or ""),
            session_id=str(payload.get("session_id") or ""),
            conversation_id=str(payload.get("conversation_id") or payload.get("conversation") or ""),
            required_grain=str(payload.get("required_grain") or payload.get("grain") or ""),
            state=state if isinstance(state, dict) else None,
        )

    def library_synthesis_thread_get(stack, query, payload, params):
        return stack.gateway.synthesis_thread_get(params["thread_id"])

    def library_synthesis_thread_patch(stack, query, payload, params):
        operations = payload.get("operations")
        return stack.gateway.synthesis_thread_apply_patch(
            params["thread_id"],
            decision=str(payload.get("decision") or payload.get("action") or ""),
            operations=operations if isinstance(operations, list) else None,
            proposal_id=str(payload.get("proposal_id") or ""),
            proposal_hash=str(payload.get("proposal_hash") or ""),
        )

    def library_synthesis_thread_set_proposal(stack, query, payload, params):
        proposal = payload.get("proposal")
        if proposal is None and "operations" in payload:
            proposal = {
                "id": str(payload.get("id") or payload.get("proposal_id") or ""),
                "title": str(payload.get("title") or ""),
                "summary": str(payload.get("summary") or ""),
                "nodeId": payload.get("nodeId") or payload.get("node_id"),
                "operations": payload.get("operations") or [],
            }
            if isinstance(payload.get("execution_spec"), dict):
                proposal["execution_spec"] = payload["execution_spec"]
        return stack.gateway.synthesis_thread_set_proposal(
            params["thread_id"],
            proposal if isinstance(proposal, dict) else None,
        )

    def library_synthesis_thread_discover_handoff(stack, query, payload, params):
        return stack.gateway.synthesis_thread_discover_handoff(params["thread_id"])

    def library_synthesis_thread_collect_missing(stack, query, payload, params):
        body = payload if isinstance(payload, dict) else {}
        return stack.gateway.synthesis_thread_collect_missing(
            params["thread_id"],
            evidence_ids=list(body.get("evidence_ids") or []),
            auto_approve_safe=bool(body.get("auto_approve_safe", True)),
            limit=int(body.get("limit") or 8),
        )

    def library_synthesis_thread_materialisation(stack, query, payload, params):
        return stack.gateway.synthesis_thread_materialisation(params["thread_id"])

    def library_synthesis_thread_execute(stack, query, payload, params):
        return stack.gateway.synthesis_thread_submit_execution(params["thread_id"])

    def library_synthesis_thread_link_conversation(stack, query, payload, params):
        return stack.gateway.synthesis_thread_link_conversation(
            params["thread_id"],
            session_id=str(payload.get("session_id") or payload.get("session") or ""),
            conversation_id=str(payload.get("conversation_id") or payload.get("conversation") or ""),
        )

    def library_synthesis_profiles(stack, query, payload, params):
        return stack.gateway.synthesis_list_profiles()

    def library_synthesis_get(stack, query, payload, params):
        refresh = query.get("refresh", "").lower() in {"1", "true", "yes"}
        profile_id = params["id"]
        if refresh:
            return stack.gateway.synthesis_run(profile_id)
        latest = stack.gateway.synthesis_get_latest(profile_id)
        if latest.get("found"):
            return latest
        # Faculty read must not build — miss returns found:false; Build uses POST /run or ?refresh=1.
        return {"found": False, "profile_id": profile_id}

    def library_synthesis_run(stack, query, payload, params):
        profile_id = str(payload.get("profile_id") or query.get("profile_id") or "")
        if not profile_id:
            raise ValueError("profile_id is required")
        return stack.gateway.synthesis_run(
            profile_id,
            preview_limit=int(payload.get("preview_limit") or query.get("preview_limit") or 50),
            gap_limit=int(payload.get("gap_limit") or query.get("gap_limit") or 100),
        )

    def library_synthesis_pair(stack, query, payload, params):
        left_id = str(payload.get("left_dataset_id") or query.get("left") or "")
        right_id = str(payload.get("right_dataset_id") or query.get("right") or "")
        if not left_id or not right_id:
            raise ValueError("left_dataset_id and right_dataset_id are required")
        return stack.gateway.synthesis_pair(left_id, right_id)

    def library_platform_state(stack, query, payload, params):
        return stack.gateway.platform_state()

    def library_source_map(stack, query, payload, params):
        live = str(query.get("live") or "").lower() in {"1", "true", "yes"}
        return stack.gateway.source_map_audit(live=live)

    def library_access_scope(stack, query, payload, params):
        live = str(query.get("live") or "").lower() in {"1", "true", "yes"}
        return stack.gateway.access_scope_audit(live=live)

    def library_dataset_coverage(stack, query, payload, params):
        live = str(query.get("live") or "").lower() in {"1", "true", "yes"}
        return stack.gateway.dataset_coverage_audit(live=live)

    def library_consolidated(stack, query, payload, params):
        live = str(query.get("live") or "").lower() in {"1", "true", "yes"}
        return stack.gateway.consolidated_state(live=live)

    def library_faculty_profile(stack, query, payload, params):
        return stack.gateway.faculty_profile(
            email=str(query.get("email") or ""),
            slug=str(query.get("slug") or ""),
        )

    def library_desk_brief(stack, query, payload, params):
        return stack.gateway.desk_vault_brief(email=str(query.get("email") or ""))

    def library_desk_resources(stack, query, payload, params):
        return stack.gateway.desk_resources(live=_live_flag(query))

    def library_desk_warm(stack, query, payload, params):
        return stack.gateway.desk_warm_session(
            user_email=str(payload.get("user_email") or payload.get("email") or query.get("email") or ""),
            session_id=str(payload.get("session_id") or ""),
            background=bool(payload.get("background", True)),
        )

    def library_procure_chat_session(stack, query, payload, params):
        return stack.gateway.procurement_chat_session(params["session_id"])

    def library_campaigns(stack, query, payload, params):
        return stack.gateway.list_campaigns(limit=int(query.get("limit", 30)), status=query.get("status", ""))

    def library_campaign_get(stack, query, payload, params):
        return stack.gateway.get_campaign(params["id"])

    def library_campaign_artifacts(stack, query, payload, params):
        return stack.gateway.list_campaign_artifacts(params["id"])

    def library_campaign_download(stack, query, payload, params):
        rel_path = str(query.get("path") or "")
        if not rel_path:
            raise ValueError("path query parameter is required")
        resolved = stack.gateway.resolve_campaign_download(params["id"], rel_path)
        file_path = resolved["file"]
        return {
            "_file_delivery": True,
            "file": str(file_path),
            "content_type": resolved["content_type"],
            "name": file_path.name,
        }

    def library_datacite_resolve(stack, query, payload, params):
        doi = str(payload.get("doi") or "")
        if not doi:
            raise ValueError("doi is required")
        return stack.gateway.datacite_resolve_repository(
            doi,
            max_file_bytes=int(payload.get("max_file_bytes") or 50_000_000),
        )

    def library_datacite_search_resolve(stack, query, payload, params):
        query_text = str(payload.get("query") or payload.get("q") or "")
        if not query_text:
            raise ValueError("query is required")
        return stack.gateway.datacite_search_and_resolve(
            query_text,
            created=str(payload.get("created") or ""),
            max_file_bytes=int(payload.get("max_file_bytes") or 50_000_000),
        )

    def library_datacite_collect(stack, query, payload, params):
        doi = str(payload.get("doi") or "")
        if not doi:
            raise ValueError("doi is required")
        out = stack.gateway.collect_datacite_doi(
            doi,
            file_index=int(payload.get("file_index") or 0),
            campaign_id=str(payload.get("campaign_id") or "") or None,
            auto_execute=bool(payload.get("auto_execute", True)),
            max_file_bytes=int(payload.get("max_file_bytes") or 50_000_000),
            license_approved=bool(payload.get("license_approved", False)),
        )
        _activity(
            stack,
            "procure",
            doi,
            meta={
                "campaign_id": out.get("campaign_id") if isinstance(out, dict) else None,
                "job_id": (out.get("job") or {}).get("id") if isinstance(out, dict) else None,
            },
        )
        return out

    def library_campaign_add_datacite(stack, query, payload, params):
        doi = str(payload.get("doi") or "")
        if not doi:
            raise ValueError("doi is required")
        return stack.gateway.add_datacite_to_collection(
            doi,
            campaign_id=params["id"],
            file_index=int(payload.get("file_index") or 0),
            auto_execute=bool(payload.get("auto_execute", True)),
        )

    def library_dataset_card(stack, query, payload, params):
        return stack.gateway.get_dataset_card(params["ref"])

    def library_dataset_open(stack, query, payload, params):
        handle = str(query.get("handle") or "")
        if not handle:
            raise ValueError("handle query parameter is required")
        return stack.gateway.open_dataset(
            handle,
            load=str(query.get("load") or "auto"),
            preview_limit=int(query.get("limit") or 5),
        )

    def library_pins_list(stack, query, payload, params):
        return stack.gateway.list_dataset_pins(limit=int(query.get("limit", 50)))

    def library_pins_create(stack, query, payload, params):
        handle = str(payload.get("handle") or "")
        if not handle:
            raise ValueError("handle is required")
        return stack.gateway.pin_dataset(
            handle,
            campaign_id=str(payload.get("campaign_id") or ""),
            file_path=str(payload.get("file_path") or ""),
            checksum=str(payload.get("checksum") or ""),
        )

    def library_campaign_approve_collect(stack, query, payload, params):
        out = stack.gateway.approve_campaign_collect(
            params["id"],
            int(payload.get("recommendation_index", 0)),
        )
        _activity(stack, "approve_collect", params["id"], meta={"recommendation_index": payload.get("recommendation_index", 0)})
        return out

    def library_campaign_resume(stack, query, payload, params):
        return stack.gateway.resume_campaign(
            params["id"],
            force_execute=bool(payload.get("force_execute")),
        )

    def library_submit_job(stack, query, payload, params):
        out = stack.jobs.submit(
            str(payload.get("title") or (payload.get("plan") or {}).get("title") or "Library job"),
            payload.get("plan") or {},
            payload.get("request") or {},
            auto_approve=bool(payload.get("auto_approve")),
        )
        job = out.get("job") if isinstance(out, dict) else None
        _activity(
            stack,
            "job_submit",
            str(payload.get("title") or (payload.get("plan") or {}).get("title") or "Library job"),
            meta={"job_id": job.get("id") if isinstance(job, dict) else None},
        )
        return out

    def yzu_submit_job(stack, query, payload, params):
        plan = payload.get("plan") or {}
        title = str(payload.get("title") or plan.get("title") or "YZU job")
        result = stack.jobs.submit(title, plan, payload.get("request") or {}, auto_approve=bool(payload.get("auto_approve")))
        job = result.get("job") if isinstance(result, dict) else None
        _activity(stack, "job_submit", title, meta={"job_id": job.get("id") if isinstance(job, dict) else None})
        return result["job"] if result.get("job") else result

    def job_list(stack, query, payload, params):
        return stack.jobs.list(limit=_query_int(query, "limit", 30), status=query.get("status", ""))

    def job_get(stack, query, payload, params):
        return stack.jobs.get(params["id"])

    def job_approve(stack, query, payload, params):
        # Desk researcher approve (gateway); synthesis allowed here, not via approve-safe/agents.
        out = stack.gateway.approve_yzu_job(params["id"])
        ticked = stack.jobs.tick()
        if isinstance(out, dict) and isinstance(ticked, dict) and ticked.get("id"):
            out["tick_started"] = ticked.get("id")
        _activity(stack, "job_approve", params["id"], meta={"status": out.get("status") if isinstance(out, dict) else None})
        return out

    def library_jobs_approve_safe(stack, query, payload, params):
        limit = int(payload.get("limit") or query.get("limit") or 200)
        out = stack.gateway.approve_safe_pending_jobs(limit=limit)
        _activity(stack, "jobs_approve_safe", "bulk", meta={"approved": out.get("approved_count")})
        return out

    def job_cancel(stack, query, payload, params):
        return stack.jobs.cancel(params["id"])

    def yzu_approve_safe_jobs(stack, query, payload, params):
        limit = int(payload.get("limit") or query.get("limit") or 200)
        return stack.gateway.approve_safe_pending_jobs(limit=limit)

    def library_archive(stack, query, payload, params):
        plan = stack.jobs.archive_plan(
            str(payload.get("local_path", "")),
            remote_suffix=str(payload.get("remote_suffix") or ""),
            verify=bool(payload.get("verify", True)),
        )
        return stack.jobs.submit(
            str(payload.get("title") or "Archive to GDrive"),
            plan,
            auto_approve=bool(payload.get("auto_approve", True)),
        )

    def yzu_status(stack, query, payload, params):
        return stack.yzu_api.status(live=_live_flag(query))

    def yzu_acquisitions(stack, query, payload, params):
        live = _live_flag(query)
        status = stack.yzu_api.status(live=live)
        acq = stack.yzu_api.acquisitions(live=live)
        return {**{"acquisitions": acq}, "generated_at": status.get("generated_at"), "live": live}

    def yzu_workers(stack, query, payload, params):
        return stack.yzu_api.workers(live=_live_flag(query))

    def yzu_activity(stack, query, payload, params):
        return {"events": stack.yzu_api.activity(live=_live_flag(query)), "live": _live_flag(query)}

    def yzu_components(stack, query, payload, params):
        return stack.orchestrator.components()

    def yzu_queue_tasks(stack, query, payload, params):
        runnable = query.get("runnable", "1").lower() not in {"0", "false", "no"}
        return {"tasks": stack.orchestrator.queue_tasks(runnable_only=runnable)}

    def yzu_schedules(stack, query, payload, params):
        return {"schedules": stack.orchestrator.schedules()}

    def yzu_run_schedule(stack, query, payload, params):
        raw = payload.get("dry_run", query.get("dry_run", False)) if isinstance(payload, dict) else query.get("dry_run", False)
        dry_run = raw is True or str(raw).strip().lower() in {"1", "true", "yes"}
        return stack.jobs.run_schedule(params["id"], dry_run=dry_run)

    def extension_tool_catalog(stack, query, payload, params):
        return stack.tools.tool_catalog()

    def extension_datacite_search(stack, query, payload, params):
        return stack.tools.datacite_search(
            query=query.get("q", query.get("query", "")),
            created=query.get("created", ""),
            cursor=query.get("cursor", "1"),
            page_size=int(query.get("page_size", 25)),
        )

    def extension_datacite_get(stack, query, payload, params):
        return stack.tools.datacite_get(params["doi"])

    def extension_hf_search(stack, query, payload, params):
        return stack.tools.huggingface_search(
            query=query.get("q", query.get("query", "")),
            limit=int(query.get("limit", 8)),
        )

    def extension_bigquery_status(stack, query, payload, params):
        return stack.tools.bigquery_status(project=query.get("project", ""), location=query.get("location", "US"))

    def extension_bigquery_dry_run(stack, query, payload, params):
        return stack.tools.bigquery_dry_run(
            sql=str(payload.get("sql", "")),
            project=str(payload.get("project", "")),
            location=str(payload.get("location", "US")),
            max_bytes_billed=int(payload.get("max_bytes_billed", 10 * 1024**3)),
        )

    return {
        "health": health,
        "datasets": datasets,
        "dataset_describe": dataset_describe,
        "dataset_query": dataset_query,
        "library_catalog": library_catalog,
        "library_unified_search": library_unified_search,
        "library_discover": library_discover,
        "library_discover_semantic": library_discover_semantic,
        "library_discover_web": library_discover_web,
        "library_discover_probe": library_discover_probe,
        "library_discover_collect": library_discover_collect,
        "library_discover_intents_list": library_discover_intents_list,
        "library_discover_intents_create": library_discover_intents_create,
        "library_discover_intent_get": library_discover_intent_get,
        "library_discover_intent_proposal": library_discover_intent_proposal,
        "library_discover_intent_review": library_discover_intent_review,
        "library_discover_intent_route": library_discover_intent_route,
        "library_discover_intent_submit": library_discover_intent_submit,
        "library_discover_sources": library_discover_sources,
        "library_discover_source_preview": library_discover_source_preview,
        "library_discover_subscriptions_list": library_discover_subscriptions_list,
        "library_discover_subscriptions_create": library_discover_subscriptions_create,
        "library_discover_subscription_get": library_discover_subscription_get,
        "library_discover_subscription_pause": library_discover_subscription_pause,
        "library_discover_subscription_resume": library_discover_subscription_resume,
        "library_discover_subscription_stop": library_discover_subscription_stop,
        "library_discover_subscriptions_tick": library_discover_subscriptions_tick,
        "library_discover_subscription_run": library_discover_subscription_run,
        "library_discover_history": library_discover_history,
        "library_datacite_enrich": library_datacite_enrich,
        "library_license_approve": library_license_approve,
        "library_credential_profiles": library_credential_profiles,
        "library_overview": library_overview,
        "library_partitions": library_partitions,
        "library_ops": library_ops,
        "library_advise": library_advise,
        "library_procure_chat": library_procure_chat,
        "library_procure_chat_stream": library_procure_chat_stream,
        "library_synthesis_profiles": library_synthesis_profiles,
        "library_synthesis_threads_list": library_synthesis_threads_list,
        "library_synthesis_threads_create": library_synthesis_threads_create,
        "library_synthesis_thread_get": library_synthesis_thread_get,
        "library_synthesis_thread_patch": library_synthesis_thread_patch,
        "library_synthesis_thread_set_proposal": library_synthesis_thread_set_proposal,
        "library_synthesis_thread_link_conversation": library_synthesis_thread_link_conversation,
        "library_synthesis_thread_discover_handoff": library_synthesis_thread_discover_handoff,
        "library_synthesis_thread_collect_missing": library_synthesis_thread_collect_missing,
        "library_synthesis_thread_materialisation": library_synthesis_thread_materialisation,
        "library_synthesis_thread_execute": library_synthesis_thread_execute,
        "library_synthesis_get": library_synthesis_get,
        "library_synthesis_run": library_synthesis_run,
        "library_synthesis_pair": library_synthesis_pair,
        "library_platform_state": library_platform_state,
        "library_source_map": library_source_map,
        "library_access_scope": library_access_scope,
        "library_dataset_coverage": library_dataset_coverage,
        "library_consolidated": library_consolidated,
        "library_faculty_profile": library_faculty_profile,
        "library_desk_brief": library_desk_brief,
        "library_desk_resources": library_desk_resources,
        "library_desk_warm": library_desk_warm,
        "library_procure_chat_session": library_procure_chat_session,
        "library_campaigns": library_campaigns,
        "library_campaign_get": library_campaign_get,
        "library_campaign_artifacts": library_campaign_artifacts,
        "library_campaign_download": library_campaign_download,
        "library_datacite_resolve": library_datacite_resolve,
        "library_datacite_collect": library_datacite_collect,
        "library_datacite_search_resolve": library_datacite_search_resolve,
        "library_campaign_add_datacite": library_campaign_add_datacite,
        "library_dataset_card": library_dataset_card,
        "library_dataset_open": library_dataset_open,
        "library_pins_list": library_pins_list,
        "library_pins_create": library_pins_create,
        "library_campaign_approve_collect": library_campaign_approve_collect,
        "library_campaign_resume": library_campaign_resume,
        "library_submit_job": library_submit_job,
        "yzu_submit_job": yzu_submit_job,
        "job_list": job_list,
        "job_get": job_get,
        "job_approve": job_approve,
        "library_jobs_approve_safe": library_jobs_approve_safe,
        "job_cancel": job_cancel,
        "yzu_approve_safe_jobs": yzu_approve_safe_jobs,
        "library_archive": library_archive,
        "extension_tool_catalog": extension_tool_catalog,
        "extension_datacite_search": extension_datacite_search,
        "extension_datacite_get": extension_datacite_get,
        "extension_hf_search": extension_hf_search,
        "extension_bigquery_status": extension_bigquery_status,
        "extension_bigquery_dry_run": extension_bigquery_dry_run,
        "yzu_status": yzu_status,
        "yzu_acquisitions": yzu_acquisitions,
        "yzu_workers": yzu_workers,
        "yzu_activity": yzu_activity,
        "yzu_components": yzu_components,
        "yzu_queue_tasks": yzu_queue_tasks,
        "yzu_schedules": yzu_schedules,
        "yzu_run_schedule": yzu_run_schedule,
    }


_HANDLERS = _handlers()


def handle_get(path: str, query: dict[str, str], stack: ResearchLibraryStack) -> dict[str, Any]:
    return _dispatch("GET", path, query, {}, stack)


def handle_post(path: str, payload: dict[str, Any], stack: ResearchLibraryStack) -> dict[str, Any]:
    return _dispatch("POST", path, {}, payload, stack)


_LEGACY_ROUTE_PREFIXES = ("/yzu/",)


def _attach_deprecation(path: str, body: Any) -> Any:
    if not any(path.startswith(prefix) for prefix in _LEGACY_ROUTE_PREFIXES):
        return body
    if not isinstance(body, dict):
        return body
    out = dict(body)
    out["_deprecated"] = {
        "message": "Legacy route — prefer /library/* equivalents where available.",
        "path": path,
        "docs": "docs/PROCUREMENT_PIPELINE.md",
    }
    return out


def _dispatch(method: str, path: str, query: dict[str, str], payload: dict[str, Any], stack: ResearchLibraryStack) -> dict[str, Any]:
    if path.startswith("/library") or path in {"/health", "/datasets"} or path.startswith("/query/"):
        try:
            from scripts.research_data_mcp.desk_runtime import touch_desk_activity

            touch_desk_activity(stack.gateway.repo_root, route=path)
        except Exception:
            pass
    handler_name, params = _resolve(path, method)
    if not handler_name:
        body = {"error": "not_found"}
        if method == "GET":
            body["paths"] = [r["path"] for r in ROUTE_CATALOG if r["method"] == "GET"]
        return {"status": 404, "body": body}
    handler = _HANDLERS.get(handler_name)
    if not handler:
        return {"status": 404, "body": {"error": "not_found", "handler": handler_name}}
    try:
        return {"status": 200, "body": _attach_deprecation(path, handler(stack, query, payload, params))}
    except PermissionError as exc:
        return {"status": 403, "body": {"error": "forbidden", "message": str(exc)}}
    except KeyError as exc:
        return {"status": 404, "body": {"error": "not_found", "message": str(exc)}}
    except ValueError as exc:
        return {"status": 400, "body": {"error": "invalid_request", "message": str(exc)}}
    except Exception as exc:
        return {"status": 500, "body": {"error": type(exc).__name__, "message": str(exc)}}
