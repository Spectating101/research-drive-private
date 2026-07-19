#!/usr/bin/env python3
"""Research Drive chat shell — session memory + Composer desk brain only."""

from __future__ import annotations

import queue
import threading
import time
from typing import Any

from scripts.research_data_mcp.procurement_session import ProcurementSessionStore


class ProcurementChatOrchestrator:
    """Multi-turn desk UI: SQLite session state + Cursor Composer via desk_brain."""

    def __init__(self, repo_root: Any) -> None:
        from pathlib import Path

        self.sessions = ProcurementSessionStore(Path(repo_root) / "data_lake/procurement_memory/chat_sessions.sqlite3")

    def get_session(self, session_id: str) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        state = session.get("state") or {}
        return {
            "session_id": session["id"],
            "title": session.get("title"),
            "state": state,
            "candidates": state.get("candidates") or [],
            "campaign_id": state.get("campaign_id"),
            "pending_job_id": state.get("pending_job_id"),
            "last_handle": state.get("last_handle"),
            "messages": self.sessions.messages(session_id, limit=50),
        }

    @staticmethod
    def _bind_faculty_profile(state: dict[str, Any], user_email: str | None) -> None:
        from scripts.research_data_mcp.faculty_profile import normalize_email, profile_summary, resolve_profile

        if user_email:
            state["user_email"] = normalize_email(user_email)
        email = str(state.get("user_email") or "")
        if not email:
            state.pop("faculty_profile", None)
            return
        if state.get("faculty_profile", {}).get("email") == email:
            return
        row = resolve_profile(email=email)
        if row:
            state["faculty_profile"] = profile_summary(row)
            state["faculty_profile_row"] = row
        else:
            state["faculty_profile"] = {"email": email, "unknown": True}

    def _wait_for_prime_events(self, gateway: Any, session_id: str, *, timeout_seconds: int = 60):
        """Yield visible progress while a background Composer warmup is still running."""
        deadline = time.monotonic() + max(timeout_seconds, 1)
        last_notice = -10
        state: dict[str, Any] = {}
        while time.monotonic() < deadline:
            session = self.sessions.get(session_id)
            state = dict(session.get("state") or {})
            if not state.get("desk_priming"):
                return state
            elapsed = int(max(0, timeout_seconds - (deadline - time.monotonic())))
            if elapsed - last_notice >= 2:
                last_notice = elapsed
                yield {
                    "type": "progress",
                    "phase": "priming",
                    "text": "Preparing the Composer research session…",
                    "elapsed_seconds": elapsed,
                }
            time.sleep(0.5)
        session = self.sessions.get(session_id)
        return dict(session.get("state") or state)

    @staticmethod
    def _watch_composer_completion(
        orchestrator: ProcurementChatOrchestrator,
        *,
        sid: str,
        thread: threading.Thread,
        turn_queue: queue.Queue,
        state: dict[str, Any],
        message: str,
        gateway: Any,
    ) -> None:
        """Append the real Composer reply when a SLA-bounded turn finishes later."""

        def _run() -> None:
            from scripts.research_data_mcp.desk_scale import composer_sla_seconds

            thread.join(timeout=max(300.0, composer_sla_seconds() * 5))
            deadline = time.monotonic() + 30.0
            while time.monotonic() < deadline:
                try:
                    kind, payload = turn_queue.get(timeout=2.0)
                except queue.Empty:
                    continue
                if kind == "error":
                    err = str(payload or "Composer background turn failed")
                    live = dict(orchestrator.sessions.get(sid).get("state") or {})
                    live.update(state)
                    live["composer_pending"] = False
                    orchestrator.sessions.append_message(
                        sid,
                        "assistant",
                        f"Composer could not finish the pending turn: {err}",
                        artifacts={"action": "composer_error", "error": err},
                    )
                    orchestrator.sessions.update_state(sid, live)
                    return
                if kind == "event":
                    continue
                if kind != "turn":
                    continue
                turn = payload
                live = dict(orchestrator.sessions.get(sid).get("state") or {})
                live.update(state)
                live["composer_pending"] = False
                action_result = dict(turn.action_result or {})
                reply = str(turn.reply or "").strip() or "Composer finished the pending turn."
                action = str(action_result.get("action") or turn.plan.get("action") or "composer")
                action = orchestrator._infer_action_label(message, reply, action, action_result)
                action_result["action"] = action
                suggestions = turn.suggested_prompts or []
                next_steps = orchestrator._build_next_steps(live, action_result, suggestions)
                orchestrator.sessions.append_message(
                    sid,
                    "assistant",
                    reply,
                    artifacts={**action_result, "suggestions": suggestions, "next_steps": next_steps, "background_completion": True},
                )
                orchestrator.sessions.update_state(sid, live)
                return

        threading.Thread(target=_run, name=f"composer-bg-{sid[:8]}", daemon=True).start()

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
        message = message.strip()
        if not message:
            raise ValueError("message is required")

        session = self.sessions.get_or_create(session_id)
        sid = session["id"]
        state = dict(session.get("state") or {})
        self._bind_faculty_profile(state, user_email)
        if isinstance(rail_context, dict) and rail_context:
            state["rail_context"] = rail_context

        from pathlib import Path as _Path

        from scripts.research_data_mcp.desk_brain import cursor_composer_available, desk_brain_mode

        from scripts.research_data_mcp.desk_direct_turns import (
            is_direct_equipment_message,
            is_direct_probe_message,
            is_direct_status_message,
        )

        rail = rail_context if isinstance(rail_context, dict) else state.get("rail_context")
        rail_dict = rail if isinstance(rail, dict) else None
        skip_composer_priming = is_direct_equipment_message(message, rail_dict)
        direct_probe = is_direct_probe_message(message, rail_dict)
        direct_search = skip_composer_priming and not direct_probe and not is_direct_status_message(message)
        direct_status = is_direct_status_message(message)

        if not skip_composer_priming and not state.get("vault_brief"):
            from pathlib import Path

            from scripts.research_data_mcp.desk_vault_brief import build_vault_brief

            state["vault_brief"] = build_vault_brief(Path(gateway.repo_root), state.get("faculty_profile"))

        if (
            not skip_composer_priming
            and desk_brain_mode(_Path(gateway.repo_root)) == "cursor_composer"
            and cursor_composer_available()
            and not state.get("desk_primed")
            and not state.get("cursor_agent_id")
        ):
            from scripts.research_data_mcp.desk_warm import warm_desk_session

            if not state.get("desk_priming"):
                warm_desk_session(
                    gateway,
                    user_email=state.get("user_email"),
                    session_id=sid,
                    background=True,
                )
            state = yield from self._wait_for_prime_events(gateway, sid, timeout_seconds=60)
            session = self.sessions.get(sid)
            state = dict(session.get("state") or state)
            self.sessions.update_state(sid, state)
        elif not skip_composer_priming and state.get("desk_priming"):
            state = yield from self._wait_for_prime_events(gateway, sid, timeout_seconds=60)
            session = self.sessions.get(sid)
            state = dict(session.get("state") or state)

        progress_text = "Understanding your request…"
        if direct_status:
            progress_text = "Checking session status…"
        elif direct_probe:
            progress_text = "Running direct probe…"
        elif direct_search:
            progress_text = "Searching the vault…"
        self.sessions.append_message(sid, "user", message)
        yield {"type": "progress", "phase": "planning", "text": progress_text}

        turn_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

        def run_turn() -> None:
            def emit_event(event: dict[str, Any]) -> None:
                turn_queue.put(("event", event))

            try:
                live_state = dict(self.sessions.get(sid).get("state") or {})
                live_state.update(state)
                turn = self._run_agent_turn(
                    gateway, message, live_state, sid, event_sink=emit_event
                )
                state.update(live_state)
                turn_queue.put(("turn", turn))
            except Exception as exc:  # noqa: BLE001
                turn_queue.put(("error", exc))

        thread = threading.Thread(target=run_turn, name=f"procure-chat-{sid[:8]}", daemon=True)
        thread.start()
        started = time.monotonic()
        from scripts.research_data_mcp.desk_brain import AgentTurn
        from scripts.research_data_mcp.desk_scale import composer_sla_seconds

        heartbeat_texts = (
            "Starting the research tool session…",
            "Checking the lab registry and procurement memory…",
            "Composer is working with the research tools…",
            "Still working across search, query, and procurement tools…",
        )
        heartbeat_idx = 0
        streamed_answer = False
        streamed_chunks: list[str] = []
        composer_sla = 0.0 if skip_composer_priming else composer_sla_seconds()
        turn: AgentTurn | None = None
        sla_hit = False

        while turn is None and not sla_hit:
            try:
                kind, payload = turn_queue.get(timeout=2.0)
                if kind == "error":
                    raise payload
                if kind == "event":
                    event = payload if isinstance(payload, dict) else {}
                    if event.get("type") == "delta":
                        streamed_answer = True
                        chunk = str(event.get("text") or "")
                        if chunk:
                            streamed_chunks.append(chunk)
                    yield event
                    continue
                turn = payload
            except queue.Empty:
                if streamed_answer:
                    if composer_sla and time.monotonic() - started >= composer_sla:
                        sla_hit = True
                        break
                    continue
                elapsed = int(time.monotonic() - started)
                text = heartbeat_texts[min(heartbeat_idx, len(heartbeat_texts) - 1)]
                heartbeat_idx += 1
                yield {
                    "type": "progress",
                    "phase": "composing",
                    "text": text,
                    "elapsed_seconds": elapsed,
                }
                if composer_sla and time.monotonic() - started >= composer_sla:
                    sla_hit = True
                    break

        if sla_hit and turn is None:
            elapsed = int(time.monotonic() - started)
            partial = "".join(streamed_chunks).strip()
            state["composer_pending"] = True
            self.sessions.update_state(sid, state)
            self._watch_composer_completion(
                self,
                sid=sid,
                thread=thread,
                turn_queue=turn_queue,
                state=state,
                message=message,
                gateway=gateway,
            )
            reply = partial or (
                f"Composer is still working ({elapsed}s). Discover and Probe stay instant — "
                "send **status** to check this session, or keep browsing while it finishes."
            )
            turn = AgentTurn(
                plan={"action": "composer_pending"},
                action_result={
                    "action": "composer_pending",
                    "still_working": True,
                    "elapsed_seconds": elapsed,
                    "partial_reply": bool(partial),
                },
                reply=reply,
                suggested_prompts=["status", "Search vault for related datasets"],
                tool_name="cursor_composer",
            )
        elif turn is None:
            raise RuntimeError("chat turn did not complete")

        if str((turn.action_result or {}).get("action") or "") == "composer_pending":
            state["composer_pending"] = True
        else:
            state.pop("composer_pending", None)

        action_result = turn.action_result
        reply = turn.reply
        action = str(action_result.get("action") or turn.plan.get("action") or "composer")
        action = self._infer_action_label(message, reply, action, action_result)
        action_result["action"] = action
        patch = action_result.get("state_patch") if isinstance(action_result.get("state_patch"), dict) else {}
        if patch:
            state.update(patch)
        job_id = str(action_result.get("job_id") or state.get("pending_job_id") or "").strip()
        job_obj = action_result.get("job") if isinstance(action_result.get("job"), dict) else None
        if job_obj:
            job_id = str(job_obj.get("id") or job_obj.get("job_id") or job_id).strip()
            if job_obj.get("status"):
                state["job_status"] = job_obj.get("status")
        if job_id:
            state["pending_job_id"] = job_id
            action_result.setdefault("job_id", job_id)
        yield {
            "type": "progress",
            "phase": "executing",
            "action": action,
            "text": self._progress_label(action),
        }

        suggestions = turn.suggested_prompts
        next_steps = self._build_next_steps(state, action_result, suggestions)

        title = session.get("title") or ""
        if not title:
            title = message[:120]

        self.sessions.append_message(
            sid,
            "assistant",
            reply,
            artifacts={**action_result, "suggestions": suggestions, "next_steps": next_steps},
        )
        self.sessions.update_state(sid, state, title=title)

        try:
            from scripts.research_data_mcp.desk_activity import record_activity
            from scripts.research_data_mcp.desk_usage import record_composer_turn

            if action != "composer_pending":
                record_composer_turn(repo_root=getattr(gateway, "repo_root", None))
            record_activity(
                "ask",
                message[:200],
                repo_root=getattr(gateway, "repo_root", None),
                session_id=sid,
                composer_turns=1,
                meta={"action": action},
            )
        except Exception:
            pass

        yield {
            "type": "complete",
            "result": {
                "session_id": sid,
                "reply": reply,
                "action": action,
                "candidates": state.get("candidates") or [],
                "selected_index": state.get("selected_index"),
                "campaign_id": state.get("campaign_id"),
                "last_handle": state.get("last_handle"),
                "preview": action_result.get("preview"),
                "compare_table": action_result.get("compare_table"),
                "suggested_prompts": suggestions,
                "next_steps": next_steps,
                "faculty_profile": state.get("faculty_profile"),
                "artifacts": action_result,
                "job": job_obj or action_result.get("job"),
                "job_id": job_id or None,
                "pending_job_id": state.get("pending_job_id"),
                "job_status": state.get("job_status"),
                "plan": action_result.get("plan"),
                "paths": action_result.get("paths") or [],
                "procured_files": action_result.get("procured_files") or [],
            },
        }

    @staticmethod
    def _progress_label(action: str) -> str:
        labels = {
            "schedule_refresh": "Registering refresh in Discover History…",
            "create_intent": "Recording Discover intent…",
            "pause_subscription": "Pausing refresh subscription…",
            "resume_subscription": "Resuming refresh subscription…",
            "stop_subscription": "Stopping refresh subscription…",
            "composer": "Composer is working with the research tools…",
            "composer_unavailable": "Composer is not configured…",
            "composer_error": "Composer hit an error…",
            "desk_session": "Searching vault and preparing your answer…",
            "search": "Searching the lab registry…",
            "discover_search": "Searching Discover catalog…",
            "discover_collect": "Queuing Discover collection…",
            "spectator_scrape": "Queuing Spectator scrape on windows_lab…",
            "query": "Querying the selected dataset…",
            "probe_url": "Probing the public source…",
            "collect_doi": "Checking DOI acquisition state…",
            "submit_collect": "Queuing cluster collection…",
            "in_lab": "Opening existing lab holding…",
            "queue": "Submitting a collection job…",
        }
        return labels.get(action, "Working…")

    @staticmethod
    def _infer_action_label(
        message: str,
        reply: str,
        action: str,
        action_result: dict[str, Any],
    ) -> str:
        """Label Composer outcomes for UI state; Composer still chooses all tools."""
        if action and action != "composer":
            return action
        # Prefer explicit platform mutations from equipment / tools.
        if action_result.get("platform_registered") and action_result.get("subscription_id"):
            return "schedule_refresh"
        if action_result.get("subscription") and isinstance(action_result.get("subscription"), dict):
            return "schedule_refresh"
        if action_result.get("intent_id") or (
            isinstance(action_result.get("intent"), dict) and action_result.get("intent", {}).get("id")
        ):
            return "create_intent"
        text = f"{message}\n{reply}".lower()
        if "subscription" in text and any(t in text for t in ("schedule", "monday", "weekly", "refresh")):
            if "pause" in text[:200]:
                return "pause_subscription"
            if "resume" in text[:200]:
                return "resume_subscription"
            if "stop" in text[:200]:
                return "stop_subscription"
            return "schedule_refresh"
        if "create" in text[:160] and "intent" in text[:200]:
            return "create_intent"
        if action_result.get("job") or action_result.get("pending_job_id"):
            return "queue"
        if action_result.get("preview"):
            return "query"
        if "probe " in text[:80] or "probe result" in text or "probe succeeded" in text:
            return "probe_url"
        doi_like = "doi" in text or "10." in text[:180]
        if "collect " in text[:120] and doi_like:
            if "already in the vault" in text or "already vaulted" in text or (
                "in the vault" in text and ("already" in text or "checksum" in text)
            ):
                return "in_lab"
            if "queued" in text or "collection job" in text or "collected" in text:
                return "collect_doi"
        if action_result.get("result_kind") == "discover_sources" or action_result.get("action") == "discover_search":
            return "discover_search"
        if action_result.get("action") == "discover_collect" or action_result.get("result_kind") == "discover_collect":
            return "discover_collect"
        if action_result.get("action") == "spectator_scrape":
            return "spectator_scrape"
        if "discover catalog" in text or "source_id" in text and "access" in text:
            if any(tkn in text[:200] for tkn in ("discover", "catalog", "source")):
                return "discover_search"
        if any(token in text[:160] for token in ("what ", "find ", "search ", "which ", "do we have")):
            return "search"
        return "composer"

    def _run_agent_turn(
        self,
        gateway: Any,
        message: str,
        state: dict[str, Any],
        session_id: str,
        event_sink: Any = None,
    ):
        from scripts.research_data_mcp.desk_brain import run_desk_agent_turn

        return run_desk_agent_turn(
            self, gateway, message, state, session_id=session_id, event_sink=event_sink
        )

    @staticmethod
    def _build_next_steps(
        state: dict[str, Any],
        action_result: dict[str, Any],
        suggestions: list[str],
    ) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        for prompt in suggestions[:3]:
            steps.append({"label": prompt[:80], "prompt": prompt, "kind": "chat"})
        if state.get("pending_job_id"):
            steps.append({"label": "Check job progress", "prompt": "status", "kind": "status"})
        paths = action_result.get("paths") or []
        if paths:
            steps.append({"label": "Open collected file", "path": paths[0], "kind": "artifact"})
        return steps[:4]
