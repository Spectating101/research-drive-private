#!/usr/bin/env python3
"""Run procurement commands on windows_lab workers via SSH."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.yzu_cluster.pools import ssh_run, windows_target, windows_workers


def windows_lab_paths(cfg: dict[str, Any], agent_cfg: dict[str, Any] | None = None) -> dict[str, str]:
    agent_cfg = agent_cfg or {}
    pool = cfg.get("worker_pools", {}).get("windows_lab") or {}
    engine = (cfg.get("spectator_engine") or {}).get("pools") or {}
    wl = engine.get("windows_lab") or {}
    sharpe = str(wl.get("sharpe_repo") or pool.get("sharpe_repo") or r"C:\cw\Sharpe-Renaissance")
    return {
        "key": str(agent_cfg.get("ssh_key") or pool.get("ssh_key") or ""),
        "inventory": str(agent_cfg.get("inventory") or pool.get("inventory") or ""),
        "remote_python": str(agent_cfg.get("remote_python") or pool.get("remote_python") or "py"),
        "sharpe_repo": sharpe,
        "molina_repo": str(wl.get("molina_repo") or pool.get("molina_repo") or r"C:\cw\Molina-Optiplex"),
    }


def translate_argv_for_windows(argv: list[str], *, sharpe_repo: str, remote_python: str) -> str:
    """Argv list → PowerShell command segment (run after cd sharpe_repo)."""
    py_remote = f"{sharpe_repo}\\.venv\\Scripts\\python.exe"
    quoted: list[str] = []
    for token in argv:
        t = str(token)
        if t in {".venv/bin/python", "python3", "python"} or t.endswith(".venv/bin/python"):
            quoted.append(f"& '{py_remote}'")
        elif t == "bash":
            quoted.append("bash")
        else:
            quoted.append(f"'{t.replace(chr(39), chr(39) * 2)}'")
    return " ".join(quoted)


def run_argv_on_windows_lab(
    cfg: dict[str, Any],
    agent_cfg: dict[str, Any],
    argv: list[str],
    log_path: Path,
    *,
    timeout: int = 3600,
) -> dict[str, Any]:
    from scripts.yzu_cluster.windows_lab_readiness import probe_windows_lab

    ready = probe_windows_lab(cfg, agent_cfg)
    if not ready.get("queue_ready"):
        raise RuntimeError(
            "windows_lab not provisioned for queue commands "
            f"({ready.get('reason')}); run locally or sync repo to {ready.get('sharpe_repo')}"
        )
    paths = windows_lab_paths(cfg, agent_cfg)
    workers = windows_workers(paths["inventory"], joined_only=True)
    if not workers:
        raise RuntimeError("no joined windows_lab workers for remote execution")
    inner = translate_argv_for_windows(
        argv,
        sharpe_repo=paths["sharpe_repo"],
        remote_python=paths["remote_python"],
    )
    ps = f"powershell.exe -NoProfile -Command \"cd '{paths['sharpe_repo']}'; {inner}\""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    last_error = ""
    for worker in workers:
        target = windows_target(worker, default_user="user")
        with log_path.open("w", encoding="utf-8") as log:
            log.write(f"target={target}\n{ps}\n\n")
            run = ssh_run(target, ps, key=paths["key"], timeout=timeout)
            log.write(run.stdout or "")
            log.write(run.stderr or "")
        if run.returncode == 0:
            return {
                "pool": "windows_lab",
                "target": target,
                "log": str(log_path),
                "collect_mode": "remote",
            }
        last_error = (run.stderr or run.stdout or f"exit {run.returncode}").strip()
    raise RuntimeError(last_error or "windows_lab remote command failed")
