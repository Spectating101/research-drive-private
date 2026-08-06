#!/usr/bin/env python3
"""Ask equipment interceptors — STRIPPED.

Former regex/script brain that stole Ask turns (search/status/probe/collect/
contextual) before Composer+MCP. Judgment and tool use belong to Cursor Composer.
This module keeps import-stable stubs that always decline.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.research_data_mcp.desk_brain import AgentTurn
else:
    AgentTurn = object  # runtime stubs only return None

_STRIPPED_NOTE = (
    "desk_direct_turns stripped — Composer + MCP owns Ask. "
    "No regex interceptors."
)


def probe_url_from_message(message: str, rail_context: dict[str, Any] | None = None) -> str | None:
    _ = message, rail_context
    return None


def is_direct_probe_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    _ = message, rail_context
    return False


def search_query_from_message(message: str, rail_context: dict[str, Any] | None = None) -> str | None:
    _ = message, rail_context
    return None


def is_direct_search_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    _ = message, rail_context
    return False


def discover_query_from_message(message: str, rail_context: dict[str, Any] | None = None) -> str | None:
    _ = message, rail_context
    return None


def is_direct_discover_search_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    _ = message, rail_context
    return False


def is_direct_collect_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    _ = message, rail_context
    return False


def is_direct_describe_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    _ = message, rail_context
    return False


def is_direct_query_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    _ = message, rail_context
    return False


def is_direct_discover_collect_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    _ = message, rail_context
    return False


def is_direct_approve_job_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    _ = message, rail_context
    return False


def is_direct_discovery_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    _ = message, rail_context
    return False


def is_direct_procurement_submit_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    _ = message, rail_context
    return False


def is_direct_equipment_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    _ = message, rail_context
    return False


def is_direct_status_message(message: str) -> bool:
    _ = message
    return False


def is_direct_schedule_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    _ = message, rail_context
    return False


def is_direct_intent_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    _ = message, rail_context
    return False


def is_direct_subscription_lifecycle_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    _ = message, rail_context
    return False


def is_direct_contextual_message(message: str, rail_context: dict[str, Any] | None = None) -> bool:
    _ = message, rail_context
    return False


def try_direct_status_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    _ = gateway, message, state
    return None


def try_direct_search_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    _ = gateway, message, state
    return None


def try_direct_discover_search_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    _ = gateway, message, state
    return None


def try_direct_refresh_tick_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    _ = gateway, message, state
    return None


def try_direct_schedule_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    _ = gateway, message, state
    return None


def try_direct_intent_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    _ = gateway, message, state
    return None


def try_direct_subscription_lifecycle_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    _ = gateway, message, state
    return None


def try_direct_discover_collect_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    _ = gateway, message, state
    return None


def try_direct_approve_job_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    _ = gateway, message, state
    return None


def try_direct_scrape_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    _ = gateway, message, state
    return None


def try_direct_contextual_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    _ = gateway, message, state
    return None


def try_direct_describe_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    _ = gateway, message, state
    return None


def try_direct_query_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    _ = gateway, message, state
    return None


def try_submit_collect_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    _ = gateway, message, state
    return None


def try_direct_probe_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    _ = gateway, message, state
    return None


def try_direct_equipment_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    """Always None — Composer + MCP owns Ask."""
    _ = gateway, message, state
    return None


def try_direct_synthesis_read_turn(gateway: Any, message: str, state: dict[str, Any]) -> AgentTurn | None:
    _ = gateway, message, state
    return None


def stripped_status() -> dict[str, Any]:
    return {
        "status": "stripped",
        "brain": "cursor_composer_mcp_only",
        "note": _STRIPPED_NOTE,
        "regex_interceptors": False,
    }
