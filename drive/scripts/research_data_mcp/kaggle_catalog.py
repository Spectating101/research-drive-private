"""Bounded Kaggle dataset catalogue client for Discover federation.

This module is intentionally read-only. It searches Kaggle's official dataset
catalogue and returns metadata only; acquisition remains a separate Discover
proposal/review/approval decision.
"""

from __future__ import annotations

import os
from typing import Any

import requests

_KAGGLE_DATASETS_LIST = "https://www.kaggle.com/api/v1/datasets/list"


def _auth_kwargs() -> tuple[dict[str, Any], str]:
    # Current Kaggle CLI/API tokens can be supplied directly as bearer tokens.
    token = str(os.environ.get("KAGGLE_API_TOKEN") or os.environ.get("KAGGLE_ACCESS_TOKEN") or "").strip()
    if token:
        return {"headers": {"Authorization": f"Bearer {token}"}}, "bearer"

    # Preserve compatibility with the long-standing username/API-key pair.
    username = str(os.environ.get("KAGGLE_USERNAME") or "").strip()
    key = str(os.environ.get("KAGGLE_KEY") or "").strip()
    if username and key:
        return {"auth": (username, key)}, "basic"
    return {}, "anonymous"


def _dataset_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("datasets", "results", "items"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _normalize_dataset(row: dict[str, Any]) -> dict[str, Any] | None:
    owner = str(row.get("ownerRef") or row.get("ownerSlug") or row.get("ownerName") or "").strip()
    slug = str(row.get("slug") or "").strip()
    ref = str(row.get("ref") or row.get("id") or "").strip()
    if not ref and owner and slug:
        ref = f"{owner}/{slug}"
    if not ref or "/" not in ref:
        return None

    tags_raw = row.get("tags") or []
    tags: list[str] = []
    if isinstance(tags_raw, list):
        for tag in tags_raw[:12]:
            if isinstance(tag, dict):
                value = tag.get("name") or tag.get("slug") or tag.get("ref")
            else:
                value = tag
            value_s = str(value or "").strip()
            if value_s:
                tags.append(value_s)

    total = row.get("totalBytes")
    try:
        total_bytes = int(total) if total not in (None, "") else None
    except (TypeError, ValueError):
        total_bytes = None

    usability = row.get("usabilityRating")
    try:
        usability_rating = float(usability) if usability not in (None, "") else None
    except (TypeError, ValueError):
        usability_rating = None

    return {
        "ref": ref,
        "title": str(row.get("title") or ref).strip(),
        "subtitle": str(row.get("subtitle") or row.get("description") or "").strip()[:500],
        "license": str(row.get("licenseName") or row.get("license") or "").strip(),
        "total_bytes": total_bytes,
        "updated_at": str(row.get("lastUpdated") or row.get("updatedAt") or row.get("lastUpdatedTime") or "").strip(),
        "usability_rating": usability_rating,
        "tags": tags,
    }


def search_datasets(query: str, *, limit: int = 5, timeout: float = 8.0) -> dict[str, Any]:
    """Search Kaggle dataset metadata without downloading or subscribing.

    Authentication failures and rate limits are returned as explicit states so
    Discover cannot convert missing access into an empty-search claim.
    """
    q = str(query or "").strip()
    bounded = min(max(int(limit or 0), 1), 20)
    if not q:
        return {"status": "empty_query", "datasets": [], "returned": 0, "auth_mode": "none"}

    auth_kwargs, auth_mode = _auth_kwargs()
    try:
        response = requests.get(
            _KAGGLE_DATASETS_LIST,
            params={"search": q, "page": 1, "pageSize": bounded, "sortBy": "hottest"},
            timeout=max(1.0, min(float(timeout), 15.0)),
            **auth_kwargs,
        )
    except requests.RequestException as exc:
        return {
            "status": "network_unavailable",
            "datasets": [],
            "returned": 0,
            "auth_mode": auth_mode,
            "error": f"{type(exc).__name__}: {exc}"[:240],
        }

    if response.status_code in {401, 403}:
        return {
            "status": "authentication_required",
            "datasets": [],
            "returned": 0,
            "auth_mode": auth_mode,
            "http_status": response.status_code,
        }
    if response.status_code == 429:
        return {
            "status": "rate_limited",
            "datasets": [],
            "returned": 0,
            "auth_mode": auth_mode,
            "http_status": response.status_code,
        }
    if not response.ok:
        return {
            "status": "provider_error",
            "datasets": [],
            "returned": 0,
            "auth_mode": auth_mode,
            "http_status": response.status_code,
        }

    try:
        raw_rows = _dataset_rows(response.json())
    except ValueError:
        return {
            "status": "invalid_response",
            "datasets": [],
            "returned": 0,
            "auth_mode": auth_mode,
            "http_status": response.status_code,
        }

    datasets = []
    for raw in raw_rows:
        normalized = _normalize_dataset(raw)
        if normalized:
            datasets.append(normalized)
        if len(datasets) >= bounded:
            break
    return {
        "status": "ok",
        "datasets": datasets,
        "returned": len(datasets),
        "auth_mode": auth_mode,
        "http_status": response.status_code,
    }
