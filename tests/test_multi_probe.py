from pathlib import Path

import pandas as pd

from scripts.research_data_mcp.synthesis.multi_probe import probe_many


def _csv(tmp_path: Path, name: str, values: list[str]) -> Path:
    path = tmp_path / name
    pd.DataFrame({"entity_id": values, "value": range(len(values))}).to_csv(path, index=False)
    return path


def test_probe_many_measures_true_three_way_regions(tmp_path):
    a = _csv(tmp_path, "a.csv", ["a", "b", "c", "d"])
    b = _csv(tmp_path, "b.csv", ["b", "c", "e"])
    c = _csv(tmp_path, "c.csv", ["c", "d", "e", "f"])

    result = probe_many(
        [
            {"dataset_id": "a", "path": a},
            {"dataset_id": "b", "path": b},
            {"dataset_id": "c", "path": c},
        ],
        "entity_id",
        row_cap_per_source=100,
    )

    assert result["applicable"] is True
    assert result["bounded"] is False
    assert result["union_distinct"] == 6
    assert result["all_shared_distinct"] == 1  # c
    regions = {row["mask"]: row["count"] for row in result["intersections"]}
    assert regions == {
        0b001: 1,  # a
        0b011: 1,  # b
        0b111: 1,  # c
        0b101: 1,  # d
        0b110: 1,  # e
        0b100: 1,  # f
    }
    pair = {(row["left_index"], row["right_index"]): row for row in result["pairwise"]}
    assert pair[(0, 1)]["shared_distinct"] == 2
    assert pair[(0, 2)]["shared_distinct"] == 2
    assert pair[(1, 2)]["shared_distinct"] == 2


def test_probe_many_marks_bounded_receipt_when_cap_is_reached(tmp_path):
    a = _csv(tmp_path, "a.csv", [f"a{i}" for i in range(20)])
    b = _csv(tmp_path, "b.csv", [f"a{i}" for i in range(10, 30)])

    result = probe_many(
        [
            {"dataset_id": "a", "path": a},
            {"dataset_id": "b", "path": b},
        ],
        "entity_id",
        row_cap_per_source=10,
    )

    assert result["applicable"] is True
    assert result["bounded"] is True
    assert all(source["truncated"] for source in result["sources"])
    assert "Bounded" in result["note"]


def test_probe_many_refuses_more_than_eight_sources(tmp_path):
    path = _csv(tmp_path, "a.csv", ["x"])
    result = probe_many(
        [{"dataset_id": f"d{i}", "path": path} for i in range(9)],
        "entity_id",
    )
    assert result["applicable"] is False
    assert "limited to 8" in result["probe_error"]
