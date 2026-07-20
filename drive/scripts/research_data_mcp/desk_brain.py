#!/usr/bin/env python3
"""Research Drive desk — same pattern as Cursor: Composer + project rules + MCP tools."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


from collections.abc import Callable
from typing import TypeAlias
from sharpe_kernel.paths import repo_root_from_file

DeskEventSink: TypeAlias = Callable[[dict[str, Any]], None]


@dataclass
class AgentTurn:
    plan: dict[str, Any]
    action_result: dict[str, Any]
    reply: str
    suggested_prompts: list[str] = field(default_factory=list)
    tool_name: str = ""


_TOOL_ACTIVITY_LABELS: dict[str, str] = {
    "collection_status": "Checking the vault…",
    "research_discover_search": "Searching Discover catalog…",
    "research_discover_source_search": "Searching Discover sources…",
    "research_describe_dataset": "Reading dataset details…",
    "research_query_dataset": "Querying a dataset…",
    "research_analyze_dataset": "Analyzing sample rows…",
    "research_synthesis_list_profiles": "Listing synthesis profiles…",
    "research_synthesis_run": "Synthesizing multi-source panel…",
    "research_synthesis_pair": "Comparing dataset join overlap…",
    "research_synthesis_propose_state": "Recording synthesis proposal…",
    "research_synthesis_preflight_spec": "Preflighting execution spec…",
    "research_synthesis_discover_handoff": "Building Discover handoff…",
    "research_synthesis_collect_missing": "Collecting missing evidence…",
    "research_synthesis_materialisation": "Checking synthesis materialisation…",
    "research_synthesis_submit_execution": "Submitting synthesis for approval…",
    "research_collection_hydrate": "Pulling files from Drive…",
    "yzu_submit_job": "Submitting collection job…",
    "datacite_collect_doi": "Collecting dataset…",
    "research_quant_brief": "Building quant summary…",
    "procurement_probe_public_source": "Probing source…",
}


def _emit_event(sink: DeskEventSink | None, event: dict[str, Any]) -> None:
    if not sink:
        return
    try:
        sink(event)
    except Exception:
        pass


def _interaction_payload(update: Any) -> dict[str, Any]:
    if isinstance(update, dict):
        return update
    out: dict[str, Any] = {"type": str(getattr(update, "type", "") or "")}
    for key in ("text", "call_id", "tool_call", "thinking_duration_ms"):
        val = getattr(update, key, None)
        if val is not None:
            out[key] = val
    return out


EMPTY_REPLY_FALLBACK = (
    "I looked at the request but did not get a final answer back — "
    "please try rephrasing or ask for a specific dataset or market."
)


def is_empty_desk_reply(text: str) -> bool:
    msg = (text or "").strip()
    return not msg or msg == EMPTY_REPLY_FALLBACK


def _reply_from_run(run: Any, streamed: list[str]) -> str:
    """Best-effort final assistant text — run.text() is sometimes empty after tool turns."""
    reply = (run.text() or "").strip()
    if reply:
        return reply
    if streamed:
        reply = "".join(streamed).strip()
        if reply:
            return reply
    chunks: list[str] = []
    try:
        for turn in run.conversation():
            for step in getattr(turn, "steps", ()) or ():
                msg = getattr(step, "message", None)
                if msg is None:
                    continue
                mtype = str(getattr(msg, "type", "") or "")
                if mtype not in {"assistant", "text", "assistant_message"}:
                    continue
                text = getattr(msg, "text", None) or getattr(msg, "content", None)
                if text:
                    chunks.append(str(text))
    except Exception:
        pass
    return "".join(chunks).strip()


def _tool_activity_label(tool_name: str) -> str:
    name = str(tool_name or "").strip()
    if not name:
        return ""
    if name in _TOOL_ACTIVITY_LABELS:
        return _TOOL_ACTIVITY_LABELS[name]
    readable = name.removeprefix("research_").replace("_", " ")
    return f"Using {readable}…"


def _load_magic_chat(repo_root: Path | None = None) -> dict[str, Any]:
    from scripts.research_data_mcp.magic_config import load_magic_config

    root = repo_root or repo_root_from_file(__file__)
    return dict(load_magic_config(root).get("chat") or {})


def cursor_composer_available() -> bool:
    """True only when Composer can actually run — key present *and* cursor_sdk importable.

    Health used to report composer_configured from the key alone, which masked
    ModuleNotFoundError on Ask when the front door ran on system Python.
    """
    if not os.getenv("CURSOR_API_KEY", "").strip():
        return False
    try:
        import cursor_sdk  # noqa: F401
    except ImportError:
        return False
    return True


def desk_brain_mode(repo_root: Path | None = None) -> str:
    _ = repo_root
    return "cursor_composer"


def _repo_python(repo_root: Path) -> str:
    venv = repo_root / ".venv/bin/python"
    if venv.is_file():
        return str(venv)
    return os.getenv("PYTHON", "python3")


def _desk_pythonpath(repo_root: Path) -> str:
    parts = [
        str(repo_root),
        str(repo_root / "kernel"),
        str(repo_root / "drive"),
        str(repo_root / "alpha"),
    ]
    existing = os.environ.get("PYTHONPATH", "").strip()
    if existing:
        parts.append(existing)
    return os.pathsep.join(dict.fromkeys(parts))


def _mcp_stdio_config(repo_root: Path, *, vault_primed: bool = False) -> dict[str, Any]:
    from cursor_sdk.types import StdioMcpServerConfig

    env = {k: v for k, v in os.environ.items() if isinstance(v, str)}
    env["PYTHONPATH"] = _desk_pythonpath(repo_root)
    env["SHARPE_REPO_ROOT"] = str(repo_root)
    env["RESEARCH_MCP_DESK"] = "1"
    if vault_primed:
        env["RESEARCH_MCP_VAULT_PRIMED"] = "1"
    return {
        "research_procurement": StdioMcpServerConfig(
            command=_repo_python(repo_root),
            args=["-m", "scripts.research_data_mcp.server", "--transport", "stdio"],
            cwd=str(repo_root),
            env=env,
        )
    }


def _faculty_starter_prompts(state: dict[str, Any]) -> list[str]:
    row = state.get("faculty_profile_row") or {}
    out: list[str] = []
    for item in (row.get("lab_fintech_stack") or [])[:4]:
        p = str(item.get("prompt") or "").strip()
        if p:
            out.append(p[:120])
    return out[:5]


def _desk_setting_sources() -> list[str]:
    raw = os.getenv("DESK_SETTING_SOURCES", "project").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _desk_local_options(repo_root: Path) -> Any:
    from cursor_sdk.types import LocalAgentOptions

    sources = _desk_setting_sources()
    if sources:
        return LocalAgentOptions(cwd=str(repo_root), setting_sources=sources)
    return LocalAgentOptions(cwd=str(repo_root))


def _desk_composer_models() -> list[str]:
    primary = os.getenv("DESK_COMPOSER_MODEL", "default").strip() or "default"
    fallback = os.getenv("DESK_COMPOSER_MODEL_FALLBACK", "composer-2.5").strip()
    models = [primary]
    if fallback and fallback not in models:
        models.append(fallback)
    return models


def _desk_agent_runtime_kwargs(repo_root: Path) -> dict[str, Any]:
    """Cloud agents use CURSOR_API_KEY only (headless desk). Local needs Cursor IDE bridge."""
    if os.getenv("DESK_COMPOSER_LOCAL", "").strip().lower() in {"1", "true", "yes"}:
        return {"local": _desk_local_options(repo_root)}
    from cursor_sdk.types import CloudAgentOptions

    return {"cloud": CloudAgentOptions()}


def _artifacts_from_conversation(run: Any) -> dict[str, Any]:
    """Optional UI enrichments from tool results — best-effort, not scripted."""
    action_result: dict[str, Any] = {"action": "composer"}
    state_patch: dict[str, Any] = {}
    preview = None
    action_rank = {
        "composer": 0,
        "search": 10,
        "query": 15,
        "probe_url": 20,
        "collect_doi": 30,
        "queue": 40,
        "collect": 45,
    }

    def set_action(action: str) -> None:
        current = str(action_result.get("action") or "composer")
        if action_rank.get(action, 0) >= action_rank.get(current, 0):
            action_result["action"] = action

    try:
        for turn in run.conversation():
            for step in getattr(turn, "steps", ()) or ():
                msg = getattr(step, "message", None)
                if msg is None:
                    continue
                mtype = str(getattr(msg, "type", "") or "")
                if mtype != "tool_call":
                    continue
                name = str(getattr(msg, "name", "") or "")
                result = getattr(msg, "result", None)
                if not result:
                    continue
                payload: Any = result
                if isinstance(result, str):
                    try:
                        payload = json.loads(result)
                    except json.JSONDecodeError:
                        payload = None
                if not isinstance(payload, dict):
                    continue
                if name in (
                    "research_discover_search",
                    "research_discover_source_search",
                    "research_unified_search",
                ):
                    is_discover_catalog = (
                        name == "research_discover_source_search"
                        or payload.get("result_kind") == "discover_sources"
                        or any(
                            isinstance(sec, dict) and sec.get("id") == "discover_sources"
                            for sec in (payload.get("sections") or [])
                        )
                        or any(
                            isinstance(row, dict) and row.get("source_id")
                            for row in (payload.get("results") or [])[:3]
                        )
                    )
                    set_action("discover_search" if is_discover_catalog else "search")
                    cands = []
                    raw_cands = payload.get("discover", {}).get("candidates") or payload.get("candidates") or []
                    if raw_cands:
                        cands = list(raw_cands)
                    else:
                        if payload.get("results") and is_discover_catalog:
                            cands = list(payload.get("results") or [])
                        for sec in payload.get("sections") or []:
                            for row in sec.get("rows") or []:
                                cands.append(row)
                    if not cands and "rows" in payload:
                        cands = list(payload["rows"])

                    if cands:
                        cleaned_cands = []
                        for i, c in enumerate(cands[:8], 1):
                            cand = dict(c)
                            cand.setdefault("index", i)
                            if "open_handle" in cand and not cand.get("collect_via"):
                                handle = cand["open_handle"]
                                if handle.startswith("dataset:"):
                                    cand.setdefault("collect_via", "local_open")
                                    cand.setdefault("trust_tier", "fully_ready")
                                elif handle.startswith("doi:"):
                                    cand.setdefault("collect_via", "datacite")
                                    cand.setdefault("trust_tier", "acquisition_route")
                                elif handle.startswith("hf:"):
                                    cand.setdefault("collect_via", "huggingface")
                                    cand.setdefault("trust_tier", "acquisition_route")
                            cand.setdefault("title", cand.get("name") or cand.get("id") or "Dataset")
                            cand.setdefault("doi", cand.get("id") if cand.get("kind") == "datacite" else "")
                            cand.setdefault("collect_via", cand.get("source") or "none")
                            cand.setdefault("trust_tier", "acquisition_route" if cand.get("collect_via") != "none" else "metadata_only")
                            cleaned_cands.append(cand)
                        state_patch["candidates"] = cleaned_cands
                if name == "research_query_dataset" and not preview:
                    set_action("query")
                    rows = payload.get("rows") or payload.get("data") or []
                    if rows and isinstance(rows[0], dict):
                        preview = {
                            "kind": "table",
                            "columns": list(rows[0].keys())[:12],
                            "rows": rows[:5],
                        }
                if name == "research_analyze_dataset" and isinstance(payload.get("sample_rows"), list):
                    set_action("query")
                    sr = payload["sample_rows"]
                    if sr and isinstance(sr[0], dict):
                        preview = {
                            "kind": "table",
                            "columns": list(sr[0].keys())[:12],
                            "rows": sr[:5],
                        }
                if name in (
                    "research_synthesis_run",
                    "research_synthesis_list_profiles",
                    "research_synthesis_pair",
                    "research_synthesis_propose_state",
                    "research_synthesis_preflight_spec",
                    "research_synthesis_discover_handoff",
                    "research_synthesis_collect_missing",
                    "research_synthesis_materialisation",
                    "research_synthesis_submit_execution",
                ):
                    summary = payload.get("summary") or {}
                    samples = payload.get("panel_samples") or payload.get("entities") or []
                    if summary or samples:
                        action_result["synthesis"] = {
                            "profile_id": payload.get("profile_id"),
                            "type": payload.get("type"),
                            "summary": summary,
                            "samples": samples[:5],
                            "artifacts": payload.get("artifacts") or {},
                        }
                        if samples and isinstance(samples[0], dict):
                            preview = {
                                "kind": "table",
                                "columns": list(samples[0].keys())[:12],
                                "rows": samples[:5],
                            }
                        elif summary:
                            preview = {
                                "kind": "kv",
                                "rows": [{"metric": k, "value": v} for k, v in list(summary.items())[:10]],
                            }
                if name == "research_synthesis_propose_state":
                    proposal = payload.get("synthesis_proposal")
                    if isinstance(proposal, dict):
                        action_result["synthesis_proposal"] = proposal
                        action_result["synthesis_thread_id"] = payload.get("thread_id")
                if name == "procurement_probe_public_source":
                    set_action("probe_url")
                    action_result["probe"] = payload
                    if payload.get("connector"):
                        action_result["connector"] = payload.get("connector")
                if name == "datacite_collect_doi":
                    set_action("collect_doi")
                    for key in ("campaign_id", "doi", "dataset_id", "paths", "procured_files"):
                        if payload.get(key) is not None:
                            action_result[key] = payload.get(key)
                    if payload.get("job"):
                        action_result["job"] = payload.get("job")
                if name == "yzu_submit_job":
                    set_action("queue")
                    job = payload.get("job") if isinstance(payload.get("job"), dict) else payload
                    if isinstance(job, dict):
                        action_result["job"] = job
                        job_id = job.get("id") or job.get("job_id")
                        status = job.get("status")
                        if job_id:
                            state_patch["pending_job_id"] = job_id
                        if status:
                            state_patch["job_status"] = status
                    if payload.get("campaign_id"):
                        action_result["campaign_id"] = payload.get("campaign_id")
    except Exception:
        pass
    if state_patch:
        action_result["state_patch"] = state_patch
    if preview:
        action_result["preview"] = preview
    return action_result


def _format_rail_context(ctx: dict[str, Any]) -> str:
    """Compact UI envelope for Composer — matches RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT."""
    if not isinstance(ctx, dict) or not ctx:
        return ""
    entity = ctx.get("entity") if isinstance(ctx.get("entity"), dict) else {}
    lines = ["[UI rail context]"]
    for key in (
        "tab", "mode", "thread_id", "session_id", "conversation_id", "dataset_id",
        "folder_id", "search_query", "readiness", "vault_path",
    ):
        val = ctx.get(key)
        if val:
            lines.append(f"- {key}: {str(val)[:240]}")
    if entity.get("kind"):
        lines.append(
            f"- entity: {entity.get('kind')} · {entity.get('title') or entity.get('id') or ''}"[:280]
        )
    actions = ctx.get("actions")
    if isinstance(actions, list) and actions:
        lines.append(f"- actions: {', '.join(str(a) for a in actions[:8])}")
    compare = ctx.get("compare")
    if isinstance(compare, dict) and compare.get("left") and compare.get("right"):
        lines.append(f"- compare: {compare.get('left')} × {compare.get('right')}")
    return "\n".join(lines) + "\n\n"


def run_cursor_composer_turn(
    gateway: Any,
    message: str,
    state: dict[str, Any],
    *,
    session_id: str = "",
    event_sink: DeskEventSink | None = None,
    prime: bool = False,
) -> AgentTurn:
    """Composer chooses tools freely via procurement MCP."""
    repo_root = Path(gateway.repo_root).resolve()
    api_key = os.getenv("CURSOR_API_KEY", "").strip()
    if not api_key:
        return AgentTurn(
            plan={"action": "composer_unavailable"},
            action_result={"action": "composer_unavailable", "error": "missing CURSOR_API_KEY"},
            reply=(
                "The research desk runs on Cursor Composer with the procurement tool library. "
                "Ask the lab operator to set CURSOR_API_KEY in .env.local, then try again."
            ),
            suggested_prompts=_faculty_starter_prompts(state),
            tool_name="",
        )
    from cursor_sdk import Agent
    from cursor_sdk.types import AgentOptions, ModelSelection, SendOptions

    model_candidates = _desk_composer_models()
    agent_id = str(state.get("cursor_agent_id") or "").strip()
    had_agent = bool(agent_id)
    user_text = message.strip()
    rail_prefix = _format_rail_context(state.get("rail_context") or {})
    if rail_prefix and rail_prefix not in user_text:
        user_text = rail_prefix + user_text
    vault_primed_env = False
    if prime:
        pass
    elif not had_agent and not state.get("desk_primed"):
        from scripts.research_data_mcp.desk_vault_brief import build_vault_brief, wrap_first_turn_message

        brief = str(state.get("vault_brief") or "").strip()
        if not brief:
            brief = build_vault_brief(repo_root, state.get("faculty_profile"))
            state["vault_brief"] = brief
        user_text = wrap_first_turn_message(brief, user_text)
        vault_primed_env = True
    mcp_servers = _mcp_stdio_config(repo_root, vault_primed=vault_primed_env)

    try:
        streamed: list[str] = []
        run = None
        reply = ""
        model_id = model_candidates[0]

        def on_delta(update: Any) -> None:
            payload = _interaction_payload(update)
            typ = str(payload.get("type") or "")
            if typ == "text-delta":
                chunk = str(payload.get("text") or "")
                if chunk:
                    streamed.append(chunk)
                    _emit_event(event_sink, {"type": "delta", "text": chunk})
                return
            if typ == "tool-call-started":
                tool_call = payload.get("tool_call") or {}
                name = str(tool_call.get("name") or tool_call.get("toolName") or "")
                label = _tool_activity_label(name)
                if label:
                    _emit_event(event_sink, {"type": "activity", "text": label})

        send_opts = SendOptions(mcp_servers=mcp_servers, on_delta=on_delta)

        for model_idx, model_id in enumerate(model_candidates):
            agent_opts = AgentOptions(
                model=ModelSelection(id=model_id),
                api_key=api_key,
                name=f"research-desk-{session_id[:8] or 'anon'}",
                mcp_servers=mcp_servers,
                **_desk_agent_runtime_kwargs(repo_root),
            )
            resume_id = agent_id if model_idx == 0 else ""
            if resume_id:
                agent = Agent.resume(resume_id, agent_opts)
            else:
                agent = Agent.create(agent_opts)
                state["cursor_agent_id"] = agent.agent_id
                agent_id = agent.agent_id

            with agent:
                turn_text = user_text
                for attempt in range(2):
                    streamed.clear()
                    run = agent.send(turn_text, send_opts)
                    run.wait()
                    reply = _reply_from_run(run, streamed)
                    if reply or prime or attempt == 1:
                        break
                    turn_text = f"{message.strip()}\n\n(Please answer in plain prose for the faculty user.)"

            is_model_error = (
                run is None
                or getattr(run, "status", "") == "error"
                or (not reply and not prime)
            )
            if not is_model_error or model_idx == len(model_candidates) - 1:
                break
            if had_agent:
                break
            agent_id = ""
            state.pop("cursor_agent_id", None)

        if not reply:
            reply = EMPTY_REPLY_FALLBACK

        if not prime and not had_agent:
            from scripts.research_data_mcp.desk_reply_sanitize import sanitize_desk_reply
            reply = sanitize_desk_reply(reply, first_turn=True)

        is_error = (run is None) or (getattr(run, "status", "") == "error") or (not reply) or (reply == EMPTY_REPLY_FALLBACK)
        if is_error and not prime:
            action_result = {
                "action": "composer_error",
                "status": str(getattr(run, "status", "") or "empty_reply"),
            }
            if reply == EMPTY_REPLY_FALLBACK:
                from scripts.research_data_mcp.desk_catalog_fallback import try_inventory_fallback

                brief = str(state.get("vault_brief") or "").strip()
                fallback = try_inventory_fallback(message.strip(), brief, repo_root=repo_root)
                if fallback:
                    reply = fallback
                    is_error = False
                    action_result = {
                        "action": "composer",
                        "brain": "cursor_composer",
                        "fallback": "vault_inventory",
                    }
                else:
                    reply = (
                        "Composer did not return a usable answer for that turn. "
                        "No dataset candidates or collection status were inferred."
                    )
        else:
            action_result = _artifacts_from_conversation(run)

        action_result["brain"] = "cursor_composer"
        action_result["composer_model"] = model_id
        action_result["cursor_agent_id"] = state.get("cursor_agent_id")
        if action_result.get("state_patch"):
            state.update(action_result["state_patch"])
        if prime and state.get("cursor_agent_id"):
            state["desk_primed"] = True

        return AgentTurn(
            plan={"action": "composer", "brain": "cursor_composer"},
            action_result=action_result,
            reply=reply,
            suggested_prompts=_faculty_starter_prompts(state),
            tool_name="cursor_composer",
        )
    except Exception as exc:
        return AgentTurn(
            plan={"action": "composer_error"},
            action_result={"action": "composer_error", "error": str(exc)[:400]},
            reply=(
                "Composer could not complete that turn (connection or tool error). "
                f"Detail: {str(exc)[:200]}"
            ),
            suggested_prompts=_faculty_starter_prompts(state),
            tool_name="cursor_composer",
        )


def run_desk_agent_turn(
    orchestrator: Any,
    gateway: Any,
    message: str,
    state: dict[str, Any],
    *,
    session_id: str = "",
    event_sink: DeskEventSink | None = None,
) -> AgentTurn:
    _ = orchestrator, session_id
    from scripts.research_data_mcp.desk_direct_turns import try_direct_equipment_turn

    direct = try_direct_equipment_turn(gateway, message, state)
    if direct is not None:
        return direct
    return run_cursor_composer_turn(
        gateway, message, state, session_id=session_id, event_sink=event_sink
    )
