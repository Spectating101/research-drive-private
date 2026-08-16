"""Bounded execution for researcher-approved synthesis thread specifications."""

from __future__ import annotations

import ast
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
ALLOWED_TRANSFORM_OPS = frozenset({"filter", "select", "rename", "sort", "head", "drop_na", "join", "join_asof", "derive", "drop_duplicates"})
# As-of is the point-in-time join: take the most recent right-hand row at or
# before each left row's timestamp. `backward` is the only direction that cannot
# see the future, so it is the default; `forward` and `nearest` are available but
# a researcher choosing them is choosing to look ahead.
ALLOWED_ASOF_DIRECTIONS = frozenset({"backward", "forward", "nearest"})
ALLOWED_DERIVE_FNS = frozenset({"indicator", "add", "sub", "mul", "div", "abs"})
# A 1:N join side multiplies rows. The researcher chooses how it collapses; the
# engine never picks silently.
ALLOWED_COLLAPSE_STRATEGIES = frozenset({"first", "last", "error"})
# Structural interlock, not a research standard. Losing most of BOTH sides means
# the keys do not describe the same calendar; it says nothing about whether the
# surviving rows are worth studying — the caller judges that. Measured retention
# is always reported in join_probes regardless of this value, and callers may
# override it per call.
DEFAULT_JOIN_RETENTION_FLOOR_PCT = 20.0
ARITHMETIC_DERIVE_FNS = frozenset({"add", "sub", "mul", "div"})
DERIVE_COLUMN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
PROXY_FITNESS = frozenset({"untested", "face_valid"})


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
    derived_names: set[str] = set()
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
            collapse = step.get("collapse")
            if collapse is not None:
                if not isinstance(collapse, dict):
                    raise ValueError("join collapse must be an object")
                strategy = str(collapse.get("strategy") or "").strip().lower()
                if strategy not in ALLOWED_COLLAPSE_STRATEGIES:
                    raise ValueError(
                        "join collapse strategy must be one of " + ", ".join(sorted(ALLOWED_COLLAPSE_STRATEGIES))
                    )
                collapse = {"strategy": strategy}
            step = {**step, "on": on, "how": how, "right_dataset_id": right, "collapse": collapse,
                    "accept_row_loss": bool(step.get("accept_row_loss"))}
        elif op == "join_asof":
            right = str(step.get("right_dataset_id") or "").strip()
            on = str(step.get("on") or "").strip()
            # Real datasets rarely agree on the name of their time column: a daily
            # panel says `date`, a point-in-time snapshot says `as_of_date`.
            left_on = str(step.get("left_on") or "").strip()
            right_on = str(step.get("right_on") or "").strip()
            by = step.get("by") or []
            direction = str(step.get("direction") or "backward").strip().lower()
            tolerance = step.get("tolerance")
            if not right:
                raise ValueError("join_asof requires right_dataset_id")
            if on and (left_on or right_on):
                raise ValueError("join_asof takes either `on` or both `left_on` and `right_on`, not both")
            if not on and not (left_on and right_on):
                raise ValueError(
                    "join_asof requires a single ordered `on` column, or `left_on` and `right_on` when the sides name it differently"
                )
            if on:
                left_on = right_on = on
            if isinstance(by, str):
                by = [by]
            if not isinstance(by, list) or not all(isinstance(x, str) and x for x in by):
                raise ValueError("join_asof `by` must be a list of column names")
            if direction not in ALLOWED_ASOF_DIRECTIONS:
                raise ValueError(
                    "join_asof direction must be one of " + ", ".join(sorted(ALLOWED_ASOF_DIRECTIONS))
                )
            if tolerance is not None and not isinstance(tolerance, (str, int, float)):
                raise ValueError("join_asof tolerance must be a string like '31D' or a number")
            step = {
                **step,
                "right_dataset_id": right,
                "on": on or None,
                "left_on": left_on,
                "right_on": right_on,
                "by": by,
                "direction": direction,
                "tolerance": tolerance,
            }
        elif op == "derive":
            step = _validate_derive(step, derived_names)
            derived_names.add(step["as"])
        normalized_transforms.append(dict(step, op=op))
    return {
        "input_dataset_id": dataset_id,
        "output_dataset_id": output_id,
        "group_by": group_by,
        "metrics": metrics,
        "transforms": normalized_transforms,
        "proxy": _validate_proxy(spec.get("proxy")),
    }


