"""One model-owned handoff for public, licensed, and webfetch acquisition.

Cursor/Composer (and its webfetch tool) owns the research judgment: which result is
the intended source, whether a page is relevant, and which link should be collected.
This module is deliberately passive.  It validates that explicit choice, attaches a
stable candidate identity and provenance, and routes the choice to an existing plan
builder.  It never searches for a replacement, follows arbitrary page links, or
submits a job.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from scripts.research_data_mcp.candidate_key import candidate_key, canonicalize_url
from scripts.research_data_mcp.discover_collect_plan import resolve_discover_collect_plan
from scripts.research_data_mcp.licensed_sources import inspect_source


_HEX64 = re.compile(r"^[0-9a-f]{64}$", re.I)
_MODEL_AUTHORITIES = frozenset({"cursor_composer", "cursor_webfetch", "composer", "llm"})
_LICENSED = frozenset({"crsp_moveit", "capital_iq_compustat", "compustat", "lseg_edp", "lseg_desktop_rescue"})


def _url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return ""
    if parts.username or parts.password:
        return ""
    return canonicalize_url(raw)


def _link_urls(links: Any) -> list[str]:
    out: list[str] = []
    for item in links or []:
        raw = item.get("url") if isinstance(item, dict) else item
        value = _url(str(raw or ""))
        if value and value not in out:
            out.append(value)
    return out[:100]


def validate_webfetch_handoff(
    *,
    fetched_url: str,
    selected_url: str = "",
    title: str = "",
    provider: str = "",
    candidate_key_value: str = "",
    selection_authority: str = "cursor_webfetch",
    fetched_at: str = "",
    content_sha256: str = "",
    links: list[Any] | None = None,
) -> dict[str, Any]:
    """Validate a Cursor-owned webfetch receipt without performing any fetch."""
    authority = str(selection_authority or "").strip().lower()
    source_url = _url(fetched_url)
    chosen_url = _url(selected_url) if selected_url else source_url
    errors: list[str] = []
    if authority not in _MODEL_AUTHORITIES:
        errors.append("selection_authority must identify Cursor/Composer")
    if not source_url:
        errors.append("fetched_url must be an absolute HTTP(S) URL")
    if not chosen_url:
        errors.append("selected_url must be an absolute HTTP(S) URL")
    link_urls = _link_urls(links)
    if selected_url and chosen_url and chosen_url != source_url and link_urls and chosen_url not in link_urls:
        errors.append("selected_url is not present in the webfetch link evidence")
    digest = str(content_sha256 or "").strip().lower()
    if digest and not _HEX64.fullmatch(digest):
        errors.append("content_sha256 must be a 64-character hexadecimal digest")
    if errors:
        return {
            "ok": False,
            "status": "invalid_webfetch_handoff",
            "errors": errors,
            "selection_authority": authority or None,
            "side_effects": "none",
        }
    candidate = {
        "kind": "live_candidate",
        "provider": provider or (urlsplit(chosen_url).hostname or "webfetch"),
        "title": str(title or chosen_url)[:240],
        "url": chosen_url,
        "source_url": source_url,
        "external_id": chosen_url,
    }
    key = str(candidate_key_value or "").strip() or candidate_key(candidate)
    return {
        "ok": True,
        "status": "validated",
        "candidate": {**candidate, "candidate_key": key},
        "candidate_key": key,
        "selection_authority": authority,
        "webfetch": {
            "fetched_url": source_url,
            "selected_url": chosen_url,
            "fetched_at": str(fetched_at or "")[:80] or None,
            "content_sha256": digest or None,
            "link_count": len(link_urls),
            "link_evidence": link_urls[:20],
        },
        "side_effects": "none — validation only",
    }


def build_acquisition_handoff(
    gateway: Any,
    *,
    research_need: str = "",
    source_id: str = "",
    connector_id: str = "",
    candidate_key_value: str = "",
    title: str = "",
    provider: str = "",
    kind: str = "",
    dataset_id: str = "",
    doi: str = "",
    url: str = "",
    selection_authority: str = "cursor_composer",
    webfetch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a no-side-effect acquisition plan for one explicit model choice."""
    root = Path(gateway.repo_root).resolve()
    selected = {
        "source_id": str(source_id or "").strip(),
        "connector_id": str(connector_id or "").strip(),
        "candidate_key": str(candidate_key_value or "").strip(),
        "title": str(title or "").strip(),
        "provider": str(provider or "").strip(),
        "kind": str(kind or "").strip(),
        "dataset_id": str(dataset_id or "").strip(),
        "doi": str(doi or "").strip(),
        "url": str(url or "").strip(),
    }
    receipt: dict[str, Any] | None = None
    if isinstance(webfetch, dict):
        receipt = validate_webfetch_handoff(
            fetched_url=str(webfetch.get("fetched_url") or webfetch.get("url") or url),
            selected_url=str(webfetch.get("selected_url") or webfetch.get("candidate_url") or url),
            title=selected["title"] or str(webfetch.get("title") or ""),
            provider=selected["provider"] or str(webfetch.get("provider") or ""),
            candidate_key_value=selected["candidate_key"] or str(webfetch.get("candidate_key") or ""),
            selection_authority=str(webfetch.get("selection_authority") or selection_authority),
            fetched_at=str(webfetch.get("fetched_at") or ""),
            content_sha256=str(webfetch.get("content_sha256") or ""),
            links=webfetch.get("links") or webfetch.get("link_evidence") or [],
        )
        if not receipt.get("ok"):
            return {"ok": False, "status": "invalid_webfetch_handoff", "research_need": research_need, "handoff": receipt}
        candidate = receipt.get("candidate") or {}
        for key in ("url", "title", "provider", "candidate_key"):
            if candidate.get(key):
                selected[key if key != "url" else "url"] = str(candidate[key])
        selected["kind"] = selected["kind"] or "live_candidate"

    identity = selected["candidate_key"] or candidate_key(selected)
    if not identity:
        return {
            "ok": False,
            "status": "missing_candidate_identity",
            "research_need": research_need,
            "selection_authority": selection_authority,
            "error": "pass an explicit source_id, dataset_id, DOI, URL, or candidate_key",
            "side_effects": "none",
        }
    selected["candidate_key"] = identity
    sid = selected["source_id"].lower()
    if sid in {"compustat", "capitaliq", "capital_iq"}:
        sid = "capital_iq_compustat"
        selected["source_id"] = sid
    if sid in {"crsp", "moveit"}:
        sid = "crsp_moveit"
        selected["source_id"] = sid

    status = inspect_source(root, sid) if sid else {"sources": []}
    source_row = (status.get("sources") or [{}])[0]
    out: dict[str, Any] = {
        "ok": True,
        "status": "planned",
        "research_need": str(research_need or "").strip(),
        "selection_authority": str(selection_authority or "cursor_composer").strip().lower(),
        "candidate": selected,
        "candidate_key": identity,
        "source_status": source_row,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "side_effects": "none — plan only; no fetch, job submission, or registry mutation",
    }
    if receipt:
        out["webfetch"] = receipt.get("webfetch")
    if sid in _LICENSED:
        out["collection"] = {
            "mode": "licensed_source_job",
            "requires_approval": True,
            "source_id": sid,
            "next_action": source_row.get("next_action") or "inspect_source_status",
            "note": "Licensed source execution is intentionally separate from this handoff and must use an approved job.",
        }
        return out
    try:
        plan = resolve_discover_collect_plan(
            gateway.procurement,
            root,
            connector_id=selected["connector_id"],
            source_id=selected["source_id"],
            title=selected["title"],
            url=selected["url"],
            candidate_key=identity,
            doi=selected["doi"],
            provider=selected["provider"],
            kind=selected["kind"] or "live_candidate",
            dataset_id=selected["dataset_id"],
        )
    except (KeyError, ValueError) as exc:
        plan = None
        out["resolution_error"] = str(exc)[:240]
    if plan:
        out["collection"] = {"mode": "public_or_web_candidate", "requires_approval": True, "plan": plan}
    else:
        out["collection"] = {
            "mode": "preview_then_resolve",
            "requires_approval": True,
            "next_action": "research_discover_source_preview",
        }
    return out
