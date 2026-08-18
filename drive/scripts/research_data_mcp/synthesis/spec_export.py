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

from scripts.research_data_mcp.synthesis.expr_runtime import RUNTIME_SOURCE

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
    selected = sorted(files)[:FINGERPRINT_FILE_CAP]

    # One file gets the plain hash of its bytes, so the reader can confirm it with
    # sha256sum and it agrees with the run manifest. Chaining the name in is right for
    # many files but is not a file hash, so it carries a different label.
    single = len(selected) == 1
    digest = hashlib.sha256()
    total = 0
    for f in selected:
        try:
            data = f.read_bytes()
        except Exception as exc:  # noqa: BLE001
            return {"path": str(p), "fingerprint": None, "files": len(files), "bytes": 0, "note": f"unreadable: {exc}"}
        total += len(data)
        if not single:
            digest.update(f.name.encode("utf-8"))
        digest.update(data)

    notes = []
    if truncated:
        notes.append(f"first {FINGERPRINT_FILE_CAP} files only")
    if single:
        label = "sha256"
        notes.append("sha256sum of the file")
    else:
        label = "sha256-manifest"
        notes.append(f"chained over {len(selected)} files by name then bytes; not a single file hash")
    return {
        "path": str(p),
        "fingerprint": f"{label}:{digest.hexdigest()}",
        "files": len(files),
        "bytes": total,
        "note": "; ".join(notes) or None,
    }


def _py(value: Any) -> str:
    return json.dumps(value)


