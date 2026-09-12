#!/usr/bin/env python3
"""Bounded Synthesis Preview route for signed-in researchers.

Preview executes the accepted deterministic recipe only against a bounded input
window. It creates no collection job, materialized dataset, registry row, or
approval. Full execution continues to use `/execute` and its stronger
`submit_collection` permission.
"""

from __future__ import annotations

from typing import Any

SYNTHESIS_PREVIEW_ROUTES: list[dict[str, str]] = [
    {
        "method": "POST",
        "path": "/library/synthesis/threads/{thread_id}/preview",
        "handler": "library_synthesis_thread_preview",
    },
]


def synthesis_preview_handlers() -> dict[str, Any]:
    def library_synthesis_thread_preview(stack, query, payload, params):
        del query, payload
        return stack.gateway.synthesis_thread_submit_execution(
            params["thread_id"], action="preview"
        )

    return {"library_synthesis_thread_preview": library_synthesis_thread_preview}
