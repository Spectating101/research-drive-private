from pathlib import Path

import pandas as pd

from scripts.research_data_mcp.http_router import ROUTE_CATALOG
from scripts.research_data_mcp.synthesis.measured_state import measured_state
from scripts.research_data_mcp.synthesis.multi_probe import probe_many


class FakeGateway:
    def __init__(self, root: Path, specs: dict[str, dict]):
        self.repo_root = root
        self._specs = specs

    def describe_dataset(self, dataset_id: str) -> dict:
        return self._specs[dataset_id]


def _dataset(root: Path, dataset_id: str, entity_ids: list[str], values=None) -> dict:
    path = root / "data" / f"{dataset_id}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    if values is None:
        values = list(range(len(entity_ids)))
    pd.DataFrame({"entity_id": entity_ids, "value": values}).to_csv(path, index=False)
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


def test_measurements_prefer_identity_key_over_coincidental_numeric_overlap(tmp_path):
    specs = {
        "left": _dataset(tmp_path, "left", ["a", "b", "c", "d"], [0, 1, 2, 3]),
        "right": _dataset(tmp_path, "right", ["b", "c", "e"], [0, 1, 2]),
    }
    result = measured_state(FakeGateway(tmp_path, specs), _nodes(["left", "right"]), max_inputs=8)

    assert result["measured_inputs"] == 2
    assert result["join_candidates"]
    assert [row["left_key"] for row in result["join_candidates"]] == ["entity_id"]
    assert result["join_candidates"][0]["matched"] == 2
    assert result["join_candidates"][0]["match_rate_pct"] == 50.0
    assert result["join_candidate_dataset_id"] == "right"
    assert result["join_candidate_rows"] == 3


def test_measurements_compute_true_three_source_exclusive_overlap(tmp_path):
    specs = {
        "a": _dataset(tmp_path, "a", ["a", "b", "c", "d"]),
        "b": _dataset(tmp_path, "b", ["b", "c", "e"]),
        "c": _dataset(tmp_path, "c", ["c", "d", "e", "f"]),
    }
    result = measured_state(FakeGateway(tmp_path, specs), _nodes(["a", "b", "c"]), max_inputs=8)
    overlap = result["multi_overlap"]

    assert result["measured_inputs"] == 3
    assert overlap["applicable"] is True
    assert overlap["bounded"] is False
    assert overlap["union_distinct"] == 6
    assert overlap["all_shared_distinct"] == 1
    regions = {row["mask"]: row["count"] for row in overlap["intersections"]}
    assert regions[7] == 1  # c is in A, B, and C
    assert regions[3] == 1  # b is A+B only
    assert regions[5] == 1  # d is A+C only
    assert regions[6] == 1  # e is B+C only
    assert regions[1] == 1  # a is A only
    assert regions[4] == 1  # f is C only


def test_measurements_support_eight_inputs_and_report_ninth_as_truncated(tmp_path):
    specs = {}
    ids = []
    for index in range(9):
        dataset_id = f"d{index}"
        ids.append(dataset_id)
        specs[dataset_id] = _dataset(tmp_path, dataset_id, ["shared", f"only-{index}"])

    result = measured_state(FakeGateway(tmp_path, specs), _nodes(ids), max_inputs=8)

    assert result["max_inputs"] == 8
    assert result["measured_inputs"] == 8
    assert result["truncated_inputs"] == 1
    assert result["multi_overlap"]["source_count"] == 8
    assert result["multi_overlap"]["all_shared_distinct"] == 1


def test_multi_probe_marks_bounded_window_without_impossible_cardinality(tmp_path):
    specs = {
        "a": _dataset(tmp_path, "a", ["a", "b", "c", "d", "e"]),
        "b": _dataset(tmp_path, "b", ["b", "c", "d", "e", "f"]),
        "c": _dataset(tmp_path, "c", ["c", "d", "e", "f", "g"]),
    }
    sources = [
        {"dataset_id": dataset_id, "label": dataset_id, "path": tmp_path / spec["local_path"]}
        for dataset_id, spec in specs.items()
    ]
    result = probe_many(sources, "entity_id", row_cap_per_source=3)

    assert result["bounded"] is True
    assert result["row_cap_per_source"] == 3
    assert all(source["rows_read"] == 3 for source in result["sources"])
    assert all(source["distinct"] <= source["rows_read"] for source in result["sources"])
    assert result["union_distinct"] >= max(source["distinct"] for source in result["sources"])


def test_measurement_http_route_precedes_greedy_thread_get():
    paths = [row["path"] for row in ROUTE_CATALOG]
    measurement = "/library/synthesis/threads/{thread_id}/measurements"
    catch_all = "/library/synthesis/threads/{thread_id}"

    assert measurement in paths
    assert paths.index(measurement) < paths.index(catch_all)
