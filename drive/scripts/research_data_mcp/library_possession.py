#!/usr/bin/env python3
"""Fail-closed possession boundary for Library retrieval.

This mirrors the desk contract: registry awareness is broader than possession.
Catalogue references and generic live connectors stay outside Library unless
materialization/registration evidence says the lab actually holds the asset.
"""

from __future__ import annotations

from typing import Any


CATALOG_ONLY_ACCESS = frozenset({"catalog_reference", "procurement_catalog", "live_connector"})
MATERIALIZED_ACCESS = frozenset({"derived_internal", "materialized_bulk", "materialized_instant"})
QUERY_READY = frozenset({"instant", "query_ready", "registered"})


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def is_library_holding(row: dict[str, Any] | None) -> bool:
    if not isinstance(row, dict):
        return False

    access = _lower(row.get("source_access_mode") or row.get("access_shape"))
    materialization = row.get("materialization") if isinstance(row.get("materialization"), dict) else {}
    has_materialized = bool(
        row.get("local_ready")
        or row.get("in_vault")
        or materialization.get("query_ready") is True
        or materialization.get("resolved_path")
    )
    if access in CATALOG_ONLY_ACCESS and not has_materialized:
        return False

    if row.get("local_ready") or row.get("in_vault"):
        return True
    if _lower(row.get("kind")) in {"local_registry", "lab"}:
        return True
    if row.get("local") is True or row.get("in_lab") is True:
        return True
    if row.get("registry_id") or row.get("registration_id") or row.get("registered") is True:
        return True
    if materialization.get("query_ready") is True or materialization.get("resolved_path"):
        return True

    has_local_path = bool(row.get("local_root") or row.get("local_path"))
    if not has_local_path:
        return False
    if access in MATERIALIZED_ACCESS:
        return True
    readiness = _lower(row.get("analysis_readiness") or row.get("readiness"))
    if readiness in QUERY_READY:
        return True
    return not access and _lower(row.get("backend")).startswith("local_")
