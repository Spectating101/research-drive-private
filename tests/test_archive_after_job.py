#!/usr/bin/env python3
"""GDrive archive path resolution after collection jobs."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_resolve_archive_file(tmp_path: Path) -> None:
    from scripts.research_data_mcp.archive_after_job import resolve_archive_target

    tick = tmp_path / "data_lake/sec/company_tickers.json"
    tick.parent.mkdir(parents=True)
    tick.write_text("{}", encoding="utf-8")
    path = resolve_archive_target(tmp_path, "data_lake/sec/company_tickers.json")
    assert path is not None
    assert path.name == "company_tickers.json"


def test_resolve_archive_glob_dir() -> None:
    from scripts.research_data_mcp.archive_after_job import resolve_archive_target

    path = resolve_archive_target(ROOT, "data_lake/sec/submissions/*.json")
    assert path is not None
    assert path.name == "submissions"


def test_remote_suffix_queue_task() -> None:
    from scripts.research_data_mcp.archive_after_job import remote_suffix_for_job

    assert remote_suffix_for_job(
        {"job_type": "collection_queue_task", "task_id": "sec_company_tickers"},
        "sec_company_tickers",
    ) == "collection/ops/collection-queue/sec_company_tickers"