_EXPR_NODES = (
    ast.Expression,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Call,
    ast.IfExp,
    ast.Tuple,
    ast.List,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.BitAnd,
    ast.BitOr,
    ast.BitXor,
    ast.Invert,
    ast.USub,
    ast.UAdd,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
)


def expression_functions() -> dict[str, Any]:
    """The callable surface an expression may reach. Adding a row here widens
    what Composer can express; nothing else in the grammar needs to change."""
    import numpy as np
    import pandas as pd

    def dt(series):
        return pd.to_datetime(series, errors="coerce")

    periods = {"day": "D", "week": "W", "month": "M", "quarter": "Q", "year": "Y"}

    def date_trunc(series, unit):
        key = str(unit).lower()
        if key not in periods:
            raise ValueError(f"date_trunc unit must be one of {sorted(periods)}")
        return dt(series).dt.to_period(periods[key]).astype(str)

    def substr(series, start, length=None):
        start = int(start)
        stop = start + int(length) if length is not None else None
        return series.astype(str).str[start:stop]

    def concat(*parts):
        out = None
        for part in parts:
            piece = part.astype(str) if hasattr(part, "astype") else str(part)
            out = piece if out is None else out + piece
        return out

    def if_else(cond, when_true, when_false):
        return pd.Series(np.where(cond, when_true, when_false), index=cond.index)

    def ntile(series, buckets):
        return pd.qcut(series, int(buckets), labels=False, duplicates="drop") + 1

    return {
        "date_trunc": date_trunc,
        "year": lambda s: dt(s).dt.year,
        "month": lambda s: dt(s).dt.month,
        "quarter": lambda s: dt(s).dt.quarter,
        "day_of_week": lambda s: dt(s).dt.dayofweek,
        "lower": lambda s: s.astype(str).str.lower(),
        "upper": lambda s: s.astype(str).str.upper(),
        "strip": lambda s: s.astype(str).str.strip(),
        "substr": substr,
        "replace": lambda s, old, new: s.astype(str).str.replace(str(old), str(new), regex=False),
        "contains": lambda s, pat: s.astype(str).str.contains(str(pat), na=False),
        "concat": concat,
        "length": lambda s: s.astype(str).str.len(),
        "abs": lambda s: s.abs(),
        "round": lambda s, digits=0: s.round(int(digits)),
        "clip": lambda s, low, high: s.clip(low, high),
        "log": lambda s: np.log(s.where(s > 0)),
        "sqrt": lambda s: np.sqrt(s.where(s >= 0)),
        "if_else": if_else,
        "coalesce": lambda a, b: a.fillna(b),
        "is_null": lambda s: s.isna(),
        "rank_pct": lambda s: s.rank(pct=True),
        "ntile": ntile,
    }


