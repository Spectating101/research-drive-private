"""Drive-first finalize helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_is_drive_first_enabled():
    from scripts.research_data_mcp.drive_first import is_drive_first

    assert is_drive_first(REPO) is True


def test_remote_suffix_uses_partition_wiring():
    from scripts.research_data_mcp.drive_first import remote_suffix_for_collect

    suffix = remote_suffix_for_collect(
        REPO,
        {"partition_id": "official.mops-disclosures"},
        dataset_id="procured_abc",
        job_id="job1",
    )
    assert suffix == "collection/official/mops-disclosures/procured_abc"


def test_finalize_skips_when_no_targets(tmp_path):
    from scripts.research_data_mcp.drive_first import finalize_job_to_drive

    out = finalize_job_to_drive(
        tmp_path,
        job_id="x",
        plan={"job_type": "source_probe"},
        result={},
        promoted=[],
        materialized={},
    )
    assert out.get("ok") is True
    assert out.get("skipped") is True
