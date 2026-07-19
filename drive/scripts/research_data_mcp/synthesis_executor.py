"""Bounded execution for researcher-approved synthesis thread specifications."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

OUTPUT_DATASET_ID = re.compile(r"^synthesis_[a-z0-9][a-z0-9_]{2,117}$")
MAX_INPUT_BYTES = 512 * 1024 * 1024
MAX_OUTPUT_ROWS = 1_000_000
ALLOWED_METRIC_FNS = frozenset({"count", "sum", "mean", "min", "max"})
ALLOWED_FILTER_OPS = frozenset({"eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "contains"})
ALLOWED_TRANSFORM_OPS = frozenset({"filter", "select", "rename", "sort", "head", "drop_na", "join"})


def validate_execution_spec(spec: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise ValueError("execution_spec must be an object")
    dataset_id = str(spec.get("input_dataset_id") or "").strip()
    output_id = str(spec.get("output_dataset_id") or "").strip()
    group_by = spec.get("group_by") or []
    metrics = spec.get("metrics") or []
    transforms = spec.get("transforms") or []
    if not dataset_id or not output_id:
        raise ValueError("execution_spec requires input_dataset_id and output_dataset_id")
    if dataset_id == output_id:
        raise ValueError("execution output_dataset_id must differ from input_dataset_id")
    if not OUTPUT_DATASET_ID.fullmatch(output_id):
        raise ValueError("output_dataset_id must match synthesis_[a-z0-9_], 13-128 characters")
    if not isinstance(group_by, list) or not all(isinstance(x, str) and x for x in group_by):
        raise ValueError("group_by must be a list of column names")
    if not isinstance(metrics, list) or not metrics:
        raise ValueError("execution_spec requires one or more aggregate metrics")
    for metric in metrics:
        if not isinstance(metric, dict) or str(metric.get("function") or "") not in ALLOWED_METRIC_FNS:
            raise ValueError("metrics only support count, sum, mean, min, or max")
        if not str(metric.get("as") or "").strip():
            raise ValueError("each metric requires an output name")
        if metric.get("function") != "count" and not str(metric.get("column") or "").strip():
            raise ValueError("non-count metrics require a source column")
    if transforms is None:
        transforms = []
    if not isinstance(transforms, list):
        raise ValueError("transforms must be a list")
    if len(transforms) > 16:
        raise ValueError("transforms limited to 16 steps")
    normalized_transforms: list[dict[str, Any]] = []
    for step in transforms:
        if not isinstance(step, dict):
            raise ValueError("each transform must be an object")
        op = str(step.get("op") or "").strip()
        if op not in ALLOWED_TRANSFORM_OPS:
            raise ValueError(f"unsupported transform op: {op or 'empty'}")
        if op == "filter":
            if str(step.get("column") or "").strip() == "":
                raise ValueError("filter requires column")
            if str(step.get("cmp") or "") not in ALLOWED_FILTER_OPS:
                raise ValueError(f"filter cmp must be one of {sorted(ALLOWED_FILTER_OPS)}")
        elif op == "select":
            cols = step.get("columns") or []
            if not isinstance(cols, list) or not cols or not all(isinstance(c, str) and c for c in cols):
                raise ValueError("select requires a non-empty columns list")
        elif op == "rename":
            mapping = step.get("mapping") or {}
            if not isinstance(mapping, dict) or not mapping:
                raise ValueError("rename requires mapping object")
        elif op == "sort":
            by = step.get("by") or step.get("columns") or []
            if isinstance(by, str):
                by = [by]
            if not isinstance(by, list) or not by:
                raise ValueError("sort requires by/columns")
        elif op == "head":
            n = int(step.get("n") or 0)
            if n < 1 or n > MAX_OUTPUT_ROWS:
                raise ValueError("head n must be 1..1000000")
        elif op == "join":
            right = str(step.get("right_dataset_id") or "").strip()
            on = step.get("on") or []
            how = str(step.get("how") or "inner").strip().lower()
            if not right:
                raise ValueError("join requires right_dataset_id")
            if isinstance(on, str):
                on = [on]
            if not isinstance(on, list) or not on or not all(isinstance(x, str) and x for x in on):
                raise ValueError("join requires on columns")
            if how not in {"inner", "left"}:
                raise ValueError("join how must be inner or left")
            step = {**step, "on": on, "how": how, "right_dataset_id": right}
        normalized_transforms.append(dict(step, op=op))
    return {
        "input_dataset_id": dataset_id,
        "output_dataset_id": output_id,
        "group_by": group_by,
        "metrics": metrics,
        "transforms": normalized_transforms,
    }



def preflight_execution_spec(repo_root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Validate structure and, when local bytes exist, required columns.

    Returns a structured report so agents can fix proposals before researcher review.
    Does not invent data or run aggregates.
    """
    repo_root = Path(repo_root).resolve()
    normalized = validate_execution_spec(dict(spec or {}))
    registry = _load_registry(repo_root)
    issues: list[dict[str, Any]] = []
    warnings: list[str] = []

    def need_row(dataset_id: str) -> dict[str, Any] | None:
        try:
            return _registry_row(registry, dataset_id)
        except ValueError as exc:
            issues.append({"code": "unknown_dataset", "dataset_id": dataset_id, "detail": str(exc)})
            return None

    def try_columns(dataset_id: str, source: dict[str, Any]) -> list[str] | None:
        local = str(source.get("local_path") or "").strip()
        if not local or "*" in local:
            warnings.append(f"{dataset_id}: local path missing or glob — column check skipped")
            return None
        path = repo_root / local
        if not path.is_file():
            # directory or compacted
            if path.is_dir():
                warnings.append(f"{dataset_id}: directory input — column check skipped")
                return None
            warnings.append(f"{dataset_id}: local bytes absent — hydrate before execute; column check skipped")
            return None
        try:
            frame = _read_frame(path)
        except Exception as exc:  # noqa: BLE001
            issues.append({"code": "unreadable_input", "dataset_id": dataset_id, "detail": str(exc)[:400]})
            return None
        return [str(c) for c in frame.columns]

    input_row = need_row(normalized["input_dataset_id"])
    input_cols = try_columns(normalized["input_dataset_id"], input_row) if input_row else None

    # Transform column checks (approximate: filter/select/sort against input before join)
    working_cols = set(input_cols) if input_cols is not None else None
    for step in normalized.get("transforms") or []:
        op = step.get("op")
        if working_cols is None:
            if op == "join":
                need_row(str(step.get("right_dataset_id") or ""))
            continue
        if op == "filter":
            col = str(step.get("column") or "")
            if col not in working_cols:
                issues.append({"code": "missing_column", "op": "filter", "column": col, "available_sample": sorted(working_cols)[:24]})
        elif op == "select":
            missing = [c for c in (step.get("columns") or []) if c not in working_cols]
            if missing:
                issues.append({"code": "missing_column", "op": "select", "columns": missing, "available_sample": sorted(working_cols)[:24]})
            else:
                working_cols = set(step.get("columns") or [])
        elif op == "rename":
            mapping = step.get("mapping") or {}
            missing = [str(k) for k in mapping if str(k) not in working_cols]
            if missing:
                issues.append({"code": "missing_column", "op": "rename", "columns": missing})
            else:
                for old, new in mapping.items():
                    working_cols.discard(str(old))
                    working_cols.add(str(new))
        elif op == "sort":
            by = step.get("by") or step.get("columns") or []
            if isinstance(by, str):
                by = [by]
            missing = [c for c in by if c not in working_cols]
            if missing:
                issues.append({"code": "missing_column", "op": "sort", "columns": missing})
        elif op == "drop_na":
            subset = step.get("columns")
            if isinstance(subset, list) and subset:
                missing = [c for c in subset if c not in working_cols]
                if missing:
                    issues.append({"code": "missing_column", "op": "drop_na", "columns": missing})
        elif op == "join":
            right_id = str(step.get("right_dataset_id") or "")
            right_row = need_row(right_id)
            right_cols = try_columns(right_id, right_row) if right_row else None
            on = list(step.get("on") or [])
            for col in on:
                if col not in working_cols:
                    issues.append({"code": "missing_column", "op": "join", "side": "left", "column": col})
                if right_cols is not None and col not in right_cols:
                    issues.append({"code": "missing_column", "op": "join", "side": "right", "column": col, "dataset_id": right_id})
            if right_cols is not None:
                # approximate post-join columns
                working_cols = set(working_cols) | set(right_cols)

    if working_cols is not None:
        needed = set(normalized.get("group_by") or [])
        needed.update(str(m.get("column") or "") for m in normalized.get("metrics") or [] if m.get("column"))
        missing = sorted(c for c in needed if c and c not in working_cols)
        if missing:
            issues.append({"code": "missing_column", "op": "aggregate", "columns": missing, "available_sample": sorted(working_cols)[:24]})

    ok = not issues
    return {
        "ok": ok,
        "execution_spec": normalized,
        "issues": issues,
        "warnings": warnings,
        "review_required": True,
        "note": (
            "Preflight only — does not execute or materialise. "
            + ("Fix issues before proposing." if not ok else "Spec is structurally runnable when local inputs are present.")
        ),
    }