def validate_expression(expr: str) -> tuple[ast.Expression, list[str]]:
    """Parse one row-wise expression and prove it is safe before it ever runs.

    Safety is structural: no attribute access, no subscripting, no lambdas or
    comprehensions, and calls only to names in expression_functions(). Returns
    the tree and the column names it reads.
    """
    text = str(expr or "").strip()
    if not text:
        raise ValueError("derive expr must be a non-empty expression")
    if len(text) > 2000:
        raise ValueError("derive expr is limited to 2000 characters")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"derive expr is not a valid expression: {exc.msg}") from exc
    functions = set(expression_functions())
    referenced: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BoolOp):
            raise ValueError("use & and | instead of and/or: expressions operate on whole columns")
        if not isinstance(node, _EXPR_NODES):
            raise ValueError(f"derive expr may not use {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("derive expr may only call named functions")
            if node.func.id not in functions:
                raise ValueError(
                    f"unknown function {node.func.id!r}; available: {', '.join(sorted(functions))}"
                )
            if node.keywords:
                raise ValueError("derive expr functions take positional arguments only")
        elif isinstance(node, ast.Name):
            if node.id not in functions and node.id not in referenced:
                referenced.append(node.id)
    if not referenced:
        raise ValueError("derive expr must read at least one column")
    return tree, referenced


def _validate_derive(step: dict[str, Any], derived_names: set[str]) -> dict[str, Any]:
    """One computed column, from a fixed operator set. No expressions, no eval."""
    alias = str(step.get("as") or "").strip()
    fn = str(step.get("fn") or "").strip()
    column = str(step.get("column") or "").strip()
    if not DERIVE_COLUMN.fullmatch(alias):
        raise ValueError("derive requires as: lowercase name matching [a-z][a-z0-9_]{0,63}")
    if alias in derived_names:
        raise ValueError(f"derive produces duplicate column: {alias}")
    if step.get("expr") is not None:
        if fn or column:
            raise ValueError("derive takes either expr or fn/column, not both")
        _tree, reads = validate_expression(step.get("expr"))
        return {"op": "derive", "as": alias, "expr": str(step["expr"]).strip(), "reads": reads}
    if fn not in ALLOWED_DERIVE_FNS:
        raise ValueError(f"derive fn must be one of {sorted(ALLOWED_DERIVE_FNS)}")
    if not column:
        raise ValueError("derive requires a source column")
    normalized: dict[str, Any] = {"op": "derive", "as": alias, "fn": fn, "column": column}
    if fn == "indicator":
        cmp = str(step.get("cmp") or "")
        if cmp not in ALLOWED_FILTER_OPS:
            raise ValueError(f"derive indicator cmp must be one of {sorted(ALLOWED_FILTER_OPS)}")
        if "value" not in step:
            raise ValueError("derive indicator requires a comparison value")
        normalized["cmp"] = cmp
        normalized["value"] = step.get("value")
    elif fn in ARITHMETIC_DERIVE_FNS:
        by_column = str(step.get("by_column") or "").strip()
        has_value = "value" in step and step.get("value") is not None
        if bool(by_column) == has_value:
            raise ValueError(f"derive {fn} requires exactly one of by_column or value")
        if by_column:
            normalized["by_column"] = by_column
        else:
            value = step.get("value")
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"derive {fn} value must be a number")
            normalized["value"] = value
    return normalized


def _validate_proxy(proxy: Any) -> dict[str, Any] | None:
    """A declared stand-in. Optional, but when present it must say what it replaces."""
    if proxy is None:
        return None
    if not isinstance(proxy, dict):
        raise ValueError("proxy must be an object")
    stands_in_for = str(proxy.get("stands_in_for") or "").strip()
    construction = str(proxy.get("construction") or "").strip()
    limitations = proxy.get("limitations") or []
    fitness = str(proxy.get("fitness") or "untested").strip()
    if not stands_in_for:
        raise ValueError("proxy requires stands_in_for: the construct this output substitutes for")
    if not construction:
        raise ValueError("proxy requires construction: how the substitute is built")
    if not isinstance(limitations, list) or not limitations or not all(
        isinstance(x, str) and x.strip() for x in limitations
    ):
        raise ValueError("proxy requires limitations: a non-empty list of stated weaknesses")
    if fitness == "validated":
        raise ValueError(
            "proxy fitness cannot be declared validated: nothing in this system measures proxy fitness"
        )
    if fitness not in PROXY_FITNESS:
        raise ValueError(f"proxy fitness must be one of {sorted(PROXY_FITNESS)}")
    return {
        "stands_in_for": stands_in_for,
        "construction": construction,
        "limitations": [x.strip() for x in limitations],
        "fitness": fitness,
    }



def _probe_join_step(
    *,
    left_path: Path | None,
    right_path: Path | None,
    key: str,
    left_id: str,
    right_id: str,
) -> dict[str, Any]:
    """Measure a declared join against the real bytes.

    Never guesses: an unresolved side returns probe_error and no counts, so a
    caller cannot mistake absence of evidence for a working join.
    """
    from scripts.research_data_mcp.synthesis.pair_probe import probe_pair

    return probe_pair(left_path, right_path, key, left_id=left_id, right_id=right_id)


def _non_finite_report(path: Path, columns: list[str]) -> dict[str, int]:
    """Count inf/-inf per aggregate column. Silence means the file was unreadable
    or the columns absent — never that the data was checked and found clean."""
    if not columns:
        return {}
    try:
        import numpy as np
        import pandas as pd

        frame = pd.read_parquet(path) if str(path).endswith(".parquet") else pd.read_csv(path, low_memory=False)
    except Exception:
        return {}
    found: dict[str, int] = {}
    for column in columns:
        if column not in frame.columns:
            continue
        series = pd.to_numeric(frame[column], errors="coerce")
        count = int(np.isinf(series).sum())
        if count:
            found[column] = count
    return found


