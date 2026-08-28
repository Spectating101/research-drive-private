"""Durable provenance fields for promoted Library assets.

The Library registry must remain self-describing. Provider identity is useful,
but a researcher reproducing an acquisition needs the exact recorded URL plus
the collection mechanism/runnable route when those facts existed at execution
time. This module only copies recorded facts; it never manufactures a URL from
a provider name or generic source domain.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return " ".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _first_text(*values: Any) -> str:
    for value in values:
        normalized = _text(value)
        if normalized:
            return normalized
    return ""


def _http_url(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.username or parsed.password:
        return ""
    return raw


def _first_url(*values: Any) -> str:
    for value in values:
        normalized = _http_url(value)
        if normalized:
            return normalized
    return ""


def _command(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return " ".join(str(part).strip() for part in value if str(part).strip())
    return _text(value)


def provenance_from_job(job: dict[str, Any]) -> dict[str, str]:
    """Extract only provenance facts actually recorded on one execution job."""
    plan = _mapping(job.get("plan"))
    request = _mapping(job.get("request"))
    result = _mapping(job.get("result"))
    materialized = _mapping(result.get("materialized"))
    materialized_plan = _mapping(materialized.get("plan"))
    candidate = _mapping(plan.get("candidate")) or _mapping(request.get("candidate"))
    webfetch = _mapping(result.get("webfetch")) or _mapping(job.get("webfetch"))

    source_url = _first_url(
        webfetch.get("selected_url"),
        webfetch.get("fetched_url"),
        plan.get("source_url"),
        plan.get("url"),
        candidate.get("source_url"),
        candidate.get("url"),
        materialized.get("source_url"),
        materialized_plan.get("url"),
        request.get("source_url"),
        request.get("url"),
    )
    method = _first_text(
        plan.get("collect_via"),
        plan.get("collection_method"),
        plan.get("job_type"),
        result.get("collect_mode"),
    )
    script = _first_text(
        plan.get("script_path"),
        plan.get("collection_script"),
        plan.get("pipeline_script"),
    )
    command = _command(
        plan.get("command")
        or plan.get("collection_command")
        or plan.get("pipeline_command")
    )
    route = _first_text(
        plan.get("route"),
        plan.get("source_route"),
        plan.get("connector_id"),
        plan.get("pipeline_id"),
        plan.get("task_id"),
        plan.get("script_key"),
    )
    fetched_at = _first_text(webfetch.get("fetched_at"), result.get("fetched_at"))
    content_sha256 = _first_text(
        webfetch.get("content_sha256"),
        result.get("content_sha256"),
    )

    return {
        "source_url": source_url,
        "collection_method": method,
        "collection_script": script,
        "collection_command": command,
        "source_route": route,
        "fetched_at": fetched_at,
        "content_sha256": content_sha256,
    }


def stamp_spec_with_job_provenance(spec: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    """Copy missing execution provenance into a registry spec without upgrading claims."""
    out = dict(spec)
    receipt = provenance_from_job(job)
    for key, value in receipt.items():
        if value and not _text(out.get(key)):
            out[key] = value

    procurement = dict(_mapping(out.get("procurement")))
    nested_map = {
        "source_url": "source_url",
        "collect_via": "collection_method",
        "script": "collection_script",
        "command": "collection_command",
        "route": "source_route",
        "fetched_at": "fetched_at",
        "content_sha256": "content_sha256",
    }
    for nested_key, receipt_key in nested_map.items():
        value = receipt.get(receipt_key, "")
        if value and not _text(procurement.get(nested_key)):
            procurement[nested_key] = value
    if procurement:
        out["procurement"] = procurement
    return out
