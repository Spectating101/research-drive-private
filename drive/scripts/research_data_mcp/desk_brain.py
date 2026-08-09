#!/usr/bin/env python3
"""Research Drive desk — same pattern as Cursor: Composer + project rules + MCP tools."""

from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


from collections.abc import Callable
from typing import TypeAlias
from sharpe_kernel.paths import repo_root_from_file

DeskEventSink: TypeAlias = Callable[[dict[str, Any]], None]


class CursorSdkUnavailable(RuntimeError):
    """Raised when the optional Cursor SDK runtime cannot be imported."""


@dataclass(frozen=True)
class _CursorSdkBindings:
    agent: Any
    agent_options: Any
    model_selection: Any
    send_options: Any
    stdio_mcp_server_config: Any
    local_agent_options: Any
    cloud_agent_options: Any


def _load_cursor_sdk_bindings() -> _CursorSdkBindings:
    try:
        from cursor_sdk import Agent
        from cursor_sdk.types import (
            AgentOptions,
            CloudAgentOptions,
            LocalAgentOptions,
            ModelSelection,
            SendOptions,
            StdioMcpServerConfig,
        )
    except ImportError as exc:
        raise CursorSdkUnavailable("cursor_sdk is not installed or is incomplete") from exc
    return _CursorSdkBindings(
        agent=Agent,
        agent_options=AgentOptions,
        model_selection=ModelSelection,
        send_options=SendOptions,
        stdio_mcp_server_config=StdioMcpServerConfig,
        local_agent_options=LocalAgentOptions,
        cloud_agent_options=CloudAgentOptions,
    )


@dataclass
class AgentTurn:
    plan: dict[str, Any]
    action_result: dict[str, Any]
    reply: str
    suggested_prompts: list[str] = field(default_factory=list)
    tool_name: str = ""
    tools_called: list[str] = field(default_factory=list)


