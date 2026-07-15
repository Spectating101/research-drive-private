"""Derived Discover History — intents, subscriptions, and linked runs only.

Raw global job queues stay out unless the job is linked to a Discover intent,
subscription, or discover_* request source.
"""

from __future__ import annotations

from typing import Any

from scripts.research_data_mcp.discover_progress import attach_subscription_progress

_DISCOVER_JOB_SOURCES = frozenset(
    {
        "discover_ui",
        "discover_intent",
        "discover_refresh",
        "discover",
    }
)


def _job_linked_to_discover(job: dict[str, Any]) -> bool:
    if not isinstance(job, dict):
        return False
    plan = job.get("plan") if isinstance(job.get("plan"), dict) else {}
    request = job.get("request") if isinstance(job.get("request"), dict) else {}
    if plan.get("discover_intent_id") or request.get("discover_intent_id"):
        return True
    if plan.get("discover_subscription_id") or request.get("discover_subscription_id"):
        return True
    src = str(request.get("source") or plan.get("source") or "").strip().lower()
    if src in _DISCOVER_JOB_SOURCES or src.startswith("discover"):
        return True
    return False


def _intent_item(intent: dict[str, Any]) -> dict[str, Any]:
    state = intent.get("state") if isinstance(intent.get("state"), dict) else {}
    collection = state.get("collection") if isinstance(state.get("collection"), dict) else {}
    candidate = state.get("candidate") if isinstance(state.get("candidate"), dict) else {}
    return {
        "kind": "intent",
        "id": intent.get("id"),
        "title": intent.get("title") or intent.get("research_need") or "Discover intent",
        "status": state.get("status") or "draft",
        "updated_at": intent.get("updated_at") or intent.get("created_at"),
        "created_at": intent.get("created_at"),
        "intent_id": intent.get("id"),
        "candidate_key": candidate.get("candidate_key") or "",
        "job_id": collection.get("job_id") or "",
        "summary": str(intent.get("research_need") or "")[:300],
    }


def _subscription_item(sub: dict[str, Any]) -> dict[str, Any]:
    cadence = str(sub.get("cadence") or "manual")
    requested = str(sub.get("requested_schedule") or "").strip()
    title_src = sub.get("source_id") or sub.get("connector_id") or sub.get("candidate_key") or sub.get("id")
    cadence_label = requested or cadence
    note = str(sub.get("execution_note") or "Refresh subscription")
    summary = f"{cadence_label} · {note}" if cadence_label else note
    item = {
        "kind": "subscription",
        "id": sub.get("id"),
        "title": f"Refresh · {title_src}",
        "status": sub.get("status"),
        "updated_at": sub.get("updated_at") or sub.get("created_at"),
        "created_at": sub.get("created_at"),
        "intent_id": sub.get("intent_id") or "",
        "subscription_id": sub.get("id"),
        "source_id": sub.get("source_id") or "",
        "connector_id": sub.get("connector_id") or "",
        "candidate_key": sub.get("candidate_key") or "",
        "cadence": cadence,
        "requested_schedule": requested,
        "schedule_spec": sub.get("schedule_spec") or {},
        "enabled": bool(sub.get("enabled")),
        "execution_mode": sub.get("execution_mode"),
        "auto_refresh": bool(sub.get("auto_refresh")),
        "last_run_at": sub.get("last_run_at"),
        "next_run_at": sub.get("next_run_at"),
        "last_job_id": sub.get("last_job_id"),
        "last_run_status": sub.get("last_run_status"),
        "last_run_plan": sub.get("last_run_plan"),
        "summary": summary,
    }
    # Prefer store-attached progress; rebuild if absent.
    if not item.get("progress"):
        item = attach_subscription_progress(
            {
                **item,
                "execution_mode": sub.get("execution_mode"),
                "auto_refresh": bool(sub.get("auto_refresh")),
                "cadence": cadence,
                "schedule_spec": sub.get("schedule_spec") or {},
                "last_run_at": sub.get("last_run_at"),
                "next_run_at": sub.get("next_run_at"),
                "last_job_id": sub.get("last_job_id"),
                "last_run_status": sub.get("last_run_status"),
                "last_run_plan": sub.get("last_run_plan"),
                "last_run_error": sub.get("last_run_error"),
            }
        )
    else:
        item["progress"] = sub.get("progress")
    return item


def _run_item(job: dict[str, Any], *, intent_id: str = "", subscription_id: str = "") -> dict[str, Any]:
    plan = job.get("plan") if isinstance(job.get("plan"), dict) else {}
    request = job.get("request") if isinstance(job.get("request"), dict) else {}
    return {
        "kind": "collection_run",
        "id": job.get("id"),
        "title": job.get("title") or plan.get("title") or "Discover collection",
        "status": job.get("status"),
        "updated_at": job.get("updated_at") or job.get("created_at"),
        "created_at": job.get("created_at"),
        "intent_id": intent_id or plan.get("discover_intent_id") or request.get("discover_intent_id") or "",
        "subscription_id": subscription_id
        or plan.get("discover_subscription_id")
        or request.get("discover_subscription_id")
        or "",
        "job_id": job.get("id"),
        "candidate_key": plan.get("candidate_key") or request.get("candidate_key") or "",
        "summary": f"Job {job.get('status') or 'unknown'}",
        "progress": {
            "phase": str(job.get("status") or "unknown"),
            "label": f"Collection {job.get('status') or 'unknown'}",
            "last_job_id": job.get("id"),
            "last_run_status": job.get("status"),
        },
    }


def build_discover_history(
    *,
    intents: list[dict[str, Any]] | None = None,
    subscriptions: list[dict[str, Any]] | None = None,
    jobs: list[dict[str, Any]] | None = None,
    limit: int = 50,
    kind: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    """Collapse intents + subscriptions + Discover-linked runs into researcher history."""
    limit = max(1, min(int(limit or 50), 200))
    kind_filter = str(kind or "").strip().lower()
    session_id = str(session_id or "").strip()

    items: list[dict[str, Any]] = []
    intent_job_ids: set[str] = set()

    for intent in intents or []:
        if session_id and str(intent.get("session_id") or "") != session_id:
            continue
        item = _intent_item(intent)
        items.append(item)
        jid = str(item.get("job_id") or "")
        if jid:
            intent_job_ids.add(jid)
        # Collapse: if job attached on intent payload, emit one run under the intent.
        job = intent.get("job") if isinstance(intent.get("job"), dict) else None
        if job and _job_linked_to_discover(job):
            items.append(_run_item(job, intent_id=str(intent.get("id") or "")))
            intent_job_ids.add(str(job.get("id") or ""))

    for sub in subscriptions or []:
        items.append(_subscription_item(sub))

    for job in jobs or []:
        jid = str(job.get("id") or "")
        if jid and jid in intent_job_ids:
            continue  # already collapsed under intent
        if not _job_linked_to_discover(job):
            continue
        items.append(_run_item(job))

    if kind_filter:
        if kind_filter in {"intent", "intents"}:
            items = [i for i in items if i.get("kind") == "intent"]
        elif kind_filter in {"subscription", "subscriptions", "refresh"}:
            items = [i for i in items if i.get("kind") == "subscription"]
        elif kind_filter in {"run", "runs", "collection_run", "job", "jobs"}:
            items = [i for i in items if i.get("kind") == "collection_run"]

    items.sort(key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)
    clipped = items[:limit]
    return {
        "items": clipped,
        "total": len(clipped),
        "filters_applied": {
            "kind": kind_filter or None,
            "session_id": session_id or None,
            "limit": limit,
            "excludes_raw_global_jobs": True,
        },
    }
