#!/usr/bin/env python3
"""Lean ownership rules for private researcher work.

Catalog, Library and operations remain shared platform objects. Ask sessions,
Discover intents and Synthesis threads belong to the authenticated member who
created them. Operators and trusted in-process jobs may inspect all records.
"""

from __future__ import annotations

import os
from typing import Any


def _principal():
    # Lazy import avoids coupling storage initialization to HTTP auth setup.
    from scripts.research_data_mcp.desk_auth import current_desk_principal

    principal = current_desk_principal()
    if principal is not None:
        return principal
    # The desk Composer runs its MCP server as a child process. ContextVars do
    # not cross that process boundary, so carry the already-authorized
    # principal through a server-owned environment contract. This prevents a
    # member tool call from becoming an ownerless, implicitly trusted action.
    principal_id = os.getenv("RESEARCH_MCP_PRINCIPAL_ID", "").strip()
    role = os.getenv("RESEARCH_MCP_PRINCIPAL_ROLE", "").strip().lower()
    if principal_id and role in {"public_member", "member", "operator"}:
        from scripts.research_data_mcp.desk_principal import DeskPrincipal

        return DeskPrincipal(
            principal_id=principal_id[:96],
            email="",
            display_name="Desk MCP principal",
            role=role,
        )
    return None


def owner_id_for_create(explicit_owner_id: str = "") -> str:
    principal = _principal()
    if principal is not None:
        return principal.principal_id
    return str(explicit_owner_id or "").strip()[:96]


def can_access_owner(owner_id: Any) -> bool:
    principal = _principal()
    if principal is None:
        # Internal MCP/worker calls are trusted; HTTP requests always bind a
        # principal before reaching protected handlers.
        return True
    if principal.role == "operator":
        return True
    return bool(owner_id) and str(owner_id) == principal.principal_id


def require_owner(owner_id: Any, record_id: str) -> None:
    if not can_access_owner(owner_id):
        # Do not reveal whether another member's private record exists.
        raise KeyError(record_id)


def owner_filter() -> tuple[str, tuple[str, ...]]:
    """SQL predicate for list endpoints; empty predicate means trusted/all."""
    principal = _principal()
    if principal is None or principal.role == "operator":
        return "", ()
    return "owner_id = ?", (principal.principal_id,)
