#!/usr/bin/env python3
"""HTTP binding for the principal-scoped Research Drive seed package."""

from __future__ import annotations

from typing import Any

from scripts.research_data_mcp.research_seed import build_research_seed


RESEARCH_SEED_ROUTES: list[dict[str, str]] = [
    {"method": "GET", "path": "/library/seed", "handler": "library_seed"},
]


def research_seed_handlers() -> dict[str, Any]:
    def library_seed(stack, query, payload, params):
        return build_research_seed(stack.gateway.repo_root)

    return {"library_seed": library_seed}
