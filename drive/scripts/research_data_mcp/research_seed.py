#!/usr/bin/env python3
"""Principal-scoped Research Drive bootstrap / seed contract.

A seed is a plan over authorities the desk already has.  It does not copy bytes,
recursively index a cloud account, or mutate the shared connector registry.
Faculty research memory remains useful when no cloud account is connected; a
verified ConnectedAccount simply contributes another principal-bound source
authority to the same package.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.research_data_mcp.connected_accounts import list_connected_accounts
from scripts.research_data_mcp.desk_auth import current_desk_principal
from scripts.research_data_mcp.desk_principal import DeskPrincipal
from scripts.research_data_mcp.faculty_profile import (
    cold_start_prompts,
    lab_fintech_stack_recommendations,
    procurement_recommendations,
    resolve_profile,
)


def _require_named_principal(principal: DeskPrincipal | None = None) -> DeskPrincipal:
    actor = principal or current_desk_principal()
    if actor is None or actor.role not in {"member", "operator"}:
        raise PermissionError("Research seeding requires an authenticated named Research Drive account")
    return actor


def _capabilities(access_mode: str) -> dict[str, bool]:
    """Honor the authority the user selected even if an upstream OAuth scope is broader."""
    mode = str(access_mode or "read").strip().lower()
    return {
        "metadata_index": mode in {"index", "read", "write"},
        "read": mode in {"read", "write"},
        "write": mode == "write",
    }


def connected_source_authorities(
    repo_root: Path,
    *,
    principal: DeskPrincipal | None = None,
) -> list[dict[str, Any]]:
    """Return verified principal-local cloud authorities safe for seed/reconcile use.

    Internal rclone remote names, provider account ids, OAuth material, and host
    configuration are deliberately absent from this contract.
    """
    actor = _require_named_principal(principal)
    sources: list[dict[str, Any]] = []
    for row in list_connected_accounts(repo_root, principal=actor):
        if str(row.get("status") or "").lower() != "connected":
            continue
        if not str(row.get("verified_at") or "").strip():
            # OAuth completion proves identity, but a source is not seed-usable
            # until Research Drive has also verified the remote itself.
            continue
        mode = str(row.get("access_mode") or "read").strip().lower()
        sources.append(
            {
                "id": str(row.get("id") or ""),
                "kind": "connected_storage",
                "provider": str(row.get("provider") or ""),
                "label": str(row.get("label") or row.get("email") or "Connected storage"),
                "email": str(row.get("email") or "") or None,
                "access_mode": mode,
                "status": "verified",
                "verified_at": row.get("verified_at"),
                "capabilities": _capabilities(mode),
            }
        )
    sources.sort(key=lambda row: (str(row.get("provider")), str(row.get("label")).lower(), str(row.get("id"))))
    return sources


def _research_context(profile: dict[str, Any] | None) -> dict[str, Any]:
    if not profile:
        return {
            "profile_bound": False,
            "profile_unknown": True,
            "name": None,
            "discipline": None,
            "specialties": [],
            "research_tracks": [],
            "method_tags": [],
        }
    return {
        "profile_bound": True,
        "profile_unknown": bool(profile.get("unknown")),
        "name": profile.get("name_en") or profile.get("name"),
        "discipline": profile.get("discipline"),
        "specialties": [str(v) for v in (profile.get("specialties") or []) if str(v).strip()],
        "research_tracks": [dict(v) for v in (profile.get("research_tracks") or []) if isinstance(v, dict)],
        "method_tags": [str(v) for v in (profile.get("method_tags") or []) if str(v).strip()],
    }


def build_research_seed(
    repo_root: Path,
    *,
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    """Build the non-destructive initial/reseed package for one desk principal."""
    actor = _require_named_principal(principal)
    profile = resolve_profile(email=actor.email) if actor.email else None
    context = _research_context(profile)
    connected = connected_source_authorities(repo_root, principal=actor)

    if profile and not profile.get("unknown"):
        mode = "faculty_profile"
    elif profile:
        mode = "yzu_profile_fallback"
    else:
        mode = "generic_cold_start"

    references = (
        lab_fintech_stack_recommendations(profile, repo_root=repo_root)
        if profile
        else []
    )
    procurement = procurement_recommendations(profile, repo_root=repo_root) if profile else []
    starters = cold_start_prompts(profile)

    return {
        "version": 1,
        "principal": {
            "id": actor.principal_id,
            "display_name": actor.display_name or None,
        },
        "bootstrap_mode": mode,
        "research_context": context,
        "starter_prompts": starters,
        "reference_holdings": references,
        "procurement_recommendations": procurement,
        "connected_sources": connected,
        "source_summary": {
            "connected_sources": len(connected),
            "reference_holdings": len(references),
            "procurement_candidates": len(procurement),
        },
        "policy": {
            "connected_storage_optional": True,
            "seed_without_connected_storage": True,
            "automatic_byte_copy": False,
            "automatic_recursive_cloud_index": False,
            "materialization_requires_explicit_operation": True,
        },
    }
