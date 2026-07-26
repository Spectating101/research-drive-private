#!/usr/bin/env python3
"""Canonical folder/asset membership — no fuzzy name guessing."""

from __future__ import annotations

from pathlib import Path

from scripts.research_data_mcp.asset_folder_membership import (
    asset_belongs_in_folder,
    resolve_asset_membership,
    stamp_asset_membership,
)


def test_explicit_partition_membership_is_canonical():
    partitions = [
        {
            "partition_id": "news.gdelt",
            "shelf_id": "news",
            "detail": {"registry_dataset_ids": ["gdelt_events_daily"]},
        },
        {
            "partition_id": "stocks.tw",
            "shelf_id": "stocks",
            "detail": {"registry_dataset_ids": []},
        },
    ]
    row = {"dataset_id": "gdelt_events_daily", "partition_id": "news.gdelt", "name": "GDELT"}
    mem = resolve_asset_membership(row, partitions=partitions)
    assert mem["partition_id"] == "news.gdelt"
    assert mem["shelf_id"] == "news"
    assert mem["folder_id"] == "news/news.gdelt"
    assert mem["membership_basis"] == "partition_id"
    assert mem["known"] is True
    assert asset_belongs_in_folder(mem, "news/news.gdelt") is True
    assert asset_belongs_in_folder(mem, "stocks/stocks.tw") is False
    assert asset_belongs_in_folder(mem, "stocks") is False


def test_registry_list_membership_without_guessing_names():
    partitions = [
        {
            "partition_id": "crypto.onchain",
            "shelf_id": "crypto",
            "detail": {"registry_dataset_ids": ["eth_stablecoin_flows"]},
        },
        {
            "partition_id": "empty.lane",
            "shelf_id": "news",
            "detail": {"registry_dataset_ids": []},
        },
    ]
    # Name contains "news" but must not join the empty news folder.
    row = {"dataset_id": "eth_stablecoin_flows", "name": "ETH news-adjacent flows"}
    mem = resolve_asset_membership(row, partitions=partitions)
    assert mem["folder_id"] == "crypto/crypto.onchain"
    assert mem["membership_basis"] == "registry_dataset_ids"
    assert asset_belongs_in_folder(mem, "news/empty.lane") is False
    assert asset_belongs_in_folder(mem, "news") is False


def test_unknown_membership_does_not_invent_folder():
    partitions = [
        {
            "partition_id": "news.gdelt",
            "shelf_id": "news",
            "detail": {"registry_dataset_ids": ["other_id"]},
        }
    ]
    row = {"dataset_id": "orphan_asset", "name": "GDELT lookalike", "local_root": "data_lake/news"}
    mem = resolve_asset_membership(row, partitions=partitions)
    assert mem["known"] is False
    assert mem["folder_id"] is None
    assert mem["membership_basis"] == "unknown"
    assert asset_belongs_in_folder(mem, "news/news.gdelt") is False
    assert asset_belongs_in_folder(mem, "") is False


def test_stamp_asset_membership_on_catalog_row():
    partitions = [
        {
            "partition_id": "panels.research",
            "shelf_id": "panels",
            "registry_dataset_ids": ["alpha_panel"],
        }
    ]
    stamped = stamp_asset_membership(
        {"dataset_id": "alpha_panel", "name": "Alpha"},
        partitions=partitions,
    )
    assert stamped["folder_id"] == "panels/panels.research"
    assert stamped["shelf_id"] == "panels"
    assert stamped["partition_id"] == "panels.research"
    assert stamped["membership"]["known"] is True


def test_professor_view_stamps_membership_from_partitions(tmp_path: Path, monkeypatch):
    from scripts.research_data_mcp.search import SearchService

    partitions = (
        {
            "partition_id": "news.gdelt",
            "shelf_id": "news",
            "registry_dataset_ids": ["gdelt_events_daily"],
            "detail": {
                "partition_id": "news.gdelt",
                "shelf_id": "news",
                "registry_dataset_ids": ["gdelt_events_daily"],
            },
        },
    )
    monkeypatch.setattr(
        "scripts.research_data_mcp.asset_folder_membership.load_partition_membership_index",
        lambda repo_root: partitions,
    )
    svc = object.__new__(SearchService)
    svc.repo_root = tmp_path
    row = svc._professor_view_row(
        {"dataset_id": "gdelt_events_daily", "partition_id": "news.gdelt", "name": "GDELT"}
    )
    assert row["folder_id"] == "news/news.gdelt"
    assert row["membership"]["membership_basis"] == "partition_id"
    assert row["membership"]["known"] is True
