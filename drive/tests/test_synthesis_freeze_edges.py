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
    assert candidates[0]["match_rate_pct"] == 50.0

    constant = next(row for row in candidates if row["key_parts"] == ["cusip"])
    assert constant["identity_capacity"] == 1
    assert constant["match_rate_pct"] == 100.0


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
