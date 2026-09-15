#!/usr/bin/env python3
"""Principal-scoped learned research memory.

The declared personal profile remains user-authored. Learned memory is a
separate, inspectable authority that the desk Composer may update when a
researcher states durable research context. Users can disable learning,
disable use without deleting data, remove one memory, or clear all memories.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.desk_auth import current_desk_principal
from scripts.research_data_mcp.desk_principal import DeskPrincipal

_MEMORY_RELATIVE_ROOT = Path("data_lake/research_drive/profile_memory")
_ALLOWED_ROLES = frozenset({"public_member", "member", "operator"})
_ALLOWED_KINDS = frozenset(
    {"topic", "method", "data_interest", "research_goal", "preference"}
)
_ALLOWED_SCOPES = frozenset({"account", "project"})
_MAX_MEMORIES = 100
_MAX_EVIDENCE = 8
_VALUE_LIMIT = 300
_EVIDENCE_LIMIT = 400
_SECRET_LIKE = re.compile(
    r"(?:-----BEGIN [A-Z ]+PRIVATE KEY-----|\b(?:sk|gh[opusr])_[A-Za-z0-9_-]{16,}|"
    r"\b(?:password|passwd|api[_ -]?key|access[_ -]?token)\s*[:=])",
    re.IGNORECASE,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _mcp_principal() -> DeskPrincipal | None:
    principal_id = str(os.getenv("RESEARCH_MCP_PRINCIPAL_ID") or "").strip()
    role = str(os.getenv("RESEARCH_MCP_PRINCIPAL_ROLE") or "").strip().lower()
    if not principal_id or role not in _ALLOWED_ROLES:
        return None
    return DeskPrincipal(
        principal_id=principal_id[:96],
        email="",
        display_name="Researcher",
        role=role,
    )


def _require_researcher(principal: DeskPrincipal | None = None) -> DeskPrincipal:
    actor = principal or current_desk_principal() or _mcp_principal()
    if actor is None or actor.role not in _ALLOWED_ROLES:
        raise PermissionError("Research memory requires a signed-in Research Drive account")
    return actor


def memory_storage_root(repo_root: Path) -> Path:
    runtime = str(os.getenv("YZU_RUNTIME_DRIVE_ROOT") or "").strip()
    if runtime:
        return Path(runtime).expanduser().resolve() / _MEMORY_RELATIVE_ROOT
    return Path(repo_root).resolve() / _MEMORY_RELATIVE_ROOT


def _memory_path(repo_root: Path, principal: DeskPrincipal) -> Path:
    stable = hashlib.sha256(principal.principal_id.encode("utf-8")).hexdigest()
    return memory_storage_root(repo_root) / f"{stable}.json"


def _empty_document(principal: DeskPrincipal) -> dict[str, Any]:
    return {
        "version": 1,
        "principal_id": principal.principal_id,
        "settings": {"auto_learn": True, "use_memory": True},
        "memories": [],
        "updated_at": None,
    }


def _load_document(repo_root: Path, principal: DeskPrincipal) -> dict[str, Any]:
    base = _empty_document(principal)
    try:
        payload = json.loads(_memory_path(repo_root, principal).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return base
    if not isinstance(payload, dict) or payload.get("principal_id") != principal.principal_id:
        return base
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    base["settings"] = {
        "auto_learn": bool(settings.get("auto_learn", True)),
        "use_memory": bool(settings.get("use_memory", True)),
    }
    rows = payload.get("memories") if isinstance(payload.get("memories"), list) else []
    base["memories"] = [dict(row) for row in rows if isinstance(row, dict)][:_MAX_MEMORIES]
    base["updated_at"] = payload.get("updated_at")
    return base


def _write_document(repo_root: Path, principal: DeskPrincipal, document: dict[str, Any]) -> None:
    path = _memory_path(repo_root, principal)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    document["updated_at"] = _utc_now()
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp")
    try:
        tmp.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
        try:
            tmp.chmod(0o600)
        except OSError:
            pass
        tmp.replace(path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _clean_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _memory_id(kind: str, value: str, scope: str, project_id: str) -> str:
    key = "\0".join((kind, _normalize(value), scope, project_id))
    return "memory-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def _public_document(document: dict[str, Any]) -> dict[str, Any]:
    memories = [dict(row) for row in document.get("memories") or [] if isinstance(row, dict)]
    settings = dict(document.get("settings") or {})
    return {
        "version": 1,
        "settings": settings,
        "memories": memories,
        "stored_count": len(memories),
        "active_count": len(memories) if settings.get("use_memory", True) else 0,
        "updated_at": document.get("updated_at"),
        "authority": {
            "kind": "learned_research_memory",
            "principal_scoped": True,
            "separate_from_declared_profile": True,
            "user_controllable": True,
        },
    }


def research_memory_document(
    repo_root: Path,
    *,
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    actor = _require_researcher(principal)
    return _public_document(_load_document(repo_root, actor))


def active_research_memories(
    repo_root: Path,
    *,
    principal: DeskPrincipal | None = None,
) -> list[dict[str, Any]]:
    actor = _require_researcher(principal)
    document = _load_document(repo_root, actor)
    if not document["settings"].get("use_memory", True):
        return []
    return [dict(row) for row in document.get("memories") or [] if isinstance(row, dict)]


def remember_research_context(
    repo_root: Path,
    *,
    kind: str,
    value: str,
    scope: str = "account",
    project_id: str = "",
    evidence: str = "",
    source: str = "ask",
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    """Upsert one durable, non-sensitive research memory for the current principal."""
    actor = _require_researcher(principal)
    memory_kind = _clean_text(kind, 40).lower().replace("-", "_")
    if memory_kind not in _ALLOWED_KINDS:
        raise ValueError(f"unsupported research memory kind: {memory_kind}")
    memory_scope = _clean_text(scope, 20).lower()
    if memory_scope not in _ALLOWED_SCOPES:
        raise ValueError(f"unsupported research memory scope: {memory_scope}")
    clean_project_id = _clean_text(project_id, 120)
    if memory_scope == "project" and not clean_project_id:
        raise ValueError("project-scoped research memory requires project_id")
    clean_value = _clean_text(value, _VALUE_LIMIT)
    if len(clean_value) < 3:
        raise ValueError("research memory value is too short")
    if _SECRET_LIKE.search(clean_value):
        raise ValueError("credentials and secrets cannot be stored in research memory")
    clean_evidence = _clean_text(evidence, _EVIDENCE_LIMIT)
    if _SECRET_LIKE.search(clean_evidence):
        raise ValueError("credentials and secrets cannot be stored in research memory evidence")

    document = _load_document(repo_root, actor)
    if not document["settings"].get("auto_learn", True):
        return {
            "remembered": False,
            "reason": "auto_learn_disabled",
            "memory": None,
            "memory_document": _public_document(document),
        }

    now = _utc_now()
    mid = _memory_id(memory_kind, clean_value, memory_scope, clean_project_id)
    clean_source = _clean_text(source, 40) or "ask"
    rows = [dict(row) for row in document.get("memories") or [] if isinstance(row, dict)]
    existing = next((row for row in rows if row.get("id") == mid), None)
    evidence_row = {
        "source": clean_source,
        "note": clean_evidence or None,
        "observed_at": now,
    }
    if existing is None:
        existing = {
            "id": mid,
            "kind": memory_kind,
            "value": clean_value,
            "scope": memory_scope,
            "project_id": clean_project_id or None,
            "created_at": now,
            "updated_at": now,
            "evidence_count": 1,
            "evidence": [evidence_row],
        }
        rows.insert(0, existing)
    else:
        existing["value"] = clean_value
        existing["updated_at"] = now
        existing["evidence_count"] = max(1, int(existing.get("evidence_count") or 0) + 1)
        prior = [dict(row) for row in existing.get("evidence") or [] if isinstance(row, dict)]
        signature = (clean_source, clean_evidence.casefold())
        if signature not in {
            (str(row.get("source") or ""), str(row.get("note") or "").casefold())
            for row in prior
        }:
            prior.insert(0, evidence_row)
        existing["evidence"] = prior[:_MAX_EVIDENCE]
        rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
    document["memories"] = rows[:_MAX_MEMORIES]
    _write_document(repo_root, actor, document)
    return {
        "remembered": True,
        "memory": dict(existing),
        "memory_document": _public_document(document),
    }


def forget_research_memory(
    repo_root: Path,
    memory_id: str,
    *,
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    actor = _require_researcher(principal)
    wanted = _clean_text(memory_id, 80)
    document = _load_document(repo_root, actor)
    before = list(document.get("memories") or [])
    document["memories"] = [row for row in before if str(row.get("id") or "") != wanted]
    removed = len(document["memories"]) != len(before)
    if removed:
        _write_document(repo_root, actor, document)
    return {"removed": removed, "memory_document": _public_document(document)}


def update_research_memory_settings(
    repo_root: Path,
    *,
    auto_learn: bool | None = None,
    use_memory: bool | None = None,
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    actor = _require_researcher(principal)
    document = _load_document(repo_root, actor)
    if auto_learn is not None:
        if not isinstance(auto_learn, bool):
            raise ValueError("auto_learn must be a boolean")
        document["settings"]["auto_learn"] = auto_learn
    if use_memory is not None:
        if not isinstance(use_memory, bool):
            raise ValueError("use_memory must be a boolean")
        document["settings"]["use_memory"] = use_memory
    _write_document(repo_root, actor, document)
    return _public_document(document)


def clear_research_memories(
    repo_root: Path,
    *,
    principal: DeskPrincipal | None = None,
) -> dict[str, Any]:
    actor = _require_researcher(principal)
    document = _load_document(repo_root, actor)
    document["memories"] = []
    _write_document(repo_root, actor, document)
    return _public_document(document)
