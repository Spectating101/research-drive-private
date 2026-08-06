#!/usr/bin/env python3
"""Discover Explore — desk-grounded Composer + MCP.

Hands measure held/routes on this machine first. Composer gets those facts plus
MCP tools so it can beat naked Composer: real vault holdings, collectable
routes, credentials-aware next steps, verified open URLs — without replacing
judgment with catalog junk (the prior Zenodo failure mode).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from typing import Any

from scripts.research_data_mcp.evidence_placement import (
    PLACEMENT_CONTEXT,
    PLACEMENT_HELD,
    PLACEMENT_ROUTE,
    stamp_evidence_fields,
)

_LOG = logging.getLogger(__name__)

# Lexical availability scores often land 20–30 on real topic hits after meaning match.
# Old floor of 2.0 treated almost any token overlap as "strong" and skipped Composer.
_STRONG_SCORE = 8.0
_READY_MIN_SCORE = 2.0

_QUESTION_WORDS = frozenset({
    "what", "which", "where", "when", "who", "how", "can", "could", "should",
    "do", "does", "is", "are", "need", "want", "find", "looking", "study",
    "analyse", "analyze", "research", "measure", "test", "compare", "for",
})

_NOISE_TITLE = (
    "coingecko", "ethereum usdt", "spk v1", "gdelt asia", "bitcoin",
)

_COMPOSER_ONLY_PROMPT = """Best public data sources for: {query}

Return ONLY JSON (no markdown fences):
{{
  "context": [{{"title":"...","url":"...","why":"..."}}],
  "next_action": "probe_url|ask_clarify|paste_url",
  "summary": "one sentence"
}}

Rules:
- Max 6 context rows. Prefer canonical orgs (Gallup, Pew, TWSE, ANES, …).
- Real URLs when possible. No vault/dataset_id claims.
- No unrelated catalogs (no crypto dumps for polling, etc.).
"""

_COMPOSER_MCP_PROMPT = """You are Research Drive Discover on a lab desk with MCP tools and local credentials.

Query: {query}

DESK_FACTS (already measured via research_discover_desk — authoritative for held/route):
{desk_facts}

{capabilities}

Stack contract:
- L0 hands already ran. Do not invent dataset_ids or source_ids outside DESK_FACTS.
- Copy DESK_FACTS held/routes into your JSON when present.
- Prefer research_discover_desk if you need to re-check; prefer research_web_discover to confirm live URLs.
- research_platform_consolidated only if credentials/access change the next step.

Hard bans:
- Do NOT call research_search_catalog (dumps unrelated vault rows / Zenodo noise).
- Do NOT keep tool hits weaker than a known canonical source for this query.
- Do NOT claim vault holdings absent from DESK_FACTS.
- If DESK_FACTS held exists but does not answer the research question / method ask,
  say so plainly; next_action may be ask_clarify, probe_url, or paste_url — do not
  pretend use_held is sufficient.

For context (max 6): canonical matching sources with real URLs (Gallup/Pew/ANES/Roper/538/TWSE/TPEx…).
Pretrained knowledge is allowed. Summary MUST state desk truth (held / collectable route / neither).

