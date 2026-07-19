#!/usr/bin/env python3
"""Four-way procurement capability benchmark (same queries, comparable metrics)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from sharpe_kernel.paths import repo_root_from_file

REPO = repo_root_from_file(__file__)


def main() -> int:
    print("capability_benchmark.py is deprecated — use composer_mcp_benchmark.py (Composer-only).", file=sys.stderr)
    cmd = [sys.executable, str(REPO / "scripts/research_data_mcp/composer_mcp_benchmark.py")]
    return subprocess.call(cmd, cwd=str(REPO))


if __name__ == "__main__":
    raise SystemExit(main())
