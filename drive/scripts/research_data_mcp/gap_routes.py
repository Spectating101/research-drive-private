#!/usr/bin/env python3
"""Model-mediated collection options for a confirmed Discover evidence gap.

This module deliberately does *not* infer research requirements from a
question.  It receives the typed result of held-evidence assessment and uses
the model only to compare that confirmed gap against the desk's declared
source inventory.  Code validates identity and lifecycle policy; it never
tries to replace the research judgement with a keyword taxonomy.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Iterable


SOURCE_MAP_REL = "config/databank_source_map.json"
_UNMET_STATES = frozenset({"not_supported", "unknown", "unverified", "conflicting"})
_SELF_SERVE_ACCESS_MODES = frozenset(
    {
        "materialized_instant",
        "materialized_bulk",
        "live_connector",
        "procurement_catalog",
        "catalog_reference",
        "derived_internal",
    }
)


class GapRouteModelUnavailable(RuntimeError):
    """No trustworthy model answer is available for route comparison."""


def load_declared_sources(repo_root: Path) -> dict[str, dict[str, Any]]:
    """Load the only sources a route proposal may name."""
    try:
        document = json.loads((Path(repo_root) / SOURCE_MAP_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    raw = document.get("sources") if isinstance(document, dict) else None
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items() if isinstance(value, dict)}
    return {
        str(item["id"]): item
        for item in raw or []
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }


def unmet_dimensions(assessment: dict[str, Any]) -> list[str]:
    """Read only exact backend-assessment statuses; never parse the question."""
    basis = assessment.get("assessment_basis") if isinstance(assessment, dict) else None
    statuses = basis.get("dimension_status") if isinstance(basis, dict) else None
    if not isinstance(statuses, dict):
        return []
    return sorted(
        str(dimension)
        for dimension, status in statuses.items()
        if str(status) in _UNMET_STATES
    )


def _source_prompt_block(sources: dict[str, dict[str, Any]]) -> str:
    rows = []
    for source_id, source in sorted(sources.items()):
        label = str(source.get("label") or source.get("name") or source_id)
        provider = str(source.get("provider") or "unspecified provider")
        access = str(source.get("access_mode") or "unspecified access")
        notes = str(source.get("notes") or "")[:300]
        rows.append(f"{source_id} | {label} | {provider} | {access} | {notes}")
    return "\n".join(rows)


_PROMPT = """You are selecting possible collection routes for a research desk.

Research question:
{question}

The desk's held-evidence assessment explicitly marked only these dimensions as
unmet: {gaps}

Below are the ONLY sources the desk is allowed to offer. Each row is:
source_id | label | provider | access_mode | declared notes

For each unmet dimension, propose at most two genuinely relevant sources. Do
not invent sources or claim that collection will succeed. If the source list
does not justify a route, omit that dimension.

Return only one route per line in this exact format:
dimension | source_id | short reason (12 words maximum)

DECLARED SOURCES:
{sources}
"""


def _run_model(prompt: str, model: str, timeout: float) -> str:
    """Run the configured local agent; failures produce no routes, never a heuristic."""
    binary = shutil.which("cursor-agent")
    if not binary:
        raise GapRouteModelUnavailable("cursor-agent is not installed")
    environment = dict(os.environ)
    if not environment.get("CURSOR_API_KEY"):
        raise GapRouteModelUnavailable("CURSOR_API_KEY is not configured")
    try:
        completed = subprocess.run(
            [
                binary,
                "-p",
                prompt,
                "--model",
                model,
                "--output-format",
                "text",
                "--mode",
                "ask",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=environment,
            cwd="/tmp",
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GapRouteModelUnavailable("model timed out") from exc
    except OSError as exc:
        raise GapRouteModelUnavailable("model process could not start") from exc
    if completed.returncode:
        raise GapRouteModelUnavailable(f"model process failed (exit {completed.returncode})")
    return completed.stdout


def parse_model_routes(text: str, gaps: Iterable[str], source_ids: Iterable[str]) -> list[dict[str, str]]:
    """Validate model output as identities, not as an alternative reasoning engine."""
    allowed_gaps = {str(gap) for gap in gaps}
    allowed_sources = {str(source_id) for source_id in source_ids}
    routes: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw_line in str(text or "").splitlines():
        parts = [part.strip() for part in raw_line.strip().strip("`").lstrip("-* ").split("|")]
        if len(parts) < 3:
            continue
        dimension, source_id, reason = parts[0], parts[1], parts[2]
        key = (dimension, source_id)
        if dimension not in allowed_gaps or source_id not in allowed_sources or key in seen:
            continue
        seen.add(key)
        routes.append({"dimension": dimension, "source_id": source_id, "reason": reason[:120]})
    return routes


def routes_for_gaps(
    question: str,
    assessment: dict[str, Any],
    repo_root: Path,
    *,
    model: str | None = None,
    timeout: float = 12.0,
    run_model: Callable[[str, str, float], str] = _run_model,
) -> dict[str, Any]:
    """Return verified source options after a real assessment—not a promise to collect."""
    status = str(assessment.get("assessment_status") or "") if isinstance(assessment, dict) else ""
    if status != "assessed":
        return {
            "gaps": [],
            "routes": [],
            "reason": "requirement_not_established",
            "detail": "Coverage was not assessed from a confirmed requirement.",
        }
    gaps = unmet_dimensions(assessment)
    if not gaps:
        return {"gaps": [], "routes": [], "reason": "nothing_missing"}
    sources = load_declared_sources(repo_root)
    if not sources:
        return {"gaps": gaps, "routes": [], "reason": "no_declared_sources"}

    prompt = _PROMPT.format(
        question=str(question or "").strip(),
        gaps=", ".join(gaps),
        sources=_source_prompt_block(sources),
    )
    try:
        raw = run_model(prompt, model or os.getenv("RD_CATALOG_MODEL", "composer-2.5"), timeout)
    except GapRouteModelUnavailable as exc:
        return {"gaps": gaps, "routes": [], "reason": f"backend_unavailable: {exc}"}

    routes = parse_model_routes(raw, gaps, sources)
    for route in routes:
        source = sources[route["source_id"]]
        access_mode = str(source.get("access_mode") or "")
        route.update(
            {
                "label": str(source.get("label") or source.get("name") or route["source_id"]),
                "provider": source.get("provider"),
                "access_mode": access_mode,
                "actionable": access_mode in _SELF_SERVE_ACCESS_MODES,
                "action": "collect" if access_mode in _SELF_SERVE_ACCESS_MODES else "request_access",
            }
        )
    return {"gaps": gaps, "routes": routes, "reason": "ok" if routes else "no_route_found"}
