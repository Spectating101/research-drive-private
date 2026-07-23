#!/usr/bin/env python3
"""Dispatch Molina spectator scrapers across cluster pools (optiplex, windows, spectator)."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.yzu_cluster.pools import scp_pull, scp_pull_recursive, spectator_targets, ssh_run, windows_target, windows_workers
from scripts.yzu_cluster.cluster_ops import disable_local_scrape
from scripts.yzu_cluster.acquisitions import repo_relpath


@dataclass
class ResolvedScript:
    script_key: str
    script: str
    args: list[str]
    workdir_key: str
    runner: str
    spec: dict[str, Any]


class SpectatorEngine:
    """Run allowlisted spectator scripts on any capable cluster pool."""

    def __init__(self, repo_root: Path, cfg: dict[str, Any], *, agent_cfg: dict[str, Any] | None = None) -> None:
        self.repo_root = repo_root.resolve()
        self.cfg = cfg
        self.agent_cfg = agent_cfg or {}
        self.engine_cfg = dict(cfg.get("spectator_engine") or {})
        self.allowlist = cfg.get("spectator_scripts") or {}
        self.pools = cfg.get("worker_pools") or {}
        self.dispatch_script = self._resolve_dispatch_script()
        self.local_staging = self.repo_root / str(self.engine_cfg.get("local_staging") or "data_lake/spectator_engine")
        self.molina_repo = self._resolve_molina_repo()

    def _resolve_molina_repo(self) -> Path:
        raw = str(self.engine_cfg.get("molina_repo") or "..").strip()
        path = Path(raw)
        if not path.is_absolute():
            path = (self.repo_root / path).resolve()
        return path

    def _resolve_dispatch_script(self) -> Path:
        raw = str(self.engine_cfg.get("dispatch_script") or "scripts/yzu_cluster/workers/scraper_dispatch.sh").strip()
        candidates = (
            self.repo_root / raw,
            self.repo_root / "drive" / raw,
            self.repo_root / "drive/scripts/yzu_cluster/workers/scraper_dispatch.sh",
            self.repo_root / "scripts/yzu_cluster/workers/scraper_dispatch.sh",
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return candidates[0]

    def resolve(self, plan: dict[str, Any]) -> ResolvedScript:
        script_key = str(plan.get("script_key") or "")
        script = str(plan.get("script") or "")
        args = [str(a) for a in plan.get("args", [])]
        spec: dict[str, Any] = {}
        if script_key:
            spec = dict(self.allowlist.get(script_key) or {})
            if not spec:
                raise ValueError(f"script_key not allowlisted: {script_key}")
            script = str(spec["script"])
            args = [str(a) for a in spec.get("args", [])] + args
        elif script and script in self.allowlist and isinstance(self.allowlist[script], dict):
            spec = dict(self.allowlist[script])
            script = str(spec.get("script", script))
            args = [str(a) for a in spec.get("args", [])] + args
        if not script:
            raise ValueError("scraper_run requires script or script_key")
        allowed_scripts = {row["script"] for row in self.allowlist.values() if isinstance(row, dict) and row.get("script")}
        if script not in allowed_scripts:
            raise ValueError(f"script not allowlisted: {script}")
        return ResolvedScript(
            script_key=script_key or script,
            script=script,
            args=args,
            workdir_key=str(spec.get("workdir") or "molina_repo"),
            runner=str(spec.get("runner") or "").strip().lower(),
            spec=spec,
        )

    def _windows_staging(self) -> tuple[str, str]:
        pool_cfg = (self.engine_cfg.get("pools") or {}).get("windows_lab") or {}
        sr_repo = str(pool_cfg.get("sharpe_repo") or r"C:\cw\Sharpe-Renaissance")
        staging = str(pool_cfg.get("staging") or rf"{sr_repo}\data_lake\spectator_engine")
        return sr_repo, staging

    def _apply_plan_url_args(
        self,
        resolved: ResolvedScript,
        plan: dict[str, Any],
        job_id: str,
        *,
        pool_id: str,
    ) -> ResolvedScript:
        """Inject --url/--out for generic_url_scrape from plan fields."""
        if resolved.script_key != "generic_url_scrape" and "generic_url_scrape" not in resolved.script:
            return resolved
        url = str(plan.get("url") or "").strip()
        if not url.startswith("http"):
            raise ValueError("generic_url_scrape requires plan.url (https://...)")
        mode = str(plan.get("scrape_mode") or "page")
        local_base = self.local_staging / "scrapes" / job_id
        local_base.mkdir(parents=True, exist_ok=True)
        if mode in {"catalog", "token"}:
            local_out = local_base
            out_path = str(local_out)
        else:
            local_out = local_base / "extract.json"
            out_path = str(local_out)
        pool = self.pools.get(pool_id) or {}
        kind = pool.get("kind", "")
        if pool_id == "optiplex" or kind == "local_linux":
            out_path_arg = out_path
        elif kind == "ssh_windows":
            _, staging = self._windows_staging()
            if mode in {"catalog", "token"}:
                win_out = f"{staging}\\scrapes\\{job_id}"
            else:
                win_out = f"{staging}\\scrapes\\{job_id}\\extract.json"
            out_path_arg = win_out
            if mode == "token":
                plan["pull_paths"] = [
                    {
                        "remote": win_out.replace("\\", "/"),
                        "local": repo_relpath(local_base, self.repo_root),
                        "recursive": True,
                    }
                ]
            else:
                plan["pull_paths"] = [
                    {
                        "remote": win_out.replace("\\", "/"),
                        "local": repo_relpath(local_out, self.repo_root),
                    }
                ]
        elif kind == "ssh_linux":
            pool_cfg = (self.engine_cfg.get("pools") or {}).get(pool_id) or {}
            sr_repo = str(pool_cfg.get("sharpe_repo") or self.repo_root)
            staging = str(pool_cfg.get("staging") or f"{sr_repo}/data_lake/spectator_engine")
            if mode in {"catalog", "token"}:
                remote_out = f"{staging}/scrapes/{job_id}"
            else:
                remote_out = f"{staging}/scrapes/{job_id}/extract.json"
            out_path_arg = remote_out
            if mode == "token":
                plan["pull_paths"] = [
                    {
                        "remote": remote_out,
                        "local": repo_relpath(local_base, self.repo_root),
                        "recursive": True,
                    }
                ]
            else:
                plan["pull_paths"] = [
                    {
                        "remote": remote_out,
                        "local": repo_relpath(local_out, self.repo_root),
                    }
                ]
        else:
            out_path_arg = out_path
        args = ["--url", url, "--mode", mode, "--out", out_path_arg]
        if mode == "catalog":
            if plan.get("catalog_max_pages") is not None:
                args.extend(["--max-pages", str(int(plan["catalog_max_pages"]))])
            if plan.get("catalog_max_tokens") is not None:
                args.extend(["--max-tokens", str(int(plan["catalog_max_tokens"]))])
            if plan.get("catalog_pause_ms") is not None:
                args.extend(["--pause-ms", str(int(plan["catalog_pause_ms"]))])
        return ResolvedScript(
            script_key=resolved.script_key,
            script=resolved.script,
            args=args,
            workdir_key=resolved.workdir_key,
            runner=resolved.runner,
            spec=resolved.spec,
        )

    def pool_order(self, plan: dict[str, Any]) -> list[str]:
        override = str(plan.get("pool") or "").strip()
        if override:
            return self._filter_pools([override])
        default_order = list(
            self.engine_cfg.get("pool_order_default") or self.engine_cfg.get("pool_order") or ["windows_lab"]
        )
        order = self._filter_pools(default_order)
        if disable_local_scrape(self.cfg):
            order = [
                pool_id
                for pool_id in order
                if pool_id != "optiplex" and (self.pools.get(pool_id) or {}).get("kind") != "local_linux"
            ]
        return order

    def _filter_pools(self, order: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for pool_id in order:
            if pool_id in seen or pool_id not in self.pools:
                continue
            pool = self.pools[pool_id]
            if pool.get("enabled") is False:
                continue
            seen.add(pool_id)
            out.append(pool_id)
        return out

    def probe_pool(self, pool_id: str) -> bool:
        pool = self.pools.get(pool_id) or {}
        kind = pool.get("kind", "")
        timeout = int(self.engine_cfg.get("probe_timeout_seconds") or 15)
        if pool_id == "optiplex" or kind == "local_linux":
            if disable_local_scrape(self.cfg):
                return False
            pool = self.pools.get(pool_id) or {}
            if pool.get("enabled") is False:
                return False
            return self._probe_local()
        if kind == "ssh_linux":
            key = pool.get("ssh_key") or self.agent_cfg.get("ssh_key", "")
            for target in spectator_targets(pool):
                run = ssh_run(target, "command -v node >/dev/null && test -d \"$HOME\" && echo OK", key=key, timeout=timeout)
                if run.returncode == 0 and "OK" in (run.stdout or ""):
                    return True
            return False
        if kind == "ssh_windows":
            from scripts.yzu_cluster.windows_lab_readiness import probe_windows_lab

            return bool(probe_windows_lab(self.cfg, self.agent_cfg).get("scraper_ready"))
        return False

    def _probe_local(self) -> bool:
        if not shutil.which("node"):
            return False
        if not self.molina_repo.exists():
            return False
        if not (self.molina_repo / "scripts").exists():
            return False
        if not (self.molina_repo / "node_modules/sqlite3").exists():
            return False
        return self.dispatch_script.exists()

    def run(self, job_id: str, plan: dict[str, Any], *, jobs_root: Path, event_cb: Any = None) -> dict[str, Any]:
        jobs_root = jobs_root.resolve()
        resolved = self.resolve(plan)
        log_path = jobs_root / job_id / "scraper.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        errors: list[str] = []
        for pool_id in self.pool_order(plan):
            if not self.probe_pool(pool_id):
                errors.append(f"{pool_id}: not capable")
                continue
            try:
                plan_attempt = dict(plan)
                pool_resolved = self._apply_plan_url_args(resolved, plan_attempt, job_id, pool_id=pool_id)
                result = self._run_on_pool(pool_id, pool_resolved, plan_attempt, log_path)
                result["pool"] = pool_id
                result["script_key"] = resolved.script_key
                if resolved.script_key == "generic_url_scrape":
                    scrape_dir = self.local_staging / "scrapes" / job_id
                    manifest = scrape_dir / "manifest.json"
                    scrape_out = scrape_dir / "extract.json"
                    if manifest.exists():
                        result["extract_path"] = repo_relpath(manifest, self.repo_root)
                        result["catalog_dir"] = repo_relpath(scrape_dir, self.repo_root)
                    elif scrape_out.exists():
                        result["extract_path"] = repo_relpath(scrape_out, self.repo_root)
                    result["url"] = plan.get("url")
                return result
            except Exception as exc:
                errors.append(f"{pool_id}: {exc}")
                if event_cb:
                    event_cb(job_id, "warn", f"scraper pool {pool_id} failed: {exc}")
        raise RuntimeError("spectator scraper failed on all pools: " + "; ".join(errors))

    def _run_on_pool(
        self,
        pool_id: str,
        resolved: ResolvedScript,
        plan: dict[str, Any],
        log_path: Path,
    ) -> dict[str, Any]:
        pool = self.pools.get(pool_id) or {}
        kind = pool.get("kind", "")
        timeout = int(plan.get("timeout_seconds") or self.engine_cfg.get("default_timeout_seconds") or 3600)
        if pool_id == "optiplex" or kind == "local_linux":
            if pool.get("enabled") is False:
                raise RuntimeError(f"pool {pool_id} is disabled (cluster_only)")
            return self._run_local(resolved, log_path, timeout=timeout)
        if kind == "ssh_linux":
            return self._run_ssh_linux(pool, resolved, plan, log_path, timeout=timeout)
        if kind == "ssh_windows":
            return self._run_ssh_windows(pool, resolved, plan, log_path, timeout=timeout)
        raise ValueError(f"unsupported pool kind for scraper: {pool_id}")

    def _env_base(self) -> dict[str, str]:
        env = os.environ.copy()
        env["SR_REPO_ROOT"] = str(self.repo_root)
        env["MOLINA_REPO"] = str(self.molina_repo)
        env["SPECTATOR_STAGING"] = str(self.local_staging)
        env["DISPATCH_LOG"] = ""
        return env

    def _run_local(self, resolved: ResolvedScript, log_path: Path, *, timeout: int) -> dict[str, Any]:
        self.local_staging.mkdir(parents=True, exist_ok=True)
        env = self._env_base()
        env["DISPATCH_LOG"] = str(log_path)
        cmd = ["bash", str(self.dispatch_script), resolved.script, "--", *resolved.args]
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"pool=optiplex local\n{' '.join(cmd)}\n\n")
            process = subprocess.run(
                cmd,
                cwd=self.repo_root,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
        if process.returncode:
            raise RuntimeError(f"local scraper exited {process.returncode}")
        return {
            "target": "local",
            "script": resolved.script,
            "args": resolved.args,
            "log": repo_relpath(log_path, self.repo_root),
            "staging": repo_relpath(self.local_staging, self.repo_root),
        }

    def _remote_dispatch_cmd(self, resolved: ResolvedScript, *, sr_repo: str, molina_repo: str, staging: str) -> str:
        quoted_args = " ".join(resolved.args)
        dispatch = f"{sr_repo}/scripts/yzu_cluster/workers/scraper_dispatch.sh"
        return (
            f"export SR_REPO_ROOT='{sr_repo}' MOLINA_REPO='{molina_repo}' SPECTATOR_STAGING='{staging}'; "
            f"bash '{dispatch}' '{resolved.script}' -- {quoted_args}"
        ).strip()

    def _pull_staging(self, target: str, plan: dict[str, Any], *, key: str) -> list[str]:
        pulled: list[str] = []
        for item in plan.get("pull_paths", []):
            remote = item["remote"]
            local = self.repo_root / item["local"]
            if item.get("recursive"):
                scp_pull_recursive(target, remote, local, key=key, timeout=600)
                pulled.append(repo_relpath(local, self.repo_root))
            else:
                scp_pull(target, remote, local, key=key, timeout=300)
                pulled.append(repo_relpath(local, self.repo_root))
        return pulled

    def _run_ssh_linux(
        self,
        pool: dict[str, Any],
        resolved: ResolvedScript,
        plan: dict[str, Any],
        log_path: Path,
        *,
        timeout: int,
    ) -> dict[str, Any]:
        key = pool.get("ssh_key") or self.agent_cfg.get("ssh_key", "")
        pool_cfg = (self.engine_cfg.get("pools") or {}).get("spectator") or {}
        if pool.get("host") or pool.get("tailscale_ip"):
            pool_cfg = (self.engine_cfg.get("pools") or {}).get("spectator") or pool_cfg
        sr_repo = str(pool.get("sharpe_repo") or pool_cfg.get("sharpe_repo") or self.repo_root)
        molina_repo = str(pool.get("molina_repo") or pool_cfg.get("molina_repo") or self.molina_repo)
        staging = str(pool.get("staging") or pool_cfg.get("staging") or f"{sr_repo}/data_lake/spectator_engine")
        remote_cmd = self._remote_dispatch_cmd(resolved, sr_repo=sr_repo, molina_repo=molina_repo, staging=staging)
        last_error = ""
        for target in spectator_targets(pool):
            with log_path.open("w", encoding="utf-8") as log:
                log.write(f"target={target}\n{remote_cmd}\n\n")
                run = ssh_run(target, remote_cmd, key=key, timeout=timeout)
                log.write(run.stdout or "")
                log.write(run.stderr or "")
            if run.returncode == 0:
                pulled = self._pull_staging(target, plan, key=key)
                return {
                    "target": target,
                    "script": resolved.script,
                    "args": resolved.args,
                    "log": repo_relpath(log_path, self.repo_root),
                    "pulled": pulled,
                }
            last_error = (run.stderr or run.stdout or f"exit {run.returncode}").strip()
        raise RuntimeError(last_error or "ssh linux scraper failed")

    def _run_ssh_windows(
        self,
        pool: dict[str, Any],
        resolved: ResolvedScript,
        plan: dict[str, Any],
        log_path: Path,
        *,
        timeout: int,
    ) -> dict[str, Any]:
        key = pool.get("ssh_key") or self.agent_cfg.get("ssh_key", "")
        pool_cfg = (self.engine_cfg.get("pools") or {}).get("windows_lab") or {}
        molina_repo = pool_cfg.get("molina_repo") or pool.get("molina_repo") or r"C:\cw\Molina-Optiplex"
        sr_repo = pool_cfg.get("sharpe_repo") or pool.get("sharpe_repo") or r"C:\cw\Sharpe-Renaissance"
        staging = pool_cfg.get("staging") or rf"{sr_repo}\data_lake\spectator_engine"
        quoted_args = " ".join(f"'{arg.replace(chr(39), chr(39) * 2)}'" for arg in resolved.args)
        etherscan = any("etherscan.io" in str(arg) for arg in resolved.args)
        pw_env = ""
        if etherscan:
            pw_env = "$env:PLAYWRIGHT_CHANNEL='chrome'; $env:PLAYWRIGHT_HEADLESS='false'; "
        if resolved.script.endswith(".mjs") or resolved.script.endswith(".js"):
            if resolved.script.startswith("yzu_cluster/"):
                rel = "scripts\\" + resolved.script.replace("/", "\\")
                inner = f"cd '{sr_repo}'; $env:SPECTATOR_STAGING='{staging}'; {pw_env}node '{rel}' {quoted_args}"
            else:
                inner = f"cd '{molina_repo}'; $env:NODE_PATH='{molina_repo}\\node_modules'; node scripts\\{resolved.script} {quoted_args}"
        elif resolved.script.startswith("ops"):
            inner = f"cd '{molina_repo}'; bash {resolved.script} {quoted_args}"
        else:
            inner = f"cd '{molina_repo}'; bash scripts\\{resolved.script} {quoted_args}"
        ps = f"powershell.exe -NoProfile -Command \"{inner}\""
        workers = windows_workers(pool.get("inventory", ""), joined_only=True)
        if not workers:
            raise RuntimeError("no joined windows workers for scraper_run")
        last_error = ""
        for worker in workers:
            target = windows_target(worker, default_user=pool.get("default_user", "user"))
            with log_path.open("w", encoding="utf-8") as log:
                log.write(f"target={target}\n{ps}\n\n")
                run = ssh_run(target, ps, key=key, timeout=timeout)
                log.write(run.stdout or "")
                log.write(run.stderr or "")
            if run.returncode == 0:
                pulled = self._pull_staging(target, plan, key=key)
                return {
                    "target": target,
                    "script": resolved.script,
                    "args": resolved.args,
                    "log": repo_relpath(log_path, self.repo_root),
                    "pulled": pulled,
                }
            last_error = (run.stderr or run.stdout or f"exit {run.returncode}").strip()
        raise RuntimeError(last_error or "windows scraper failed")