Return ONLY JSON:
{{
  "held": [{{"title":"...","dataset_id":"...","why":"..."}}],
  "route": [{{"title":"...","source_id":"...","why":"..."}}],
  "context": [{{"title":"...","url":"...","why":"..."}}],
  "next_action": "use_held|collect_route|probe_url|ask_clarify|paste_url|none",
  "summary": "one sentence with desk truth"
}}
"""

# Shortlist cache — Composer enrich is the expensive layer.
_ENRICH_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_ENRICH_TTL_S = float(os.getenv("RD_DISCOVER_ENRICH_TTL_S", "900") or 900)


def is_question_like(query: str) -> bool:
    text = str(query or "").strip().lower()
    if not text:
        return False
    words = re.findall(r"[a-z0-9-]+", text)
    if len(words) >= 5:
        return True
    return len(words) >= 3 and any(w in _QUESTION_WORDS for w in words)


def is_keyword_fast_path(query: str) -> bool:
    text = str(query or "").strip()
    if not text or is_question_like(text):
        return False
    words = re.findall(r"[a-z0-9-]+", text.lower())
    return 1 <= len(words) <= 4


def strong_held_hits(candidates: list[dict[str, Any]]) -> bool:
    """True when the desk already has a confident local answer — not mere token overlap.

    Used to skip L1 Composer on short keyword searches. Question-like queries still
    enrich even when this is true (see ``should_skip_l1_enrich``).
    """
    if not candidates:
        return False
    top = candidates[0]
    if float(top.get("score") or 0) >= _STRONG_SCORE:
        return True
    return any(
        bool(c.get("local_ready")) and float(c.get("score") or 0) >= _READY_MIN_SCORE
        for c in candidates[:5]
    )


def should_skip_l1_enrich(
    query: str,
    *,
    strong_held: bool,
    held: list[dict[str, Any]],
    routes: list[dict[str, Any]],
) -> tuple[bool, str]:
    """Discover research AI always runs L1 when enrich is open.

    ``strong_held`` remains an L0 *signal* (Ask / UI), not a gate that skips Composer.
    Use ``mode=lexical`` for catalog-only speed. Unused args kept for call-site compat.
    """
    _ = (query, strong_held, held, routes)
    return False, ""


def _stamp_row(row: dict[str, Any], *, placement: str) -> dict[str, Any]:
    out = dict(row)
    out["placement"] = placement
    if placement == PLACEMENT_HELD and not out.get("kind"):
        out["kind"] = "dataset"
    if placement == PLACEMENT_ROUTE and not out.get("kind"):
        out["kind"] = "declared_route"
    if placement == PLACEMENT_CONTEXT and not out.get("kind"):
        out["kind"] = "web_hit" if out.get("url") else "catalog_hit"
    why = str(out.get("why") or out.get("selection_reason") or "").strip()
    if why:
        out["why"] = why
        out["selection_reason"] = out.get("selection_reason") or why
    out["selected_by"] = out.get("selected_by") or (
        "gap_routes" if placement == PLACEMENT_ROUTE else "composer_only"
    )
    return stamp_evidence_fields(out)


def parse_composer_discover_json(reply: str) -> dict[str, Any] | None:
    text = str(reply or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        payload = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def package_from_composer(
    query: str,
    parsed: dict[str, Any],
    *,
    limit: int = 12,
) -> dict[str, Any]:
    """Legacy packager for tests — context-focused Composer-only replies."""
    held = [
        _stamp_row(r, placement=PLACEMENT_HELD)
        for r in (parsed.get("held") or [])
        if isinstance(r, dict) and (r.get("title") or r.get("dataset_id"))
    ][:limit]
    routes = [
        _stamp_row(
            {
                **(r if isinstance(r, dict) else {"title": str(r)}),
                "title": (r.get("title") or r.get("label") if isinstance(r, dict) else str(r)),
            },
            placement=PLACEMENT_ROUTE,
        )
        for r in (parsed.get("route") or parsed.get("routes") or [])
        if (isinstance(r, dict) and (r.get("title") or r.get("source_id") or r.get("label")))
        or (isinstance(r, str) and r.strip())
    ][: min(3, limit)]
    context = []
    for r in parsed.get("context") or []:
        if isinstance(r, str) and r.strip():
            r = {"title": r.strip()}
        if not isinstance(r, dict):
            continue
        if not (r.get("title") or r.get("url") or r.get("doi")):
            continue
        context.append(_stamp_row(r, placement=PLACEMENT_CONTEXT))
    context = context[:limit]

    next_action = str(parsed.get("next_action") or "").strip()
    if not next_action:
        if held:
            next_action = "use_held"
        elif routes:
            next_action = "collect_route"
        elif any(c.get("url") or c.get("doi") for c in context):
            next_action = "probe_url"
        elif context:
            next_action = "search_wider"
        else:
            next_action = "paste_url"

    summary = str(parsed.get("summary") or "").strip() or None
    sections: list[dict[str, Any]] = []
    if held:
        sections.append({"id": "held", "label": "In Library", "rows": held})
    if routes:
        sections.append({"id": "route", "label": "Declared routes", "rows": routes})
    if context:
        sections.append({"id": "context", "label": "Open sources", "rows": context})

    total = len(held) + len(routes) + len(context)
    return {
        "query": query,
        "mode": "composer",
        "engine": "composer_only",
        "sections": sections,
        "rows": held + routes + context,
        "total": total,
        "held_count": len(held),
        "route_count": len(routes),
        "context_count": len(context),
        "index_miss": len(held) == 0,
        "weak_match": False,
        "judgment": None,
        "next_action": next_action,
        "summary": summary,
        "tools_used": ["composer_only"],
    }


def _composer_only_context(query: str, *, limit: int = 6) -> tuple[list[dict[str, Any]], str, str]:
    """Composer with no MCP — open-web shortlist only. Returns context, summary, next."""
    from scripts.research_data_mcp.desk_brain import (
        _desk_agent_runtime_kwargs,
        _desk_composer_models,
        _interaction_payload,
        _load_cursor_sdk_bindings,
        _reply_from_run,
        _wait_run_bounded,
        cursor_composer_available,
    )

    if not cursor_composer_available():
        return [], "Composer is not configured on this desk.", "paste_url"

    api_key = os.getenv("CURSOR_API_KEY", "").strip()
    if not api_key:
        return [], "Composer is not configured on this desk.", "paste_url"

    from pathlib import Path

    # repo root via gateway caller — resolve from env or sharpe helper
    try:
        from sharpe_kernel.paths import repo_root_from_file

        repo_root = repo_root_from_file(__file__)
    except Exception:  # noqa: BLE001
        repo_root = Path(os.environ.get("SHARPE_REPO_ROOT") or ".").resolve()

    sdk = _load_cursor_sdk_bindings()
    model_id = _desk_composer_models()[0]
    prompt = _COMPOSER_ONLY_PROMPT.format(query=query)
    streamed: list[str] = []

    def on_delta(update: Any) -> None:
        payload = _interaction_payload(update)
        if str(payload.get("type") or "") == "text-delta":
            streamed.append(str(payload.get("text") or ""))

    try:
        agent_opts = sdk.agent_options(
            model=sdk.model_selection(id=model_id),
            api_key=api_key,
            name="discover-composer-only",
            mcp_servers={},
            **_desk_agent_runtime_kwargs(Path(repo_root), sdk=sdk),
        )
        send_opts = sdk.send_options(mcp_servers={}, on_delta=on_delta)
        agent = sdk.agent.create(agent_opts)
        with agent:
            run = agent.send(prompt, send_opts)
            _wait_run_bounded(run, 90.0)
            reply = _reply_from_run(run, streamed)
    except Exception:  # noqa: BLE001
        _LOG.exception("composer-only discover failed")
        return [], f"Composer failed while exploring “{query}”.", "paste_url"

    parsed = parse_composer_discover_json(reply) or {}
    context: list[dict[str, Any]] = []
    for r in parsed.get("context") or []:
        if isinstance(r, str) and r.strip():
            r = {"title": r.strip()}
        if not isinstance(r, dict):
            continue
        if not (r.get("title") or r.get("url") or r.get("doi")):
            continue
        context.append(_stamp_row(r, placement=PLACEMENT_CONTEXT))
    context = context[:limit]
    summary = str(parsed.get("summary") or "").strip()
    next_action = str(parsed.get("next_action") or "").strip() or (
        "probe_url" if any(c.get("url") or c.get("doi") for c in context) else "paste_url"
    )
    if not summary and context:
        summary = f"{len(context)} open source(s) to inspect for “{query}”."
    return context, summary, next_action


def _desk_facts_block(held: list[dict[str, Any]], routes: list[dict[str, Any]], route_reason: str) -> str:
    held_lines = []
    for r in held[:8]:
        held_lines.append(
            f"- {r.get('title') or r.get('dataset_id')} | dataset_id={r.get('dataset_id') or ''} | local_ready={bool(r.get('local_ready'))}"
        )
    route_lines = []
    for r in routes[:5]:
        route_lines.append(
            f"- {r.get('title') or r.get('source_id')} | source_id={r.get('source_id')} | "
            f"access={r.get('access_mode') or ''} | actionable={r.get('actionable')}"
        )
    try:
        from scripts.research_data_mcp.fleet_capacity import fleet_facts_line

        fleet_line = fleet_facts_line()
    except Exception:  # noqa: BLE001 - fleet facts are advisory, never fatal
        fleet_line = ""
    return (
        f"held_count={len(held)}\n"
        + ("\n".join(held_lines) if held_lines else "(none)")
        + f"\n\nroutes_count={len(routes)} reason={route_reason or 'n/a'}\n"
        + ("\n".join(route_lines) if route_lines else "(none)")
        + (f"\n\n{fleet_line}" if fleet_line else "")
    )


def _filter_context_noise(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    q = (query or "").lower()
    out = []
    for r in rows:
        title = str(r.get("title") or "").lower()
        url = str(r.get("url") or r.get("doi") or "").lower()
        blob = f"{title} {url}"
        if any(n in blob for n in _NOISE_TITLE):
            continue
        # Drop pure Zenodo metadata papers when query is polling/markets and title lacks substance
        if "zenodo" in blob and "poll" in q and not any(
            k in title for k in ("poll", "anes", "roper", "election", "survey", "gallup", "pew")
        ):
            continue
        out.append(r)
    return out


def _normalize_context_rows(raw: list[Any], *, limit: int) -> list[dict[str, Any]]:
    context: list[dict[str, Any]] = []
    for r in raw or []:
        if isinstance(r, str) and r.strip():
            r = {"title": r.strip()}
        if not isinstance(r, dict):
            continue
        if not (r.get("title") or r.get("url") or r.get("doi")):
            continue
        stamped = _stamp_row(r, placement=PLACEMENT_CONTEXT)
        stamped["selected_by"] = "composer_mcp"
        context.append(stamped)
    return context[:limit]


def _composer_mcp_grounded(
    gateway: Any,
    query: str,
    *,
    held: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    route_reason: str,
    limit: int = 6,
) -> tuple[list[dict[str, Any]], str, str, list[str]]:
    """Composer + MCP with desk facts pre-injected. Returns context, summary, next, tools_note."""
    from scripts.research_data_mcp.desk_brain import (
        cursor_composer_available,
        run_cursor_composer_turn,
    )

    if not cursor_composer_available():
        # Fall back to composer-only knowledge path
        ctx, summary, nxt = _composer_only_context(query, limit=limit)
        return ctx, summary, nxt, ["composer_only_fallback"]

    desk_facts = _desk_facts_block(held, routes, route_reason)
    try:
        from scripts.research_data_mcp.desk_capabilities import capability_block

        capabilities = capability_block(
            gateway,
            has_held=bool(held),
            has_routes=bool(routes),
            is_question=is_question_like(query),
        )
    except Exception:  # noqa: BLE001 - capability hints are advisory, never fatal
        capabilities = ""
    prompt = _COMPOSER_MCP_PROMPT.format(
        query=query, desk_facts=desk_facts, capabilities=capabilities
    )
    state: dict[str, Any] = {
        "discover_composer": True,
        "desk_primed": True,
    }
    try:
        turn = run_cursor_composer_turn(
            gateway,
            prompt,
            state,
            session_id=f"discover-mcp-{abs(hash(query)) % 10_000_000}",
        )
    except Exception:  # noqa: BLE001
        _LOG.exception("composer+mcp discover failed; falling back to composer-only")
        ctx, summary, nxt = _composer_only_context(query, limit=limit)
        return ctx, summary, nxt, ["composer_only_fallback"]

    reply = str(getattr(turn, "reply", "") or "")
    parsed = parse_composer_discover_json(reply) or {}
    context = _filter_context_noise(
        _normalize_context_rows(parsed.get("context") or [], limit=limit),
        query,
    )
    summary = str(parsed.get("summary") or "").strip()
    next_action = str(parsed.get("next_action") or "").strip()
    allowed = {"use_held", "collect_route", "probe_url", "ask_clarify", "paste_url", "none"}
    if next_action not in allowed:
        next_action = ""
    if held:
        # Prefer Composer judgment; default use_held only when it did not decide.
        if not next_action:
            next_action = "use_held"
    elif routes:
        if not next_action or next_action == "use_held":
            next_action = "collect_route"
    elif not next_action:
        next_action = "probe_url" if any(c.get("url") or c.get("doi") for c in context) else "paste_url"
    if not summary:
        if held:
            summary = f"Library holds {len(held)} dataset(s) for “{query}”."
        elif routes:
            summary = f"Desk can collect via {len(routes)} declared route(s); {len(context)} open source(s) listed."
        elif context:
            summary = f"{len(context)} open source(s) to inspect for “{query}”."
        else:
            summary = f"No desk holding for “{query}”."
    return context, summary, next_action, ["cursor_composer", "mcp"]


def _enrich_cache_key(query: str, *, use_mcp: bool, desk_sig: str) -> str:
    raw = f"{query.strip().lower()}|mcp={int(use_mcp)}|{desk_sig}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _desk_sig(held: list[dict[str, Any]], routes: list[dict[str, Any]]) -> str:
    h = ",".join(str(r.get("dataset_id") or "") for r in held[:5])
    rt = ",".join(str(r.get("source_id") or "") for r in routes[:5])
    return f"{h}|{rt}"


def _cache_get(key: str) -> dict[str, Any] | None:
    hit = _ENRICH_CACHE.get(key)
    if not hit:
        return None
    ts, payload = hit
    if time.time() - ts > _ENRICH_TTL_S:
        _ENRICH_CACHE.pop(key, None)
        return None
    return dict(payload)


def _cache_put(key: str, payload: dict[str, Any]) -> None:
    _ENRICH_CACHE[key] = (time.time(), dict(payload))
    # bound memory
    if len(_ENRICH_CACHE) > 256:
        oldest = sorted(_ENRICH_CACHE.items(), key=lambda kv: kv[1][0])[:64]
        for k, _ in oldest:
            _ENRICH_CACHE.pop(k, None)


def _profile_extra(gateway: Any, query: str, email: str) -> dict[str, Any]:
    from scripts.research_data_mcp.faculty_profile import (
        bigquery_route_hints,
        expand_datacite_queries,
        normalize_email,
        resolve_profile,
    )

    profile = resolve_profile(email=normalize_email(email)) if email else None
    return {
        "profile_queries": expand_datacite_queries(query, profile) if profile else [],
        "bigquery_hints": bigquery_route_hints(profile, query) if profile else [],
    }


def _package_hybrid(
    query: str,
    *,
    held: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    context: list[dict[str, Any]],
    engine: str,
    route_reason: str = "",
    summary: str | None = None,
    next_action: str | None = None,
    tools_used: list[str] | None = None,
    profile_extra: dict[str, Any] | None = None,
    layers: dict[str, Any] | None = None,
    cache_hit: bool = False,
) -> dict[str, Any]:
    if not next_action:
        if held:
            next_action = "use_held"
        elif routes:
            next_action = "collect_route"
        elif any(c.get("url") or c.get("doi") for c in context):
            next_action = "probe_url"
        elif context:
            next_action = "search_wider"
        else:
            next_action = "paste_url"
    if not summary:
        if held:
            summary = f"Library holds {len(held)} dataset(s) for “{query}”."
        elif routes:
            summary = f"Nothing held; {len(routes)} declared route(s) could supply “{query}”."
        elif context:
            summary = f"No desk holding or declared route; {len(context)} open source(s) to inspect."
        elif route_reason == "no_route_found":
            summary = f"No source on this desk carries “{query}”."
        else:
            summary = f"No results for “{query}”."

    sections: list[dict[str, Any]] = []
    if held:
        sections.append({"id": "held", "label": "In Library", "rows": held})
    if routes:
        sections.append({"id": "route", "label": "Declared routes", "rows": routes})
    if context:
        sections.append({"id": "context", "label": "Open sources", "rows": context})

    total = len(held) + len(routes) + len(context)
    out = {
        "query": query,
        "mode": "auto",
        "engine": engine,
        "sections": sections,
        "rows": held + routes + context,
        "total": total,
        "held_count": len(held),
        "route_count": len(routes),
        "context_count": len(context),
        "index_miss": len(held) == 0,
        "weak_match": False,
        "judgment": None,
        "next_action": next_action,
        "summary": summary,
        "route_reason": route_reason or None,
        "tools_used": list(tools_used or []),
        "layers": layers or {},
        "cache_hit": cache_hit,
        "stack": "discover_l0_hands_l1_composer_mcp",
    }
    if profile_extra:
        out.update(profile_extra)
    return out


def run_hybrid_discover(
    gateway: Any,
    query: str,
    *,
    email: str = "",
    limit: int = 12,
    enrich_open: bool = True,
    use_mcp: bool = True,
) -> dict[str, Any]:
    """Best-practice Discover stack: L0 hands → L1 desk-grounded Composer(+MCP)."""
    from scripts.research_data_mcp.discover_desk import desk_check

    q = str(query or "").strip()
    profile_extra = _profile_extra(gateway, q, email)
    t_all = time.perf_counter()

    desk = desk_check(gateway, q, email=email, limit=limit)
    held = list(desk.get("held") or [])
    routes = list(desk.get("routes") or [])
    route_reason = str(desk.get("route_reason") or "")
    hands_ms = dict(desk.get("timing_ms") or {})
    tools: list[str] = ["research_discover_desk"]

    layers: dict[str, Any] = {
        "L0_hands": {
            "ms": hands_ms.get("total"),
            "strong_held": bool(desk.get("strong_held")),
            "held_count": desk.get("held_count"),
            "route_count": desk.get("route_count"),
        }
    }

    skip_l1, skip_reason = should_skip_l1_enrich(
        q,
        strong_held=bool(desk.get("strong_held")),
        held=held,
        routes=routes,
    )
    # Research Discover: never short-circuit on strong_held / routes_enough.
    # L0 still measures held+routes; L1 Composer judges fit and next_action.
    _ = skip_l1, skip_reason

    context: list[dict[str, Any]] = []
    composer_summary = ""
    composer_next = ""
    engine = "hands_routes" if routes else ("lexical" if held else "miss")
    cache_hit = False
    enrich_ms = 0.0

    # Always enrich when open — strong_held is informational only (layers.L0_hands).
    if enrich_open:
        ckey = _enrich_cache_key(
            q,
            use_mcp=use_mcp,
            desk_sig=_desk_sig(held, routes)
            + f"|strong={int(bool(desk.get('strong_held')))}|q={int(is_question_like(q))}",
        )
        cached = _cache_get(ckey)
        if cached:
            context = list(cached.get("context") or [])
            composer_summary = str(cached.get("summary") or "")
            composer_next = str(cached.get("next_action") or "")
            tools.extend(list(cached.get("tools") or []) + ["enrich_cache"])
            engine = str(cached.get("engine") or engine)
            cache_hit = True
            layers["L1_enrich"] = {
                "cache_hit": True,
                "ms": 0,
                "reason": "always_enrich",
                "strong_held_signal": bool(desk.get("strong_held")),
            }
        else:
            t1 = time.perf_counter()
            note: list[str] = []
            if use_mcp:
                context, composer_summary, composer_next, note = _composer_mcp_grounded(
                    gateway,
                    q,
                    held=held,
                    routes=routes,
                    route_reason=route_reason,
                    limit=min(6, limit),
                )
                tools.extend(note)
                engine = "composer_mcp_grounded"
            else:
                note = ["composer_only"]
                tools.append("composer_only")
                context, composer_summary, composer_next = _composer_only_context(
                    q, limit=min(6, limit)
                )
                engine = "hybrid_hands_composer"
            enrich_ms = (time.perf_counter() - t1) * 1000
            layers["L1_enrich"] = {
                "cache_hit": False,
                "ms": round(enrich_ms, 1),
                "engine": engine,
                "reason": "always_enrich",
                "strong_held_signal": bool(desk.get("strong_held")),
            }
            _cache_put(
                ckey,
                {
                    "context": context,
                    "summary": composer_summary,
                    "next_action": composer_next,
                    "tools": note,
                    "engine": engine,
                },
            )
    else:
        layers["L1_enrich"] = {
            "skipped": True,
            "reason": "hands_only",
        }

    summary = None
    next_action = None
    if composer_summary:
        summary = composer_summary
        next_action = composer_next or ("use_held" if held else "paste_url")
    elif held:
        summary = f"Library holds {len(held)} dataset(s) for “{q}”."
        next_action = "use_held"
    elif routes:
        summary = (
            f"Nothing held; {len(routes)} declared route(s) could supply “{q}”."
            + (f" Also {len(context)} open source(s) to inspect." if context else "")
        )
        next_action = "collect_route"
    elif context:
        summary = f"{len(context)} open source(s) to inspect for “{q}”."
        next_action = composer_next or "probe_url"

    layers["total_ms"] = round((time.perf_counter() - t_all) * 1000, 1)
    return _package_hybrid(
        q,
        held=held,
        routes=routes,
        context=context,
        engine=engine,
        route_reason=route_reason,
        summary=summary,
        next_action=next_action,
        tools_used=tools,
        profile_extra=profile_extra,
        layers=layers,
        cache_hit=cache_hit,
    )


def run_composer_discover(
    gateway: Any,
    query: str,
    *,
    email: str = "",
    limit: int = 12,
) -> dict[str, Any]:
    """Composer Explore mode — desk-grounded Composer + MCP."""
    return run_hybrid_discover(
        gateway, query, email=email, limit=limit, enrich_open=True, use_mcp=True
    )


def discover_turn(
    gateway: Any,
    query: str,
    *,
    email: str = "",
    limit: int = 12,
    mode: str = "auto",
) -> dict[str, Any]:
    """Explore entry — L0 hands / L1 desk-grounded Composer+MCP."""
    q = str(query or "").strip()
    mode_norm = str(mode or "auto").strip().lower()
    if mode_norm in {"agent", "toolbox", "toolbox_agent"}:
        mode_norm = "auto"
    if mode_norm not in {"auto", "composer", "lexical", "hands", "composer_only"}:
        mode_norm = "auto"

    if mode_norm == "lexical":
        out = gateway.discover_search_lexical(q, email=email, limit=limit)
        out["mode"] = "lexical"
        out["engine"] = "lexical"
        out["next_action"] = "use_held" if not out.get("index_miss") else "paste_url"
        out["summary"] = (
            f"Lexical catalog match for “{q}”."
            if not out.get("index_miss")
            else f"No lexical catalog match for “{q}”."
        )
        out["stack"] = "discover_lexical_only"
        return out

    if mode_norm == "hands":
        return run_hybrid_discover(
            gateway, q, email=email, limit=limit, enrich_open=False, use_mcp=False
        )

    if mode_norm == "composer_only":
        return run_hybrid_discover(
            gateway, q, email=email, limit=limit, enrich_open=True, use_mcp=False
        )

    return run_hybrid_discover(
        gateway, q, email=email, limit=limit, enrich_open=True, use_mcp=True
    )