def _load_registry(repo_root: Path) -> dict[str, Any]:
    return json.loads((repo_root / "config/research_query_registry.json").read_text(encoding="utf-8"))


def _registry_row(registry: dict[str, Any], dataset_id: str) -> dict[str, Any]:
    row = next((r for r in registry.get("datasets") or [] if r.get("dataset_id") == dataset_id), None)
    if not row:
        raise ValueError(f"dataset is not registered: {dataset_id}")
    return row


def _ensure_local_file(repo_root: Path, source: dict[str, Any]) -> Path:
    """Hydrate from Drive when local bytes were compacted, then return concrete file path."""
    from scripts.research_data_mcp.registry_hydrate import ensure_registry_local_bytes

    path = str(source.get("local_path") or "").strip()
    if not path or "*" in path:
        # Directory local_path: try hydrate then pick first tabular file
        hydrate = ensure_registry_local_bytes(repo_root, source)
        root = str(source.get("local_path") or source.get("local_root") or "").rstrip("/*")
        if not root:
            raise ValueError("execution input must have one concrete local file path")
        base = repo_root / root
        if not base.exists():
            raise ValueError(
                f"execution input bytes are unavailable locally"
                + (f" (hydrate={hydrate.get('error') or hydrate.get('reason')})" if hydrate else "")
            )
        candidates = sorted(
            [
                p
                for p in base.rglob("*")
                if p.is_file()
                and (
                    p.suffix.lower() in {".csv", ".parquet", ".json"}
                    or p.name in {"STOCK_DAY_ALL", "STOCK_DAY_AVG_ALL"}
                )
            ]
        )
        if not candidates:
            raise ValueError("execution input directory has no csv/parquet/json files")
        return candidates[0]

    file_path = repo_root / path
    if not file_path.is_file():
        hydrate = ensure_registry_local_bytes(repo_root, source)
        if not file_path.is_file():
            raise ValueError(
                "execution input bytes are unavailable locally"
                + (f" (hydrate={hydrate.get('error') or hydrate.get('ok')})" if hydrate else "")
            )
    if file_path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("execution input exceeds the 512 MiB in-memory execution limit")
    return file_path


