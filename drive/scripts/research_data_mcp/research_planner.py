#!/usr/bin/env python3
"""Legacy index-miss research planning for campaign resume paths only."""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

INDEX_META_IDS = frozenset(
    {
        "datacite_local_harvest_status",
        "collection_queue_status",
        "external_dataset_catalog",
        "external_dataset_catalog_curated",
        "procurement_source_registry",
        "research_source_plan",
    }
)

_OPS_GOAL_RE = re.compile(
    r"\b(shard|harvest|monitor|status|datacite|gdelt|queue|progress|y20\d{2})\b",
    re.I,
)
_URL_RE = re.compile(r"https?://", re.I)


def is_index_miss(advice: dict[str, Any], message: str = "") -> bool:
    message = message.strip()
    if _URL_RE.search(message):
        return False
    if _OPS_GOAL_RE.search(message) and advice.get("verdict") in {"good_fit", "partial_fit"}:
        return False

    verdict = str(advice.get("verdict") or "")
    if verdict in {"wrong_fit", "partial_fit"}:
        return True
    recommended = advice.get("recommended") or []
    if not recommended:
        return True
    top = recommended[0]
    top_id = str(top.get("id") or "")
    if verdict == "good_fit" and top.get("kind") == "registry_dataset":
        if top_id in INDEX_META_IDS and not _OPS_GOAL_RE.search(message):
            return True
        return False
    if top_id in INDEX_META_IDS and not _OPS_GOAL_RE.search(message):
        return True
    return verdict != "good_fit"


