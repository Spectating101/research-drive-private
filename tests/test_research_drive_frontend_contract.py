from __future__ import annotations

import inspect

from scripts.research_data_mcp.http_router import ROUTE_CATALOG
from scripts.research_query_engine.server import ResearchQueryHandler


# Public frontend convergence candidate whose HTTP surface this backend RC must satisfy.
FRONTEND_RC_SHA = "9b4e8b7d90f95c28afeec36263cbfc6093995256"


REQUIRED_ROUTER_ROUTES = {
    # Core registry / health
    ("GET", "/health"),
    ("GET", "/datasets"),
    ("GET", "/datasets/{id}"),
    ("GET", "/query/{id}"),
    # Library / HPS / Resources / principal bootstrap
    ("GET", "/library/catalog"),
    ("GET", "/library/search"),
    ("GET", "/library/overview"),
    ("GET", "/library/partitions"),
    ("GET", "/library/ops"),
    ("GET", "/library/consolidated"),
    ("GET", "/library/faculty/profile"),
    ("GET", "/library/seed"),
    ("GET", "/library/desk/resources"),
    ("POST", "/library/desk/warm"),
    ("GET", "/library/live-identity"),
    ("GET", "/library/jobs"),
    ("POST", "/library/jobs"),
    ("POST", "/library/jobs/{id}/approve"),
    ("GET", "/yzu/status"),
    ("GET", "/yzu/acquisitions"),
    # Principal-owned connected storage authority
    ("GET", "/library/accounts"),
    ("POST", "/library/accounts/oauth/start"),
    ("POST", "/library/accounts/oauth/complete"),
    ("POST", "/library/accounts/{account_id}/verify"),
    ("POST", "/library/accounts/{account_id}/disconnect"),
    # Discover
    ("GET", "/library/discover"),
    ("GET", "/library/discover/web"),
    ("GET", "/library/discover/sources"),
    ("POST", "/library/discover/sources/preview"),
    ("POST", "/library/discover/assessment"),
    ("POST", "/library/discover/routes"),
    ("POST", "/library/discover/probe"),
    ("POST", "/library/discover/collect"),
    ("GET", "/library/discover/history"),
    ("POST", "/library/discover/intents"),
    ("GET", "/library/discover/intents/{intent_id}"),
    ("POST", "/library/discover/intents/{intent_id}/proposal"),
    ("POST", "/library/discover/intents/{intent_id}/review"),
    ("POST", "/library/discover/intents/{intent_id}/route"),
    ("POST", "/library/discover/intents/{intent_id}/submit"),
    ("POST", "/library/craft/collect-plan"),
    ("POST", "/library/craft/discover-proposal"),
    # Synthesis
    ("GET", "/library/synthesis/profiles"),
    ("GET", "/library/synthesis/threads"),
    ("POST", "/library/synthesis/threads"),
    ("GET", "/library/synthesis/threads/{thread_id}"),
    ("GET", "/library/synthesis/threads/{thread_id}/measurements"),
    ("GET", "/library/synthesis/threads/{thread_id}/evidence-map"),
    ("POST", "/library/synthesis/threads/{thread_id}/evidence-map"),
    ("POST", "/library/synthesis/threads/{thread_id}/conversation"),
    ("POST", "/library/synthesis/threads/{thread_id}/patches"),
    ("GET", "/library/synthesis/threads/{thread_id}/discover-handoff"),
    ("GET", "/library/synthesis/threads/{thread_id}/materialisation"),
    ("GET", "/library/synthesis/threads/{thread_id}/method"),
    ("POST", "/library/synthesis/threads/{thread_id}/execute"),
    ("GET", "/library/synthesis/{id}"),
    ("POST", "/library/synthesis/run"),
    ("POST", "/library/synthesis/pair"),
    # Ask / contextual interpretation
    ("GET", "/library/chat/{session_id}"),
    ("POST", "/library/chat"),
    ("POST", "/library/chat/stream"),
    ("POST", "/library/advise"),
}


SPECIAL_SERVER_ROUTES = {
    ("GET", "/library/desk/capabilities"),
    ("POST", "/library/desk/session"),
    ("DELETE", "/library/desk/session"),
}


def test_frontend_release_candidate_routes_exist_on_backend_rc():
    actual = {(row["method"], row["path"]) for row in ROUTE_CATALOG}
    missing = sorted(REQUIRED_ROUTER_ROUTES - actual)
    assert not missing, (
        f"backend RC no longer satisfies frontend {FRONTEND_RC_SHA}: missing routes {missing}"
    )


def test_special_browser_session_routes_are_owned_by_http_server():
    sources = {
        "GET": inspect.getsource(ResearchQueryHandler.do_GET),
        "POST": inspect.getsource(ResearchQueryHandler.do_POST),
        "DELETE": inspect.getsource(ResearchQueryHandler.do_DELETE),
    }
    missing = sorted(
        (method, path)
        for method, path in SPECIAL_SERVER_ROUTES
        if path not in sources[method]
    )
    assert not missing, (
        f"backend RC no longer satisfies frontend {FRONTEND_RC_SHA}: missing special routes {missing}"
    )


def test_frontend_api_prefix_is_normalized_by_production_server():
    from scripts.research_query_engine.server import normalize_api_path

    assert normalize_api_path("/api/library/discover") == "/library/discover"
    assert normalize_api_path("/api/library/seed") == "/library/seed"
    assert normalize_api_path("/api/library/accounts") == "/library/accounts"
    assert normalize_api_path("/api/health") == "/health"
    assert normalize_api_path("/library/discover") == "/library/discover"
