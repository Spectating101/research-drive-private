from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research_data_mcp.coverage_label_migration import MigrationError, main, migrate, normalize_labels


def registry(*rows: dict) -> dict:
    return {"version": "test", "datasets": list(rows)}


def test_exact_match_is_reversible_and_does_not_mutate_input() -> None:
    original = registry({"dataset_id": "asset-a", "name": "A"})
    result = migrate(
        original,
        [{
            "dataset_id": "asset-a",
            "coverage_metadata": {
                "unit": "firm_day",
                "geography": ["Taiwan"],
                "time_range": {"start": "2012", "end": "2026"},
            },
            "provenance": {"reviewed": True},
        }],
        source_sha256="abc",
    )
    assert "coverage_metadata" not in original["datasets"][0]
    row = result["candidate_registry"]["datasets"][0]
    assert row["coverage_metadata"]["universe/geography"] == ["Taiwan"]
    assert row["coverage_metadata"]["provenance"]["source_label_sha256"] == "abc"
    assert result["report"]["counts"] == {"changed": 1, "rejected_invalid": 0}
    assert result["forward_patch"][0]["before"] is None
    assert result["rollback_patch"][0]["after"] is None


def test_mapping_key_and_claim_list_formats_are_supported() -> None:
    labels, rejected = normalize_labels({
        "asset-a": {
            "claims": [
                {"dimension": "frequency", "value": "daily"},
                {"dimension": "fields", "value": ["price", "volume"]},
            ]
        }
    })
    assert rejected == []
    assert labels[0]["source_id"] == "asset-a"
    assert labels[0]["coverage"] == {"frequency": "daily", "fields": ["price", "volume"]}


def test_orphan_is_expected() -> None:
    result = migrate(
        registry({"dataset_id": "asset-a"}),
        [{"dataset_id": "retired-craft-probe", "unit": "event"}],
    )
    assert result["report"]["counts"] == {"orphaned": 1, "rejected_invalid": 0}
    assert result["forward_patch"] == []


def test_identical_coverage_is_already_present() -> None:
    result = migrate(
        registry({"dataset_id": "asset-a", "coverage_metadata": {"frequency": "daily"}}),
        [{"dataset_id": "asset-a", "frequency": "daily"}],
    )
    assert result["report"]["counts"] == {"already_present": 1, "rejected_invalid": 0}


def test_conflicting_coverage_is_not_overwritten() -> None:
    original = registry({"dataset_id": "asset-a", "coverage_metadata": {"frequency": "monthly"}})
    result = migrate(original, [{"dataset_id": "asset-a", "frequency": "daily"}])
    assert result["report"]["counts"] == {"conflict": 1, "rejected_invalid": 0}
    assert result["candidate_registry"] == original


def test_unique_alias_matches_and_ambiguous_alias_conflicts() -> None:
    matched = migrate(
        registry({"dataset_id": "asset-current", "legacy_ids": ["asset-old"]}),
        [{"dataset_id": "asset-old", "event_type": ["filing"]}],
    )
    assert matched["report"]["details"][0]["match_type"] == "alias_match"

    conflict = migrate(
        registry(
            {"dataset_id": "asset-a", "aliases": ["old"]},
            {"dataset_id": "asset-b", "aliases": ["old"]},
        ),
        [{"dataset_id": "old", "unit": "firm"}],
    )
    assert conflict["report"]["counts"] == {"conflict": 1, "rejected_invalid": 0}


def test_invalid_labels_are_rejected() -> None:
    result = migrate(
        registry({"dataset_id": "asset-a"}),
        [{"dataset_id": "asset-a", "unsupported": "x"}, {"unit": "firm_day"}],
    )
    assert result["report"]["counts"] == {"rejected_invalid": 2}


def test_selection_and_max_changes_bound_candidate() -> None:
    result = migrate(
        registry({"dataset_id": "a"}, {"dataset_id": "b"}, {"dataset_id": "c"}),
        [
            {"dataset_id": "a", "unit": "firm"},
            {"dataset_id": "b", "unit": "firm"},
            {"dataset_id": "c", "unit": "firm"},
        ],
        selected_ids={"a", "b"},
        max_changes=1,
    )
    assert result["report"]["counts"] == {
        "changed": 1,
        "change_deferred": 1,
        "not_selected": 1,
        "rejected_invalid": 0,
    }


def test_cli_refuses_in_place_registry_write(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    labels_path = tmp_path / "labels.json"
    report_path = tmp_path / "report.json"
    registry_path.write_text(json.dumps(registry({"dataset_id": "a"})), encoding="utf-8")
    labels_path.write_text(json.dumps([{"dataset_id": "a", "unit": "firm"}]), encoding="utf-8")
    with pytest.raises(MigrationError, match="refusing to overwrite input"):
        main([
            "--registry", str(registry_path),
            "--labels", str(labels_path),
            "--report", str(report_path),
            "--candidate", str(registry_path),
        ])
