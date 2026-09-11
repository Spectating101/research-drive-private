#!/usr/bin/env python3
"""HTTP binding for the authenticated researcher's personal research profile."""

from __future__ import annotations

from typing import Any

from scripts.research_data_mcp.research_profile import (
    research_profile_document,
    update_personal_profile,
)

RESEARCH_PROFILE_ROUTES: list[dict[str, str]] = [
    {"method": "GET", "path": "/library/profile", "handler": "library_research_profile"},
    {"method": "POST", "path": "/library/profile", "handler": "library_research_profile_update"},
]


def research_profile_handlers() -> dict[str, Any]:
    def library_research_profile(stack, query, payload, params):
        del query, payload, params
        return research_profile_document(stack.gateway.repo_root)

    def library_research_profile_update(stack, query, payload, params):
        del query, params
        return update_personal_profile(
            stack.gateway.repo_root,
            payload if isinstance(payload, dict) else {},
        )

    return {
        "library_research_profile": library_research_profile,
        "library_research_profile_update": library_research_profile_update,
    }
