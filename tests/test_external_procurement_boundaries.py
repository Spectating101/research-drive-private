from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.research_data_mcp import datacite_repository, doi_resolve_cache
from scripts.research_data_mcp.desk_ownership import owner_id_for_create
from scripts.research_data_mcp.discover_collect_plan import resolve_discover_collect_plan
from scripts.research_data_mcp.discover_history import build_discover_history
from scripts.research_data_mcp.gateway import ResearchDataGateway
from scripts.research_data_mcp.mcp_register import registered_tool_names
from scripts.research_data_mcp.tool_handlers import ResearchToolHandlers


class _Procurement:
    store = SimpleNamespace(list=lambda: [])

    def manifest_plan_from_connector(self, _connector_id: str, *, limit: int):
        raise KeyError("no manifest")


def test_doi_candidate_key_survives_non_doi_landing_url(monkeypatch, tmp_path):
    monkeypatch.setattr(
        doi_resolve_cache,
        "resolve_doi_cached",
        lambda _root, doi: {
            "doi": doi,
            "title": "Forest evidence",
            "repository": "figshare",
            "files": [{"url": "https://example.test/forest.xls", "name": "forest.xls"}],
        },
    )
    monkeypatch.setattr(
        datacite_repository,
        "build_http_manifest_plan",
        lambda resolved: {
            "job_type": "http_manifest",
            "items": list(resolved["files"]),
            "launchable": True,
        },
    )

    plan = resolve_discover_collect_plan(
        _Procurement(),
        tmp_path,
        connector_id="datacite",
        candidate_key="doi:10.1234/forest-data",
        url="https://repository.example.test/article/forest-data",
        title="Forest evidence",
    )

    assert plan["job_type"] == "http_manifest"
    assert plan["doi"] == "10.1234/forest-data"
    assert plan["collect_resolution"] == "datacite_selected_doi"


def test_discover_submit_surfaces_plan_validation_error(monkeypatch, tmp_path):
    class Store:
        def get(self, _intent_id):
            return {
                "title": "Forest evidence",
                "research_need": "Forest losses",
                "state": {
                    "selected_route_id": "route-a",
                    "candidate": {"candidate_key": "doi:10.1234/forest"},
                    "routes": [{"id": "route-a", "title": "DataCite", "connector_id": "datacite"}],
                },
            }

    gateway = ResearchDataGateway.__new__(ResearchDataGateway)
    gateway._discover_intents_store = Store()
    gateway.repo_root = tmp_path
    gateway.agent = SimpleNamespace(procurement=_Procurement())
    gateway.jobs = SimpleNamespace(
        submit=lambda *_args, **_kwargs: {
            "job": None,
            "error": "target host does not resolve: repository.example.test",
        }
    )

    monkeypatch.setattr(
        "scripts.research_data_mcp.discover_collect_plan.resolve_discover_collect_plan",
        lambda *_args, **_kwargs: {"job_type": "source_probe", "launchable": False},
    )

    with pytest.raises(ValueError, match="target host does not resolve"):
        gateway.discover_intent_submit_collection("intent-a")


def test_mcp_role_profiles_keep_approval_operator_only(monkeypatch):
    monkeypatch.delenv("RESEARCH_MCP_SYNTHESIS_READ_ONLY", raising=False)

    monkeypatch.setenv("RESEARCH_MCP_PRINCIPAL_ROLE", "public_member")
    public_tools = set(registered_tool_names())
    assert "research_discover_search" in public_tools
    assert "research_craft_discover_proposal" in public_tools
    assert "research_profile_memory" in public_tools
    assert "research_profile_remember" in public_tools
    assert "research_profile_forget" in public_tools
    assert "research_discover_submit_intent" not in public_tools
    assert "yzu_submit_job" not in public_tools
    assert "yzu_approve_job" not in public_tools

    monkeypatch.setenv("RESEARCH_MCP_PRINCIPAL_ROLE", "member")
    member_tools = set(registered_tool_names())
    assert "research_discover_create_intent" in member_tools
    assert "research_discover_review_intent" in member_tools
    assert "research_discover_select_intent_route" in member_tools
    assert "research_discover_submit_intent" in member_tools
    assert "yzu_approve_job" not in member_tools
    assert "procurement_approve_job" not in member_tools

    monkeypatch.setenv("RESEARCH_MCP_PRINCIPAL_ROLE", "operator")
    operator_tools = set(registered_tool_names())
    assert "research_discover_submit_intent" in operator_tools
    assert "yzu_approve_job" in operator_tools


def test_mcp_child_process_preserves_member_ownership(monkeypatch):
    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_auth.current_desk_principal",
        lambda: None,
    )
    monkeypatch.setenv("RESEARCH_MCP_PRINCIPAL_ID", "member-from-http")
    monkeypatch.setenv("RESEARCH_MCP_PRINCIPAL_ROLE", "member")

    assert owner_id_for_create() == "member-from-http"


def test_reviewed_intent_mcp_tools_follow_browser_ladder():
    calls: list[tuple] = []

    class Gateway:
        def discover_intent_review(self, intent_id, **kwargs):
            calls.append(("review", intent_id, kwargs))
            return {"id": intent_id, "state": {"status": "ready_for_review"}}

        def discover_intent_select_route(self, intent_id, route_id):
            calls.append(("route", intent_id, route_id))
            return {"id": intent_id, "state": {"selected_route_id": route_id}}

        def discover_intent_submit_collection(self, intent_id, *, limit):
            calls.append(("submit", intent_id, limit))
            return {"job": {"id": "job-a", "status": "pending_approval"}}

    tools = ResearchToolHandlers(SimpleNamespace(gateway=Gateway()))
    tools.research_discover_review_intent("intent-a", "accept", "proposal-a", "hash-a")
    tools.research_discover_select_intent_route("intent-a", "route-a")
    submitted = tools.research_discover_submit_intent("intent-a", 5)

    assert submitted["job"]["status"] == "pending_approval"
    assert submitted["approval_required"] is True
    assert submitted["agent_may_approve"] is False
    assert calls == [
        (
            "review",
            "intent-a",
            {"decision": "accept", "proposal_id": "proposal-a", "proposal_hash": "hash-a"},
        ),
        ("route", "intent-a", "route-a"),
        ("submit", "intent-a", 5),
    ]


def test_history_intent_uses_linked_job_terminal_status():
    history = build_discover_history(
        intents=[
            {
                "id": "intent-a",
                "title": "Forest evidence",
                "state": {
                    "status": "pending_approval",
                    "collection": {"job_id": "job-a", "status": "cancelled"},
                },
            }
        ],
        include_ops=True,
    )

    intent = next(item for item in history["items"] if item["kind"] == "intent")
    assert intent["status"] == "cancelled"
