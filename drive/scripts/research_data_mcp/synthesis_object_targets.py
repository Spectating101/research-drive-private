#!/usr/bin/env python3
"""Typed Synthesis object targets shared by Ask stream and buffered chat responses.

The browser already sends the active durable Synthesis thread as ``rail_context``.
This module turns typed backend actions/results into the same stable research-object
identity used by the workstation.  It deliberately does not infer from hidden model
reasoning or arbitrary prose: explicit targets, typed actions/results, and durable
thread state are the only authorities.
"""

from __future__ import annotations

from typing import Any


_SURFACES = {
    "evidence": "synthesis-evidence-state",
    "scope": "synthesis-scope-block",
    "units": "synthesis-unit-conflict",
    "join": "synthesis-join-decision",
    "method": "synthesis-evidence-proposal",
    "proposal": "synthesis-proposal-state",
    "preview": "synthesis-preview-state",
    "execution": "synthesis-execution-state",
    "result": "synthesis-query-ready-state",
}

_LABELS = {
    "evidence": "Evidence map",
    "scope": "Scope decision",
    "units": "Unit decision",
    "join": "Join decision",
    "method": "Method construction",
    "proposal": "Method proposal",
    "preview": "Bounded Preview",
    "execution": "Execution",
    "result": "Query-ready result",
}

_DECISION_KINDS = {
    "map_evidence": "evidence",
    "resolve_scope": "scope",
    "resolve_units": "units",
    "resolve_join": "join",
    "design_method": "method",
    "review_recommendation": "method",
    "review_proposal": "proposal",
    "run_preview": "preview",
    "recover_preview": "preview",
    "review_preview": "preview",
    "approve_execution": "execution",
    "review_execution": "execution",
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return _clean(value).lower().replace("-", "_").replace(" ", "_")


def _synthesis_scope(rail_context: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any], str]:
    rail = _dict(rail_context)
    entity = _dict(rail.get("entity"))
    selected = _dict(rail.get("selected"))
    is_synthesis = _norm(rail.get("tab")) == "synthesis" or _norm(entity.get("kind")) == "synthesis_thread"
    if not is_synthesis:
        return {}, {}, ""
    thread_id = _clean(selected.get("thread_id") or rail.get("thread_id") or entity.get("id"))
    return rail, selected, thread_id


def _explicit_target(source: dict[str, Any]) -> dict[str, Any]:
    target = _dict(source.get("target"))
    if target:
        return target
    kind = source.get("object_kind") or source.get("target_kind")
    object_id = source.get("object_id") or source.get("target_id")
    surface = source.get("surface") or source.get("surface_testid") or source.get("target_surface")
    if kind or object_id or surface:
        return {
            "kind": kind,
            "object_id": object_id,
            "surface": surface,
            "label": source.get("object_label") or source.get("target_label"),
        }
    return {}


def _kind_from_surface(surface: Any) -> str:
    value = _clean(surface)
    if value.startswith('[data-testid="') and value.endswith('"]'):
        value = value[len('[data-testid="') : -2]
    for kind, test_id in _SURFACES.items():
        if value == test_id:
            return kind
    return ""


def _typed_kind(action: str, source: dict[str, Any], selected: dict[str, Any]) -> str:
    artifacts = _dict(source.get("artifacts"))
    payload = {**artifacts, **source}
    action_n = _norm(action or source.get("action") or artifacts.get("action"))

    # Durable result shapes outrank broad action labels such as ``queue``.
    proposal = _dict(payload.get("synthesis_proposal") or payload.get("proposal"))
    if proposal or payload.get("proposal_recorded"):
        return "proposal"
    preview = _dict(payload.get("preview"))
    if preview and (preview.get("spec_hash") or preview.get("authority_hash") or preview.get("bounded") is not None):
        return "preview"
    job = _dict(payload.get("job"))
    plan = _dict(payload.get("plan")) or _dict(job.get("plan"))
    if _norm(plan.get("job_type")) == "synthesis_execute":
        return "execution"
    if payload.get("registration_id") or payload.get("registered_dataset_id") or payload.get("query_ready"):
        return "result"

    if any(token in action_n for token in ("registry", "register", "query_ready", "library_handoff")):
        return "result"
    if "proposal" in action_n or "accepted_method" in action_n:
        return "proposal"
    if "preview" in action_n or "bounded_test" in action_n:
        return "preview"
    if any(token in action_n for token in ("execute", "execution", "approval", "authoriz", "materialis", "materializ", "build")):
        return "execution"
    if "join" in action_n or "key_overlap" in action_n or "fanout" in action_n:
        return "join"
    if "scope" in action_n or "row_limit" in action_n or "population" in action_n:
        return "scope"
    if "unit" in action_n or "rescal" in action_n:
        return "units"
    if "method" in action_n or "construction" in action_n or "transform" in action_n:
        return "method"
    if "evidence" in action_n or "measure" in action_n or "schema" in action_n:
        return "evidence"

    selected_object = _dict(_dict(selected.get("synthesis_object_context")))
    if action_n in {"contextual", "synthesis_reasoning", "composer", ""} and selected_object.get("kind"):
        return _norm(selected_object.get("kind"))

    decision_kind = _norm(selected.get("decision_kind"))
    if decision_kind in _DECISION_KINDS:
        return _DECISION_KINDS[decision_kind]
    if _norm(selected.get("synthesis_stage")) == "result":
        return "result"
    return ""


