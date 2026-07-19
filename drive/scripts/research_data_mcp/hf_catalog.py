#!/usr/bin/env python3
"""Hugging Face Hub cross-reference (metadata + load hints, not byte proxy)."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "ResearchDrive/1.0"


def search_datasets(query: str, *, limit: int = 8, timeout: int = 8) -> dict[str, Any]:
    q = urllib.parse.quote(query.strip())
    url = f"https://huggingface.co/api/datasets?search={q}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"query": query, "rows": [], "error": str(exc)}
    out: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        did = str(row.get("id") or "")
        if not did:
            continue
        out.append(
            {
                "id": did,
                "title": did.split("/")[-1],
                "author": did.split("/")[0] if "/" in did else "",
                "downloads": row.get("downloads"),
                "likes": row.get("likes"),
                "tags": row.get("tags") or [],
                "url": f"https://huggingface.co/datasets/{did}",
                "load_hint": f'load_dataset("{did}")',
                "source": "huggingface",
            }
        )
    return {"query": query, "rows": out, "total": len(out)}


def get_dataset(dataset_id: str) -> dict[str, Any]:
    did = dataset_id.strip().removeprefix("https://huggingface.co/datasets/")
    url = f"https://huggingface.co/api/datasets/{urllib.parse.quote(did, safe='/')}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        row = json.loads(resp.read().decode("utf-8"))
    return {
        "id": did,
        "title": row.get("id"),
        "description": (row.get("description") or "")[:500],
        "downloads": row.get("downloads"),
        "tags": row.get("tags") or [],
        "url": f"https://huggingface.co/datasets/{did}",
        "load_hint": f'load_dataset("{did}")',
        "source": "huggingface",
    }
