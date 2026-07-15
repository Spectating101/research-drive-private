#!/usr/bin/env python3
"""Stack-fast Ask turns — direct equipment paths that should not wait on Composer."""

from __future__ import annotations

import re
from typing import Any

from scripts.research_data_mcp.desk_brain import AgentTurn
from scripts.research_data_mcp.http_router import _compact_probe_response
from scripts.research_data_mcp.scrape_plan import extract_urls

_PROBE_INTENT = re.compile(r"\bprobe\b", re.I)


def probe_url_from_message(message: str, rail_context: dict[str, Any] | None = None) -> str | None:
    """Return a URL when the user clearly asked to probe, not plan."""
    text = (message or "").strip()
    if not text:
        return None
    urls = extract_urls(text)
    if not urls:
        return None
    actions = rail_context.get("actions") if isinstance(rail_context, dict) else None
    if isinstance(actions, list) and any(str(a).lower() == "probe" for a in actions):
        return urls[0]
    if _PROBE_INTENT.search(text[:160]):
        return urls[0]
    return None


def is_direct_probe_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    return probe_url_from_message(message, rail_context) is not None


_SEARCH_BLOCK = re.compile(
    r"\b(probe|collect|compare|plan|explain|why|how\s+should|summarize)\b",
    re.I,
)
_SEARCH_PATTERNS = (
    re.compile(
        r"^\s*(?:search|find|look\s+up)(?:\s+(?:the\s+)?(?:vault|lab|library|registry))?(?:\s+for)?\s+(.+?)\s*[?.!]*\s*$",
        re.I,
    ),
    re.compile(
        r"^\s*what\s+do\s+we\s+have\s+(?:on|for|about)\s+(.+?)\s*[?.!]*\s*$",
        re.I,
    ),
    re.compile(
        r"^\s*search\s+(?!https?://)([a-z0-9][\w\s\-./]{1,120}?)\s*[?.!]*\s*$",
        re.I,
    ),
)


def search_query_from_message(message: str, rail_context: dict[str, Any] | None = None) -> str | None:
    """Return a query when the user clearly asked to search the vault, not plan."""
    text = (message or "").strip()
    if not text or _SEARCH_BLOCK.search(text[:200]):
        return None
    # Discover Explore search is a different equipment path — do not steal as vault search.
    if _DISCOVER_SEARCH_HINT.search(text[:280]):
        return None
    rail = rail_context if isinstance(rail_context, dict) else {}
    actions = [str(a).lower() for a in (rail.get("actions") or [])]
    if "search" in actions:
        explicit = str(rail.get("search_query") or "").strip()
        if explicit:
            return explicit
    for pattern in _SEARCH_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        query = match.group(1).strip().strip('"').strip("'")
        if len(query) >= 2:
            return query
    return None


def is_direct_search_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    return search_query_from_message(message, rail_context) is not None


_DISCOVER_SEARCH_HINT = re.compile(
    r"\bresearch_discover_(?:source_)?search\b|"
    r"\bdiscover\s+(?:source[_\s-]*)?(?:search|catalog|explore)\b|"
    r"\bsearch\s+(?:the\s+)?discover\b|"
    r"\b(?:search|find|look\s+up)\s+(?:in\s+|across\s+)?(?:discover|catalog)\b|"
    r"\bdiscover\s+sources?\b",
    re.I,
)

_DISCOVER_QUERY_PATTERNS = (
    re.compile(
        r"research_discover_(?:source_)?search\s+for\s+query\s+['\"]?([^'\".,;\n]+)['\"]?",
        re.I,
    ),
    re.compile(
        r"research_discover_(?:source_)?search(?:\s+with)?(?:\s+query)?\s*[:=]\s*['\"]?([^'\"\n]+)['\"]?",
        re.I,
    ),
    re.compile(
        r"(?:search|find|look\s+up)\s+(?:the\s+)?(?:discover(?:\s+catalog|\s+sources?)?|catalog)\s+(?:for\s+)?(.+?)\s*[?.!]*\s*$",
        re.I,
    ),
    re.compile(
        r"discover\s+(?:source[_\s-]*)?(?:search|catalog|explore)\s+(?:for\s+)?(.+?)\s*[?.!]*\s*$",
        re.I,
    ),
    re.compile(
        r"\bquery\s+['\"]([^'\"]+)['\"]",
        re.I,
    ),
)


def discover_query_from_message(message: str, rail_context: dict[str, Any] | None = None) -> str | None:
    """Return a query when the user asked to search Discover Explore (not vault)."""
    text = (message or "").strip()
    if not text:
        return None
    rail = rail_context if isinstance(rail_context, dict) else {}
    actions = [str(a).lower() for a in (rail.get("actions") or [])]
    if any(a in {"discover_search", "discover_sources", "search_discover"} for a in actions):
        explicit = str(rail.get("search_query") or rail.get("discover_query") or "").strip()
        if explicit:
            return explicit
    # Multi-step judgment (search → pick → intent) belongs to Composer, not a direct query steal.
    lowered = text.lower()
    if any(tok in lowered for tok in ("pick the best", "then create", "then record", "and then create")):
        return None
    if "create" in lowered and "intent" in lowered and "search" in lowered and len(text) > 140:
        return None
    if not _DISCOVER_SEARCH_HINT.search(text[:320]) and "discover_search" not in actions:
        return None
    for pattern in _DISCOVER_QUERY_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        query = match.group(1).strip().strip('"').strip("'").rstrip(".,;")
        query = re.sub(r"^(?:for\s+)?(?:query\s+)?", "", query, flags=re.I).strip()
        query = re.sub(r"\s+", " ", query)
        # Strip trailing instruction clauses
        query = re.split(
            r"\b(?:list\s+top|do\s+not|return\s+|confirm\s+|ignore\s+|use\s+only)\b",
            query,
            maxsplit=1,
            flags=re.I,
        )[0].strip(" .,;:-")
        if len(query) >= 2:
            return query[:160]
    # Fallback: quoted phrase after discover hint
    q = re.search(r"['\"]([^'\"]{2,120})['\"]", text)
    if q:
        return q.group(1).strip()[:160]
    return None


def is_direct_discover_search_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    return discover_query_from_message(message, rail_context) is not None