def _read_frame(file_path: Path):
    import pandas as pd

    suffix = file_path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(file_path)
    if suffix == ".csv":
        return pd.read_csv(file_path)

    def _from_json_bytes() -> Any:
        # Prefer explicit JSON parse first. pd.read_json on SEC company_tickers
        # ({"0":{cik,ticker,title}, ...}) succeeds but returns a transposed wide frame.
        raw = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return pd.DataFrame(raw)
        if isinstance(raw, dict):
            if raw and all(isinstance(v, dict) for v in raw.values()):
                return pd.DataFrame(list(raw.values()))
            return pd.json_normalize(raw)
        raise ValueError("unsupported json shape for execution input")

    if suffix == ".json" or suffix == "":
        return _from_json_bytes()
    # TWSE OpenAPI harvests sometimes land as extensionless JSON payloads
    head = file_path.read_bytes()[:1]
    if head in (b"[", b"{"):
        return _from_json_bytes()
    raise ValueError("execution input must be parquet, csv, or json")


def _apply_filter(frame, step: dict[str, Any]):
    col = str(step["column"])
    cmp = str(step["cmp"])
    value = step.get("value")
    series = frame[col]
    if cmp == "eq":
        return frame[series == value]
    if cmp == "ne":
        return frame[series != value]
    if cmp == "gt":
        return frame[series > value]
    if cmp == "gte":
        return frame[series >= value]
    if cmp == "lt":
        return frame[series < value]
    if cmp == "lte":
        return frame[series <= value]
    if cmp == "in":
        return frame[series.isin(list(value or []))]
    if cmp == "not_in":
        return frame[~series.isin(list(value or []))]
    if cmp == "contains":
        return frame[series.astype(str).str.contains(str(value), na=False)]
    raise ValueError(f"unsupported filter cmp: {cmp}")


