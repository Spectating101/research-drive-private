#!/usr/bin/env python3
"""Run the local Sharpe data collection queue.

The queue is intentionally conservative: only tasks that are explicitly enabled
and do not require credentials are executed. Paid/lab tasks remain cataloged but
blocked until the user handles access.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE = REPO / "config/data_collection_queue.json"
STATUS_DIR = REPO / "data_lake/data_collection_queue"
LOG_DIR = REPO / "logs/data_collection_queue"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_latest(row: dict[str, Any]) -> None:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    (STATUS_DIR / "latest.json").write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def acquire_lock(lock_path: Path) -> None:
    if lock_path.exists():
        try:
            old = json.loads(lock_path.read_text())
            pid = int(old.get("pid", 0))
        except Exception:
            pid = 0
        if pid and pid_alive(pid):
            raise SystemExit(f"Queue already running with pid {pid}: {lock_path}")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps({"pid": os.getpid(), "started_at": utc_now()}, indent=2) + "\n", encoding="utf-8")


def release_lock(lock_path: Path) -> None:
    try:
        if lock_path.exists():
            old = json.loads(lock_path.read_text())
            if int(old.get("pid", 0)) == os.getpid():
                lock_path.unlink()
    except Exception:
        pass


def task_selected(task: dict[str, Any], only: set[str]) -> bool:
    if only and str(task.get("id")) not in only:
        return False
    if not bool(task.get("enabled", False)):
        return False
    if bool(task.get("credential_required", False)):
        return False
    return bool(task.get("command"))


def memory_limiter(task: dict[str, Any]):
    """Cap a task's address space so one runaway job can't take the box down.

    crsp_moveit_ingest read a 9.6 GiB zip member into a single allocation and
    peaked at ~21 GB on a 31 GB machine; the OOM killer chose GNOME Shell and
    the desktop died instead of the batch job. A ceiling here bounds every task,
    including bugs not yet found -- the task dies with MemoryError and the queue
    records `failed` while the rest of the run continues.

    Per-task override: "memory_limit_gb" in the queue entry. 0 disables.
    """
    try:
        import resource
    except ImportError:  # non-POSIX
        return None

    limit_gb = float(task.get("memory_limit_gb", os.environ.get("QUEUE_TASK_MEMORY_GB", 8)))
    if limit_gb <= 0:
        return None
    limit = int(limit_gb * 1024**3)

    def _apply() -> None:
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        # Make the batch job, not the desktop, the kernel's preferred victim.
        try:
            with open("/proc/self/oom_score_adj", "w") as fh:
                fh.write("500")
        except OSError:
            pass

    return _apply


def resolve_command(command: list[str]) -> tuple[list[str], Path]:
    """Return (command, cwd) pointing at paths that actually exist.

    This queue predates the drive/ split: 12 of its task scripts still live only
    in the parent repo, and most entries call `.venv/bin/python`, which exists
    only there too. Running them with cwd=REPO meant the interpreter or the
    script was missing, and the resulting FileNotFoundError propagated out of
    run_task and killed the whole queue on its first task -- 23 consecutive runs
    recorded a start and nothing else.

    Each task is anchored to whichever repo root actually contains its script, so
    the script's own relative paths resolve the way its author intended.
    """
    if not command:
        return command, REPO

    script = next((c for c in command[1:] if c.endswith((".py", ".sh"))), None)
    base = REPO
    if script and not (REPO / script).exists() and (REPO.parent / script).exists():
        base = REPO.parent

    exe = command[0]
    if not Path(exe).is_absolute() and "/" in exe and not (base / exe).exists():
        for candidate in (REPO.parent / exe, REPO / exe, Path(sys.executable)):
            if candidate.exists():
                return [str(candidate), *command[1:]], base
    return command, base


def run_task(task: dict[str, Any], run_id: str, dry_run: bool = False) -> dict[str, Any]:
    task_id = str(task["id"])
    command, cwd = resolve_command([str(part) for part in task["command"]])
    log_path = LOG_DIR / f"{run_id}_{task_id}.log"
    status_path = STATUS_DIR / "status.jsonl"
    start = time.time()
    start_row = {
        "ts": utc_now(),
        "run_id": run_id,
        "task_id": task_id,
        "status": "started",
        "title": task.get("title", ""),
        "command": command,
        "cwd": str(cwd),
        "log_path": str(log_path.relative_to(REPO)),
        "output_hint": task.get("output_hint", ""),
    }
    append_jsonl(status_path, start_row)
    write_latest(start_row)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if dry_run:
        row = dict(start_row)
        row.update({"ts": utc_now(), "status": "dry_run", "duration_seconds": 0, "returncode": 0})
        append_jsonl(status_path, row)
        write_latest(row)
        return row

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    # Task scripts import sibling packages as `scripts.<pkg>`, which only
    # resolves when their repo root is importable.
    env["PYTHONPATH"] = os.pathsep.join(
        x for x in (str(cwd), str(REPO), env.get("PYTHONPATH", "")) if x
    )
    launch_error = None
    returncode = 1
    with log_path.open("ab") as log:
        log.write((json.dumps(start_row, ensure_ascii=False) + "\n").encode("utf-8"))
        log.flush()
        try:
            proc = subprocess.run(
                command, cwd=cwd, env=env, stdout=log,
                stderr=subprocess.STDOUT, preexec_fn=memory_limiter(task),
            )
            returncode = int(proc.returncode)
        except (OSError, ValueError) as exc:
            # A task that cannot even be launched must not take the queue down
            # with it -- record the failure and let the remaining tasks run.
            launch_error = f"{type(exc).__name__}: {exc}"
            returncode = 127
            log.write((json.dumps({"launch_error": launch_error}) + "\n").encode("utf-8"))
    duration = round(time.time() - start, 3)
    final = {
        "ts": utc_now(),
        "run_id": run_id,
        "task_id": task_id,
        "status": "ok" if returncode == 0 else "failed",
        "returncode": returncode,
        "duration_seconds": duration,
        "title": task.get("title", ""),
        "log_path": str(log_path.relative_to(REPO)),
        "output_hint": task.get("output_hint", ""),
    }
    if launch_error:
        final["launch_error"] = launch_error
    append_jsonl(status_path, final)
    write_latest(final)
    return final


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    ap.add_argument("--only", default="", help="Comma-separated task ids to run.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--continue-on-error", action="store_true", default=True)
    args = ap.parse_args()

    queue_path = args.queue if args.queue.is_absolute() else (REPO / args.queue)
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    tasks = sorted(queue.get("tasks", []), key=lambda t: int(t.get("priority", 9999)))
    only = {item.strip() for item in args.only.split(",") if item.strip()}
    selected = [task for task in tasks if task_selected(task, only)]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = STATUS_DIR / "queue.lock"
    acquire_lock(lock_path)

    summary = {
        "ts": utc_now(),
        "run_id": run_id,
        "status": "queue_started",
        "queue": str(queue_path.relative_to(REPO)),
        "selected_task_ids": [task["id"] for task in selected],
        "skipped_task_ids": [task.get("id") for task in tasks if task not in selected],
    }
    append_jsonl(STATUS_DIR / "status.jsonl", summary)
    write_latest(summary)
    exit_code = 0
    try:
        for task in selected:
            result = run_task(task, run_id, dry_run=bool(args.dry_run))
            if result["status"] == "failed":
                exit_code = int(result.get("returncode", 1)) or 1
                if not args.continue_on_error:
                    break
        final = {
            "ts": utc_now(),
            "run_id": run_id,
            "status": "queue_finished" if exit_code == 0 else "queue_finished_with_errors",
            "exit_code": exit_code,
        }
        append_jsonl(STATUS_DIR / "status.jsonl", final)
        write_latest(final)
    finally:
        release_lock(lock_path)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
