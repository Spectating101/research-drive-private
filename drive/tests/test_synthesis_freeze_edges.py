from pathlib import Path

import pandas as pd

from scripts.research_data_mcp.synthesis.measured_state import measured_state
from scripts.research_data_mcp.synthesis import multi_probe as multi_probe_module
from scripts.research_data_mcp.synthesis import pair_probe as pair_probe_module


class FakeGateway:
    def __init__(self, root: Path, specs: dict[str, dict]):
        self.repo_root = root
        self._specs = specs

    def describe_dataset(self, dataset_id: str) -> dict:
        return self._specs[dataset_id]


def _frame_dataset(root: Path, dataset_id: str, frame: pd.DataFrame) -> dict:
    path = root / "data" / f"{dataset_id}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return {"dataset_id": dataset_id, "local_path": str(path.relative_to(root))}


def _nodes(ids: list[str]) -> list[dict]:
    return [
        {
            "id": f"node-{index}",
            "dataset_id": dataset_id,
            "type": "source",
            "layer": "evidence",
            "label": f"Dataset {index + 1}",
        }
        for index, dataset_id in enumerate(ids)
    ]


def test_pairwise_constant_identifier_does_not_beat_informative_entity_key(tmp_path):
    specs = {
        "left": _frame_dataset(
            tmp_path,
            "left",
            pd.DataFrame(
                {
                    "entity_id": ["a", "b", "c", "d"],
                    "cusip": ["same"] * 4,
                }
            ),
        ),
        "right": _frame_dataset(
            tmp_path,
            "right",
            pd.DataFrame(
                {
                    "entity_id": ["a", "b", "x", "y"],
                    "cusip": ["same"] * 4,
                }
            ),
        ),
    }

    result = measured_state(FakeGateway(tmp_path, specs), _nodes(["left", "right"]), max_inputs=8)
    candidates = result["join_candidates"]

    assert candidates[0]["key_parts"] == ["entity_id"]
    assert candidates[0]["identity_capacity"] == 4
    assert candidates[0]["degenerate_identity"] is False
    assert candidates[0]["match_rate_pct"] == 50.0

    constant = next(row for row in candidates if row["key_parts"] == ["cusip"])
    assert constant["identity_capacity"] == 1
    assert constant["degenerate_identity"] is True
    assert constant["match_rate_pct"] == 100.0


def test_pairwise_coverage_beats_capacity_once_both_identity_keys_are_non_degenerate(tmp_path):
    left_large = [f"a{i}" for i in range(100)]
    right_large = [*left_large[:10], *[f"x{i}" for i in range(90)]]
    left_good = [f"g{i}" for i in range(90)] + ["g0"] * 10
    right_good = [f"g{i}" for i in range(89)] + ["outside"] + ["g0"] * 10
    specs = {
        "left": _frame_dataset(
            tmp_path,
            "left",
            pd.DataFrame({"entity_id": left_large, "ticker": left_good}),
        ),
        "right": _frame_dataset(
            tmp_path,
            "right",
            pd.DataFrame({"entity_id": right_large, "ticker": right_good}),
        ),
    }

    result = measured_state(FakeGateway(tmp_path, specs), _nodes(["left", "right"]), max_inputs=8)
    candidates = result["join_candidates"]

    assert candidates[0]["key_parts"] == ["ticker"]
    assert candidates[0]["identity_capacity"] == 90
    assert candidates[0]["match_rate_pct"] == 98.9
    larger = next(row for row in candidates if row["key_parts"] == ["entity_id"])
    assert larger["identity_capacity"] == 100
    assert larger["match_rate_pct"] == 10.0


def test_measurement_only_columns_are_not_auto_promoted_to_join_keys(tmp_path):
    specs = {
        "left": _frame_dataset(
            tmp_path,
            "left",
            pd.DataFrame({"value": [100.1, 101.2, 102.3, 103.4, 104.5, 105.6, 106.7, 107.8, 108.9, 109.1, 110.2, 111.3, 112.4]}),
        ),
        "right": _frame_dataset(
            tmp_path,
            "right",
            pd.DataFrame({"value": [100.1, 101.2, 102.3, 200.4, 201.5, 202.6, 203.7, 204.8, 205.9, 206.1, 207.2, 208.3, 209.4]}),
        ),
    }

    result = measured_state(FakeGateway(tmp_path, specs), _nodes(["left", "right"]), max_inputs=8)

    assert result["join_candidates"] == []
    assert "no shared candidate key" in result["join_unmeasured_because"]


def test_shared_categorical_dimension_remains_a_safe_fallback_key(tmp_path):
    specs = {
        "left": _frame_dataset(
            tmp_path,
            "left",
            pd.DataFrame({"country": ["TW", "JP", "US", "ID"], "value": [1.1, 2.2, 3.3, 4.4]}),
        ),
        "right": _frame_dataset(
            tmp_path,
            "right",
            pd.DataFrame({"country": ["TW", "JP", "KR"], "value": [9.1, 9.2, 9.3]}),
        ),
    }

    result = measured_state(FakeGateway(tmp_path, specs), _nodes(["left", "right"]), max_inputs=8)

    assert [row["key_parts"] for row in result["join_candidates"]] == [["country"]]
    assert result["join_candidates"][0]["matched"] == 2
    assert result["join_candidates"][0]["match_rate_pct"] == 50.0


