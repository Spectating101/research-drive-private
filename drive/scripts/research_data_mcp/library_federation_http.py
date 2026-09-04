#!/usr/bin/env python3
"""HTTP bindings for Library connected-storage federation and usage memory."""

from __future__ import annotations

from typing import Any

from scripts.research_data_mcp.library_federation import (
    list_library_usage_events,
    list_provider_directory,
    persist_library_usage_event,
)


LIBRARY_FEDERATION_ROUTES: list[dict[str, str]] = [
    {"method": "GET", "path": "/library/folders", "handler": "library_provider_folders"},
    {"method": "GET", "path": "/library/evidence-usage", "handler": "library_evidence_usage_list"},
    {"method": "POST", "path": "/library/evidence-usage", "handler": "library_evidence_usage_create"},
]


def _limit(query: dict[str, str], key: str, default: int) -> int:
    raw = str(query.get(key) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc


def library_federation_handlers() -> dict[str, Any]:
    def repo_root(stack):
        return stack.gateway.repo_root

    def library_provider_folders(stack, query, payload, params):
        return list_provider_directory(
            repo_root(stack),
            provider=str(query.get("provider") or ""),
            account_id=str(query.get("account_id") or ""),
            parent_id=str(query.get("parent_id") or ""),
            cursor=str(query.get("cursor") or ""),
            limit=_limit(query, "limit", 50),
            registry_path=stack.registry_path,
        )

    def library_evidence_usage_create(stack, query, payload, params):
        return persist_library_usage_event(repo_root(stack), payload)

    def library_evidence_usage_list(stack, query, payload, params):
        return list_library_usage_events(
            repo_root(stack),
            logical_asset_id=str(query.get("logical_asset_id") or ""),
            project_id=str(query.get("project_id") or ""),
            limit=_limit(query, "limit", 100),
        )

    return {
        "library_provider_folders": library_provider_folders,
        "library_evidence_usage_create": library_evidence_usage_create,
        "library_evidence_usage_list": library_evidence_usage_list,
    }