def preflight_execution_spec(
    repo_root: Path,
    spec: dict[str, Any],
    *,
    retention_floor_pct: float = DEFAULT_JOIN_RETENTION_FLOOR_PCT,
) -> dict[str, Any]:
    """Validate structure and, when local bytes exist, required columns.

    Returns a structured report so agents can fix proposals before researcher review.
    Does not invent data or run aggregates.
    """
    repo_root = Path(repo_root).resolve()
    normalized = validate_execution_spec(dict(spec or {}))
    registry = _load_registry(repo_root)
    issues: list[dict[str, Any]] = []
    warnings: list[str] = []
    probes: list[dict[str, Any]] = []

    def try_path(source: dict[str, Any] | None) -> Path | None:
        """Same addressing the executor uses, or the gate probes nothing."""
        from scripts.research_data_mcp.synthesis.dataset_paths import resolve_dataset_file

        if not source:
            return None
        found, _reason = resolve_dataset_file(repo_root, source)
        return found

    def need_row(dataset_id: str) -> dict[str, Any] | None:
        try:
            return _registry_row(registry, dataset_id)
        except ValueError as exc:
            issues.append({"code": "unknown_dataset", "dataset_id": dataset_id, "detail": str(exc)})
            return None

    def try_columns(dataset_id: str, source: dict[str, Any]) -> list[str] | None:
        from scripts.research_data_mcp.synthesis.dataset_paths import resolve_dataset_file

        path, reason = resolve_dataset_file(repo_root, source)
        if path is None:
            # The reason names what is actually wrong — a root that is not on this
            # machine, a file the registry names but does not exist, or a directory
            # holding several datasets — rather than "column check skipped".
            warnings.append(f"{reason}; column check skipped")
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
        elif op == "derive":
            alias = str(step.get("as") or "")
            read_keys = step.get("reads") or [] if step.get("expr") else [
                str(step.get(key) or "") for key in ("column", "by_column")
            ]
            for col in read_keys:
                if col and col not in working_cols:
                    issues.append(
                        {
                            "code": "missing_column",
                            "op": "derive",
                            "column": col,
                            "available_sample": sorted(working_cols)[:24],
                        }
                    )
            if alias in working_cols:
                issues.append({"code": "column_conflict", "op": "derive", "column": alias})
            else:
                working_cols.add(alias)
        elif op == "join_asof":
            right_id = str(step.get("right_dataset_id") or "")
            right_row = need_row(right_id)
            right_cols = try_columns(right_id, right_row) if right_row else None
            left_on = str(step.get("left_on") or step.get("on") or "")
            right_on = str(step.get("right_on") or step.get("on") or "")
            by = list(step.get("by") or [])
            for col in [left_on, *by]:
                if col and col not in working_cols:
                    issues.append({"code": "missing_column", "op": "join_asof", "side": "left", "column": col})
            for col in [right_on, *by]:
                if right_cols is not None and col and col not in right_cols:
                    issues.append({"code": "missing_column", "op": "join_asof", "side": "right",
                                   "column": col, "dataset_id": right_id})
            if by and right_row is not None:
                # An as-of join matches entities exactly and only then reaches back
                # in time, so entity overlap is what decides whether it yields rows.
                probe = _probe_join_step(
                    left_path=try_path(input_row), right_path=try_path(right_row), key=by,
                    left_id=normalized["input_dataset_id"], right_id=right_id,
                )
                probes.append(probe)
                if probe.get("probe_error"):
                    warnings.append(f"{right_id}: as-of entity overlap not measured — {probe['probe_error']}")
                elif probe.get("shared_distinct") == 0:
                    issues.append({
                        "code": "empty_join", "op": "join_asof", "dataset_id": right_id, "key": by,
                        "detail": "the `by` entities share no values; this as-of join returns nothing",
                    })
            if str(step.get("direction") or "backward") != "backward":
                warnings.append(
                    f"{right_id}: as-of direction is "
                    f"'{step.get('direction')}' — this reads values dated after the left row, "
                    "which is lookahead unless the study intends it"
                )
            if step.get("tolerance") is None:
                warnings.append(
                    f"{right_id}: no as-of tolerance set, so an unmatched row may pull an "
                    "arbitrarily old value; set tolerance (e.g. '31D') to bound staleness"
                )
            if right_cols is not None:
                working_cols = set(working_cols) | set(right_cols)
        elif op == "join":
            right_id = str(step.get("right_dataset_id") or "")
            right_row = need_row(right_id)
            right_cols = try_columns(right_id, right_row) if right_row else None
            on = list(step.get("on") or [])
            missing_here = False
            for col in on:
                if col not in working_cols:
                    issues.append({"code": "missing_column", "op": "join", "side": "left", "column": col})
                    missing_here = True
                if right_cols is not None and col not in right_cols:
                    issues.append({"code": "missing_column", "op": "join", "side": "right", "column": col, "dataset_id": right_id})
                    missing_here = True
            if not missing_here:
                probe = _probe_join_step(
                    left_path=try_path(input_row),
                    right_path=try_path(right_row),
                    key=list(on),
                    left_id=normalized["input_dataset_id"],
                    right_id=right_id,
                )
                probes.append(probe)
                if probe.get("probe_error"):
                    warnings.append(
                        f"{right_id}: join not measured — {probe['probe_error']}; hydrate both sides before execute"
                    )
                elif probe.get("shared_distinct") == 0:
                    issues.append({
                        "code": "empty_join",
                        "op": "join",
                        "dataset_id": right_id,
                        "key": list(on),
                        "detail": "the declared key shares no values; this join returns nothing",
                    })
                elif (
                    (probe.get("coverage_left_pct") or 0) < retention_floor_pct
                    and (probe.get("coverage_right_pct") or 0) < retention_floor_pct
                    and not step.get("accept_row_loss")
                ):
                    # Losing most of the long side while keeping all of the short one is
                    # ordinary history truncation. Losing most of BOTH means the keys do
                    # not describe the same calendar — a daily series against month-start
                    # dates, say — and that is almost never intended.
                    issues.append({
                        "code": "join_discards_most_rows",
                        "op": "join",
                        "dataset_id": right_id,
                        "key": list(on),
                        "retained_left_pct": probe.get("coverage_left_pct"),
                        "retained_right_pct": probe.get("coverage_right_pct"),
                        "detail": (
                            f"this join keeps {probe.get('coverage_left_pct')}% of the input and "
                            f"{probe.get('coverage_right_pct')}% of {right_id} "
                            f"({probe.get('shared_distinct')} shared keys). Both sides lose most of "
                            "their rows, which usually means a frequency or calendar mismatch. "
                            "Set accept_row_loss to proceed deliberately."
                        ),
                    })
                elif probe.get("right_cardinality") == "1:N" and not step.get("collapse"):
                    issues.append({
                        "code": "collapse_rule_required",
                        "op": "join",
                        "dataset_id": right_id,
                        "key": list(on),
                        "detail": (
                            f"a side is 1:N ({probe['right_rows']} rows over {probe['right_distinct']} keys); "
                            "declare collapse.strategy so rows are not silently multiplied"
                        ),
                    })
            if right_cols is not None:
                # A name present on both sides is kept from the LEFT; the right one
                # is suffixed _right. A researcher who names it in a metric gets the
                # left value without being told.
                collided = sorted((set(working_cols) & set(right_cols)) - set(on))
                if collided:
                    warnings.append(
                        f"{right_id}: column name(s) {', '.join(collided)} exist on both sides; "
                        f"the input's values are kept and {right_id}'s become "
                        f"{', '.join(c + '_right' for c in collided)}"
                    )
                if str(step.get("how") or "inner").lower() == "left":
                    metric_cols = {str(m.get("column") or "") for m in normalized.get("metrics") or []}
                    from_right = sorted(metric_cols & (set(right_cols) - set(on)))
                    if from_right:
                        warnings.append(
                            f"{right_id}: left join leaves nulls where a key is unmatched, so "
                            f"count() and mean({', '.join(from_right)}) are computed over different "
                            "row counts; use an inner join or drop_na to make the denominator one number"
                        )
                # approximate post-join columns
                working_cols = set(working_cols) | set(right_cols)

    if working_cols is not None:
        needed = set(normalized.get("group_by") or [])
        needed.update(str(m.get("column") or "") for m in normalized.get("metrics") or [] if m.get("column"))
        missing = sorted(c for c in needed if c and c not in working_cols)
        if missing:
            issues.append({"code": "missing_column", "op": "aggregate", "columns": missing, "available_sample": sorted(working_cols)[:24]})

    # `_finite` scrubs inf out of DERIVED columns because inf is not a measurement.
    # The same is true of inf arriving in source data, but silently rewriting a
    # researcher's input would be the engine deciding for them — so report it.
    input_path = try_path(input_row) if input_row else None
    if input_path is not None:
        agg_cols = [str(m.get("column") or "") for m in normalized.get("metrics") or [] if m.get("column")]
        report = _non_finite_report(input_path, agg_cols)
        for column, count in report.items():
            warnings.append(
                f"{normalized['input_dataset_id']}.{column}: {count} non-finite value(s) (inf/-inf) "
                "in the source; aggregates over this column inherit them"
            )

    ok = not issues
    return {
        "ok": ok,
        "execution_spec": normalized,
        "issues": issues,
        "warnings": warnings,
        "join_probes": probes,
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
    """Hydrate from Drive when local bytes were compacted, then return concrete file path.

    Resolution honours the registry's own addressing (local_path, or
    local_root + default_run_id + local_file) across every configured data root.
    It previously looked only under repo_root and, for a directory, took the
    first tabular file it found — which returns a different dataset than the one
    asked for whenever several share a root.
    """
    from scripts.research_data_mcp.registry_hydrate import ensure_registry_local_bytes
    from scripts.research_data_mcp.synthesis.dataset_paths import resolve_dataset_file

    file_path, reason = resolve_dataset_file(repo_root, source)
    if file_path is None:
        # Bytes may be compacted; hydrate then look once more before failing.
        hydrate = ensure_registry_local_bytes(repo_root, source)
        file_path, reason = resolve_dataset_file(repo_root, source)
        if file_path is None:
            detail = f" (hydrate={hydrate.get('error') or hydrate.get('reason') or hydrate.get('ok')})" if hydrate else ""
            raise ValueError(f"execution input bytes are unavailable locally: {reason}{detail}")
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

    def _from_json_lines() -> Any:
        return pd.read_json(file_path, lines=True)

    if suffix in (".jsonl", ".ndjson"):
        return _from_json_lines()

    if suffix == ".json" or suffix == "":
        try:
            return _from_json_bytes()
        except json.JSONDecodeError:
            return _from_json_lines()
    # TWSE OpenAPI harvests sometimes land as extensionless JSON payloads
    head = file_path.read_bytes()[:1]
    if head in (b"[", b"{"):
        try:
            return _from_json_bytes()
        except json.JSONDecodeError:
            return _from_json_lines()
    raise ValueError("execution input must be parquet, csv, json, or jsonl")


def _compare_series(series, cmp: str, value: Any):
    if cmp == "eq":
        return series == value
    if cmp == "ne":
        return series != value
    if cmp == "gt":
        return series > value
    if cmp == "gte":
        return series >= value
    if cmp == "lt":
        return series < value
    if cmp == "lte":
        return series <= value
    if cmp == "in":
        return series.isin(list(value or []))
    if cmp == "not_in":
        return ~series.isin(list(value or []))
    if cmp == "contains":
        return series.astype(str).str.contains(str(value), na=False)
    raise ValueError(f"unsupported filter cmp: {cmp}")


def _apply_filter(frame, step: dict[str, Any]):
    return frame[_compare_series(frame[str(step["column"])], str(step["cmp"]), step.get("value"))]


def _finite(result, notes: dict[str, int] | None = None, alias: str = ""):
    """inf is not a measurement. Division or a log that blew up becomes NaN so a
    downstream mean() cannot report a finite-looking number built on it.

    How many it masked is recorded in `notes`. Without that count a group whose
    every value was undefined reports sum() == 0.0, which reads as a measured
    zero rather than nothing to measure.
    """
    import numpy as np

    try:
        masked = int(np.isinf(result).sum())
    except (TypeError, ValueError):
        masked = 0
    if masked and notes is not None and alias:
        notes[alias] = notes.get(alias, 0) + masked
    try:
        return result.replace([np.inf, -np.inf], np.nan)
    except (TypeError, AttributeError):
        return result


def _apply_expression(frame, step: dict[str, Any], notes: dict[str, int] | None = None):
    alias = str(step["as"])
    if alias in frame.columns:
        raise ValueError(f"derive would overwrite an existing column: {alias}")
    tree, reads = validate_expression(step["expr"])
    missing = [name for name in reads if name not in frame.columns]
    if missing:
        raise ValueError(f"derive expr reads missing columns: {', '.join(missing)}")
    namespace = dict(expression_functions())
    namespace.update({name: frame[name] for name in reads})
    code = compile(ast.fix_missing_locations(tree), "<derive>", "eval")
    result = eval(code, {"__builtins__": {}}, namespace)  # noqa: S307 - AST validated above
    frame = frame.copy()
    frame[alias] = _finite(result, notes, alias)
    return frame


def _apply_derive(frame, step: dict[str, Any], notes: dict[str, int] | None = None):
    if step.get("expr") is not None:
        return _apply_expression(frame, step, notes)
    alias = str(step["as"])
    fn = str(step["fn"])
    column = str(step["column"])
    if column not in frame.columns:
        raise ValueError(f"derive source column missing: {column}")
    if alias in frame.columns:
        raise ValueError(f"derive would overwrite an existing column: {alias}")
    series = frame[column]
    if fn == "indicator":
        result = _compare_series(series, str(step["cmp"]), step.get("value")).fillna(False).astype("int64")
    elif fn == "abs":
        result = series.abs()
    else:
        if "by_column" in step:
            other = str(step["by_column"])
            if other not in frame.columns:
                raise ValueError(f"derive by_column missing: {other}")
            right = frame[other]
        else:
            right = step["value"]
        if fn == "add":
            result = series + right
        elif fn == "sub":
            result = series - right
        elif fn == "mul":
            result = series * right
        elif fn == "div":
            result = _finite(series / right, notes, alias)
        else:
            raise ValueError(f"unsupported derive fn: {fn}")
    frame = frame.copy()
    frame[alias] = result
    return frame


def _apply_transforms(repo_root: Path, registry: dict[str, Any], frame, transforms: list[dict[str, Any]], notes: dict[str, int] | None = None, asof_report: list[dict[str, Any]] | None = None, row_ledger: list[dict[str, Any]] | None = None):
    for position, step in enumerate(transforms, start=1):
        op = step["op"]
        rows_before = len(frame)
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
            # The probe measures overlap on string values, so a key stored as a
            # date on one side and text on the other reads as compatible and then
            # fails the merge on dtype. Align them the way the probe compared them
            # rather than letting the two disagree.
            for key_col in on:
                left_kind = frame[key_col].dtype.kind
                right_kind = right[key_col].dtype.kind
                if left_kind != right_kind:
                    frame = frame.copy()
                    right = right.copy()
                    frame[key_col] = frame[key_col].astype(str)
                    right[key_col] = right[key_col].astype(str)

            # Preflight refuses a 1:N join unless the researcher declared how it
            # collapses. Honour that declaration here, or the rule is theatre and
            # the fan-out happens anyway.
            strategy = str((step.get("collapse") or {}).get("strategy") or "").strip().lower()
            if strategy in {"first", "last"}:
                right = right.drop_duplicates(subset=on, keep=strategy)
            elif strategy == "error" and right.duplicated(subset=on).any():
                raise ValueError(
                    f"join right side {step['right_dataset_id']} is not 1:1 on "
                    f"{', '.join(on)} and collapse.strategy is 'error'"
                )
            frame = frame.merge(right, on=on, how=str(step.get("how") or "inner"), suffixes=("", "_right"))
        elif op == "join_asof":
            import pandas as pd

            right_src = _registry_row(registry, str(step["right_dataset_id"]))
            right_path = _ensure_local_file(repo_root, right_src)
            right = _read_frame(right_path)
            left_on = str(step.get("left_on") or step.get("on") or "")
            right_on = str(step.get("right_on") or step.get("on") or "")
            by = list(step.get("by") or [])
            for side, cols, f in (("left", [left_on, *by], frame), ("right", [right_on, *by], right)):
                missing = [c for c in cols if c not in f.columns]
                if missing:
                    raise ValueError(f"join_asof {side} is missing: {', '.join(missing)}")
            # merge_asof requires both sides ordered by the as-of column, and a
            # comparable dtype on each. Dates arrive as strings often enough that
            # coercing here is the difference between a join and a crash.
            left_frame = frame.copy()
            right_frame = right.copy()
            left_frame[left_on] = pd.to_datetime(left_frame[left_on], errors="coerce")
            right_frame[right_on] = pd.to_datetime(right_frame[right_on], errors="coerce")
            rows_in = len(left_frame)
            left_frame = left_frame.dropna(subset=[left_on]).sort_values(left_on)
            right_frame = right_frame.dropna(subset=[right_on]).sort_values(right_on)
            undated_left = rows_in - len(left_frame)
            tolerance = step.get("tolerance")
            kwargs: dict[str, Any] = {"direction": str(step.get("direction") or "backward")}
            if left_on == right_on:
                kwargs["on"] = left_on
            else:
                kwargs["left_on"] = left_on
                kwargs["right_on"] = right_on
            if by:
                kwargs["by"] = by
            if tolerance is not None:
                kwargs["tolerance"] = pd.Timedelta(tolerance) if isinstance(tolerance, str) else tolerance
            marker = "__asof_matched"
            if marker not in right_frame.columns:
                right_frame[marker] = True
            frame = pd.merge_asof(left_frame, right_frame, suffixes=("", "_right"), **kwargs)
            matched = int(frame[marker].notna().sum()) if marker in frame.columns else len(frame)
            if marker in frame.columns:
                frame = frame.drop(columns=[marker])
            if asof_report is not None:
                asof_report.append({
                    "right_dataset_id": str(step["right_dataset_id"]),
                    "direction": kwargs["direction"],
                    "left_rows": rows_in,
                    "undated_left_rows_dropped": undated_left,
                    "matched_rows": matched,
                    "unmatched_rows": len(frame) - matched,
                    "match_rate_pct": round(100 * matched / len(frame), 1) if len(frame) else 0.0,
                })
        elif op == "derive":
            frame = _apply_derive(frame, step, notes)
        elif op == "drop_duplicates":
            subset = step.get("columns")
            frame = frame.drop_duplicates(subset=subset if isinstance(subset, list) and subset else None)
        else:
            raise ValueError(f"unsupported transform op: {op}")
        if row_ledger is not None:
            row_ledger.append({"step": position, "op": op,
                               "rows_in": rows_before, "rows_out": len(frame)})
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
    undefined: dict[str, int] = {}
    asof_coverage: list[dict[str, Any]] = []
    row_ledger: list[dict[str, Any]] = []
    source_rows = len(frame)
    frame = _apply_transforms(repo_root, registry, frame, spec.get("transforms") or [], undefined, asof_coverage, row_ledger)
    rows_aggregated = len(frame)

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
                "proxy": spec.get("proxy"),
                "input": {
                    "dataset_id": spec["input_dataset_id"],
                    "path": rel_input,
                    "bytes": file_path.stat().st_size,
                    "sha256": hashlib.sha256(file_path.read_bytes()).hexdigest(),
                },
                "undefined_derived_values": undefined,
                "asof_coverage": asof_coverage,
                "rows": {"source": source_rows, "aggregated": rows_aggregated, "by_step": row_ledger},
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
        "proxy": spec.get("proxy"),
        "output_manifest_id": f"synthesis_manifest_{job_id}",
        "undefined_derived_values": undefined,
        "asof_coverage": asof_coverage,
        "source_rows": source_rows,
        "rows_aggregated": rows_aggregated,
        "row_ledger": row_ledger,
        "rows": len(output),
        "materialized": {
            "dataset_id": spec["output_dataset_id"],
            "proxy": spec.get("proxy"),
            "canonical_dir": rel,
            "manifest_path": str(manifest.relative_to(repo_root)),
            "files": [{"name": "output.parquet", "path": str(parquet.relative_to(repo_root)), "bytes": parquet.stat().st_size}],
        },
    }
