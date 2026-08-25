"""Install the bounded-preview gate on the canonical Synthesis execution path.

The faculty HTTP endpoint and Composer MCP tool already converge on
ResearchDataGateway.synthesis_thread_submit_execution().  Wrapping that single
boundary preserves one execution authority without adding a second router path:

1. accepted spec + no current successful preview -> run/persist preview only;
2. same accepted spec + successful preview -> submit pending-approval job;
3. changed spec hash -> previous receipt is stale and preview runs again.

No preview call creates a worker job, materialised output, registry row, or Drive
artifact.  The original submission implementation remains the only function that
can create the synthesis_execute approval job.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_INSTALLED = False


def _failed_receipt(spec_hash: str, error: Exception) -> dict[str, Any]:
    return {
        "status": "failed",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "spec_hash": spec_hash,
        "bounded": True,
        "error": str(error)[:2000],
        "materialised": False,
        "registered": False,
        "review_required": True,
    }


def _persist_preview(gateway, thread_id: str, state: dict[str, Any], receipt: dict[str, Any]):
    next_state = dict(state)
    next_state["preview"] = dict(receipt)
    next_state["lastActivity"] = (
        "Bounded synthesis preview succeeded; review it before requesting execution."
        if receipt.get("status") == "succeeded"
        else "Bounded synthesis preview failed; inspect the receipt before execution."
    )
    activity = list(next_state.get("activity") or [])
    activity.append(
        {
            "time": "Now",
            "kind": "preview",
            "message": next_state["lastActivity"],
        }
    )
    next_state["activity"] = activity
    return gateway._synthesis_thread_store()._save_state(thread_id, next_state)


def install_synthesis_preview_gate() -> None:
    """Install once per process; idempotent across repeated imports/tests."""
    global _INSTALLED
    if _INSTALLED:
        return

    from scripts.research_data_mcp.gateway import ResearchDataGateway
    from scripts.research_data_mcp.synthesis_preview import run_bounded_preview

    current = ResearchDataGateway.synthesis_thread_submit_execution
    if getattr(current, "_synthesis_preview_gate", False):
        _INSTALLED = True
        return

    original_submit = current

    def submit_with_preview(self, thread_id: str) -> dict[str, Any]:
        thread = self._synthesis_thread_store().get(thread_id)
        state = thread.get("state") or {}
        spec = dict(state.get("execution_spec") or {})
        accepted_hash = str(state.get("accepted_spec_hash") or "")
        if not spec or not accepted_hash:
            # Preserve the canonical error semantics for unaccepted/incomplete work.
            return original_submit(self, thread_id)

        preview = state.get("preview") or {}
        current_preview = (
            preview.get("status") == "succeeded"
            and preview.get("spec_hash") == accepted_hash
        )
        if not current_preview:
            try:
                receipt = run_bounded_preview(self.repo_root, spec)
                if receipt.get("spec_hash") != accepted_hash:
                    raise ValueError(
                        "preview normalized to a different accepted synthesis revision"
                    )
            except Exception as exc:  # noqa: BLE001
                receipt = _failed_receipt(accepted_hash, exc)

            updated = _persist_preview(self, thread_id, state, receipt)
            return {
                "thread": updated,
                "preview": (updated.get("state") or {}).get("preview") or receipt,
                "preview_only": True,
                "execution_submitted": False,
                "review_required": True,
                "note": (
                    "Bounded preview recorded. No execution job was created."
                    if receipt.get("status") == "succeeded"
                    else "Bounded preview failed. No execution job was created."
                ),
            }

        submitted = original_submit(self, thread_id)
        if isinstance(submitted, dict):
            submitted = dict(submitted)
            submitted["preview"] = preview
            submitted["preview_only"] = False
            submitted["execution_submitted"] = bool(
                isinstance(submitted.get("job"), dict) and submitted["job"].get("id")
            )
        return submitted

    submit_with_preview._synthesis_preview_gate = True
    submit_with_preview._ungated_submit = original_submit
    ResearchDataGateway.synthesis_thread_submit_execution = submit_with_preview
    _INSTALLED = True
