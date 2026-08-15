"""An exported method must be runnable and must not overstate its own provenance."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from scripts.research_data_mcp.synthesis.spec_export import (
    fingerprint_path,
    render_script,
    spec_hash,
)


def _spec(**over):
    spec = {
        "input_dataset_id": "spine",
        "output_dataset_id": "synthesis_export_test_v1",
        "group_by": ["sector"],
        "metrics": [{"function": "count", "as": "n"}],
        "transforms": [],
    }
    spec.update(over)
    return spec


def test_spec_hash_is_canonical_and_order_independent():
    a = spec_hash({"b": 1, "a": 2})
    b = spec_hash({"a": 2, "b": 1})
    assert a == b and len(a) == 64


def test_fingerprint_reports_real_bytes(tmp_path):
    p = tmp_path / "x.parquet"
    pd.DataFrame({"ric": ["A"]}).to_parquet(p)
    fp = fingerprint_path(p)
    assert fp["fingerprint"].startswith("sha256:")
    assert fp["files"] == 1 and fp["bytes"] > 0


def test_missing_input_is_not_fingerprinted_and_says_why(tmp_path):
    fp = fingerprint_path(tmp_path / "absent.parquet")
    assert fp["fingerprint"] is None
    assert "does not exist" in fp["note"]


def test_script_flags_an_unfingerprinted_input(tmp_path):
    script = render_script(_spec(), {"spine": fingerprint_path(tmp_path / "gone.parquet")})
    assert "NOT FINGERPRINTED" in script


def test_script_carries_measured_join_evidence():
    probe = {"right_dataset_id": "attr", "key": "ric", "shared_distinct": 570, "coverage_right_pct": 100.0}
    script = render_script(_spec(), {}, probes=[probe])
    assert "570 shared keys" in script
    assert "100.0% of the joining side" in script


def test_unmeasured_join_is_reported_as_unmeasured():
    probe = {"right_dataset_id": "attr", "key": "ric", "probe_error": "path does not exist"}
    script = render_script(_spec(), {}, probes=[probe])
    assert "not measured" in script


def test_out_of_envelope_method_says_it_was_never_run():
    script = render_script(_spec(), {}, runnable_on_desk=False)
    assert "outside what the desk engine will execute" in script
    assert "was not run there" in script


def test_declared_collapse_renders_as_an_explicit_dedupe():
    spec = _spec(transforms=[{
        "op": "join", "right_dataset_id": "attr", "on": ["ric"],
        "how": "inner", "collapse": {"strategy": "first"},
    }])
    script = render_script(spec, {})
    assert 'drop_duplicates(subset=["ric"], keep="first")' in script
    assert "declared collapse" in script


def test_generated_script_actually_runs(tmp_path):
    spine = tmp_path / "spine.parquet"
    pd.DataFrame({"sector": ["A", "A", "B"], "v": [1, 2, 3]}).to_parquet(spine)
    script = render_script(_spec(), {"spine": fingerprint_path(spine)})
    path = tmp_path / "method.py"
    path.write_text(script, encoding="utf-8")
    out = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "2 rows" in out.stdout


def test_generated_join_script_runs_and_merges(tmp_path):
    spine = tmp_path / "spine.parquet"
    attr = tmp_path / "attr.parquet"
    pd.DataFrame({"ric": ["A", "B"], "sector": ["X", "Y"]}).to_parquet(spine)
    pd.DataFrame({"ric": ["A", "B"], "score": [10, 20]}).to_parquet(attr)
    spec = _spec(
        metrics=[{"function": "mean", "column": "score", "as": "mean_score"}],
        transforms=[{"op": "join", "right_dataset_id": "attr", "on": ["ric"], "how": "inner"}],
    )
    script = render_script(spec, {"spine": fingerprint_path(spine), "attr": fingerprint_path(attr)})
    path = tmp_path / "join_method.py"
    path.write_text(script, encoding="utf-8")
    out = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "2 rows" in out.stdout
