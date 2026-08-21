#!/usr/bin/env python3
"""Propose the held evidence a research objective would actually be built from.

Every synthesis thread on this desk carries nodes=0. Nothing maps Library
evidence onto a thread, so the whole downstream chain is starved: column
profiles need mapped inputs, unit conflicts need two profiled columns, join
candidates need two datasets. The workspace renders a full method surface over
fields no producer writes.

The retrieval to do it already works. Asked the JKSE thread's own objective,
semantic_discover returns the datasets that thread's blueprint names by hand.

Two rules this holds to:

  * Only held registry datasets are proposed. An external candidate is a
    procurement decision, not evidence, and mapping one would let a thread
    claim an input the desk does not have.
  * Nothing is written. This returns a proposal for a researcher or an agent to
    accept, because a thread that silently acquires inputs is a thread whose
    provenance nobody can reconstruct.
"""

from __future__ import annotations

from typing import Any

# The store treats type=source or layer=evidence as an evidence node.
_NODE_TYPE = "source"
_NODE_LAYER = "evidence"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _readiness(gateway: Any, dataset_id: str) -> dict[str, Any]:
    """Registry truth for one dataset, or nothing. Never a guess."""
    try:
        row = gateway.describe_dataset(dataset_id) or {}
    except Exception:
        return {}
    materialization = row.get("materialization")
    materialization = materialization if isinstance(materialization, dict) else {}
    return {
        "readiness": _text(row.get("readiness")) or _text(materialization.get("readiness")),
        "query_ready": bool(materialization.get("query_ready")),
        "grain": _text(row.get("grain")) or _text(materialization.get("grain")),
        "coverage": _text(row.get("coverage")) or _text(row.get("period")),
    }


def propose_evidence_nodes(gateway: Any, objective: str, *, limit: int = 6) -> dict[str, Any]:
    """Held datasets that answer the objective, shaped as evidence nodes.

    `status` reports what the registry says, not what the thread would like. A
    dataset that is registered but not query-ready is still proposable evidence —
    the researcher needs to see it and its state together, rather than have it
    filtered out silently and wonder why an obvious input never appeared.
    """
    question = _text(objective)
    if not question:
        return {"objective": "", "nodes": [], "reason": "no objective to map evidence against"}

    try:
        found = gateway.semantic_discover(question, limit=max(1, min(int(limit), 12)))
    except Exception as exc:  # retrieval failure must not read as "no evidence exists"
        return {
            "objective": question,
            "nodes": [],
            "reason": f"evidence retrieval failed ({type(exc).__name__}); this is not a finding of no evidence",
        }

    rows = found.get("results") or found.get("rows") or []
    nodes: list[dict[str, Any]] = []
    for row in rows:
        dataset_id = _text(row.get("dataset_id"))
        if not dataset_id:
            continue
        facts = _readiness(gateway, dataset_id)
        node: dict[str, Any] = {
            "id": dataset_id,
            "dataset_id": dataset_id,
            "type": _NODE_TYPE,
            "layer": _NODE_LAYER,
            "label": _text(row.get("title")) or dataset_id,
            "status": facts.get("readiness") or "registered",
            "query_ready": facts.get("query_ready", False),
            "proposed_by": "semantic_evidence_map",
        }
        grain = facts.get("grain") or _text(row.get("grain"))
        coverage = facts.get("coverage") or _text(row.get("coverage"))
        if grain:
            node["grain"] = grain
        if coverage:
            node["coverage"] = coverage
        nodes.append(node)

    if not nodes:
        return {
            "objective": question,
            "nodes": [],
            "reason": "no held dataset matched this objective; Discover can look beyond the Library",
        }
    return {
        "objective": question,
        "nodes": nodes,
        "reason": "",
        "review_required": True,
        "writes": False,
    }
