"""Differential checks against the registry's real bytes.

These are the checks that justify trusting the engine, and they were throwaway
scripts in a temp directory. Each one computes an answer with the engine and the
same answer with an independently written pandas expression, over whatever data
is actually on this machine, and compares.

Marked slow: they need RESEARCH_DATA_ROOTS pointing at the real data roots and
take minutes. Excluded from the default run by addopts, so:

    pytest -m slow tests/test_registry_differential_slow.py

Skipped rather than failed when the data is not present, because absent data is
a fact about the machine, not a defect in the engine.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts.research_data_mcp.synthesis.dataset_paths import resolve_dataset_file
from scripts.research_data_mcp.synthesis.integrity_sweep import sweep
from scripts.research_data_mcp.synthesis.spec_export import fingerprint_path, render_script
from scripts.research_data_mcp.synthesis_executor import _read_frame, execute

pytestmark = pytest.mark.slow

REPO = Path(__file__).resolve().parent.parent
MIN_DATASETS = 20
MAX_ROWS = 300_000
METRICS = [{"function": "count", "as": "n"},
           {"function": "sum", "column": None, "as": "s"},
           {"function": "mean", "column": None, "as": "m"}]


def _registry() -> list[dict]:
    raw = json.loads((REPO / "drive/config/research_query_registry.json").read_text(encoding="utf-8"))
    return list((raw.get("datasets") if isinstance(raw, dict) else raw) or [])


@pytest.fixture(scope="module")
def frames() -> dict[str, pd.DataFrame]:
    loaded: dict[str, pd.DataFrame] = {}
    for row in _registry():
        path, _reason = resolve_dataset_file(REPO, row)
        if path is None:
            continue
        try:
            frame = _read_frame(path)
        except Exception:
            continue
        if isinstance(frame, pd.DataFrame) and 5 <= len(frame) <= MAX_ROWS:
            frame.columns = [str(c) for c in frame.columns]
            loaded[str(row.get("dataset_id"))] = frame
    if len(loaded) < MIN_DATASETS:
        pytest.skip(f"only {len(loaded)} datasets readable here; set RESEARCH_DATA_ROOTS")
    return loaded


def _metrics(column: str) -> list[dict]:
    return [{"function": "count", "as": "n"},
            {"function": "sum", "column": column, "as": "s"},
            {"function": "mean", "column": column, "as": "m"}]


def _groupable(frame: pd.DataFrame, limit: int = 400) -> list[str]:
    out = []
    for col in frame.columns:
        try:
            n = frame[col].nunique(dropna=False)
        except TypeError:
            continue
        if 2 <= n <= min(limit, max(2, len(frame) // 2)):
            out.append(col)
    return out


def _numeric(frame: pd.DataFrame, exclude: set[str]) -> list[str]:
    return [c for c in frame.columns
            if c not in exclude and pd.api.types.is_numeric_dtype(frame[c]) and frame[c].notna().any()]


def _run(tmp_path: Path, spec: dict, job: str) -> pd.DataFrame:
    execute(REPO, job, {"execution_spec": spec, "thread_id": "differential"})
    return pd.read_parquet(REPO / "data_lake/synthesis/thread_outputs/differential" / job / "output.parquet")


def _same(engine: pd.DataFrame, want: pd.DataFrame, keys: list[str]) -> list[str]:
    if len(engine) != len(want):
        return [f"groups engine={len(engine)} independent={len(want)}"]
    left = engine.sort_values(keys).reset_index(drop=True)
    right = want.sort_values(keys).reset_index(drop=True)
    bad = []
    for col in ("n", "s", "m"):
        a, b = left[col], right[col]
        if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
            close = ((a - b).abs() <= 1e-6 * (1 + b.abs())) | (a.isna() & b.isna())
            if not close.all():
                bad.append(f"{col} differs on {int((~close).sum())} of {len(a)} groups")
        elif not a.astype(str).equals(b.astype(str)):
            bad.append(f"{col} differs")
    return bad


def test_grouped_aggregates_match_an_independent_computation(frames, tmp_path):
    checked = rows = 0
    problems = []
    for n, (dataset_id, frame) in enumerate(sorted(frames.items())):
        keys = _groupable(frame)
        if not keys:
            continue
        nums = _numeric(frame, {keys[0]})
        if not nums:
            continue
        key, col = keys[0], nums[0]
        spec = {"input_dataset_id": dataset_id, "output_dataset_id": f"synthesis_diff_a{n:04d}",
                "group_by": [key], "metrics": _metrics(col)}
        try:
            engine = _run(tmp_path, spec, f"agg{n}")
        except Exception as exc:
            problems.append(f"{dataset_id}: engine raised {type(exc).__name__}: {exc}")
            continue
        grouped = frame.groupby(key, dropna=False)
        want = pd.DataFrame({"n": grouped.size(), "s": grouped[col].sum(),
                             "m": grouped[col].mean()}).reset_index()
        bad = _same(engine, want, [key])
        if bad:
            problems.append(f"{dataset_id} on {key}/{col}: {'; '.join(bad)}")
        checked += 1
        rows += len(frame)
    assert checked >= MIN_DATASETS, f"only {checked} datasets aggregated"
    assert not problems, f"{len(problems)} of {checked} disagreed:\n" + "\n".join(problems[:10])
    print(f"\n  {checked} datasets, {rows:,} rows aggregated, all matching")


def test_joins_match_an_independent_merge(frames, tmp_path):
    from collections import defaultdict

    by_col = defaultdict(list)
    for dataset_id, frame in frames.items():
        for col in frame.columns:
            by_col[col].append(dataset_id)

    def align(a, b):
        return (a.astype(str), b.astype(str)) if a.dtype.kind != b.dtype.kind else (a, b)

    pairs = []
    for key, ids in by_col.items():
        if not 2 <= len(ids) <= 30:
            continue
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                try:
                    ka, kb = align(frames[ids[i]][key], frames[ids[j]][key])
                    shared = len(set(ka.dropna().unique()) & set(kb.dropna().unique()))
                except Exception:
                    continue
                if shared >= 3:
                    pairs.append((shared, ids[i], ids[j], key))
    pairs.sort(key=lambda row: -row[0])
    if len(pairs) < 5:
        pytest.skip(f"only {len(pairs)} joinable pairs on this machine")

    checked = 0
    problems = []
    for n, (_shared, aid, bid, key) in enumerate(pairs[:40]):
        left, right = frames[aid], frames[bid]
        # A column only on the right proves right-hand data arrived, so prefer it;
        # a shared name still compares, against the left's values the engine keeps.
        numeric = [c for c in right.columns
                   if c != key and pd.api.types.is_numeric_dtype(right[c]) and right[c].notna().any()]
        if not numeric:
            continue
        unique = [c for c in numeric if c not in left.columns]
        col = (unique or numeric)[0]
        fans_out = bool(right[key].duplicated().any())
        step = {"op": "join", "right_dataset_id": bid, "on": [key], "how": "inner",
                "accept_row_loss": True}
        if fans_out:
            step["collapse"] = {"strategy": "first"}
        spec = {"input_dataset_id": aid, "output_dataset_id": f"synthesis_diff_j{n:04d}",
                "group_by": [key], "metrics": _metrics(col), "transforms": [step]}
        try:
            engine = _run(tmp_path, spec, f"join{n}")
        except Exception as exc:
            problems.append(f"{aid}+{bid}: engine raised {type(exc).__name__}: {exc}")
            continue
        r = right.drop_duplicates(subset=[key], keep="first") if fans_out else right.copy()
        l = left.copy()
        l[key], r[key] = align(l[key], r[key])
        merged = l.merge(r, on=[key], how="inner", suffixes=("", "_right"))
        grouped = merged.groupby(key, dropna=False)
        want = pd.DataFrame({"n": grouped.size(), "s": grouped[col].sum(),
                             "m": grouped[col].mean()}).reset_index()
        bad = _same(engine, want, [key])
        if bad:
            problems.append(f"{aid}+{bid} on {key}: {'; '.join(bad)}")
        checked += 1
    assert checked >= 5, f"only {checked} joins compared"
    assert not problems, f"{len(problems)} of {checked} disagreed:\n" + "\n".join(problems[:10])
    print(f"\n  {checked} join pairs compared, all matching")


def test_the_exported_script_reproduces_the_engine_on_real_joins(frames, tmp_path):
    """The earlier sweep reported 26/26 while never exporting a join, which is
    where both fidelity bugs were. Joins are the case that must be covered."""
    from collections import defaultdict

    paths = {}
    for row in _registry():
        path, _ = resolve_dataset_file(REPO, row)
        if path is not None:
            paths[str(row.get("dataset_id"))] = path

    by_col = defaultdict(list)
    for dataset_id, frame in frames.items():
        for col in frame.columns:
            by_col[col].append(dataset_id)

    candidates = []
    for key, ids in by_col.items():
        if not 2 <= len(ids) <= 30:
            continue
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = frames[ids[i]], frames[ids[j]]
                if (set(a.columns) & set(b.columns)) - {key}:
                    candidates.append((ids[i], ids[j], key))
    if len(candidates) < 3:
        pytest.skip("no colliding-column join pairs on this machine")

    checked = 0
    problems = []
    for n, (aid, bid, key) in enumerate(candidates[:12]):
        right = frames[bid]
        nums = [c for c in right.columns
                if c != key and pd.api.types.is_numeric_dtype(right[c]) and right[c].notna().any()]
        if not nums or aid not in paths or bid not in paths:
            continue
        step = {"op": "join", "right_dataset_id": bid, "on": [key], "how": "inner",
                "accept_row_loss": True}
        if right[key].duplicated().any():
            step["collapse"] = {"strategy": "first"}
        spec = {"input_dataset_id": aid, "output_dataset_id": f"synthesis_diff_x{n:04d}",
                "group_by": [key], "metrics": _metrics(nums[0]), "transforms": [step]}
        try:
            engine = _run(tmp_path, spec, f"exp{n}")
        except Exception:
            continue
        out = tmp_path / f"exported_{n}.parquet"
        script = tmp_path / f"exported_{n}.py"
        script.write_text(
            render_script(spec, {aid: fingerprint_path(paths[aid]), bid: fingerprint_path(paths[bid])})
            + f"\nresult.to_parquet({str(out)!r})\n", encoding="utf-8")
        done = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                              timeout=900, cwd=str(REPO))
        if not out.exists():
            tail = (done.stderr or done.stdout or "no output").strip().splitlines()
            problems.append(f"{aid}+{bid}: script failed: {tail[-1][:120] if tail else '?'}")
            continue
        bad = _same(engine, pd.read_parquet(out), [key])
        if bad:
            problems.append(f"{aid}+{bid}: {'; '.join(bad)}")
        checked += 1
    assert checked >= 3, f"only {checked} joins exported"
    assert not problems, f"{len(problems)} of {checked} diverged:\n" + "\n".join(problems[:10])
    print(f"\n  {checked} exported join scripts reproduce the engine")


def test_every_registered_dataset_is_openable_or_explained():
    """Not an assertion that all 168 are present — a record of what is broken.

    Absent data is a fact about the machine. A file that is present and
    unreadable is a defect, and this is what names it.
    """
    report = sweep(REPO)
    if report["counts"].get("readable", 0) < MIN_DATASETS:
        pytest.skip("registry data not present on this machine")
    broken = [f"{r['dataset_id']}: {r['status']} — {str(r['detail'])[:90]}" for r in report["corrupt"]]
    print(f"\n  {report['counts'].get('readable', 0)} readable, "
          f"{report['readable_rows']:,} rows, {len(broken)} broken")
    for line in broken:
        print(f"    {line}")
    assert report["counts"].get("readable", 0) >= MIN_DATASETS