def _discover_search_reply(query: str, out: dict[str, Any]) -> str:
    rows = list(out.get("results") or [])
    if not rows:
        for sec in out.get("sections") or []:
            if isinstance(sec, dict) and sec.get("id") == "discover_sources":
                rows = list(sec.get("rows") or [])
                break
    mode = out.get("search_mode") or "catalog"
    if not rows:
        return (
            f"No Discover catalog sources for **{query}** (mode={mode}). "
            "Try live search, or search the vault for lab holdings."
        )
    lines = [f"Discover catalog · **{len(rows)}** source(s) for **{query}** (mode={mode}):"]
    for i, row in enumerate(rows[:6], 1):
        sid = row.get("source_id") or row.get("connector_id") or "?"
        title = row.get("title") or row.get("label") or sid
        access = row.get("access_mode") or "—"
        lines.append(f"{i}. `{sid}` — {title} · access=`{access}`")
    return "\n".join(lines)


def try_direct_discover_search_turn(
    gateway: Any,
    message: str,
    state: dict[str, Any],
) -> AgentTurn | None:
    """Run Discover Explore catalog search directly — not vault/registry."""
    query = discover_query_from_message(message, state.get("rail_context"))
    if not query:
        return None
    live = bool(re.search(r"\blive\b", message or "", re.I))
    out = gateway.discover_source_search(query, limit=12, live=live)
    # Shape like research_discover_search for FE/artifacts
    rows = list(out.get("results") or [])
    shaped = {
        "query": query,
        "result_kind": "discover_sources",
        "search_mode": out.get("search_mode") or ("live" if live else "catalog"),
        "sections": [{"id": "discover_sources", "label": "Discover catalog", "rows": rows}] if rows else [],
        "results": rows,
        "catalog_total": len(rows),
        "lab_total": 0,
        "total": len(rows),
        "index_miss": not rows,
    }
    return AgentTurn(
        plan={"action": "discover_search", "fast_path": True, "query": query},
        action_result={
            "action": "discover_search",
            "fast_path": True,
            "query": query,
            "result_kind": "discover_sources",
            "search": shaped,
            "discover": shaped,
            "results": rows,
            "total": len(rows),
            "search_mode": shaped["search_mode"],
        },
        reply=_discover_search_reply(query, shaped),
        suggested_prompts=[
            f"Preview source {(rows[0].get('source_id') if rows else query)}",
            f"Create a Discover intent for {query}",
        ],
        tool_name="research_discover_source_search",
    )


_DOI_RE = re.compile(r"(?:doi:\s*)?(10\.\d{4,9}/[^\s'\"<>]+)", re.I)
_COLLECT_BLOCK = re.compile(r"\b(plan|compare|explain|why|should|summarize)\b", re.I)
_COLLECT_INTENT = re.compile(r"\bcollect\b", re.I)
_DESCRIBE_PATTERNS = (
    re.compile(
        r"^\s*(?:describe|show|open|inspect)\s+(?:dataset\s+)?([a-z0-9][\w:./-]{2,120})\s*[?.!]*\s*$",
        re.I,
    ),
)
_QUERY_PATTERNS = (
    re.compile(
        r"^\s*query\s+(?:dataset\s+)?([a-z0-9][\w:./-]{2,120})(?:\s+limit\s+(\d+))?\s*[?.!]*\s*$",
        re.I,
    ),
)


def doi_from_message(message: str, rail_context: dict[str, Any] | None = None) -> str | None:
    text = (message or "").strip()
    if not text:
        return None
    rail = rail_context if isinstance(rail_context, dict) else {}
    actions = [str(a).lower() for a in (rail.get("actions") or [])]
    explicit = str(rail.get("doi") or "").strip()
    if explicit and ("collect" in actions or _COLLECT_INTENT.search(text[:120])):
        match = _DOI_RE.search(explicit)
        return match.group(1) if match else explicit
    if not _COLLECT_INTENT.search(text[:160]):
        return None
    if _COLLECT_BLOCK.search(text[:120]):
        return None
    match = _DOI_RE.search(text)
    return match.group(1) if match else None


def is_direct_collect_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    return doi_from_message(message, rail_context) is not None


def dataset_id_from_message(
    message: str,
    rail_context: dict[str, Any] | None = None,
    *,
    mode: str = "describe",
) -> str | None:
    text = (message or "").strip()
    if not text:
        return None
    rail = rail_context if isinstance(rail_context, dict) else {}
    explicit = str(rail.get("dataset_id") or "").strip()
    if explicit:
        return explicit
    patterns = _DESCRIBE_PATTERNS if mode == "describe" else _QUERY_PATTERNS
    for pattern in patterns:
        match = pattern.match(text)
        if match:
            return match.group(1).strip()
    return None


def query_limit_from_message(message: str) -> int:
    text = (message or "").strip()
    for pattern in _QUERY_PATTERNS:
        match = pattern.match(text)
        if match and match.lastindex and match.lastindex >= 2 and match.group(2):
            try:
                return max(1, min(50, int(match.group(2))))
            except ValueError:
                pass
    return 10


def is_direct_describe_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    return dataset_id_from_message(message, rail_context, mode="describe") is not None


def is_direct_query_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    return dataset_id_from_message(message, rail_context, mode="query") is not None


def is_direct_discover_collect_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    return parse_discover_collect_request(message, rail_context) is not None


def is_direct_approve_job_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    return bool(_APPROVE_JOB.search((message or "").strip()[:200]))


def is_direct_discovery_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    return (
        is_direct_probe_message(message, rail_context)
        or is_direct_search_message(message, rail_context)
        or is_direct_discover_search_message(message, rail_context)
        or is_direct_discover_collect_message(message, rail_context)
        or is_direct_approve_job_message(message, rail_context)
        or (parse_scrape_request(message, rail_context) is not None)
        or is_direct_status_message(message)
        or is_direct_describe_message(message, rail_context)
        or is_direct_query_message(message, rail_context)
        or is_direct_schedule_message(message, rail_context)
        or is_direct_intent_message(message, rail_context)
        or is_direct_subscription_lifecycle_message(message, rail_context)
        or (parse_refresh_tick_request(message) is not None)
    )


def is_direct_procurement_submit_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    """Explicit collect/submit — skips Composer but work continues on cluster."""
    return is_direct_collect_message(message, rail_context)


def is_direct_equipment_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    """Any turn that should not wait on Composer priming or planning."""
    return is_direct_discovery_message(message, rail_context) or is_direct_procurement_submit_message(
        message, rail_context
    )


_STATUS_INTENT = re.compile(r"^(?:status|check\s+status|job\s+status)\s*[?.!]*$", re.I)


def is_direct_status_message(message: str) -> bool:
    return bool(_STATUS_INTENT.match((message or "").strip()))


