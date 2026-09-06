from pathlib import Path

import pandas as pd

from scripts.research_data_mcp.synthesis.measured_state import measured_state


class FakeGateway:
    def __init__(self, root: Path, specs: dict[str, dict]):
        self.repo_root = root
        self._specs = specs

    def describe_dataset(self, dataset_id: str) -> dict:
        return self._specs[dataset_id]


def _dataset(root: Path, dataset_id: str, frame: pd.DataFrame) -> dict:
    path = root / "data" / f"{dataset_id}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return {"dataset_id": dataset_id, "local_path": str(path.relative_to(root))}


def test_join_candidates_carry_mapped_source_labels(tmp_path):
    specs = {
        "issuer_week_panel": _dataset(
            tmp_path,
            "issuer_week_panel",
            pd.DataFrame({"entity_id": ["a", "a", "b", "b"], "week": [1, 2, 1, 2]}),
        ),
        "market_week_panel": _dataset(
            tmp_path,
            "market_week_panel",
            pd.DataFrame({"entity_id": ["a", "a", "b", "b"], "week": [1, 3, 1, 3]}),
        ),
    }
    nodes = [
        {
            "id": "issuer-node",
            "dataset_id": "issuer_week_panel",
            "type": "source",
            "layer": "evidence",
            "label": "Issuer-week research panel",
        },
        {
            "id": "market-node",
            "dataset_id": "market_week_panel",
            "type": "source",
            "layer": "evidence",
            "label": "Weekly market evidence",
        },
    ]

    result = measured_state(FakeGateway(tmp_path, specs), nodes, max_inputs=8)
    candidate = result["join_candidates"][0]

    assert candidate["left_dataset_id"] == "issuer_week_panel"
    assert candidate["right_dataset_id"] == "market_week_panel"
    assert candidate["left_label"] == "Issuer-week research panel"
    assert candidate["right_label"] == "Weekly market evidence"
    assert candidate["key_parts"] == ["entity_id", "week"]
    assert candidate["match_rate_pct"] == 50.0
