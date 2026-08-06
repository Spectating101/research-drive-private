#!/usr/bin/env python3
"""Turn a coverage gap into something the desk can actually collect.

Discover can already say *"you hold 3 of 5 requirements; geography and
time_range are missing"*, and ``POST /library/discover/collect`` can already
acquire from a named source.  Nothing joined the two, so a researcher was told
what they lacked and left to know, unaided, which of 25 declared sources
supplies it.  Finding without getting is where the desk stopped being a
procurement tool.

This maps each unmet dimension to the sources that could close it, so the answer
to "missing geography" is a route with an ``Add to collection`` action rather
than a diagnosis.

Two constraints shape the design:

* **Only declared sources.** Every proposed ``source_id`` must exist in
  ``databank_source_map.json``, or it is dropped. Proposing a plausible source
  the desk has no route to would be worse than proposing nothing -- the
  researcher cannot tell the difference until a collect job fails.
* **Access mode is part of the answer.** A source behind a licence
  (``planned``, or requiring manual entitlement) is not the same offer as one
  that is already materialised, and saying so up front is the difference between
  a route and a dead end.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

SOURCE_MAP_REL = "config/databank_source_map.json"

# Access modes that can be actioned without a human clearing an entitlement.
_SELF_SERVE = frozenset({
    "materialized_instant", "materialized_bulk", "live_connector",
    "procurement_catalog", "catalog_reference", "derived_internal",
})


def load_sources(repo_root: Path) -> dict[str, dict[str, Any]]:
    """Declared sources, keyed by source_id."""
    path = Path(repo_root) / SOURCE_MAP_REL
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    raw = doc.get("sources") or {}
    if isinstance(raw, dict):
        return {str(k): (v if isinstance(v, dict) else {}) for k, v in raw.items()}
    out: dict[str, dict[str, Any]] = {}
    for item in raw:
        if isinstance(item, dict) and item.get("id"):
            out[str(item["id"])] = item
    return out


def unmet_dimensions(assessment: dict[str, Any]) -> list[str]:
    """Dimensions the held evidence does not satisfy.

    ``unknown`` counts as unmet: a dimension nobody could verify is exactly the
    case a researcher needs a route for, and treating it as satisfied would be
    the false-clean-negative failure one layer up.
    """
    basis = (assessment or {}).get("assessment_basis") or {}
    status = basis.get("dimension_status") or {}
    return sorted(
        dim for dim, state in status.items()
        if str(state) in {"not_supported", "unknown", "unverified", "conflicting"}
    )


def _sources_block(sources: dict[str, dict[str, Any]]) -> str:
    """One line per source: id, access mode, and what it actually carries.

    Used to read ``meta.get("name")``, but the source map has no ``name`` key --
    it uses ``label``. Every description came out empty, so the model was shown
    ``lseg_edp | materialized_instant |`` and nothing else, and had to infer
    each source's contents from its id. Asked for US opinion polling it
    answered ``derived_research_panels`` with "Survey panels carry US public
    opinion and election polling data" -- a real source id and an invented
    claim, which is precisely the failure grounding is supposed to stop.

    Declared capabilities and geographies are included because they are what
    the desk actually asserts about each source, and a model that can see
    "daily_prices, fundamentals" will not offer it as a polling route.
    """
    lines = []
    for sid, meta in sources.items():
        mode = str(meta.get("access_mode") or "")
        label = str(meta.get("label") or meta.get("name") or "")[:60]
        carries = ", ".join(str(c) for c in (meta.get("capabilities") or []))[:110]
        geo = ", ".join(str(g) for g in (meta.get("geographies") or []))[:60]
        parts = [p for p in (label, f"carries: {carries}" if carries else "",
                             f"covers: {geo}" if geo else "") if p]
        lines.append(f"{sid} | {mode} | {' | '.join(parts)}")
    return "\n".join(lines)


_STOP = frozenset({
    "a", "an", "the", "and", "or", "for", "of", "to", "in", "on", "at", "by",
    "from", "with", "that", "this", "these", "those", "data", "dataset",
    "datasets", "source", "sources", "research", "desk", "get", "need",
})

# Query tokens that imply a capability family. If the question lights one of
# these up, a candidate source must declare at least one matching capability
# (or carry the token in its label). Otherwise the model can still invent a
# plausible-sounding reason for an unrelated declared source_id.
_CAP_HINTS: tuple[tuple[frozenset[str], frozenset[str]], ...] = (
    (frozenset({"price", "prices", "pricing", "ohlc", "equity", "equities",
                "stock", "stocks", "share", "shares", "ticker", "tickers"}),
     frozenset({"daily_prices", "index_pit_survivorship"})),
    (frozenset({"fundamental", "fundamentals", "earnings", "revenue",
                "balance", "income", "compustat"}),
     frozenset({"fundamentals", "estimates_revisions"})),
    (frozenset({"estimate", "estimates", "revision", "revisions", "analyst"}),
     frozenset({"estimates_revisions"})),
    (frozenset({"news", "shock", "shocks", "headline", "headlines", "gdelt"}),
     frozenset({"entity_news_shocks", "country_news_shocks", "entity_join_gdelt_ric"})),
    (frozenset({"sentiment", "social", "twitter", "reddit"}),
     frozenset({"social_sentiment"})),
    (frozenset({"crypto", "onchain", "on-chain", "bitcoin", "ethereum",
                "stablecoin", "defi"}),
     frozenset({"onchain_crypto"})),
    (frozenset({"risk", "vol", "volatility", "skew", "option", "options"}),
     frozenset({"risk_overlay"})),
    (frozenset({"governance", "regulatory", "regulation", "filing", "filings"}),
     frozenset({"governance_regulatory"})),
    # Desk has no declared capability for these. Lighting the hint forces every
    # candidate through the matching-cap check, which none can pass.
    (frozenset({"poll", "polling", "polls", "survey", "surveys", "opinion",
                "ballot", "election", "elections", "referendum"}),
     frozenset()),
)

_GEO_ONLY = frozenset({
    "us", "usa", "america", "american", "taiwan", "indonesia", "japan", "korea",
    "singapore", "asia", "asian", "macro", "global", "world", "international",
})


def _tokens(text: str) -> set[str]:
    out: set[str] = set()
    for raw in str(text or "").lower().replace("-", " ").replace("_", " ").split():
        tok = "".join(ch for ch in raw if ch.isalnum())
        if len(tok) > 2 and tok not in _STOP:
            out.add(tok)
    return out


def _source_bag(meta: dict[str, Any]) -> set[str]:
    parts = [
        str(meta.get("label") or ""),
        str(meta.get("provider") or ""),
        " ".join(str(c) for c in (meta.get("capabilities") or [])),
        " ".join(str(g) for g in (meta.get("geographies") or [])),
    ]
    return _tokens(" ".join(parts))


def route_plausible(question: str, meta: dict[str, Any]) -> bool:
    """Deterministic veto after the model proposes a declared source_id.

    Prompt grounding stops most hallucinations; this is the belt. A source with
    no declared label/capabilities cannot justify any route. A question that
    clearly asks for prices/news/crypto/etc. cannot be answered by a source that
    does not declare a matching capability. Soft token overlap covers the rest.
    """
    q = _tokens(question)
    if not q:
        return False
    bag = _source_bag(meta)
    caps = {str(c) for c in (meta.get("capabilities") or [])}
    label = str(meta.get("label") or meta.get("name") or "").strip()
    if not caps and not label:
        return False

    hinted = False
    for q_hints, need_caps in _CAP_HINTS:
        if q & q_hints:
            hinted = True
            if need_caps and caps & need_caps:
                return True
            # Label may name the family even when capabilities are empty
            # (e.g. derived_synthesis). Require the hint token itself then.
            if need_caps and q_hints & bag:
                return True
    if hinted:
        return False

    # No strong family hint -- require shared *substance* between question and
    # what the desk asserts. Geography alone ("US") must not rescue an unrelated
    # source when the question also asked for something the source does not carry.
    substance = q - _GEO_ONLY
    if substance:
        return bool(substance & bag)
    return bool(q & bag)


_PROMPT = """A researcher asked: {question}

