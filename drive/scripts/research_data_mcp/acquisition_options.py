"""Passive, federated evidence bundle for Composer source selection.

This is intentionally an *options* call, not a router.  It gathers the local
library evidence, source/connector facts, live public-adapter candidates, optional
general web results, and licensed-source readiness in one bounded response.  The
model still decides which candidate is relevant and must pass that exact identity to
``research_webfetch_handoff`` before any collection plan is executed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.research_data_mcp.candidate_key import stamp_rows
from scripts.research_data_mcp.licensed_sources import inspect_source


def _section(section_id: str, label: str, rows: list[dict[str, Any]], *, note: str = "") -> dict[str, Any]:
    return {
        "id": section_id,
        "label": label,
        "count": len(rows),
        "rows": stamp_rows(rows),
        **({"note": note} if note else {}),
    }


def build_acquisition_options(
    gateway: Any,
    query: str,
    *,
    email: str = "",
    limit: int = 12,
    live: bool = True,
    include_web: bool = False,
    tavily_live: bool = False,
) -> dict[str, Any]:
    """Gather all source evidence without selecting, fetching, or submitting."""
    q = str(query or "").strip()
    lim = max(1, min(int(limit or 12), 24))
    if not q:
        return {
            "ok": False,
            "query": "",
            "error": "query is required",
            "sections": [],
            "source_readiness": inspect_source(Path(gateway.repo_root)),
            "selection_policy": "Composer/Cursor selects; backend only validates the explicit choice",
            "side_effects": "none",
        }

    sections: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    try:
        held = gateway.discover_search(q, email=str(email or ""), limit=lim)
        held_rows: list[dict[str, Any]] = []
        for section in held.get("sections") or []:
            for row in section.get("rows") or []:
                if isinstance(row, dict):
                    held_rows.append({**row, "result_role": "library_evidence", "is_offering": False})
        if held_rows:
            sections.append(
                _section(
                    "library_evidence",
                    "Already held (evidence only)",
                    held_rows[:lim],
                    note="Held rows show what is already available; they are not automatically selected as the offering.",
                )
            )
    except Exception as exc:  # noqa: BLE001 - one lane cannot hide the others
        errors.append({"lane": "library", "error": f"{type(exc).__name__}: {exc}"[:240]})

    try:
        sources = gateway.discover_source_search(q, limit=lim, live=bool(live), semantic=True)
        source_rows = [row for row in (sources.get("results") or []) if isinstance(row, dict)]
        if source_rows:
            sections.append(
                _section(
                    "source_options",
                    "Source routes and live candidates",
                    source_rows[:lim],
                    note="Includes source metadata and inspect-only public adapter candidates; model judgment is still required.",
                )
            )
        source_search_meta = {
            "search_mode": sources.get("search_mode"),
            "sources_tried": sources.get("sources_tried") or [],
            "remote_search": sources.get("remote_search") or {},
            "index_miss": sources.get("index_miss"),
            "no_supported_route": sources.get("no_supported_route"),
        }
    except Exception as exc:  # noqa: BLE001
        source_search_meta = {"error": f"{type(exc).__name__}: {exc}"[:240]}
        errors.append({"lane": "source_search", "error": source_search_meta["error"]})

    web: dict[str, Any] = {}
    if include_web:
        try:
            from scripts.research_data_mcp.web_search import discover_sources

            web = discover_sources(
                Path(gateway.repo_root),
                q,
                max_results=lim,
                tavily_live=bool(tavily_live),
            )
            web_rows = [row for row in (web.get("results") or []) if isinstance(row, dict)]
            if web_rows:
                sections.append(
                    _section(
                        "web_options",
                        "General web discovery",
                        web_rows[:lim],
                        note="Web results are evidence only; Cursor/webfetch may inspect and select one exact candidate.",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            errors.append({"lane": "web_discovery", "error": f"{type(exc).__name__}: {exc}"[:240]})

    readiness = inspect_source(Path(gateway.repo_root))
    return {
        "ok": True,
        "query": q,
        "sections": sections,
        "total_options": sum(int(section.get("count") or 0) for section in sections),
        "source_search": source_search_meta,
        "web_search": {
            "requested": bool(include_web),
            "tavily_live": bool(tavily_live),
            "sources_tried": web.get("sources_tried") or [],
            "queries_tried": web.get("queries_tried") or [],
            "relevance": web.get("relevance") or {},
        },
        "source_readiness": readiness,
        "selection_policy": {
            "authority": "cursor_composer",
            "model_selects": True,
            "backend_selects": False,
            "next_step": "Pass the selected candidate identity and optional webfetch receipt to research_webfetch_handoff.",
            "held_data": "library_evidence is reassurance, not an offering unless the model explicitly selects it.",
            "inspect_only": "Live public candidates are not claims of entitlement, bytes, or queryability.",
        },
        "errors": errors,
        "side_effects": "none — no fetch, job submission, download, or registry mutation",
    }

