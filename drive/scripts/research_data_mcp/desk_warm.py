#!/usr/bin/env python3
"""Pre-warm desk Composer sessions so the first faculty message skips vault discovery."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any


def build_prime_prompt(brief: str) -> str:
    b = brief.strip()
    return (
        "Internal desk setup (not shown to the faculty user).\n\n"
        f"{b}\n\n"
        "Session rules: answer faculty in normal short prose; no file paths or registry ids "
        "unless they ask for technical detail; do not call collection_status or vault inventory "
        "tools — the brief above is authoritative.\n\n"
        "Reply with exactly: Ready"
    )


def prime_desk_agent(gateway: Any, state: dict[str, Any], session_id: str) -> bool:
    """Create a Composer agent and load the vault brief. Mutates state in place."""
    from scripts.research_data_mcp.desk_brain import cursor_composer_available, run_cursor_composer_turn

    if state.get("desk_primed") and state.get("cursor_agent_id"):
        return True
    if not cursor_composer_available():
        return False

    brief = str(state.get("vault_brief") or "").strip()
    if not brief:
        from scripts.research_data_mcp.desk_vault_brief import build_vault_brief

        brief = build_vault_brief(Path(gateway.repo_root), state.get("faculty_profile"))
        state["vault_brief"] = brief

    turn = run_cursor_composer_turn(
        gateway,
        build_prime_prompt(brief),
        state,
        session_id=session_id,
        prime=True,
    )
    action = str(turn.action_result.get("action") or "")
    if action in {"composer_error", "composer_unavailable"}:
        return False
    state["desk_primed"] = True
    state.pop("desk_priming", None)
    return bool(state.get("cursor_agent_id"))


def warm_desk_session(
    gateway: Any,
    *,
    user_email: str | None = None,
    session_id: str | None = None,
    background: bool = True,
) -> dict[str, Any]:
    """Return a session id and optionally prime Composer in the background."""
    orch = gateway._procurement_chat_orchestrator()
    session = orch.sessions.get_or_create(session_id)
    sid = session["id"]
    state = dict(session.get("state") or {})

    from scripts.research_data_mcp.procurement_chat import ProcurementChatOrchestrator

    ProcurementChatOrchestrator._bind_faculty_profile(state, user_email)
    if not state.get("vault_brief"):
        from scripts.research_data_mcp.desk_vault_brief import build_vault_brief

        state["vault_brief"] = build_vault_brief(Path(gateway.repo_root), state.get("faculty_profile"))

    from scripts.research_data_mcp.desk_brain import cursor_composer_available

    if state.get("desk_primed") and state.get("cursor_agent_id"):
        orch.sessions.update_state(sid, state)
        return {"session_id": sid, "primed": True, "priming": False}

    if state.get("desk_priming"):
        orch.sessions.update_state(sid, state)
        return {"session_id": sid, "primed": False, "priming": True, "composer": True}

    if not cursor_composer_available():
        orch.sessions.update_state(sid, state)
        return {"session_id": sid, "primed": False, "priming": False, "composer": False}

    if background:

        def _run() -> None:
            local = dict(state)
            try:
                prime_desk_agent(gateway, local, sid)
            finally:
                local.pop("desk_priming", None)
                orch.sessions.update_state(sid, local)

        state["desk_priming"] = True
        orch.sessions.update_state(sid, state)
        threading.Thread(target=_run, name=f"desk-warm-{sid[:8]}", daemon=True).start()
        return {"session_id": sid, "primed": False, "priming": True, "composer": True}

    ok = prime_desk_agent(gateway, state, sid)
    orch.sessions.update_state(sid, state)
    return {"session_id": sid, "primed": ok, "priming": False, "composer": True}


def wait_for_desk_prime(gateway: Any, session_id: str, *, timeout_seconds: int = 45) -> dict[str, Any]:
    """Block until background priming finishes or timeout."""
    import time

    orch = gateway._procurement_chat_orchestrator()
    deadline = time.monotonic() + max(timeout_seconds, 1)
    while time.monotonic() < deadline:
        session = orch.sessions.get(session_id)
        state = dict(session.get("state") or {})
        if not state.get("desk_priming"):
            return state
        time.sleep(0.5)
    session = orch.sessions.get(session_id)
    return dict(session.get("state") or {})
