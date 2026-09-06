from pathlib import Path

import pandas as pd

from scripts.research_data_mcp import http_router
from scripts.research_data_mcp.synthesis.measured_state import measured_state
from scripts.research_data_mcp.synthesis.multi_probe import probe_many
from scripts.research_data_mcp.synthesis.pair_probe import _read_key_column


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


def _dataset(root: Path, dataset_id: str, entity_ids: list[str], values=None) -> dict:
    if values is None:
        values = list(range(len(entity_ids)))
    return _frame_dataset(
        root,
        dataset_id,
        pd.DataFrame({"entity_id": entity_ids, "value": values}),
    )


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


def test_measurements_preserve_entity_period_grain_before_partial_identity(tmp_path):
    specs = {
        "left": _frame_dataset(
            tmp_path,
            "left",
            pd.DataFrame(
                {
                    "entity_id": ["a", "a", "b", "b"],
                    "week": [1, 2, 1, 2],
                    "signal": [10, 11, 12, 13],
                }
            ),
        ),
        "right": _frame_dataset(
            tmp_path,
            "right",
            pd.DataFrame(
                {
                    "entity_id": ["a", "a", "b", "b"],
                    "week": [1, 3, 1, 3],
                    "signal": [20, 21, 22, 23],
                }
            ),
        ),
    }
    result = measured_state(FakeGateway(tmp_path, specs), _nodes(["left", "right"]), max_inputs=8)
    candidates = result["join_candidates"]

    assert candidates[0]["key_parts"] == ["entity_id", "week"]
    assert candidates[0]["complete_identity_domain"] is True
    assert candidates[0]["left_key"] == "entity_id + week"
    assert candidates[0]["matched"] == 2
    assert candidates[0]["match_rate_pct"] == 50.0

    entity_only = next(row for row in candidates if row["key_parts"] == ["entity_id"])
    assert entity_only["match_rate_pct"] == 100.0
    assert entity_only["complete_identity_domain"] is False


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


def test_multi_source_overlap_preserves_common_entity_period_grain(tmp_path):
    specs = {
        "a": _frame_dataset(
            tmp_path,
            "a",
            pd.DataFrame({"entity_id": ["a", "a", "b"], "week": [1, 2, 1]}),
        ),
        "b": _frame_dataset(
            tmp_path,
            "b",
            pd.DataFrame({"entity_id": ["a", "a", "b"], "week": [1, 3, 1]}),
        ),
        "c": _frame_dataset(
            tmp_path,
            "c",
            pd.DataFrame({"entity_id": ["a", "a", "b"], "week": [1, 4, 2]}),
        ),
    }
    result = measured_state(FakeGateway(tmp_path, specs), _nodes(["a", "b", "c"]), max_inputs=8)
    overlap = result["multi_overlap"]

    assert overlap["key_parts"] == ["entity_id", "week"]
    assert overlap["all_shared_distinct"] == 1
    assert overlap["union_distinct"] == 6


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


def test_duplicate_mapped_dataset_does_not_become_fake_multi_source_overlap(tmp_path):
    spec = _dataset(tmp_path, "same", ["a", "b", "c"])
    result = measured_state(
        FakeGateway(tmp_path, {"same": spec}),
        _nodes(["same", "same", "same"]),
        max_inputs=8,
    )

    assert result["measured_inputs"] == 1
    assert result["truncated_inputs"] == 0
    assert len(result["input_measurements"]) == 1
    assert result["multi_overlap"] is None


def test_csv_key_reader_projects_and_streams_in_bounded_chunks(tmp_path, monkeypatch):
    spec = _dataset(tmp_path, "chunked", [f"k{i}" for i in range(20)])
    path = tmp_path / spec["local_path"]
    real_read_csv = pd.read_csv
    calls = []

    def tracked_read_csv(*args, **kwargs):
        calls.append(dict(kwargs))
        return real_read_csv(*args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", tracked_read_csv)
    values, error = _read_key_column(path, ["entity_id"], 3)

    assert error is None
    assert len(values) == 3
    assert any(call.get("nrows") == 0 for call in calls)
    streamed = [call for call in calls if call.get("chunksize")]
    assert streamed
    assert streamed[0]["usecols"] == ["entity_id"]
    assert streamed[0]["chunksize"] == 3


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
    measurement = "/library/synthesis/threads/{thread_id}/measurements"
    catch_all = "/library/synthesis/threads/{thread_id}"
    get_routes = [
        row["path"]
        for row in http_router.ROUTE_CATALOG
        if row.get("method") == "GET"
    ]

    assert measurement in get_routes
    assert catch_all in get_routes
    assert get_routes.index(measurement) < get_routes.index(catch_all)
