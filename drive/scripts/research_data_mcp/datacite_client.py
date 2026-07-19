#!/usr/bin/env python3
"""DataCite REST helpers — shared by MCP and HTTP extension routes."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from scripts.research_query_engine.procurement import assert_public_url

DATACITE_API = "https://api.datacite.org/dois"


def request_json(url: str, timeout: int = 45) -> dict[str, Any]:
    assert_public_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "ResearchDrive-MCP/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        final_url = response.geturl()
        assert_public_url(final_url)
        return json.loads(response.read().decode("utf-8"))


def datacite_row(item: dict[str, Any]) -> dict[str, Any]:
    attrs = item.get("attributes") or {}
    titles = attrs.get("titles") or []
    creators = attrs.get("creators") or []
    rights = attrs.get("rightsList") or []
    descriptions = attrs.get("descriptions") or []
    return {
        "doi": item.get("id") or attrs.get("doi"),
        "title": titles[0].get("title") if titles and isinstance(titles[0], dict) else "",
        "publisher": attrs.get("publisher"),
        "publication_year": attrs.get("publicationYear"),
        "created": attrs.get("created"),
        "updated": attrs.get("updated"),
        "url": attrs.get("url"),
        "resource_type": (attrs.get("types") or {}).get("resourceTypeGeneral"),
        "creators": [row.get("name") for row in creators[:10] if isinstance(row, dict)],
        "description": descriptions[0].get("description", "")[:1200] if descriptions and isinstance(descriptions[0], dict) else "",
        "license": rights[0].get("rightsIdentifier") or rights[0].get("rights") if rights and isinstance(rights[0], dict) else None,
        "subjects": [row.get("subject") for row in (attrs.get("subjects") or [])[:20] if isinstance(row, dict)],
    }


def datacite_url(query: str = "", created: str = "", cursor: str = "1", page_size: int = 25) -> str:
    params = {"resource-types": "dataset", "page[size]": min(max(page_size, 1), 1000), "page[cursor]": cursor or "1"}
    if query.strip():
        params["query"] = query.strip()
    if created.strip():
        params["created"] = created.strip()
    return DATACITE_API + "?" + urllib.parse.urlencode(params)


def next_cursor(payload: dict[str, Any]) -> str | None:
    next_url = (payload.get("links") or {}).get("next")
    if not next_url:
        return None
    values = urllib.parse.parse_qs(urllib.parse.urlparse(next_url).query)
    return (values.get("page[cursor]") or values.get("page%5Bcursor%5D") or [None])[0]


def search(query: str = "", created: str = "", cursor: str = "1", page_size: int = 25, *, timeout: int = 45) -> dict[str, Any]:
    payload = request_json(
        datacite_url(query=query, created=created, cursor=cursor, page_size=page_size),
        timeout=timeout,
    )
    return {
        "rows": [datacite_row(item) for item in payload.get("data", [])],
        "returned": len(payload.get("data", [])),
        "total": (payload.get("meta") or {}).get("total"),
        "next_cursor": next_cursor(payload),
        "query": query,
        "created": created,
    }


def get_doi(doi: str) -> dict[str, Any]:
    clean = doi.strip().removeprefix("https://doi.org/")
    if not clean or len(clean) > 500:
        raise ValueError("a valid DOI is required")
    payload = request_json(DATACITE_API + "/" + urllib.parse.quote(clean, safe=""))
    return datacite_row(payload.get("data") or {})


def scope(created: str) -> dict[str, Any]:
    import re

    if not re.fullmatch(r"\d{4}(,\d{4})*", created.strip()):
        raise ValueError("created must be YYYY or comma-separated YYYY values")
    payload = request_json(datacite_url(created=created, page_size=1))
    total = int((payload.get("meta") or {}).get("total") or 0)
    return {
        "created": created,
        "total_records": total,
        "nominal_50000_row_chunks": (total + 49999) // 50000,
        "recommended_access": "cursor API backfill with checkpoints and throttling",
    }


def backfill_spec(created: str, workers: int = 1) -> dict[str, Any]:
    scope_row = scope(created)
    selected_workers = min(max(int(workers), 1), 4)
    return {
        "source": "DataCite REST API",
        "created": created,
        "estimated_records": scope_row["total_records"],
        "workers": selected_workers,
        "page_size": 500,
        "chunk_size": 50000,
        "sleep_seconds": 0.35,
        "checkpoint_required": True,
        "archive_format": "jsonl.gz",
        "execution": "approval_required",
        "warning": "Do not run overlapping workers against the same created-year scope.",
    }
