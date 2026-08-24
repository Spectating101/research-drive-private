"""A registered dataset whose bytes are present but unlinked reports
local_bytes_missing, which reads like an acquisition problem when it is a broken
link. The repair must be reproducible and must never invent or overwrite a path.
"""

import json

import pytest

from scripts.research_data_mcp.registry_relink import apply, locate, plan


@pytest.fixture
def backfill(tmp_path):
    d = tmp_path / "data_lake/refinitiv_backfill/2026-07-06-complete/processed"
    d.mkdir(parents=True)
    (d / "esg_snapshot.parquet").write_bytes(b"x")
    (d / "refinitiv_security_master.parquet").write_bytes(b"x")
    return tmp_path


def _registry(rows):
    return {"datasets": rows}


def test_finds_a_file_that_drops_the_prefix(backfill):
    assert locate(backfill, "refinitiv_esg_snapshot").endswith("esg_snapshot.parquet")


def test_finds_a_file_that_keeps_the_prefix(backfill):
    assert locate(backfill, "refinitiv_security_master").endswith("refinitiv_security_master.parquet")


def test_reports_nothing_for_a_dataset_with_no_file(backfill):
    assert locate(backfill, "refinitiv_risk_tape_daily") is None


def test_never_touches_a_row_that_already_has_a_path(backfill):
    reg = _registry([{"dataset_id": "refinitiv_esg_snapshot", "local_path": "somewhere/else.parquet"}])
    assert plan(reg, backfill) == []


def test_only_offers_rows_whose_bytes_exist(backfill):
    reg = _registry([
        {"dataset_id": "refinitiv_esg_snapshot"},
        {"dataset_id": "refinitiv_risk_tape_daily"},
    ])
    got = [d for d, _ in plan(reg, backfill)]
    assert got == ["refinitiv_esg_snapshot"]


def test_apply_writes_only_the_planned_links(backfill):
    reg = _registry([
        {"dataset_id": "refinitiv_esg_snapshot"},
        {"dataset_id": "refinitiv_risk_tape_daily"},
    ])
    changed = apply(reg, plan(reg, backfill))
    assert changed == 1
    rows = {r["dataset_id"]: r for r in reg["datasets"]}
    assert rows["refinitiv_esg_snapshot"]["local_path"].endswith("esg_snapshot.parquet")
    assert "local_path" not in rows["refinitiv_risk_tape_daily"]


def test_running_twice_changes_nothing_the_second_time(backfill):
    reg = _registry([{"dataset_id": "refinitiv_esg_snapshot"}])
    assert apply(reg, plan(reg, backfill)) == 1
    assert plan(reg, backfill) == []
    assert apply(reg, plan(reg, backfill)) == 0


def test_a_dataset_outside_the_backfill_is_ignored(backfill):
    reg = _registry([{"dataset_id": "gdelt_asia_daily_country_panel"}])
    assert plan(reg, backfill) == []
