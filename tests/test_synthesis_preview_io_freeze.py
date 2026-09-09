"""Adversarial I/O and concurrency contract for bounded Synthesis Preview."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest


def _repo(tmp_path: Path, *, suffix: str = ".csv", rows: int = 100) -> tuple[Path, dict]:
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "data").mkdir(parents=True)
    path = root / f"data/input{suffix}"
    frame = pd.DataFrame(
        {
            "asset": [f"A{i % 5}" for i in range(rows)],
            "week": [f"2026-W{1 + (i % 10)}" for i in range(rows)],
            "value": list(range(rows)),
        }
    )
    if suffix == ".csv":
        frame.to_csv(path, index=False)
    elif suffix == ".parquet":
        frame.to_parquet(path, index=False)
    else:
        raise AssertionError(suffix)
    (root / "config/research_query_registry.json").write_text(
        json.dumps(
            {
                "datasets": [
                    {
                        "dataset_id": "fixture_input",
                        "name": "Fixture input",
                        "local_path": f"data/input{suffix}",
                        "analysis_readiness": "query_ready",
                        "revision": "fixture-r1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    spec = {
        "input_dataset_id": "fixture_input",
        "output_dataset_id": "synthesis_preview_io_probe",
        "group_by": ["asset"],
        "metrics": [{"function": "mean", "column": "value", "as": "mean_value"}],
        "transforms": [],
    }
    return root, spec


def _accepted_gateway(tmp_path: Path):
    from scripts.research_data_mcp.gateway import ResearchDataGateway
    from scripts.research_data_mcp.synthesis_preview import execution_spec_hash
    from scripts.research_data_mcp.synthesis_thread_store import SynthesisThreadStore
    from scripts.research_data_mcp.synthesis_executor import validate_execution_spec

    root, raw_spec = _repo(tmp_path, rows=24)
    spec = validate_execution_spec(raw_spec)
    store = SynthesisThreadStore(root / "data_lake/procurement_memory/synthesis_threads.sqlite3")
    thread = store.create(objective="Test bounded Preview authority.")
    state = thread["state"]
    state["execution_spec"] = spec
    state["accepted_spec_hash"] = execution_spec_hash(spec)
    state["execution"] = {
        "status": "spec_accepted",
        "spec_hash": state["accepted_spec_hash"],
        "output_dataset_id": spec["output_dataset_id"],
    }
    thread = store._save_state(thread["id"], state)

    class Jobs:
        def __init__(self):
            self.submitted = []
            self.by_id = {}

        def submit(self, title, plan, request, auto_approve=False):
            assert auto_approve is False
            job = {
                "id": f"job-{len(self.submitted) + 1}",
                "status": "pending_approval",
                "title": title,
                "plan": plan,
                "request": request,
            }
            self.submitted.append(job)
            self.by_id[job["id"]] = job
            return {"job": job, "plan": plan}

        def get(self, job_id):
            return self.by_id[job_id]

    gateway = ResearchDataGateway.__new__(ResearchDataGateway)
    gateway.repo_root = root
    gateway.registry_path = root / "config/research_query_registry.json"
    gateway.jobs = Jobs()
    gateway._synthesis_thread_store = lambda: store
    return gateway, store, thread, spec


def test_csv_window_passes_nrows_to_pandas(tmp_path: Path, monkeypatch):
    from scripts.research_data_mcp.synthesis.bounded_read import read_bounded_frame

    root, _ = _repo(tmp_path, suffix=".csv", rows=100)
    path = root / "data/input.csv"
    original = pd.read_csv
    calls = []

    def guarded(*args, **kwargs):
        calls.append(kwargs.get("nrows"))
        assert kwargs.get("nrows") is not None, "bounded CSV read must always pass nrows"
        return original(*args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", guarded)
    frame, total, observed, exact = read_bounded_frame(path, 10)

    assert calls == [11]
    assert len(frame) == 11
    assert total is None
    assert observed == 11
    assert exact is False


def test_parquet_window_uses_record_batches_not_full_read_parquet(tmp_path: Path, monkeypatch):
    from scripts.research_data_mcp.synthesis.bounded_read import read_bounded_frame

    root, _ = _repo(tmp_path, suffix=".parquet", rows=100)
    path = root / "data/input.parquet"

    def forbidden(*_args, **_kwargs):
        raise AssertionError("bounded Parquet diagnostics must not call pandas.read_parquet")

    monkeypatch.setattr(pd, "read_parquet", forbidden)
    frame, total, observed, exact = read_bounded_frame(path, 10)

    assert len(frame) == 11
    assert total == 100
    assert observed == 11
    assert exact is True


@pytest.mark.parametrize("suffix", [".csv", ".parquet"])
def test_bounded_preflight_never_uses_full_executor_reader(tmp_path: Path, monkeypatch, suffix: str):
    from scripts.research_data_mcp import synthesis_executor

    root, spec = _repo(tmp_path, suffix=suffix, rows=100)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("bounded preflight must not call the full-frame executor reader")

    monkeypatch.setattr(synthesis_executor, "_read_frame", forbidden)
    report = synthesis_executor.preflight_execution_spec(root, spec, row_cap=10)

    assert report["ok"] is True
    assert report["bounded_row_cap"] == 10


@pytest.mark.parametrize("suffix", [".csv", ".parquet"])
def test_preview_primary_and_preflight_remain_bounded(tmp_path: Path, monkeypatch, suffix: str):
    from scripts.research_data_mcp import synthesis_executor
    from scripts.research_data_mcp.synthesis_preview import run_bounded_preview

    root, spec = _repo(tmp_path, suffix=suffix, rows=100)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Preview must not need the full primary-frame reader")

    monkeypatch.setattr(synthesis_executor, "_read_frame", forbidden)
    receipt = run_bounded_preview(root, spec, input_row_limit=10)

    assert receipt["status"] == "succeeded"
    assert receipt["sampling"]["previewed_rows"] == 10
    assert receipt["sampling"]["source_truncated"] is True
    assert receipt["preflight"]["bounded_row_cap"] == 10


def test_preview_refuses_oversized_full_join_side_before_any_data_read(tmp_path: Path, monkeypatch):
    from scripts.research_data_mcp import synthesis_executor, synthesis_preview

    _root, base = _repo(tmp_path, rows=10)
    spec = {
        **base,
        "transforms": [
            {
                "op": "join",
                "right_dataset_id": "right_big",
                "on": ["asset"],
                "how": "left",
                "collapse": {"strategy": "first"},
                "accept_row_loss": True,
            }
        ],
    }
    normalized = synthesis_executor.validate_execution_spec(spec)

    monkeypatch.setattr(
        synthesis_executor,
        "preflight_execution_spec",
        lambda *_args, **_kwargs: {
            "ok": True,
            "execution_spec": normalized,
            "warnings": [],
            "join_probes": [],
            "bounded_row_cap": 10,
        },
    )
    monkeypatch.setattr(
        synthesis_preview,
        "input_revision_snapshot",
        lambda *_args, **_kwargs: [
            {"dataset_id": "fixture_input", "size_bytes": 100},
            {
                "dataset_id": "right_big",
                "size_bytes": synthesis_preview.MAX_PREVIEW_JOIN_INPUT_BYTES + 1,
            },
        ],
    )

    with pytest.raises(ValueError, match="refuses full right-hand join input"):
        synthesis_preview.run_bounded_preview(tmp_path, normalized, input_row_limit=10)


def test_preview_receipt_cannot_overwrite_a_newly_accepted_revision(tmp_path: Path, monkeypatch):
    from scripts.research_data_mcp import synthesis_preview
    from scripts.research_data_mcp.synthesis_execution_authority import (
        handle_synthesis_execution_action,
    )
    from scripts.research_data_mcp.synthesis_preview import execution_spec_hash
    from scripts.research_data_mcp.synthesis_executor import validate_execution_spec

    gateway, store, thread, spec = _accepted_gateway(tmp_path)
    old_hash = execution_spec_hash(spec)
    real_run = synthesis_preview.run_bounded_preview

    def racing_run(repo_root, execution_spec, **kwargs):
        receipt = real_run(repo_root, execution_spec, **kwargs)
        changed = validate_execution_spec(
            {
                **spec,
                "output_dataset_id": "synthesis_preview_io_probe_v2",
                "metrics": [{"function": "count", "as": "n"}],
            }
        )
        state = store.get(thread["id"])["state"]
        state["execution_spec"] = changed
        state["accepted_spec_hash"] = execution_spec_hash(changed)
        state["preview"] = None
        state["execution"] = {
            "status": "spec_accepted",
            "spec_hash": state["accepted_spec_hash"],
            "output_dataset_id": changed["output_dataset_id"],
        }
        store._save_state(thread["id"], state)
        return receipt

    monkeypatch.setattr(synthesis_preview, "run_bounded_preview", racing_run)

    with pytest.raises(ValueError, match="revision changed while Preview was running"):
        handle_synthesis_execution_action(gateway, thread["id"], action="preview")

    fresh = store.get(thread["id"])["state"]
    assert fresh["accepted_spec_hash"] != old_hash
    assert not fresh.get("preview")
    assert gateway.jobs.submitted == []


def test_low_level_submit_rechecks_expected_authority_before_job_creation(tmp_path: Path):
    gateway, store, thread, _spec = _accepted_gateway(tmp_path)
    preview = gateway.synthesis_thread_submit_execution(thread["id"], action="preview")
    expected = preview["preview"]["authority_hash"]

    state = store.get(thread["id"])["state"]
    state["preview"] = {**state["preview"], "authority_hash": "changed-after-review"}
    store._save_state(thread["id"], state)

    with pytest.raises(ValueError, match="authority changed before job creation"):
        gateway._synthesis_thread_submit_approval(
            thread["id"], expected_authority_hash=expected
        )
    assert gateway.jobs.submitted == []
