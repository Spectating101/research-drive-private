#!/usr/bin/env python3
"""Ground selected Library assets for desk Ask / Composer turns.

Canonical registry readiness wins over model guesswork. When a selected asset is
registered or query-ready, replies and next-actions must not invent "readiness
unknown" or offer DOI collection for that existing holding. Facts that are
absent stay unknown — this module does not fabricate archive proof.
"""

from __future__ import annotations

import re
from typing import Any

_QUERY_READY = frozenset({"query_ready", "instant"})
_REGISTERED = frozenset({"registered", "query_ready", "instant"})

_DOI_COLLECT_RE = re.compile(
    r"(?i)\b(?:queue\s+)?doi\s+collect(?:ion)?\b|\bcollect\s+(?:via\s+)?doi\b|\bdatacite\s+collect\b"
)
_DOI_COLLECT_SENTENCE_RE = re.compile(
    r"(?i)(?:\s*(?:you\s+could|next,?|then,?)?\s*"
    r"(?:queue\s+)?doi\s+collect(?:ion)?[^.\n!?]*[.?!]?)"
)
_READINESS_UNKNOWN_RE = re.compile(
    r"(?i)\breadiness\s*(?:is|:)?\s*unknown\b|\breadiness\s*:\s*unknown\b|\bunknown\s+readiness\b"
)
_DOI_PROMPT_RE = re.compile(r"(?i)\b(?:queue\s+)?doi\s+collect\b|\bcollect\s+.*\bdoi\b|\bdatacite\b")


def normalize_canonical_readiness(raw: Any) -> str:
    text = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return ""
    if text in _QUERY_READY or text in {"queryready", "ready", "instant_query_ready"}:
        return "query_ready"
    if "query" in text and "ready" in text:
        return "query_ready"
    if text == "registered":
        return "registered"
    return text


def is_query_ready(readiness: Any) -> bool:
    return normalize_canonical_readiness(readiness) == "query_ready"


def is_registered_or_ready(readiness: Any) -> bool:
    return normalize_canonical_readiness(readiness) in {"registered", "query_ready"}


def selected_dataset_id(rail_context: dict[str, Any] | None) -> str:
    rail = rail_context if isinstance(rail_context, dict) else {}
    dataset_id = str(rail.get("dataset_id") or "").strip()
    if dataset_id:
        return dataset_id
    entity = rail.get("entity") if isinstance(rail.get("entity"), dict) else {}
    if str(entity.get("kind") or "") == "dataset":
        return str(entity.get("id") or "").strip()
    return ""


def _tri_state(value: Any) -> bool | None:
    if value is True:
        return True
    if value is False:
        return False
    return None


def ground_from_dataset_row(row: dict[str, Any] | None, *, dataset_id: str = "") -> dict[str, Any]:
    """Build grounding facts from a registry/describe row. Absent facts stay unknown."""
    spec = dict(row or {})
    did = str(spec.get("dataset_id") or dataset_id or "").strip()
    raw_readiness = (
        spec.get("analysis_readiness")
        or spec.get("readiness")
        or spec.get("lifecycle")
        or ""
    )
    canonical = normalize_canonical_readiness(raw_readiness)
    name = str(spec.get("name") or spec.get("title") or spec.get("display_name") or did).strip()
    backend = str(spec.get("backend") or "").strip()

    authority = spec.get("authority") if isinstance(spec.get("authority"), dict) else {}
    reconciliation = (
        spec.get("catalog_reconciliation") if isinstance(spec.get("catalog_reconciliation"), dict) else {}
    )
    receipt = spec.get("registration_receipt") if isinstance(spec.get("registration_receipt"), dict) else {}

    archive_verified = _tri_state(
        spec.get("archive_verified")
        if "archive_verified" in spec
        else authority.get("archive_verified")
        if "archive_verified" in authority
        else receipt.get("archive_verified")
        if "archive_verified" in receipt
        else None
    )
    registry_readback = _tri_state(
        spec.get("registry_readback")
        if "registry_readback" in spec
        else authority.get("registry_readback")
        if "registry_readback" in authority
        else receipt.get("registry_readback")
        if "registry_readback" in receipt
        else None
    )
    if "registry_row_loaded" in reconciliation:
        registry_row_loaded = bool(reconciliation.get("registry_row_loaded"))
    else:
        registry_row_loaded = bool(did) and spec.get("backend") != "registered_asset_receipt"

    identity = {
        "dataset_id": did,
        "name": name,
        "backend": backend or None,
    }
    proof = {
        "registry_row_loaded": registry_row_loaded,
        "archive_verified": archive_verified,
        "registry_readback": registry_readback,
    }
    actions = valid_next_actions(canonical, dataset_id=did)
    return {
        "dataset_id": did,
        "analysis_readiness": str(raw_readiness or "").strip() or None,
        "canonical_readiness": canonical or None,
        "asset_identity": identity,
        "registry_proof": proof,
        "valid_next_actions": actions,
        "query_ready": canonical == "query_ready",
        "registered_or_ready": canonical in {"registered", "query_ready"},
    }


