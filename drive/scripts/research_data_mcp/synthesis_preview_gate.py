"""Install the bounded-preview authority gate on Synthesis execution submission.

Preview and approval are deliberately separate researcher intentions even though
both still converge on ResearchDataGateway.synthesis_thread_submit_execution().
The caller must choose an action:

* ``preview`` executes/persists bounded evidence and can NEVER create a job;
* ``request_approval`` can create the existing pending-approval job, but only
  when the exact accepted method AND its current input revisions have a
  successful preview receipt.

This separation is an idempotency/safety boundary. If a successful Preview HTTP
response is lost, repeating the visible Preview action remains a Preview and
cannot silently become an execution-approval request.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_INSTALLED = False
_PREVIEW_ACTIONS = frozenset({"preview", "test", "run_preview", "rerun_preview"})
_APPROVAL_ACTIONS = frozenset({"request_approval", "approval", "submit", "execute"})


def _failed_receipt(
    spec_hash: str,
    error: Exception,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    authority = authority or {}
    return {
        "status": "failed",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "spec_hash": spec_hash,
        **(
            {"authority_hash": authority.get("authority_hash")}
            if authority.get("authority_hash")
            else {}
        ),
        **(
            {"input_revisions": authority.get("input_revisions")}
            if authority.get("input_revisions")
            else {}
        ),
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


def _preview_response(thread: dict[str, Any], preview: dict[str, Any], *, reused: bool) -> dict[str, Any]:
    return {
        "thread": thread,
        "preview": preview,
        "preview_only": True,
        "execution_submitted": False,
        "review_required": True,
        "preview_reused": reused,
        "note": (
            "Current bounded preview returned. No execution job was created."
            if reused and preview.get("status") == "succeeded"
            else "Bounded preview recorded. No execution job was created."
            if preview.get("status") == "succeeded"
            else "Bounded preview failed. No execution job was created."
        ),
    }


def install_synthesis_preview_gate() -> None:
    """Install once per process; idempotent across repeated imports/tests."""
    global _INSTALLED
    if _INSTALLED:
        return

    from scripts.research_data_mcp.gateway import ResearchDataGateway
    from scripts.research_data_mcp.synthesis_preview import (
        current_preview_authority,
        run_bounded_preview,
    )

    current = ResearchDataGateway.synthesis_thread_submit_execution
    if getattr(current, "_synthesis_preview_gate", False):
        _INSTALLED = True
        return

    original_submit = current

    def submit_with_preview(
        self,
        thread_id: str,
        action: str = "request_approval",
    ) -> dict[str, Any]:
        requested_action = str(action or "request_approval").strip().lower().replace("-", "_")
        if requested_action in _PREVIEW_ACTIONS:
            intent = "preview"
        elif requested_action in _APPROVAL_ACTIONS:
            intent = "request_approval"
        else:
            raise ValueError("synthesis execution action must be preview or request_approval")

        thread = self._synthesis_thread_store().get(thread_id)
        state = thread.get("state") or {}
        spec = dict(state.get("execution_spec") or {})
        accepted_hash = str(state.get("accepted_spec_hash") or "")
        if not spec or not accepted_hash:
            # Preserve the canonical submission error on the approval path. A
            # Preview cannot exist before an exact method revision is accepted.
            if intent == "request_approval":
                return original_submit(self, thread_id)
            raise ValueError("accept an exact synthesis method before running Preview")

        preview = dict(state.get("preview") or {})
        try:
            authority = current_preview_authority(self.repo_root, spec)
        except Exception as exc:  # noqa: BLE001
            if intent == "request_approval":
                raise ValueError(
                    "execution approval refused: current preview input revisions cannot be verified; rerun Preview"
                ) from exc
            receipt = _failed_receipt(accepted_hash, exc)
            updated = _persist_preview(self, thread_id, state, receipt)
            durable = (updated.get("state") or {}).get("preview") or receipt
            return _preview_response(updated, durable, reused=False)

        if authority.get("spec_hash") != accepted_hash:
            raise ValueError(
                "accepted synthesis revision no longer matches the normalized execution specification"
            )

        current_preview = (
            preview.get("status") == "succeeded"
            and preview.get("spec_hash") == accepted_hash
            and bool(preview.get("authority_hash"))
            and preview.get("authority_hash") == authority.get("authority_hash")
        )

        if intent == "preview":
            # Idempotent retry: a lost Preview response can be repeated forever
            # without crossing into Approval or creating a job.
            if current_preview:
                return _preview_response(thread, preview, reused=True)
            try:
                receipt = run_bounded_preview(self.repo_root, spec)
                if receipt.get("spec_hash") != accepted_hash:
                    raise ValueError(
                        "preview normalized to a different accepted synthesis revision"
                    )
                if receipt.get("authority_hash") != authority.get("authority_hash"):
                    raise ValueError(
                        "preview inputs changed while the bounded preview was running; rerun Preview"
                    )
            except Exception as exc:  # noqa: BLE001
                receipt = _failed_receipt(accepted_hash, exc, authority)

            updated = _persist_preview(self, thread_id, state, receipt)
            durable = (updated.get("state") or {}).get("preview") or receipt
            return _preview_response(updated, durable, reused=False)

        # Approval is a separate authority boundary. It may never silently run a
        # Preview on behalf of the researcher or accept a receipt from old bytes.
        if not current_preview:
            stale_reason = (
                "the saved Preview belongs to different input revisions"
                if preview.get("status") == "succeeded" and preview.get("spec_hash") == accepted_hash
                else "this accepted revision has no current successful Preview"
            )
            raise ValueError(
                f"execution approval refused: {stale_reason}; run and review Preview first"
            )

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
