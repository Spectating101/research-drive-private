"""The catalog must be seedable from the registry the desk already holds.

The flywheel is reactive: promote_after_collect fires only when a collect job
completes and promotes a dataset. Anything acquired before auto-promotion
existed, or by a route that never ran as a job, is never enumerated. Measured
consequence: curated_live held 2 files and the curated_fts topic index held 0
rows over a registry of 163 datasets, so topic and category search were dead
while the data sat on disk. flywheel_backfill knows only the two pipelines in
procurement_registry_map.json, so it could not close the gap.
"""

from __future__ import annotations

import json

from scripts.research_data_mcp.flywheel_seed_registry import seed


def _repo(tmp_path, rows):
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "research_query_registry.json").write_text(
        json.dumps({"version": "t", "datasets": rows}), encoding="utf-8"
    )
    return tmp_path


def _row(did, **kw):
    base = {"dataset_id": did, "name": f"Name {did}", "professor_visible": True,
            "description": f"Description for {did}", "analysis_readiness": "instant"}
    base.update(kw)
    return base


def test_dry_run_writes_nothing(tmp_path):
    root = _repo(tmp_path, [_row("a"), _row("b")])
    out = seed(root, dry_run=True)
    assert out["curated_added"] == 2
    assert not (root / "data_lake/dataset_catalog/curated_live").exists()


def test_seeding_writes_one_row_per_visible_dataset(tmp_path):
    root = _repo(tmp_path, [_row("a"), _row("b")])
    out = seed(root)
    assert out["curated_added"] == 2
    jsonl = root / "data_lake/dataset_catalog/curated_live/curated_dataset_index.jsonl"
    assert len([l for l in jsonl.read_text().splitlines() if l.strip()]) == 2


def test_reseeding_converges_rather_than_duplicating(tmp_path):
    """Re-running must be safe; the catalog is append-only and keyed."""
    root = _repo(tmp_path, [_row("a"), _row("b")])
    seed(root)
    again = seed(root)
    assert again["curated_added"] == 0
    assert again["skipped_already_present"] == 2


def test_internal_rows_are_excluded_by_default(tmp_path):
    """The catalog is faculty-facing; ops rows would be noise in every search."""
    root = _repo(tmp_path, [_row("a"), _row("ops", professor_visible=False)])
    assert seed(root, dry_run=True)["considered"] == 1
    assert seed(root, dry_run=True, visible_only=False)["considered"] == 2


def test_untitled_rows_are_skipped_not_given_placeholders(tmp_path):
    """An unsearchable row that only raises the count is worse than none."""
    root = _repo(tmp_path, [_row("a"), {"dataset_id": "", "name": "", "professor_visible": True}])
    out = seed(root, dry_run=True)
    assert out["curated_added"] == 1
    assert out["skipped_no_title"] == 1
