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
    lines = []
    for sid, meta in sources.items():
        mode = str(meta.get("access_mode") or "")
        note = str(meta.get("name") or meta.get("summary") or "")[:70]
        lines.append(f"{sid} | {mode} | {note}")
    return "\n".join(lines)


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


def routes_for_gaps(
    question: str,
    assessment: dict[str, Any],
    repo_root: Path,
    *,
    model: str | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Propose a collection route per unmet requirement."""
    gaps = unmet_dimensions(assessment)
    sources = load_sources(repo_root)
    status = str((assessment or {}).get("assessment_status") or "")
    if status and status != "assessed":
        # No requirement could be established, so no dimension was ever checked.
        # Reporting "nothing_missing" here would tell a researcher their library
        # covers data the desk does not hold -- "patent citation networks"
        # returned no gaps against a catalog with no patent data at all. Not
        # knowing and having everything must not share an answer.
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

    from scripts.research_data_mcp.requirement_extraction import (
        ExtractionUnavailable,
        run_cursor_prompt,
    )

    prompt = _PROMPT.format(
        question=str(question or "").strip(),
        gaps=", ".join(gaps),
        sources=_sources_block(sources),
    )
    try:
        raw = run_cursor_prompt(
            prompt, model or os.getenv("RD_CATALOG_MODEL", "composer-2.5"), timeout
        )
    except ExtractionUnavailable as exc:
        return {"gaps": gaps, "routes": [], "reason": f"backend_unavailable: {exc}"}

    routes = parse_routes(raw, gaps, set(sources))
    for route in routes:
        meta = sources.get(route["source_id"]) or {}
        mode = str(meta.get("access_mode") or "")
        route["access_mode"] = mode
        # A licensed or planned source is a request, not a click. Saying which
        # it is up front stops "Add to collection" promising what it cannot do.
        route["actionable"] = mode in _SELF_SERVE
        route["action"] = "collect" if route["actionable"] else "request_access"
    return {"gaps": gaps, "routes": routes, "reason": "ok" if routes else "no_route_found"}
