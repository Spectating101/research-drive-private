#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from scripts.research_data_mcp.bootstrap import create_stack
from scripts.research_data_mcp.mcp_instructions import mcp_server_instructions
from scripts.research_data_mcp.mcp_register import build_mcp_server
from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)
REGISTRY = ROOT / "config/research_query_registry.json"

mcp = FastMCP(
    "Research Procurement MCP",
    instructions=mcp_server_instructions(),
    host=os.getenv("RESEARCH_MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("RESEARCH_MCP_PORT", "8770")),
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
)

_stack = create_stack(ROOT, REGISTRY)
build_mcp_server(mcp, _stack.tools, registry_text=REGISTRY.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "streamable-http", "sse"], default=os.getenv("RESEARCH_MCP_TRANSPORT", "stdio"))
    args = parser.parse_args()
    mcp.run(transport=args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