def _apply_transforms(repo_root: Path, registry: dict[str, Any], frame, transforms: list[dict[str, Any]]):
    for step in transforms:
        op = step["op"]
        if op == "filter":
            if step["column"] not in frame.columns:
                raise ValueError(f"filter column missing: {step['column']}")
            frame = _apply_filter(frame, step)
        elif op == "select":
            missing = [c for c in step["columns"] if c not in frame.columns]
            if missing:
                raise ValueError(f"select columns missing: {', '.join(missing)}")
            frame = frame[list(step["columns"])]
        elif op == "rename":
            frame = frame.rename(columns={str(k): str(v) for k, v in (step.get("mapping") or {}).items()})
        elif op == "sort":
            by = step.get("by") or step.get("columns") or []
            if isinstance(by, str):
                by = [by]
            missing = [c for c in by if c not in frame.columns]
            if missing:
                raise ValueError(f"sort columns missing: {', '.join(missing)}")
            frame = frame.sort_values(by, ascending=bool(step.get("ascending", True)))
        elif op == "head":
            frame = frame.head(int(step["n"]))
        elif op == "drop_na":
            subset = step.get("columns")
            frame = frame.dropna(subset=subset if isinstance(subset, list) and subset else None)
        elif op == "join":
            right_src = _registry_row(registry, str(step["right_dataset_id"]))
            right_path = _ensure_local_file(repo_root, right_src)
            right = _read_frame(right_path)
            on = list(step["on"])
            missing_l = [c for c in on if c not in frame.columns]
            missing_r = [c for c in on if c not in right.columns]
            if missing_l or missing_r:
                raise ValueError(
                    "join columns missing: "
                    + ", ".join([*(f"left.{c}" for c in missing_l), *(f"right.{c}" for c in missing_r)])
                )
            frame = frame.merge(right, on=on, how=str(step.get("how") or "inner"), suffixes=("", "_right"))
        else:
            raise ValueError(f"unsupported transform op: {op}")
        if len(frame) > MAX_OUTPUT_ROWS:
            raise ValueError("transform intermediate result exceeds the 1,000,000-row safety limit")
    return frame


def execute(repo_root: Path, job_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Materialise one approved local aggregate into a parquet research asset."""
    repo_root = Path(repo_root).resolve()
    spec = validate_execution_spec(dict(plan.get("execution_spec") or {}))
    registry = _load_registry(repo_root)
    source = _registry_row(registry, spec["input_dataset_id"])
    file_path = _ensure_local_file(repo_root, source)
    frame = _read_frame(file_path)
    frame = _apply_transforms(repo_root, registry, frame, spec.get("transforms") or [])

    needed = set(spec["group_by"])
    needed.update(str(m.get("column") or "") for m in spec["metrics"] if m.get("column"))
    missing = sorted(column for column in needed if column and column not in frame.columns)
    if missing:
        raise ValueError(f"execution input is missing columns: {', '.join(missing)}")
    grouped = frame.groupby(spec["group_by"], dropna=False) if spec["group_by"] else frame.groupby(lambda _x: 0)
    output = None
    for metric in spec["metrics"]:
        fn, column, alias = metric["function"], metric.get("column"), metric["as"]
        series = grouped.size() if fn == "count" else getattr(grouped[column], fn)()
        series = series.rename(alias)
        output = series.to_frame() if output is None else output.join(series)
    output = output.reset_index(drop=not bool(spec["group_by"]))
    if len(output) > MAX_OUTPUT_ROWS:
        raise ValueError("execution output exceeds the 1,000,000-row safety limit")
    out_dir = repo_root / "data_lake/synthesis/thread_outputs" / str(plan.get("thread_id") or "unknown") / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet = out_dir / "output.parquet"
    output.to_parquet(parquet, index=False)
    rel_input = str(file_path.relative_to(repo_root)) if file_path.is_relative_to(repo_root) else str(file_path)
    manifest = out_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_id": f"synthesis_manifest_{job_id}",
                "job_id": job_id,
                "execution_spec": spec,
                "input": {
                    "dataset_id": spec["input_dataset_id"],
                    "path": rel_input,
                    "bytes": file_path.stat().st_size,
                    "sha256": hashlib.sha256(file_path.read_bytes()).hexdigest(),
                },
                "output": {
                    "dataset_id": spec["output_dataset_id"],
                    "path": str(parquet.relative_to(repo_root)),
                    "bytes": parquet.stat().st_size,
                    "sha256": hashlib.sha256(parquet.read_bytes()).hexdigest(),
                    "rows": len(output),
                    "columns": list(output.columns),
                    "dtypes": {key: str(value) for key, value in output.dtypes.items()},
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    rel = str(out_dir.relative_to(repo_root))
    return {
        "execution_spec": spec,
        "output_manifest_id": f"synthesis_manifest_{job_id}",
        "rows": len(output),
        "materialized": {
            "dataset_id": spec["output_dataset_id"],
            "canonical_dir": rel,
            "manifest_path": str(manifest.relative_to(repo_root)),
            "files": [{"name": "output.parquet", "path": str(parquet.relative_to(repo_root)), "bytes": parquet.stat().st_size}],
        },
    }
