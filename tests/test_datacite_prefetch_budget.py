"""DataCite prefetch budget and bounded vault shard scans."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import scripts.research_data_mcp.datacite_prefetch as prefetch_mod
import scripts.research_data_mcp.datacite_vault_search as vault_mod
from scripts.research_data_mcp.datacite_prefetch import _merge_datacite_rows, prefetch_datacite_layer
from scripts.research_data_mcp.datacite_vault_search import search_shard_indexes, search_vault_topics_fast


def test_merge_datacite_rows_dedupes_by_doi():
    rows = _merge_datacite_rows(
        [{"doi": "10.1/a", "title": "a"}],
        [{"doi": "10.1/a", "title": "dup"}, {"doi": "10.1/b", "title": "b"}],
        limit=5,
    )
    assert len(rows) == 2
    assert {r["doi"] for r in rows} == {"10.1/a", "10.1/b"}


def test_prefetch_datacite_layer_parallel_api(monkeypatch, tmp_path: Path):
    repo = tmp_path
    deep_called: list[str] = []

    monkeypatch.setattr(prefetch_mod, "search_curated_datasets", lambda *_a, **_k: [])
    monkeypatch.setattr(vault_mod, "search_curated_fts", lambda *_a, **_k: [])
    monkeypatch.setattr(vault_mod, "search_scrape_snippets_fts", lambda *_a, **_k: [])
    monkeypatch.setattr(
        vault_mod,
        "search_vault_topics_deep",
        lambda *_a, **_k: deep_called.append("deep") or [],
    )

    api_called: list[str] = []

    def fast_api(query, **kwargs):
        api_called.append(query)
        return [{"doi": "10.5555/api", "title": "API hit", "source": "datacite_api", "score": 4.0}]

    monkeypatch.setattr(prefetch_mod, "search_datacite_api", fast_api)

    rows = prefetch_datacite_layer(repo, "mops", limit=4, budget_seconds=0.35)
    assert api_called == ["mops"]
    assert deep_called == []
    assert any(r.get("doi") == "10.5555/api" for r in rows)


def test_prefetch_datacite_layer_deep_vault_opt_in(monkeypatch, tmp_path: Path):
    repo = tmp_path
    deep_called: list[str] = []

    monkeypatch.setattr(prefetch_mod, "search_curated_datasets", lambda *_a, **_k: [])
    monkeypatch.setattr(vault_mod, "search_curated_fts", lambda *_a, **_k: [])
    monkeypatch.setattr(vault_mod, "search_scrape_snippets_fts", lambda *_a, **_k: [])
    monkeypatch.setattr(prefetch_mod, "search_datacite_api", lambda *_a, **_k: [])
    monkeypatch.setattr(
        vault_mod,
        "search_vault_topics_deep",
        lambda *_a, **_k: deep_called.append("deep") or [{"doi": "10.1/deep", "title": "deep"}],
    )

    rows = prefetch_datacite_layer(repo, "mops", limit=4, budget_seconds=1.0, deep_vault=True)
    assert deep_called == ["deep"]
    assert any(r.get("doi") == "10.1/deep" for r in rows)


def test_search_shard_indexes_respects_deadline(monkeypatch):
    repo = MagicMock()

    def slow_shard(*_args, **_kwargs):
        time.sleep(0.25)
        return [{"doi": "10.1/x", "title": "x", "score": 1.0}]

    entries = [{"shard": f"s{i}"} for i in range(8)]
    monkeypatch.setattr(vault_mod, "list_shard_indexes", lambda _repo: entries)
    monkeypatch.setattr(vault_mod, "shard_index_candidates", lambda _repo, **kwargs: [Path("/tmp/shards")])
    monkeypatch.setattr(vault_mod, "_search_single_vault_fts", slow_shard)

    deadline = time.monotonic() + 0.3
    rows = search_shard_indexes(repo, "mops", limit=4, max_shards=8, deadline=deadline)
    assert len(rows) <= 4


def test_search_vault_topics_fast_only_local_layers(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        vault_mod,
        "search_curated_fts",
        lambda *_a, **_k: [{"doi": "10.1/fast", "title": "fast", "score": 5.0}],
    )
    monkeypatch.setattr(vault_mod, "search_scrape_snippets_fts", lambda *_a, **_k: [])
    rows = search_vault_topics_fast(tmp_path, "mops", limit=3)
    assert rows[0]["doi"] == "10.1/fast"
