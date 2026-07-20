#!/usr/bin/env python3
"""Runtime-authority bind coverage for the front-door host linker."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "drive/scripts/research_query_engine/link_front_door_host_config.sh"


def test_runtime_drive_root_dry_run_lists_binds(tmp_path: Path):
    runtime = tmp_path / "runtime_drive"
    (runtime / "config").mkdir(parents=True)
    (runtime / "data_lake" / "procured").mkdir(parents=True)
    (runtime / "data_lake" / "yzu_cluster").mkdir(parents=True)
    (runtime / "config" / "research_query_registry.json").write_text("{}\n", encoding="utf-8")

    env = os.environ.copy()
    env["YZU_RUNTIME_DRIVE_ROOT"] = str(runtime)
    out = subprocess.check_output(["bash", str(SCRIPT), "--dry-run"], text=True, env=env, cwd=REPO)
    assert "would_runtime_link=drive/config/research_query_registry.json" in out or "would_replace_runtime_link=drive/config/research_query_registry.json" in out
    assert "would_runtime_link=data_lake/procured" in out or "ok_runtime_link=data_lake/procured" in out or "skip_runtime_existing=data_lake/procured" in out
    assert "would_runtime_link=data_lake/yzu_cluster" in out or "ok_runtime_link=data_lake/yzu_cluster" in out or "skip_runtime_existing=data_lake/yzu_cluster" in out
    assert f"runtime_drive={runtime.resolve()}" in out
    assert "dry_run=1" in out


def test_runtime_drive_root_unset_reports_unset():
    env = os.environ.copy()
    env.pop("YZU_RUNTIME_DRIVE_ROOT", None)
    out = subprocess.check_output(["bash", str(SCRIPT), "--dry-run"], text=True, env=env, cwd=REPO)
    assert "runtime_drive=unset" in out
