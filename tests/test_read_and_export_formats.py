"""Every format the engine reads, the exported script must read the same way.

Found by aggregating the registry's real bytes: two datasets are .jsonl, which
the engine parsed with json.load and the exported script with read_csv. A third
gap only shows on a NaN group key, where the engine counts rows with size() and
the script counted a column with count(), reporting 0 observations for a group
the desk had shown as 2.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts.research_data_mcp.synthesis_executor import _read_frame, execute
from scripts.research_data_mcp.synthesis.spec_export import fingerprint_path, render_script

FRAME = pd.DataFrame({"k": ["a", "a", None, None, "b"], "v": [1.0, 2.0, 3.0, 4.0, 5.0]})

WRITERS = {
    ".parquet": lambda d, p: d.to_parquet(p),
    ".csv": lambda d, p: d.to_csv(p, index=False),
    ".jsonl": lambda d, p: d.to_json(p, orient="records", lines=True),
    ".json": lambda d, p: d.to_json(p, orient="records"),
}


def _repo(tmp_path: Path, suffix: str) -> tuple[Path, Path]:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    rel = f"data/t{suffix}"
    WRITERS[suffix](FRAME, tmp_path / rel)
    (tmp_path / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": [{"dataset_id": "probe", "name": "n",
                                  "local_path": rel, "grain": "row"}]}),
        encoding="utf-8")
    return tmp_path, tmp_path / rel


SPEC = {
    "input_dataset_id": "probe",
    "output_dataset_id": "synthesis_fidelity_probe",
    "group_by": ["k"],
    "metrics": [{"function": "count", "as": "n"}, {"function": "sum", "column": "v", "as": "s"}],
}


@pytest.mark.parametrize("suffix", sorted(WRITERS))
def test_the_engine_reads_every_registry_format(tmp_path, suffix):
    _, path = _repo(tmp_path, suffix)
    frame = _read_frame(path)
    assert len(frame) == 5
    assert set(frame.columns) == {"k", "v"}


def test_line_delimited_json_named_json_is_not_a_hard_failure(tmp_path):
    (tmp_path / "d").mkdir()
    path = tmp_path / "d/rows.json"
    FRAME.to_json(path, orient="records", lines=True)
    assert len(_read_frame(path)) == 5


def test_an_extensionless_line_delimited_file_reads(tmp_path):
    (tmp_path / "d").mkdir()
    path = tmp_path / "d/rows"
    FRAME.to_json(path, orient="records", lines=True)
    assert len(_read_frame(path)) == 5


@pytest.mark.parametrize("suffix", sorted(WRITERS))
def test_the_exported_script_reproduces_the_engine(tmp_path, suffix):
    repo, path = _repo(tmp_path, suffix)
    execute(repo, "job", {"execution_spec": SPEC, "thread_id": "t"})
    engine = pd.read_parquet(repo / "data_lake/synthesis/thread_outputs/t/job/output.parquet")

    out = tmp_path / "exported.parquet"
    script = tmp_path / "exported.py"
    script.write_text(
        render_script(SPEC, {"probe": fingerprint_path(path)})
        + f"\nresult.to_parquet({str(out)!r})\n",
        encoding="utf-8")
    done = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-400:]

    exported = pd.read_parquet(out)
    left = engine.sort_values("k", na_position="last").reset_index(drop=True)
    right = exported.sort_values("k", na_position="last").reset_index(drop=True)
    pd.testing.assert_frame_equal(left, right, check_dtype=False)


def test_a_null_group_key_counts_rows_not_non_null_values(tmp_path):
    repo, path = _repo(tmp_path, ".parquet")
    execute(repo, "job", {"execution_spec": SPEC, "thread_id": "t"})
    engine = pd.read_parquet(repo / "data_lake/synthesis/thread_outputs/t/job/output.parquet")
    null_row = engine[engine["k"].isna()]
    assert len(null_row) == 1
    assert int(null_row["n"].iloc[0]) == 2

    out = tmp_path / "exported.parquet"
    script = tmp_path / "exported.py"
    script.write_text(
        render_script(SPEC, {"probe": fingerprint_path(path)})
        + f"\nresult.to_parquet({str(out)!r})\n",
        encoding="utf-8")
    subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=300, check=True)
    exported = pd.read_parquet(out)
    assert int(exported[exported["k"].isna()]["n"].iloc[0]) == 2


def test_an_ungrouped_count_still_counts(tmp_path):
    repo, path = _repo(tmp_path, ".parquet")
    spec = dict(SPEC, group_by=[], output_dataset_id="synthesis_fidelity_ungrouped")
    execute(repo, "job2", {"execution_spec": spec, "thread_id": "t"})
    engine = pd.read_parquet(repo / "data_lake/synthesis/thread_outputs/t/job2/output.parquet")
    assert int(engine["n"].iloc[0]) == 5
