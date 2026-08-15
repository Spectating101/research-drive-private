"""Render a durable execution_spec as a standalone, runnable script.

Two jobs. It lets a researcher reproduce an output off-desk, and it is the
escape hatch: when a method exceeds what the engine will run, the same renderer
emits the script instead of the desk failing or faking a result.

The script carries input identity and content fingerprints, because a transform
alone is not reproducible — you must be able to prove you ran it on the same
bytes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA_SUFFIXES = (".parquet", ".csv", ".csv.gz")
FINGERPRINT_FILE_CAP = 64


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def spec_hash(spec: dict[str, Any]) -> str:
    """Same canonical hash the thread store records as accepted_spec_hash."""
    return hashlib.sha256(
        json.dumps(spec, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def fingerprint_path(path: Path | str | None) -> dict[str, Any]:
    """Content fingerprint for a dataset's bytes.

    Reports what it actually hashed. An unreadable or absent input yields
    `fingerprint: None` and a reason — never a placeholder that would make an
    irreproducible script look reproducible.
    """
    if not path:
        return {"path": None, "fingerprint": None, "files": 0, "bytes": 0, "note": "no path resolved"}
    p = Path(path)
    if not p.exists():
        return {"path": str(p), "fingerprint": None, "files": 0, "bytes": 0, "note": "path does not exist"}

    files: list[Path] = []
    if p.is_file():
        files = [p]
    else:
        for suffix in DATA_SUFFIXES:
            files.extend(sorted(p.rglob(f"*{suffix}")))
    if not files:
        return {"path": str(p), "fingerprint": None, "files": 0, "bytes": 0, "note": "no data files found"}

    truncated = len(files) > FINGERPRINT_FILE_CAP
    digest = hashlib.sha256()
    total = 0
    for f in sorted(files)[:FINGERPRINT_FILE_CAP]:
        try:
            data = f.read_bytes()
        except Exception as exc:  # noqa: BLE001
            return {"path": str(p), "fingerprint": None, "files": len(files), "bytes": 0, "note": f"unreadable: {exc}"}
        total += len(data)
        digest.update(f.name.encode("utf-8"))
        digest.update(data)
    return {
        "path": str(p),
        "fingerprint": f"sha256:{digest.hexdigest()}",
        "files": len(files),
        "bytes": total,
        "note": f"first {FINGERPRINT_FILE_CAP} files only" if truncated else None,
    }


def _py(value: Any) -> str:
    return json.dumps(value)


def _transform_lines(transforms: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for step in transforms or []:
        op = step.get("op")
        if op == "filter":
            col, o, v = step.get("column"), step.get("cmp") or "eq", step.get("value")
            cmp = {"eq": "==", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}.get(o)
            if cmp:
                lines.append(f"frame = frame[frame[{_py(col)}] {cmp} {_py(v)}]")
            elif o == "in":
                lines.append(f"frame = frame[frame[{_py(col)}].isin({_py(v)})]")
            elif o == "not_in":
                lines.append(f"frame = frame[~frame[{_py(col)}].isin({_py(v)})]")
            elif o == "contains":
                lines.append(f"frame = frame[frame[{_py(col)}].astype(str).str.contains({_py(v)}, na=False)]")
        elif op == "select":
            lines.append(f"frame = frame[{_py(list(step.get('columns') or []))}]")
        elif op == "rename":
            lines.append(f"frame = frame.rename(columns={_py(step.get('mapping') or {})})")
        elif op == "sort":
            by = step.get("by") or step.get("columns") or []
            by = [by] if isinstance(by, str) else list(by)
            lines.append(f"frame = frame.sort_values({_py(by)})")
        elif op == "head":
            lines.append(f"frame = frame.head({int(step.get('n') or 10)})")
        elif op == "drop_na":
            cols = step.get("columns")
            lines.append(f"frame = frame.dropna(subset={_py(list(cols))})" if cols else "frame = frame.dropna()")
        elif op == "drop_duplicates":
            cols = step.get("columns")
            lines.append(
                f"frame = frame.drop_duplicates(subset={_py(list(cols))})" if cols else "frame = frame.drop_duplicates()"
            )
        elif op == "join":
            right = step.get("right_dataset_id")
            on = list(step.get("on") or [])
            how = step.get("how") or "inner"
            collapse = (step.get("collapse") or {}).get("strategy")
            var = f"right_{str(right).replace('-', '_')}"
            lines.append(f"{var} = read_input({_py(right)})")
            if collapse in {"first", "last"}:
                lines.append(
                    f"# declared collapse: the right side is 1:N on {on[0] if on else '?'}; "
                    f"keeping {collapse} row per key"
                )
                lines.append(f"{var} = {var}.drop_duplicates(subset={_py(on)}, keep={_py(collapse)})")
            elif collapse == "error":
                lines.append(f"assert not {var}.duplicated(subset={_py(on)}).any(), 'right side is not 1:1 on the key'")
            lines.append(f"frame = frame.merge({var}, on={_py(on)}, how={_py(how)})")
        elif op == "derive":
            alias = step.get("as")
            if step.get("expr") is not None:
                # Same namespace the engine builds: whitelisted helpers plus the
                # frame's columns, so the expression evaluates identically.
                lines.append(f"frame[{_py(alias)}] = _finite(_derive_expr(frame, {_py(step['expr'])}))")
            else:
                fn = step.get("fn")
                col = step.get("column")
                if fn == "abs":
                    lines.append(f"frame[{_py(alias)}] = frame[{_py(col)}].abs()")
                elif fn == "indicator":
                    lines.append(
                        f"frame[{_py(alias)}] = _compare(frame[{_py(col)}], {_py(step.get('cmp'))}, "
                        f"{_py(step.get('value'))}).fillna(False).astype('int64')"
                    )
                else:
                    right = (
                        f"frame[{_py(step['by_column'])}]" if "by_column" in step else _py(step.get("value"))
                    )
                    sym = {"add": "+", "sub": "-", "mul": "*", "div": "/"}.get(fn)
                    expr = f"frame[{_py(col)}] {sym} {right}"
                    lines.append(
                        f"frame[{_py(alias)}] = _finite({expr})" if fn == "div" else f"frame[{_py(alias)}] = {expr}"
                    )
    return lines


DERIVE_RUNTIME = '''
def _finite(result):
    """inf is not a measurement — mirrors the engine."""
    try:
        return result.replace([np.inf, -np.inf], np.nan)
    except (TypeError, AttributeError):
        return result


def _compare(series, cmp, value):
    ops = {"eq": series == value, "ne": series != value, "gt": series > value,
           "gte": series >= value, "lt": series < value, "lte": series <= value}
    if cmp in ops:
        return ops[cmp]
    if cmp == "in":
        return series.isin(value)
    if cmp == "not_in":
        return ~series.isin(value)
    if cmp == "contains":
        return series.astype(str).str.contains(str(value), na=False)
    raise ValueError("unsupported cmp: " + str(cmp))


def _expr_functions():
    periods = {"day": "D", "week": "W", "month": "M", "quarter": "Q", "year": "Y"}

    def dt(series):
        return pd.to_datetime(series, errors="coerce")

    def date_trunc(series, unit):
        return dt(series).dt.to_period(periods[str(unit).lower()]).astype(str)

    def substr(series, start, length=None):
        start = int(start)
        stop = start + int(length) if length is not None else None
        return series.astype(str).str.slice(start, stop)

    def concat(*parts):
        out = None
        for p in parts:
            s = p.astype(str) if hasattr(p, "astype") else pd.Series([str(p)])
            out = s if out is None else out.str.cat(s, na_rep="")
        return out

    def if_else(cond, when_true, when_false):
        return pd.Series(np.where(cond, when_true, when_false), index=getattr(cond, "index", None))

    def ntile(series, buckets):
        return pd.qcut(series.rank(method="first"), int(buckets), labels=False) + 1

    return {"dt": dt, "date_trunc": date_trunc, "substr": substr,
            "concat": concat, "if_else": if_else, "ntile": ntile}


def _derive_expr(frame, expr):
    """Evaluate a derive expression exactly as the desk engine did.

    SAFETY: `expr` is not arbitrary code. Before a spec can be accepted it passes
    synthesis_executor.validate_expression, which walks the AST and rejects any
    node outside a fixed whitelist — no imports, attribute access, subscripts,
    comprehensions, lambdas or names beyond the helpers below and the frame's own
    columns. The string embedded in this script is that already-validated
    expression, reproduced verbatim so the result matches the desk. __builtins__
    is emptied so nothing outside `ns` is reachable.

    If you did not get this file from the desk, read the expression before running.
    """
    ns = dict(_expr_functions())
    ns.update({c: frame[c] for c in frame.columns})
    return eval(expr, {"__builtins__": {}}, ns)  # noqa: S307 - AST-whitelisted upstream
'''


def render_script(
    spec: dict[str, Any],
    inputs: dict[str, dict[str, Any]],
    *,
    probes: list[dict[str, Any]] | None = None,
    runnable_on_desk: bool = True,
) -> str:
    """Emit a self-contained pandas script reproducing `spec`.

    `inputs` maps dataset_id -> fingerprint_path() result.
    """
    metrics = spec.get("metrics") or []
    group_by = list(spec.get("group_by") or [])
    agg = {}
    for m in metrics:
        fn = m.get("function")
        alias = m.get("as")
        if not alias:
            continue
        if fn == "count":
            # count needs any column when grouped, and none at all when ungrouped
            column = group_by[0] if group_by else None
        else:
            column = m.get("column")
        agg[alias] = (column, fn)

    head: list[str] = [
        '"""Reproduces a Research Drive synthesis output.',
        "",
        f"execution_spec sha256 : {spec_hash(spec)}",
        f"generated             : {_now()}",
        f"output                : {spec.get('output_dataset_id')}",
        "",
    ]
    if not runnable_on_desk:
        head += [
            "This method is outside what the desk engine will execute.",
            "It was not run there. Run it yourself and judge the result.",
            "",
        ]
    head += ["INPUTS — verify these fingerprints before trusting a reproduction:"]
    for dataset_id, fp in (inputs or {}).items():
        if fp.get("fingerprint"):
            head.append(f"  {dataset_id}: {fp['fingerprint']}  ({fp['files']} file(s), {fp['bytes']} bytes)")
        else:
            head.append(f"  {dataset_id}: NOT FINGERPRINTED — {fp.get('note')}")
    if probes:
        head += ["", "MEASURED JOINS:"]
        for p in probes:
            if p.get("probe_error"):
                head.append(f"  {p.get('right_dataset_id')} on {p.get('key')}: not measured — {p['probe_error']}")
            else:
                head.append(
                    f"  {p.get('right_dataset_id')} on {p.get('key')}: "
                    f"{p.get('shared_distinct')} shared keys, "
                    f"{p.get('coverage_right_pct')}% of the joining side"
                )
    head += ['"""', ""]

    needs_runtime = any(t.get("op") == "derive" for t in (spec.get("transforms") or []))
    body: list[str] = [
        "import numpy as np",
        "import pandas as pd",
        "",
    ]
    if needs_runtime:
        body += [DERIVE_RUNTIME, ""]
    body += ["PATHS = {"]
    for dataset_id, fp in (inputs or {}).items():
        body.append(f"    {_py(dataset_id)}: {_py(fp.get('path'))},")
    body += [
        "}",
        "",
        "",
        "def read_input(dataset_id):",
        "    path = PATHS[dataset_id]",
        "    if path is None:",
        "        raise SystemExit(f'no local path recorded for {dataset_id}')",
        "    if str(path).endswith('.parquet'):",
        "        return pd.read_parquet(path)",
        "    return pd.read_csv(path)",
        "",
        "",
        f"frame = read_input({_py(spec.get('input_dataset_id'))})",
    ]
    body += _transform_lines(spec.get("transforms") or [])
    if group_by and agg:
        pairs = ", ".join(f"{k}=pd.NamedAgg(column={_py(v[0])}, aggfunc={_py(v[1])})" for k, v in agg.items() if k)
        body += ["", f"result = frame.groupby({_py(group_by)}, dropna=False).agg({pairs}).reset_index()"]
    elif agg:
        # Ungrouped: the engine aggregates the whole frame to a single row. Emitting
        # the frame here would hand a reviewer a different result than the desk got.
        cells = []
        for alias, (col, fn) in agg.items():
            if not alias:
                continue
            expr = "frame.shape[0]" if fn == "count" else f"frame[{_py(col)}].{fn}()"
            cells.append(f"{_py(alias)}: [{expr}]")
        body += ["", f"result = pd.DataFrame({{{', '.join(cells)}}})"]
    else:
        body += ["", "result = frame"]
    body += [
        "",
        "print(result.head(20).to_string(index=False))",
        "print(f'{len(result)} rows')",
        f"# result.to_parquet({_py(str(spec.get('output_dataset_id')) + '.parquet')})",
        "",
    ]
    return "\n".join(head + body)
