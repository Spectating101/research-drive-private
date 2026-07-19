#!/usr/bin/env python3
"""License approvals and credential profile refs for gated procurement."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def vault_path(repo_root: Path) -> Path:
    return repo_root / "data_lake/procurement_memory/credentials.json"


def load_vault(repo_root: Path) -> dict[str, Any]:
    path = vault_path(repo_root)
    if not path.exists():
        example = repo_root / "config/procurement_credentials.example.json"
        if example.exists():
            payload = json.loads(example.read_text(encoding="utf-8"))
            save_vault(repo_root, payload)
            return payload
        return {"profiles": [], "license_approvals": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_vault(repo_root: Path, payload: dict[str, Any]) -> None:
    path = vault_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def list_profiles(repo_root: Path) -> list[dict[str, Any]]:
    profiles = []
    for row in load_vault(repo_root).get("profiles") or []:
        env_var = str(row.get("env_var") or "")
        profiles.append(
            {
                **row,
                "required": bool(row.get("required")),
                "configured": bool(env_var and os.environ.get(env_var)),
            }
        )
    return profiles


def upsert_profile(repo_root: Path, profile: dict[str, Any]) -> dict[str, Any]:
    store = load_vault(repo_root)
    profiles: list[dict[str, Any]] = store.setdefault("profiles", [])
    pid = str(profile.get("id") or "").strip()
    if not pid:
        raise ValueError("profile id is required")
    row = {
        "id": pid,
        "label": profile.get("label") or pid,
        "env_var": str(profile.get("env_var") or ""),
        "domains": list(profile.get("domains") or []),
        "updated_at": _utc_now(),
    }
    profiles = [p for p in profiles if p.get("id") != pid]
    profiles.append(row)
    store["profiles"] = profiles
    save_vault(repo_root, store)
    return row


def approve_license(
    repo_root: Path,
    *,
    doi: str = "",
    url: str = "",
    license_text: str = "",
    note: str = "",
) -> dict[str, Any]:
    store = load_vault(repo_root)
    approvals: list[dict[str, Any]] = store.setdefault("license_approvals", [])
    key = doi or url
    if not key:
        raise ValueError("doi or url required")
    row = {
        "doi": doi,
        "url": url,
        "license": license_text,
        "note": note,
        "approved_at": _utc_now(),
    }
    approvals = [a for a in approvals if (doi and a.get("doi") != doi) or (url and a.get("url") != url)]
    approvals.insert(0, row)
    store["license_approvals"] = approvals[:500]
    save_vault(repo_root, store)
    return row


def has_license_approval(repo_root: Path, *, doi: str = "", url: str = "") -> bool:
    for row in load_vault(repo_root).get("license_approvals") or []:
        if doi and str(row.get("doi") or "") == doi:
            return True
        if url and str(row.get("url") or "") == url:
            return True
    return False


def credential_for_url(repo_root: Path, url: str) -> dict[str, Any] | None:
    host = (url or "").lower()
    for profile in list_profiles(repo_root):
        domains = [str(d).lower() for d in profile.get("domains") or []]
        if any(d in host for d in domains if d):
            env_var = str(profile.get("env_var") or "")
            token = os.environ.get(env_var, "") if env_var else ""
            return {**profile, "required": bool(profile.get("required")), "token_present": bool(token)}
    return None