def valid_next_actions(readiness: Any, *, dataset_id: str = "") -> list[str]:
    _ = dataset_id
    canonical = normalize_canonical_readiness(readiness)
    if canonical == "query_ready":
        return ["preview_rows", "query_sample", "ask_about"]
    if canonical == "registered":
        return ["hydrate", "describe", "ask_about"]
    # Facts absent — keep discover/procure options available.
    return ["ask_about", "search_vault", "doi_collect"]


def suggested_prompts_for_asset(dataset_id: str, readiness: Any) -> list[str]:
    did = str(dataset_id or "").strip() or "this dataset"
    canonical = normalize_canonical_readiness(readiness)
    if canonical == "query_ready":
        return [
            f"Query sample rows from {did}",
            f"Describe coverage for {did}",
        ]
    if canonical == "registered":
        return [
            f"Hydrate {did} for querying",
            f"Describe {did}",
        ]
    return [
        f"Search vault for {did}",
        f"Queue DOI collect for {did}",
    ]


def enrich_rail_context(
    rail_context: dict[str, Any] | None,
    row: dict[str, Any] | None,
    *,
    dataset_id: str = "",
) -> dict[str, Any]:
    """Merge grounded asset facts into rail_context for Composer / tools."""
    rail = dict(rail_context or {})
    did = str(dataset_id or selected_dataset_id(rail) or "").strip()
    if not did and not row:
        return rail
    grounding = ground_from_dataset_row(row, dataset_id=did)
    if not grounding.get("dataset_id"):
        return rail

    rail["dataset_id"] = grounding["dataset_id"]
    if grounding.get("canonical_readiness"):
        rail["readiness"] = grounding["canonical_readiness"]
        rail["analysis_readiness"] = grounding.get("analysis_readiness") or grounding["canonical_readiness"]
    rail["asset_identity"] = grounding["asset_identity"]
    rail["registry_proof"] = grounding["registry_proof"]
    rail["valid_next_actions"] = list(grounding["valid_next_actions"])
    if grounding.get("registered_or_ready"):
        rail["actions"] = list(grounding["valid_next_actions"])
    rail["asset_grounding"] = {
        "canonical_readiness": grounding.get("canonical_readiness"),
        "query_ready": grounding.get("query_ready"),
        "registered_or_ready": grounding.get("registered_or_ready"),
    }
    return rail


def resolve_and_enrich_rail_context(gateway: Any, rail_context: dict[str, Any] | None) -> dict[str, Any]:
    """Describe the selected asset when possible and enrich rail_context."""
    rail = dict(rail_context or {})
    did = selected_dataset_id(rail)
    if not did or gateway is None:
        return rail
    try:
        row = gateway.describe_dataset(did)
    except Exception:  # noqa: BLE001 — preserve unknown when lookup fails
        return rail
    if not isinstance(row, dict):
        return rail
    return enrich_rail_context(rail, row, dataset_id=did)


