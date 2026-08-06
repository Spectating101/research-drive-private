#!/usr/bin/env python3
"""Vault-wide meaning contract — show vs store vs match.

Show (Library / rail / Synthesis face):
  title, description, recommended_use

Store (same registry row; not required in list UI):
  aliases[], keywords[], meaning_about

Handle (never the faculty face):
  dataset_id

Matching (Discover / Library search / Ask / Synthesis) reads show + store.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

MEANING_SHOW_KEYS = ("title", "display_name", "description", "recommended_use")
MEANING_STORE_KEYS = ("aliases", "keywords", "meaning_about")

_OPS_FACE_RE = re.compile(
    r"^(?:Custom collect|Route prove|Synthesis)\b|"
    r"dataset_id\s+craft_|Using the Library asset",
    re.IGNORECASE,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_ops_face(text: str, *, allow_long: bool = False) -> bool:
    s = str(text or "").strip()
    if not s:
        return True
    if _OPS_FACE_RE.search(s):
        return True
    if not allow_long and len(s) > 96:
        return True
    if s.startswith("data_lake/") or "Inspect files under" in s:
        return True
    return False


def normalize_meaning_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate / clamp an AI meaning proposal. dataset_id is never taken from AI."""
    title = re.sub(r"\s+", " ", str(raw.get("title") or "").strip())[:80]
    description = re.sub(r"\s+", " ", str(raw.get("description") or "").strip())[:420]
    recommended = re.sub(r"\s+", " ", str(raw.get("recommended_use") or "").strip())[:200]
    about = re.sub(r"\s+", " ", str(raw.get("meaning_about") or raw.get("about") or "").strip())[:800]

    aliases: list[str] = []
    for item in raw.get("aliases") or []:
        a = re.sub(r"\s+", " ", str(item or "").strip())
        if a and a.lower() not in {x.lower() for x in aliases} and len(a) <= 80:
            aliases.append(a)
        if len(aliases) >= 12:
            break

    keywords: list[str] = []
    for item in raw.get("keywords") or []:
        k = re.sub(r"\s+", " ", str(item or "").strip().lower())
        if k and k not in keywords and 2 <= len(k) <= 48:
            keywords.append(k)
        if len(keywords) >= 24:
            break

    if not title or is_ops_face(title):
        raise ValueError("meaning title missing or still ops jargon")
    if not description or is_ops_face(description, allow_long=True):
        raise ValueError("meaning description missing or still ops jargon")

    # Ensure title itself is findable via aliases
    if title.lower() not in {a.lower() for a in aliases}:
        aliases = [title, *aliases][:12]

    return {
        "title": title,
        "display_name": title,
        "description": description,
        "recommended_use": recommended or description[:160],
        "aliases": aliases,
        "keywords": keywords,
        "meaning_about": about or description,
    }


def apply_meaning_to_row(
    row: dict[str, Any],
    meaning: dict[str, Any],
    *,
    labeled_by: str,
    model: str = "",
) -> dict[str, Any]:
    """Write show+store fields; keep dataset_id; park old ops name under ops_title."""
    out = dict(row)
    did = str(out.get("dataset_id") or "").strip()
    if not did:
        raise ValueError("registry row missing dataset_id")

    old_name = str(out.get("name") or out.get("title") or "").strip()
    if old_name and is_ops_face(old_name):
        out.setdefault("ops_title", old_name[:240])

    clean = normalize_meaning_payload(meaning)
    out["title"] = clean["title"]
    out["display_name"] = clean["display_name"]
    out["name"] = clean["title"]  # FE / flywheel that still read name
    out["description"] = clean["description"]
    out["recommended_use"] = clean["recommended_use"]
    out["aliases"] = list(clean["aliases"])
    out["keywords"] = list(clean["keywords"])
    out["meaning_about"] = clean["meaning_about"]
    out["meaning"] = {
        "labeled_at": utc_now(),
        "labeled_by": labeled_by,
        "model": model or labeled_by,
        "schema": "vault_meaning_v1",
    }
    out["dataset_id"] = did
    return out


def meaning_match_blob(row: dict[str, Any]) -> str:
    """Text used by search / Discover lexical match — show + store, not ops dumps."""
    parts: list[str] = [
        str(row.get("title") or ""),
        str(row.get("display_name") or ""),
        str(row.get("description") or ""),
        str(row.get("recommended_use") or ""),
        str(row.get("meaning_about") or ""),
        str(row.get("grain") or ""),
        str(row.get("coverage") or ""),
        str(row.get("dataset_id") or ""),
    ]
    for key in ("aliases", "keywords", "tags"):
        vals = row.get(key) or []
        if isinstance(vals, list):
            parts.extend(str(v) for v in vals if v)
    return " ".join(parts).lower()


