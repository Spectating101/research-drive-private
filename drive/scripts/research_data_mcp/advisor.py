#!/usr/bin/env python3
"""Legacy dataset advisor — deterministic catalog hints; Composer judges fit."""

from __future__ import annotations

import json
import re
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.research_data_mcp.gateway import ResearchDataGateway


class DatasetAdvisor:
    def __init__(self, gateway: ResearchDataGateway) -> None:
        self.gateway = gateway

    def advise(
        self,
        goal: str,
        *,
        current_dataset_id: str = "",
        current_task_id: str = "",
        limit: int = 5,
    ) -> dict[str, Any]:
        goal = goal.strip()
        if not goal:
            raise ValueError("goal is required — describe what you are trying to analyze or procure")
        catalog = self.gateway.procurement_catalog(q=goal, limit=80)
        source_plan = self.gateway.plan_sources(goal, limit=min(limit * 3, 25))
        context = {
            "goal": goal,
            "current_dataset_id": current_dataset_id.strip(),
            "current_task_id": current_task_id.strip(),
            "catalog_summary": catalog.get("summary", {}),
            "registry_hits": catalog.get("registry", [])[:20],
            "queue_tasks": catalog.get("queue_tasks", [])[:20],
            "pipelines": catalog.get("pipelines", []),
            "source_plan_top": (source_plan.get("rows") or [])[:12],
        }
        body = self._fallback(context, limit=limit)
        body["advisor_note"] = "Deterministic catalog ranking — Composer judges fit via MCP."
        return body

    def _fallback(self, context: dict[str, Any], *, limit: int) -> dict[str, Any]:
        goal = context["goal"].lower()
        tokens = set(re.findall(r"[a-z][a-z0-9_]{2,}", goal))
        current = context.get("current_dataset_id") or context.get("current_task_id") or ""

        scored: list[tuple[float, dict[str, str]]] = []

        for row in context.get("registry_hits") or []:
            blob = " ".join(
                str(row.get(k, "")) for k in ("dataset_id", "name", "grain", "analysis_readiness", "recommended_use")
            ).lower()
            score = sum(1.0 for t in tokens if t in blob)
            if row.get("analysis_readiness") == "instant":
                score += 0.5
            scored.append(
                (
                    score,
                    {
                        "id": row["dataset_id"],
                        "kind": "registry_dataset",
                        "reason": row.get("recommended_use") or row.get("grain", ""),
                    },
                )
            )

        for row in context.get("queue_tasks") or []:
            blob = f"{row.get('id', '')} {row.get('title', '')} {row.get('output_hint', '')}".lower()
            score = sum(1.2 for t in tokens if t in blob)
            if row.get("runnable"):
                score += 0.3
            scored.append((score, {"id": row["id"], "kind": "queue_task", "reason": row.get("title", "")}))

        for row in context.get("pipelines") or []:
            blob = f"{row.get('id', '')} {row.get('label', '')}".lower()
            score = sum(0.8 for t in tokens if t in blob)
            scored.append((score, {"id": row["id"], "kind": "pipeline", "reason": row.get("label", "")}))

        for row in context.get("source_plan_top") or []:
            rid = str(row.get("dataset_id") or row.get("source_id") or "")
            if not rid:
                continue
            blob = json.dumps(row, ensure_ascii=False).lower()
            score = sum(0.6 for t in tokens if t in blob)
            scored.append(
                (
                    score,
                    {
                        "id": rid,
                        "kind": "registry_dataset",
                        "reason": str(row.get("access_recommendation") or row.get("name", "")),
                    },
                )
            )

        if tokens & {"sec", "edgar", "filing", "filings", "10k", "10q", "cik"}:
            for task in context.get("queue_tasks") or []:
                blob = f"{task.get('id', '')} {task.get('title', '')}".lower()
                if any(token in blob for token in ("sec", "edgar", "cik", "filing")):
                    scored.append(
                        (
                            5.0,
                            {
                                "id": task["id"],
                                "kind": "queue_task",
                                "reason": task.get("title") or task["id"],
                            },
                        )
                    )
        if tokens & {"news", "headline", "shock", "gdelt"}:
            scored.append(
                (
                    4.0,
                    {
                        "id": "gdelt_asia_daily_country_panel",
                        "kind": "registry_dataset",
                        "reason": "Instant local GDELT Asia country panel",
                    },
                )
            )
        if tokens & {"doi", "datacite", "metadata", "citation"} and not tokens.isdisjoint({"harvest", "datacite", "doi", "metadata", "mirror"}):
            scored.append(
                (
                    3.5,
                    {
                        "id": "datacite_local_harvest_status",
                        "kind": "registry_dataset",
                        "reason": "Check local DataCite mirror before re-harvesting",
                    },
                )
            )

        scored.sort(key=lambda pair: pair[0], reverse=True)
        seen: set[str] = set()
        recommended: list[dict[str, str]] = []
        for _score, item in scored:
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            recommended.append(item)
            if len(recommended) >= limit:
                break

        not_recommended: list[dict[str, str]] = []
        verdict = "good_fit"
        if current:
            current_l = current.lower()
            top_ids = {r["id"].lower() for r in recommended[:3]}
            if current_l not in top_ids and recommended:
                verdict = "wrong_fit"
                not_recommended.append(
                    {
                        "id": current,
                        "kind": "user_selection",
                        "reason": f"'{current}' is weak for this goal; prefer {recommended[0]['id']} ({recommended[0]['kind']}).",
                    }
                )
            elif current_l in top_ids:
                verdict = "good_fit"

        message = (
            f"For '{context['goal']}', start with {recommended[0]['id']} ({recommended[0]['kind']})."
            if recommended
            else "No strong catalog match — try research_plan_sources or procurement_probe_public_source."
        )
        if verdict == "wrong_fit" and not_recommended:
            message = not_recommended[0]["reason"]

        next_steps: list[str] = []
        if recommended:
            kind = recommended[0]["kind"]
            rid = recommended[0]["id"]
            if kind == "registry_dataset":
                next_steps.append(f"research_describe_dataset('{rid}') then research_query_dataset if instant")
            elif kind == "queue_task":
                next_steps.append(f"yzu_submit_job with job_type=collection_queue_task, task_id={rid}")
            elif kind == "pipeline":
                next_steps.append(f"yzu_submit_job with job_type=registered_pipeline, pipeline_id={rid}")
            elif kind == "probe":
                next_steps.append(f"procurement_probe_public_source on the source URL, then approve connector")

        return {
            "verdict": verdict,
            "message": message,
            "recommended": recommended,
            "not_recommended": not_recommended,
            "next_steps": next_steps,
            "engine": "deterministic",
            "goal": context["goal"],
        }
