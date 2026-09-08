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
