#!/usr/bin/env python3
"""Cluster ops routing when windows_lab is not provisioned."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def cfg() -> dict:
    return json.loads((ROOT / "config/yzu_cluster.json").read_text(encoding="utf-8"))


def test_remote_queue_off_when_prefer_local(cfg: dict) -> None:
    from scripts.yzu_cluster.cluster_ops import remote_queue_on_windows

    assert remote_queue_on_windows(cfg) is False


def test_remote_queue_off_when_windows_unprovisioned(cfg: dict) -> None:
    from scripts.yzu_cluster.cluster_ops import remote_queue_on_windows

    patched = dict(cfg)
    patched["operations"] = dict(cfg["operations"])
    patched["operations"]["prefer_local_queue"] = False
    with patch(
        "scripts.yzu_cluster.windows_lab_readiness.probe_windows_lab",
        return_value={"queue_ready": False, "joined_workers": 3},
    ):
        assert remote_queue_on_windows(patched) is False


def test_prefer_local_collect_when_no_joined_workers(cfg: dict) -> None:
    from scripts.yzu_cluster.cluster_ops import prefer_local_collect

    with patch(
        "scripts.yzu_cluster.windows_lab_readiness.probe_windows_lab",
        return_value={"queue_ready": False, "http_shard_ready": False},
    ):
        assert prefer_local_collect(cfg) is True


def test_prefer_remote_http_when_workers_joined(cfg: dict) -> None:
    from scripts.yzu_cluster.cluster_ops import prefer_local_collect

    with patch(
        "scripts.yzu_cluster.windows_lab_readiness.probe_windows_lab",
        return_value={"queue_ready": False, "http_shard_ready": True},
    ):
        assert prefer_local_collect(cfg) is False
