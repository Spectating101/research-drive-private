from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research_data_mcp.registry_promotion import RegistryPromoter


def test_canonical_registry_rejects_non_drive_first_promotion(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config/yzu_cluster.json").write_text(
        json.dumps({"storage": {"drive_first": False}}),
        encoding="utf-8",
    )
    registry_path = tmp_path / "config/research_query_registry.json"
    original = {"updated_at": "before", "datasets": []}
    registry_path.write_text(json.dumps(original), encoding="utf-8")
    artifact = tmp_path / "data/example.json"
    artifact.parent.mkdir()
    artifact.write_text('{"ok": true}\n', encoding="utf-8")
    promoter = RegistryPromoter(tmp_path, registry_path)

    with pytest.raises(PermissionError, match="Drive-first verified storage"):
        promoter._upsert_dataset(
            {
                "dataset_id": "local_only_example",
                "name": "Local-only example",
                "backend": "local_json_file",
                "local_path": "data/example.json",
            },
            task_id="local_only_example",
            job_id="job-local-only",
        )

    assert json.loads(registry_path.read_text(encoding="utf-8")) == original
