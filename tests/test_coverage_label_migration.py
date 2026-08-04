from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research_data_mcp.coverage_label_migration import MigrationError, _json_sha256, main, migrate, normalize_labels


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
    assert result["report"]["input_registry_sha256"] != result["report"]["candidate_registry_sha256"]
    assert result["forward_patch"][0]["before"] is None
    assert result["rollback_patch"][0]["after"] is None


def test_mapping_key_claim_list_and_claim_per_record_formats_are_supported() -> None:
    labels, rejected = normalize_labels({
        "labels": [
            {"dataset_id": "asset-a", "dimension": "frequency", "value": "daily"},
            {
                "dataset_id": "asset-a",
                "claims": [{"dimension": "fields", "value": ["price", "volume"]}],
            },
        ]
    })
    assert rejected == []
    assert len(labels) == 1
    assert labels[0]["source_id"] == "asset-a"
    assert labels[0]["coverage"] == {"frequency": "daily", "fields": ["price", "volume"]}
    assert labels[0]["source_record_indices"] == [0, 1]


def test_duplicate_dataset_disagreement_is_rejected_before_migration() -> None:
    labels, rejected = normalize_labels([
        {"dataset_id": "asset-a", "frequency": "daily"},
        {"dataset_id": "asset-a", "frequency": "monthly"},
    ])
    assert labels == []
    assert rejected[0]["dataset_id"] == "asset-a"
    assert rejected[0]["reasons"] == ["duplicate records disagree on coverage"]


def test_any_invalid_record_blocks_partial_dataset_migration() -> None:
    labels, rejected = normalize_labels([
        {"dataset_id": "asset-a", "frequency": "daily"},
        {"dataset_id": "asset-a", "dimension": "frequency"},
    ])
    assert labels == []
    assert rejected[0]["dataset_id"] == "asset-a"


def test_orphan_is_expected() -> None:
    result = migrate(
        registry({"dataset_id": "asset-a"}),
        [{"dataset_id": "retired-craft-probe", "unit": "event"}],
    )
    assert result["report"]["counts"] == {"orphaned": 1, "rejected_invalid": 0}
    assert result["forward_patch"] == []


def test_identical_coverage_is_already_present_across_noncanonical_surface() -> None:
    result = migrate(
        registry({"dataset_id": "asset-a", "evidence_coverage": {"frequency": "daily"}}),
        [{"dataset_id": "asset-a", "frequency": "daily"}],
    )
    assert result["report"]["counts"] == {"already_present": 1, "rejected_invalid": 0}


def test_conflicting_coverage_on_any_explicit_surface_is_not_overwritten() -> None:
    original = registry({"dataset_id": "asset-a", "dimensions": {"frequency": "monthly"}})
    result = migrate(original, [{"dataset_id": "asset-a", "frequency": "daily"}])
    assert result["report"]["counts"] == {"conflict": 1, "rejected_invalid": 0}
    assert result["candidate_registry"] == original


def test_preexisting_cross_surface_conflict_blocks_migration() -> None:
    original = registry({
        "dataset_id": "asset-a",
        "coverage_metadata": {"frequency": "daily"},
        "frequency": "monthly",
    })
    result = migrate(original, [{"dataset_id": "asset-a", "fields": ["price"]}])
    detail = result["report"]["details"][0]
    assert detail["classification"] == "conflict"
    assert "already contains contradictory" in detail["reason"]
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


def test_selection_and_max_changes_bound_datasets_not_claim_rows() -> None:
    result = migrate(
        registry({"dataset_id": "a"}, {"dataset_id": "b"}, {"dataset_id": "c"}),
        [
            {"dataset_id": "a", "dimension": "unit", "value": "firm"},
            {"dataset_id": "a", "dimension": "frequency", "value": "daily"},
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
    assert result["report"]["normalized_dataset_label_count"] == 3
    assert result["report"]["input_label_record_count"] == 4


def test_unchanged_candidate_has_equal_fingerprints() -> None:
    result = migrate(
        registry({"dataset_id": "asset-a", "frequency": "daily"}),
        [{"dataset_id": "asset-a", "frequency": "daily"}],
    )
    assert result["report"]["input_registry_sha256"] == result["report"]["candidate_registry_sha256"]
    assert result["report"]["registry_changed"] is False


def test_semantically_equivalent_claim_order_and_case_are_not_conflicts() -> None:
    result = migrate(
        registry({
            "dataset_id": "asset-a",
            "evidence_coverage": {
                "fields": ["Volume", "Price"],
                "geography": ["Taiwan", "Japan"],
            },
        }),
        [{
            "dataset_id": "asset-a",
            "fields": ["price", "volume"],
            "universe/geography": ["japan", "taiwan"],
        }],
    )
    assert result["report"]["counts"] == {"already_present": 1, "rejected_invalid": 0}


def test_registry_fingerprint_preserves_empty_structural_drift() -> None:
    assert _json_sha256({"datasets": [], "note": ""}) != _json_sha256({"datasets": []})


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


def test_cli_refuses_output_path_collisions(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    labels_path = tmp_path / "labels.json"
    output_path = tmp_path / "same.json"
    registry_path.write_text(json.dumps(registry({"dataset_id": "a"})), encoding="utf-8")
    labels_path.write_text(json.dumps([{"dataset_id": "a", "unit": "firm"}]), encoding="utf-8")
    with pytest.raises(MigrationError, match="output paths must be unique"):
        main([
            "--registry", str(registry_path),
            "--labels", str(labels_path),
            "--report", str(output_path),
            "--candidate", str(output_path),
        ])
