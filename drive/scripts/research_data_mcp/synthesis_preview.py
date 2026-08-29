"""Bounded, non-materialising preview for accepted Synthesis execution specs.

Preview deliberately reuses the production executor's validation, transform, join,
and aggregation semantics. It differs from Build in only three ways:

* the primary input is deterministically capped before pandas can load it in full;
* no output files, manifests, jobs, registry rows, or Drive artifacts are written;
* the result is a compact receipt intended to be persisted on the Synthesis thread.

A preview therefore answers "what does this accepted recipe do on bounded bytes?"
It is not evidence that a full build has completed and it is not a statistical
claim about the full population.

A successful receipt is bound to BOTH the normalized execution spec and the
resolved input revisions. A method that has not changed can still require a new
preview when its underlying Library bytes have changed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_INPUT_ROW_LIMIT = 5_000
MAX_INPUT_ROW_LIMIT = 25_000
DEFAULT_OUTPUT_ROW_LIMIT = 20
MAX_OUTPUT_ROW_LIMIT = 100
# Right-hand join inputs are intentionally read with production join semantics.
# Keep that full-side read finite and substantially below the 512 MiB Build cap.
MAX_PREVIEW_JOIN_INPUT_BYTES = 64 * 1024 * 1024

_REVISION_FIELDS = (
    "manifest_id",
    "registration_id",
    "revision",
    "version",
    "checksum",
    "sha256",
    "content_hash",
    "etag",
    "updated_at",
    "registered_at",
    "default_run_id",
    "local_path",
    "local_root",
    "local_file",
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def execution_spec_hash(spec: dict[str, Any]) -> str:
    return _stable_hash(spec)


def execution_input_dataset_ids(spec: dict[str, Any]) -> list[str]:
    ids: list[str] = []

    def add(raw: Any) -> None:
        value = str(raw or "").strip()
        if value and value not in ids:
            ids.append(value)

    add(spec.get("input_dataset_id"))
    for step in spec.get("transforms") or []:
        if isinstance(step, dict):
            add(step.get("right_dataset_id"))
    return ids


def input_revision_snapshot(repo_root: Path, execution_spec: dict[str, Any]) -> list[dict[str, Any]]:
    from scripts.research_data_mcp.synthesis.dataset_paths import resolve_dataset_file
    from scripts.research_data_mcp.synthesis_executor import _load_registry, _registry_row, validate_execution_spec

    root = Path(repo_root).resolve()
    spec = validate_execution_spec(dict(execution_spec or {}))
    registry = _load_registry(root)
    snapshots: list[dict[str, Any]] = []

    for dataset_id in execution_input_dataset_ids(spec):
        source = _registry_row(registry, dataset_id)
        path, reason = resolve_dataset_file(root, source)
        if path is None:
            raise ValueError(
                f"preview input revision cannot be resolved for {dataset_id}: {reason or 'bytes unavailable'}"
            )
        stat = path.stat()
        declared = {
            key: source.get(key)
            for key in _REVISION_FIELDS
            if source.get(key) not in (None, "", [], {})
        }
        snapshots.append(
            {
                "dataset_id": dataset_id,
                "declared": declared,
                "resolved_path": str(path.resolve()),
                "size_bytes": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
            }
        )
    return snapshots


def preview_authority_hash(spec_hash: str, input_revisions: list[dict[str, Any]]) -> str:
    return _stable_hash({"spec_hash": str(spec_hash or ""), "input_revisions": input_revisions})


def current_preview_authority(repo_root: Path, execution_spec: dict[str, Any]) -> dict[str, Any]:
    from scripts.research_data_mcp.synthesis_executor import validate_execution_spec

    spec = validate_execution_spec(dict(execution_spec or {}))
    spec_hash = execution_spec_hash(spec)
    revisions = input_revision_snapshot(repo_root, spec)
    return {
        "execution_spec": spec,
        "spec_hash": spec_hash,
        "input_revisions": revisions,
        "authority_hash": preview_authority_hash(spec_hash, revisions),
    }


def _bounded_primary_frame(path: Path, limit: int):
    from scripts.research_data_mcp.synthesis.bounded_read import read_bounded_frame

    return read_bounded_frame(path, limit)


def _aggregate_preview(frame, spec: dict[str, Any]):
    from scripts.research_data_mcp.synthesis_executor import MAX_OUTPUT_ROWS

    needed = set(spec["group_by"])
    needed.update(
        str(metric.get("column") or "")
        for metric in spec["metrics"]
        if metric.get("column")
    )
    missing = sorted(column for column in needed if column and column not in frame.columns)
    if missing:
        raise ValueError(f"preview input is missing columns: {', '.join(missing)}")

    grouped = frame.groupby(spec["group_by"], dropna=False) if spec["group_by"] else frame.groupby(lambda _x: 0)
    output = None
    for metric in spec["metrics"]:
        fn = metric["function"]
        column = metric.get("column")
        alias = metric["as"]
        if fn == "count":
            series = grouped.size()
        elif fn == "quantile":
            series = grouped[column].quantile(float(metric["q"]))
        else:
            series = getattr(grouped[column], fn)()
        series = series.rename(alias)
        output = series.to_frame() if output is None else output.join(series)
    output = output.reset_index(drop=not bool(spec["group_by"]))
    if len(output) > MAX_OUTPUT_ROWS:
        raise ValueError("preview output exceeds the 1,000,000-row safety limit")
    return output


def _json_records(frame, limit: int) -> list[dict[str, Any]]:
    if frame is None or len(frame) == 0:
        return []
    text = frame.head(limit).to_json(
        orient="records", date_format="iso", date_unit="ms", default_handler=str
    )
    return json.loads(text)


def run_bounded_preview(
    repo_root: Path,
    execution_spec: dict[str, Any],
    *,
    input_row_limit: int = DEFAULT_INPUT_ROW_LIMIT,
    output_row_limit: int = DEFAULT_OUTPUT_ROW_LIMIT,
) -> dict[str, Any]:
    """Execute an accepted recipe on bounded primary rows; perform no durable writes."""
    from scripts.research_data_mcp.synthesis_executor import (
        _apply_transforms,
        _ensure_local_file,
        _load_registry,
        _registry_row,
        preflight_execution_spec,
    )

    root = Path(repo_root).resolve()
    in_limit = min(max(int(input_row_limit or DEFAULT_INPUT_ROW_LIMIT), 10), MAX_INPUT_ROW_LIMIT)
    out_limit = min(max(int(output_row_limit or DEFAULT_OUTPUT_ROW_LIMIT), 1), MAX_OUTPUT_ROW_LIMIT)

    preflight = preflight_execution_spec(root, dict(execution_spec or {}), row_cap=in_limit)
    if not preflight.get("ok"):
        issues = preflight.get("issues") or []
        detail = "; ".join(
            str(issue.get("detail") or issue.get("code") or "preflight issue")
            for issue in issues[:6]
        )
        raise ValueError(f"preview preflight failed: {detail or 'execution spec is not runnable'}")

    spec = dict(preflight["execution_spec"])
    spec_hash = execution_spec_hash(spec)
    input_revisions = input_revision_snapshot(root, spec)
    authority_hash = preview_authority_hash(spec_hash, input_revisions)
    oversized_join_inputs = [
        row for row in input_revisions
        if row.get("dataset_id") != spec["input_dataset_id"]
        and int(row.get("size_bytes") or 0) > MAX_PREVIEW_JOIN_INPUT_BYTES
    ]
    if oversized_join_inputs:
        names = ", ".join(str(row.get("dataset_id") or "unknown") for row in oversized_join_inputs)
        raise ValueError(
            f"bounded Preview refuses full right-hand join input(s) above "
            f"{MAX_PREVIEW_JOIN_INPUT_BYTES} bytes: {names}"
        )

    registry = _load_registry(root)
    source = _registry_row(registry, spec["input_dataset_id"])
    input_path = _ensure_local_file(root, source)
    bounded, source_rows, observed_rows, source_rows_exact = _bounded_primary_frame(input_path, in_limit)
    frame = bounded.head(in_limit).copy()
    preview_input_rows = len(frame)
    source_truncated = bool(
        (source_rows is not None and source_rows > preview_input_rows)
        or observed_rows > preview_input_rows
    )

    undefined: dict[str, int] = {}
    asof_coverage: list[dict[str, Any]] = []
    row_ledger: list[dict[str, Any]] = []
    frame = _apply_transforms(
        root,
        registry,
        frame,
        spec.get("transforms") or [],
        undefined,
        asof_coverage,
        row_ledger,
    )
    rows_after_transforms = len(frame)
    output = _aggregate_preview(frame, spec)

    return {
        "status": "succeeded",
        "created_at": _now(),
        "spec_hash": spec_hash,
        "authority_hash": authority_hash,
        "input_revisions": input_revisions,
        "bounded": True,
        "sampling": {
            "strategy": "first_rows",
            "input_row_limit": in_limit,
            "source_rows": source_rows,
            "source_rows_exact": source_rows_exact,
            "source_rows_observed": observed_rows,
            "previewed_rows": preview_input_rows,
            "source_truncated": source_truncated,
            "note": (
                "Deterministic bounded execution preview. Values and row effects describe "
                "the preview window, not the full population. CSV/JSONL totals are not "
                "scanned to EOF merely to count rows."
            ),
        },
        "execution_spec": spec,
        "preflight": {
            "warnings": list(preflight.get("warnings") or []),
            "join_probes": list(preflight.get("join_probes") or []),
            "bounded_row_cap": preflight.get("bounded_row_cap"),
            "right_input_full_read_cap_bytes": MAX_PREVIEW_JOIN_INPUT_BYTES,
        },
        "rows": {
            "source": source_rows,
            "source_exact": source_rows_exact,
            "source_observed": observed_rows,
            "preview_input": preview_input_rows,
            "after_transforms": rows_after_transforms,
            "output": len(output),
            "by_step": row_ledger,
        },
        "asof_coverage": asof_coverage,
        "undefined_derived_values": undefined,
        "output": {
            "dataset_id": spec["output_dataset_id"],
            "columns": list(output.columns),
            "dtypes": {key: str(value) for key, value in output.dtypes.items()},
            "rows_returned": min(len(output), out_limit),
            "rows": _json_records(output, out_limit),
        },
        "materialised": False,
        "registered": False,
        "review_required": True,
    }
