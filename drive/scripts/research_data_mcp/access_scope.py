"""Desk entitlement scope — what we CAN access vs what is materialized."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ACCESS_SCOPE_REL = "config/databank_access_scope.json"
RESEARCH_COVERAGE_REL = "docs/status/generated/databank_research_coverage.json"
REFINITIV_ENTITLEMENT_REL = "docs/status/generated/refinitiv_harvest_completion.json"

# Numeric rank for max-merge across sources (higher = more reachable)
ACCESS_RANK: dict[str, int] = {
    "blocked": 0,
    "metadata_only": 1,
    "partial": 2,
    "on_demand": 2,
    "not_wired": 3,
    "full": 3,
}

ACCESS_LABEL = {v: k for k, v in sorted(ACCESS_RANK.items(), key=lambda x: -x[1])}
for k in ACCESS_RANK:
    ACCESS_LABEL[ACCESS_RANK[k]] = k


def _repo(repo_root: Path) -> Path:
    return Path(repo_root).resolve()


@lru_cache(maxsize=8)
def _load_json(repo_root: str, rel: str) -> dict[str, Any]:
    path = _repo(Path(repo_root)) / rel
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def access_scope_path(repo_root: Path) -> Path:
    root = _repo(repo_root)
    for candidate in (root / "config/databank_access_scope.json", root / "drive/config/databank_access_scope.json"):
        if candidate.is_file():
            return candidate
    return root / ACCESS_SCOPE_REL


def load_access_scope(repo_root: Path) -> dict[str, Any]:
    path = access_scope_path(repo_root)
    if not path.is_file():
        return {"version": 0, "sources": [], "error": f"missing {path}"}
    return json.loads(path.read_text(encoding="utf-8"))


def _max_access(current: str, new: str) -> str:
    if ACCESS_RANK.get(new, 0) > ACCESS_RANK.get(current, 0):
        return new
    return current


def _build_entitlement_matrix(doc: dict[str, Any]) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, list[str]]]]:
    """Return geo×cap access level + contributing source ids per cell."""
    geos = list(doc.get("geographies") or [])
    caps = list(doc.get("capabilities") or [])
    matrix: dict[str, dict[str, str]] = {g: {c: "blocked" for c in caps} for g in geos}
    contributors: dict[str, dict[str, list[str]]] = {g: {c: [] for c in caps} for g in geos}

    for src in doc.get("sources") or []:
        sid = str(src.get("source_id") or "")
        if not sid:
            continue
        for cell in src.get("coverage_cells") or []:
            cap = str(cell.get("capability") or "")
            geo = str(cell.get("geography") or "")
            access = str(cell.get("access") or "blocked")
            if geo not in matrix or cap not in matrix[geo]:
                continue
            prev = matrix[geo][cap]
            matrix[geo][cap] = _max_access(prev, access)
            if ACCESS_RANK.get(access, 0) > 0:
                contributors[geo][cap].append(sid)
    return matrix, contributors


def _load_materialized_matrix(repo_root: Path) -> dict[str, dict[str, int]] | None:
    for rel in (RESEARCH_COVERAGE_REL, f"drive/{RESEARCH_COVERAGE_REL}"):
        path = _repo(repo_root) / rel
        if path.is_file():
            doc = json.loads(path.read_text(encoding="utf-8"))
            return doc.get("coverage_matrix")
    return None


def _gap_type(access: str, materialized: int) -> str | None:
    ar = ACCESS_RANK.get(access, 0)
    if ar == 0:
        return "license_block" if access == "blocked" else None
    if access == "not_wired" and materialized == 0:
        return "not_wired"
    if access in ("on_demand", "metadata_only") and materialized < 2:
        return "on_demand_only"
    if ar >= 2 and materialized < 2:
        return "entitlement_gap"
    return None


def build_access_coverage_audit(repo_root: Path) -> dict[str, Any]:
    root = _repo(repo_root)
    doc = load_access_scope(root)
    entitlement_matrix, contributors = _build_entitlement_matrix(doc)
    materialized = _load_materialized_matrix(root)

    geos = list(doc.get("geographies") or [])
    caps = list(doc.get("capabilities") or [])

    gap_matrix: dict[str, dict[str, str | None]] = {g: {} for g in geos}
    combined: dict[str, dict[str, dict[str, Any]]] = {g: {} for g in geos}
    gap_cells: list[dict[str, Any]] = []

    for g in geos:
        for c in caps:
            access = entitlement_matrix[g][c]
            mat = (materialized or {}).get(g, {}).get(c, 0) if materialized else None
            gap = _gap_type(access, mat if mat is not None else 0)
            gap_matrix[g][c] = gap
            combined[g][c] = {
                "accessible": access,
                "accessible_rank": ACCESS_RANK.get(access, 0),
                "materialized_score": mat,
                "gap": gap,
                "sources": sorted(set(contributors[g][c])),
            }
            if gap in ("entitlement_gap", "not_wired"):
                gap_cells.append(
                    {
                        "geography": g,
                        "capability": c,
                        "accessible": access,
                        "materialized_score": mat,
                        "gap": gap,
                        "sources": combined[g][c]["sources"],
                    }
                )

    # Per-source entitlement rows (accessible scope, not vault)
    source_rows: list[dict[str, Any]] = []
    for src in doc.get("sources") or []:
        sid = str(src.get("source_id") or "")
        cells = list(src.get("coverage_cells") or [])
        source_rows.append(
            {
                "source_id": sid,
                "subscription_status": src.get("subscription_status"),
                "license_holder": src.get("license_holder"),
                "fetch_modes": src.get("fetch_modes") or [],
                "reachable_products": src.get("reachable_products") or [],
                "coverage_cell_count": len(cells),
                "license_blocks": src.get("license_blocks") or [],
                "notes": src.get("notes"),
            }
        )

    # Per-source not_wired / on_demand gaps (source-specific, not aggregate cell)
    source_level_gaps: dict[str, list[dict[str, Any]]] = {}
    for src in doc.get("sources") or []:
        sid = str(src.get("source_id") or "")
        for cell in src.get("coverage_cells") or []:
            access = str(cell.get("access") or "")
            if access not in ("not_wired", "on_demand"):
                continue
            geo = str(cell.get("geography") or "")
            cap = str(cell.get("capability") or "")
            mat = (materialized or {}).get(geo, {}).get(cap, 0) if materialized else None
            source_level_gaps.setdefault(sid, []).append(
                {
                    "geography": geo,
                    "capability": cap,
                    "access": access,
                    "materialized_score": mat,
                    "note": cell.get("note"),
                }
            )

    # Highlight not_wired from aggregate gap_cells grouped by source
    not_wired_sources: dict[str, list[dict[str, Any]]] = {}
    for cell in gap_cells:
        if cell["gap"] != "not_wired":
            continue
        for sid in cell["sources"]:
            not_wired_sources.setdefault(sid, []).append(cell)

    refinitiv_ent = _load_json(str(root), REFINITIV_ENTITLEMENT_REL)
    entitlement_probe = None
    if refinitiv_ent:
        entitlement_probe = {
            "canonical_run_id": refinitiv_ent.get("canonical_run_id"),
            "summary": refinitiv_ent.get("entitlement_summary"),
            "blocked_categories": refinitiv_ent.get("blocked_categories"),
            "entitled_categories": [
                {"id": c.get("category_id"), "description": c.get("description")}
                for c in refinitiv_ent.get("entitled_categories") or []
            ],
        }

    accessible_cells = sum(
        1 for g in geos for c in caps if ACCESS_RANK.get(entitlement_matrix[g][c], 0) >= 2
    )
    gap_count = sum(1 for g in geos for c in caps if gap_matrix[g][c] in ("entitlement_gap", "not_wired"))

    return {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "access_scope_version": doc.get("version"),
        "principle": doc.get("principle"),
        "access_levels": doc.get("access_levels") or {},
        "summary": {
            "geographies": len(geos),
            "capabilities": len(caps),
            "entitlement_sources": len(doc.get("sources") or []),
            "accessible_cells_ge_2": accessible_cells,
            "total_cells": len(geos) * len(caps),
            "gap_cells": gap_count,
            "not_wired_sources": sorted(not_wired_sources.keys()),
            "materialized_matrix_loaded": materialized is not None,
        },
        "entitlement_matrix": entitlement_matrix,
        "materialized_matrix": materialized,
        "gap_matrix": gap_matrix,
        "combined_matrix": combined,
        "priority_gaps": sorted(gap_cells, key=lambda x: (-ACCESS_RANK.get(x["accessible"], 0), x["geography"], x["capability"]))[:40],
        "not_wired_by_source": {k: v for k, v in not_wired_sources.items()},
        "source_level_gaps": source_level_gaps,
        "sources": source_rows,
        "refinitiv_entitlement_probe": entitlement_probe,
        "documentation": {
            "canonical_config": "drive/config/databank_access_scope.json",
            "materialized_scores": "docs/status/generated/databank_research_coverage.json",
            "regenerate": "python3 scripts/databank_access_scope.py --json",
        },
    }
