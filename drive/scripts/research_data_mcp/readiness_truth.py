#!/usr/bin/env python3
"""Honest query_ready / materialization fields from smoke proof.

query_ready means local bytes exist AND a bounded query smoke succeeded.
registered means bytes/archive exist without that proof.
"""

from __future__ import annotations

from typing import Any


def apply_smoke_readiness(spec: dict[str, Any], smoke: dict[str, Any] | None) -> dict[str, Any]:
    """Mutate and return spec with analysis_readiness + materialization from smoke."""
    smoke = smoke if isinstance(smoke, dict) else {}
    ok = bool(smoke.get("ok"))
    spec["query_smoke"] = smoke
    materialization = dict(spec.get("materialization") or {})
    if ok:
        spec["analysis_readiness"] = "query_ready"
        # Smoke proof upgrades access mode even if an earlier bulk label was set.
        prior_mode = str(spec.get("source_access_mode") or "").strip()
        if prior_mode in {"", "materialized_bulk", "registered", "metadata_only"}:
            spec["source_access_mode"] = "materialized_query_ready"
        materialization.update(
            {
                "query_ready": True,
                "query_verified": True,
                "query_smoke": smoke,
            }
        )
    else:
        # Bytes may exist; do not claim query_ready without proof.
        if str(spec.get("analysis_readiness") or "") in {"instant", "query_ready"}:
            spec["analysis_readiness"] = "registered"
        else:
            spec["analysis_readiness"] = str(spec.get("analysis_readiness") or "registered")
        materialization.update(
            {
                "query_ready": False,
                "query_verified": False,
                "query_smoke": smoke,
            }
        )
    spec["materialization"] = materialization
    return spec
