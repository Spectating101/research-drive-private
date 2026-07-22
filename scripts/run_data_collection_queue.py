#!/usr/bin/env python3
"""Run the explicitly enabled, credential-free collection queue.

The private runtime is a split checkout.  Queue definitions are shared through
``config/`` symlinks, while this entrypoint lives at the repository root so
controller and worker execution use the same relative paths.
"""

from __future__ import annotations

import argparse
import json
import os
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
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_latest(row: dict[str, Any]) -> None:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    (STATUS_DIR / "latest.json").write_text(
        json.dumps(row, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def acquire_lock(lock_path: Path) -> None:
    if lock_path.exists():
        try:
            old = json.loads(lock_path.read_text(encoding="utf-8"))
            pid = int(old.get("pid", 0))
        except Exception:
            pid = 0
        if pid and pid_alive(pid):
            raise SystemExit(f"Queue already running with pid {pid}: {lock_path}")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps({"pid": os.getpid(), "started_at": utc_now()}, indent=2) + "\n",
        encoding="utf-8",
    )


def release_lock(lock_path: Path) -> None:
    try:
        if lock_path.exists():
            old = json.loads(lock_path.read_text(encoding="utf-8"))
            if int(old.get("pid", 0)) == os.getpid():
                lock_path.unlink()
    except Exception:
        pass


def resolve_command(command: list[str], repo: Path = REPO) -> list[str]:
    """Resolve legacy interpreter paths without hiding missing task scripts."""
    resolved = [str(part) for part in command]
    if resolved and resolved[0] in {".venv/bin/python", ".venv/bin/python3"}:
        if not (repo / resolved[0]).exists():
            resolved[0] = sys.executable
    return resolved


def missing_script_args(command: list[str], repo: Path = REPO) -> list[str]:
    """Return missing relative script arguments before spawning a subprocess."""
    missing: list[str] = []
    for arg in command[1:]:
        path = Path(arg)
        if path.suffix.lower() not in {".py", ".sh", ".ps1", ".cmd"} or path.is_absolute():
            continue
        if not (repo / path).exists():
            missing.append(arg)
    return missing


def task_selected(task: dict[str, Any], only: set[str]) -> bool:
    if only and str(task.get("id")) not in only:
        return False
    if not bool(task.get("enabled", False)):
        return False
    if bool(task.get("credential_required", False)):
        return False
    return bool(task.get("command"))


def run_task(task: dict[str, Any], run_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    task_id = str(task["id"])
    command = resolve_command([str(part) for part in task["command"]])
    log_path = LOG_DIR / f"{run_id}_{task_id}.log"
    status_path = STATUS_DIR / "status.jsonl"
    start_row = {
        "ts": utc_now(),
        "run_id": run_id,
        "task_id": task_id,
        "status": "started",
        "title": task.get("title", ""),
        "command": command,
        "log_path": str(log_path.relative_to(REPO)),
        "output_hint": task.get("output_hint", ""),
    }
    append_jsonl(status_path, start_row)
    write_latest(start_row)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    missing = missing_script_args(command)
    if missing:
        result = dict(start_row)
        result.update({
            "ts": utc_now(),
            "status": "failed",
            "returncode": 2,
            "error": f"missing task script(s): {', '.join(missing)}",
        })
        append_jsonl(status_path, result)
        write_latest(result)
        return result

    if dry_run:
        result = dict(start_row)
        result.update({"ts": utc_now(), "status": "dry_run", "duration_seconds": 0, "returncode": 0})
        append_jsonl(status_path, result)
        write_latest(result)
        return result

    start = time.time()
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    try:
        with log_path.open("ab") as log:
            log.write((json.dumps(start_row, ensure_ascii=False) + "\n").encode("utf-8"))
            log.flush()
            process = subprocess.run(command, cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
        result = {
            "ts": utc_now(),
            "run_id": run_id,
            "task_id": task_id,
            "status": "ok" if process.returncode == 0 else "failed",
            "returncode": int(process.returncode),
            "duration_seconds": round(time.time() - start, 3),
            "title": task.get("title", ""),
            "log_path": str(log_path.relative_to(REPO)),
            "output_hint": task.get("output_hint", ""),
        }
    except OSError as exc:
        result = dict(start_row)
        result.update({"ts": utc_now(), "status": "failed", "returncode": 2, "error": str(exc)})
    append_jsonl(status_path, result)
    write_latest(result)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    ap.add_argument("--only", default="", help="Comma-separated task ids to run.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    queue_path = args.queue if args.queue.is_absolute() else REPO / args.queue
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    tasks = sorted(queue.get("tasks", []), key=lambda item: int(item.get("priority", 9999)))
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
