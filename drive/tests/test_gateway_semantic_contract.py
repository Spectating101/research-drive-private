from pathlib import Path

from scripts.research_data_mcp.gateway import ResearchDataGateway


class _SubjectOnlyIndex:
    _embedding_model = "stub"

    @staticmethod
    def subject_search(*_args, **_kwargs):
        return [
            {
                "id": "stablecoin_panel",
                "subject_score": 0.82,
                "metadata": {
                    "title": "Stablecoin protocol panel",
                    "description": "Protocol evidence",
                },
            }
        ]

    @staticmethod
    def semantic_search(*_args, **_kwargs):
        return []

    @staticmethod
    def doc_index_for(_dataset_id):
        return None


def test_subject_ranked_discover_rows_keep_their_score(monkeypatch):
    """Subject-first rows must not become false zero-score Discover matches."""
    from scripts.research_data_mcp import semantic_index

    monkeypatch.setattr(semantic_index, "get_semantic_index", lambda _gateway: _SubjectOnlyIndex())
    gateway = ResearchDataGateway.__new__(ResearchDataGateway)
    gateway.repo_root = Path(".")

    out = gateway.semantic_discover("stablecoin market risk", limit=8)

    assert out["total"] == 1
    assert out["rows"][0]["semantic_score"] == 0.82


def test_semantic_source_supplement_cannot_bypass_source_relevance_gate(monkeypatch):
    """A weak generic semantic route must not displace a direct source match."""
    gateway = ResearchDataGateway.__new__(ResearchDataGateway)
    gateway.repo_root = Path(".")
    monkeypatch.setattr(
        "scripts.research_data_mcp.discover_source_search.search_discover_sources",
        lambda *_args, **_kwargs: {
            "results": [{
                "source_id": "coingecko",
                "title": "Stablecoin market API",
                "capabilities": ["onchain_crypto"],
                "query_relevance": 3.0,
            }],
            "total": 1,
            "index_miss": False,
        },
    )
    monkeypatch.setattr(
        gateway,
        "semantic_source_routes",
        lambda *_args, **_kwargs: [{
            "source_id": "yfinance_public",
            "title": "Yahoo Finance",
            "capabilities": ["daily_prices"],
            "match_type": "semantic",
            "score": 0.25,
        }],
    )

    out = gateway.discover_source_search("stablecoin market risk", limit=8)

    assert [row["source_id"] for row in out["results"]] == ["coingecko"]
    assert "semantic_routes_added" not in out
