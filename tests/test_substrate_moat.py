#!/usr/bin/env python3
"""Substrate tests: transform plane, readiness truth, headroom, job-first."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drive"))

from scripts.research_data_mcp.execution_policy import enforce_execution_submit, enforce_nvme_headroom
from scripts.research_data_mcp.job_first_procure import propose_pending_collect
from scripts.research_data_mcp.procure_lifecycle import procure_phase_from_job
from scripts.research_data_mcp.readiness_truth import apply_smoke_readiness
from scripts.research_data_mcp.synthesis_executor import execute, validate_execution_spec


def test_validate_allows_row_output_without_metrics():
    spec = validate_execution_spec(
        {
            "input_dataset_id": "keeling_co2",
            "output_dataset_id": "synthesis_keeling_lag1",
            "row_output": True,
            "transforms": [{"op": "lag", "column": "co2", "periods": 1, "as": "co2_lag1"}],
        }
    )
    assert spec["row_output"] is True
    assert spec["metrics"] == []
    assert spec["transforms"][0]["op"] == "lag"


def test_validate_rejects_empty_metrics_without_row_output():
    with pytest.raises(ValueError, match="row_output"):
        validate_execution_spec(
            {
                "input_dataset_id": "keeling_co2",
                "output_dataset_id": "synthesis_keeling_bad",
                "transforms": [{"op": "lag", "column": "co2", "periods": 1, "as": "co2_lag1"}],
            }
        )


def test_execute_lag_row_output(tmp_path: Path):
    lake = tmp_path / "data_lake" / "inputs"
    lake.mkdir(parents=True)
    src = lake / "panel.csv"
    pd.DataFrame({"t": [1, 2, 3, 4], "co2": [10.0, 11.0, 12.0, 13.0]}).to_csv(src, index=False)
    registry = {
        "datasets": [
            {
                "dataset_id": "keeling_co2",
                "local_path": "data_lake/inputs/panel.csv",
                "analysis_readiness": "query_ready",
            }
        ]
    }
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "research_query_registry.json").write_text(
        json.dumps(registry), encoding="utf-8"
    )
    result = execute(
        tmp_path,
        "job_lag1",
        {
            "thread_id": "thr_test",
            "execution_spec": {
                "input_dataset_id": "keeling_co2",
                "output_dataset_id": "synthesis_keeling_lag1",
                "row_output": True,
                "transforms": [{"op": "lag", "column": "co2", "periods": 1, "as": "co2_lag1"}],
            },
        },
    )
    assert result["rows"] == 4
    out = pd.read_parquet(tmp_path / result["materialized"]["files"][0]["path"])
    assert list(out["co2_lag1"])[1:] == [10.0, 11.0, 12.0]
    assert pd.isna(out["co2_lag1"].iloc[0])


def test_execute_diff_and_rolling(tmp_path: Path):
    lake = tmp_path / "data_lake" / "inputs"
    lake.mkdir(parents=True)
    src = lake / "panel.csv"
    pd.DataFrame({"v": [1.0, 2.0, 4.0, 7.0]}).to_csv(src, index=False)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "research_query_registry.json").write_text(
        json.dumps(
            {
                "datasets": [
                    {
                        "dataset_id": "series_a",
                        "local_path": "data_lake/inputs/panel.csv",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    result = execute(
        tmp_path,
        "job_win",
        {
            "thread_id": "thr_win",
            "execution_spec": {
                "input_dataset_id": "series_a",
                "output_dataset_id": "synthesis_series_win",
                "row_output": True,
                "transforms": [
                    {"op": "diff", "column": "v", "periods": 1, "as": "v_diff"},
                    {"op": "rolling", "column": "v", "window": 2, "fn": "mean", "as": "v_ma2"},
                ],
            },
        },
    )
    out = pd.read_parquet(tmp_path / result["materialized"]["files"][0]["path"])
    assert out["v_diff"].iloc[1] == pytest.approx(1.0)
    assert out["v_ma2"].iloc[1] == pytest.approx(1.5)


def test_apply_smoke_readiness_ok():
    spec: dict = {"materialization": {}}
    apply_smoke_readiness(spec, {"ok": True, "rows": 3})
    assert spec["analysis_readiness"] == "query_ready"
    assert spec["materialization"]["query_verified"] is True


def test_apply_smoke_readiness_fail_stays_registered():
    spec: dict = {"materialization": {"bytes_ready": True}}
    apply_smoke_readiness(spec, {"ok": False, "rows": 0})
    assert spec["analysis_readiness"] == "registered"
    assert spec["materialization"]["query_ready"] is False


def test_procure_phase_pending_and_query_ready():
    assert procure_phase_from_job({"status": "pending_approval"}) == "pending_approval"
    assert (
        procure_phase_from_job(
            {
                "status": "completed",
                "result": {"promotion": {"analysis_readiness": "query_ready"}},
            }
        )
        == "query_ready"
    )


def test_headroom_blocks_landing_when_low(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RD_ENFORCE_HEADROOM", "1")
    with patch(
        "scripts.research_data_mcp.storage_tiers.nvme_disk_headroom_gb",
        return_value=(10.0, 40),
    ):
        with pytest.raises(ValueError, match="nvme headroom blocked"):
            enforce_nvme_headroom(tmp_path, {"job_type": "http_manifest"})


def test_headroom_allows_probe_when_low(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RD_ENFORCE_HEADROOM", "1")
    with patch(
        "scripts.research_data_mcp.storage_tiers.nvme_disk_headroom_gb",
        return_value=(10.0, 40),
    ):
        enforce_nvme_headroom(tmp_path, {"job_type": "source_probe"})  # no raise


def test_faculty_submit_still_forces_pending(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("RD_ENFORCE_HEADROOM", "0")
    plan, auto = enforce_execution_submit(
        {"job_type": "http_manifest", "url": "https://example.org/a.csv", "title": "t"},
        {},
        auto_approve=True,
        repo_root=tmp_path,
    )
    assert auto is False
    assert plan["execution_policy"]["scope"] == "faculty"


def test_job_first_refuses_invented_url():
    gw = MagicMock()
    measured = {
        "strong_held": False,
        "held": [],
        "routes": [{"source_id": "twse", "title": "TWSE", "url": ""}],
    }
    with (
        patch("scripts.research_data_mcp.desk_ask_grounding.measure_ask_desk", return_value=measured),
        patch("scripts.research_data_mcp.desk_ask_grounding.resolve_ask_measure_query", return_value="twse"),
        patch("scripts.research_data_mcp.desk_ask_grounding.serialize_desk_facts_ui", return_value={}),
    ):
        out = propose_pending_collect(gw, query="taiwan stocks")
    assert out["ok"] is False
    assert out["action"] == "need_url"
    assert out["composer_required"] is False
    gw.submit_yzu_job.assert_not_called()


def test_job_first_submits_pending_when_url_present():
    gw = MagicMock()
    gw.submit_yzu_job.return_value = {"job": {"id": "job_abc", "status": "pending_approval"}, "plan": {}}
    measured = {
        "strong_held": False,
        "held": [],
        "routes": [{"source_id": "ex", "title": "Example", "url": "https://example.org/data.csv"}],
    }
    crafted = {
        "plan": {
            "job_type": "http_manifest",
            "url": "https://example.org/data.csv",
            "title": "Collect · Example",
        }
    }
    with (
        patch("scripts.research_data_mcp.desk_ask_grounding.measure_ask_desk", return_value=measured),
        patch("scripts.research_data_mcp.desk_ask_grounding.resolve_ask_measure_query", return_value="ex"),
        patch("scripts.research_data_mcp.desk_ask_grounding.serialize_desk_facts_ui", return_value={}),
        patch("scripts.research_data_mcp.craft_collect.craft_collect_plan", return_value=crafted),
    ):
        out = propose_pending_collect(gw, query="example data")
    assert out["ok"] is True
    assert out["action"] == "pending_collect_proposed"
    assert out["job_id"] == "job_abc"
    gw.submit_yzu_job.assert_called_once()
    _, kwargs = gw.submit_yzu_job.call_args
    assert kwargs.get("auto_approve") is False


def test_job_first_refuses_redundant_collect_when_no_url_given():
    # The courtesy path: a bare need with no specific target — a real held
    # match should block a redundant collect here.
    gw = MagicMock()
    measured = {
        "strong_held": True,
        "held": [{"dataset_id": "twse_daily", "analysis_readiness": "instant"}],
        "routes": [],
    }
    with (
        patch("scripts.research_data_mcp.desk_ask_grounding.measure_ask_desk", return_value=measured),
        patch("scripts.research_data_mcp.desk_ask_grounding.resolve_ask_measure_query", return_value="twse"),
        patch("scripts.research_data_mcp.desk_ask_grounding.serialize_desk_facts_ui", return_value={}),
    ):
        out = propose_pending_collect(gw, query="taiwan stocks")
    assert out["ok"] is False
    assert out["action"] == "already_held"
    gw.submit_yzu_job.assert_not_called()


def test_job_first_allows_explicit_url_despite_a_loosely_related_held_row():
    # Composer only calls this tool after judging held data insufficient for
    # the specific need (e.g. metadata held, sales history asked for) — an
    # explicit url is that judgment made concrete, and should not be
    # second-guessed by a blunt "something strong-held exists" check.
    gw = MagicMock()
    gw.submit_yzu_job.return_value = {"job": {"id": "job_xyz", "status": "pending_approval"}, "plan": {}}
    measured = {
        "strong_held": True,
        "held": [{"dataset_id": "opensea_nft_metadata_layer", "analysis_readiness": "instant"}],
        "routes": [],
    }
    crafted = {
        "plan": {
            "job_type": "scraper_run",
            "url": "https://opensea.io/collection/boredapeyachtclub",
            "title": "Collect · BAYC sales history",
        }
    }
    with (
        patch("scripts.research_data_mcp.desk_ask_grounding.measure_ask_desk", return_value=measured),
        patch("scripts.research_data_mcp.desk_ask_grounding.resolve_ask_measure_query", return_value="bayc"),
        patch("scripts.research_data_mcp.desk_ask_grounding.serialize_desk_facts_ui", return_value={}),
        patch("scripts.research_data_mcp.craft_collect.craft_collect_plan", return_value=crafted),
    ):
        out = propose_pending_collect(
            gw,
            query="bayc sales history",
            url="https://opensea.io/collection/boredapeyachtclub",
        )
    assert out["ok"] is True
    assert out["action"] == "pending_collect_proposed"
    assert out["job_id"] == "job_xyz"
    gw.submit_yzu_job.assert_called_once()


def test_job_first_surfaces_submit_envelope_failure():
    gw = MagicMock()
    gw.submit_yzu_job.return_value = {"job": None, "error": "plan not launchable"}
    measured = {"strong_held": False, "held": [], "routes": []}
    crafted = {"plan": {"job_type": "http_manifest", "url": "https://example.org/a.csv"}}
    with (
        patch("scripts.research_data_mcp.desk_ask_grounding.measure_ask_desk", return_value=measured),
        patch("scripts.research_data_mcp.desk_ask_grounding.resolve_ask_measure_query", return_value="x"),
        patch("scripts.research_data_mcp.desk_ask_grounding.serialize_desk_facts_ui", return_value={}),
        patch("scripts.research_data_mcp.craft_collect.craft_collect_plan", return_value=crafted),
    ):
        out = propose_pending_collect(gw, query="x", url="https://example.org/a.csv")
    assert out["ok"] is False
    assert out["action"] == "submit_failed"
