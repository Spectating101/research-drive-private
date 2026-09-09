"""Freeze-grade authority boundary for Synthesis Preview and execution approval.

The public Synthesis execution surface has two and only two intentions:

* ``preview`` runs the accepted recipe against bounded bytes, persists a receipt,
  and can never create a worker job;
* ``request_approval`` can create/reuse the existing pending-approval job only
  when the accepted method and current input-revision fingerprint match a
  successful Preview receipt.

The job itself carries the Preview authority hash. The worker recomputes that
identity immediately before execution, so Library inputs changing after approval
cannot silently produce output from a different resolved revision.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_PREVIEW_ACTIONS = frozenset({"preview", "test", "run_preview", "rerun_preview"})
_APPROVAL_ACTIONS = frozenset({"request_approval", "approval", "submit", "execute"})


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _failed_receipt(
    spec_hash: str,
    error: Exception,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    authority = authority or {}
    return {
        "status": "failed",
        "created_at": _now(),
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


def _persist_preview(
    gateway: Any,
    thread_id: str,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    """Merge a receipt into fresh state; never overwrite a newer accepted revision."""
    store = gateway._synthesis_thread_store()
    current = store.get(thread_id)
    current_state = dict(current.get("state") or {})
    receipt_hash = str(receipt.get("spec_hash") or "")
    accepted_hash = str(current_state.get("accepted_spec_hash") or "")
    if not receipt_hash or accepted_hash != receipt_hash:
        raise ValueError(
            "accepted synthesis revision changed while Preview was running; rerun Preview"
        )

    next_state = dict(current_state)
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
    return store._save_state(thread_id, next_state)


def _preview_response(
    thread: dict[str, Any],
    preview: dict[str, Any],
    *,
    reused: bool,
) -> dict[str, Any]:
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


def _normalize_action(action: str) -> str:
    requested = str(action or "request_approval").strip().lower().replace("-", "_")
    if requested in _PREVIEW_ACTIONS:
        return "preview"
    if requested in _APPROVAL_ACTIONS:
        return "request_approval"
    raise ValueError("synthesis execution action must be preview or request_approval")


def _current_successful_preview(
    state: dict[str, Any], authority: dict[str, Any], accepted_hash: str
) -> bool:
    preview = dict(state.get("preview") or {})
    return bool(
        preview.get("status") == "succeeded"
        and preview.get("spec_hash") == accepted_hash
        and preview.get("authority_hash")
        and preview.get("authority_hash") == authority.get("authority_hash")
    )


def handle_synthesis_execution_action(
    gateway: Any,
    thread_id: str,
    *,
    action: str = "request_approval",
) -> dict[str, Any]:
    """Apply the explicit Preview/approval authority contract for one thread."""
    from scripts.research_data_mcp.synthesis_preview import (
        current_preview_authority,
        run_bounded_preview,
    )

    intent = _normalize_action(action)
    store = gateway._synthesis_thread_store()
    thread = store.get(thread_id)
    state = thread.get("state") or {}
    spec = dict(state.get("execution_spec") or {})
    accepted_hash = str(state.get("accepted_spec_hash") or "")

    if not spec or not accepted_hash:
        if intent == "request_approval":
            # Preserve the canonical submission error from the low-level submitter.
            return gateway._synthesis_thread_submit_approval(thread_id)
        raise ValueError("accept an exact synthesis method before running Preview")

    preview = dict(state.get("preview") or {})
    try:
        authority = current_preview_authority(gateway.repo_root, spec)
    except Exception as exc:  # noqa: BLE001
        if intent == "request_approval":
            raise ValueError(
                "execution approval refused: current preview input revisions cannot be verified; rerun Preview"
            ) from exc
        receipt = _failed_receipt(accepted_hash, exc)
        updated = _persist_preview(gateway, thread_id, receipt)
        durable = (updated.get("state") or {}).get("preview") or receipt
        return _preview_response(updated, durable, reused=False)

    if authority.get("spec_hash") != accepted_hash:
        raise ValueError(
            "accepted synthesis revision no longer matches the normalized execution specification"
        )

    current_preview = _current_successful_preview(state, authority, accepted_hash)

    if intent == "preview":
        # Lost-response retries remain Preview forever and never cross the approval boundary.
        if current_preview:
            return _preview_response(thread, preview, reused=True)
        try:
            receipt = run_bounded_preview(gateway.repo_root, spec)
            if receipt.get("spec_hash") != accepted_hash:
                raise ValueError("preview normalized to a different accepted synthesis revision")
            if receipt.get("authority_hash") != authority.get("authority_hash"):
                raise ValueError(
                    "preview inputs changed while the bounded preview was running; rerun Preview"
                )
        except Exception as exc:  # noqa: BLE001
            receipt = _failed_receipt(accepted_hash, exc, authority)

        updated = _persist_preview(gateway, thread_id, receipt)
        durable = (updated.get("state") or {}).get("preview") or receipt
        return _preview_response(updated, durable, reused=False)

    if not current_preview:
        stale_reason = (
            "the saved Preview belongs to different input revisions"
            if preview.get("status") == "succeeded" and preview.get("spec_hash") == accepted_hash
            else "this accepted revision has no current successful Preview"
        )
        raise ValueError(
            f"execution approval refused: {stale_reason}; run and review Preview first"
        )

    # Re-read immediately before submission so a concurrent proposal acceptance
    # cannot ride on the authority check performed above.
    fresh = store.get(thread_id)
    fresh_state = fresh.get("state") or {}
    fresh_spec = dict(fresh_state.get("execution_spec") or {})
    fresh_hash = str(fresh_state.get("accepted_spec_hash") or "")
    if fresh_hash != accepted_hash or fresh_spec != spec:
        raise ValueError(
            "execution approval refused: accepted revision changed during review; rerun Preview"
        )
    fresh_authority = current_preview_authority(gateway.repo_root, fresh_spec)
    if not _current_successful_preview(fresh_state, fresh_authority, fresh_hash):
        raise ValueError(
            "execution approval refused: Preview became stale during review; rerun Preview"
        )

    submitted = gateway._synthesis_thread_submit_approval(
        thread_id,
        expected_authority_hash=str(fresh_authority.get("authority_hash") or ""),
    )
    if isinstance(submitted, dict):
        submitted = dict(submitted)
        submitted["preview"] = dict(fresh_state.get("preview") or {})
        submitted["preview_only"] = False
        submitted["execution_submitted"] = bool(
            isinstance(submitted.get("job"), dict) and submitted["job"].get("id")
        )
    return submitted


def verify_worker_preview_authority(repo_root: Any, plan: dict[str, Any]) -> dict[str, Any]:
    """Fail closed if execution-time inputs differ from the previewed authority."""
    from scripts.research_data_mcp.synthesis_preview import current_preview_authority

    expected = str(plan.get("preview_authority_hash") or "").strip()
    accepted_hash = str(plan.get("accepted_spec_hash") or "").strip()
    spec = dict(plan.get("execution_spec") or {})
    if not expected or not accepted_hash or not spec:
        raise ValueError(
            "synthesis execution lacks preview authority; create a new reviewed execution request"
        )
    current = current_preview_authority(repo_root, spec)
    if current.get("spec_hash") != accepted_hash:
        raise ValueError("synthesis execution spec no longer matches its accepted revision")
    if current.get("authority_hash") != expected:
        raise ValueError(
            "synthesis execution inputs changed after Preview; rerun Preview and request approval again"
        )
    return current
