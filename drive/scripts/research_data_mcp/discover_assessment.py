"""Held-evidence assessment for Discover.

This module deliberately assesses catalog evidence, rather than predicting whether
research is "ready".  A catalog row only supports a requirement dimension when
that dimension is explicitly documented in the row's coverage metadata.

Verdicts remain `covered`, `partially_covered`, or `not_covered`. Assessment
status is separate: `insufficient_metadata` means no candidate considered
declared coverage metadata for any requested dimension, so no coverage verdict
can honestly be established. Collapsing that state into `not_covered` would
misrepresent an absence of data as a checked-and-failed result.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import date
from typing import Any


DIMENSIONS = ("unit", "universe/geography", "time_range", "frequency", "fields", "event_type")
_COVERAGE_KEYS = ("coverage_metadata", "evidence_coverage", "coverage", "dimensions")
_DIMENSION_ALIASES = {"universe/geography": ("universe/geography", "universe", "geography")}
_DIMENSION_LABELS = {
    "unit": "unit of observation",
    "universe/geography": "geography or universe",
    "time_range": "time range",
    "frequency": "frequency",
    "fields": "required fields",
    "event_type": "event type",
}


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        return [item for item in (_clean(item) for item in value) if item is not None]
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            normalized = _clean(item)
            if normalized is not None:
                cleaned[str(key)] = normalized
        return cleaned
    return value


def _label(dimension: str) -> str:
    return _DIMENSION_LABELS.get(dimension, dimension.replace("_", " "))


def _display(value: Any) -> str:
    if isinstance(value, dict) and ("start" in value or "end" in value):
        start = value.get("start") or "unspecified"
        end = value.get("end") or "unspecified"
        return f"{start}–{end}"
    if isinstance(value, list):
        return ", ".join(_display(item) for item in value)
    return str(value).replace("_", " ")


def normalize_requirement(requirement: Any) -> dict[str, dict[str, Any]]:
    """Normalize caller input and fill only explicit, deterministic question drafts."""
    source = requirement if isinstance(requirement, dict) else {}
    needs_draft = any(
        next(
            (source.get(key) for key in _DIMENSION_ALIASES.get(dimension, (dimension,)) if source.get(key) is not None),
            None,
        ) is None
        for dimension in DIMENSIONS
    )
    drafted = draft_requirement_from_question(str(source.get("question") or "")) if needs_draft else {}
    normalized: dict[str, dict[str, Any]] = {}
    for dimension in DIMENSIONS:
        incoming = next(
            (source.get(key) for key in _DIMENSION_ALIASES.get(dimension, (dimension,)) if source.get(key) is not None),
            None,
        )
        if (
            incoming is None
            or (isinstance(incoming, dict) and _clean(incoming.get("value")) is None)
        ) and dimension in drafted:
            incoming = drafted[dimension]
        if isinstance(incoming, dict):
            value = _clean(incoming.get("value"))
            provenance = str(incoming.get("provenance") or ("explicit" if value is not None else "unspecified"))
        else:
            value = _clean(incoming)
            provenance = "explicit" if value is not None else "unspecified"
        if provenance not in {"explicit", "drafted", "unspecified"}:
            provenance = "explicit" if value is not None else "unspecified"
        normalized[dimension] = {"value": value, "provenance": provenance}
    return normalized


_INTERPRET_REQUIREMENT_PROMPT = """Extract only explicit or clearly implied research requirements from this question:
{question}

Return one JSON object and no prose. Use only these keys:
unit, universe/geography, time_range, frequency, fields, event_type.

