#!/usr/bin/env python3
"""Job-first procure — measure → craft → pending job without Composer prose.

Faculty (or Ask tools) can land a reviewable collect from L0 desk measure alone.
Composer may narrate later; it is not required to create the pending job.
"""

from __future__ import annotations

from typing import Any


def _extract_plan(crafted: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(crafted, dict):
        return {}
    plan = crafted.get("plan")
    return dict(plan) if isinstance(plan, dict) else dict(crafted)


def propose_pending_collect(
    gateway: Any,
    *,
    query: str = "",
    rail_context: dict[str, Any] | None = None,
    research_need: str = "",
    url: str = "",
    title: str = "",
) -> dict[str, Any]:
    """Craft a collect plan from open workspace / typed need and submit pending_approval."""
    from scripts.research_data_mcp.craft_collect import craft_collect_plan
    from scripts.research_data_mcp.desk_ask_grounding import (
        measure_ask_desk,
        resolve_ask_measure_query,
        serialize_desk_facts_ui,
    )
    from scripts.research_data_mcp.procure_lifecycle import procure_phase_report

    rail = rail_context if isinstance(rail_context, dict) else {}
    measure_q = resolve_ask_measure_query(query or research_need or "collect", rail)
    measured = measure_ask_desk(gateway, measure_q or research_need or query, rail_context=rail)
    desk_ui = serialize_desk_facts_ui(measured)

    routes = list(measured.get("routes") or [])
    held = list(measured.get("held") or [])
    if measured.get("strong_held") and held:
        return {
            "ok": False,
            "action": "already_held",
            "phase": "query_ready"
            if any(str(r.get("analysis_readiness") or "") in {"query_ready", "instant"} for r in held)
            else "registered",
            "desk_facts": desk_ui,
            "message": "Library already measures holdings for this need — collect not proposed.",
            "held": held[:5],
            "composer_required": False,
        }

    need = (research_need or query or measure_q or "").strip()
    route = routes[0] if routes else {}
    source_id = str(route.get("source_id") or route.get("collect_via") or "").strip()
    route_title = str(route.get("title") or route.get("label") or source_id or "Declared route").strip()
    craft_url = str(
        url
        or route.get("url")
        or route.get("homepage")
        or route.get("collect_url")
        or ""
    ).strip()

    if not craft_url:
        return {
            "ok": False,
            "action": "need_url",
            "phase": "crafted",
            "desk_facts": desk_ui,
            "route": {"source_id": source_id, "title": route_title},
            "message": (
                f"L0 measured route `{source_id or route_title}` but no concrete URL — "
                "pass url= to propose a pending collect (job-first path refuses inventing targets)."
            ),
            "composer_required": False,
        }

    try:
        crafted = craft_collect_plan(
            research_need=need or route_title,
            url=craft_url,
            title=title or f"Collect · {route_title}"[:120],
        )
    except ValueError as exc:
        return {
            "ok": False,
            "action": "craft_failed",
            "phase": "crafted",
            "desk_facts": desk_ui,
            "error": str(exc)[:400],
            "composer_required": False,
        }

    plan = _extract_plan(crafted)
    job_title = str(title or plan.get("title") or f"Collect · {route_title}")[:160]
    submitted = gateway.submit_yzu_job(plan, title=job_title, auto_approve=False)
    # JobService returns {"job": {...}, "plan": ...}; orchestrator may return the job dict.
    if isinstance(submitted, dict) and isinstance(submitted.get("job"), dict):
        job_dict = submitted["job"]
    elif isinstance(submitted, dict) and submitted.get("id"):
        job_dict = submitted
    else:
        return {
            "ok": False,
            "action": "submit_failed",
            "phase": "crafted",
            "desk_facts": desk_ui,
            "craft": crafted if isinstance(crafted, dict) else {"plan": plan},
            "plan": plan,
            "submit": submitted,
            "error": str(
                (submitted or {}).get("error")
                if isinstance(submitted, dict)
                else "submit_yzu_job returned no job"
            )[:400],
            "composer_required": False,
        }
    if not str(job_dict.get("id") or "").strip():
        return {
            "ok": False,
            "action": "submit_failed",
            "phase": "crafted",
            "desk_facts": desk_ui,
            "craft": crafted if isinstance(crafted, dict) else {"plan": plan},
            "plan": plan,
            "submit": submitted,
            "error": "submit returned empty job id",
            "composer_required": False,
        }
    phase = procure_phase_report(job_dict)
    return {
        "ok": True,
        "action": "pending_collect_proposed",
        "composer_required": False,
        "desk_facts": desk_ui,
        "route": {"source_id": source_id, "title": route_title},
        "craft": crafted if isinstance(crafted, dict) else {"plan": plan},
        "plan": plan,
        "job": job_dict,
        "job_id": str(job_dict.get("id") or ""),
        "lifecycle": phase,
        "message": (
            f"Pending collect job `{job_dict.get('id')}` proposed from L0 measure "
            f"(route={source_id or 'craft'}). Researcher approval required — Composer not used."
        ),
    }
