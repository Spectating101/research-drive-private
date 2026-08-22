"""Keyword recall — not ranking — is the binding constraint on the curated
corpus, so a thin FTS pass is widened by meaning. Semantic rows are supplementary
and must stay labelled; the floor exists to keep nonsense out, and it is NOT a
claim that a surviving hit is relevant."""

import ast
from pathlib import Path

DRIVE = Path(__file__).resolve().parents[1]
PREFETCH = DRIVE / "scripts/research_data_mcp/datacite_prefetch.py"
VAULT = DRIVE / "scripts/research_data_mcp/datacite_vault_search.py"


def _fn(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name), None
    )


def _names(node):
    out = set()
    for c in ast.walk(node):
        if isinstance(c, ast.Call):
            out.add(c.func.id if isinstance(c.func, ast.Name) else getattr(c.func, "attr", ""))
        elif isinstance(c, ast.ImportFrom):
            out |= {a.name for a in c.names}
    return out


def test_live_search_path_consults_semantic():
    fn = _fn(PREFETCH, "prefetch_datacite_layer")
    assert fn is not None
    assert "search_curated_semantic" in _names(fn)


def test_semantic_fill_is_switchable():
    assert _fn(PREFETCH, "semantic_fill_enabled") is not None
    assert "semantic_fill_enabled" in _names(_fn(PREFETCH, "prefetch_datacite_layer"))


def test_semantic_has_a_score_floor():
    assert _fn(VAULT, "_semantic_floor") is not None
    assert "_semantic_floor" in _names(_fn(VAULT, "search_curated_semantic"))


def test_floor_default_and_override():
    import os

    from scripts.research_data_mcp.datacite_vault_search import _semantic_floor

    prior = os.environ.pop("RESEARCH_SEMANTIC_MIN_SCORE", None)
    try:
        assert _semantic_floor() == 0.40
        os.environ["RESEARCH_SEMANTIC_MIN_SCORE"] = "0.55"
        assert _semantic_floor() == 0.55
        os.environ["RESEARCH_SEMANTIC_MIN_SCORE"] = "not-a-number"
        assert _semantic_floor() == 0.40
    finally:
        os.environ.pop("RESEARCH_SEMANTIC_MIN_SCORE", None)
        if prior is not None:
            os.environ["RESEARCH_SEMANTIC_MIN_SCORE"] = prior


def test_semantic_returns_empty_without_an_index(tmp_path):
    from scripts.research_data_mcp.datacite_vault_search import search_curated_semantic

    assert search_curated_semantic(tmp_path, "anything", limit=5) == []


def test_blank_query_is_not_searched(tmp_path):
    from scripts.research_data_mcp.datacite_vault_search import search_curated_semantic

    assert search_curated_semantic(tmp_path, "   ", limit=5) == []


def test_warmup_pages_in_the_vector_matrix():
    assert "search_curated_semantic" in _names(_fn(PREFETCH, "warm_search_indexes"))
