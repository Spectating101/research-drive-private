#!/usr/bin/env python3
"""Apply the freeze-grade Synthesis Preview authority integration atomically.

This script exists only to make large-file edits through exact source assertions.
It refuses ambiguous/drifted source shapes instead of guessing. The freeze
workflow commits the resulting product changes, after which this staging script
can be removed.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> bool:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if new in text:
        return False
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one guarded fragment, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


def main() -> None:
    changed = []

    gateway = "drive/scripts/research_data_mcp/gateway.py"
    if replace_once(
        gateway,
        '    def synthesis_thread_submit_execution(self, thread_id: str) -> dict:\n        """Submit an accepted, bounded execution spec for researcher approval."""',
        '    def _synthesis_thread_submit_approval(self, thread_id: str) -> dict:\n        """Low-level pending-approval submitter; public authority lives above this."""',
    ):
        changed.append(gateway)
    if replace_once(
        gateway,
        '            "accepted_spec_hash": accepted_hash,\n            "dataset_id": spec["output_dataset_id"],',
        '            "accepted_spec_hash": accepted_hash,\n            "preview_spec_hash": str((state.get("preview") or {}).get("spec_hash") or ""),\n            "preview_authority_hash": str((state.get("preview") or {}).get("authority_hash") or ""),\n            "preview_input_revisions": list((state.get("preview") or {}).get("input_revisions") or []),\n            "dataset_id": spec["output_dataset_id"],',
    ):
        changed.append(gateway)
    if replace_once(
        gateway,
        '        return submitted\n\n    def synthesis_thread_link_conversation(\n',
        '        return submitted\n\n    def synthesis_thread_submit_execution(\n        self, thread_id: str, action: str = "request_approval"\n    ) -> dict:\n        """Run bounded Preview or request approval for that exact previewed revision."""\n        from scripts.research_data_mcp.synthesis_execution_authority import (\n            handle_synthesis_execution_action,\n        )\n\n        return handle_synthesis_execution_action(self, thread_id, action=action)\n\n    def synthesis_thread_link_conversation(\n',
    ):
        changed.append(gateway)

    router = "drive/scripts/research_data_mcp/http_router.py"
    if replace_once(
        router,
        '    def library_synthesis_thread_execute(stack, query, payload, params):\n        return stack.gateway.synthesis_thread_submit_execution(params["thread_id"])',
        '    def library_synthesis_thread_execute(stack, query, payload, params):\n        action = str((payload or {}).get("action") or "request_approval").strip()\n        return stack.gateway.synthesis_thread_submit_execution(\n            params["thread_id"], action=action\n        )',
    ):
        changed.append(router)

    handlers = "drive/scripts/research_data_mcp/tool_handlers.py"
    if replace_once(
        handlers,
        '''    def research_synthesis_submit_execution(self, thread_id: str) -> dict[str, Any]:
        """Queue accepted execution_spec as pending_approval. Agent cannot approve it."""
        out = self.gateway.synthesis_thread_submit_execution(thread_id)
        job = out.get("job") if isinstance(out, dict) else None
        return {
            **(out if isinstance(out, dict) else {"result": out}),
            "review_required": True,
            "agent_may_approve_synthesis": False,
            "note": "Submitted for researcher desk approval only — Composer cannot approve synthesis_execute.",
            "job_id": (job or {}).get("id") if isinstance(job, dict) else None,
            "job_status": (job or {}).get("status") if isinstance(job, dict) else None,
        }''',
        '''    def research_synthesis_submit_execution(
        self, thread_id: str, action: str = "request_approval"
    ) -> dict[str, Any]:
        """Run bounded Preview or request approval for the exact previewed revision.

        Preview can never create a job. Approval remains researcher-only and is
        refused unless the accepted method and current input revisions match the
        successful Preview receipt.
        """
        intent = str(action or "request_approval").strip()
        out = self.gateway.synthesis_thread_submit_execution(thread_id, action=intent)
        job = out.get("job") if isinstance(out, dict) else None
        preview_only = bool(isinstance(out, dict) and out.get("preview_only"))
        return {
            **(out if isinstance(out, dict) else {"result": out}),
            "review_required": True,
            "agent_may_approve_synthesis": False,
            "note": (
                "Bounded Preview only — no execution job was created."
                if preview_only
                else "Submitted for researcher desk approval only — Composer cannot approve synthesis_execute."
            ),
            "job_id": (job or {}).get("id") if isinstance(job, dict) else None,
            "job_status": (job or {}).get("status") if isinstance(job, dict) else None,
        }''',
    ):
        changed.append(handlers)

    executor = "drive/scripts/yzu_cluster/executor.py"
    if replace_once(
        executor,
        '''    def _synthesis_execute(self, job_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        from scripts.research_data_mcp.synthesis_executor import execute
        return execute(self.repo_root, job_id, plan)''',
        '''    def _synthesis_execute(self, job_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        from scripts.research_data_mcp.synthesis_execution_authority import (
            verify_worker_preview_authority,
        )
        from scripts.research_data_mcp.synthesis_executor import execute

        # Approval authorizes the exact Previewed bytes, not whatever happens to
        # resolve later. Re-check immediately before the production executor.
        verify_worker_preview_authority(self.repo_root, plan)
        return execute(self.repo_root, job_id, plan)''',
    ):
        changed.append(executor)

    store = "drive/scripts/research_data_mcp/synthesis_thread_store.py"
    if replace_once(
        store,
        '''        # A new accepted spec starts a new execution revision; it must never inherit
        # the registered/pending state of an earlier output.
        next_state["execution"] = {''',
        '''        # A new accepted spec starts a new execution revision. A Preview is
        # revision-bound evidence and must never survive acceptance of a new spec.
        next_state.pop("preview", None)
        # It must also never inherit registered/pending state from an earlier output.
        next_state["execution"] = {''',
    ):
        changed.append(store)

    tests = "tests/test_synthesis_thread_state.py"
    if replace_once(
        tests,
        'def test_synthesis_submit_uses_server_internal_scope_but_never_auto_approves(',
        'def test_synthesis_low_level_submit_uses_server_internal_scope_but_never_auto_approves(',
    ):
        changed.append(tests)
    if replace_once(
        tests,
        '    result = stack.gateway.synthesis_thread_submit_execution(thread["id"])\n\n    assert observed["request"]["_ops_internal"] is True',
        '    # This test owns the lower-level submitter. Preview/approval authority\n    # is pinned separately in test_synthesis_preview_freeze_authority.py.\n    result = stack.gateway._synthesis_thread_submit_approval(thread["id"])\n\n    assert observed["request"]["_ops_internal"] is True',
    ):
        changed.append(tests)

    print("patched:", ", ".join(dict.fromkeys(changed)) if changed else "already applied")


if __name__ == "__main__":
    main()
