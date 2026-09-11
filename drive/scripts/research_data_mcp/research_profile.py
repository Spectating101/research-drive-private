#!/usr/bin/env python3
"""Principal-scoped personal research profile for Research Drive.

Authentication answers *who the researcher is*.  This module stores only the
research context that researcher explicitly chooses to save.  It never creates
credentials, changes roles, grants permissions, or edits the faculty registry.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.desk_auth import current_desk_principal
from scripts.research_data_mcp.desk_principal import DeskPrincipal

_PROFILE_ROOT = Path("data_lake/research_drive/profiles")
_SCALAR_LIMITS = {
    "academic_stage": 80,
    "discipline": 160,
    "current_project": 1200,
}
_LIST_LIMITS = {
    "research_topics": (20, 160),
    "methods": (20, 160),
    "data_interests": (20, 160),
}
_FORBIDDEN_IDENTITY_FIELDS = frozenset(
    {"id", "principal", "principal_id", "email", "display_name", "role", "permissions"}
)
_ALLOWED_ROLES = frozenset({"public_member", "member", "operator"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _require_researcher(principal: DeskPrincipal | None = None) -> DeskPrincipal:
    actor = principal or current_desk_principal()
    if actor is None or actor.role not in _ALLOWED_ROLES:
        raise PermissionError("Personal research profile requires a signed-in Research Drive account")
    return actor


def _profile_path(repo_root: Path, principal: DeskPrincipal) -> Path:
    stable = hashlib.sha256(principal.principal_id.encode("utf-8")).hexdigest()
    return Path(repo_root).resolve() / _PROFILE_ROOT / f"{stable}.json"


def _load_saved(repo_root: Path, principal: DeskPrincipal) -> dict[str, Any]:
    path = _profile_path(repo_root, principal)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    profile = payload.get("profile")
    return dict(profile) if isinstance(profile, dict) else {}


def _clean_scalar(value: Any, limit: int) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def _clean_list(value: Any, *, max_items: int, item_limit: int) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("profile list fields must be JSON arrays")
    out: list[str] = []
    seen: set[str] = set()
    for raw in value:
        item = _clean_scalar(raw, item_limit)
        key = item.casefold()
        if not item or key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= max_items:
            break
    return out


def normalize_profile_patch(payload: dict[str, Any] | None) -> dict[str, Any]:
    body = dict(payload or {})
    forbidden = sorted(_FORBIDDEN_IDENTITY_FIELDS & set(body))
    if forbidden:
        raise ValueError(f"profile payload cannot change account identity: {', '.join(forbidden)}")
    allowed = set(_SCALAR_LIMITS) | set(_LIST_LIMITS) | {"clear_profile"}
    unknown = sorted(set(body) - allowed)
    if unknown:
        raise ValueError(f"unsupported profile fields: {', '.join(unknown)}")
    if body.get("clear_profile") is True:
        return {"__clear__": True}
    patch: dict[str, Any] = {}
    for key, limit in _SCALAR_LIMITS.items():
        if key in body:
            patch[key] = _clean_scalar(body.get(key), limit)
    for key, (max_items, item_limit) in _LIST_LIMITS.items():
        if key in body:
            patch[key] = _clean_list(body.get(key), max_items=max_items, item_limit=item_limit)
    return patch


def profile_configured(profile: dict[str, Any] | None) -> bool:
    if not isinstance(profile, dict):
        return False
    return any(bool(profile.get(key)) for key in (*_SCALAR_LIMITS, *_LIST_LIMITS))


def _write_saved(repo_root: Path, principal: DeskPrincipal, profile: dict[str, Any]) -> None:
    path = _profile_path(repo_root, principal)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    payload = {
        "version": 1,
        "principal_id": principal.principal_id,
        "profile": profile,
        "updated_at": _utc_now(),
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def personal_profile(repo_root: Path, *, principal: DeskPrincipal | None = None) -> dict[str, Any]:
    actor = _require_researcher(principal)
    return _load_saved(repo_root, actor)


def update_personal_profile(
    repo_root: Path,
    payload: dict[str, Any] | None,
    *,
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    actor = _require_researcher(principal)
    patch = normalize_profile_patch(payload)
    current = _load_saved(repo_root, actor)
    if patch.pop("__clear__", False):
        current = {}
    else:
        current.update(patch)
        current = {key: value for key, value in current.items() if value not in ("", [], None)}
    _write_saved(repo_root, actor, current)
    return research_profile_document(repo_root, principal=actor)


def _starter_prompts(profile: dict[str, Any]) -> list[str]:
    project = str(profile.get("current_project") or "").strip()
    topics = [str(v) for v in profile.get("research_topics") or [] if str(v).strip()]
    interests = [str(v) for v in profile.get("data_interests") or [] if str(v).strip()]
    prompts: list[str] = []
    if project:
        prompts.append(f"Find evidence and datasets for: {project}")
    if topics:
        prompts.append(f"Search the Library and wider sources for {'; '.join(topics[:3])}")
    if interests:
        prompts.append(f"Find data matching these interests: {'; '.join(interests[:3])}")
    prompts.extend(
        [
            "Find relevant evidence in the shared Library",
            "Search wider for datasets related to my current research",
        ]
    )
    return list(dict.fromkeys(prompts))[:5]


def effective_profile_row(
    repo_root: Path,
    *,
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    """Compile user-confirmed context into the legacy profile shape used by search/Ask.

    Same-email faculty registry facts may enrich the row, but never replace the
    authenticated identity and never make a non-faculty account a faculty account.
    """
    actor = _require_researcher(principal)
    from scripts.research_data_mcp.faculty_profile import resolve_profile

    faculty = resolve_profile(email=actor.email) if actor.email else None
    base = dict(faculty) if isinstance(faculty, dict) else {}
    saved = _load_saved(repo_root, actor)
    configured = profile_configured(saved)
    name = actor.display_name or (actor.email.split("@", 1)[0] if actor.email else "Researcher")
    base.update(
        {
            "email": actor.email,
            "name_en": name,
            "personal_profile": True,
            "profile_schema": "personal_research_profile_v1",
        }
    )
    if saved.get("discipline"):
        base["discipline"] = saved["discipline"]
    topics = list(saved.get("research_topics") or [])
    methods = list(saved.get("methods") or [])
    interests = list(saved.get("data_interests") or [])
    if topics:
        base["specialties"] = topics
    if methods:
        base["method_tags"] = methods
    if topics or interests:
        base["research_keywords"] = list(dict.fromkeys([*topics, *interests]))
    if saved.get("current_project"):
        base["research_tracks"] = [
            {
                "id": "personal-current-project",
                "title": saved["current_project"],
                "phase": "user_confirmed",
                "weight": 1.0,
            }
        ]
    if configured:
        base["starter_prompts"] = _starter_prompts(saved)
        base["unknown"] = False
    else:
        base.setdefault("unknown", True)
    return base


def effective_profile_for_email(repo_root: Path, email: str) -> dict[str, Any] | None:
    """Use personal context only for the current authenticated principal's own email."""
    from scripts.research_data_mcp.faculty_profile import normalize_email, resolve_profile

    requested = normalize_email(email)
    actor = current_desk_principal()
    if (
        actor is not None
        and actor.role in _ALLOWED_ROLES
        and actor.email
        and normalize_email(actor.email) == requested
    ):
        return effective_profile_row(repo_root, principal=actor)
    return resolve_profile(email=requested) if requested else None


def research_profile_document(
    repo_root: Path,
    *,
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    actor = _require_researcher(principal)
    saved = _load_saved(repo_root, actor)
    configured = profile_configured(saved)
    return {
        "version": 1,
        "principal": actor.public_dict(),
        "profile": saved,
        "configured": configured,
        "onboarding_required": not configured,
        "starter_prompts": _starter_prompts(saved),
        "authority": {
            "identity": "authenticated_principal",
            "research_context": "user_confirmed" if configured else "empty",
            "faculty_registry_is_account_authority": False,
            "role_editable_here": False,
        },
    }
