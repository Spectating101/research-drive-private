#!/usr/bin/env python3
"""Research Drive chat shell with typed Synthesis operation receipts.

The stable Composer/session implementation lives in ``procurement_chat_core``.
This adapter adds cross-surface correlation and principal-scoped research
context without changing planning, authority, or execution behavior.
"""

from __future__ import annotations

from pathlib import Path
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
    """Core desk chat plus personal profile and typed Synthesis correlation."""

    def __init__(self, repo_root: Any) -> None:
        super().__init__(repo_root)
        self.repo_root = Path(repo_root).resolve()

    def _bind_faculty_profile(self, state: dict[str, Any], user_email: str | None) -> None:
        """Preserve faculty behavior, then overlay the signed-in researcher's own context.

        The authenticated principal remains authority for identity. Personal
        profile fields can shape research semantics but cannot change account
        email, role, permissions, or collection authority.
        """
        super()._bind_faculty_profile(state, user_email)
        try:
            from scripts.research_data_mcp.desk_auth import current_desk_principal
            from scripts.research_data_mcp.faculty_profile import profile_summary
            from scripts.research_data_mcp.research_profile import (
                effective_profile_row,
                personal_profile,
            )

            actor = current_desk_principal()
            if actor is None or actor.role not in {"public_member", "member", "operator"}:
                state.pop("research_profile", None)
                return
            row = effective_profile_row(self.repo_root, principal=actor)
            state["faculty_profile"] = profile_summary(row, repo_root=self.repo_root)
            state["faculty_profile_row"] = row
            state["research_profile"] = personal_profile(self.repo_root, principal=actor)
            state["user_email"] = actor.email
        except Exception:
            # Personalization must never make Ask unavailable. The previously
            # bound faculty/unknown context remains an honest fallback.
            state.setdefault("research_profile", {})

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