def faculty_face(row: dict[str, Any]) -> dict[str, Any]:
    """Compact show fields for UI / DESK_FACTS."""
    title = str(
        row.get("display_name") or row.get("title") or row.get("name") or ""
    ).strip()
    if not title or is_ops_face(title):
        title = str(row.get("dataset_id") or "Dataset")
    return {
        "dataset_id": row.get("dataset_id"),
        "title": title,
        "description": str(row.get("description") or "")[:420],
        "recommended_use": str(row.get("recommended_use") or "")[:200],
        "analysis_readiness": row.get("analysis_readiness"),
        "grain": row.get("grain"),
        "coverage": row.get("coverage"),
        "local_ready": row.get("local_ready"),
    }


_CUSTOM_COLLECT_WITH_ID_RE = re.compile(
    r"Custom collect\s*[·:\-—]\s*[^\s(,]+(?:\s*\(dataset_id\s+([a-zA-Z0-9_]+)\))?",
    re.IGNORECASE,
)
_DATASET_ID_PAREN_RE = re.compile(r"\(dataset_id\s+([a-zA-Z0-9_]+)\)", re.IGNORECASE)


def faculty_objective(text: str, faces: dict[str, dict[str, Any]]) -> str:
    """Rewrite durable objectives that still embed ops collect faces."""
    s = str(text or "").strip()
    if not s or not faces:
        return s

    def _custom_sub(match: re.Match[str]) -> str:
        did = str(match.group(1) or "").strip()
        if did and did in faces:
            return str(faces[did].get("title") or did)
        return match.group(0)

    s = _CUSTOM_COLLECT_WITH_ID_RE.sub(_custom_sub, s)

    def _did_sub(match: re.Match[str]) -> str:
        did = str(match.group(1) or "").strip()
        if did and did in faces:
            # Drop the ops parenthetical once the asset is named in prose.
            return ""
        return match.group(0)

    s = _DATASET_ID_PAREN_RE.sub(_did_sub, s)
    return re.sub(r"\s{2,}", " ", s).replace(" ,", ",").strip()


def enrich_synthesis_thread_face(thread: dict[str, Any], describe) -> dict[str, Any]:
    """Overlay vault meaning onto synthesis thread title/nodes for faculty UI.

    ``describe`` is gateway.describe_dataset(dataset_id) -> row dict.
    """
    out = dict(thread or {})
    state = dict(out.get("state") or {})
    exec_spec = state.get("execution_spec") if isinstance(state.get("execution_spec"), dict) else {}
    execution = dict(state.get("execution") or {}) if isinstance(state.get("execution"), dict) else {}
    output_id = str(
        execution.get("output_dataset_id")
        or exec_spec.get("output_dataset_id")
        or ""
    ).strip()
    input_id = str(exec_spec.get("input_dataset_id") or "").strip()

    candidate_ids: list[str] = []
    for did in (input_id, output_id):
        if did:
            candidate_ids.append(did)
    for node in state.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        did = str(node.get("dataset_id") or "").strip()
        if did:
            candidate_ids.append(did)

    faces: dict[str, dict[str, Any]] = {}
    if callable(describe):
        for did in candidate_ids:
            if not did or did in faces:
                continue
            try:
                faces[did] = faculty_face(describe(did))
            except Exception:  # noqa: BLE001
                continue

    if output_id and output_id in faces and is_ops_face(str(out.get("title") or "")):
        out["title"] = faces[output_id]["title"]
        out["faculty_title"] = faces[output_id]["title"]

    nodes = []
    for node in state.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        n = dict(node)
        did = str(n.get("dataset_id") or "").strip()
        # Map placeholder node ids like keeling_accel_monthly → output dataset
        if not did and output_id and str(n.get("id") or "").endswith("accel_monthly"):
            did = output_id
        if did and did in faces:
            n["dataset_id"] = did
            n["title"] = faces[did]["title"]
            n["label"] = faces[did]["title"]
            n["description"] = faces[did].get("description")
        elif did:
            try:
                face = faculty_face(describe(did))
                faces[did] = face
                n["title"] = face["title"]
                n["label"] = face["title"]
                n.setdefault("dataset_id", did)
            except Exception:  # noqa: BLE001
                pass
        nodes.append(n)
    if nodes:
        state["nodes"] = nodes

    for key in ("objective",):
        raw_obj = str(out.get(key) or state.get(key) or "")
        if raw_obj and is_ops_face(raw_obj, allow_long=True):
            faced_obj = faculty_objective(raw_obj, faces)
            if faced_obj and faced_obj != raw_obj:
                out[key] = faced_obj
                state[key] = faced_obj

    if output_id and output_id in faces:
        readiness = str(faces[output_id].get("analysis_readiness") or "").lower()
        if readiness == "query_ready":
            execution["query_ready"] = True
            status = str(execution.get("status") or out.get("materialisation") or "").lower()
            if status in {"", "registered"}:
                execution["status"] = "query_ready"
                out["materialisation"] = "query_ready"
                state["materialisation"] = "query_ready"
                state["maturity"] = "query_ready"
                state["maturityLabel"] = "Query-ready output"
            state["execution"] = execution

    out["state"] = state
    out["vault_faces"] = faces
    return out
