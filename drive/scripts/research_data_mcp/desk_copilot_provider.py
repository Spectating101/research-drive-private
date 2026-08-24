#!/usr/bin/env python3
"""GitHub Copilot SDK transport for the Research Drive desk.

The desk's existing orchestration contract is synchronous and Cursor-shaped.
This module adapts Copilot's async SDK to that narrow transport contract while
keeping all research policy, grounding, and mutation controls in ``desk_brain``
and the MCP server.

Production invariants:

* each desk session is sticky to one explicitly configured account;
* headless runtimes never use prompt-mode account rotation;
* Copilot runs in ``empty`` mode with only the configured MCP tools;
* Synthesis read-only mode is still enforced by the MCP process itself;
* account tokens stay in the operator credential launcher and are never copied
  into desk state, logs, or API responses.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import os
import re
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any


class CopilotSdkUnavailable(RuntimeError):
    """Raised when the optional Copilot runtime cannot be invoked safely."""


_ACCOUNT_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_LOOP_LOCK = threading.Lock()
_LOOP: asyncio.AbstractEventLoop | None = None
_LOOP_THREAD: threading.Thread | None = None
_CLIENTS: dict[str, Any] = {}
_SYNTHESIS_SAFE_TOOLS = [
    "research_semantic_discover",
    "research_discover_search",
    "research_describe_dataset",
    "research_query_dataset",
    "research_synthesis_pair",
]
_GENERAL_SAFE_TOOLS = [
    "collection_status",
    "research_semantic_discover",
    "research_discover_search",
    "research_discover_source_search",
    "research_discover_source_preview",
    "research_acquisition_status",
    "research_acquisition_options",
    "research_web_discover",
    "research_describe_dataset",
    "research_query_dataset",
    "research_analyze_dataset",
    "research_collection_hydrate",
    "research_synthesis_pair",
    "research_quant_brief",
    "procurement_probe_public_source",
    "research_craft_collect_plan",
    "research_craft_discover_proposal",
    "research_procure_resume_campaign",
    "research_procure_campaign_artifacts",
    "research_procure_approve_collect",
    "datacite_collect_doi",
    "datacite_search_and_resolve",
    "huggingface_collect_dataset",
    "procurement_submit_collection_job",
    "procurement_approve_job",
    "yzu_submit_job",
    "yzu_approve_job",
    "bigquery_dry_run",
    "bigquery_read_query",
    "bigquery_status",
    "bigquery_list_datasets",
    "bigquery_list_tables",
    "bigquery_table_schema",
    "research_ops_status",
    "collection_queue_status",
    "research_procurement_catalog",
    "research_advise_datasets",
    "research_plan_sources",
    "huggingface_search",
    "procurement_list_connectors",
    "procurement_prepare_collection",
    "procurement_list_jobs",
    "procurement_get_job",
    "procurement_cancel_job",
    "research_dataset_card",
    "research_open_dataset",
    "research_list_pins",
    "research_pin_dataset",
    "yzu_cluster_status",
    "yzu_list_acquisitions",
    "yzu_cluster_components",
    "yzu_list_queue_tasks",
    "yzu_cancel_job",
    "yzu_get_job",
    "yzu_list_jobs",
    "yzu_archive_to_gdrive",
]


def configured_copilot_accounts() -> list[str]:
    """Return the ordered, de-duplicated operator-approved account aliases."""
    raw = os.getenv("DESK_COPILOT_ACCOUNTS", "").strip()
    if not raw:
        raw = os.getenv("COPILOT_ACCOUNT", "").strip()
    accounts: list[str] = []
    for part in raw.split(","):
        account = part.strip()
        if account and _ACCOUNT_RE.fullmatch(account) and account not in accounts:
            accounts.append(account)
    return accounts


def copilot_launcher_path() -> Path:
    configured = os.getenv("DESK_COPILOT_LAUNCHER", "").strip()
    if configured:
        return Path(configured).expanduser()
    # Fail closed instead of guessing a user-specific installation path or
    # accidentally selecting the older system ``copilot`` binary.
    return Path("/DESK_COPILOT_LAUNCHER_UNSET")


def copilot_composer_available() -> bool:
    if os.getenv("DESK_COMPOSER_FORCE_UNAVAILABLE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return False
    if not configured_copilot_accounts():
        return False
    launcher = copilot_launcher_path()
    if not launcher.is_file() or not os.access(launcher, os.X_OK):
        return False
    try:
        import copilot  # noqa: F401
    except ImportError:
        return False
    return True


def choose_copilot_account(
    session_id: str,
    state: dict[str, Any],
) -> str:
    """Choose one stable account without storing or exposing its credential."""
    accounts = configured_copilot_accounts()
    if not accounts:
        raise CopilotSdkUnavailable("no DESK_COPILOT_ACCOUNTS are configured")
    current = str(state.get("copilot_account") or "").strip()
    if current in accounts:
        return current
    identity = str(session_id or state.get("session_id") or "desk-anonymous")
    digest = hashlib.sha256(identity.encode("utf-8")).digest()
    account = accounts[int.from_bytes(digest[:8], "big") % len(accounts)]
    state["copilot_account"] = account
    return account


def _event_type(event: Any) -> str:
    typ = getattr(event, "type", "")
    return str(getattr(typ, "value", typ) or "")


def _start_event_loop() -> asyncio.AbstractEventLoop:
    global _LOOP, _LOOP_THREAD
    with _LOOP_LOCK:
        if _LOOP is not None and _LOOP.is_running():
            return _LOOP
        ready = threading.Event()
        loop = asyncio.new_event_loop()

        def serve() -> None:
            asyncio.set_event_loop(loop)
            ready.set()
            loop.run_forever()

        thread = threading.Thread(
            target=serve,
            name="research-drive-copilot-sdk",
            daemon=True,
        )
        thread.start()
        ready.wait(timeout=5)
        if not loop.is_running():
            raise CopilotSdkUnavailable("Copilot SDK event loop did not start")
        _LOOP = loop
        _LOOP_THREAD = thread
        return loop


def _submit(coro: Any) -> concurrent.futures.Future[Any]:
    return asyncio.run_coroutine_threadsafe(coro, _start_event_loop())


def _state_root(account: str) -> Path:
    configured = os.getenv("DESK_COPILOT_STATE_ROOT", "").strip()
    if configured:
        root = Path(configured).expanduser()
    else:
        xdg = os.getenv("XDG_STATE_HOME", "").strip()
        root = Path(xdg).expanduser() if xdg else Path.home() / ".local/state"
        root = root / "research-drive/copilot"
    return root / account


async def _client_for(account: str) -> Any:
    from copilot import CopilotClient, RuntimeConnection

    existing = _CLIENTS.get(account)
    if existing is not None:
        return existing
    env = {k: v for k, v in os.environ.items() if isinstance(v, str)}
    env["COPILOT_ACCOUNT"] = account
    client = CopilotClient(
        connection=RuntimeConnection.for_stdio(path=str(copilot_launcher_path())),
        mode="empty",
        base_directory=str(_state_root(account)),
        env=env,
        use_logged_in_user=True,
        log_level=os.getenv("DESK_COPILOT_LOG_LEVEL", "error").strip() or "error",
        session_idle_timeout_seconds=max(
            30,
            int(os.getenv("DESK_COPILOT_SESSION_IDLE_SECONDS", "900") or 900),
        ),
    )
    await client.start()
    _CLIENTS[account] = client
    return client


@dataclass(frozen=True)
class _ModelSelection:
    id: str


@dataclass
class _AgentOptions:
    model: _ModelSelection
    name: str
    mcp_servers: dict[str, Any]


@dataclass
class _SendOptions:
    mcp_servers: dict[str, Any]
    on_delta: Any = None


class _CopilotRun:
    def __init__(self, future: concurrent.futures.Future[Any], account: str) -> None:
        self._future = future
        self._resolved = False
        self._reply = ""
        self._messages: list[Any] = []
        self.status = "pending"
        self.model = "auto"
        self.account = account
        self.tool_call_started = False

    def wait(self) -> None:
        if self._resolved:
            return
        payload = self._future.result()
        self._resolved = True
        self._reply = str(payload.get("reply") or "")
        self._messages = list(payload.get("messages") or [])
        self.status = str(payload.get("status") or "completed")
        self.model = str(payload.get("model") or "auto")
        self.tool_call_started = bool(payload.get("tool_call_started"))

    def text(self) -> str:
        self.wait()
        return self._reply

    def conversation(self) -> list[Any]:
        self.wait()
        steps = [SimpleNamespace(message=message) for message in self._messages]
        return [SimpleNamespace(steps=steps)] if steps else []


class _CopilotAgent:
    def __init__(
        self,
        account: str,
        options: _AgentOptions,
        *,
        agent_id: str = "",
        resume: bool = False,
    ) -> None:
        self.account = account
        self.options = options
        self.agent_id = agent_id or f"rd-{uuid.uuid4().hex}"
        self.resume = resume

    def __enter__(self) -> "_CopilotAgent":
        return self

    def __exit__(self, *_args: Any) -> bool:
        return False

    def close(self) -> None:
        return None

    def send(self, text: str, options: _SendOptions | None = None) -> _CopilotRun:
        send_options = options or _SendOptions(mcp_servers=self.options.mcp_servers)
        future = _submit(
            _send_turn(
                account=self.account,
                session_id=self.agent_id,
                resume=self.resume,
                model=self.options.model.id,
                prompt=str(text),
                mcp_servers=send_options.mcp_servers or self.options.mcp_servers,
                on_delta=send_options.on_delta,
            )
        )
        self.resume = True
        return _CopilotRun(future, self.account)


class _CopilotAgentFactory:
    def __init__(self, account: str) -> None:
        self.account = account

    def create(self, options: _AgentOptions) -> _CopilotAgent:
        return _CopilotAgent(self.account, options)

    def resume(self, agent_id: str, options: _AgentOptions) -> _CopilotAgent:
        return _CopilotAgent(
            self.account,
            options,
            agent_id=str(agent_id),
            resume=True,
        )


async def _send_turn(
    *,
    account: str,
    session_id: str,
    resume: bool,
    model: str,
    prompt: str,
    mcp_servers: dict[str, Any],
    on_delta: Any,
) -> dict[str, Any]:
    from copilot import ToolSet
    from copilot.session import PermissionHandler

    client = await _client_for(account)
    events: list[Any] = []
    tool_call_started = False
    chosen_model = model or "auto"

    def on_event(event: Any) -> None:
        nonlocal tool_call_started, chosen_model
        events.append(event)
        typ = _event_type(event)
        data = getattr(event, "data", None)
        if typ == "assistant.message_delta" and callable(on_delta):
            chunk = str(getattr(data, "delta_content", "") or "")
            if chunk:
                on_delta({"type": "text-delta", "text": chunk})
        elif typ == "tool.execution_start":
            tool_call_started = True
            name = str(
                getattr(data, "mcp_tool_name", "")
                or getattr(data, "tool_name", "")
                or ""
            )
            if callable(on_delta):
                on_delta(
                    {
                        "type": "tool-call-started",
                        "tool_call": {"name": name},
                    }
                )
        elif typ == "session.auto_mode_resolved":
            chosen_model = str(getattr(data, "chosen_model", "") or chosen_model)

    kwargs = {
        "model": model or "auto",
        "available_tools": ToolSet().add_mcp("*"),
        "on_permission_request": PermissionHandler.approve_all,
        "on_event": on_event,
        "mcp_servers": mcp_servers,
        "streaming": True,
        "enable_session_store": True,
        "enable_skills": False,
        "skip_custom_instructions": True,
        "enable_host_git_operations": False,
        "mcp_oauth_token_storage": "in-memory",
    }
    if resume:
        try:
            session = await client.resume_session(session_id, **kwargs)
        except Exception:
            session = await client.create_session(session_id=session_id, **kwargs)
    else:
        session = await client.create_session(session_id=session_id, **kwargs)
    try:
        timeout = max(
            5.0,
            float(os.getenv("DESK_CHAT_TIMEOUT_SECONDS", "150") or 150),
        )
        result = await session.send_and_wait(prompt, timeout=timeout)
        data = getattr(result, "data", None)
        # ``send_and_wait`` may return the pre-tool narration even though the
        # same turn later emitted a completed post-tool answer. The event stream
        # is the authoritative sequence; surface its final top-level assistant
        # message and use the direct result only as a compatibility fallback.
        reply = _final_assistant_reply(events) or str(
            getattr(data, "content", "") or ""
        )
        messages = _conversation_messages(events)
        return {
            "reply": reply,
            "messages": messages,
            "model": chosen_model,
            "status": "completed" if reply else "error",
            "tool_call_started": tool_call_started,
        }
    finally:
        await session.disconnect()


def _conversation_messages(events: list[Any]) -> list[Any]:
    starts: dict[str, Any] = {}
    order: list[str] = []
    for event in events:
        typ = _event_type(event)
        data = getattr(event, "data", None)
        if typ == "tool.execution_start":
            call_id = str(getattr(data, "tool_call_id", "") or "")
            if not call_id:
                continue
            starts[call_id] = SimpleNamespace(
                type="tool_call",
                name=str(
                    getattr(data, "mcp_tool_name", "")
                    or getattr(data, "tool_name", "")
                    or ""
                ),
                result=None,
            )
            order.append(call_id)
        elif typ == "tool.execution_complete":
            call_id = str(getattr(data, "tool_call_id", "") or "")
            message = starts.get(call_id)
            if message is None:
                continue
            result = getattr(data, "result", None)
            message.result = str(getattr(result, "content", "") or "")
    return [starts[call_id] for call_id in order if call_id in starts]


def _final_assistant_reply(events: list[Any]) -> str:
    replies: list[str] = []
    for event in events:
        if _event_type(event) != "assistant.message":
            continue
        data = getattr(event, "data", None)
        if getattr(data, "parent_tool_call_id", None):
            continue
        content = str(getattr(data, "content", "") or "").strip()
        if content:
            replies.append(content)
    return replies[-1] if replies else ""


def load_copilot_cursor_bindings(account: str) -> Any:
    """Return the structural binding consumed by ``run_cursor_composer_turn``."""
    if not copilot_composer_available():
        raise CopilotSdkUnavailable(
            "GitHub Copilot SDK, launcher, or approved account pool is unavailable"
        )
    if account not in configured_copilot_accounts():
        raise CopilotSdkUnavailable(f"Copilot account is not approved: {account}")
    from scripts.research_data_mcp.desk_brain import _CursorSdkBindings

    def agent_options(*_args: Any, **kwargs: Any) -> _AgentOptions:
        return _AgentOptions(
            model=kwargs.get("model") or _ModelSelection("auto"),
            name=str(kwargs.get("name") or "research-desk"),
            mcp_servers=dict(kwargs.get("mcp_servers") or {}),
        )

    def stdio_mcp_server_config(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        env = dict(kwargs.get("env") or {})
        synthesis_read_only = str(
            env.get("RESEARCH_MCP_SYNTHESIS_READ_ONLY") or ""
        ).strip().lower() in {"1", "true", "yes"}
        return {
            "type": "local",
            "command": str(kwargs.get("command") or ""),
            "args": list(kwargs.get("args") or []),
            "cwd": str(kwargs.get("cwd") or ""),
            "env": env,
            "tools": (
                list(_SYNTHESIS_SAFE_TOOLS)
                if synthesis_read_only
                else list(_GENERAL_SAFE_TOOLS)
            ),
            "timeout": 30000,
        }

    return _CursorSdkBindings(
        agent=_CopilotAgentFactory(account),
        agent_options=agent_options,
        model_selection=lambda **kwargs: _ModelSelection(
            str(kwargs.get("id") or "auto")
        ),
        send_options=lambda **kwargs: _SendOptions(
            mcp_servers=dict(kwargs.get("mcp_servers") or {}),
            on_delta=kwargs.get("on_delta"),
        ),
        stdio_mcp_server_config=stdio_mcp_server_config,
        local_agent_options=lambda **_kwargs: {},
        cloud_agent_options=lambda **_kwargs: {},
    )


def _reset_copilot_provider_for_tests() -> None:
    """Clear only process-local selection state; clients die with the process."""
    _CLIENTS.clear()
