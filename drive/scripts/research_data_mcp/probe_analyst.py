#!/usr/bin/env python3
"""Analyze source_probe results → feasibility + next collect plan."""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

from scripts.research_data_mcp.governance import allow_auto_collect, classify_url as classify_access
from scripts.research_data_mcp.scrape_plan import (
    build_generic_scrape_plan,
    build_http_manifest_plan_for_url,
    classify_url as classify_fetch_mode,
    plan_for_url,
)
from scripts.yzu_cluster.acquisitions import enrich_http_manifest_plan


class ProbeAnalyst:
    def __init__(self, procurement: Any | None = None) -> None:
        self.procurement = procurement

    def analyze(
        self,
        *,
        url: str,
        name: str,
        job: dict[str, Any],
        goal: str,
        governance: dict[str, Any],
    ) -> dict[str, Any]:
        result = job.get("result") or {}
        connector_id = result.get("connector_id")
        summary = str(result.get("summary") or "")
        access_class = classify_access(url, name=name)
        context = {
            "goal": goal,
            "url": url,
            "name": name,
            "access_class": access_class,
            "job_status": job.get("status"),
            "connector_id": connector_id,
            "summary": summary[:3000],
            "result": result,
        }
        if os.getenv("DEEPSEEK_API_KEY") and job.get("status") == "completed":
            try:
                out = self._ask_deepseek(context)
                out["engine"] = "deepseek"
                return self._normalize(out, url, connector_id, access_class, governance)
            except Exception as exc:
                pass
        out = self._fallback(context)
        out["engine"] = "heuristic"
        out["planner_note"] = out.get("planner_note") or "Heuristic probe analysis."
        return self._normalize(out, url, connector_id, access_class, governance)

    def _ask_deepseek(self, context: dict[str, Any]) -> dict[str, Any]:
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/chat/completions")
        system = """Analyze a source_probe result for research data procurement.
Return JSON:
{
  "feasibility": "instant_download|manifest|scrape|credentials|blocked|unknown",
  "access_class": "public_government|public_academic|public_unknown|commercial",
  "summary": "1-2 sentences for the researcher",
  "recommended_action": "probe_only|approve_collect|needs_credentials|skip",
  "collect_plan": null or {"job_type":"source_probe|http_manifest|scraper_run","title":"...","url":"...","script_key":"cake_board|yourator_board|...","items":[...],"launchable":true},
  "license_note": "short note",
  "estimated_effort": "minutes|hours|blocked"
}"""
        body = json.dumps(
            {
                "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
                ],
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        request = urllib.request.Request(base_url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return json.loads(payload["choices"][0]["message"]["content"])

    def _fallback(self, context: dict[str, Any]) -> dict[str, Any]:
        url = context["url"]
        access = context["access_class"]
        summary = context.get("summary") or ""
        feasibility = "unknown"
        action = "probe_only"
        collect_plan = None
        if access == "commercial":
            feasibility = "credentials"
            action = "needs_credentials"
        elif classify_fetch_mode(url) == "direct_http" or re.search(
            r"\.(csv|tsv|json|zip|parquet)(\?|$)", url, re.I
        ):
            feasibility = "instant_download"
            action = "approve_collect"
            collect_plan = build_http_manifest_plan_for_url(
                url,
                title=f"Collect {url.split('/')[-1][:60]}",
            )
        elif "download" in summary.lower() or "dataset" in summary.lower() or context.get("connector_id"):
            feasibility = "manifest"
            action = "approve_collect"
            collect_plan = self._manifest_from_connector(context, url)
        elif "html" in summary.lower() or context.get("result", {}).get("access_mode") == "html_catalog":
            feasibility = "scrape"
            action = "approve_collect"
            collect_plan = plan_for_url(url, mode="datasets", title=f"Scrape datasets from {url[:60]}")
            if collect_plan.get("job_type") == "scraper_run":
                feasibility = "scrape"
        return {
            "feasibility": feasibility,
            "access_class": access,
            "summary": summary or f"Probed {url}",
            "recommended_action": action,
            "collect_plan": collect_plan,
            "license_note": "Commercial" if access == "commercial" else "Public source — verify license before redistribution.",
            "estimated_effort": "blocked" if access == "commercial" else "minutes",
        }

    def _normalize(
        self,
        raw: dict[str, Any],
        url: str,
        connector_id: str | None,
        access_class: str,
        governance: dict[str, Any],
    ) -> dict[str, Any]:
        action = str(raw.get("recommended_action") or "probe_only")
        collect = raw.get("collect_plan")
        if collect and isinstance(collect, dict):
            if collect.get("job_type") == "source_probe" and classify_fetch_mode(url) == "direct_http":
                collect = build_http_manifest_plan_for_url(
                    url,
                    title=str(collect.get("title") or f"Collect {url.split('/')[-1][:40]}"),
                )
            collect.setdefault("launchable", True)
            if collect.get("job_type") == "http_manifest":
                item_url = str(collect.get("url") or url or "")
                if not item_url and collect.get("items"):
                    item_url = str((collect["items"][0] or {}).get("url") or "")
                if item_url and (
                    classify_fetch_mode(item_url) == "direct_http" or not collect.get("destination")
                ):
                    base = build_http_manifest_plan_for_url(item_url, title=str(collect.get("title") or ""))
                    collect = {**base, **collect}
                if connector_id:
                    collect["connector_id"] = connector_id
                if self.procurement:
                    collect = enrich_http_manifest_plan(collect, self.procurement)
            elif connector_id and not collect.get("items"):
                collect.setdefault("url", url)
            access = str(raw.get("access_class") or access_class)
            if not allow_auto_collect(access, governance):
                collect = None
                action = "needs_credentials"
        return {
            "url": url,
            "connector_id": connector_id,
            "feasibility": raw.get("feasibility", "unknown"),
            "access_class": raw.get("access_class", access_class),
            "summary": raw.get("summary", ""),
            "recommended_action": action,
            "collect_plan": collect,
            "license_note": raw.get("license_note", ""),
            "estimated_effort": raw.get("estimated_effort", ""),
            "engine": raw.get("engine", "heuristic"),
        }

    def _manifest_from_connector(self, context: dict[str, Any], url: str) -> dict[str, Any] | None:
        cid = context.get("connector_id")
        if self.procurement and cid:
            try:
                return self.procurement.manifest_plan_from_connector(str(cid), limit=25)
            except ValueError:
                pass
        return build_http_manifest_plan_for_url(
            url,
            title=f"Collect: {url[:60]}",
        )