def try_direct_status_turn(
    gateway: Any,
    message: str,
    state: dict[str, Any],
) -> AgentTurn | None:
    if not is_direct_status_message(message):
        return None
    lines: list[str] = []
    if state.get("composer_pending"):
        lines.append(
            "Composer is still finishing your previous planning turn in the background. "
            "You can keep using Discover and Probe while it completes."
        )
    pending_job_id = str(state.get("pending_job_id") or "").strip()
    if pending_job_id:
        try:
            job = gateway.orchestrator.store.get(pending_job_id)
            status = str(job.get("status") or "unknown")
            lines.append(f"Pending job `{pending_job_id[:12]}…` is **{status}**.")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"Pending job `{pending_job_id[:12]}…` — could not load status ({exc}).")
    campaign_id = str(state.get("campaign_id") or "").strip()
    if campaign_id:
        lines.append(f"Active campaign: `{campaign_id[:16]}…`")
    if not lines:
        lines.append("No pending Composer turn or collection job for this session.")
    return AgentTurn(
        plan={"action": "status", "fast_path": True},
        action_result={"action": "status", "fast_path": True},
        reply="\n".join(lines),
        suggested_prompts=["Search vault for related datasets", "Probe a candidate URL"],
        tool_name="desk_status",
    )


def _search_reply(query: str, out: dict[str, Any]) -> str:
    rows = list(out.get("rows") or [])
    if not rows:
        note = ""
        if out.get("timed_out_layers"):
            note = f" Some layers timed out ({', '.join(out['timed_out_layers'])}); retry Discover for a fuller pass."
        return f"No vault matches for **{query}**.{note}"
    lines = [f"Found **{len(rows)}** match(es) for **{query}**:"]
    for row in rows[:6]:
        title = str(row.get("title") or row.get("dataset_id") or row.get("doi") or row.get("id") or "untitled")
        kind = str(row.get("kind") or row.get("source") or "result")
        lines.append(f"- {title} ({kind})")
    if len(rows) > 6:
        lines.append(f"- …and {len(rows) - 6} more")
    if out.get("timed_out_layers"):
        lines.append(f"_Partial results — timed out: {', '.join(out['timed_out_layers'])}_")
    return "\n".join(lines)


def try_direct_search_turn(
    gateway: Any,
    message: str,
    state: dict[str, Any],
) -> AgentTurn | None:
    """Run vault search equipment directly, skip Composer."""
    query = search_query_from_message(message, state.get("rail_context"))
    if not query:
        return None
    email = str(state.get("user_email") or "").strip()
    if email:
        out = gateway.unified_search_with_profile(query, email=email, limit=12, parallel_profile=True)
    else:
        out = gateway.unified_dataset_search(query, limit=12)
    reply = _search_reply(query, out)
    return AgentTurn(
        plan={"action": "search", "fast_path": True, "query": query},
        action_result={
            "action": "search",
            "fast_path": True,
            "query": query,
            "search": out,
            "preview": out,
            "total": out.get("total"),
            "timed_out_layers": out.get("timed_out_layers") or [],
        },
        reply=reply,
        suggested_prompts=[
            f"Probe the top result for {query}",
            f"Queue cluster collection for the best {query} match",
        ],
        tool_name="research_unified_search",
    )



_SCHEDULE_INTENT = re.compile(
    r"\b(schedule|subscribe|subscription|auto[- ]?refresh|recurring|cron)\b|"
    r"\b(every\s+monday|every\s+week)\b|"
    r"\b(weekly|daily|monthly)\s+(refresh|schedule|subscription|update|sync)\b|"
    r"\b(refresh|update|sync)\s+(weekly|daily|monthly)\b",
    re.I,
)


def _rail_selected(rail_context: dict[str, Any] | None) -> dict[str, Any]:
    rail = rail_context if isinstance(rail_context, dict) else {}
    for key in ("selected", "object", "candidate", "source", "dataset", "entity"):
        val = rail.get(key)
        if isinstance(val, dict) and val:
            return val
    return rail if any(k in rail for k in ("source_id", "connector_id", "candidate_key", "dataset_id")) else {}


