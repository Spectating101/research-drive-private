#!/usr/bin/env python3
"""Bounded Synthesis terminal allowlist contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.research_data_mcp.synthesis_terminal import (
    list_terminal_commands,
    run_terminal_command,
)


class _FakeGateway:
    def __init__(self, repo_root: Path, thread: dict) -> None:
        self.repo_root = repo_root
        self._thread = thread

    def synthesis_thread_get(self, thread_id: str) -> dict:
        if thread_id != self._thread["id"]:
            raise ValueError(f"missing thread {thread_id}")
        return self._thread


def _write_keeling_like(repo: Path, thread_id: str, job_id: str) -> Path:
    out = repo / "data_lake/synthesis/thread_outputs" / thread_id / job_id
    out.mkdir(parents=True, exist_ok=True)
    table = pa.table(
        {
            "date": ["2026-04", "2026-05", "2026-06"],
            "sa_ppm": [428.61, 429.10, 429.06],
            "annual_rate_ppm": [1.48, 1.84, 1.83],
            "acceleration_ppm": [-1.65, -1.77, -0.86],
        }
    )
    path = out / "output.parquet"
    pq.write_table(table, path)
    (out / "manifest.json").write_text(json.dumps({"job_id": job_id}), encoding="utf-8")
    return path


def test_list_commands_includes_inspect_surface():
    catalog = list_terminal_commands()
    names = {row["command"] for row in catalog["commands"]}
    assert "output_sample" in names
    assert "verify_spec_columns" in names
    assert "free_shell" not in names


def test_unknown_command_rejected(tmp_path: Path):
    thread = {
        "id": "abc123",
        "state": {"execution": {}, "execution_spec": {}},
    }
    gw = _FakeGateway(tmp_path, thread)
    out = run_terminal_command(gw, thread_id="abc123", command="rm -rf /")
    assert out["ok"] is False
    assert "not allowlisted" in out["error"]


def test_path_traversal_thread_id_rejected(tmp_path: Path):
    thread = {"id": "safe", "state": {}}
    gw = _FakeGateway(tmp_path, thread)
    with pytest.raises(ValueError, match="thread_id"):
        run_terminal_command(gw, thread_id="../etc", command="thread_artifacts")


def test_output_sample_capped_and_column_filter(tmp_path: Path):
    thread_id = "db8f9c8a34894890"
    job_id = "5f9b86fa6be8"
    _write_keeling_like(tmp_path, thread_id, job_id)
    thread = {
        "id": thread_id,
        "state": {
            "execution": {"job_id": job_id, "status": "registered"},
            "execution_spec": {
                "input_dataset_id": "keeling_mlo_monthly_clean",
                "output_dataset_id": "synthesis_keeling_accel_monthly_v1",
                "transforms": [
                    {"op": "diff", "column": "sa_ppm", "periods": 12, "as": "annual_rate_ppm"},
                    {"op": "diff", "column": "annual_rate_ppm", "periods": 12, "as": "acceleration_ppm"},
                ],
            },
        },
    }
    gw = _FakeGateway(tmp_path, thread)
    sample = run_terminal_command(
        gw,
        thread_id=thread_id,
        command="output_sample",
        limit=100,  # must clamp to MAX_SAMPLE_ROWS
        tail=True,
        columns=["date", "acceleration_ppm"],
    )
    assert sample["ok"] is True
    assert sample["returned_rows"] == 3
    assert sample["columns"] == ["date", "acceleration_ppm"]
    assert "acceleration_ppm" in sample["rows"][-1]
    assert "sa_ppm" not in sample["rows"][-1]

    bad = run_terminal_command(
        gw,
        thread_id=thread_id,
        command="output_sample",
        columns=["not_a_column"],
    )
    assert bad["ok"] is False

    verify = run_terminal_command(gw, thread_id=thread_id, command="verify_spec_columns")
    assert verify["ok"] is True
    assert verify["missing_aliases"] == []
    assert "acceleration_ppm" in verify["expected_aliases"]

    artifacts = run_terminal_command(gw, thread_id=thread_id, command="thread_artifacts")
    assert artifacts["ok"] is True
    assert artifacts["file_count"] >= 2
    assert all(".." not in f["path"] for f in artifacts["files"])
