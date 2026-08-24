#!/usr/bin/env python3
"""Read-only production preflight for the GitHub Copilot desk pool."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

from scripts.research_data_mcp.desk_copilot_provider import (
    configured_copilot_accounts,
    copilot_launcher_path,
)


def probe_copilot_pool(
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    requested = configured_copilot_accounts()
    launcher = copilot_launcher_path()
    problems: list[str] = []
    if not requested:
        problems.append("DESK_COPILOT_ACCOUNTS is empty")
    if not launcher.is_file() or not os.access(launcher, os.X_OK):
        problems.append(f"Copilot launcher is not executable: {launcher}")
    try:
        sdk_version = importlib.metadata.version("github-copilot-sdk")
    except importlib.metadata.PackageNotFoundError:
        sdk_version = ""
        problems.append("github-copilot-sdk is not installed")

    active: list[str] = []
    if not problems:
        env = dict(os.environ)
        env.pop("COPILOT_ACCOUNT", None)
        try:
            completed = runner(
                [str(launcher), "--list-accounts"],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            problems.append(f"Copilot account probe failed: {type(exc).__name__}")
        else:
            if int(getattr(completed, "returncode", 1) or 0) != 0:
                problems.append("Copilot launcher could not validate its account roster")
            else:
                active = [
                    line.strip()
                    for line in str(getattr(completed, "stdout", "") or "").splitlines()
                    if line.strip()
                ]
                missing = [account for account in requested if account not in active]
                if missing:
                    problems.append(
                        "configured Copilot account(s) are inactive: " + ", ".join(missing)
                    )

    return {
        "ready": not problems,
        "requested_accounts": requested,
        "active_requested_accounts": [name for name in requested if name in active],
        "launcher": str(launcher),
        "sdk_version": sdk_version,
        "problems": problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = probe_copilot_pool()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("copilot_pool=" + ("ready" if result["ready"] else "not_ready"))
        print("accounts=" + ",".join(result["active_requested_accounts"]))
        print("sdk=" + str(result["sdk_version"] or "missing"))
        for problem in result["problems"]:
            print("FAIL: " + problem)
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

