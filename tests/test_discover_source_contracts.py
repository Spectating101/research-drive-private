"""Discover Explore — source search, preview, refresh subscriptions, history."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1] / "drive"


@pytest.fixture(scope="module")
def stack():
    from scripts.research_data_mcp.bootstrap import create_stack

    return create_stack(repo_root=REPO)


def test_source_search_returns_sources_not_registry_datasets(stack):
    from scripts.research_data_mcp.http_router import handle_get

    out = handle_get("/library/discover/sources", {"q": "gdelt", "limit": "10"}, stack)
    assert out["status"] == 200
    body = out["body"]
    assert body["result_kind"] == "source"
    assert body["remote_search"]["attempted"] is False
    assert body["excludes"]["registry_datasets"] is True
    assert body["total"] >= 1
    kinds = {str(row.get("kind")) for row in body["results"]}
    assert "local_registry" not in kinds
    assert "registry_dataset" not in kinds
    assert "dataset" not in kinds
    assert any(row.get("kind") in {"source", "provider", "connector"} for row in body["results"])
    for row in body["results"]:
        assert row.get("candidate_key")
        assert str(row["candidate_key"]).startswith(("source:", "url:", "doi:", "title:"))
        assert row.get("result_type") != "registry_dataset"


def test_source_search_stable_candidate_identity(stack):
    from scripts.research_data_mcp.discover_source_search import search_discover_sources

    a = search_discover_sources(stack.gateway.repo_root, "bigquery", limit=20)
    b = search_discover_sources(stack.gateway.repo_root, "bigquery", limit=20)
    keys_a = [r["candidate_key"] for r in a["results"]]
    keys_b = [r["candidate_key"] for r in b["results"]]
    assert keys_a == keys_b
    assert any("bigquery" in k for k in keys_a)


def test_source_preview_catalog_schema_only_and_access_required(stack):
    from scripts.research_data_mcp.http_router import handle_post

    gdelt = handle_post(
        "/library/discover/sources/preview",
        {"source_id": "gdelt", "limit": 5},
        stack,
    )
    assert gdelt["status"] == 200
    body = gdelt["body"]
    assert body["status"] in {"schema_only", "ready", "access_required"}
    assert body.get("sample_rows") is None or len(body.get("sample_rows") or []) <= 8
    # Must not dump unbounded nested blobs
    assert "state_json" not in body
    raw = str(body)
    assert len(raw) < 8000

    wrds = handle_post(
        "/library/discover/sources/preview",
        {"source_id": "wrds_crsp_compustat"},
        stack,
    )
    assert wrds["status"] == 200
    assert wrds["body"]["status"] == "access_required"


def test_source_preview_failed_without_target(stack):
    from scripts.research_data_mcp.http_router import handle_post

    out = handle_post("/library/discover/sources/preview", {}, stack)
    assert out["status"] == 200
    assert out["body"]["status"] == "failed"


def test_refresh_subscription_non_executing_and_transitions(tmp_path):
    from scripts.research_data_mcp.discover_refresh_store import DiscoverRefreshStore

    store = DiscoverRefreshStore(tmp_path / "refresh.sqlite3")
    sub = store.create(source_id="gdelt", connector_id="gdelt", cadence="daily", destination="collection/acquired/news")
    assert sub["status"] == "active"
    assert sub["enabled"] is True
    assert sub["execution_mode"] == "non_executing"
    assert sub["auto_refresh"] is False
    assert sub["next_run_at"] is None
    assert sub["last_run_at"] is None

    paused = store.pause(sub["id"])
    assert paused["status"] == "paused"
    assert paused["enabled"] is False

    resumed = store.resume(sub["id"])
    assert resumed["status"] == "active"
    assert resumed["enabled"] is True
    assert resumed["execution_mode"] == "non_executing"
    assert resumed["next_run_at"] is None
    assert store.list_due() == []

    stopped = store.stop(sub["id"])
    assert stopped["status"] == "stopped"
    assert stopped["enabled"] is False

    with pytest.raises(ValueError, match="cannot resume"):
        store.resume(sub["id"])
    with pytest.raises(ValueError, match="cannot pause"):
        store.pause(sub["id"])


def test_refresh_subscription_http_routes(stack, tmp_path, monkeypatch):
    from scripts.research_data_mcp import discover_refresh_store as refresh_mod
    from scripts.research_data_mcp.http_router import handle_get, handle_post

    monkeypatch.setattr(
        refresh_mod,
        "discover_refresh_store_path",
        lambda repo_root: tmp_path / "discover_refresh_subscriptions.sqlite3",
    )
    # Force gateway to rebuild store against tmp path
    if hasattr(stack.gateway, "_discover_refresh_subscriptions_store"):
        delattr(stack.gateway, "_discover_refresh_subscriptions_store")

    created = handle_post(
        "/library/discover/subscriptions",
        {
            "source_id": "sec_edgar",
            "connector_id": "sec_edgar",
            "cadence": "weekly",
            "destination": "collection/acquired/filings",
        },
        stack,
    )
    assert created["status"] == 200
    sub = created["body"]
    assert sub["execution_mode"] == "non_executing"
    assert sub["auto_refresh"] is False
    sid = sub["id"]

    manual_run = handle_post(f"/library/discover/subscriptions/{sid}/run", {}, stack)
    assert manual_run["status"] == 200
    assert manual_run["body"]["fired"] == []
    assert manual_run["body"]["skipped"] == [
        {"subscription_id": sid, "reason": "subscription_non_executing"}
    ]

    paused = handle_post(f"/library/discover/subscriptions/{sid}/pause", {}, stack)
    assert paused["status"] == 200
    assert paused["body"]["status"] == "paused"

    listed = handle_get("/library/discover/subscriptions", {"limit": "20"}, stack)
    assert listed["status"] == 200
    assert any(row["id"] == sid for row in listed["body"]["subscriptions"])


def test_discover_history_filters_raw_jobs(stack, tmp_path, monkeypatch):
    from scripts.research_data_mcp import discover_intent_store as intent_mod
    from scripts.research_data_mcp import discover_refresh_store as refresh_mod
    from scripts.research_data_mcp.discover_history import build_discover_history
    from scripts.research_data_mcp.http_router import handle_get, handle_post

    monkeypatch.setattr(
        intent_mod,
        "discover_intent_store_path",
        lambda repo_root: tmp_path / "discover_intents.sqlite3",
    )
    monkeypatch.setattr(
        refresh_mod,
        "discover_refresh_store_path",
        lambda repo_root: tmp_path / "discover_refresh_subscriptions.sqlite3",
    )
    for attr in ("_discover_intents_store", "_discover_refresh_subscriptions_store"):
        if hasattr(stack.gateway, attr):
            delattr(stack.gateway, attr)

    intent = handle_post(
        "/library/discover/intents",
        {"research_need": "Need GDELT country shocks", "title": "GDELT shocks"},
        stack,
    )
    assert intent["status"] == 200
    intent_id = intent["body"]["id"]

    handle_post(
        "/library/discover/subscriptions",
        {"intent_id": intent_id, "source_id": "gdelt", "cadence": "manual"},
        stack,
    )

    history = handle_get("/library/discover/history", {"limit": "50"}, stack)
    assert history["status"] == 200
    body = history["body"]
    assert body["filters_applied"]["excludes_raw_global_jobs"] is True
    kinds = {row["kind"] for row in body["items"]}
    assert "intent" in kinds
    assert "subscription" in kinds

    # Raw unrelated job must not appear
    derived = build_discover_history(
        intents=[intent["body"]],
        subscriptions=[{"id": "sub1", "status": "active", "source_id": "gdelt", "enabled": True, "cadence": "manual", "execution_mode": "non_executing", "auto_refresh": False}],
        jobs=[
            {"id": "job-raw", "title": "Unrelated", "status": "pending_approval", "plan": {}, "request": {"source": "ops"}},
            {
                "id": "job-disc",
                "title": "Discover collect",
                "status": "pending_approval",
                "plan": {"discover_intent_id": intent_id},
                "request": {"source": "discover_ui"},
            },
        ],
        limit=50,
    )
    job_ids = {row.get("job_id") for row in derived["items"] if row.get("kind") == "collection_run"}
    assert "job-raw" not in job_ids
    assert "job-disc" in job_ids

    only_subs = handle_get("/library/discover/history", {"kind": "subscription", "limit": "20"}, stack)
    assert only_subs["status"] == 200
    assert all(row["kind"] == "subscription" for row in only_subs["body"]["items"])


def test_composer_cannot_approve_collection_or_schedule(stack):
    tools = stack.tools
    with pytest.raises(PermissionError, match="Collection approval"):
        tools.yzu_approve_job("job-x")
    with pytest.raises(PermissionError, match="Collection approval"):
        tools.procurement_approve_job("job-x")
    with pytest.raises(PermissionError, match="Collection approval"):
        tools.research_procure_approve_collect("camp-x")
    with pytest.raises(PermissionError, match="Connector approval"):
        tools.procurement_approve_connector("conn-x")
    with pytest.raises(PermissionError, match="Schedule execution"):
        tools.yzu_run_schedule("public_collection_daily")
    with pytest.raises(PermissionError, match="approval"):
        tools.yzu_submit_job('{"job_type":"source_probe","launchable":true}', auto_approve=True)


def test_route_catalog_includes_discover_explore_paths():
    from scripts.research_data_mcp.http_router import ROUTE_CATALOG

    paths = {(r["method"], r["path"]) for r in ROUTE_CATALOG}
    assert ("GET", "/library/discover/sources") in paths
    assert ("POST", "/library/discover/sources/preview") in paths
    assert ("GET", "/library/discover/history") in paths
    assert ("POST", "/library/discover/subscriptions") in paths
    assert ("POST", "/library/discover/subscriptions/{subscription_id}/pause") in paths


def test_source_search_dedupes_bigquery_to_one_source_capability(stack):
    """Default Explore collapses connector+source+provider BigQuery duplicates."""
    from scripts.research_data_mcp.http_router import handle_get

    out = handle_get("/library/discover/sources", {"q": "bigquery", "limit": "20"}, stack)
    assert out["status"] == 200
    body = out["body"]
    assert body["search_mode"] == "catalog"
    assert body["dedupe"]["per_capability"] is True
    results = body["results"]
    assert len(results) >= 1
    # One capability for the BigQuery connector — source preferred over connector.
    bq_rows = [
        r
        for r in results
        if str(r.get("connector_id") or "").lower() == "bigquery"
        or str(r.get("source_id") or "").lower() in {"bigquery", "bigquery_public"}
        or "bigquery" in str(r.get("candidate_key") or "").lower()
    ]
    kinds = {str(r.get("kind")) for r in bq_rows}
    assert "connector" not in kinds
    assert "provider" not in kinds
    assert any(r.get("kind") == "source" for r in bq_rows)
    # Distinct capability keys only once for connector:bigquery
    cap_ids = {
        str(r.get("connector_id") or r.get("source_id") or "")
        for r in bq_rows
        if str(r.get("connector_id") or "") == "bigquery"
    }
    assert len(cap_ids) <= 1 or all(r.get("kind") == "source" for r in bq_rows)
    assert sum(1 for r in results if str(r.get("connector_id") or "") == "bigquery") == 1


def test_source_search_explicit_connector_request_exposes_connector(stack):
    from scripts.research_data_mcp.discover_source_search import search_discover_sources

    default = search_discover_sources(stack.gateway.repo_root, "bigquery", limit=10)
    assert all(r.get("kind") != "connector" for r in default["results"])

    explicit = search_discover_sources(stack.gateway.repo_root, "bigquery", limit=10, prefer="connector")
    assert any(r.get("kind") == "connector" and r.get("connector_id") == "bigquery" for r in explicit["results"])


def test_source_search_live_federates_hf_and_datacite_with_monkeypatch(stack, monkeypatch):
    from scripts.research_data_mcp import discover_source_search as mod
    from scripts.research_data_mcp.http_router import handle_get

    def boom_hf(query, *, limit):
        return [], {"adapter": "huggingface", "ok": False, "error": "timeout", "returned": 0}

    monkeypatch.setattr(mod, "_live_search_huggingface", boom_hf)
    monkeypatch.setattr(
        mod,
        "_live_search_datacite",
        lambda query, *, limit: (
            [
                mod._normalize_live_candidate(
                    provider="DataCite",
                    title="Example Dataset",
                    url="https://doi.org/10.1234/example",
                    doi="10.1234/example",
                    external_id="10.1234/example",
                    capabilities=["doi_metadata"],
                    availability="public_datacite",
                )
            ],
            {"adapter": "datacite", "ok": True, "error": None, "returned": 1},
        ),
    )

    out = handle_get("/library/discover/sources", {"q": "climate", "live": "1", "limit": "20"}, stack)
    assert out["status"] == 200
    body = out["body"]
    assert body["remote_search"]["attempted"] is True
    adapters = {a["adapter"]: a for a in body["remote_search"]["adapters"]}
    assert adapters["huggingface"]["ok"] is False
    assert adapters["huggingface"]["error"]
    assert adapters["datacite"]["ok"] is True
    live_rows = [r for r in body["results"] if r.get("live_hit") or r.get("kind") == "live_candidate"]
    assert any(r.get("doi") == "10.1234/example" or "10.1234/example" in str(r.get("candidate_key")) for r in live_rows)
    for r in live_rows:
        assert r.get("candidate_key")
        assert r.get("provider")
        assert r.get("title") or r.get("label")


def test_source_search_live_default_remains_catalog_only(stack):
    from scripts.research_data_mcp.http_router import handle_get

    out = handle_get("/library/discover/sources", {"q": "gdelt", "limit": "10"}, stack)
    assert out["status"] == 200
    assert out["body"]["remote_search"]["attempted"] is False
    assert out["body"]["search_mode"] == "catalog"


def test_semantic_source_search_matches_capability_wording(stack, monkeypatch):
    """Query wording differs from source name but matches capability metadata."""
    from scripts.research_data_mcp import discover_source_search as mod
    from scripts.research_data_mcp.http_router import handle_get

    # Force honest lexical fallback (no slow/heavy embedding dependency in unit tests).
    monkeypatch.setattr(mod, "_try_embedding_source_search", lambda *a, **k: None)

    out = handle_get(
        "/library/discover/sources",
        {"q": "country news event shocks timeline", "semantic": "1", "limit": "10"},
        stack,
    )
    assert out["status"] == 200
    body = out["body"]
    assert body["search_mode"] in {
        "lexical_capability_fallback",
        "hybrid_capability",
        "hybrid_lexical_capability_fallback",
    }
    # Forced embedding miss → lexical base (possibly hybrid-reranked).
    assert (body.get("ranking") or {}).get("base_mode", "lexical_capability_fallback") == (
        "lexical_capability_fallback"
    )
    assert body["result_kind"] == "source"
    assert body["excludes"]["registry_datasets"] is True
    assert any(str(r.get("source_id") or "") == "gdelt" for r in body["results"])
    for r in body["results"]:
        assert r.get("kind") not in {"local_registry", "registry_dataset", "dataset"}
        assert str(r.get("candidate_key") or "").startswith(("source:", "url:", "doi:", "title:"))


def test_semantic_embedding_mode_reported_when_embeddings_return(stack, monkeypatch):
    from scripts.research_data_mcp import discover_source_search as mod

    corpus = mod._catalog_corpus(stack.gateway.repo_root)
    gdelt = next(r for r in corpus if r.get("source_id") == "gdelt")

    monkeypatch.setattr(
        mod,
        "_try_embedding_source_search",
        lambda corpus, query, *, limit: [(0.91, gdelt)],
    )
    out = mod.semantic_search_discover_sources(
        stack.gateway.repo_root,
        "global media conflict event graph",
        limit=5,
        prefer_embeddings=True,
    )
    assert out["search_mode"] in {"semantic_embedding", "hybrid_capability", "hybrid_semantic_embedding"}
    if out.get("ranking"):
        assert out["ranking"]["base_mode"] == "semantic_embedding"
    assert any(r.get("source_id") == "gdelt" for r in out["results"])
    assert all(r.get("kind") != "registry_dataset" for r in out["results"])


def test_post_source_preview_requires_desk_auth_policy():
    """POST preview can probe/persist; path is behind desk auth (GET is not gated by server)."""
    from scripts.research_data_mcp.desk_auth import path_requires_auth

    assert path_requires_auth("/library/discover/sources/preview") is True
    # Read-only discover sources list stays open.
    assert path_requires_auth("/library/discover/sources") is False


def test_refresh_subscription_response_never_claims_auto_refresh(stack, tmp_path, monkeypatch):
    from scripts.research_data_mcp import discover_refresh_store as refresh_mod
    from scripts.research_data_mcp.http_router import handle_post

    monkeypatch.setattr(
        refresh_mod,
        "discover_refresh_store_path",
        lambda repo_root: tmp_path / "discover_refresh_subscriptions.sqlite3",
    )
    if hasattr(stack.gateway, "_discover_refresh_subscriptions_store"):
        delattr(stack.gateway, "_discover_refresh_subscriptions_store")

    created = handle_post(
        "/library/discover/subscriptions",
        {"source_id": "gdelt", "cadence": "daily", "destination": "collection/acquired/news"},
        stack,
    )
    assert created["status"] == 200
    body = created["body"]
    assert body["execution_mode"] == "non_executing"
    assert body["auto_refresh"] is False
    assert body.get("next_run_at") is None
    # No scheduled/auto-refresh marketing language.
    blob = str(body).lower()
    assert "auto-refreshing" not in blob
    assert "scheduler will run" not in blob


def test_semantic_onchain_query_ranks_crypto_ahead_of_governance_real_catalog(stack):
    """Regression: blockchain/tx NL queries must prefer on-chain sources over SEC/MOPS.

    Uses the real databank source catalog (not mocks). Hybrid ranking must place
    ethereum/bigquery/onchain_crypto capability ahead of governance_regulatory.
    """
    from scripts.research_data_mcp.discover_source_search import semantic_search_discover_sources
    from scripts.research_data_mcp.http_router import handle_get

    out = semantic_search_discover_sources(
        stack.gateway.repo_root,
        "blockchain transaction history",
        limit=12,
        prefer_embeddings=True,
    )
    assert out["result_kind"] == "source"
    assert out["excludes"]["registry_datasets"] is True
    assert out.get("ranking", {}).get("rule") == "hybrid_capability"
    assert "onchain" in (out.get("ranking", {}).get("domains") or [])

    results = out["results"]
    assert results
    ids = [str(r.get("source_id") or "") for r in results]

    def _pos(sid: str) -> int:
        try:
            return ids.index(sid)
        except ValueError:
            return 10**9

    onchain_pos = min(
        _pos("ethereum_onchain"),
        _pos("bigquery_public"),
        _pos("coingecko"),
        _pos("nft_opensea"),
    )
    gov_pos = min(_pos("sec_edgar"), _pos("mops_taiwan"))
    assert onchain_pos < gov_pos, (
        f"on-chain source must outrank governance; ids={ids[:8]} "
        f"onchain_pos={onchain_pos} gov_pos={gov_pos}"
    )
    eth_bq_pos = min(_pos("ethereum_onchain"), _pos("bigquery_public"))
    assert eth_bq_pos < gov_pos, f"ethereum/bigquery must beat SEC/MOPS; ids={ids[:8]}"
    top_caps = {str(c).lower() for c in (results[0].get("capabilities") or [])}
    assert "onchain_crypto" in top_caps or results[0].get("source_id") in {
        "ethereum_onchain",
        "bigquery_public",
        "coingecko",
        "nft_opensea",
    }
    assert any(r.get("rank_signals") or r.get("rank_explanation") for r in results[:3])

    http = handle_get(
        "/library/discover/sources",
        {"q": "blockchain transaction history", "semantic": "1", "limit": "12"},
        stack,
    )
    assert http["status"] == 200
    http_ids = [str(r.get("source_id") or "") for r in http["body"]["results"]]

    def _hpos(sid: str) -> int:
        try:
            return http_ids.index(sid)
        except ValueError:
            return 10**9

    assert min(_hpos("ethereum_onchain"), _hpos("bigquery_public")) < min(
        _hpos("sec_edgar"), _hpos("mops_taiwan")
    )


def test_semantic_onchain_query_hybrid_fixes_bad_embedding_order(stack, monkeypatch):
    """Even if embeddings prefer SEC/MOPS, hybrid capability signals must invert that."""
    from scripts.research_data_mcp import discover_source_search as mod

    corpus = mod._catalog_corpus(stack.gateway.repo_root)
    by_id = {str(r.get("source_id") or ""): r for r in corpus}
    bad = [
        (0.2240, by_id["sec_edgar"]),
        (0.2132, by_id["mops_taiwan"]),
        (0.2019, by_id["nft_opensea"]),
        (0.2009, by_id["ethereum_onchain"]),
        (0.1518, by_id["bigquery_public"]),
        (0.1376, by_id["coingecko"]),
    ]
    monkeypatch.setattr(mod, "_try_embedding_source_search", lambda *a, **k: list(bad))
    out = mod.semantic_search_discover_sources(
        stack.gateway.repo_root,
        "blockchain transaction history",
        limit=10,
        prefer_embeddings=True,
    )
    assert out["ranking"]["base_mode"] == "semantic_embedding"
    ids = [str(r.get("source_id") or "") for r in out["results"]]
    eth_bq = min(i for i, x in enumerate(ids) if x in {"ethereum_onchain", "bigquery_public"})
    for gov in ("sec_edgar", "mops_taiwan"):
        if gov in ids:
            assert ids.index(gov) > eth_bq
    assert ids[0] in {"ethereum_onchain", "bigquery_public", "nft_opensea", "coingecko"}


def test_live_diversify_helper_deterministic_provider_cap():
    """Deterministic round-robin / soft-cap diversification across live providers."""
    from scripts.research_data_mcp.discover_source_search import (
        _diversify_live_hits,
        _normalize_live_candidate,
    )

    hits = []
    for i in range(5):
        hits.append(
            _normalize_live_candidate(
                provider="Hugging Face",
                title=f"HF {i}",
                external_id=f"hf-{i}",
                url=f"https://huggingface.co/datasets/x-{i}",
            )
        )
    for i in range(5):
        hits.append(
            _normalize_live_candidate(
                provider="DataCite",
                title=f"DC {i}",
                doi=f"10.9/{i}",
                external_id=f"10.9/{i}",
            )
        )
    out = _diversify_live_hits(hits, limit=5)
    assert [r["provider"] for r in out] == [
        "Hugging Face",
        "DataCite",
        "Hugging Face",
        "DataCite",
        "Hugging Face",
    ]
    assert [r["external_id"] for r in out if r["provider"] == "Hugging Face"] == [
        "hf-0",
        "hf-1",
        "hf-2",
    ]
    assert [r["external_id"] for r in out if r["provider"] == "DataCite"] == [
        "10.9/0",
        "10.9/1",
    ]


def test_live_results_round_robin_diversify_hf_and_datacite(stack, monkeypatch):
    """GET live=1 with limit=5 must return both HF and DataCite when both have candidates."""
    from scripts.research_data_mcp import discover_source_search as mod
    from scripts.research_data_mcp.http_router import handle_get

    def fake_hf(query, *, limit):
        rows = [
            mod._normalize_live_candidate(
                provider="Hugging Face",
                title=f"HF Stablecoin {i}",
                url=f"https://huggingface.co/datasets/hf-stable-{i}",
                external_id=f"org/hf-stable-{i}",
                capabilities=["dataset_cards", "stablecoin"],
                availability="public_hub",
            )
            for i in range(limit)
        ]
        return rows, {
            "adapter": "huggingface",
            "ok": True,
            "error": None,
            "returned": len(rows),
        }

    def fake_dc(query, *, limit):
        rows = [
            mod._normalize_live_candidate(
                provider="DataCite",
                title=f"DataCite Stablecoin {i}",
                url=f"https://doi.org/10.1234/stable-{i}",
                doi=f"10.1234/stable-{i}",
                external_id=f"10.1234/stable-{i}",
                capabilities=["doi_metadata", "stablecoin"],
                availability="public_datacite",
            )
            for i in range(limit)
        ]
        return rows, {
            "adapter": "datacite",
            "ok": True,
            "error": None,
            "returned": len(rows),
        }

    monkeypatch.setattr(mod, "_live_search_huggingface", fake_hf)
    monkeypatch.setattr(mod, "_live_search_datacite", fake_dc)

    # Use a query that does not match local catalog tokens so live fills the window.
    out = handle_get(
        "/library/discover/sources",
        {"q": "zzlive-diversify-stablecoin-probe", "live": "1", "limit": "5"},
        stack,
    )
    assert out["status"] == 200
    body = out["body"]
    assert body["remote_search"]["attempted"] is True
    assert body["remote_search"].get("diversification", {}).get("rule") == (
        "round_robin_provider_soft_cap"
    )
    adapters = {a["adapter"]: a for a in body["remote_search"]["adapters"]}
    assert adapters["huggingface"]["ok"] is True
    assert adapters["datacite"]["ok"] is True
    assert adapters["huggingface"]["returned"] >= 1
    assert adapters["datacite"]["returned"] >= 1

    live_rows = [
        r for r in body["results"] if r.get("live_hit") or r.get("kind") == "live_candidate"
    ]
    assert len(live_rows) == 5
    providers = {str(r.get("provider") or "") for r in live_rows}
    assert "Hugging Face" in providers
    assert "DataCite" in providers
    # Round-robin interleaves providers at the head of the window.
    assert live_rows[0]["provider"] != live_rows[1]["provider"]