def parse_schedule_request(
    message: str,
    rail_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return cadence + source identity when the user asked to schedule a refresh."""
    text = (message or "").strip()
    if not text or not _SCHEDULE_INTENT.search(text[:240]):
        return None
    if _INTENT_CREATE.search(text[:220]):
        return None
    # Avoid treating pure "status" / probe as schedule.
    if is_direct_status_message(text) or is_direct_probe_message(text, rail_context):
        return None
    lowered = text.lower()
    if re.search(r"\bevery\s+day\b|\bdaily\b", lowered):
        cadence = "daily"
    elif re.search(r"\bmonthly\b|\bevery\s+month\b", lowered):
        cadence = "monthly"
    elif re.search(r"\bmanual\b", lowered):
        cadence = "manual"
    else:
        # Monday 10am / weekly / every week / generic schedule → weekly bucket
        cadence = "weekly"

    selected = _rail_selected(rail_context)
    source_id = str(
        selected.get("source_id")
        or selected.get("id")
        or ""
    ).strip()
    # Prefer explicit twse_official style ids over titles
    if source_id and (" " in source_id or source_id.lower() in {"twse open api", "selected"}):
        source_id = str(selected.get("source_id") or "").strip()
    connector_id = str(selected.get("connector_id") or selected.get("desk_connector_id") or "").strip()
    candidate_key = str(selected.get("candidate_key") or "").strip()
    if not candidate_key and source_id:
        candidate_key = f"source:{source_id}"
    # Parse inline source_id=... from message when rail is thin
    m_src = re.search(r"source_id\s*=\s*([a-z0-9_.:-]+)", text, re.I)
    m_conn = re.search(r"connector_id\s*=\s*([a-z0-9_.:-]+)", text, re.I)
    if m_src:
        source_id = m_src.group(1)
        candidate_key = candidate_key or f"source:{source_id}"
    if m_conn:
        connector_id = m_conn.group(1)
    if not (source_id or connector_id or candidate_key):
        return None
    # Keep faculty wording for History (e.g. every Monday at 10:00)
    requested = text
    for prefix in ("For the selected", "Please ", "Can you ", "Could you "):
        if requested.lower().startswith(prefix.lower()):
            requested = requested[len(prefix):].strip()
            break
    requested = re.sub(r"\s+", " ", requested)[:240]
    return {
        "cadence": cadence,
        "source_id": source_id,
        "connector_id": connector_id,
        "candidate_key": candidate_key,
        "requested_schedule": requested,
        "destination": "ask-schedule",
    }


def is_direct_schedule_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    return parse_schedule_request(message, rail_context) is not None



_TICK_REFRESH = re.compile(
    r"\b(?:tick|run)\s+(?:due\s+)?(?:discover\s+)?(?:refresh\s+)?(?:subscriptions?|schedules?)\b"
    r"|\bforce\s+(?:refresh\s+)?(?:tick|run)\b"
    r"|\brun\s+(?:this\s+)?(?:refresh\s+)?subscription\b",
    re.I,
)


def parse_refresh_tick_request(message: str) -> dict[str, Any] | None:
    text = (message or "").strip()
    if not text or len(text) > 240:
        return None
    if not _TICK_REFRESH.search(text):
        return None
    force = bool(re.search(r"\bforce\b", text, re.I))
    m = re.search(r"subscription\s+([a-f0-9]{8,16})", text, re.I)
    return {
        "force": force or bool(m),
        "force_subscription_id": (m.group(1) if m else ""),
        "limit": 10,
    }


def try_direct_refresh_tick_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    req = parse_refresh_tick_request(message)
    if not req:
        return None
    try:
        out = gateway.discover_refresh_tick(
            limit=int(req.get("limit") or 10),
            force_subscription_id=str(req.get("force_subscription_id") or ""),
            force=bool(req.get("force")),
            auto_approve_safe=True,
        )
    except Exception as exc:  # noqa: BLE001
        return AgentTurn(
            plan={"action": "refresh_tick", "fast_path": True, **req},
            action_result={"action": "refresh_tick", "fast_path": True, "error": str(exc), **req},
            reply=f"Could not tick Discover refresh subscriptions: {exc}",
            suggested_prompts=["Open Discover History", "Schedule a weekly refresh first"],
            tool_name="research_discover_tick_refresh_subscriptions",
        )
    fired = out.get("fired") or []
    errors = out.get("errors") or []
    lines = [
        f"Discover refresh tick — checked **{out.get('checked', 0)}**, fired **{len(fired)}**.",
    ]
    for row in fired[:5]:
        lines.append(
            f"- `{row.get('subscription_id','')[:12]}…` → job `{str(row.get('job_id') or '')[:12]}…` "
            f"({row.get('job_status')}) next `{row.get('next_run_at') or '—'}`"
        )
    if errors:
        lines.append(f"Errors: {len(errors)} (see action result).")
    if not fired and not errors:
        lines.append("Nothing due — use force tick or wait until next_run_at.")
    return AgentTurn(
        plan={"action": "refresh_tick", "fast_path": True, **req},
        action_result={"action": "refresh_tick", "fast_path": True, "tick": out, **req},
        reply="\n".join(lines),
        suggested_prompts=["Open Discover History", "Approve pending refresh jobs"],
        tool_name="research_discover_tick_refresh_subscriptions",
    )


def try_direct_schedule_turn(
    gateway: Any,
    message: str,
    state: dict[str, Any],
) -> AgentTurn | None:
    """Persist a Discover refresh subscription immediately — agent operates the platform."""
    req = parse_schedule_request(message, state.get("rail_context"))
    if not req:
        return None
    try:
        sub = gateway.discover_refresh_create(
            cadence=req["cadence"],
            destination=req.get("destination") or "ask-schedule",
            source_id=req.get("source_id") or "",
            connector_id=req.get("connector_id") or "",
            candidate_key=req.get("candidate_key") or "",
            enabled=True,
            requested_schedule=req.get("requested_schedule") or "",
            timezone="Asia/Taipei",
            schedule_note=(
                "Registered from Ask. Visible in Discover → History → Scheduled. "
                "When cron is present, the Discover refresh runner arms next_run_at."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return AgentTurn(
            plan={"action": "schedule_refresh", "fast_path": True, **req},
            action_result={"action": "schedule_refresh", "fast_path": True, "error": str(exc), **req},
            reply=f"Could not register the refresh subscription: {exc}",
            suggested_prompts=["Open Discover History", "Probe this source first"],
            tool_name="research_discover_create_refresh_subscription",
        )

    sub_id = str(sub.get("id") or "")
    cadence = str(sub.get("cadence") or req["cadence"])
    requested = str(sub.get("requested_schedule") or req.get("requested_schedule") or cadence)
    target = sub.get("source_id") or sub.get("connector_id") or sub.get("candidate_key") or "source"
    spec = sub.get("schedule_spec") if isinstance(sub.get("schedule_spec"), dict) else {}
    cron = str(spec.get("cron") or "")
    tz = str(spec.get("timezone") or "Asia/Taipei")
    next_run = sub.get("next_run_at") or ""
    mode = sub.get("execution_mode") or "non_executing"
    reply = (
        f"Registered refresh for **{target}** in Discover History.\n"
        f"- Requested: {requested}\n"
        f"- Platform cadence bucket: `{cadence}`\n"
        f"- Schedule spec: `{cron or 'manual'}` ({tz})\n"
        f"- Execution: `{mode}`"
        + (f" · next run `{next_run}`" if next_run else " · no automatic next run")
        + f"\n- Subscription `{sub_id[:12]}…` · status **{sub.get('status') or 'active'}**\n\n"
        "Open **Discover → History → Scheduled** to see it. "
        + (
            "The refresh runner will submit a Discover collect job when due (or on force tick)."
            if next_run
            else "Manual cadence — run collect from Ask when you need a refresh."
        )
    )
    try:
        from scripts.research_data_mcp.desk_activity import record_activity

        record_activity(
            "refresh_subscription",
            str(target)[:200],
            repo_root=getattr(gateway, "repo_root", None),
            meta={"subscription_id": sub_id, "cadence": cadence, "requested_schedule": requested},
        )
    except Exception:
        pass
    return AgentTurn(
        plan={"action": "schedule_refresh", "fast_path": True, **req},
        action_result={
            "action": "schedule_refresh",
            "fast_path": True,
            "subscription": sub,
            "subscription_id": sub_id,
            "cadence": cadence,
            "requested_schedule": requested,
            "history_kind": "subscription",
            "platform_registered": True,
        },
        reply=reply,
        suggested_prompts=[
            "Open Discover History Scheduled",
            "Pause this refresh subscription",
            "Probe this source",
        ],
        tool_name="research_discover_create_refresh_subscription",
    )



_INTENT_CREATE = re.compile(
    r"\b(create|record|open|start)\b.{0,40}\b(discover\s+)?intent\b|\bresearch\s+intent\b",
    re.I | re.S,
)
_INTENT_NEED = re.compile(
    r"(?:intent(?:\s+for)?|need(?:ing)?|research(?:ing)?)\s*[:\-]?\s*(.+)$",
    re.I | re.S,
)


def parse_intent_request(message: str, rail_context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    text = (message or "").strip()
    if not text or not _INTENT_CREATE.search(text[:220]):
        return None
    if is_direct_schedule_message(text, rail_context) or is_direct_probe_message(text, rail_context):
        return None
    # Multi-step / Composer instruction turns belong to Composer (or discover search), not intent steal.
    lowered = text.lower()
    if any(
        token in lowered
        for token in (
            "research_discover_search",
            "research_discover_source_search",
            "call only",
            "use only the mcp",
            "pick the best",
            "search discover",
        )
    ):
        return None
    if "search" in lowered[:240] and "intent" in lowered and len(text) > 160:
        return None
    need = ""
    # Prefer explicit "for: …" / "for …" research need.
    m = re.search(r"\bintent\b(?:\s+for)?\s*[:\-]?\s*(.+)$", text, re.I | re.S)
    if m:
        need = m.group(1).strip().strip('"').strip("'")
        need = re.sub(r"^(a\s+|an\s+|the\s+)?", "", need, flags=re.I)
    if not need or len(need) < 8:
        need = re.sub(
            r"^(please\s+)?(create|record|open|start)\s+(a\s+)?(discover\s+)?(research\s+)?intent\s*(for)?\s*[:\-]?",
            "",
            text,
            flags=re.I,
        ).strip()
    need = re.sub(r"\s+", " ", need).strip(" :-")
    need = re.split(
        r"\b(?:Do not collect|Return the|Use research_|Confirm via|Call only)\b",
        need,
        maxsplit=1,
        flags=re.I,
    )[0].strip(" :-")
    if len(need) < 8:
        return None
    selected = _rail_selected(rail_context)
    candidate = {}
    for key in ("source_id", "connector_id", "candidate_key", "title", "endpoint", "url"):
        if selected.get(key):
            candidate[key] = selected.get(key)
    title = str(selected.get("title") or need[:80])
    return {"research_need": need[:500], "title": title[:160], "candidate": candidate or None}


def is_direct_intent_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    return parse_intent_request(message, rail_context) is not None


def try_direct_intent_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    req = parse_intent_request(message, state.get("rail_context"))
    if not req:
        return None
    try:
        intent = gateway.discover_intent_create(
            research_need=req["research_need"],
            title=req.get("title") or "",
            candidate=req.get("candidate"),
            session_id=str(state.get("session_id") or ""),
            user_email=str(state.get("user_email") or ""),
        )
    except Exception as exc:  # noqa: BLE001
        return AgentTurn(
            plan={"action": "create_intent", "fast_path": True},
            action_result={"action": "create_intent", "fast_path": True, "error": str(exc)},
            reply=f"Could not record Discover intent: {exc}",
            suggested_prompts=["Search vault for related datasets"],
            tool_name="research_discover_create_intent",
        )
    iid = str(intent.get("id") or "")
    reply = (
        f"Recorded Discover intent `{iid[:12]}…`\\n"
        f"- Need: {req['research_need'][:200]}\\n"
        f"- Status: draft (no collection started)\\n\\n"
        "It appears under Discover → History. Propose routes or collect only after review."
    )
    try:
        from scripts.research_data_mcp.desk_activity import record_activity
        record_activity("intent", req["research_need"][:200], repo_root=getattr(gateway, "repo_root", None), meta={"intent_id": iid})
    except Exception:
        pass
    return AgentTurn(
        plan={"action": "create_intent", "fast_path": True},
        action_result={
            "action": "create_intent",
            "fast_path": True,
            "intent": intent,
            "intent_id": iid,
            "platform_registered": True,
            "history_kind": "intent",
        },
        reply=reply,
        suggested_prompts=["Open Discover History", "Propose collection routes for this intent"],
        tool_name="research_discover_create_intent",
    )


_SUB_LIFECYCLE = re.compile(r"\b(pause|resume|stop)\b.{0,40}\b(subscription|refresh|schedule)\b|\b(subscription|refresh)\b.{0,40}\b(pause|resume|stop)\b", re.I)
_SUB_ID = re.compile(r"\b([a-f0-9]{12,16})\b", re.I)


def parse_subscription_lifecycle(message: str, rail_context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    text = (message or "").strip()
    if not text or not _SUB_LIFECYCLE.search(text[:240]):
        return None
    lowered = text.lower()
    if re.search(r"\bpause\b", lowered):
        op = "pause"
    elif re.search(r"\bresume\b", lowered):
        op = "resume"
    elif re.search(r"\bstop\b", lowered):
        op = "stop"
    else:
        return None
    sid = ""
    m = _SUB_ID.search(text)
    if m:
        sid = m.group(1)
    selected = _rail_selected(rail_context)
    if not sid:
        sid = str(selected.get("subscription_id") or selected.get("id") or "").strip()
    if not sid:
        return None
    return {"op": op, "subscription_id": sid}


def is_direct_subscription_lifecycle_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    return parse_subscription_lifecycle(message, rail_context) is not None


def try_direct_subscription_lifecycle_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    req = parse_subscription_lifecycle(message, state.get("rail_context"))
    if not req:
        return None
    op = req["op"]
    sid = req["subscription_id"]
    try:
        if op == "pause":
            sub = gateway.discover_refresh_pause(sid)
            action = "pause_subscription"
        elif op == "resume":
            sub = gateway.discover_refresh_resume(sid)
            action = "resume_subscription"
        else:
            sub = gateway.discover_refresh_stop(sid)
            action = "stop_subscription"
    except Exception as exc:  # noqa: BLE001
        return AgentTurn(
            plan={"action": "subscription_lifecycle", "fast_path": True, **req},
            action_result={"action": "subscription_lifecycle", "fast_path": True, "error": str(exc), **req},
            reply=f"Could not {op} subscription `{sid[:12]}…`: {exc}",
            suggested_prompts=["Open Discover History Scheduled"],
            tool_name=f"research_discover_{op}_refresh_subscription",
        )
    reply = (
        f"{op.capitalize()}d refresh subscription `{sid[:12]}…`\\n"
        f"- Status: **{sub.get('status')}**\\n"
        f"- Source: {sub.get('source_id') or sub.get('connector_id') or 'n/a'}\\n"
        "Discover → History → Scheduled reflects this change."
    )
    return AgentTurn(
        plan={"action": action, "fast_path": True, **req},
        action_result={
            "action": action,
            "fast_path": True,
            "subscription": sub,
            "subscription_id": sid,
            "platform_registered": True,
        },
        reply=reply,
        suggested_prompts=["Open Discover History Scheduled", "status"],
        tool_name=f"research_discover_{op}_refresh_subscription",
    )



_COLLECT_SELECTED = re.compile(
    r"\b(collect|queue\s+collect(?:ion)?|start\s+collect(?:ion)?)\b",
    re.I,
)
_COLLECT_SELECTED_BLOCK = re.compile(
    r"\b(plan|compare|explain|why|should|summarize|doi)\b",
    re.I,
)


def parse_discover_collect_request(message: str, rail_context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    text = (message or "").strip()
    if not text or not _COLLECT_SELECTED.search(text[:200]):
        return None
    # Negation: "do not collect" is intent/language, not a collect command.
    if re.search(r"\b(do\s+not|don'?t|without|no)\s+collect\b", text, re.I):
        return None
    if _COLLECT_SELECTED_BLOCK.search(text[:160]):
        return None
    # Multi-step Composer instructions — leave alone
    if any(tok in text.lower() for tok in ("research_discover_search", "pick the best", "then create")):
        return None
    selected = _rail_selected(rail_context)
    if not (selected.get("connector_id") or selected.get("source_id") or selected.get("candidate_key")):
        return None
    # Prefer short imperative collects
    if len(text) > 220 and "intent" in text.lower():
        return None
    return {
        "connector_id": str(selected.get("connector_id") or "").strip(),
        "source_id": str(selected.get("source_id") or "").strip(),
        "candidate_key": str(selected.get("candidate_key") or "").strip(),
        "title": str(selected.get("title") or selected.get("source_id") or "Discover source").strip(),
        "url": str(selected.get("url") or selected.get("endpoint") or "").strip(),
    }


def try_direct_discover_collect_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    req = parse_discover_collect_request(message, state.get("rail_context"))
    if not req:
        return None
    from scripts.research_data_mcp.discover_collect_plan import resolve_discover_collect_plan
    from scripts.research_data_mcp.job_identity import enrich_job_identity

    try:
        plan = resolve_discover_collect_plan(
            gateway.procurement,
            gateway.repo_root,
            connector_id=req["connector_id"],
            source_id=req["source_id"],
            limit=25,
            title=req["title"],
            url=req["url"],
            candidate_key=req["candidate_key"],
        )
    except Exception as exc:  # noqa: BLE001
        return AgentTurn(
            plan={"action": "discover_collect", "fast_path": True, **req},
            action_result={"action": "discover_collect", "fast_path": True, "error": str(exc), **req},
            reply=f"Could not build a Discover collect plan: {exc}",
            suggested_prompts=["Probe the selected source", "Create a Discover intent instead"],
            tool_name="research_discover_collect",
        )
    request = {
        "source": "discover_ui",
        "connector_id": plan.get("connector_id") or req["connector_id"],
        "candidate_key": req["candidate_key"],
    }
    if req["source_id"]:
        request["source_id"] = req["source_id"]
        plan = dict(plan)
        plan["source_id"] = req["source_id"]
    submitted = gateway.jobs.submit(plan.get("title") or req["title"], plan, request, auto_approve=False)
    job = submitted.get("job") if isinstance(submitted, dict) else None
    if isinstance(job, dict):
        job = enrich_job_identity(job)
    jid = str((job or {}).get("id") or "")
    resolution = plan.get("collect_resolution") or plan.get("job_type")
    reply = (
        f"Queued Discover collect for **{req['title']}** as job `{jid[:12]}…`\n"
        f"- Status: {(job or {}).get('status') or 'unknown'}\n"
        f"- Plan: `{resolution}`\n"
        f"- Appears under Discover → History (collection run). Approve to execute."
    )
    return AgentTurn(
        plan={"action": "discover_collect", "fast_path": True, **req},
        action_result={
            "action": "discover_collect",
            "fast_path": True,
            "job": job,
            "job_id": jid,
            "plan": plan,
            "platform_registered": bool(jid),
            "history_kind": "collection_run",
            "result_kind": "discover_collect",
            **req,
        },
        reply=reply,
        suggested_prompts=[f"Approve job {jid}" if jid else "Open Discover History", "Pause if this was a mistake"],
        tool_name="procurement_submit_collection_job",
    )



_APPROVE_JOB = re.compile(r"\bapprove\s+(?:job\s+)?([a-f0-9]{8,16})\b", re.I)


def try_direct_approve_job_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    text = (message or "").strip()
    m = _APPROVE_JOB.search(text[:200] if text else "")
    if not m:
        return None
    jid = m.group(1)
    try:
        job = gateway.jobs.approve(jid)
        # kick worker once like HTTP handler
        try:
            gateway.jobs.tick()
        except Exception:
            pass
        job = gateway.jobs.get(jid) or job
    except Exception as exc:  # noqa: BLE001
        return AgentTurn(
            plan={"action": "approve_job", "fast_path": True, "job_id": jid},
            action_result={"action": "approve_job", "fast_path": True, "job_id": jid, "error": str(exc)},
            reply=f"Could not approve job `{jid}`: {exc}",
            suggested_prompts=["Open Discover History"],
            tool_name="procurement_approve_job",
        )
    status = (job or {}).get("status")
    return AgentTurn(
        plan={"action": "approve_job", "fast_path": True, "job_id": jid},
        action_result={
            "action": "approve_job",
            "fast_path": True,
            "job_id": jid,
            "job": job,
            "platform_registered": True,
            "history_kind": "collection_run",
        },
        reply=f"Approved job `{jid}` — status now **{status}**. Discover History should reflect the collection run.",
        suggested_prompts=["Open Discover History", f"status"],
        tool_name="procurement_approve_job",
    )



_SCRAPE_INTENT = re.compile(
    r"\b(scrape|browser[- ]?scrape|playwright|spectator\s+scrape)\b",
    re.I,
)


def parse_scrape_request(message: str, rail_context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    text = (message or "").strip()
    if not text:
        return None
    urls = extract_urls(text)
    selected = _rail_selected(rail_context)
    actions = [str(a).lower() for a in ((rail_context or {}).get("actions") or [])] if isinstance(rail_context, dict) else []
    wants = bool(_SCRAPE_INTENT.search(text[:200])) or "scrape" in actions
    if not wants:
        return None
    url = urls[0] if urls else ""
    if not url:
        endpoint = str(selected.get("url") or selected.get("endpoint") or "").strip()
        if endpoint:
            url = endpoint if endpoint.startswith("http") else f"https://{endpoint}"
    script_key = "generic_url_scrape"
    m = re.search(r"\b(cake_board|yourator_board|tw_boards_refresh|generic_url_scrape)\b", text, re.I)
    if m:
        script_key = m.group(1).lower()
    # Named board scrapers are allowlisted without a URL; generic scrape still needs one.
    if script_key == "generic_url_scrape" and not url.startswith("http"):
        return None
    if script_key != "generic_url_scrape" and not url.startswith("http"):
        url = ""
    mode = "page"
    if re.search(r"\bcatalog\b", text, re.I):
        mode = "catalog"
    return {
        "url": url,
        "script_key": script_key,
        "mode": mode,
        "title": str(selected.get("title") or script_key or url)[:160],
        "source_id": str(selected.get("source_id") or ""),
        "connector_id": str(selected.get("connector_id") or ""),
        "candidate_key": str(selected.get("candidate_key") or ""),
    }


def try_direct_scrape_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    """Queue Spectator/windows_lab scrape — niche/browser harvest path."""
    req = parse_scrape_request(message, state.get("rail_context"))
    if not req:
        return None
    from scripts.research_data_mcp.job_identity import enrich_job_identity
    from scripts.research_data_mcp.spectator_tools import build_spectator_plan

    try:
        plan = build_spectator_plan(
            url=req["url"],
            script_key=req["script_key"],
            mode=req.get("mode") or "",
            title=req.get("title") or "",
            agent_initiated=True,
        )
    except Exception as exc:  # noqa: BLE001
        return AgentTurn(
            plan={"action": "spectator_scrape", "fast_path": True, **req},
            action_result={"action": "spectator_scrape", "fast_path": True, "error": str(exc), **req},
            reply=f"Could not build Spectator scrape plan: {exc}",
            suggested_prompts=["Probe the URL first", "Collect via HTTP if it is a direct file"],
            tool_name="procurement_submit_collection_job",
        )
    if req.get("source_id"):
        plan["source_id"] = req["source_id"]
    if req.get("connector_id"):
        plan["connector_id"] = req["connector_id"]
    if req.get("candidate_key"):
        plan["candidate_key"] = req["candidate_key"]
    plan["collect_resolution"] = plan.get("collect_resolution") or "spectator_scrape"
    request = {
        "source": "discover_ui",
        "url": req["url"],
        "script_key": req["script_key"],
    }
    for k in ("source_id", "connector_id", "candidate_key"):
        if req.get(k):
            request[k] = req[k]
    submitted = gateway.jobs.submit(plan.get("title") or req["title"], plan, request, auto_approve=False)
    job = submitted.get("job") if isinstance(submitted, dict) else None
    if isinstance(job, dict):
        job = enrich_job_identity(job)
    jid = str((job or {}).get("id") or "")
    reply = (
        f"Queued Spectator scrape on **windows_lab** for `{req['url']}`\n"
        f"- Job `{jid[:12]}…` · status={(job or {}).get('status')}\n"
        f"- Script `{req['script_key']}` · mode={plan.get('scrape_mode') or req.get('mode') or 'page'}\n"
        f"- Lands in Discover History; approve to run the remote Playwright worker."
    )
    return AgentTurn(
        plan={"action": "spectator_scrape", "fast_path": True, **req},
        action_result={
            "action": "spectator_scrape",
            "fast_path": True,
            "job": job,
            "job_id": jid,
            "plan": plan,
            "platform_registered": bool(jid),
            "history_kind": "collection_run",
            "pool_hint": "windows_lab",
            **req,
        },
        reply=reply,
        suggested_prompts=[f"Approve job {jid}" if jid else "Open Discover History"],
        tool_name="procurement_submit_collection_job",
    )


def try_direct_equipment_turn(
    gateway: Any,
    message: str,
    state: dict[str, Any],
) -> AgentTurn | None:
    status = try_direct_status_turn(gateway, message, state)
    if status is not None:
        return status
    approve = try_direct_approve_job_turn(gateway, message, state)
    if approve is not None:
        return approve
    scrape = try_direct_scrape_turn(gateway, message, state)
    if scrape is not None:
        return scrape
    discover = try_direct_discover_search_turn(gateway, message, state)
    if discover is not None:
        return discover
    collect = try_direct_discover_collect_turn(gateway, message, state)
    if collect is not None:
        return collect
    intent = try_direct_intent_turn(gateway, message, state)
    if intent is not None:
        return intent
    schedule = try_direct_schedule_turn(gateway, message, state)
    if schedule is not None:
        return schedule
    lifecycle = try_direct_subscription_lifecycle_turn(gateway, message, state)
    if lifecycle is not None:
        return lifecycle
    tick = try_direct_refresh_tick_turn(gateway, message, state)
    if tick is not None:
        return tick
    probe = try_direct_probe_turn(gateway, message, state)
    if probe is not None:
        return probe
    describe = try_direct_describe_turn(gateway, message, state)
    if describe is not None:
        return describe
    query = try_direct_query_turn(gateway, message, state)
    if query is not None:
        return query
    collect = try_submit_collect_turn(gateway, message, state)
    if collect is not None:
        return collect
    return try_direct_search_turn(gateway, message, state)


def _describe_reply(dataset_id: str, out: dict[str, Any]) -> str:
    title = str(out.get("title") or out.get("name") or dataset_id)
    readiness = str(out.get("readiness") or out.get("access_mode") or "unknown")
    lines = [f"**{title}** (`{dataset_id}`) — readiness: {readiness}"]
    summary = str(out.get("summary") or out.get("description") or "").strip()
    if summary:
        lines.append(summary[:500])
    local = out.get("local_path") or out.get("path")
    if local:
        lines.append(f"Local path: `{local}`")
    return "\n".join(lines)


def try_direct_describe_turn(
    gateway: Any,
    message: str,
    state: dict[str, Any],
) -> AgentTurn | None:
    dataset_id = dataset_id_from_message(message, state.get("rail_context"), mode="describe")
    if not dataset_id:
        return None
    try:
        out = gateway.describe_dataset(dataset_id)
    except Exception as exc:  # noqa: BLE001
        return AgentTurn(
            plan={"action": "describe_dataset", "fast_path": True, "dataset_id": dataset_id},
            action_result={"action": "describe_dataset", "fast_path": True, "error": str(exc), "dataset_id": dataset_id},
            reply=f"Could not describe `{dataset_id}`: {exc}",
            suggested_prompts=[f"Search vault for {dataset_id}"],
            tool_name="research_describe_dataset",
        )
    return AgentTurn(
        plan={"action": "describe_dataset", "fast_path": True, "dataset_id": dataset_id},
        action_result={"action": "describe_dataset", "fast_path": True, "dataset": out, "dataset_id": dataset_id},
        reply=_describe_reply(dataset_id, out),
        suggested_prompts=[f"Query sample rows from {dataset_id}", f"Queue DOI collect for {dataset_id}"],
        tool_name="research_describe_dataset",
    )


def _query_reply(dataset_id: str, out: dict[str, Any]) -> str:
    rows = list(out.get("rows") or out.get("data") or [])
    columns = out.get("columns") or []
    lines = [f"Query on **{dataset_id}** — {len(rows)} row(s) returned."]
    if columns:
        lines.append(f"Columns: {', '.join(str(c) for c in columns[:12])}")
    for row in rows[:5]:
        if isinstance(row, dict):
            preview = ", ".join(f"{k}={v!r}" for k, v in list(row.items())[:4])
            lines.append(f"- {preview}")
        else:
            lines.append(f"- {row!r}")
    if len(rows) > 5:
        lines.append(f"- …and {len(rows) - 5} more")
    return "\n".join(lines)


def try_direct_query_turn(
    gateway: Any,
    message: str,
    state: dict[str, Any],
) -> AgentTurn | None:
    dataset_id = dataset_id_from_message(message, state.get("rail_context"), mode="query")
    if not dataset_id:
        return None
    limit = query_limit_from_message(message)
    try:
        out = gateway.query_dataset(dataset_id, {"limit": limit})
    except Exception as exc:  # noqa: BLE001
        return AgentTurn(
            plan={"action": "query_dataset", "fast_path": True, "dataset_id": dataset_id},
            action_result={"action": "query_dataset", "fast_path": True, "error": str(exc), "dataset_id": dataset_id},
            reply=f"Query failed for `{dataset_id}`: {exc}",
            suggested_prompts=[f"Describe {dataset_id}"],
            tool_name="research_query_dataset",
        )
    return AgentTurn(
        plan={"action": "query_dataset", "fast_path": True, "dataset_id": dataset_id, "limit": limit},
        action_result={"action": "query_dataset", "fast_path": True, "query": out, "dataset_id": dataset_id},
        reply=_query_reply(dataset_id, out),
        suggested_prompts=[f"Describe {dataset_id}", "Search vault for related datasets"],
        tool_name="research_query_dataset",
    )


def try_submit_collect_turn(
    gateway: Any,
    message: str,
    state: dict[str, Any],
) -> AgentTurn | None:
    """Queue a DOI collect on the cluster — discovery is done; download is background."""
    doi = doi_from_message(message, state.get("rail_context"))
    if not doi:
        return None
    try:
        out = gateway.collect_datacite_doi(doi, auto_execute=True)
    except Exception as exc:  # noqa: BLE001
        return AgentTurn(
            plan={"action": "submit_collect", "procurement_submit": True, "doi": doi},
            action_result={
                "action": "submit_collect",
                "procurement_submit": True,
                "error": str(exc),
                "doi": doi,
            },
            reply=f"Could not queue collect for `{doi}`: {exc}",
            suggested_prompts=[f"Probe landing page for {doi}"],
            tool_name="datacite_collect_doi",
        )
    if out.get("blocked"):
        gate = out.get("gate") if isinstance(out.get("gate"), dict) else {}
        reason = str(out.get("message") or gate.get("blocked_reason") or "approval required")
        return AgentTurn(
            plan={"action": "submit_collect", "procurement_submit": True, "doi": doi, "blocked": True},
            action_result={
                "action": "submit_collect",
                "procurement_submit": True,
                "collect": out,
                "doi": doi,
            },
            reply=f"Collect for `{doi}` needs approval before the cluster can run: {reason}",
            suggested_prompts=["Approve license and retry collect"],
            tool_name="datacite_collect_doi",
        )
    job = out.get("job") if isinstance(out.get("job"), dict) else {}
    job_id = str(job.get("id") or job.get("job_id") or out.get("job_id") or "").strip()
    job_status = str(job.get("status") or ("pending_approval" if out.get("blocked") else "queued"))
    campaign = str(out.get("campaign_id") or job.get("campaign_id") or "").strip()
    title = str((out.get("resolved") or {}).get("title") or doi)
    reply = (
        f"Queued **{title}** (`{doi}`) for cluster collection. "
        "The download runs in the background — check job status or keep browsing Discover."
    )
    if job_id:
        reply += f" Job `{job_id[:12]}…`."
    elif campaign:
        reply += f" Campaign `{campaign[:16]}…`."
    if job_id:
        state["pending_job_id"] = job_id
        state["job_status"] = job_status
    return AgentTurn(
        plan={"action": "submit_collect", "procurement_submit": True, "doi": doi},
        action_result={
            "action": "submit_collect",
            "procurement_submit": True,
            "collect": out,
            "doi": doi,
            "job_id": job_id,
            "job": job if job else None,
            "background": True,
        },
        reply=reply,
        suggested_prompts=["Check job status", f"Search vault for related {doi}"],
        tool_name="datacite_collect_doi",
    )


try_direct_collect_turn = try_submit_collect_turn


def _probe_reply(url: str, out: dict[str, Any]) -> str:
    summary = str(out.get("summary") or "").strip()
    connector = out.get("connector") if isinstance(out.get("connector"), dict) else {}
    spec = connector.get("spec") if isinstance(connector.get("spec"), dict) else {}
    access = spec.get("access_mode") or "unknown"
    content = spec.get("content_type") or "unknown"
    files = spec.get("discovered_file_count")
    if summary:
        return summary
    parts = [f"`{url}` is reachable as **{access}** (`{content}`)"]
    if files is not None:
        parts.append(f"{files} downloadable file(s) detected")
    parts.append("Use **Add to lab** in Discover to queue cluster collection once fit is confirmed.")
    return " ".join(parts) + "."


def try_direct_probe_turn(
    gateway: Any,
    message: str,
    state: dict[str, Any],
) -> AgentTurn | None:
    """Run procurement probe equipment directly (~0.5s), skip Composer (~45–90s)."""
    url = probe_url_from_message(message, state.get("rail_context"))
    if not url:
        return None
    raw = gateway.probe_source(url, name=url[:120])
    if raw.get("error"):
        return AgentTurn(
            plan={"action": "probe_url", "fast_path": True},
            action_result={"action": "probe_url", "fast_path": True, "error": raw.get("error"), "url": url},
            reply=f"Probe failed for `{url}`: {raw.get('error')}",
            suggested_prompts=[],
            tool_name="procurement_probe_public_source",
        )
    compact = _compact_probe_response(raw)
    reply = _probe_reply(url, compact)
    return AgentTurn(
        plan={"action": "probe_url", "fast_path": True},
        action_result={
            "action": "probe_url",
            "fast_path": True,
            "probe": compact,
            "connector": compact.get("connector"),
            "url": url,
        },
        reply=reply,
        suggested_prompts=[
            "Add this source to the lab vault",
            "What registry datasets overlap this source?",
        ],
        tool_name="procurement_probe_public_source",
    )