def _source_id(kind: str, source: dict[str, Any]) -> str:
    artifacts = _dict(source.get("artifacts"))
    payload = {**artifacts, **source}
    proposal = _dict(payload.get("synthesis_proposal") or payload.get("proposal"))
    preview = _dict(payload.get("preview"))
    job = _dict(payload.get("job"))
    materialized = _dict(payload.get("materialized"))

    if kind == "proposal":
        return _clean(proposal.get("id") or payload.get("proposal_id") or proposal.get("proposal_hash") or payload.get("proposal_hash"))
    if kind == "preview":
        return _clean(preview.get("spec_hash") or preview.get("authority_hash") or payload.get("preview_spec_hash"))
    if kind == "execution":
        return _clean(job.get("id") or job.get("job_id") or payload.get("job_id") or payload.get("run_id"))
    if kind == "result":
        return _clean(
            payload.get("output_dataset_id")
            or payload.get("registered_dataset_id")
            or materialized.get("dataset_id")
            or payload.get("registration_id")
        )
    if kind == "method":
        return _clean(payload.get("accepted_spec_hash") or proposal.get("proposal_hash") or proposal.get("id"))
    return ""


def _durable_id(kind: str, selected: dict[str, Any], thread_id: str) -> str:
    if kind == "proposal":
        return _clean(selected.get("proposal_id") or selected.get("proposal_hash")) or (f"{thread_id}:proposal" if thread_id else "")
    if kind == "preview":
        return _clean(selected.get("preview_spec_hash") or selected.get("accepted_spec_hash")) or (f"{thread_id}:preview" if thread_id else "")
    if kind == "execution":
        return _clean(selected.get("job_id") or selected.get("run_id")) or (f"{thread_id}:execution" if thread_id else "")
    if kind == "result":
        return _clean(selected.get("output_dataset_id") or selected.get("registration_id")) or (f"{thread_id}:result" if thread_id else "")
    if kind == "method":
        return _clean(selected.get("accepted_spec_hash") or selected.get("proposal_id") or selected.get("proposal_hash")) or (f"{thread_id}:method" if thread_id else "")
    return f"{thread_id}:{kind}" if thread_id else ""


def synthesis_target(
    rail_context: dict[str, Any] | None,
    source: dict[str, Any] | None = None,
    *,
    action: str = "",
) -> dict[str, Any] | None:
    """Return an exact workstation object target for one typed backend event/result."""

    rail, selected, thread_id = _synthesis_scope(rail_context)
    if not rail:
        return None
    row = _dict(source)
    explicit = _explicit_target(row)
    explicit_kind = _norm(explicit.get("kind")) or _kind_from_surface(explicit.get("surface"))
    kind = explicit_kind or _typed_kind(action, row, {**selected, "synthesis_object_context": rail.get("synthesis_object_context")})
    if kind not in _SURFACES:
        return None

    selected_object = _dict(rail.get("synthesis_object_context"))
    explicit_id = _clean(explicit.get("object_id") or explicit.get("id"))
    selected_object_id = _clean(selected_object.get("object_id")) if _norm(selected_object.get("kind")) == kind else ""
    object_id = explicit_id or _source_id(kind, row) or selected_object_id or _durable_id(kind, selected, thread_id)
    surface = _clean(explicit.get("surface") or selected_object.get("surface")) if _norm(selected_object.get("kind")) == kind else _clean(explicit.get("surface"))
    if not surface:
        surface = _SURFACES[kind]
    label = _clean(explicit.get("label"))
    if not label and _norm(selected_object.get("kind")) == kind:
        label = _clean(selected_object.get("label"))
    if not label:
        label = _LABELS[kind]

    return {
        "kind": kind,
        "object_id": object_id or None,
        "label": label,
        "thread_id": thread_id or None,
        "surface": surface,
    }


def attach_synthesis_target(
    event: dict[str, Any], rail_context: dict[str, Any] | None
) -> dict[str, Any]:
    """Copy an event and attach typed target metadata when Synthesis is active."""

    row = dict(event or {})
    target = synthesis_target(rail_context, row, action=_clean(row.get("action")))
    if target:
        row["target"] = target
    return row


def activity_receipt(event: dict[str, Any]) -> dict[str, Any] | None:
    """Return the bounded, transport-safe observable receipt for buffered Ask."""

    row = _dict(event)
    target = _dict(row.get("target"))
    text = _clean(row.get("text"))
    if not target or not text or row.get("type") not in {"activity", "progress"}:
        return None
    return {
        "type": "activity",
        "text": text[:500],
        "action": _clean(row.get("action")) or None,
        "elapsed_seconds": row.get("elapsed_seconds"),
        "target": target,
    }
