#!/usr/bin/env python3
"""Execute YZU procurement jobs across worker pools."""

from __future__ import annotations

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from scripts.research_query_engine.procurement import ProcurementWorkbench
from scripts.yzu_cluster.acquisitions import (
    collect_local_manifest,
    enrich_http_manifest_plan,
    materialize_job,
    registry_spec_from_materialized,
    remote_collect_script,
    repo_relpath,
)
from scripts.yzu_cluster.pools import (
    datacite_shard_probe_argv,
    parse_datacite_lane_probe,
    parse_datacite_shard,
    scp_pull,
    ssh_run,
    windows_target,
    windows_workers,
)
from scripts.yzu_cluster.cluster_ops import cluster_only, run_on_ops_host, use_ops_host_for_pool
from scripts.yzu_cluster.spectator_engine import SpectatorEngine
from scripts.yzu_cluster.windows_remote import run_argv_on_windows_lab


ALLOWED_JOB_TYPES = {
    "source_probe",
    "http_manifest",
    "registered_pipeline",
    "collection_queue_task",
    "collection_queue_batch",
    "harvest_shard",
    "archive_upload",
    "scraper_run",
    "bigquery_query",
    "collection_hydrate",
    "huggingface_collect",
    "synthesis_execute",
}


def collection_queue_runner(repo_root: Path) -> Path:
    """Resolve the queue entrypoint in both split and legacy checkout layouts."""
    candidates = (
        repo_root / "scripts/run_data_collection_queue.py",
        repo_root / "drive/scripts/run_data_collection_queue.py",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("collection queue runner is missing from the private checkout")


class YzuExecutor:
    def __init__(self, repo_root: Path, cfg: dict[str, Any], jobs_root: Path, event_cb: Callable[[str, str, str], None] | None = None):
        self.repo_root = repo_root
        self.cfg = cfg
        self.jobs_root = jobs_root
        self.procurement = ProcurementWorkbench(jobs_root)
        self.remote_worker = remote_collect_script(repo_root)
        self.agent_cfg = self._load_agent_cfg()
        self.spectator = SpectatorEngine(self.repo_root, self.cfg, agent_cfg=self.agent_cfg)
        self._event = event_cb or (lambda _j, _l, _m: None)

    def _load_agent_cfg(self) -> dict[str, Any]:
        path = self.repo_root / self.cfg.get("agent", {}).get("config", "config/research_agent.json")
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def pipelines(self) -> dict[str, Any]:
        merged = dict(self.agent_cfg.get("pipelines", {}))
        merged.update(self.cfg.get("pipelines", {}))
        return merged

    def _python(self) -> str:
        venv = self.repo_root / ".venv/bin/python"
        return str(venv if venv.exists() else "python3")

    def execute(self, job_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        job_type = plan.get("job_type")
        if job_type not in ALLOWED_JOB_TYPES:
            raise ValueError(f"unsupported job_type: {job_type}")
        handler = {
            "source_probe": self._source_probe,
            "http_manifest": self._http_manifest,
            "registered_pipeline": self._registered_pipeline,
            "collection_queue_task": self._collection_queue_task,
            "collection_queue_batch": self._collection_queue_batch,
            "harvest_shard": self._harvest_shard,
            "archive_upload": self._archive_upload,
            "scraper_run": self._scraper_run,
            "bigquery_query": self._bigquery_query,
            "collection_hydrate": self._collection_hydrate,
            "huggingface_collect": self._huggingface_collect,
            "synthesis_execute": self._synthesis_execute,
        }[job_type]
        return handler(job_id, plan)

    def _synthesis_execute(self, job_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        from scripts.research_data_mcp.synthesis_executor import execute
        return execute(self.repo_root, job_id, plan)

    def _source_probe(self, _job_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        payload = self.procurement.probe(plan["url"], plan.get("title", ""))
        connector = payload.get("connector") or {}
        return {
            "connector_id": connector.get("id"),
            "source_url": connector.get("source_url"),
            "status": connector.get("status"),
            "summary": payload.get("summary"),
        }

    def _run_subprocess(
        self,
        job_id: str,
        command: list[str],
        *,
        log_name: str,
        timeout: int,
        pool: str = "optiplex",
    ) -> dict[str, Any]:
        log_path = self.jobs_root / job_id / log_name
        log_path.parent.mkdir(parents=True, exist_ok=True)
        shell_cmd = subprocess.list2cmdline(command)
        if use_ops_host_for_pool(self.cfg, pool):
            process = run_on_ops_host(self.cfg, shell_cmd, log_path=log_path, timeout=timeout)
        elif pool == "windows_lab":
            from scripts.yzu_cluster.windows_lab_readiness import probe_windows_lab

            if not probe_windows_lab(self.cfg, self.agent_cfg).get("queue_ready"):
                raise RuntimeError(
                    "windows_lab pool requested but workers are not provisioned; "
                    "use optiplex or run scripts/yzu_cluster/provision_windows_worker.sh"
                )
            meta = run_argv_on_windows_lab(
                self.cfg,
                self.agent_cfg,
                command,
                log_path,
                timeout=timeout,
            )
            rel_log = Path(meta["log"])
            if rel_log.is_absolute():
                try:
                    rel_log = rel_log.relative_to(self.repo_root)
                except ValueError:
                    pass
            return {"pool": "windows_lab", "log": str(rel_log), "target": meta.get("target")}
        elif cluster_only(self.cfg) and pool in {"spectator", "windows_lab"}:
            raise RuntimeError(
                f"pool {pool} is not an ops host; use scraper_run/harvest_shard instead of shell pipelines"
            )
        else:
            with log_path.open("w", encoding="utf-8") as log:
                process = subprocess.run(
                    command,
                    cwd=self.repo_root,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                    check=False,
                )
        if process.returncode:
            raise RuntimeError(f"command failed ({process.returncode}); see {log_path}")
        return {"pool": pool, "log": str(log_path.relative_to(self.repo_root))}

    def _registered_pipeline(self, job_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        pipeline_id = plan["pipeline_id"]
        pipeline = self.pipelines().get(pipeline_id)
        if not pipeline:
            raise ValueError(f"pipeline is not registered: {pipeline_id}")
        command = [str(part) for part in pipeline["command"]]
        pool = str(pipeline.get("pool", "optiplex"))
        if pool == "windows_lab":
            from scripts.yzu_cluster.windows_lab_readiness import probe_windows_lab

            if not probe_windows_lab(self.cfg, self.agent_cfg).get("queue_ready"):
                self._event(job_id, "warn", "windows_lab not provisioned; running pipeline on optiplex")
                pool = "optiplex"
        meta = self._run_subprocess(
            job_id,
            command,
            log_name="pipeline.log",
            timeout=int(plan.get("timeout_seconds", 3600)),
            pool=pool,
        )
        return {"pipeline_id": pipeline_id, **meta}

    def _collection_queue_task(self, job_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        from scripts.yzu_cluster.cluster_ops import remote_queue_on_windows

        task_id = plan["task_id"]
        queue_path = self.repo_root / "config/data_collection_queue.json"
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        task = next((t for t in queue.get("tasks", []) if t.get("id") == task_id), None)
        if not task:
            raise ValueError(f"unknown collection queue task: {task_id}")
        if task.get("credential_required"):
            raise ValueError(f"task {task_id} requires credentials")
        command = [str(part) for part in task["command"]]
        timeout = int(plan.get("timeout_seconds", 7200))
        if remote_queue_on_windows(self.cfg, agent_cfg=self.agent_cfg):
            log_path = self.jobs_root / job_id / f"queue_{task_id}.log"
            try:
                meta = run_argv_on_windows_lab(self.cfg, self.agent_cfg, command, log_path, timeout=timeout)
                rel_log = Path(meta["log"])
                if rel_log.is_absolute():
                    try:
                        rel_log = rel_log.relative_to(self.repo_root)
                    except ValueError:
                        pass
                return {
                    "task_id": task_id,
                    "output_hint": task.get("output_hint", ""),
                    "pool": "windows_lab",
                    "log": str(rel_log),
                    "target": meta.get("target"),
                }
            except RuntimeError as exc:
                fallback = self.cfg.get("operations", {}).get("queue_local_fallback", True)
                if not fallback:
                    raise
                self._event(job_id, "warn", f"windows_lab queue failed ({exc}); running on controller")
        if cluster_only(self.cfg) and not self.cfg.get("operations", {}).get("queue_local_fallback", True):
            raise RuntimeError(
                f"collection task {task_id} is disabled in cluster_only mode; enable remote_queue_on_windows or queue_local_fallback"
            )
        log_path = self.repo_root / "logs/data_collection_queue" / f"yzu_{job_id}_{task_id}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.run(
                command,
                cwd=self.repo_root,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=int(plan.get("timeout_seconds", 7200)),
                check=False,
            )
        if process.returncode:
            raise RuntimeError(f"collection task {task_id} exited {process.returncode}")
        return {
            "task_id": task_id,
            "output_hint": task.get("output_hint", ""),
            "log": str(log_path.relative_to(self.repo_root)),
            "collect_mode": "local",
        }

    def _collection_queue_batch(self, job_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        from scripts.yzu_cluster.cluster_ops import remote_queue_on_windows

        runner = collection_queue_runner(self.repo_root)
        runner_arg = runner.relative_to(self.repo_root).as_posix()
        command = ["python3", runner_arg]
        only = plan.get("only") or plan.get("task_ids")
        if only:
            if isinstance(only, list):
                only = ",".join(only)
            command.extend(["--only", str(only)])
        if plan.get("dry_run"):
            command.append("--dry-run")
        timeout = int(plan.get("timeout_seconds", 14400))
        if remote_queue_on_windows(self.cfg, agent_cfg=self.agent_cfg):
            log_path = self.jobs_root / job_id / "queue_batch.log"
            try:
                meta = run_argv_on_windows_lab(self.cfg, self.agent_cfg, command, log_path, timeout=timeout)
                rel_log = Path(meta["log"])
                if rel_log.is_absolute():
                    try:
                        rel_log = rel_log.relative_to(self.repo_root)
                    except ValueError:
                        pass
                return {"log": str(rel_log), "only": only or "all_runnable", "pool": "windows_lab"}
            except RuntimeError as exc:
                if not self.cfg.get("operations", {}).get("queue_local_fallback", True):
                    raise
                self._event(job_id, "warn", f"windows_lab batch failed ({exc}); running on controller")
        if cluster_only(self.cfg) and not self.cfg.get("operations", {}).get("queue_local_fallback", True):
            raise RuntimeError(
                "collection_queue_batch is disabled in cluster_only mode; enable remote_queue_on_windows or queue_local_fallback"
            )
        log_path = self.repo_root / "logs/data_collection_queue" / f"yzu_{job_id}_batch.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.run(
                command,
                cwd=self.repo_root,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=int(plan.get("timeout_seconds", 14400)),
                check=False,
            )
        if process.returncode:
            raise RuntimeError(f"collection queue batch exited {process.returncode}")
        return {"log": str(log_path.relative_to(self.repo_root)), "only": only or "all_runnable"}

    def _harvest_shard(self, job_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        shard = plan["shard"]
        action = plan.get("action", "restart")
        shards_file = self.repo_root / "scripts/data_catalog/datacite_y2025_parallel_shards.list"
        meta = parse_datacite_shard(shards_file, shard)
        host = plan.get("host") or meta["host"]
        log_path = self.jobs_root / job_id / f"harvest_{shard}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        if host == "local":
            if cluster_only(self.cfg) or self.cfg.get("operations", {}).get("disable_local_harvest"):
                raise RuntimeError(
                    f"local DataCite harvest disabled (cluster_only); assign {shard} to a Windows worker"
                )
            if action == "status":
                base = self.repo_root / "data_lake/dataset_catalog/index_v3" / shard
                hb = base / "datacite.heartbeat.json"
                comp = base / "datacite.complete.json"
                return {
                    "shard": shard,
                    "host": host,
                    "action": action,
                    "complete": comp.exists(),
                    "heartbeat": json.loads(hb.read_text()) if hb.exists() else {},
                }
            if action == "restart":
                svc = f"datacite-local-{shard}.service"
                with log_path.open("w", encoding="utf-8") as log:
                    process = subprocess.run(
                        ["systemctl", "--user", "restart", svc],
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        timeout=60,
                        check=False,
                    )
                if process.returncode:
                    raise RuntimeError(f"failed to restart {svc}")
                return {"shard": shard, "host": host, "action": action, "service": svc}
            env = os.environ.copy()
            env["DATACITE_LOCAL_SHARD"] = shard
            if meta.get("query"):
                env["DATACITE_LOCAL_QUERY"] = meta["query"]
            script = self.repo_root / "scripts/data_catalog/run_datacite_local_shard.sh"
            with log_path.open("w", encoding="utf-8") as log:
                process = subprocess.run(
                    ["bash", str(script)],
                    cwd=self.repo_root,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=int(plan.get("timeout_seconds", 7200)),
                    check=False,
                )
            if process.returncode:
                raise RuntimeError(f"local harvest {shard} exited {process.returncode}")
            return {"shard": shard, "pool": "optiplex", "action": action, "log": str(log_path.relative_to(self.repo_root))}

        key = self.agent_cfg.get("ssh_key") or self.cfg["worker_pools"]["windows_lab"]["ssh_key"]
        target = f"user@{host}"
        if action == "status":
            run = ssh_run(
                target,
                " ".join(datacite_shard_probe_argv(shard)),
                key=key,
                timeout=30,
            )
            line = [x.strip() for x in (run.stdout or "").splitlines() if x.strip()][-1:] or [""]
            parsed = parse_datacite_lane_probe(line[0]) if run.returncode == 0 else {}
            return {
                "shard": shard,
                "host": host,
                "action": action,
                "probe": parsed,
                "stdout": (run.stdout or "").strip(),
                "ok": run.returncode == 0 and bool(parsed),
            }
        if action == "pull_meta":
            remote = f"C:/cw/dataset_index_{shard}/datacite.heartbeat.json"
            local = log_path.parent / f"{shard}_heartbeat.json"
            scp_pull(target, remote, local, key=key, timeout=120)
            payload = json.loads(local.read_text(encoding="utf-8")) if local.exists() else {}
            return {"shard": shard, "host": host, "action": action, "heartbeat": payload}
        ps = (
            "powershell.exe -NoProfile -ExecutionPolicy Bypass "
            f"-File C:/Users/user/restart_datacite_shard_clean.ps1 -ShardName {shard}"
        )
        with log_path.open("w", encoding="utf-8") as log:
            run = ssh_run(target, ps, key=key, timeout=120)
            log.write(run.stdout or "")
            log.write(run.stderr or "")
        if run.returncode:
            raise RuntimeError(f"remote harvest restart failed for {shard}@{host}")
        return {"shard": shard, "host": host, "action": action, "log": str(log_path.relative_to(self.repo_root))}

    def _archive_upload(self, job_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        local_path = self.repo_root / plan["local_path"]
        if not local_path.exists():
            raise ValueError(f"local path missing: {local_path}")
        remote = plan.get("remote_path") or f"{self.cfg['storage']['drive_root']}/{plan.get('remote_suffix', local_path.name)}"
        log_path = self.jobs_root / job_id / "archive.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "rclone",
            "copy",
            str(local_path),
            remote,
            "--transfers",
            "2",
            "--checkers",
            "4",
            "--retries",
            "5",
            "--low-level-retries",
            "10",
        ]
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=int(plan.get("timeout_seconds", 3600)), check=False)
        if process.returncode:
            raise RuntimeError(f"rclone copy failed ({process.returncode})")
        if plan.get("verify", True):
            check = subprocess.run(
                ["rclone", "check", str(local_path), remote, "--one-way", "--size-only"],
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            if check.returncode:
                raise RuntimeError("rclone verify failed after upload")
        return {"local_path": str(local_path.relative_to(self.repo_root)), "remote_path": remote, "verified": bool(plan.get("verify", True))}

    def _collection_hydrate(self, job_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        from scripts.research_data_mcp.collection_hydrate import execute_hydrate
        from scripts.research_data_mcp.registry_hydrate import _hydrate_registry_file

        if plan.get("scope") == "registry_file":
            log_path = self.jobs_root / job_id / "hydrate.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            return _hydrate_registry_file(plan, log_path=log_path)
        return execute_hydrate(self.repo_root, plan, job_id=job_id)

    def _huggingface_collect(self, job_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        hf_id = str(plan.get("hf_dataset_id") or "").strip().removeprefix("hf:")
        if not hf_id:
            raise ValueError("hf_dataset_id is required")
        command = [
            self._python(),
            "scripts/hf_collect_dataset.py",
            "--dataset-id",
            hf_id,
            "--split",
            str(plan.get("split") or "train"),
            "--max-shards",
            str(int(plan.get("max_shards") or 2)),
        ]
        meta = self._run_subprocess(
            job_id,
            command,
            log_name="hf_collect.log",
            timeout=int(plan.get("timeout_seconds", 3600)),
            pool=str(plan.get("pool") or "optiplex"),
        )
        from scripts.hf_collect_dataset import hf_slug

        slug = hf_slug(hf_id)
        manifest_path = self.repo_root / "data_lake/procured/huggingface" / slug / "manifest.json"
        materialized: dict[str, Any] = {}
        if manifest_path.is_file():
            materialized = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {
            "hf_dataset_id": hf_id,
            "materialized": materialized,
            "canonical_dir": materialized.get("canonical_dir"),
            **meta,
        }

    def _scraper_run(self, job_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        return self.spectator.run(
            job_id,
            plan,
            jobs_root=self.jobs_root,
            event_cb=self._event,
        )

    def _bigquery_query(self, job_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        from scripts.research_data_mcp.bigquery_client import dry_run_query, read_query

        sql = str(plan.get("sql") or "").strip()
        sql_file = plan.get("sql_file")
        if sql_file:
            path = self.repo_root / str(sql_file)
            if not path.is_file():
                raise ValueError(f"sql_file not found: {sql_file}")
            sql = path.read_text(encoding="utf-8")
        if not sql:
            raise ValueError("sql or sql_file is required")

        project = str(plan.get("project") or "")
        location = str(plan.get("location") or "US")
        max_bytes = plan.get("max_bytes_billed")
        kwargs: dict[str, Any] = {"project": project, "location": location}
        if max_bytes is not None:
            kwargs["max_bytes_billed"] = int(max_bytes)

        out_dir = self.jobs_root / job_id
        out_dir.mkdir(parents=True, exist_ok=True)

        execute = bool(plan.get("execute")) or not bool(plan.get("dry_run", True))
        if not execute:
            report = dry_run_query(sql, **kwargs)
            report_path = out_dir / "bigquery_dry_run.json"
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            return {**report, "mode": "dry_run", "report": str(report_path.relative_to(self.repo_root))}

        rows = read_query(
            sql,
            confirm=str(plan.get("confirm") or ""),
            max_rows=int(plan.get("max_rows", 1000)),
            **kwargs,
        )
        report_path = out_dir / "bigquery_results.json"
        report_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
        return {**rows, "mode": "run", "report": str(report_path.relative_to(self.repo_root))}

    def _http_manifest(self, job_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        from scripts.research_data_mcp.domain_packs import load_domain_packs

        plan = enrich_http_manifest_plan(dict(plan), self.procurement, domain_packs=load_domain_packs(self.repo_root))
        items = plan.get("items") or []
        if not items:
            raise ValueError("http_manifest requires at least one downloadable item (probe may have found none)")
        force_local = bool(plan.get("local_collect")) or bool(plan.get("public_direct_url"))
        disable_local = bool(self.cfg.get("operations", {}).get("disable_local_http_collect"))
        if force_local:
            prefer_local = True
        else:
            from scripts.yzu_cluster.cluster_ops import prefer_local_collect

            prefer_local = prefer_local_collect(self.cfg, agent_cfg=self.agent_cfg)
        if prefer_local:
            result = collect_local_manifest(self.repo_root, job_id, plan, jobs_root=self.jobs_root)
            if not force_local and cluster_only(self.cfg):
                from scripts.yzu_cluster.windows_lab_readiness import probe_windows_lab

                if not probe_windows_lab(self.cfg, self.agent_cfg, force=True).get("http_shard_ready"):
                    result["collect_mode"] = "local_fallback"
        else:
            try:
                result = self._http_manifest_remote(job_id, plan)
            except Exception as exc:
                # The personal controller is a disaster-recovery path, not a
                # second attempt after a Windows collection failure. Re-probe
                # the pool so source/provider errors stay attached to the
                # Windows attempt instead of silently moving execution local.
                from scripts.yzu_cluster.windows_lab_readiness import probe_windows_lab

                ready = probe_windows_lab(self.cfg, self.agent_cfg, force=True)
                windows_unavailable = not bool(ready.get("http_shard_ready"))
                if (
                    disable_local
                    or not self.cfg.get("operations", {}).get("http_remote_fallback", True)
                    or not windows_unavailable
                ):
                    raise
                self._event(job_id, "warn", f"windows_lab unavailable ({exc}); collecting on controller fallback")
                result = collect_local_manifest(self.repo_root, job_id, plan, jobs_root=self.jobs_root)
                result["collect_mode"] = "local_fallback"
        return materialize_job(self.repo_root, job_id, plan, result, cfg=self.cfg)

    def _http_manifest_remote(self, job_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        items = plan["items"]
        workers = self._windows_workers()[: min(int(plan.get("shards", 4)), int(self.agent_cfg.get("max_cluster_workers", 4)))]
        if not workers:
            raise RuntimeError("no joined windows_lab workers")
        shards = [[] for _ in workers]
        for index, item in enumerate(items):
            shards[index % len(shards)].append(item)
        job_dir = self.jobs_root / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        results = []
        with ThreadPoolExecutor(max_workers=len(workers)) as pool:
            futures = []
            for index, (worker, shard_items) in enumerate(zip(workers, shards), 1):
                if shard_items:
                    futures.append(pool.submit(self._dispatch_shard, job_id, index, worker, shard_items, job_dir, plan))
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                self._event(job_id, "info", f"Shard {result['shard']} returned from {result['worker']}")
        return {"artifacts": sorted(results, key=lambda row: row["shard"]), "output_dir": repo_relpath(job_dir, self.repo_root), "collect_mode": "remote"}

    def _windows_workers(self) -> list[dict[str, Any]]:
        inv = self.agent_cfg.get("inventory") or self.cfg["worker_pools"]["windows_lab"]["inventory"]
        key = self.agent_cfg.get("ssh_key") or self.cfg["worker_pools"]["windows_lab"].get("ssh_key")
        # Skip inventory hosts that are marked joined but SSH-dead — otherwise the
        # first shards burn ConnectTimeout before local_fallback.
        return windows_workers(inv, require_reachable=True, ssh_key=key)

    def _dispatch_shard(self, job_id: str, shard: int, worker: dict, items: list[dict], job_dir: Path, plan: dict) -> dict:
        prefix = f"rd_{job_id}_{shard:02d}"
        manifest = job_dir / f"{prefix}.json"
        artifact = job_dir / f"{prefix}.zip"
        manifest.write_text(json.dumps({"job_id": job_id, "shard": shard, "items": items}, indent=2), encoding="utf-8")
        key = self.agent_cfg.get("ssh_key") or self.cfg["worker_pools"]["windows_lab"]["ssh_key"]
        target = windows_target(worker)
        common = ["-q", "-i", key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8"]
        remote_script = f"{prefix}_collect.py"
        remote_manifest = f"{prefix}.json"
        remote_artifact = f"{prefix}.zip"
        remote_policy = "network_policy.py"
        policy_src = self.remote_worker.with_name("network_policy.py")
        if not policy_src.is_file():
            raise FileNotFoundError(f"network policy module missing next to collector: {policy_src}")
        subprocess.run(["scp", *common, str(self.remote_worker), f"{target}:{remote_script}"], check=True, timeout=60)
        # Sibling import: remote_collect falls back to `from network_policy import …`
        subprocess.run(["scp", *common, str(policy_src), f"{target}:{remote_policy}"], check=True, timeout=60)
        subprocess.run(["scp", *common, str(manifest), f"{target}:{remote_manifest}"], check=True, timeout=60)
        remote_python = (
            self.agent_cfg.get("remote_python")
            or self.cfg.get("worker_pools", {}).get("windows_lab", {}).get("remote_python")
            or "py -3"
        )
        command = (
            f"{remote_python} .\\{remote_script} --manifest .\\{remote_manifest} "
            f"--artifact .\\{remote_artifact} --workers {min(int(plan.get('per_node_workers', 2)), 4)} "
            f"--timeout {min(int(plan.get('request_timeout', 60)), 300)} --retries {min(int(plan.get('retries', 3)), 5)} "
            f"--delay {max(float(plan.get('delay_seconds', 0.25)), 0.1)}"
        )
        run = subprocess.run(
            ["ssh", "-n", "-i", key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", target, command],
            capture_output=True,
            text=True,
            timeout=int(plan.get("timeout_seconds", 3600)),
            check=False,
        )
        if run.returncode != 0:
            raise RuntimeError(f"{worker['hostname']} shard {shard} collect exited {run.returncode}: {(run.stderr or run.stdout)[-500:]}")
        subprocess.run(["scp", *common, f"{target}:{remote_artifact}", str(artifact)], check=True, timeout=300)
        if not artifact.exists() or artifact.stat().st_size < 32:
            raise RuntimeError(f"{worker['hostname']} shard {shard} artifact missing or too small ({artifact.stat().st_size if artifact.exists() else 0} bytes)")
        cleanup = (
            f"powershell -NoProfile -Command \"Remove-Item -Force -ErrorAction SilentlyContinue "
            f"'{remote_script}','{remote_policy}','{remote_manifest}','{remote_artifact}'\""
        )
        subprocess.run(["ssh", "-n", "-i", key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", target, cleanup], check=False, timeout=30)
        return {
            "shard": shard,
            "worker": worker["hostname"],
            "artifact": repo_relpath(artifact, self.repo_root),
            "bytes": artifact.stat().st_size,
            "worker_exit": run.returncode,
        }