_TOOL_ACTIVITY_LABELS: dict[str, str] = {
    "collection_status": "Checking the vault…",
    "research_discover_search": "Searching Discover catalog…",
    "research_discover_desk": "Checking Library holdings and declared routes…",
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
    "research_synthesis_terminal_list": "Listing synthesis terminal commands…",
    "research_synthesis_terminal_run": "Inspecting synthesis thread output…",
    "research_collection_hydrate": "Pulling files from Drive…",
    "yzu_submit_job": "Submitting collection job…",
    "research_craft_collect_plan": "Crafting custom collect plan…",
    "research_craft_discover_proposal": "Building Discover craft proposal…",
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


def _emit_mutation_proposal_event(
    sink: DeskEventSink | None,
    *,
    name: str = "",
    payload: dict[str, Any] | None = None,
) -> None:
    """Stream a reviewable mutation as soon as a tool persists one — before final prose."""
    if sink is None or not isinstance(payload, dict):
        return
    job = payload.get("job") if isinstance(payload.get("job"), dict) else None
    job_id = str(
        (job or {}).get("id")
        or (job or {}).get("job_id")
        or payload.get("job_id")
        or payload.get("pending_job_id")
        or ""
    ).strip()
    job_status = str((job or {}).get("status") or payload.get("job_status") or "").strip()
    proposal = payload.get("synthesis_proposal")
    if not isinstance(proposal, dict):
        proposal = None
    if not job_id and not proposal:
        return
    event: dict[str, Any] = {
        "type": "mutation_proposal",
        "text": (
            "Reviewable synthesis proposal recorded — accept or reject before execution."
            if proposal
            else "Collection/job proposal recorded — approve before it runs."
        ),
        "tool_name": str(name or "")[:120] or None,
    }
    if job_id:
        event["job_id"] = job_id
        event["pending_job_id"] = job_id
        if job:
            event["job"] = job
        event["job_status"] = job_status or "pending_approval"
    if proposal:
        event["synthesis_proposal"] = proposal
        event["synthesis_thread_id"] = payload.get("thread_id")
    _emit_event(sink, event)


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


def tool_call_name(tool_call: Any) -> tuple[str, bool]:
    """Return (name, is_mcp) from a Cursor SDK tool_call payload.

    Two shapes reach us and neither carries a top-level name:
      built-in : {"type": "grep", "args": {...}}
      mcp      : {"type": "mcp", "args": {"toolName": "research_query_dataset", ...}}
    Reading tool_call["name"] silently yielded "" for every call, which left
    tools_called empty and every activity label blank.
    """
    if not isinstance(tool_call, dict):
        return "", False
    kind = str(tool_call.get("type") or "").strip()
    args = tool_call.get("args")
    if kind == "mcp" and isinstance(args, dict):
        name = str(args.get("toolName") or args.get("tool_name") or "").strip()
        return name, bool(name)
    direct = str(tool_call.get("name") or tool_call.get("toolName") or "").strip()
    return (direct or kind), False


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
    # Operator/test override: force the unavailable path without unsetting a
    # real key. Dropping this silently made the desk claim Composer was usable
    # in situations where it provably was not.
    if os.getenv("DESK_COMPOSER_FORCE_UNAVAILABLE", "").strip().lower() in {"1", "true", "yes"}:
        return False
    if not os.getenv("CURSOR_API_KEY", "").strip():
        return False
    try:
        _load_cursor_sdk_bindings()
    except CursorSdkUnavailable:
        return False
    return True


def desk_brain_mode(repo_root: Path | None = None) -> str:
    _ = repo_root
    return "cursor_composer" if cursor_composer_available() else "unavailable"


def composer_runtime_status(repo_root: Path | None = None) -> dict[str, Any]:
    """Project provider observations together with the brain users can invoke."""
    from scripts.research_data_mcp.desk_composer_health import (
        composer_runtime_status as provider_runtime_status,
    )

    configured = cursor_composer_available()
    runtime = dict(provider_runtime_status(configured=configured))
    runtime.update(
        {
            "brain": desk_brain_mode(repo_root),
            "composer_configured": configured,
            "composer_status": runtime.get("status") or "unavailable",
        }
    )
    return runtime


def _repo_python(repo_root: Path) -> str:
    """Interpreter for the MCP server subprocess.

    Falling back to bare python3 spawns an interpreter without the desk
    dependencies, so the server dies on import and the SDK reports
    "MCP server does not exist" — the model then answers with no tools at all
    while the engine still calls itself composer_mcp_grounded. Prefer the
    running interpreter, which provably has the deps, over a bare guess.
    """
    venv = repo_root / ".venv/bin/python"
    if venv.is_file():
        return str(venv)
    override = os.getenv("PYTHON", "").strip()
    if override:
        return override
    return sys.executable or "python3"


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


def _mcp_stdio_config(
    repo_root: Path,
    *,
    vault_primed: bool = False,
    synthesis_read_only: bool = False,
    discover: bool = False,
    sdk: _CursorSdkBindings | None = None,
) -> dict[str, Any]:
    bindings = sdk or _load_cursor_sdk_bindings()
    env = {k: v for k, v in os.environ.items() if isinstance(v, str)}
    env["PYTHONPATH"] = _desk_pythonpath(repo_root)
    env["SHARPE_REPO_ROOT"] = str(repo_root)
    env["RESEARCH_MCP_DESK"] = "1"
    if discover:
        env["RESEARCH_MCP_DISCOVER"] = "1"
    if synthesis_read_only:
        env["RESEARCH_MCP_SYNTHESIS_READ_ONLY"] = "1"
    if vault_primed:
        env["RESEARCH_MCP_VAULT_PRIMED"] = "1"
    if discover:
        server_name = "research_procurement_discover"
    elif synthesis_read_only:
        server_name = "research_procurement_synthesis_read_only"
    else:
        server_name = "research_procurement"
    return {
        server_name: bindings.stdio_mcp_server_config(
            command=_repo_python(repo_root),
            args=["-m", "scripts.research_data_mcp.server", "--transport", "stdio"],
            cwd=str(repo_root),
            env=env,
        )
    }


def _faculty_starter_prompts(state: dict[str, Any]) -> list[str]:
    from scripts.research_data_mcp.desk_synthesis_contract import (
        is_synthesis_context,
        synthesis_starter_prompts,
    )

    if is_synthesis_context(state):
        return synthesis_starter_prompts()
    row = state.get("faculty_profile_row") or {}
    out: list[str] = []
    for item in row.get("starter_prompts") or []:
        p = str(item or "").strip()
        if p:
            out.append(p[:160])
    if out:
        return out[:5]
    return [
        "Identify a public dataset for my research and land it via custom procure",
        "Craft a collect plan for a public URL I provide",
        "Search DataCite for recent panels in my field",
    ]


def _desk_setting_sources() -> list[str]:
    raw = os.getenv("DESK_SETTING_SOURCES", "project").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _desk_local_options(
    repo_root: Path, *, sdk: _CursorSdkBindings | None = None
) -> Any:
    bindings = sdk or _load_cursor_sdk_bindings()
    sources = _desk_setting_sources()
    if sources:
        return bindings.local_agent_options(cwd=str(repo_root), setting_sources=sources)
    return bindings.local_agent_options(cwd=str(repo_root))


def _desk_composer_models() -> list[str]:
    # "composer-2.5-fast" is not a valid model on this account — verified live,
    # BadRequestError: "Cannot use this model: composer-2.5-fast. Available
    # models: default, grok-4.5, composer-2.5, ...". Every single call was
    # eating one guaranteed failed attempt before falling through.
    primary = os.getenv("DESK_COMPOSER_MODEL", "composer-2.5").strip() or "composer-2.5"
    fallback = os.getenv("DESK_COMPOSER_MODEL_FALLBACK", "default").strip()
    models = [primary]
    if fallback and fallback not in models:
        models.append(fallback)
    return models


def _desk_agent_runtime_kwargs(
    repo_root: Path, *, sdk: _CursorSdkBindings | None = None
) -> dict[str, Any]:
    """Cloud agents use CURSOR_API_KEY only (headless desk). Local needs Cursor IDE bridge."""
    bindings = sdk or _load_cursor_sdk_bindings()
    if os.getenv("DESK_COMPOSER_LOCAL", "").strip().lower() in {"1", "true", "yes"}:
        return {"local": _desk_local_options(repo_root, sdk=bindings)}
    return {"cloud": bindings.cloud_agent_options()}


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
                    "research_synthesis_terminal_list",
                    "research_synthesis_terminal_run",
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
                    if name in {
                        "research_synthesis_materialisation",
                        "research_synthesis_terminal_run",
                        "research_synthesis_submit_execution",
                    }:
                        # Keep only lifecycle fields needed by the response gate;
                        # never copy an unbounded provider payload into UI state.
                        verification = {
                            "tool": name,
                            **{
                                key: payload.get(key)
                                for key in (
                                    "status",
                                    "materialisation",
                                    "materialization",
                                    "executed",
                                    "execution_recorded",
                                    "output_registered",
                                    "query_ready",
                                    "registered",
                                    "archive_verified",
                                    "verified",
                                    "ok",
                                    "command",
                                    "job_id",
                                    "output_dataset_id",
                                )
                                if payload.get(key) is not None
                            },
                        }
                        action_result.setdefault("synthesis_verifications", []).append(verification)
                if name == "research_synthesis_propose_state":
                    proposal = payload.get("synthesis_proposal")
                    if isinstance(proposal, dict):
                        action_result["synthesis_proposal"] = proposal
                        action_result["synthesis_thread_id"] = payload.get("thread_id")
                        action_result["synthesis_state_artifact"] = {
                            "tool": name,
                            "thread_id": payload.get("thread_id"),
                            "proposal_id": proposal.get("id"),
                            "proposal_hash": proposal.get("proposal_hash"),
                        }
                if name == "research_synthesis_terminal_run":
                    rows = payload.get("rows")
                    cols = payload.get("columns")
                    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                        set_action("query")
                        preview = {
                            "kind": "table",
                            "columns": list(cols or rows[0].keys())[:12],
                            "rows": rows[:5],
                        }
                    action_result["synthesis_terminal"] = {
                        "ok": payload.get("ok"),
                        "thread_id": payload.get("thread_id"),
                        "command_result_keys": sorted(payload.keys())[:24],
                    }
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
    from scripts.research_data_mcp.desk_asset_grounding import format_asset_grounding_block

    entity = ctx.get("entity") if isinstance(ctx.get("entity"), dict) else {}
    workspace = ctx.get("workspace") if isinstance(ctx.get("workspace"), dict) else {}
    surface = str(
        workspace.get("label")
        or workspace.get("surface")
        or ctx.get("surface")
        or ctx.get("tab")
        or "desk"
    ).strip()
    lines = [
        f"[Workspace — {surface}]",
        "Ask is assisting this open surface. Prefer this context over a detached inventory survey.",
    ]
    ws_query = str(workspace.get("query") or ctx.get("search_query") or "").strip()
    if ws_query:
        lines.append(f"- open_query: {ws_query[:240]}")
    for key in ("mode", "engine", "next_action", "summary", "objective", "maturity"):
        val = workspace.get(key)
        if val:
            lines.append(f"- {key}: {str(val)[:280]}")
    if workspace.get("held_count") is not None or workspace.get("route_offerings") is not None:
        lines.append(
            "- explore: "
            f"held={workspace.get('held_count', 0)} · "
            f"routes/offerings={workspace.get('route_offerings', 0)} · "
            f"web_context={workspace.get('web_context', 0)}"
        )
    for row in list(workspace.get("held") or [])[:5]:
        if isinstance(row, dict):
            title = str(row.get("title") or row.get("dataset_id") or "").strip()
            did = str(row.get("dataset_id") or "").strip()
            if title:
                lines.append(f"- held_row: {title}" + (f" [{did}]" if did else ""))
    for row in list(workspace.get("routes") or [])[:5]:
        if isinstance(row, dict):
            title = str(row.get("title") or row.get("source_id") or "").strip()
            sid = str(row.get("source_id") or "").strip()
            if title:
                lines.append(f"- route_row: {title}" + (f" [{sid}]" if sid else ""))
    if workspace.get("focus_title") or entity.get("title"):
        lines.append(
            f"- focus: {workspace.get('focus_kind') or entity.get('kind') or 'item'} · "
            f"{workspace.get('focus_title') or entity.get('title') or entity.get('id') or ''}"[:280]
        )
    if workspace.get("thread_id") or ctx.get("thread_id"):
        lines.append(f"- thread_id: {workspace.get('thread_id') or ctx.get('thread_id')}")

    lines.append("[UI rail context]")
    for key in (
        "tab",
        "mode",
        "surface",
        "thread_id",
        "session_id",
        "conversation_id",
        "dataset_id",
        "folder_id",
        "search_query",
        "readiness",
        "analysis_readiness",
        "vault_path",
    ):
        val = ctx.get(key)
        if val:
            lines.append(f"- {key}: {str(val)[:240]}")
    if entity.get("kind"):
        lines.append(
            f"- entity: {entity.get('kind')} · {entity.get('title') or entity.get('id') or ''}"[:280]
        )
    actions = ctx.get("valid_next_actions") or ctx.get("actions")
    if isinstance(actions, list) and actions:
        lines.append(f"- actions: {', '.join(str(a) for a in actions[:8])}")
    compare = ctx.get("compare")
    if isinstance(compare, dict) and compare.get("left") and compare.get("right"):
        lines.append(f"- compare: {compare.get('left')} × {compare.get('right')}")
    rail_block = "\n".join(lines) + "\n\n"
    grounding = format_asset_grounding_block(ctx)
    return rail_block + grounding


def _composer_timeout_turn(state: dict[str, Any], *, elapsed: float, limit: float) -> AgentTurn:
    return AgentTurn(
        plan={"action": "composer_timeout"},
        action_result={
            "action": "composer_timeout",
            "error_type": "composer_timeout",
            "elapsed_seconds": int(elapsed),
            "timeout_seconds": float(limit),
            "brain": desk_brain_mode(),
        },
        reply=(
            f"Ask timed out after {int(elapsed)}s waiting for Composer "
            f"(limit {int(limit)}s). No collection or approval was started. "
            "Try a direct command (search, probe, status) or ask about the selected object."
        ),
        suggested_prompts=["status", "Search vault for related datasets", "What do we know about this?"],
        tool_name="cursor_composer",
    )


def _wait_run_bounded(run: Any, timeout_seconds: float) -> None:
    """Bound run.wait() so a stuck Composer cannot hang the desk forever.

    Important: do not use ``with ThreadPoolExecutor(...)`` -- on TimeoutError the
    context-manager ``shutdown(wait=True)`` waits for the stuck worker and the
    API hangs again. Shut down with wait=False so the caller returns promptly.
    """
    wait = getattr(run, "wait", None)
    if not callable(wait):
        return
    limit = max(1.0, float(timeout_seconds))
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(wait)
        future.result(timeout=limit)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


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
    from scripts.research_data_mcp.desk_scale import chat_timeout_seconds

    turn_budget = chat_timeout_seconds()
    turn_started = time.monotonic()
    repo_root = Path(gateway.repo_root).resolve()
    from scripts.research_data_mcp.desk_synthesis_contract import (
        synthesis_continuation_request,
        synthesis_incomplete_reply,
        first_turn_reply_is_acceptable,
        is_synthesis_context,
        record_synthesis_turn,
        strip_synthesis_procurement_cta,
        synthesis_reply_needs_continuation,
        synthesis_first_turn,
        synthesis_failure_reply,
        wrap_synthesis_request,
    )

    synthesis_context = is_synthesis_context(state)
    api_key = os.getenv("CURSOR_API_KEY", "").strip()
    if not api_key:
        return AgentTurn(
            plan={"action": "composer_unavailable"},
            action_result={
                "action": "composer_unavailable",
                "error": "missing CURSOR_API_KEY",
                **({"mode": "synthesis", "fallback": "none", "brain": "cursor_composer"} if synthesis_context else {}),
            },
            reply=(
                synthesis_failure_reply("agent_unavailable")
                if synthesis_context
                else (
                    "The research desk runs on Cursor Composer with the procurement tool library. "
                    "Ask the lab operator to set CURSOR_API_KEY in .env.local, then try again."
                )
            ),
            suggested_prompts=_faculty_starter_prompts(state),
            tool_name="",
        )
    try:
        sdk = _load_cursor_sdk_bindings()
        model_candidates = _desk_composer_models()
        agent_id = str(state.get("cursor_agent_id") or "").strip()
        composer_mode = "synthesis_read_only" if synthesis_context else "default"
        if state.get("composer_context_mode") not in (None, composer_mode):
            agent_id = ""
            state.pop("cursor_agent_id", None)
        state["composer_context_mode"] = composer_mode
        had_agent = bool(agent_id)
        first_synthesis_turn = synthesis_first_turn(state)
        user_text = message.strip()
        rail_prefix = _format_rail_context(state.get("rail_context") or {})
        if rail_prefix and rail_prefix not in user_text:
            user_text = rail_prefix + user_text
        vault_primed_env = False
        ask_desk_grounded = False
        if synthesis_context:
            # Prefer the per-turn L0 measure already streamed to the UI (includes mapped
            # Synthesis evidence). Keep the first-turn profile brief as an additive layer.
            ask_measure = state.get("_ask_desk_measure")
            if isinstance(ask_measure, dict):
                from scripts.research_data_mcp.desk_ask_grounding import (
                    format_ask_desk_grounding_brief,
                    serialize_desk_facts_ui,
                )

                grounding = format_ask_desk_grounding_brief(ask_measure)
                state["ask_desk_facts_ui"] = serialize_desk_facts_ui(ask_measure)
                state["ask_desk_grounding_brief"] = grounding
                user_text = f"{grounding}\n\n{user_text}"
                ask_desk_grounded = True
            if first_synthesis_turn:
                from scripts.research_data_mcp.desk_synthesis_grounding import (
                    build_synthesis_grounding_brief,
                )

                grounding = build_synthesis_grounding_brief(
                    gateway,
                    message,
                    rail_context=state.get("rail_context"),
                )
                state["synthesis_grounding_brief"] = grounding
                user_text = f"{grounding}\n\n{user_text}"
            else:
                from scripts.research_data_mcp.desk_synthesis_contract import (
                    build_synthesis_thread_state_brief,
                )

                thread_state_brief = build_synthesis_thread_state_brief(gateway, state)
                if thread_state_brief:
                    state["synthesis_thread_state_brief"] = thread_state_brief
                    user_text = f"{thread_state_brief}\n\n{user_text}"
            user_text = wrap_synthesis_request(
                user_text,
                first_user_turn=first_synthesis_turn,
            )
        elif not prime:
            # Same L0 measure as Discover — mandatory context, conversational L1.
            from scripts.research_data_mcp.desk_ask_grounding import (
                format_ask_desk_grounding_brief,
                measure_ask_desk,
                serialize_desk_facts_ui,
            )

            desk_facts = state.get("_ask_desk_measure")
            if not isinstance(desk_facts, dict):
                desk_facts = measure_ask_desk(
                    gateway, message, rail_context=state.get("rail_context")
                )
            grounding = format_ask_desk_grounding_brief(desk_facts)
            state["ask_desk_facts"] = {
                "strong_held": desk_facts.get("strong_held"),
                "held_count": desk_facts.get("held_count"),
                "route_count": desk_facts.get("route_count"),
                "route_reason": desk_facts.get("route_reason"),
            }
            state["ask_desk_facts_ui"] = serialize_desk_facts_ui(desk_facts)
            state["ask_desk_grounding_brief"] = grounding
            user_text = f"{grounding}\n\n{user_text}"
            ask_desk_grounded = True
            # DESK_FACTS replace the old vault-brief inventory dump — don't bloat the prompt.
            vault_primed_env = True
            _emit_event(
                event_sink,
                {
                    "type": "desk_facts",
                    "desk_facts": state["ask_desk_facts_ui"],
                    "text": "Library measure ready",
                },
            )
        if prime:
            pass
        elif (
            not ask_desk_grounded
            and not had_agent
            and not state.get("desk_primed")
        ):
            from scripts.research_data_mcp.desk_vault_brief import (
                build_vault_brief,
                wrap_first_turn_message,
            )

            brief = str(state.get("vault_brief") or "").strip()
            if not brief:
                brief = build_vault_brief(repo_root, state.get("faculty_profile"))
                state["vault_brief"] = brief
            user_text = wrap_first_turn_message(brief, user_text)
            vault_primed_env = True
        # Ask already measured L0 in-process. Keep MCP hands attached so Composer can
        # query/sample/collect when the user asks — DESK_FACTS remain authoritative for
        # holdings/routes. Opt out only via DESK_ASK_ATTACH_MCP=0.
        attach_mcp = True
        attach_flag = os.getenv("DESK_ASK_ATTACH_MCP", "").strip().lower()
        if attach_flag in {"0", "false", "no"}:
            attach_mcp = False
        elif attach_flag in {"1", "true", "yes"}:
            attach_mcp = True
        discover_turn = bool(state.get("discover_composer"))
        mcp_servers = (
            _mcp_stdio_config(
                repo_root,
                vault_primed=vault_primed_env,
                synthesis_read_only=synthesis_context,
                discover=discover_turn,
                sdk=sdk,
            )
            if attach_mcp
            else {}
        )
        state["ask_mcp_attached"] = attach_mcp
        streamed: list[str] = []
        run = None
        reply = ""
        model_id = model_candidates[0]
        tool_call_started = False
        tools_called: list[str] = []

        def on_delta(update: Any) -> None:
            nonlocal tool_call_started
            payload = _interaction_payload(update)
            typ = str(payload.get("type") or "")
            if typ == "text-delta":
                chunk = str(payload.get("text") or "")
                if chunk:
                    streamed.append(chunk)
                    _emit_event(event_sink, {"type": "delta", "text": chunk})
                return
            if typ == "tool-call-started":
                tool_call_started = True
                tool_call = payload.get("tool_call") or {}
                name, is_mcp = tool_call_name(tool_call)
                if is_mcp and name and name not in tools_called:
                    tools_called.append(name)
                label = _tool_activity_label(name) if is_mcp else ""
                if label:
                    _emit_event(event_sink, {"type": "activity", "text": label})
                return
            # Some Cursor SDK builds surface completed tool calls with a result payload.
            if typ in {"tool-call-completed", "tool-call-finished", "tool_result"}:
                tool_call = payload.get("tool_call") or payload
                name, _is_mcp = tool_call_name(tool_call)
                result = tool_call.get("result") or payload.get("result")
                parsed: Any = result
                if isinstance(result, str):
                    try:
                        parsed = json.loads(result)
                    except json.JSONDecodeError:
                        parsed = None
                if isinstance(parsed, dict):
                    _emit_mutation_proposal_event(event_sink, name=name, payload=parsed)

        send_opts = sdk.send_options(mcp_servers=mcp_servers, on_delta=on_delta)

        for model_idx, model_id in enumerate(model_candidates):
            send_started = False
            try:
                agent_opts = sdk.agent_options(
                    model=sdk.model_selection(id=model_id),
                    api_key=api_key,
                    name=f"research-desk-{session_id[:8] or 'anon'}",
                    mcp_servers=mcp_servers,
                    **_desk_agent_runtime_kwargs(repo_root, sdk=sdk),
                )
                resume_id = agent_id if model_idx == 0 else ""
                if resume_id:
                    agent = sdk.agent.resume(resume_id, agent_opts)
                else:
                    agent = sdk.agent.create(agent_opts)
                    state["cursor_agent_id"] = agent.agent_id
                    agent_id = agent.agent_id

                with agent:
                    turn_text = user_text
                    for attempt in range(2):
                        streamed.clear()
                        send_started = True
                        run = agent.send(turn_text, send_opts)
                        _wait_run_bounded(run, turn_budget - (time.monotonic() - turn_started))
                        # Surface reviewable mutations as soon as tools finished, before prose gates.
                        try:
                            early_arts = _artifacts_from_conversation(run) if run is not None else {}
                            if early_arts.get("job") or early_arts.get("job_id") or early_arts.get(
                                "synthesis_proposal"
                            ):
                                _emit_mutation_proposal_event(
                                    event_sink,
                                    name=str(early_arts.get("tool_name") or ""),
                                    payload=early_arts,
                                )
                        except Exception:  # noqa: BLE001
                            pass
                        reply = _reply_from_run(run, streamed)
                        if synthesis_context:
                            reply = strip_synthesis_procurement_cta(reply)
                        if (
                            reply
                            or prime
                            or attempt == 1
                            or tool_call_started
                        ):
                            break
                        turn_text = (
                            f"{user_text}\n\n"
                            "(The previous attempt returned no final text. Answer now in plain prose.)"
                        )

                    # Providers sometimes stop after the first numbered section and
                    # append their generic catalogue CTA. A structured Synthesis
                    # brief should get one bounded continuation on the same agent,
                    # rather than surfacing a visibly unfinished answer or silently
                    # starting a new conversation. The Synthesis MCP surface is
                    # read-only, and the continuation prompt explicitly forbids
                    # proposals/collection/execution.
                    continuation_attempts = 0
                    while (
                        synthesis_context
                        and not prime
                        and not first_synthesis_turn
                        and reply
                        and synthesis_reply_needs_continuation(message, reply)
                        and continuation_attempts < 2
                    ):
                        remaining = turn_budget - (time.monotonic() - turn_started)
                        if remaining <= 1.0:
                            break
                        continuation_attempts += 1
                        continuation_run = None
                        try:
                            continuation_text = synthesis_continuation_request(
                                message, reply
                            )
                            streamed.clear()
                            continuation_run = agent.send(continuation_text, send_opts)
                            _wait_run_bounded(continuation_run, remaining)
                            continuation_reply = strip_synthesis_procurement_cta(
                                _reply_from_run(continuation_run, streamed)
                            )
                            if continuation_reply:
                                try:
                                    continuation_arts = _artifacts_from_conversation(
                                        continuation_run
                                    )
                                    if (
                                        continuation_arts.get("job")
                                        or continuation_arts.get("job_id")
                                        or continuation_arts.get("synthesis_proposal")
                                    ):
                                        _emit_mutation_proposal_event(
                                            event_sink,
                                            name=str(continuation_arts.get("tool_name") or ""),
                                            payload=continuation_arts,
                                        )
                                except Exception:  # noqa: BLE001
                                    pass
                                reply = f"{reply.rstrip()}\n\n{continuation_reply}"
                                run = continuation_run
                            else:
                                break
                        except Exception:  # noqa: BLE001
                            # The original grounded answer is safer than a provider
                            # error; the normal contract gate below will report it
                            # as retryable if it remains short.
                            break
            except Exception:
                can_retry_fresh = (
                    model_idx < len(model_candidates) - 1
                    and not send_started
                )
                if not can_retry_fresh:
                    raise
                agent_id = ""
                state.pop("cursor_agent_id", None)
                run = None
                reply = ""
                continue

            is_model_error = (
                run is None
                or getattr(run, "status", "") == "error"
                or (not reply and not prime)
            )
            if not is_model_error or model_idx == len(model_candidates) - 1:
                break
            # Empty / failed reply after send — try the next model on a fresh agent.
            # (Resume failures before send already continue via can_retry_fresh above.)
            agent_id = ""
            state.pop("cursor_agent_id", None)
            run = None
            reply = ""
            send_started = False
            tool_call_started = False
            streamed.clear()
            _emit_event(
                event_sink,
                {
                    "type": "activity",
                    "text": f"Retrying with fallback model ({model_candidates[model_idx + 1]})…",
                },
            )
            continue

        if not reply:
            reply = EMPTY_REPLY_FALLBACK

        if not prime and not had_agent:
            from scripts.research_data_mcp.desk_reply_sanitize import sanitize_desk_reply
            reply = sanitize_desk_reply(reply, first_turn=True)

        if synthesis_context and not prime and reply and reply != EMPTY_REPLY_FALLBACK:
            from scripts.research_data_mcp.desk_synthesis_contract import (
                maybe_repair_synthesis_reply,
                strip_synthesis_procurement_cta,
            )

            reply = strip_synthesis_procurement_cta(reply)
            repaired = maybe_repair_synthesis_reply(
                reply,
                first_user_turn=first_synthesis_turn,
            )
            if repaired != reply:
                reply = repaired

        is_error = (run is None) or (getattr(run, "status", "") == "error") or (not reply) or (reply == EMPTY_REPLY_FALLBACK)
        synthesis_violations: list[str] = []
        recorded_artifacts: dict[str, Any] = {}
        if synthesis_context and not prime and not is_error:
            from scripts.research_data_mcp.desk_synthesis_contract import (
                synthesis_construction_claim_violations,
                synthesis_lifecycle_claim_violations,
                synthesis_reply_violations,
            )

            recorded_artifacts = _artifacts_from_conversation(run) if run is not None else {}
            synthesis_violations = synthesis_reply_violations(
                reply,
                first_user_turn=first_synthesis_turn,
                artifacts=recorded_artifacts,
            )
            synthesis_violations.extend(
                synthesis_construction_claim_violations(
                    reply,
                    artifacts=recorded_artifacts,
                    first_user_turn=first_synthesis_turn,
                )
            )
            synthesis_violations.extend(
                synthesis_lifecycle_claim_violations(reply, recorded_artifacts)
            )
            if synthesis_reply_needs_continuation(message, reply):
                synthesis_violations.append("incomplete_structured_reply")
            is_error = bool(synthesis_violations)
        if is_error and not prime:
            action_result = {
                "action": "composer_error",
                "status": str(getattr(run, "status", "") or "empty_reply"),
            }
            recorded = recorded_artifacts or (_artifacts_from_conversation(run) if run is not None else {})
            # Soft-recover when tools already persisted a reviewable mutation — empty prose
            # must not hide a pending job / proposal behind a generic failure.
            job = recorded.get("job") if isinstance(recorded.get("job"), dict) else None
            job_id = str(
                (job or {}).get("id")
                or recorded.get("job_id")
                or recorded.get("pending_job_id")
                or ""
            ).strip()
            proposal = recorded.get("synthesis_proposal")
            if job_id and not synthesis_context:
                action_result.update(recorded)
                action_result["action"] = str(recorded.get("action") or "collect")
                action_result["job_id"] = job_id
                if job:
                    action_result["job"] = job
                status = str((job or {}).get("status") or recorded.get("job_status") or "pending_approval")
                action_result["job_status"] = status
                reply = (
                    f"Collection job `{job_id}` is recorded"
                    + (" and waiting for desk approval." if "pending" in status else ".")
                    + " Composer did not finish a prose summary — use Approve below if required."
                )
                is_error = False
            elif synthesis_context:
                # MCP proposal tools persist a review-only state before the model
                # emits its final prose. If that prose then violates the response
                # contract, a generic "nothing changed" fallback contradicts the
                # durable canvas. Surface the recorded proposal instead of hiding
                # the mutation behind another provider turn.
                if isinstance(proposal, dict):
                    from scripts.research_data_mcp.desk_synthesis_contract import (
                        synthesis_proposal_recorded_reply,
                    )

                    action_result.update(recorded)
                    action_result.update(
                        {
                            "action": "synthesis_proposal_recorded_response_error",
                            "mode": "synthesis",
                            "reason": "composer_contract_violation",
                            "contract_violations": synthesis_violations,
                            "proposal_recorded": True,
                        }
                    )
                    reply = synthesis_proposal_recorded_reply(proposal.get("title"))
                    is_error = False
                else:
                    # Composer+MCP only — no Gemini / alternate-brain fallback.
                    action_result.update(
                        {
                            "mode": "synthesis",
                            "fallback": "none",
                            "brain": "cursor_composer",
                            "reason": (
                                "composer_contract_violation"
                                if synthesis_violations
                                else "empty_or_failed_composer_reply"
                            ),
                            **(
                                {"contract_violations": synthesis_violations}
                                if synthesis_violations
                                else {}
                            ),
                        }
                    )
                    if "incomplete_structured_reply" in synthesis_violations:
                        action_result.update(
                            {
                                "action": "composer_incomplete",
                                "continuation_required": True,
                                "retryable": True,
                            }
                        )
                        reply = synthesis_incomplete_reply(reply, message)
                    elif "construction_advance_without_artifact" in synthesis_violations:
                        from scripts.research_data_mcp.desk_synthesis_contract import (
                            synthesis_advance_failure_reply,
                        )

                        action_result.update(
                            {
                                "action": "synthesis_advance_blocked",
                                "construction_advance_blocked": True,
                                "required_artifact": "research_synthesis_propose_state",
                                "retryable": True,
                            }
                        )
                        reply = synthesis_advance_failure_reply()
                    elif any(
                        violation.startswith("unverified_")
                        for violation in synthesis_violations
                    ):
                        from scripts.research_data_mcp.desk_synthesis_contract import (
                            synthesis_claim_failure_reply,
                        )

                        action_result.update(
                            {
                                "action": "synthesis_claim_blocked",
                                "lifecycle_claim_blocked": True,
                                "retryable": True,
                            }
                        )
                        reply = synthesis_claim_failure_reply()
                    else:
                        reply = synthesis_failure_reply(
                            "response_contract"
                            if synthesis_violations
                            else action_result["status"]
                        )
            elif reply == EMPTY_REPLY_FALLBACK:
                # No script-brain inventory wallpaper — Composer owns the miss.
                reply = (
                    "Composer did not return a usable answer for that turn. "
                    "No dataset candidates or collection status were inferred. "
                    "Try again — the desk will use a fresh Composer session."
                )
                action_result["retryable"] = True
            else:
                action_result["retryable"] = True
        else:
            action_result = _artifacts_from_conversation(run)

        from scripts.research_data_mcp.desk_composer_health import (
            record_composer_failure,
            record_composer_success,
        )

        if is_error:
            record_composer_failure(
                (
                    f"contract_violation:{','.join(synthesis_violations)}"
                    if synthesis_violations
                    else str(getattr(run, "status", "") or "empty_reply")
                ),
                model=model_id,
            )
        else:
            record_composer_success(model=model_id)

        action_result["brain"] = "cursor_composer"
        action_result["composer_model"] = model_id
        action_result["cursor_agent_id"] = state.get("cursor_agent_id")
        if "ask_mcp_attached" in state:
            action_result["ask_mcp_attached"] = bool(state.get("ask_mcp_attached"))
        if state.get("ask_desk_facts_ui"):
            action_result["desk_facts"] = state.get("ask_desk_facts_ui")
        if action_result.get("state_patch"):
            state.update(action_result["state_patch"])
        if prime and state.get("cursor_agent_id"):
            state["desk_primed"] = True
        if synthesis_context and not prime and not is_error:
            if first_synthesis_turn:
                action_result["synthesis_contract_validated"] = (
                    first_turn_reply_is_acceptable(reply)
                )
            if not first_synthesis_turn or action_result.get(
                "synthesis_contract_validated"
            ):
                record_synthesis_turn(
                    state,
                    user=message,
                    assistant=reply,
                    provider="cursor_composer",
                )

        from scripts.research_data_mcp.desk_asset_grounding import (
            grounding_from_rail,
            sanitize_grounded_reply,
            sanitize_suggested_prompts,
            suggested_prompts_for_asset,
        )

        grounding = grounding_from_rail(state.get("rail_context") or {})
        readiness = grounding.get("canonical_readiness")
        did = str(grounding.get("dataset_id") or "")
        reply = sanitize_grounded_reply(reply, readiness, dataset_id=did)
        suggestions = _faculty_starter_prompts(state)
        if grounding.get("registered_or_ready"):
            suggestions = suggested_prompts_for_asset(did, readiness) + suggestions
        suggestions = sanitize_suggested_prompts(suggestions, readiness)
        return AgentTurn(
            plan={"action": "composer", "brain": "cursor_composer"},
            action_result=action_result,
            reply=reply,
            suggested_prompts=suggestions[:5],
            tool_name="cursor_composer",
            tools_called=list(tools_called),
        )
    except TimeoutError:
        # A stuck Composer must not hang the desk. In Synthesis, preserve any
        # proposal the timed-out run already recorded; otherwise fail closed
        # (Composer+MCP only — no Gemini alternate brain).
        state.pop("cursor_agent_id", None)
        if synthesis_context and not prime:
            recorded = _artifacts_from_conversation(run) if run is not None else {}
            proposal = recorded.get("synthesis_proposal")
            if isinstance(proposal, dict):
                from scripts.research_data_mcp.desk_synthesis_contract import (
                    synthesis_proposal_recorded_reply,
                )

                return AgentTurn(
                    plan={"action": "synthesis_proposal_recorded_response_error"},
                    action_result={
                        **recorded,
                        "action": "synthesis_proposal_recorded_response_error",
                        "mode": "synthesis",
                        "reason": "composer_timeout",
                        "proposal_recorded": True,
                        "brain": "cursor_composer",
                    },
                    reply=synthesis_proposal_recorded_reply(proposal.get("title")),
                    suggested_prompts=_faculty_starter_prompts(state),
                    tool_name="cursor_composer",
                )
            turn = _composer_timeout_turn(
                state, elapsed=time.monotonic() - turn_started, limit=turn_budget
            )
            turn.action_result.update(
                {"mode": "synthesis", "fallback": "none", "brain": "cursor_composer"}
            )
            return turn
        return _composer_timeout_turn(
            state, elapsed=time.monotonic() - turn_started, limit=turn_budget
        )
    except CursorSdkUnavailable as exc:
        return AgentTurn(
            plan={"action": "composer_unavailable"},
            action_result={
                "action": "composer_unavailable",
                "error": str(exc),
                **(
                    {
                        "mode": "synthesis",
                        "fallback": "none",
                        "brain": "cursor_composer",
                    }
                    if synthesis_context
                    else {}
                ),
            },
            reply=(
                synthesis_failure_reply("agent_unavailable")
                if synthesis_context
                else (
                    "Cursor Composer is configured, but cursor_sdk is unavailable on this host. "
                    "Ask the lab operator to install the Cursor SDK in the desk runtime."
                )
            ),
            suggested_prompts=_faculty_starter_prompts(state),
            tool_name="",
        )
    except Exception as exc:
        from scripts.research_data_mcp.desk_composer_health import record_composer_failure

        record_composer_failure(exc, model=locals().get("model_id", ""))
        synthesis_context = is_synthesis_context(state)
        return AgentTurn(
            plan={"action": "composer_error"},
            action_result={
                "action": "composer_error",
                "error": str(exc)[:400],
                **(
                    {
                        "mode": "synthesis",
                        "fallback": "none",
                        "brain": "cursor_composer",
                    }
                    if synthesis_context
                    else {}
                ),
            },
            reply=(
                synthesis_failure_reply("connection_or_tool_error")
                if synthesis_context
                else (
                    "Composer could not complete that turn (connection or tool error). "
                    f"Detail: {str(exc)[:200]}"
                )
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
    """Composer + MCP only — regex/script Ask interceptors are stripped."""
    _ = orchestrator
    return run_cursor_composer_turn(
        gateway, message, state, session_id=session_id, event_sink=event_sink
    )