class ResearchPlanner:
    def __init__(self, gateway: Any) -> None:
        self.gateway = gateway

    def build(
        self,
        message: str,
        advice: dict[str, Any],
        *,
        source_plan: dict[str, Any] | None = None,
        catalog_hits: dict[str, Any] | None = None,
        discovery: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = {
            "goal": message,
            "advice_verdict": advice.get("verdict"),
            "advice_message": advice.get("message"),
            "advice_recommended": advice.get("recommended") or [],
            "advice_next_steps": advice.get("next_steps") or [],
            "source_plan_rows": (source_plan or {}).get("rows") or [],
            "source_plan_meta": (source_plan or {}).get("meta") or {},
            "catalog_rows": (catalog_hits or {}).get("rows") or [],
            "discovery_results": (discovery or {}).get("results") or [],
        }
        if os.getenv("DEEPSEEK_API_KEY") or "localhost" in os.getenv("DEEPSEEK_BASE_URL", ""):
            try:
                plan = self._ask_deepseek(context)
                plan["engine"] = "deepseek"
                return self._normalize_plan(plan, message)
            except Exception as exc:
                fallback = self._fallback(context, message)
                fallback["planner_note"] = f"Legacy research planner failed ({exc}); used heuristic plan."
                return fallback
        body = self._fallback(context, message)
        body["planner_note"] = "Legacy LLM planner not configured; used heuristic research plan."
        return body

    def _ask_deepseek(self, context: dict[str, Any]) -> dict[str, Any]:
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/chat/completions")
        system = """You are the research procurement planner for YZU Cluster.
The user's goal is NOT in the local finance/crypto/macro catalog. Build an actionable external acquisition strategy.

Storage model: downloads stage under data_lake/ (especially data_lake/procured/). Canonical
long-term storage is GDrive at gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data.
After collect + verify, use archive_upload (or fleet upload pipelines) to push to GDrive.
Do not assume full shard files stay on the optiplex controller — check GDrive for DataCite/GDELT.

Return one JSON object:
{
  "summary": "2-4 sentences: what we lack locally and what to try externally",
  "in_local_catalog": false,
  "search_queries": ["3-6 search strings for catalog/web APIs"],
  "probe_urls": ["3-8 concrete https URLs to probe first — data portals, .gov, ICPSR, UKDA, Zenodo, data.gov, etc."],
  "candidate_sources": [{"name": "...", "url": "https://...", "source_type": "survey|retail|academic|government|open_data", "rationale": "..."}],
  "procurement_steps": [
    {"order": 1, "action": "probe", "title": "...", "url": "https://..."},
    {"order": 2, "action": "catalog_search", "title": "...", "query": "..."},
    {"order": 3, "action": "collect", "title": "...", "job_type": "http_manifest|source_probe|scraper_run", "url": "https://...", "script_key": "optional for scraper_run", "notes": "only after probe approves"}
  ],
  "recommended_collect_plan": null
}

Rules:
- probe_urls MUST be real, well-known portals or datasets when possible (not invent DOIs).
- Do not recommend local crypto/SEC/GDELT datasets for unrelated consumer health goals.
- recommended_collect_plan stays null unless a single safe source_probe, http_manifest, or scraper_run (generic_url_scrape + url) is obvious.
- For HTML-only portals with no direct files, use scraper_run with script_key generic_url_scrape.
- Prefer government surveys (NHANES, DHS), retail data portals, academic archives for consumer product questions."""
        body = json.dumps(
            {
                "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
                ],
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(base_url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = json.loads(payload["choices"][0]["message"]["content"])
        return content

    def _fallback(self, context: dict[str, Any], message: str) -> dict[str, Any]:
        from scripts.research_data_mcp.probe_url_selection import rank_probe_urls

        goal = message.lower()
        queries = [message]
        extra_urls: list[str] = []
        candidates: list[dict[str, str]] = []

        for row in context.get("source_plan_rows") or []:
            url = str(row.get("url") or "").strip()
            if url.startswith("http"):
                candidates.append(
                    {
                        "name": str(row.get("title") or row.get("dataset_id") or url)[:120],
                        "url": url,
                        "source_type": "catalog_index",
                        "rationale": str(row.get("access_recommendation") or row.get("planning_source") or ""),
                    }
                )

        for row in context.get("catalog_rows") or []:
            url = str(row.get("url") or "").strip()
            if url.startswith("http"):
                candidates.append(
                    {
                        "name": str(row.get("title") or row.get("dataset_id") or url)[:120],
                        "url": url,
                        "source_type": "external_catalog",
                        "rationale": str(row.get("source") or "curated external index"),
                    }
                )

        probe_urls = rank_probe_urls(
            message,
            discovery_results=context.get("discovery_results") or [],
            catalog_rows=context.get("catalog_rows") or [],
            source_plan_rows=context.get("source_plan_rows") or [],
            extra_urls=extra_urls,
            limit=8,
        )

        steps: list[dict[str, Any]] = []
        for index, url in enumerate(probe_urls[:5], start=1):
            steps.append({"order": index, "action": "probe", "title": f"Probe candidate source {index}", "url": url})
        for index, query in enumerate(queries[1:4], start=len(steps) + 1):
            steps.append({"order": index, "action": "catalog_search", "title": f"Search external catalog: {query[:60]}", "query": query})

        return self._normalize_plan(
            {
                "summary": context.get("advice_message") or "No strong local match; probing external sources.",
                "in_local_catalog": False,
                "search_queries": queries[:6],
                "probe_urls": probe_urls[:8],
                "candidate_sources": candidates[:8],
                "procurement_steps": steps,
                "recommended_collect_plan": None,
                "engine": "heuristic",
            },
            message,
        )

    def _normalize_plan(self, plan: dict[str, Any], message: str) -> dict[str, Any]:
        out = dict(plan)
        out["goal"] = message
        out["search_queries"] = [str(q).strip() for q in out.get("search_queries") or [] if str(q).strip()]
        if message not in out["search_queries"]:
            out["search_queries"].insert(0, message)

        urls: list[str] = []
        for raw in out.get("probe_urls") or []:
            url = str(raw).strip()
            if url.startswith("http") and url not in urls:
                urls.append(url)
        for row in out.get("candidate_sources") or []:
            if isinstance(row, dict):
                url = str(row.get("url") or "").strip()
                if url.startswith("http") and url not in urls:
                    urls.append(url)
        for step in out.get("procurement_steps") or []:
            if isinstance(step, dict) and step.get("action") == "probe":
                url = str(step.get("url") or "").strip()
                if url.startswith("http") and url not in urls:
                    urls.append(url)
        from scripts.research_data_mcp.probe_url_selection import rank_probe_urls

        out["probe_urls"] = rank_probe_urls(message, extra_urls=urls, limit=10)

        collect = out.get("recommended_collect_plan")
        if collect is not None and not isinstance(collect, dict):
            out["recommended_collect_plan"] = None
        return out