Their library covers some requirements but not these: {gaps}

Below are the ONLY sources this desk has a collection route for, as:
source_id | access_mode | description

For each unmet requirement, name the sources that could supply it, best first,
at most 2 per requirement. Skip a requirement entirely if no listed source
plausibly supplies it -- an honest omission is correct, an invented route is a
defect. Use only source_id values that appear verbatim below.

Output only lines of the form:
<requirement> | <source_id> | <reason, max 12 words>

SOURCES:
{sources}"""


def parse_routes(text: str, gaps: Iterable[str], valid: set[str]) -> list[dict[str, str]]:
    """Keep only routes naming a real gap and a declared source."""
    wanted = {str(g) for g in gaps}
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in str(text or "").splitlines():
        line = raw.strip().strip("`").lstrip("-* ").strip()
        if not line or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        dimension, source_id = parts[0], parts[1]
        reason = parts[2] if len(parts) > 2 else ""
        if dimension not in wanted or source_id not in valid:
            continue
        if (dimension, source_id) in seen:
            continue
        seen.add((dimension, source_id))
        out.append({"dimension": dimension, "source_id": source_id, "reason": reason[:120]})
    return out


_QUERY_PROMPT = """A researcher asked this desk for: {question}

The desk holds nothing matching it. Below are the ONLY sources this desk has a
collection route for, as:
source_id | access_mode | description

