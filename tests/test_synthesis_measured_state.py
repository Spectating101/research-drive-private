#!/usr/bin/env python3
"""Half the Synthesis method surface is measured, not reasoned.

column_profiles, unit_conflict and join_candidates are facts about held bytes.
The reasoning provider being down blocks the recommendation and the method; it
blocks none of these. The measurements already existed in data_profile.py with
no callers, so the panels rendered absence over data the desk could read.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.research_data_mcp.synthesis import measured_state as ms


class _Gateway:
    def __init__(self, repo_root, specs=None, raises=False):
        self.repo_root = repo_root
        self._specs = specs or {}
        self._raises = raises

    def describe_dataset(self, dataset_id):
        if self._raises:
            raise RuntimeError("registry down")
        return self._specs.get(dataset_id, {})


@pytest.fixture(autouse=True)
def _no_ambient_roots(monkeypatch):
    monkeypatch.delenv("RESEARCH_DATA_ROOTS", raising=False)


def _frame(tmp_path: Path, name: str) -> Path:
    pd = pytest.importorskip("pandas")
    path = tmp_path / "data_lake" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({
        "ticker": [f"T{i%7}" for i in range(60)],
        "return_1d": [0.0006 + i * 1e-6 for i in range(60)],
        "return_pct": [0.06 + i * 1e-4 for i in range(60)],
    }).to_parquet(path)
    return path


def test_no_mapped_evidence_says_so_rather_than_returning_empty_fields():
    out = ms.measured_state(_Gateway(Path(".")), [])
    assert out["column_profiles"] == []
    assert out["reason"] == "no mapped evidence to measure"


def test_none_of_this_needs_a_model():
    """The whole point: these fields are measurements, not reasoning."""
    out = ms.measured_state(_Gateway(Path(".")), [])
    assert out.get("needs_model") in (False, None)


def test_profiles_are_emitted_in_the_shape_the_contract_validates(tmp_path):
    _frame(tmp_path, "panel.parquet")
    gw = _Gateway(tmp_path, {"panel": {"local_path": "data_lake/panel.parquet"}})
    out = ms.measured_state(gw, [{"dataset_id": "panel"}])
    assert out["measured_inputs"] == 1
    assert out["column_profiles"], "a readable parquet must yield profiles"
    for row in out["column_profiles"]:
        for key in ("column", "kind", "rows", "blanks", "distinct", "flags"):
            assert key in row, f"contract requires {key}"
        assert isinstance(row["flags"], list)


def test_an_unreadable_input_is_named_with_its_reason_not_dropped(tmp_path):
    """A surface that silently profiles 3 of 5 inputs is worse than one that
    says which two it could not read."""
    gw = _Gateway(tmp_path, {"missing": {"local_path": "data_lake/nope.parquet"}})
    out = ms.measured_state(gw, [{"dataset_id": "missing"}])
    assert out["column_profiles"] == []
    assert out["unmeasured"][0]["dataset_id"] == "missing"
    assert out["unmeasured"][0]["reason"]


def test_a_registry_failure_is_reported_as_a_failure(tmp_path):
    gw = _Gateway(tmp_path, raises=True)
    out = ms.measured_state(gw, [{"dataset_id": "x"}])
    assert "registry read failed" in out["unmeasured"][0]["reason"]


def test_a_unit_conflict_reports_both_outcomes_and_recommends_neither():
    rows = [
        {"column": "return_1d", "kind": "measurement", "distinct": 60,
         "typical_magnitude": 0.0006, "flags": ["unit_twin"], "twin_of": "return_pct"},
        {"column": "return_pct", "kind": "measurement", "distinct": 60,
         "typical_magnitude": 0.06, "flags": ["unit_twin"], "twin_of": "return_1d"},
    ]
    conflict = ms.unit_conflict_from(rows)
    assert conflict["left"]["column"] == "return_1d"
    assert conflict["right"]["column"] == "return_pct"
    assert [o["id"] for o in conflict["outcomes"]] == ["as_is", "rescale"]
    assert not any(o["recommended"] for o in conflict["outcomes"]), (
        "the desk cannot tell which series is correct; choosing is how a plausible "
        "wrong number reaches a paper"
    )
    assert conflict["measured_ratio"] == 100.0


def test_no_twins_means_no_conflict_not_an_empty_one():
    rows = [{"column": "a", "kind": "measurement", "distinct": 9, "typical_magnitude": 1.0, "flags": []}]
    assert ms.unit_conflict_from(rows) is None


def test_a_twin_without_a_partner_row_is_not_a_conflict():
    rows = [{"column": "a", "kind": "measurement", "distinct": 9,
             "typical_magnitude": 1.0, "flags": ["unit_twin"], "twin_of": "gone"}]
    assert ms.unit_conflict_from(rows) is None


def test_joins_are_only_probed_when_both_sides_were_measured(tmp_path):
    """Probing a join against bytes we could not read would report a coverage
    number with nothing behind it."""
    _frame(tmp_path, "left.parquet")
    gw = _Gateway(tmp_path, {
        "left": {"local_path": "data_lake/left.parquet"},
        "right": {"local_path": "data_lake/absent.parquet"},
    })
    out = ms.measured_state(gw, [{"dataset_id": "left"}, {"dataset_id": "right"}])
    assert "join_candidates" not in out
    assert out["unmeasured"]
