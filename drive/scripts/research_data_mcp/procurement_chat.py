#!/usr/bin/env python3
"""Research Drive chat shell with typed Synthesis operation receipts.

The stable Composer/session implementation lives in ``procurement_chat_core``.
This adapter adds the cross-surface contract consumed by the public Synthesis
workstation without changing planning, authority, or execution behavior.
"""

from __future__ import annotations

from typing import Any

from scripts.research_data_mcp.procurement_chat_core import (
    ProcurementChatOrchestrator as _CoreProcurementChatOrchestrator,
)
from scripts.research_data_mcp.synthesis_object_targets import (
    activity_receipt,
    attach_synthesis_target,
    synthesis_target,
)


class ProcurementChatOrchestrator(_CoreProcurementChatOrchestrator):
    """Core desk chat plus typed Synthesis object correlation."""

    def chat(
        self,
        gateway: Any,
        message: str,
        *,
        session_id: str | None = None,
        user_email: str | None = None,
        rail_context: dict[str, Any] | None = None,
        on_progress: Any = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for event in self.chat_events(
            gateway,
            message,
            session_id=session_id,
            user_email=user_email,
            rail_context=rail_context,
        ):
            if event.get("type") == "progress" and on_progress:
                on_progress(event)
            if event.get("type") == "complete":
                result = event.get("result") or {}
        return result

    def chat_events(
        self,
        gateway: Any,
        message: str,
        *,
        session_id: str | None = None,
        user_email: str | None = None,
        rail_context: dict[str, Any] | None = None,
    ):
        receipts: list[dict[str, Any]] = []
        for event in super().chat_events(
            gateway,
            message,
            session_id=session_id,
            user_email=user_email,
            rail_context=rail_context,
        ):
            row = dict(event or {})
            if row.get("type") == "complete":
                result = dict(row.get("result") or {})
                target = synthesis_target(
                    rail_context,
                    result,
                    action=str(result.get("action") or ""),
                )
                if target:
                    result["activity_target"] = target
                    artifacts = dict(result.get("artifacts") or {})
                    artifacts.setdefault("activity_target", target)
                    result["artifacts"] = artifacts
                if receipts:
                    result["activity_events"] = receipts[-20:]
                yield {**row, "result": result}
                continue

            enriched = attach_synthesis_target(row, rail_context)
            receipt = activity_receipt(enriched)
            if receipt:
                receipts.append(receipt)
                if len(receipts) > 20:
                    receipts[:] = receipts[-20:]
            yield enriched
