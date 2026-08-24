"""Agent synthesis hardening: preflight, tools, approve still blocked."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def stack():
    from scripts.research_data_mcp.bootstrap import create_stack

    return create_stack(repo_root=REPO)


def _tmp_registry_panel(tmp_path: Path) -> Path:
    """Isolated mini-repo with one panel for preflight column checks."""
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    pd.DataFrame({"week": ["2024-01"], "asset": ["USDT"], "score": [1.0]}).to_csv(
        tmp_path / "data/input.csv", index=False
    )
    (tmp_path / "config/research_query_registry.json").write_text(
        json.dumps({"datasets": [{"dataset_id": "input_panel", "local_path": "data/input.csv"}]}),
        encoding="utf-8",
    )
    return tmp_path


def test_preflight_ok_and_missing_column(tmp_path: Path):
    from scripts.research_data_mcp.synthesis_executor import preflight_execution_spec

    repo = _tmp_registry_panel(tmp_path)
    ok = preflight_execution_spec(
        repo,
        {
            "input_dataset_id": "input_panel",
            "output_dataset_id": "synthesis_agent_ok_panel",
            "group_by": ["week"],
            "metrics": [{"function": "mean", "column": "score", "as": "mean_score"}],
        },
    )
    assert ok["ok"] is True
    assert ok["execution_spec"]["input_dataset_id"] == "input_panel"

    bad = preflight_execution_spec(
        repo,
        {
            "input_dataset_id": "input_panel",
            "output_dataset_id": "synthesis_agent_bad_panel",
            "transforms": [{"op": "filter", "column": "not_a_col", "cmp": "eq", "value": 1}],
            "group_by": [],
            "metrics": [{"function": "count", "as": "n"}],
        },
    )
    assert bad["ok"] is False
    assert any(i.get("code") == "missing_column" for i in bad["issues"])


def test_agent_tools_handoff_submit_and_cannot_approve(stack, tmp_path: Path):
    gw = stack.gateway
    tools = stack.tools
    stamp = "agenthard"
    thread = gw.synthesis_thread_create(
        objective="Agent harden handoff",
        title=f"Agent harden {stamp}",
        required_grain="name-day",
        state={
            "objective": "Agent harden",
            "required_grain": "name-day",
            "materialisation": "not_materialised",
            "nodes": [
                {
                    "id": "held",
                    "type": "source",
                    "layer": "evidence",
                    "status": "held",
                    "dataset_id": "sec_company_tickers",
                    "label": "SEC",
                },
                {
                    "id": "twse_missing",
                    "type": "source",
                    "layer": "evidence",
                    "status": "missing",
                    "connector_id": "twse",
                    "source_id": "twse_openapi",
                    "label": "TWSE",
                },
            ],
            "edges": [],
            "activity": [],
        },
    )
    tid = thread["id"]
    handoff = tools.research_synthesis_discover_handoff(tid)
    assert handoff["collection"] is None
    assert handoff["agent_may_approve_synthesis"] is False
    assert any(i.get("evidence_id") == "twse_missing" and i.get("resolvable") for i in handoff.get("collect_intents") or [])

    mat = tools.research_synthesis_materialisation(tid)
    assert mat["materialisation"] in {"not_materialised", "registered"}

    # submit without accepted spec must fail
    with pytest.raises(ValueError):
        tools.research_synthesis_submit_execution(tid)

    # approve still blocked on agent tool
    job = stack.orchestrator.store.create(
        "synth block",
        {},
        {"job_type": "synthesis_execute", "launchable": True},
        status="pending_approval",
    )
    with pytest.raises(PermissionError):
        tools.yzu_approve_job(job["id"])


def test_propose_rejects_bad_execution_spec_preflight(stack):
    gw = stack.gateway
    tools = stack.tools
    thread = gw.synthesis_thread_create(
        objective="Bad spec preflight",
        title="Bad spec",
        required_grain="asset-week",
        state={
            "objective": "Bad spec",
            "materialisation": "not_materialised",
            "nodes": [
                {
                    "id": "panel",
                    "type": "source",
                    "layer": "evidence",
                    "status": "held",
                    "dataset_id": "stablecoin_trust_engagement_weekly",
                    "label": "panel",
                }
            ],
            "edges": [],
            "activity": [],
        },
    )
    with pytest.raises(ValueError, match="preflight failed"):
        tools.research_synthesis_propose_state(
            thread["id"],
            proposal_id="bad-spec-1",
            title="Bad aggregate",
            summary="Uses a missing column on purpose",
            operations=[{"op": "append_activity", "message": "bad"}],
            execution_spec={
                "input_dataset_id": "stablecoin_trust_engagement_weekly",
                "output_dataset_id": "synthesis_agent_bad_col_xyz",
                "group_by": ["definitely_not_a_column_zzz"],
                "metrics": [{"function": "count", "as": "n"}],
            },
        )


def test_new_synthesis_tools_are_registered():
    from scripts.research_data_mcp.procurement_constants import MCP_TOOL_CORE
    from scripts.research_data_mcp.tool_handlers import MCP_TOOL_NAMES

    for name in (
        "research_synthesis_preflight_spec",
        "research_synthesis_discover_handoff",
        "research_synthesis_collect_missing",
        "research_synthesis_materialisation",
        "research_synthesis_submit_execution",
    ):
        assert name in MCP_TOOL_CORE
        assert name in MCP_TOOL_NAMES
