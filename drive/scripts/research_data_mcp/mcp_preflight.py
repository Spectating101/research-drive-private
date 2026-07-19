#!/usr/bin/env python3
"""Preflight checks before starting the research MCP server."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from sharpe_kernel.paths import repo_root_from_file


def check_mcp_import(python: str | None = None) -> tuple[bool, str]:
    import subprocess

    exe = python or sys.executable
    proc = subprocess.run(
        [exe, "-c", "import mcp; from mcp.server.fastmcp import FastMCP"],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return True, "mcp package ok"
    err = (proc.stderr or proc.stdout or "unknown error").strip().splitlines()[-1]
    return False, err


def main() -> int:
    root = repo_root_from_file(__file__)
    ok, detail = check_mcp_import()
    payload = {"ok": ok, "detail": detail, "repo_root": str(root)}
    print(json.dumps(payload))
    if not ok:
        print(
            f"\nFix: {root}/.venv/bin/pip install 'mcp>=1.26.0'",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
