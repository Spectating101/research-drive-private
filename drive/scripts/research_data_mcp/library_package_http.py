#!/usr/bin/env python3
"""Thin authenticated HTTP adapter for Library research packages."""

from __future__ import annotations

import re
from typing import Any

from scripts.research_data_mcp.library_packages import (
    DEFAULT_MAX_DATASETS,
    DEFAULT_MAX_TOTAL_BYTES,
    get_library_package,
    prepare_library_package,
)

_PACKAGE_RE = re.compile(r"^/library/packages/(?P<package_id>[A-Za-z0-9._-]+)(?P<download>/download)?$")


def _error(exc: Exception, *, default_status: int = 400) -> dict[str, Any]:
    status = 404 if isinstance(exc, KeyError) else default_status
    return {
        "status": status,
        "body": {
            "error": type(exc).__name__,
            "message": str(exc),
        },
    }


def handle_library_package_get(path: str, query: dict[str, str], gateway: Any) -> dict[str, Any] | None:
    del query  # reserved for future bounded package views
    match = _PACKAGE_RE.fullmatch(str(path or ""))
    if not match:
        return None
    package_id = match.group("package_id")
    try:
        record = get_library_package(gateway.repo_root, package_id)
    except Exception as exc:
        return _error(exc)
    if match.group("download"):
        archive_file = str(record.get("_archive_file") or "")
        return {
            "status": 200,
            "body": {
                "_file_delivery": True,
                "file": archive_file,
                "content_type": "application/zip",
                "name": record["archive"]["name"],
            },
        }
    clean = {key: value for key, value in record.items() if not key.startswith("_")}
    return {"status": 200, "body": clean}


def handle_library_package_post(path: str, payload: dict[str, Any], gateway: Any) -> dict[str, Any] | None:
    if str(path or "") != "/library/packages/prepare":
        return None
    body = payload if isinstance(payload, dict) else {}
    dataset_ids = body.get("dataset_ids")
    if not isinstance(dataset_ids, list):
        return {
            "status": 400,
            "body": {
                "error": "BadRequest",
                "message": "dataset_ids must be a JSON array of held Library dataset ids",
            },
        }
    try:
        requested_max_datasets = int(body.get("max_datasets") or DEFAULT_MAX_DATASETS)
        requested_max_bytes = int(body.get("max_total_bytes") or DEFAULT_MAX_TOTAL_BYTES)
    except (TypeError, ValueError):
        return {
            "status": 400,
            "body": {"error": "BadRequest", "message": "package limits must be integers"},
        }
    # Clients may request a smaller package, never enlarge the server ceiling.
    max_datasets = min(DEFAULT_MAX_DATASETS, max(1, requested_max_datasets))
    max_total_bytes = min(DEFAULT_MAX_TOTAL_BYTES, max(0, requested_max_bytes))
    try:
        result = prepare_library_package(
            gateway,
            research_need=str(body.get("research_need") or ""),
            dataset_ids=dataset_ids,
            max_datasets=max_datasets,
            max_total_bytes=max_total_bytes,
        )
    except Exception as exc:
        return _error(exc)
    return {"status": 200, "body": result}
