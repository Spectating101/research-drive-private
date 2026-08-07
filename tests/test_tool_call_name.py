#!/usr/bin/env python3
"""Tool names come out of the shapes the Cursor SDK actually emits."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drive"))

from scripts.research_data_mcp.desk_brain import tool_call_name  # noqa: E402


def test_mcp_tool_name_is_read_from_nested_args():
    # Observed live: the name is never at the top level for MCP calls.
    call = {
        "type": "mcp",
        "args": {
            "providerIdentifier": "research_procurement",
            "toolName": "research_query_dataset",
            "args": {},
        },
    }
    assert tool_call_name(call) == ("research_query_dataset", True)


def test_builtin_tool_falls_back_to_type_and_is_not_mcp():
    call = {"type": "grep", "args": {"pattern": "x", "path": "/tmp"}}
    assert tool_call_name(call) == ("grep", False)


def test_top_level_name_still_works_if_a_build_provides_one():
    assert tool_call_name({"name": "read_file"}) == ("read_file", False)
    assert tool_call_name({"toolName": "read_file"}) == ("read_file", False)


def test_garbage_is_not_a_tool_call():
    assert tool_call_name(None) == ("", False)
    assert tool_call_name("mcp") == ("", False)
    assert tool_call_name({}) == ("", False)


def test_mcp_without_a_toolname_is_not_counted_as_evidence():
    call = {"type": "mcp", "args": {"providerIdentifier": "research_procurement"}}
    assert tool_call_name(call) == ("", False)
