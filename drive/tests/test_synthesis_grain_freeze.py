from pathlib import Path

import pandas as pd

from scripts.research_data_mcp.synthesis.measured_state import measured_state


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


def test_incidental_year_does_not_redefine_static_entity_join(tmp_path):
    specs = {
        "left": _frame_dataset(
            tmp_path,
            "left",
            pd.DataFrame(
                {
                    "entity_id": ["a", "b", "c", "d"],
                    "report_year": [2021, 2022, 2023, 2024],
                }
            ),
        ),
        "right": _frame_dataset(
            tmp_path,
            "right",
            pd.DataFrame(
                {
                    "entity_id": ["a", "b", "x", "y"],
                    "report_year": [2021, 2022, 2023, 2024],
                }
            ),
        ),
    }

    result = measured_state(FakeGateway(tmp_path, specs), _nodes(["left", "right"]), max_inputs=8)
    candidates = result["join_candidates"]

    assert candidates[0]["key_parts"] == ["entity_id"]
    assert candidates[0]["entity_identity_domain"] is True
    assert candidates[0]["match_rate_pct"] == 50.0
    assert all(row["key_parts"] != ["entity_id", "report_year"] for row in candidates)

    year = next(row for row in candidates if row["key_parts"] == ["report_year"])
    assert year["entity_identity_domain"] is False
    assert year["match_rate_pct"] == 100.0


def test_one_static_side_blocks_automatic_panel_composite(tmp_path):
    specs = {
        "panel": _frame_dataset(
            tmp_path,
            "panel",
            pd.DataFrame(
                {
                    "entity_id": ["a", "a", "b", "b"],
                    "week": [1, 2, 1, 2],
                }
            ),
        ),
        "static": _frame_dataset(
            tmp_path,
            "static",
            pd.DataFrame(
                {
                    "entity_id": ["a", "b", "c"],
                    "week": [1, 1, 1],
                }
            ),
        ),
    }

    result = measured_state(FakeGateway(tmp_path, specs), _nodes(["panel", "static"]), max_inputs=8)
    candidates = result["join_candidates"]

    assert candidates[0]["key_parts"] == ["entity_id"]
    assert all(row["key_parts"] != ["entity_id", "week"] for row in candidates)


def test_one_static_source_blocks_multi_source_panel_composite(tmp_path):
    specs = {
        "panel_a": _frame_dataset(
            tmp_path,
            "panel_a",
            pd.DataFrame({"entity_id": ["a", "a", "b"], "week": [1, 2, 1]}),
        ),
        "panel_b": _frame_dataset(
            tmp_path,
            "panel_b",
            pd.DataFrame({"entity_id": ["a", "a", "b"], "week": [1, 3, 1]}),
        ),
        "static": _frame_dataset(
            tmp_path,
            "static",
            pd.DataFrame({"entity_id": ["a", "b", "c"], "week": [1, 1, 1]}),
        ),
    }

    result = measured_state(
        FakeGateway(tmp_path, specs),
        _nodes(["panel_a", "panel_b", "static"]),
        max_inputs=8,
    )
    overlap = result["multi_overlap"]

    assert overlap["applicable"] is True
    assert overlap["key_parts"] == ["entity_id"]
    assert overlap["all_shared_distinct"] == 2