def test_multi_source_identifier_choice_uses_information_across_all_sources(tmp_path):
    specs = {
        "a": _frame_dataset(
            tmp_path,
            "a",
            pd.DataFrame({"entity_id": ["a", "b", "c"], "cusip": ["same"] * 3}),
        ),
        "b": _frame_dataset(
            tmp_path,
            "b",
            pd.DataFrame({"entity_id": ["a", "b", "d"], "cusip": ["same"] * 3}),
        ),
        "c": _frame_dataset(
            tmp_path,
            "c",
            pd.DataFrame({"entity_id": ["a", "e", "f"], "cusip": ["same"] * 3}),
        ),
    }

    result = measured_state(FakeGateway(tmp_path, specs), _nodes(["a", "b", "c"]), max_inputs=8)
    overlap = result["multi_overlap"]

    assert overlap["applicable"] is True
    assert overlap["key_parts"] == ["entity_id"]
    assert overlap["all_shared_distinct"] == 1
    assert overlap["union_distinct"] == 6


def test_multi_source_measurement_only_domain_is_reported_unmeasured(tmp_path):
    specs = {}
    for dataset_id, values in {
        "a": [1.1, 2.2, 3.3, 4.4, 5.5, 6.6, 7.7, 8.8, 9.9, 10.1, 11.2, 12.3, 13.4],
        "b": [1.1, 2.2, 20.3, 21.4, 22.5, 23.6, 24.7, 25.8, 26.9, 27.1, 28.2, 29.3, 30.4],
        "c": [1.1, 31.2, 32.3, 33.4, 34.5, 35.6, 36.7, 37.8, 38.9, 39.1, 40.2, 41.3, 42.4],
    }.items():
        specs[dataset_id] = _frame_dataset(tmp_path, dataset_id, pd.DataFrame({"value": values}))

    result = measured_state(FakeGateway(tmp_path, specs), _nodes(["a", "b", "c"]), max_inputs=8)

    assert result["multi_overlap"]["applicable"] is False
    assert "no safe common key" in result["multi_overlap"]["probe_error"]


def test_pair_probe_fails_closed_when_reader_returns_partial_values_plus_error(monkeypatch):
    calls = 0

    def partial_read(_path, _keys, _cap):
        nonlocal calls
        calls += 1
        return [f"partial-{calls}"], "broken-part.csv: parse failure"

    monkeypatch.setattr(pair_probe_module, "_read_key_column", partial_read)
    result = pair_probe_module.probe_pair("left", "right", "entity_id")

    assert result["probe_error"].startswith("left:")
    assert result["shared_distinct"] == 0
    assert result["coverage_left_pct"] is None


def test_multi_probe_fails_closed_when_any_source_read_is_partial(monkeypatch):
    def partial_read(_path, _keys, _cap):
        return [("a",), ("b",)], "broken-part.csv: parse failure"

    monkeypatch.setattr(multi_probe_module, "_read_key_column", partial_read)
    result = multi_probe_module.probe_many(
        [
            {"dataset_id": "a", "label": "A", "path": "a.csv"},
            {"dataset_id": "b", "label": "B", "path": "b.csv"},
            {"dataset_id": "c", "label": "C", "path": "c.csv"},
        ],
        "entity_id",
    )

    assert result["applicable"] is False
    assert "parse failure" in result["probe_error"]
    assert result["intersections"] == []
    assert result["union_distinct"] == 0


def test_bounded_overlap_is_called_a_window_not_a_representative_sample(tmp_path):
    sources = []
    for index, keys in enumerate((["a", "b", "c"], ["b", "c", "d"], ["c", "d", "e"])):
        dataset_id = f"d{index}"
        spec = _frame_dataset(tmp_path, dataset_id, pd.DataFrame({"entity_id": keys}))
        sources.append(
            {
                "dataset_id": dataset_id,
                "label": dataset_id,
                "path": tmp_path / spec["local_path"],
            }
        )

    result = multi_probe_module.probe_many(sources, "entity_id", row_cap_per_source=2)

    assert result["bounded"] is True
    assert "window" in result["note"].lower()
    assert "not a representative sample" in result["note"].lower()


def test_composite_probe_excludes_rows_missing_any_key_part(tmp_path):
    left = tmp_path / "left.csv"
    right = tmp_path / "right.csv"
    pd.DataFrame(
        {
            "entity_id": ["a", None, "b"],
            "week": [1, 1, None],
        }
    ).to_csv(left, index=False)
    pd.DataFrame(
        {
            "entity_id": ["a", None, "c"],
            "week": [1, 1, None],
        }
    ).to_csv(right, index=False)

    result = pair_probe_module.probe_pair(left, right, ["entity_id", "week"])

    assert result["probe_error"] is None
    assert result["left_rows"] == 1
    assert result["right_rows"] == 1
    assert result["shared_distinct"] == 1
    assert result["coverage_left_pct"] == 100.0
