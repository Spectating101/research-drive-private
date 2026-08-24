"""HTTP router contracts — single engine, datasets params, pruned legacy routes."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def stack():
    from scripts.research_data_mcp.bootstrap import create_stack

    return create_stack(repo_root=REPO)


def test_stack_uses_single_query_engine(stack):
    assert stack.engine is stack.gateway.engine
    assert stack.engine is stack.gateway.search.engine


def test_datasets_limit_query_param(stack):
    from scripts.research_data_mcp.http_router import handle_get

    out = handle_get("/datasets", {"limit": "3"}, stack)
    assert out["status"] == 200
    body = out["body"]
    assert "datasets" in body
    assert len(body["datasets"]) <= 3


def test_datasets_search_query(stack):
    from scripts.research_data_mcp.http_router import handle_get

    out = handle_get("/datasets", {"q": "gdelt", "limit": "5"}, stack)
    assert out["status"] == 200
    rows = out["body"]["datasets"]
    assert isinstance(rows, list)
    assert len(rows) <= 5


def test_pruned_agent_routes_404(stack):
    from scripts.research_data_mcp.http_router import handle_get, handle_post

    for path in ("/agent/status", "/agent/jobs", "/yzu/jobs"):
        out = handle_get(path, {}, stack)
        assert out["status"] == 404, path

    out = handle_post("/agent/chat", {"message": "hi"}, stack)
    assert out["status"] == 404


def test_library_jobs_list(stack):
    from scripts.research_data_mcp.http_router import handle_get

    out = handle_get("/library/jobs", {"limit": "3"}, stack)
    assert out["status"] == 200
    assert "jobs" in out["body"]


def test_search_trio_routes_exist():
    from scripts.research_data_mcp.http_router import ROUTE_CATALOG

    paths = {r["path"] for r in ROUTE_CATALOG if r["method"] == "GET"}
    assert "/library/discover" in paths
    assert "/library/search" in paths
    assert "/library/discover/web" in paths


def test_route_catalog_no_agent_namespace():
    from scripts.research_data_mcp.http_router import ROUTE_CATALOG

    agent_paths = [r for r in ROUTE_CATALOG if r["path"].startswith("/agent/")]
    assert agent_paths == []


def test_library_jobs_approve_safe_route(stack):
    from scripts.research_data_mcp.http_router import handle_post

    out = handle_post("/library/jobs/approve-safe", {"limit": 5}, stack)
    assert out["status"] == 200
    body = out["body"]
    assert "approved_count" in body


def test_library_synthesis_profiles_route(stack):
    from scripts.research_data_mcp.http_router import handle_get

    out = handle_get("/library/synthesis/profiles", {}, stack)
    assert out["status"] == 200
    body = out["body"]
    assert "profiles" in body
    assert isinstance(body["profiles"], list)


def test_library_chat_session_get(stack):
    from scripts.research_data_mcp.http_router import handle_get, handle_post

    chat = handle_post(
        "/library/chat",
        {"message": "status", "user_email": "drkong@saturn.yzu.edu.tw"},
        stack,
    )
    assert chat["status"] == 200
    sid = chat["body"].get("session_id")
    assert sid
    sess = handle_get(f"/library/chat/{sid}", {}, stack)
    assert sess["status"] == 200
    assert isinstance(sess["body"].get("messages"), list)
