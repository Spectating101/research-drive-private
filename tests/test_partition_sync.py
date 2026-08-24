"""Tests for partition → GDrive sync job planning."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def partitions_cfg() -> dict:
    return json.loads((REPO / "config/collection_partitions.json").read_text(encoding="utf-8"))


@pytest.fixture
def sync_cfg() -> dict:
    return json.loads((REPO / "config/partition_sync.json").read_text(encoding="utf-8"))


def test_build_sync_jobs_skips_cluster_jobs(partitions_cfg, sync_cfg):
    from scripts.ops.sync_collection_partitions_to_gdrive import build_sync_jobs

    jobs = build_sync_jobs(REPO, partitions_cfg, sync_cfg, include_large=False)
    ids = {j.job_id for j in jobs}
    assert "ops.cluster-jobs" not in ids
    assert "catalog.datacite-harvest" not in ids


def test_build_sync_jobs_includes_local_only_backfill(partitions_cfg, sync_cfg):
    from scripts.ops.sync_collection_partitions_to_gdrive import build_sync_jobs

    jobs = build_sync_jobs(REPO, partitions_cfg, sync_cfg, include_large=False)
    ids = {j.job_id for j in jobs}
    assert "markets.crypto-coingecko" in ids
    assert "markets.ethereum-usdt" in ids


def test_curated_index_excludes_harvest_shard_dir(partitions_cfg, sync_cfg):
    from scripts.ops.sync_collection_partitions_to_gdrive import build_sync_jobs

    jobs = build_sync_jobs(REPO, partitions_cfg, sync_cfg, include_large=False)
    curated = next(j for j in jobs if j.job_id == "catalog.curated-index")
    assert "index_v3/**" in curated.exclude_globs


def test_large_gdelt_skipped_without_flag(partitions_cfg, sync_cfg):
    from scripts.ops.sync_collection_partitions_to_gdrive import build_sync_jobs

    jobs = build_sync_jobs(REPO, partitions_cfg, sync_cfg, include_large=False)
    gdelt = next(j for j in jobs if j.job_id == "news.gdelt-asia")
    assert gdelt.skip_reason == "large_partition_skipped"

    jobs_all = build_sync_jobs(REPO, partitions_cfg, sync_cfg, include_large=True)
    gdelt2 = next(j for j in jobs_all if j.job_id == "news.gdelt-asia")
    assert not gdelt2.skip_reason


def test_remote_full_path_uses_collection_prefix():
    from scripts.ops.sync_collection_partitions_to_gdrive import remote_full_path

    remote = remote_full_path(REPO, "collection/markets/ethereum-usdt")
    assert remote.endswith("/collection/markets/ethereum-usdt")
    assert remote.startswith("gdrive:")