def format_asset_grounding_block(rail_context: dict[str, Any] | None) -> str:
    """Compact grounding block injected into Composer / tool context."""
    rail = rail_context if isinstance(rail_context, dict) else {}
    identity = rail.get("asset_identity") if isinstance(rail.get("asset_identity"), dict) else {}
    proof = rail.get("registry_proof") if isinstance(rail.get("registry_proof"), dict) else {}
    did = str(identity.get("dataset_id") or rail.get("dataset_id") or "").strip()
    if not did:
        return ""

    ag = rail.get("asset_grounding") if isinstance(rail.get("asset_grounding"), dict) else {}
    readiness = normalize_canonical_readiness(
        ag.get("canonical_readiness")
        or rail.get("analysis_readiness")
        or rail.get("readiness")
    )
    lines = ["[Selected asset grounding — authoritative for this turn]"]
    lines.append(
        f"- asset_identity: {did} · {identity.get('name') or did} · {identity.get('backend') or 'unknown'}"
    )
    lines.append(f"- canonical_readiness: {readiness or 'unknown'}")
    if proof:
        lines.append(
            "- registry_proof: "
            f"registry_row_loaded={proof.get('registry_row_loaded')!r} "
            f"archive_verified={proof.get('archive_verified')!r} "
            f"registry_readback={proof.get('registry_readback')!r}"
        )
    actions = rail.get("valid_next_actions") or rail.get("actions") or []
    if isinstance(actions, list) and actions:
        lines.append(f"- valid_next_actions: {', '.join(str(a) for a in actions[:8])}")
    if readiness == "query_ready":
        lines.append(
            "- grounding_rule: Selected asset is query-ready in the lab. "
            "Do not say readiness is unknown. Do not offer DOI collection for this asset."
        )
    elif readiness == "registered":
        lines.append(
            "- grounding_rule: Selected asset is registered. Prefer hydrate/describe over DOI collect."
        )
    return "\n".join(lines) + "\n\n"


def sanitize_suggested_prompts(prompts: list[str] | None, readiness: Any) -> list[str]:
    items = [str(p).strip() for p in (prompts or []) if str(p).strip()]
    if not is_registered_or_ready(readiness):
        return items[:5]
    out: list[str] = []
    for prompt in items:
        if _DOI_PROMPT_RE.search(prompt):
            continue
        out.append(prompt)
    return out[:5]


def sanitize_next_steps(
    steps: list[dict[str, Any]] | None,
    readiness: Any,
) -> list[dict[str, Any]]:
    rows = [dict(s) for s in (steps or []) if isinstance(s, dict)]
    if not is_registered_or_ready(readiness):
        return rows
    out: list[dict[str, Any]] = []
    for step in rows:
        blob = " ".join(str(step.get(k) or "") for k in ("label", "prompt", "kind"))
        if _DOI_PROMPT_RE.search(blob):
            continue
        out.append(step)
    return out


def sanitize_grounded_reply(text: str, readiness: Any, *, dataset_id: str = "") -> str:
    """Strip query-ready conflicts from model/fast-path prose."""
    if not text:
        return text
    canonical = normalize_canonical_readiness(readiness)
    if canonical != "query_ready":
        return text

    out = _READINESS_UNKNOWN_RE.sub(f"readiness: {canonical}", text)
    kept: list[str] = []
    for line in out.splitlines():
        if _DOI_COLLECT_RE.search(line):
            line = _DOI_COLLECT_SENTENCE_RE.sub("", line).strip()
            if not line:
                continue
        kept.append(line)
    cleaned = "\n".join(kept)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    _ = dataset_id
    return cleaned or f"Selected asset readiness: {canonical}."


def grounding_from_rail(rail_context: dict[str, Any] | None) -> dict[str, Any]:
    rail = rail_context if isinstance(rail_context, dict) else {}
    identity = rail.get("asset_identity") if isinstance(rail.get("asset_identity"), dict) else {}
    proof = rail.get("registry_proof") if isinstance(rail.get("registry_proof"), dict) else {}
    return ground_from_dataset_row(
        {
            "dataset_id": selected_dataset_id(rail),
            "name": identity.get("name"),
            "backend": identity.get("backend"),
            "analysis_readiness": rail.get("analysis_readiness") or rail.get("readiness"),
            **(
                {
                    "archive_verified": proof["archive_verified"],
                }
                if "archive_verified" in proof
                else {}
            ),
            **(
                {
                    "registry_readback": proof["registry_readback"],
                }
                if "registry_readback" in proof
                else {}
            ),
            "catalog_reconciliation": {
                "registry_row_loaded": proof.get("registry_row_loaded"),
            }
            if proof
            else {},
        },
        dataset_id=selected_dataset_id(rail),
    )