Values must be strings, arrays of strings, or for time_range an object with
optional string keys start and end. Omit a key when the question does not
establish it. Do not infer proxies, data sources, access, coverage, or a
research conclusion.
"""


def _run_requirement_model(prompt: str, *, timeout: float = 12.0) -> str:
    """Use the configured agent for research interpretation; no heuristic fallback."""
    binary = shutil.which("cursor-agent")
    if not binary:
        raise RuntimeError("cursor-agent is not installed")
    environment = dict(os.environ)
    if not environment.get("CURSOR_API_KEY"):
        raise RuntimeError("CURSOR_API_KEY is not configured")
    try:
        completed = subprocess.run(
            [
                binary,
                "-p",
                prompt,
                "--model",
                environment.get("RD_REQUIREMENT_MODEL", "composer-2.5"),
                "--output-format",
                "text",
                "--mode",
                "ask",
                "--sandbox",
                "enabled",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=environment,
            cwd="/tmp",
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(str(exc)) from exc
    if completed.returncode:
        raise RuntimeError((completed.stderr or completed.stdout or f"exit {completed.returncode}")[:240])
    return completed.stdout


def draft_requirement_from_question(question: str) -> dict[str, dict[str, Any]]:
    """Ask the model to draft requirements, preserving unknowns rather than guessing."""
    try:
        candidate = json.loads(_run_requirement_model(_INTERPRET_REQUIREMENT_PROMPT.format(question=str(question or "").strip())))
    except (RuntimeError, ValueError, TypeError):
        return {}
    if not isinstance(candidate, dict):
        return {}
    drafted: dict[str, dict[str, Any]] = {}
    for dimension in DIMENSIONS:
        value = _clean(candidate.get(dimension))
        if value is not None and isinstance(value, (str, list, dict)):
            drafted[dimension] = {"value": value, "provenance": "drafted"}
    return drafted


def _coverage_claims(row: dict[str, Any]) -> dict[str, list[Any]]:
    """Read only explicit coverage declarations; legacy labels are not coverage."""
    claims: dict[str, list[Any]] = {}
    for key in _COVERAGE_KEYS:
        candidate = row.get(key)
        if not isinstance(candidate, dict):
            continue
        for dimension in DIMENSIONS:
            for key in _DIMENSION_ALIASES.get(dimension, (dimension,)):
                if key in candidate and candidate[key] not in (None, "", [], {}):
                    claims.setdefault(dimension, []).append(_clean(candidate[key]))
    # These row-level fields are structured catalog metadata, unlike a free-text
    # description or a broad `field_coverage: query-ready` label.
    for dimension in DIMENSIONS:
        for key in _DIMENSION_ALIASES.get(dimension, (dimension,)):
            if key in row and row[key] not in (None, "", [], {}):
                claims.setdefault(dimension, []).append(_clean(row[key]))
    return claims


def _coverage(row: dict[str, Any]) -> dict[str, Any]:
    return {dimension: values[0] for dimension, values in _coverage_claims(row).items() if values}


def _coverage_conflicts(row: dict[str, Any]) -> dict[str, list[Any]]:
    conflicts: dict[str, list[Any]] = {}
    for dimension, values in _coverage_claims(row).items():
        distinct = {_canonical_claim(value, dimension) for value in values}
        if len(distinct) > 1:
            conflicts[dimension] = values
    return conflicts


def evidence_state(row: dict[str, Any]) -> dict[str, Any]:
    """Preserve legacy readiness signals while expressing their ambiguity."""
    materialization = row.get("materialization") if isinstance(row.get("materialization"), dict) else {}
    query_smoke = row.get("query_smoke") if isinstance(row.get("query_smoke"), dict) else {}
    readiness = _clean(row.get("analysis_readiness") or row.get("readiness"))
    materialized_ready = materialization.get("query_ready")
    legacy = {
        key: row.get(key)
        for key in ("analysis_readiness", "readiness", "field_coverage", "collection_status")
        if row.get(key) is not None
    }
    if materialized_ready is not None:
        legacy["materialization.query_ready"] = materialized_ready
    if query_smoke.get("ok") is not None:
        legacy["query_smoke.ok"] = query_smoke.get("ok")

    coverage = _coverage(row)
    conflicts = _coverage_conflicts(row)
    coverage_state = (
        {
            "status": "conflicting" if conflicts else "documented",
            "basis": "contradictory explicit catalog coverage metadata" if conflicts else "explicit catalog coverage metadata",
            "dimensions": sorted(coverage),
            "conflicts": conflicts,
        }
        if coverage
        else {"status": "unknown", "basis": "no explicit requirement coverage metadata", "dimensions": []}
    )
    # These are intentionally distinct claims.  For example, a metadata label
    # saying `instant` is not a claim that every requested field is covered.
    return {
        "materialization": (
            {"status": "verified", "basis": "observed query proof"}
            if (
                materialization.get("query_verified") is True
                or materialization.get("query_smoke_passed") is True
                or query_smoke.get("ok") is True
            )
            else {"status": "query_ready_declared", "basis": "materialization.query_ready"}
            if materialized_ready is True
            else {"status": "unavailable", "basis": "materialization.query_ready is false"}
            if materialized_ready is False
            else {"status": "unknown", "basis": "no materialization query evidence"}
        ),
        "analysis_readiness": {"status": "declared" if readiness else "unknown", "value": readiness},
        "access": {
            "status": "declared" if row.get("source_access_mode") or row.get("access_shape") else "unknown",
            "value": row.get("source_access_mode") or row.get("access_shape"),
        },
        "field_coverage": {
            "status": "declared" if row.get("field_coverage") is not None else "unknown",
            "value": row.get("field_coverage"),
        },
        "coverage": coverage_state,
        "legacy": legacy,
    }


def _fold(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("_", " ").replace("-", " ").split())


def _canonical_claim(value: Any, dimension: str) -> Any:
    if dimension == "fields":
        values = value if isinstance(value, list) else [value]
        return tuple(sorted({_fold(item) for item in values}))
    if dimension == "time_range" and isinstance(value, dict):
        return (
            _date_boundary(value.get("start"), end=False),
            _date_boundary(value.get("end"), end=True),
        )
    if isinstance(value, dict):
        return tuple(
            sorted(
                (str(key), _canonical_claim(item, dimension))
                for key, item in value.items()
            )
        )
    if isinstance(value, list):
        return tuple(sorted(_fold(item) for item in value))
    return _fold(value)


def _date_boundary(value: Any, *, end: bool) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) == 4 and text.isdigit() and text.startswith(("19", "20")):
        year = int(text)
        return date(year, 12, 31) if end else date(year, 1, 1)
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _matches(required: Any, held: Any, dimension: str) -> bool:
    if dimension == "fields":
        required_values = required if isinstance(required, list) else [required]
        held_values = held if isinstance(held, list) else [held]
        held_folded = {_fold(item) for item in held_values}
        return all(_fold(item) in held_folded for item in required_values)
    if dimension == "time_range" and isinstance(required, dict) and isinstance(held, dict):
        requested_start = _date_boundary(required.get("start"), end=False)
        requested_end = _date_boundary(required.get("end"), end=True)
        held_start = _date_boundary(held.get("start"), end=False)
        held_end = _date_boundary(held.get("end"), end=True)
        if held_start is None or held_end is None or held_start > held_end:
            return False
        if requested_start and requested_end and requested_start > requested_end:
            return False
        return bool(
            (requested_start is None or held_start <= requested_start)
            and (requested_end is None or held_end >= requested_end)
        )
    required_values = required if isinstance(required, list) else [required]
    held_values = held if isinstance(held, list) else [held]
    return all(any(_fold(want) == _fold(got) for got in held_values) for want in required_values)


def _record(row: dict[str, Any], requirements: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str]]:
    state = evidence_state(row)
    coverage = _coverage(row)
    dimension_results: dict[str, str] = {}
    for dimension, requirement in requirements.items():
        wanted = requirement["value"]
        if wanted is None:
            continue
        if dimension in state["coverage"].get("conflicts", {}):
            dimension_results[dimension] = "conflicting"
        elif dimension not in coverage:
            dimension_results[dimension] = "unknown"
        elif not _matches(wanted, coverage[dimension], dimension):
            dimension_results[dimension] = "mismatch"
        elif state["materialization"]["status"] == "verified":
            dimension_results[dimension] = "supported"
        else:
            dimension_results[dimension] = "unverified"
    supported = [dim for dim, value in dimension_results.items() if value == "supported"]
    matched_unverified = [dim for dim, value in dimension_results.items() if value == "unverified"]
    constrained = [(dim, value) for dim, value in dimension_results.items() if value != "supported"]
    if supported:
        contribution = "Supports " + ", ".join(_label(dim) for dim in supported)
    elif matched_unverified:
        contribution = "Documented match, but usability is unverified: " + ", ".join(
            _label(dim) for dim in matched_unverified
        )
    else:
        contribution = "No documented support for the requested dimensions"
    limitations = (
        [f"{_label(dim)}: {value.replace('_', ' ')}" for dim, value in constrained]
        if constrained
        else [str(row.get("limitations") or "No additional catalog limitation recorded")]
    )
    title = row.get("title") or row.get("name") or row.get("dataset_id") or row.get("id")
    return (
        {
            "dataset_id": row.get("dataset_id") or row.get("id"),
            "title": title,
            "name": title,
            "contribution": contribution,
            "limitations": limitations,
            "evidence_state": state,
        },
        dimension_results,
    )


def _gap(dimension: str, requirement: dict[str, Any], status: str) -> dict[str, Any]:
    value = requirement["value"]
    if status == "unknown":
        action = "Document held coverage for this requirement dimension before treating it as support."
    elif status == "conflicting":
        action = "Resolve the contradictory explicit coverage metadata or obtain a verified extract."
    else:
        action = "Locate or collect evidence that explicitly covers this requirement dimension."
    statement = f"Held evidence does not establish the required {_label(dimension)} ({_display(value)})."
    return {
        "dimension": dimension,
        "required": value,
        "status": status,
        "statement": statement,
        "blocks": statement,
        "action": action,
        "resolution_evidence": ["Explicit catalog coverage metadata", "Observed successful query proof"],
    }


def assess_held_evidence(gateway: Any, *, question: str, requirement: Any = None, limit: int = 100) -> dict[str, Any]:
    """Assess declared catalog evidence after explicit or model-drafted requirements."""
    question = str(question or "").strip()
    if not question:
        raise ValueError("question is required")
    # Caller-provided values remain authoritative. Missing dimensions are model-
    # drafted only when available; no deterministic vocabulary fills the gaps.
    normalized = normalize_requirement({**(requirement if isinstance(requirement, dict) else {}), "question": question})
    result = gateway.list_datasets(q=question, limit=max(1, min(int(limit or 100), 200)))
    rows = result.get("datasets") if isinstance(result, dict) else []
    if not isinstance(rows, list):
        rows = []

    requested = {dim: item for dim, item in normalized.items() if item["value"] is not None}
    assessed: list[tuple[dict[str, Any], dict[str, str]]] = []
    for row in rows:
        if isinstance(row, dict):
            assessed.append(_record(row, normalized))

    dimension_status: dict[str, str] = {}
    for dimension in requested:
        statuses = [per_dimension.get(dimension, "unknown") for _, per_dimension in assessed]
        if "supported" in statuses:
            dimension_status[dimension] = "supported"
        elif "conflicting" in statuses:
            dimension_status[dimension] = "conflicting"
        elif "unverified" in statuses:
            dimension_status[dimension] = "unverified"
        elif "mismatch" in statuses:
            dimension_status[dimension] = "not_supported"
        else:
            dimension_status[dimension] = "unknown"

    supported_count = sum(state == "supported" for state in dimension_status.values())
    compatible_records = [
        record
        for record, per_dimension in assessed
        if requested and all(per_dimension.get(dimension) == "supported" for dimension in requested)
    ]
    distributed_support = bool(requested and supported_count == len(requested) and not compatible_records)
    uncertain_states = {"unknown", "conflicting", "unverified"}
    has_uncertainty = any(
        state in uncertain_states for state in dimension_status.values()
    )
    # A dimension can fail to match for two different reasons, and conflating them
    # produces a dishonest verdict: either (a) some candidate explicitly declared
    # coverage and it didn't satisfy the requirement (a real negative finding), or
    # (b) no candidate declared coverage metadata for that dimension at all (the
    # catalog never recorded the fact, so nothing was actually checked). `cannot
    # assess` names case (b) instead of reporting it as `not_covered`, which would
    # imply a check happened and failed.
    all_dimensions_undeclared = bool(requested) and all(
        state == "unknown" for state in dimension_status.values()
    )
    if not requested:
        assessment_status = "insufficient_requirement"
        verdict = None
    elif all_dimensions_undeclared or has_uncertainty or distributed_support:
        assessment_status = "insufficient_metadata"
        verdict = None
    elif compatible_records:
        assessment_status = "assessed"
        verdict = "covered"
    elif supported_count:
        assessment_status = "assessed"
        verdict = "partially_covered"
    else:
        assessment_status = "assessed"
        verdict = "not_covered"

    held = [
        record
        for record, dimensions in assessed
        if {"supported", "unverified", "conflicting"} & set(dimensions.values())
    ]
    if verdict != "covered":
        gap_dimension = next((dim for dim, state in dimension_status.items() if state != "supported"), None)
        gap = _gap(gap_dimension, requested[gap_dimension], dimension_status[gap_dimension]) if gap_dimension else (
            {
                "dimension": "assembly",
                "required": sorted(requested),
                "status": "unknown",
                "statement": "No single held record establishes compatible coverage across all stated dimensions.",
                "blocks": "The evidence is distributed across records; its compatibility and joinability are unknown.",
                "action": "Establish compatible keys, timing, and assembly evidence in Synthesis before relying on the combined records.",
                "resolution_evidence": ["Compatible join keys", "Aligned time grain", "Observed assembled-query proof"],
            }
            if distributed_support
            else {
                "dimension": "requirement",
                "required": None,
                "status": "unspecified",
                "statement": "No assessable requirement dimension was supplied.",
                "blocks": "The requirement is unspecified.",
                "action": "State at least one research requirement dimension to assess held coverage.",
                "resolution_evidence": ["An explicit requirement dimension"],
            }
        )
    else:
        gap = None

    # Candidates that were actually considered but never declared coverage for any
    # requested dimension — these are the specific rows a curator could fix, as
    # opposed to a vague instruction to "collect more evidence".
    uncovered_candidate_ids = (
        sorted(
            {
                record.get("dataset_id")
                for record, per_dimension in assessed
                if record.get("dataset_id")
                and requested
                and all(
                    per_dimension.get(dimension, "unknown") == "unknown"
                    for dimension in requested
                )
            }
        )
        if assessment_status == "insufficient_metadata"
        else []
    )

    if assessment_status == "insufficient_requirement":
        because = "No explicit research requirement dimensions were supplied, so held coverage cannot be established."
    elif verdict == "covered":
        because = "One held catalog record explicitly documents verified support for every stated requirement dimension."
    elif verdict == "partially_covered":
        because = "Held evidence supports some stated dimensions, but at least one dimension is missing, unknown, or conflicting."
    elif assessment_status == "insufficient_metadata":
        if distributed_support:
            because = (
                "Requested dimensions are documented across different held records, "
                "but no single compatible assembled record has been verified."
            )
        elif "conflicting" in dimension_status.values():
            because = (
                "Explicit held-coverage declarations conflict, so the requirement "
                "cannot be assessed until the catalog evidence is reconciled."
            )
        elif "unverified" in dimension_status.values():
            because = (
                "A held record declares a matching dimension, but observed query "
                "proof is missing; this is not evidence that the requirement is unmet."
            )
        else:
            because = (
                "No catalog record considered declares coverage metadata for one or "
                "more requested dimensions. This is a catalog evidence gap, not a "
                "checked negative finding."
            )
    else:
        because = "At least one held catalog record declares coverage for a requested dimension, and it does not satisfy the requirement."
    return {
        "question": question,
        "requirement": normalized,
        "assessment_status": assessment_status,
        "verdict": verdict,
        "because": because,
        "held_evidence": held,
        "gap": gap,
        "assessment_basis": {
            "mode": "declared_catalog_metadata",
            "catalog_candidates_considered": len(assessed),
            "dimension_status": dimension_status,
            "compatible_record_ids": [record.get("dataset_id") for record in compatible_records],
            "uncovered_candidate_ids": uncovered_candidate_ids,
            "assembly_status": "unknown" if distributed_support else "not_needed" if compatible_records else "not_established",
            "rule": "Only explicit coverage metadata plus verified materialization supports a dimension; readiness, access, and field labels remain distinct declared evidence.",
        },
    }
