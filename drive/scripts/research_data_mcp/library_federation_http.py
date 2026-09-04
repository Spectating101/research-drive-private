#!/usr/bin/env python3
"""HTTP bindings for Library connected-storage federation and usage memory."""

from __future__ import annotations

from typing import Any

from scripts.research_data_mcp.library_federation import list_library_usage_events
from scripts.research_data_mcp.library_federation_holdings import (
    bind_provider_holding,
    list_provider_holdings,
    unbind_provider_holding,
)
from scripts.research_data_mcp.library_federation_runtime import (
    inspect_provider_item_runtime,
    list_provider_directory_runtime,
    persist_canonical_library_usage_event,
)


LIBRARY_FEDERATION_ROUTES: list[dict[str, str]] = [
    {"method": "GET", "path": "/library/folders", "handler": "library_provider_folders"},
    {"method": "GET", "path": "/library/federation/holdings", "handler": "library_federation_holdings_list"},
    {"method": "POST", "path": "/library/federation/holdings/bind", "handler": "library_federation_holdings_bind"},
    {"method": "POST", "path": "/library/federation/holdings/unbind", "handler": "library_federation_holdings_unbind"},
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
        return list_provider_directory_runtime(
            repo_root(stack),
            provider=str(query.get("provider") or ""),
            account_id=str(query.get("account_id") or ""),
            parent_id=str(query.get("parent_id") or ""),
            cursor=str(query.get("cursor") or ""),
            limit=_limit(query, "limit", 50),
            registry_path=stack.registry_path,
        )

    def library_federation_holdings_list(stack, query, payload, params):
        return list_provider_holdings(
            repo_root(stack),
            registry_path=stack.registry_path,
            provider=str(query.get("provider") or ""),
            account_id=str(query.get("account_id") or ""),
            logical_asset_id=str(query.get("logical_asset_id") or ""),
            limit=_limit(query, "limit", 200),
        )

    def library_federation_holdings_bind(stack, query, payload, params):
        provider = str(payload.get("provider") or "")
        account_id = str(payload.get("account_id") or "")
        provider_item_id = str(payload.get("provider_item_id") or "")
        logical_asset_id = str(payload.get("logical_asset_id") or "")
        observation = inspect_provider_item_runtime(
            repo_root(stack),
            provider=provider,
            account_id=account_id,
            provider_item_id=provider_item_id,
        )
        holding = bind_provider_holding(
            repo_root(stack),
            registry_path=stack.registry_path,
            provider=provider,
            account_id=account_id,
            provider_item_id=provider_item_id,
            logical_asset_id=logical_asset_id,
            observation=observation,
        )
        return {"ok": True, "holding": holding}

    def library_federation_holdings_unbind(stack, query, payload, params):
        return unbind_provider_holding(
            repo_root(stack),
            provider=str(payload.get("provider") or ""),
            account_id=str(payload.get("account_id") or ""),
            provider_item_id=str(payload.get("provider_item_id") or ""),
        )

    def library_evidence_usage_create(stack, query, payload, params):
        return persist_canonical_library_usage_event(
            repo_root(stack),
            payload,
            registry_path=stack.registry_path,
        )

    def library_evidence_usage_list(stack, query, payload, params):
        return list_library_usage_events(
            repo_root(stack),
            logical_asset_id=str(query.get("logical_asset_id") or ""),
            project_id=str(query.get("project_id") or ""),
            limit=_limit(query, "limit", 100),
        )

    return {
        "library_provider_folders": library_provider_folders,
        "library_federation_holdings_list": library_federation_holdings_list,
        "library_federation_holdings_bind": library_federation_holdings_bind,
        "library_federation_holdings_unbind": library_federation_holdings_unbind,
        "library_evidence_usage_create": library_evidence_usage_create,
        "library_evidence_usage_list": library_evidence_usage_list,
    }
