#!/usr/bin/env python3
"""Probe windows_lab workers — avoid routing queue jobs to hosts without Sharpe repo."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any
from sharpe_kernel.paths import repo_root_from_file

_ROOT = repo_root_from_file(__file__)
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.yzu_cluster.pools import ssh_run, windows_host_reachable, windows_target, windows_workers
from scripts.yzu_cluster.windows_remote import windows_lab_paths

_CACHE: dict[str, Any] = {"ts": 0.0, "payload": {}}
_CACHE_TTL = 300.0


def _probe_sharpe_repo(target: str, sharpe_repo: str, key: str, timeout: int = 12) -> str:
    """Return FULL for queue execution, THIN for HTTP pull-workers, or missing."""
    ps = (
        "powershell.exe -NoProfile -Command "
        f"\"if (Test-Path '{sharpe_repo}\\.venv\\Scripts\\python.exe') {{ 'FULL' }} "
        f"elseif ((Test-Path '{sharpe_repo}\\drive\\scripts\\yzu_cluster\\remote_worker.py') "
        f"-and (Get-Command py -ErrorAction SilentlyContinue)) {{ 'THIN' }} "
        f"elseif (Test-Path '{sharpe_repo}') {{ 'PARTIAL' }} else {{ 'MISSING' }}\""
    )
    run = ssh_run(target, ps, key=key, timeout=timeout)
    line = (run.stdout or "").strip().splitlines()[-1].strip() if run.stdout else ""
    return line if run.returncode == 0 else "ERROR"


def _probe_scraper_host(target: str, sharpe_repo: str, key: str, timeout: int = 20) -> str:
    """Return OK, NO_NODE, NO_SCRIPT, NO_PLAYWRIGHT, or MISSING."""
    ps = (
        "powershell.exe -NoProfile -Command "
        "\"$p=[Environment]::GetEnvironmentVariable('Path','User')+';'+[Environment]::GetEnvironmentVariable('Path','Machine'); "
        f"if (-not (Test-Path '{sharpe_repo}')) {{ 'MISSING'; exit 0 }} "
        f"if (-not (Test-Path '{sharpe_repo}\\scripts\\yzu_cluster\\scrapers\\generic_url_scrape.mjs')) {{ 'NO_SCRIPT'; exit 0 }} "
        f"if (-not (Test-Path '{sharpe_repo}\\node_modules\\playwright')) {{ 'NO_PLAYWRIGHT'; exit 0 }} "
        "$node=(Get-Command node -ErrorAction SilentlyContinue); "
        "if (-not $node) { $node = Get-ChildItem \"$env:LOCALAPPDATA\\Microsoft\\WinGet\\Links\\node.exe\" -ErrorAction SilentlyContinue } "
        "if (-not $node) { 'NO_NODE'; exit 0 } "
        "'OK'\""
    )
    run = ssh_run(target, ps, key=key, timeout=timeout)
    if run.returncode != 0:
        return "ERROR"
    lines = [line.strip() for line in (run.stdout or "").splitlines() if line.strip()]
    return lines[-1] if lines else "ERROR"


def probe_windows_lab(
    cfg: dict[str, Any],
    agent_cfg: dict[str, Any] | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Return joined/provisioned worker counts and whether queue/http routing is safe."""
    now = time.time()
    if not force and _CACHE["payload"] and (now - float(_CACHE["ts"])) < _CACHE_TTL:
        return dict(_CACHE["payload"])

    paths = windows_lab_paths(cfg, agent_cfg)
    workers = windows_workers(paths["inventory"], joined_only=True)
    sharpe_repo = paths["sharpe_repo"]
    key = paths["key"]
    provisioned: list[str] = []
    thin_workers: list[str] = []
    partial: list[str] = []
    reachable_hosts: list[str] = []
    scraper_hosts: list[str] = []
    errors: list[str] = []
    scraper_errors: list[str] = []

    for worker in workers:
        host = str(worker.get("hostname") or worker.get("tailscale_ip") or "")
        target = windows_target(worker)
        try:
            if not windows_host_reachable(worker, key=key, force=force):
                errors.append(f"{host}: ssh unreachable")
                continue
            reachable_hosts.append(host)
            repo_state = _probe_sharpe_repo(target, sharpe_repo, key)
            if repo_state == "FULL":
                provisioned.append(host)
            elif repo_state == "THIN":
                thin_workers.append(host)
            else:
                ps = (
                    "powershell.exe -NoProfile -Command "
                    f"\"if (Test-Path '{sharpe_repo}') {{ 'PARTIAL' }} else {{ 'MISSING' }}\""
                )
                run = ssh_run(target, ps, key=key, timeout=12)
                tag = (run.stdout or "").strip().splitlines()[-1].strip() if run.stdout else "MISSING"
                if tag == "PARTIAL":
                    partial.append(host)
                else:
                    errors.append(f"{host}: repo missing at {sharpe_repo}")
            scraper_tag = _probe_scraper_host(target, sharpe_repo, key)
            if scraper_tag == "OK":
                scraper_hosts.append(host)
            elif scraper_tag not in {"MISSING"}:
                scraper_errors.append(f"{host}: {scraper_tag}")
        except Exception as exc:
            errors.append(f"{host}: {exc}")

    payload = {
        "sharpe_repo": sharpe_repo,
        "joined_workers": len(workers),
        "reachable_workers": len(reachable_hosts),
        "reachable_hosts": reachable_hosts[:8],
        "provisioned_workers": len(provisioned),
        "thin_workers": len(thin_workers),
        "partial_workers": len(partial),
        "provisioned_hosts": provisioned[:8],
        "scraper_ready_hosts": scraper_hosts[:8],
        "scraper_ready": len(scraper_hosts) > 0,
        "queue_ready": len(provisioned) > 0,
        # HTTP SCP shards only need SSH+python; full Sharpe venv is optional.
        "http_shard_ready": len(reachable_hosts) > 0,
        "reason": (
            f"{len(reachable_hosts)}/{len(workers)} joined hosts SSH-reachable; "
            f"{len(provisioned)} full queue workers and {len(thin_workers)} thin HTTP workers at {sharpe_repo}"
            if workers
            else "no joined windows_lab workers"
        ),
        "scraper_reason": (
            f"{len(scraper_hosts)}/{len(workers)} workers ready for generic_url_scrape"
            if workers
            else "no joined windows_lab workers"
        ),
        "errors": errors[:6],
        "scraper_errors": scraper_errors[:6],
    }
    _CACHE["ts"] = now
    _CACHE["payload"] = payload
    return dict(payload)


def write_status_file(repo_root: Path, status: dict[str, Any]) -> Path:
    out = repo_root / "data_lake/yzu_cluster/status/windows_lab_readiness.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(status, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    root = _ROOT
    cfg = json.loads((root / "config/yzu_cluster.json").read_text(encoding="utf-8"))
    agent_cfg = {}
    agent_path = root / cfg.get("agent", {}).get("config", "config/research_agent.json")
    if agent_path.is_file():
        agent_cfg = json.loads(agent_path.read_text(encoding="utf-8"))
    status = probe_windows_lab(cfg, agent_cfg, force="--force" in sys.argv)
    path = write_status_file(root, status)
    print(json.dumps(status, indent=2))
    print(f"wrote {path}")
