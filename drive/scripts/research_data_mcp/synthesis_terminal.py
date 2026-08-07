#!/usr/bin/env python3
"""Bounded Synthesis Ask terminal — allowlisted inspect helpers only (no free shell)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

THREAD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MAX_SAMPLE_ROWS = 20
MAX_COLUMNS = 48

TERMINAL_COMMANDS: dict[str, dict[str, str]] = {
    "list_commands": {
        "summary": "Catalog of allowlisted Synthesis terminal commands.",
        "when_to_use": "When unsure which inspect command to run.",
    },
    "thread_artifacts": {
        "summary": "List files under this thread's synthesis output directory.",
        "when_to_use": "Before sampling — confirm a job wrote parquet/manifest bytes.",
    },
    "output_schema": {
        "summary": "Columns, dtypes, and row count for the latest thread output parquet.",
        "when_to_use": "Before claiming which derived columns exist.",
    },
    "output_sample": {
        "summary": "Head/tail sample of thread output rows (capped).",
        "when_to_use": "When the researcher asks to inspect values (e.g. acceleration_ppm).",
    },
    "input_schema": {
        "summary": "Schema for the accepted execution_spec input dataset.",
        "when_to_use": "When checking upstream columns before proposing transforms.",
    },
    "verify_spec_columns": {
        "summary": "Compare accepted transform aliases to output parquet columns.",
        "when_to_use": "Before claiming the built panel matches the accepted method.",
    },
}


def list_terminal_commands() -> dict[str, Any]:
    return {
        "commands": [
            {
                "command": key,
                "summary": meta["summary"],
                "when_to_use": meta["when_to_use"],
            }
            for key, meta in TERMINAL_COMMANDS.items()
        ],
        "note": "Allowlisted inspect helpers only — no free shell, SSH, or arbitrary argv.",
    }


def _safe_thread_id(thread_id: str) -> str:
    value = str(thread_id or "").strip()
    if not THREAD_ID_RE.fullmatch(value):
        raise ValueError("thread_id must be a short alphanumeric synthesis thread id")
    return value


def _thread_output_root(repo_root: Path, thread_id: str) -> Path:
    root = (Path(repo_root).resolve() / "data_lake/synthesis/thread_outputs" / thread_id).resolve()
    base = (Path(repo_root).resolve() / "data_lake/synthesis/thread_outputs").resolve()
    if root != base and base not in root.parents:
        raise ValueError("thread output path escaped allowlisted root")
    return root


def _latest_output_parquet(repo_root: Path, thread_id: str, *, job_id: str = "") -> Path | None:
    root = _thread_output_root(repo_root, thread_id)
    if not root.is_dir():
        return None
    if job_id:
        candidate = (root / str(job_id).strip() / "output.parquet").resolve()
        if root not in candidate.parents:
            raise ValueError("job output path escaped thread root")
        return candidate if candidate.is_file() else None
    matches = sorted(root.glob("*/output.parquet"), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _load_thread_state(gateway: Any, thread_id: str) -> dict[str, Any]:
    thread = gateway.synthesis_thread_get(thread_id)
    if not isinstance(thread, dict):
        raise ValueError(f"synthesis thread not found: {thread_id}")
    return thread


def _read_parquet_meta(path: Path) -> dict[str, Any]:
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    schema = table.schema
    return {
        "path": str(path),
        "rows": int(table.num_rows),
        "columns": list(schema.names),
        "dtypes": {field.name: str(field.type) for field in schema},
        "bytes": path.stat().st_size,
    }


def _sample_parquet(
    path: Path,
    *,
    limit: int = 5,
    tail: bool = False,
    columns: list[str] | None = None,
) -> dict[str, Any]:
    import pyarrow.parquet as pq

    n = max(1, min(int(limit or 5), MAX_SAMPLE_ROWS))
    table = pq.read_table(path)
    names = list(table.column_names)
    selected = names
    if columns:
        wanted = [str(c).strip() for c in columns if str(c).strip()][:MAX_COLUMNS]
        missing = [c for c in wanted if c not in names]
        if missing:
            return {
                "ok": False,
                "error": f"columns not in output: {missing}",
                "available_columns": names[:MAX_COLUMNS],
            }
        selected = wanted
        table = table.select(selected)
    if tail:
        start = max(0, table.num_rows - n)
        table = table.slice(start, n)
    else:
        table = table.slice(0, min(n, table.num_rows))
    rows = table.to_pylist()
    return {
        "ok": True,
        "path": str(path),
        "total_rows": int(pq.ParquetFile(path).metadata.num_rows),
        "returned_rows": len(rows),
        "tail": bool(tail),
        "columns": selected,
        "rows": rows,
    }


def _expected_transform_aliases(execution_spec: dict[str, Any] | None) -> list[str]:
    aliases: list[str] = []
    for step in (execution_spec or {}).get("transforms") or []:
        if not isinstance(step, dict):
            continue
        alias = str(step.get("as") or "").strip()
        if alias:
            aliases.append(alias)
        if str(step.get("op") or "") == "select":
            for col in step.get("columns") or []:
                name = str(col or "").strip()
                if name and name not in aliases:
                    aliases.append(name)
    return aliases


def _input_schema(repo_root: Path, dataset_id: str) -> dict[str, Any]:
    from scripts.research_data_mcp.synthesis_executor import _ensure_local_file, _load_registry, _registry_row

    dataset_id = str(dataset_id or "").strip()
    if not dataset_id:
        raise ValueError("execution_spec has no input_dataset_id")
    registry = _load_registry(repo_root)
    row = _registry_row(registry, dataset_id)
    path = _ensure_local_file(repo_root, row)
    if path.suffix.lower() == ".parquet":
        meta = _read_parquet_meta(path)
    else:
        # CSV/JSON: best-effort column peek via pandas/pyarrow when available
        try:
            import pyarrow.csv as pac

            table = pac.read_csv(path)
            meta = {
                "path": str(path),
                "rows": int(table.num_rows),
                "columns": list(table.column_names),
                "dtypes": {name: str(table.schema.field(name).type) for name in table.column_names},
                "bytes": path.stat().st_size,
            }
        except Exception as exc:  # noqa: BLE001 — honest inspect failure
            return {
                "ok": False,
                "dataset_id": dataset_id,
                "path": str(path),
                "error": f"could not read input schema: {exc}",
            }
    return {"ok": True, "dataset_id": dataset_id, **meta}


def run_terminal_command(
    gateway: Any,
    *,
    thread_id: str,
    command: str,
    limit: int = 5,
    tail: bool = False,
    columns: list[str] | None = None,
    job_id: str = "",
) -> dict[str, Any]:
    """Execute one allowlisted Synthesis terminal command."""
    tid = _safe_thread_id(thread_id)
    cmd = str(command or "").strip()
    if cmd not in TERMINAL_COMMANDS:
        return {
            "ok": False,
            "error": f"command not allowlisted: {cmd or 'empty'}",
            "allowed": sorted(TERMINAL_COMMANDS),
        }
    if cmd == "list_commands":
        return {"ok": True, **list_terminal_commands()}

    repo_root = Path(gateway.repo_root).resolve()
    thread = _load_thread_state(gateway, tid)
    state = thread.get("state") if isinstance(thread.get("state"), dict) else {}
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    execution_spec = state.get("execution_spec") if isinstance(state.get("execution_spec"), dict) else {}
    resolved_job = str(job_id or execution.get("job_id") or "").strip()

    if cmd == "thread_artifacts":
        root = _thread_output_root(repo_root, tid)
        files: list[dict[str, Any]] = []
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(repo_root)
                files.append(
                    {
                        "path": str(rel),
                        "bytes": path.stat().st_size,
                        "name": path.name,
                    }
                )
        return {
            "ok": True,
            "thread_id": tid,
            "root": str(root.relative_to(repo_root)) if root.exists() else str(root),
            "file_count": len(files),
            "files": files[:200],
            "execution_job_id": resolved_job or None,
        }

    if cmd in {"output_schema", "output_sample", "verify_spec_columns"}:
        parquet = _latest_output_parquet(repo_root, tid, job_id=resolved_job)
        if parquet is None or not parquet.is_file():
            return {
                "ok": False,
                "thread_id": tid,
                "error": "no output.parquet found for this thread",
                "job_id": resolved_job or None,
            }
        rel = str(parquet.relative_to(repo_root))

    if cmd == "output_schema":
        meta = _read_parquet_meta(parquet)
        meta["path"] = rel
        return {"ok": True, "thread_id": tid, "job_id": resolved_job or parquet.parent.name, **meta}

    if cmd == "output_sample":
        sample = _sample_parquet(parquet, limit=limit, tail=tail, columns=columns)
        if not sample.get("ok"):
            return {"thread_id": tid, **sample}
        sample["path"] = rel
        sample["thread_id"] = tid
        sample["job_id"] = resolved_job or parquet.parent.name
        return sample

    if cmd == "input_schema":
        try:
            result = _input_schema(repo_root, str(execution_spec.get("input_dataset_id") or ""))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "thread_id": tid, "error": str(exc)}
        result["thread_id"] = tid
        if result.get("path"):
            try:
                result["path"] = str(Path(result["path"]).resolve().relative_to(repo_root))
            except ValueError:
                pass
        return result

    if cmd == "verify_spec_columns":
        meta = _read_parquet_meta(parquet)
        expected = _expected_transform_aliases(execution_spec)
        present = set(meta["columns"])
        missing = [c for c in expected if c not in present]
        extra_hint = [
            c
            for c in meta["columns"]
            if c.endswith("_ppm") or "rate" in c or "accel" in c
        ]
        return {
            "ok": not missing,
            "thread_id": tid,
            "job_id": resolved_job or parquet.parent.name,
            "path": rel,
            "expected_aliases": expected,
            "missing_aliases": missing,
            "output_columns": meta["columns"],
            "derived_column_hint": extra_hint,
            "rows": meta["rows"],
            "execution_spec_output_id": execution_spec.get("output_dataset_id"),
        }

    return {"ok": False, "error": f"unhandled command: {cmd}"}