def _transform_lines(transforms: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for position, step in enumerate(transforms or [], start=1):
        op = step.get("op")
        lines.append(f"_rows_before = len(frame)  # step {position}: {op}")
        before = len(lines)
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
            lines.append(f"for _key in {_py(on)}:")
            lines.append(f"    if frame[_key].dtype.kind != {var}[_key].dtype.kind:")
            lines.append("        frame[_key] = frame[_key].astype(str)")
            lines.append(f"        {var}[_key] = {var}[_key].astype(str)")
            lines.append(
                f"frame = frame.merge({var}, on={_py(on)}, how={_py(how)}, suffixes=('', '_right'))"
            )
        elif op == "join_asof":
            right = step.get("right_dataset_id")
            left_on = step.get("left_on") or step.get("on")
            right_on = step.get("right_on") or step.get("on")
            by = list(step.get("by") or [])
            direction = step.get("direction") or "backward"
            tolerance = step.get("tolerance")
            var = f"asof_{str(right).replace('-', '_')}"
            lines.append(f"{var} = read_input({_py(right)})")
            lines.append(f"frame[{_py(left_on)}] = pd.to_datetime(frame[{_py(left_on)}], errors='coerce')")
            lines.append(f"{var}[{_py(right_on)}] = pd.to_datetime({var}[{_py(right_on)}], errors='coerce')")
            lines.append(f"frame = frame.dropna(subset=[{_py(left_on)}]).sort_values({_py(left_on)})")
            lines.append(f"{var} = {var}.dropna(subset=[{_py(right_on)}]).sort_values({_py(right_on)})")
            args = [f"direction={_py(direction)}"]
            if left_on == right_on:
                args.append(f"on={_py(left_on)}")
            else:
                args.append(f"left_on={_py(left_on)}")
                args.append(f"right_on={_py(right_on)}")
            if by:
                args.append(f"by={_py(by)}")
            if tolerance is not None:
                args.append(f"tolerance=pd.Timedelta({_py(tolerance)})" if isinstance(tolerance, str)
                            else f"tolerance={tolerance}")
            lines.append(f"# as-of: most recent {right} row {direction} of each left timestamp")
            lines.append(f"frame = pd.merge_asof(frame, {var}, suffixes=('', '_right'), {', '.join(args)})")
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
        if len(lines) > before:
            lines.append(
                f"_ledger.append(({op!r}, _rows_before, len(frame)))"
            )
        else:
            lines.pop()
    return lines


_DERIVE_RUNTIME_TEMPLATE = '''
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


{EXPR_RUNTIME}


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


DERIVE_RUNTIME = _DERIVE_RUNTIME_TEMPLATE.replace(
    "{EXPR_RUNTIME}", RUNTIME_SOURCE.strip()
)


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
            # The engine counts rows with grouped.size(). "count" would skip nulls,
            # reporting 0 for a dropna=False group whose key is itself NaN.
            column = group_by[0] if group_by else None
            fn = "size" if group_by else fn
        else:
            column = m.get("column")
        # quantile needs its fraction, so the aggfunc carries it rather than a name.
        agg[alias] = (column, fn, float(m["q"])) if fn == "quantile" else (column, fn, None)

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
        "import json",
        "from pathlib import Path",
        "",
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
        "    text = str(path)",
        "    if text.endswith('.parquet'):",
        "        return pd.read_parquet(path)",
        "    if text.endswith(('.jsonl', '.ndjson')):",
        "        return pd.read_json(path, lines=True)",
        "    if text.endswith('.json') or not Path(text).suffix:",
        "        try:",
        "            raw = json.loads(Path(path).read_text(encoding='utf-8'))",
        "        except json.JSONDecodeError:",
        "            return pd.read_json(path, lines=True)",
        "        if isinstance(raw, list):",
        "            return pd.DataFrame(raw)",
        "        if isinstance(raw, dict):",
        "            if raw and all(isinstance(v, dict) for v in raw.values()):",
        "                return pd.DataFrame(list(raw.values()))",
        "            return pd.json_normalize(raw)",
        "        raise SystemExit(f'unsupported json shape for {dataset_id}')",
        "    return pd.read_csv(path)",
        "",
        "",
        f"frame = read_input({_py(spec.get('input_dataset_id'))})",
        "_ledger = []",
        "_source_rows = len(frame)",
    ]
    body += _transform_lines(spec.get("transforms") or [])
    if group_by and agg:
        pairs = ", ".join(
            f"{k}=pd.NamedAgg(column={_py(v[0])}, aggfunc=lambda s, _q={v[2]!r}: s.quantile(_q))"
            if v[1] == "quantile"
            else f"{k}=pd.NamedAgg(column={_py(v[0])}, aggfunc={_py(v[1])})"
            for k, v in agg.items()
            if k
        )
        body += ["", f"result = frame.groupby({_py(group_by)}, dropna=False).agg({pairs}).reset_index()"]
    elif agg:
        # Ungrouped: the engine aggregates the whole frame to a single row. Emitting
        # the frame here would hand a reviewer a different result than the desk got.
        cells = []
        for alias, (col, fn, q) in agg.items():
            if not alias:
                continue
            if fn == "count":
                expr = "frame.shape[0]"
            elif fn == "quantile":
                expr = f"frame[{_py(col)}].quantile({q!r})"
            else:
                expr = f"frame[{_py(col)}].{fn}()"
            cells.append(f"{_py(alias)}: [{expr}]")
        body += ["", f"result = pd.DataFrame({{{', '.join(cells)}}})"]
    else:
        body += ["", "result = frame"]
    body += [
        "",
        "print(result.head(20).to_string(index=False))",
        "print(f'{len(result)} rows')",
        "",
        "# What this run was computed over. The desk records the same ledger; a",
        "# result over a tenth of the source reads identically to one over all of",
        "# it unless the count is stated.",
        "print(f'source rows: {_source_rows}  aggregated over: {len(frame)}')",
        "for _step, (_op, _before, _after) in enumerate(_ledger, start=1):",
        "    if _before != _after:",
        "        print(f'  step {_step} {_op}: {_before} -> {_after} rows')",
        f"# result.to_parquet({_py(str(spec.get('output_dataset_id')) + '.parquet')})",
        "",
    ]
    return "\n".join(head + body)
