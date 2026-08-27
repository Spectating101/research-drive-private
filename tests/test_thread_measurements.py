import json
from pathlib import Path

import pandas as pd

from scripts.research_data_mcp.synthesis.thread_measurements import measure_thread


def _dataset(root: Path, dataset_id: str, keys: list[str]) -> dict:
    path = root / "data_lake" / f"{dataset_id}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"entity_id": keys, "value": range(len(keys))}).to_csv(path, index=False)
    return {"dataset_id": dataset_id, "local_path": str(path.relative_to(root))}


def _thread(ids: list[str]) -> dict:
    return {
        "id": "thread-real-measurements",
        "state": {
            "nodes": [
                {"id": f"n{i}", "type": "source", "layer": "evidence", "status": "held",
                 "dataset_id": dataset_id, "label": f"Dataset {i + 1}"}
                for i, dataset_id in enumerate(ids)
            ]
        },
    }


def test_measure_thread_reads_real_mapped_bytes_and_three_way_overlap(tmp_path):
    rows = [
        _dataset(tmp_path, "a", ["a", "b", "c", "d"]),
        _dataset(tmp_path, "b", ["b", "c", "e"]),
        _dataset(tmp_path, "c", ["c", "d", "e", "f"]),
    ]
    config = tmp_path / "config"
    config.mkdir()
    (config / "research_query_registry.json").write_text(json.dumps({"datasets": rows}), encoding="utf-8")

    result = measure_thread(tmp_path, _thread(["a", "b", "c"]), max_inputs=8)

    assert result["writes"] is False
    assert result["measurement_basis"] == "mapped_library_bytes"
    assert result["measured_inputs"] == 3
    assert result["unmeasured"] == []
    assert result["join_candidates"][0]["left_key"] == "entity_id"
    assert result["join_candidates"][0]["matched"] == 2
    assert result["multi_overlap"]["applicable"] is True
    assert result["multi_overlap"]["all_shared_distinct"] == 1
    assert result["multi_overlap"]["union_distinct"] == 6


def test_measure_thread_reports_unresolved_and_caps_inputs(tmp_path):
    datasets = [_dataset(tmp_path, f"d{i}", [f"k{i}"]) for i in range(9)]
    config = tmp_path / "config"
    config.mkdir()
    (config / "research_query_registry.json").write_text(json.dumps({"datasets": datasets}), encoding="utf-8")

    result = measure_thread(tmp_path, _thread([f"d{i}" for i in range(9)]), max_inputs=8)

    assert result["measured_inputs"] == 8
    assert result["truncated_inputs"] == 1
    assert result["max_inputs"] == 8
