#!/usr/bin/env python3
"""HTTP binding for the authenticated researcher's personal research profile."""

from __future__ import annotations

from typing import Any

from scripts.research_data_mcp.research_profile import (
    research_profile_document,
    update_personal_profile,
)
from scripts.research_data_mcp.research_profile_memory import (
    clear_research_memories,
    forget_research_memory,
    research_memory_document,
    update_research_memory_settings,
)

RESEARCH_PROFILE_ROUTES: list[dict[str, str]] = [
    {"method": "GET", "path": "/library/profile", "handler": "library_research_profile"},
    {"method": "POST", "path": "/library/profile", "handler": "library_research_profile_update"},
    {"method": "GET", "path": "/library/profile/memory", "handler": "library_research_memory"},
    {"method": "POST", "path": "/library/profile/memory", "handler": "library_research_memory_update"},
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

    def library_research_memory(stack, query, payload, params):
        del query, payload, params
        return research_memory_document(stack.gateway.repo_root)

    def library_research_memory_update(stack, query, payload, params):
        del query, params
        body = payload if isinstance(payload, dict) else {}
        action = str(body.get("action") or "settings").strip().lower()
        if action == "settings":
            return update_research_memory_settings(
                stack.gateway.repo_root,
                auto_learn=body.get("auto_learn") if "auto_learn" in body else None,
                use_memory=body.get("use_memory") if "use_memory" in body else None,
            )
        if action == "forget":
            return forget_research_memory(
                stack.gateway.repo_root,
                str(body.get("memory_id") or ""),
            )["memory_document"]
        if action == "clear":
            return clear_research_memories(stack.gateway.repo_root)
        raise ValueError(f"unsupported research memory action: {action}")

    return {
        "library_research_profile": library_research_profile,
        "library_research_profile_update": library_research_profile_update,
        "library_research_memory": library_research_memory,
        "library_research_memory_update": library_research_memory_update,
    }
