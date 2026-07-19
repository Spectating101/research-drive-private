#!/usr/bin/env python3
"""File-backed TTL cache for procurement hot paths (advisor, discovery, semantic index)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


def catalog_fingerprint(repo_root: Path, registry_path: Path | None = None) -> str:
    """Invalidate caches when registry or collection queue changes."""
    root = Path(repo_root).resolve()
    reg = Path(registry_path) if registry_path else root / "config/research_query_registry.json"
    if not reg.is_absolute():
        reg = (root / reg).resolve()
    parts: list[str] = []
    for path in (reg, root / "config/data_collection_queue.json"):
        if path.exists():
            parts.append(f"{path.name}:{path.stat().st_mtime_ns}:{path.stat().st_size}")
    raw = "|".join(parts) or "empty"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def goal_key(goal: str) -> str:
    return hashlib.sha256(goal.strip().lower().encode("utf-8")).hexdigest()[:16]


class ProcurementCache:
    def __init__(self, repo_root: Path) -> None:
        self.root = Path(repo_root).resolve() / "data_lake/procurement_memory/cache"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, namespace: str, key: str) -> Path:
        safe_ns = namespace.replace("/", "_")
        safe_key = key.replace("/", "_")
        return self.root / safe_ns / f"{safe_key}.json"

    def get(
        self,
        namespace: str,
        key: str,
        *,
        fingerprint: str = "",
        ttl_hours: float | None = None,
    ) -> Any | None:
        path = self._path(namespace, key)
        if not path.exists():
            return None
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            path.unlink(missing_ok=True)
            return None
        if fingerprint and envelope.get("fingerprint") != fingerprint:
            return None
        expires = float(envelope.get("expires_at") or 0)
        if expires and time.time() > expires:
            path.unlink(missing_ok=True)
            return None
        if ttl_hours is not None:
            created = float(envelope.get("created_at") or 0)
            if created and (time.time() - created) > ttl_hours * 3600:
                path.unlink(missing_ok=True)
                return None
        return envelope.get("value")

    def set(
        self,
        namespace: str,
        key: str,
        value: Any,
        *,
        fingerprint: str = "",
        ttl_hours: float = 24,
    ) -> None:
        path = self._path(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        envelope = {
            "namespace": namespace,
            "key": key,
            "fingerprint": fingerprint,
            "created_at": now,
            "expires_at": now + ttl_hours * 3600,
            "value": value,
        }
        path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")

    def invalidate_namespace(self, namespace: str) -> int:
        ns_dir = self.root / namespace.replace("/", "_")
        if not ns_dir.exists():
            return 0
        count = 0
        for path in ns_dir.glob("*.json"):
            path.unlink(missing_ok=True)
            count += 1
        return count
