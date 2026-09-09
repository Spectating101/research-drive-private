from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from scripts.research_data_mcp.synthesis_executor import execute
from scripts.research_data_mcp.synthesis_thread_store import accept_proposal, validate_synthesis_proposal
from scripts.research_data_mcp.tool_handlers import ResearchToolHandlers


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "data").mkdir(parents=True)
    frame = pd.DataFrame({"entity_id": ["a", "a", "b"], "week": [1, 2, 1], "value": [1.0, 3.0, 5.0]})
    frame.to_parquet(tmp_path / "data/base.parquet", index=False)
    (tmp_path / "config/research_query_registry.json").write_text(json.dumps({"datasets": [{
        "dataset_id": "base", "name": "Base", "local_path": "data/base.parquet", "grain": "entity-week", "join_keys": ["entity_id", "week"]
    }]}), encoding="utf-8")
    return tmp_path


def _spec():
    return {
        "input_dataset_id": "base",
        "output_dataset_id": "synthesis_method_export_v1",
        "group_by": ["entity_id"],
        "metrics": [{"function": "mean", "column": "value", "as": "mean_value"}],
    }


def test_composer_tool_stamps_llm_origin():
    captured = {}
    class Gateway:
        def synthesis_thread_propose_state(self, thread_id, **kwargs):
            captured.update(kwargs)
            return {"id": thread_id, "state": {"proposal": {"execution_preflight": {"ok": True}}}}
    handlers = ResearchToolHandlers(SimpleNamespace(gateway=Gateway()))
    handlers.research_synthesis_propose_state(
        "t", "p", "Method", "Summary", [{"op": "update_spec", "patch": {"purpose": "x"}}], execution_spec=_spec()
    )
    assert captured["origin"] == {
        "kind": "llm_tool_call", "authority": "composer", "tool": "research_synthesis_propose_state"
    }


def test_researcher_acceptance_preserves_llm_proposal_identity():
    state = {"nodes": [], "edges": [], "activity": [], "spec": {}, "proposal": None}
    proposal = validate_synthesis_proposal(state, {
        "id": "p1", "title": "LLM method", "summary": "validated method", "operations": [
            {"op": "update_spec", "patch": {"purpose": "test"}}
        ], "execution_spec": _spec(),
        "origin": {"kind": "llm_tool_call", "authority": "composer", "tool": "research_synthesis_propose_state"},
    })
    state["proposal"] = proposal
    accepted = accept_proposal(state)
    origin = accepted["method_origin"]
    assert origin["kind"] == "llm_tool_call"
    assert origin["authority"] == "composer"
    assert origin["tool"] == "research_synthesis_propose_state"
    assert origin["proposal_hash"] == proposal["proposal_hash"]
    assert accepted["accepted_spec_hash"]


def test_executor_freezes_runnable_method_from_accepted_spec(tmp_path):
    repo = _repo(tmp_path)
    origin = {
        "kind": "llm_tool_call", "authority": "composer", "tool": "research_synthesis_propose_state",
        "proposal_id": "p1", "proposal_hash": "proposal-sha"
    }
    result = execute(repo, "job1", {"thread_id": "t1", "execution_spec": _spec(), "method_origin": origin})
    repro = result["reproducibility"]
    method = repo / repro["method_path"]
    assert method.is_file()
    text = method.read_text(encoding="utf-8")
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == repro["method_sha256"]
    assert repro["method_origin"]["authority"] == "composer"
    assert "execution_spec sha256" in text
    assert "result.to_parquet" in text
    manifest = json.loads((repo / result["materialized"]["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["reproducibility"]["method_sha256"] == repro["method_sha256"]
    assert any(row["name"] == "method.py" for row in result["materialized"]["files"])

    run_dir = repo / "reproduce"
    run_dir.mkdir()
    run = subprocess.run([sys.executable, str(method)], cwd=run_dir, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    reproduced = pd.read_parquet(run_dir / "synthesis_method_export_v1.parquet")
    engine = pd.read_parquet(repo / "data_lake/synthesis/thread_outputs/t1/job1/output.parquet")
    pd.testing.assert_frame_equal(
        engine.sort_values(list(engine.columns)).reset_index(drop=True),
        reproduced.sort_values(list(reproduced.columns)).reset_index(drop=True),
        check_dtype=False,
    )