Name the sources that could plausibly supply the requested data, best first, at
most 3. A source counts only if it genuinely carries this kind of data -- a
market-price archive is not a route to opinion polling. If no listed source
could supply it, output only: NONE

Answering NONE is correct and expected. Offering an unrelated source is the
defect this exists to prevent. Use only source_id values appearing verbatim below.

Output only lines of the form:
<source_id> | <reason this source could supply it, max 14 words>

SOURCES:
{sources}"""


def routes_for_query(
    question: str,
    repo_root: Path,
    *,
    model: str | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Declared sources that could supply the request — deterministic hand only.

    Composer owns judgment/reasons via MCP. This lists ``route_plausible`` matches
    ranked by token overlap with the source bag — never a second LLM brain.
    """
    _ = model, timeout
    sources = load_sources(repo_root)
    if not sources:
        return {"routes": [], "reason": "no_declared_sources"}

    plausible = {
        sid: meta for sid, meta in sources.items() if route_plausible(question, meta)
    }
    if not plausible:
        return {"routes": [], "reason": "no_route_found"}

    q_tokens = _tokens(question)
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for sid, meta in plausible.items():
        bag = _source_bag(meta)
        score = len(q_tokens & bag)
        scored.append((score, sid, meta))
    scored.sort(key=lambda item: (-item[0], item[1]))

    routes: list[dict[str, Any]] = []
    for score, source_id, meta in scored[:3]:
        mode = str(meta.get("access_mode") or "")
        label = meta.get("label") or source_id
        routes.append({
            "source_id": source_id,
            "label": label,
            "provider": meta.get("provider"),
            "access_mode": mode,
            "reason": f"Declared route overlaps query tokens (score={score})",
            "actionable": mode in _SELF_SERVE,
            "action": "collect" if mode in _SELF_SERVE else "request_access",
        })
    return {
        "routes": routes,
        "reason": "ok" if routes else "no_route_found",
    }


def routes_for_gaps(
    question: str,
    assessment: dict[str, Any],
    repo_root: Path,
    *,
    model: str | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Deterministic gap → declared-source listing. Composer writes narrative reasons."""
    _ = model, timeout
    gaps = unmet_dimensions(assessment)
    sources = load_sources(repo_root)
    status = str((assessment or {}).get("assessment_status") or "")
    if status and status != "assessed":
        return {
            "gaps": [],
            "routes": [],
            "reason": "requirement_not_established",
            "detail": (
                "The question did not yield a checkable requirement, so coverage "
                "was never assessed. This is not a statement that the data is held."
            ),
        }
    if not gaps:
        return {"gaps": [], "routes": [], "reason": "nothing_missing"}
    if not sources:
        return {"gaps": gaps, "routes": [], "reason": "no_declared_sources"}

    routes: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for gap in gaps:
        focus = f"{question} {gap}"
        for sid, meta in sources.items():
            if not route_plausible(focus, meta):
                continue
            key = (str(gap), sid)
            if key in seen:
                continue
            seen.add(key)
            mode = str(meta.get("access_mode") or "")
            routes.append({
                "dimension": str(gap),
                "source_id": sid,
                "reason": f"Declared source may cover unmet {gap}",
                "access_mode": mode,
                "actionable": mode in _SELF_SERVE,
                "action": "collect" if mode in _SELF_SERVE else "request_access",
            })
            if sum(1 for r in routes if r.get("dimension") == gap) >= 2:
                break
    return {"gaps": gaps, "routes": routes, "reason": "ok" if routes else "no_route_found"}
