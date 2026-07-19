#!/usr/bin/env python3
"""Domain packs — keyword-triggered procurement hints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_domain_packs(repo_root: Path) -> list[dict[str, Any]]:
    root = repo_root / "config/procurement_domain_packs"
    if not root.exists():
        return []
    packs: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            packs.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return packs


def match_domain_packs(message: str, packs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lower = message.lower()
    matched: list[dict[str, Any]] = []
    for pack in packs:
        keywords = pack.get("keywords") or []
        if any(kw in lower for kw in keywords):
            matched.append(pack)
    return matched


def pack_direct_downloads(packs: list[dict[str, Any]], url: str) -> list[dict[str, str]]:
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    items: list[dict[str, str]] = []
    for pack in packs:
        for block in pack.get("direct_downloads") or []:
            hosts = [str(h).lower() for h in block.get("match_hosts") or []]
            if any(h in host for h in hosts):
                items.extend(block.get("items") or [])
    return items


def pack_discovery_hints(packs: list[dict[str, Any]]) -> dict[str, Any]:
    queries: list[str] = []
    portals: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for pack in packs:
        queries.extend(pack.get("search_queries") or [])
        portals.extend(pack.get("trusted_portals") or [])
        blocked.extend(pack.get("blocked_commercial") or [])
    return {"search_queries": list(dict.fromkeys(queries)), "trusted_portals": portals, "blocked_commercial": blocked}
