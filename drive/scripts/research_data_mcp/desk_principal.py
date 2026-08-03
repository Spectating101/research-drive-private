#!/usr/bin/env python3
"""Provider-neutral desk identity and role contract.

The current pilot may still use one shared operator token.  A multi-user desk
can additionally load token *digests* from DESK_PRINCIPALS_FILE without putting
raw user tokens in repository configuration.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "member": frozenset(
        {
            "view_research_data",
            "view_faculty_profile",
            "use_ask",
            "submit_collection",
        }
    ),
    "operator": frozenset(
        {
            "view_research_data",
            "view_faculty_profile",
            "view_operations",
            "use_ask",
            "submit_collection",
            "approve_jobs",
        }
    ),
}

_ROLE_ALIASES = {
    "viewer": "member",
    "researcher": "member",
    "steward": "operator",
    "admin": "operator",
}


@dataclass(frozen=True)
class DeskPrincipal:
    principal_id: str
    email: str
    display_name: str
    role: str

    @property
    def permissions(self) -> frozenset[str]:
        return _ROLE_PERMISSIONS.get(self.role, _ROLE_PERMISSIONS["member"])

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.principal_id,
            "email": self.email or None,
            "display_name": self.display_name or None,
            "role": self.role,
        }


def _clean_id(value: Any, *, fallback: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return fallback
    return "".join(ch for ch in raw if ch.isalnum() or ch in "._-")[:96] or fallback


def _normalize_principal(row: dict[str, Any], *, fallback_id: str) -> DeskPrincipal:
    principal_id = _clean_id(row.get("id") or row.get("principal_id"), fallback=fallback_id)
    role = str(row.get("role") or "member").strip().lower()
    role = _ROLE_ALIASES.get(role, role)
    if role not in _ROLE_PERMISSIONS:
        role = "member"
    return DeskPrincipal(
        principal_id=principal_id,
        email=str(row.get("email") or "").strip().lower()[:320],
        display_name=str(row.get("display_name") or row.get("name") or "").strip()[:160],
        role=role,
    )


def default_principal() -> DeskPrincipal:
    return _normalize_principal(
        {
            "id": os.getenv("DESK_DEFAULT_USER_ID") or "desk-operator",
            "email": os.getenv("DESK_DEFAULT_USER_EMAIL") or "",
            "display_name": os.getenv("DESK_DEFAULT_USER_NAME") or "Desk operator",
            "role": os.getenv("DESK_DEFAULT_USER_ROLE") or "operator",
        },
        fallback_id="desk-operator",
    )


def _principal_rows() -> list[dict[str, Any]]:
    path = str(os.getenv("DESK_PRINCIPALS_FILE") or "").strip()
    if not path:
        return []
    try:
        payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    rows = payload.get("principals") if isinstance(payload, dict) else payload
    return [row for row in (rows or []) if isinstance(row, dict)]


def configured_principals() -> dict[str, DeskPrincipal]:
    out: dict[str, DeskPrincipal] = {}
    for index, row in enumerate(_principal_rows(), start=1):
        principal = _normalize_principal(row, fallback_id=f"user-{index}")
        out[principal.principal_id] = principal
    return out


def principal_for_token(token: str, *, shared_token: str = "") -> DeskPrincipal | None:
    supplied = str(token or "").strip()
    if not supplied:
        return None
    supplied_digest = hashlib.sha256(supplied.encode("utf-8")).hexdigest()
    for index, row in enumerate(_principal_rows(), start=1):
        expected = str(row.get("token_sha256") or "").strip().lower()
        if expected and hmac.compare_digest(expected, supplied_digest):
            return _normalize_principal(row, fallback_id=f"user-{index}")
    if shared_token and hmac.compare_digest(supplied_digest, hashlib.sha256(shared_token.encode()).hexdigest()):
        return default_principal()
    return None


def principal_by_id(principal_id: str) -> DeskPrincipal | None:
    wanted = str(principal_id or "").strip()
    if not wanted:
        return None
    if wanted == default_principal().principal_id:
        return default_principal()
    return configured_principals().get(wanted)


def permissions_document(principal: DeskPrincipal | None) -> dict[str, bool]:
    permissions = principal.permissions if principal else frozenset()
    return {
        "view_static_ui": True,
        "view_research_data": "view_research_data" in permissions,
        "view_faculty_profile": "view_faculty_profile" in permissions,
        "view_operations": "view_operations" in permissions,
        "use_ask": "use_ask" in permissions,
        "submit_collection": "submit_collection" in permissions,
        "approve_jobs": "approve_jobs" in permissions,
    }
