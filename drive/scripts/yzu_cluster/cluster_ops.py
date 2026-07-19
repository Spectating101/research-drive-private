#!/usr/bin/env python3
"""Remote cluster operations — keep heavy work off the personal controller."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from scripts.yzu_cluster.pools import ssh_run


def operations_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    return dict(cfg.get("operations") or {})


def cluster_only(cfg: dict[str, Any]) -> bool:
    return bool(operations_cfg(cfg).get("cluster_only"))


def disable_local_scrape(cfg: dict[str, Any]) -> bool:
    return bool(operations_cfg(cfg).get("disable_local_scrape"))


def prefer_local_collect(cfg: dict[str, Any], *, agent_cfg: dict[str, Any] | None = None) -> bool:
    """Whether http_manifest should collect on the controller vs windows_lab."""
    ops = operations_cfg(cfg)
    if ops.get("force_local_http_collect"):
        return True
    if ops.get("disable_local_http_collect"):
        return False
    if cluster_only(cfg):
        from scripts.yzu_cluster.windows_lab_readiness import probe_windows_lab

        ready = probe_windows_lab(cfg, agent_cfg)
        if not ready.get("http_shard_ready"):
            return True
        if ops.get("require_windows_repo_for_http") and not ready.get("queue_ready"):
            return True
        return False
    return True


def queue_tasks_enabled(cfg: dict[str, Any]) -> bool:
    if not cluster_only(cfg):
        return True
    return bool(operations_cfg(cfg).get("remote_queue_on_windows", True))


def remote_queue_on_windows(cfg: dict[str, Any], *, agent_cfg: dict[str, Any] | None = None) -> bool:
    if prefer_local_queue(cfg):
        return False
    if not cluster_only(cfg) or not queue_tasks_enabled(cfg):
        return False
    from scripts.yzu_cluster.windows_lab_readiness import probe_windows_lab

    ready = probe_windows_lab(cfg, agent_cfg)
    return bool(ready.get("queue_ready"))


def prefer_local_queue(cfg: dict[str, Any]) -> bool:
    """Skip windows_lab for collection queue when controller should run tasks locally."""
    return bool(operations_cfg(cfg).get("prefer_local_queue"))


def describe_job_route(cfg: dict[str, Any], job_type: str, *, script_key: str = "") -> str:
    """Short human label for where a YZU job executes."""
    engine = cfg.get("spectator_engine") or {}
    if job_type == "scraper_run":
        order = engine.get("pool_order_default") or engine.get("pool_order") or ["windows_lab"]
        return f"windows_lab cluster scrape ({' → '.join(order)})"
    if job_type == "http_manifest":
        return "windows_lab (remote HTTP collect)" if not prefer_local_collect(cfg) else "local or windows_lab"
    if job_type == "source_probe":
        return "optiplex (probe)"
    if job_type == "registered_pipeline":
        return "windows_lab" if operations_cfg(cfg).get("procurement_routes_via_cluster") else "cluster ops host"
    if job_type in {"harvest_shard", "datacite_harvest"}:
        return "windows_lab"
    if job_type in {"collection_queue_task", "collection_queue_batch"}:
        if prefer_local_queue(cfg):
            return "local collection queue (controller)"
        if remote_queue_on_windows(cfg):
            return "windows_lab (remote collection queue)"
        if cluster_only(cfg):
            return "unavailable (cluster_only, remote queue off)"
        return "local queue runner"
    if job_type == "collection_hydrate":
        return "optiplex (rclone pull from GDrive vault)"
    return "yzu cluster queue"


def format_cluster_summary(status: dict[str, Any]) -> str:
    """One-line cluster health for chat status replies."""
    pools = status.get("worker_pools") or {}
    wl = pools.get("windows_lab") or {}
    joined = int(wl.get("joined") or 0)
    total = int(wl.get("total") or 0)
    jobs = status.get("jobs") or {}
    queued = int(jobs.get("queued") or 0)
    running = int(jobs.get("running") or 0)
    controller = status.get("controller") or "optiplex"
    mode = "cluster_only" if status.get("cluster_only") else "hybrid"
    return (
        f"_Cluster ({controller}, {mode}): windows_lab **{joined}/{total}** joined · "
        f"jobs **{running}** running, **{queued}** queued_"
    )


def ops_host(cfg: dict[str, Any]) -> dict[str, str]:
    raw = operations_cfg(cfg).get("ops_host") or {}
    controller = cfg.get("controller") or {}
    pools = cfg.get("worker_pools") or {}
    spectator = pools.get("spectator") or {}
    mode = str(raw.get("mode") or "local").lower()
    key = str(raw.get("ssh_key") or spectator.get("ssh_key") or "")
    user = str(raw.get("user") or spectator.get("user") or "spectator")
    host = str(raw.get("host") or spectator.get("tailscale_ip") or spectator.get("host") or "100.96.62.97")
    target = str(raw.get("ssh_target") or f"{user}@{host}")
    repo = str(
        raw.get("repo_root")
        or controller.get("repo_root")
        or spectator.get("sharpe_repo")
        or "."
    )
    staging = str(raw.get("staging_root") or f"{repo}/data_lake/dataset_catalog/index_v3")
    return {
        "mode": mode,
        "ssh_target": target,
        "ssh_key": key,
        "repo_root": repo,
        "staging_root": staging,
    }


def ops_host_is_local(cfg: dict[str, Any]) -> bool:
    return ops_host(cfg).get("mode") == "local"


def use_ops_host_for_pool(cfg: dict[str, Any], pool: str) -> bool:
    """Only light orchestration pipelines run on the ops host."""
    if not cluster_only(cfg):
        return False
    return pool in {"optiplex", "ops"}


def run_on_ops_host(
    cfg: dict[str, Any],
    command: str,
    *,
    log_path: Path | None = None,
    timeout: int = 3600,
) -> subprocess.CompletedProcess[str]:
    """Run a shell command on the cluster ops host (local controller or remote SSH)."""
    host = ops_host(cfg)
    repo = Path(host["repo_root"]).expanduser().resolve()
    if host.get("mode") == "local":
        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("w", encoding="utf-8") as log:
                log.write(f"target=local\nrepo={repo}\n$ {command}\n\n")
                process = subprocess.run(
                    command,
                    shell=True,
                    cwd=repo,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
            return process
        return subprocess.run(
            command,
            shell=True,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    target = host["ssh_target"]
    key = host["ssh_key"]
    remote = f"export PATH=$HOME/bin:$PATH; cd {repo} && {command}"
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as log:
            log.write(f"target={target}\nrepo={repo}\n$ {command}\n\n")
            process = subprocess.run(
                [
                    "ssh",
                    "-n",
                    "-i",
                    key,
                    "-o",
                    "IdentitiesOnly=yes",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ConnectTimeout=15",
                    target,
                    remote,
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
                check=False,
            )
        return process
    return ssh_run(target, remote, key=key, timeout=timeout, capture=True)
