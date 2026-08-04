"""Registry paths must resolve to bytes wherever the desk actually keeps them.

Several checkouts share one registry by symlink -- the front door, the security
checkout and the runtime-integration checkout all resolve
``config/research_query_registry.json`` to the same file -- while each keeps its
own ``data_lake``.  Registry paths are relative, so they resolved against
whichever checkout happened to be serving, and the serving checkout holds a
near-empty stub.

Measured against the live registry (154 disk-probed datasets), that reported
**1** dataset as query-ready.  Every other dataset was declared unavailable
while its bytes sat on disk in a sibling checkout.  Because the assessment
engine caps every coverage dimension at ``unverified`` when a dataset is not
query-ready, a verdict of ``covered`` was unreachable for the entire corpus
regardless of how good the coverage metadata was.

Two distinct defects produced it, and each is pinned below:

1. resolution never looked outside the serving checkout -- and ``hot`` paths
   (which include ``data_lake/sec``, ``data_lake/research_panels``,
   ``data_lake/procured``) returned repo-local *immediately*, bypassing every
   fallback;
2. glob patterns were existence-tested literally, and a pattern never exists as
   a path, so every glob-backed dataset fell through to the stub root; the
   usability count then required ``is_file()``, missing collections written as
   timestamped run directories.

After both fixes the same probe reports **106** query-ready with **zero** false
positives (each verified to resolve to a path carrying bytes).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research_data_mcp.data_paths import data_lake_search_roots
from scripts.research_data_mcp.storage_tiers import resolve_data_path_tiered
from scripts.sync_materialized_registry import _has_bytes


def _make_repo(root, *, hot_prefixes=("data_lake/sec",), data_roots=()):
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "storage_tiers.json").write_text(
        json.dumps(
            {
                "tiers": {
                    "hot": {"path_prefixes": list(hot_prefixes), "data_roots": list(data_roots)},
                    "cache": {"bulk_subdirs": []},
                },
                "rules": {"prefer_cache_for_bulk_reads": False},
            }
        ),
        encoding="utf-8",
    )
    return root


def test_repo_local_path_still_wins_when_it_exists(tmp_path):
    """No path that resolves today may change: the serving checkout stays first."""
    serving = _make_repo(tmp_path / "serving", data_roots=[str(tmp_path / "sibling")])
    sibling = _make_repo(tmp_path / "sibling")
    for base in (serving, sibling):
        (base / "data_lake/sec").mkdir(parents=True)
        (base / "data_lake/sec/company_tickers.json").write_text("{}", encoding="utf-8")

    resolved = resolve_data_path_tiered(serving, "data_lake/sec/company_tickers.json")
    assert resolved == (serving / "data_lake/sec/company_tickers.json").resolve()


def test_hot_path_falls_back_to_sibling_root(tmp_path):
    """The 153-dataset bug: hot paths returned repo-local without ever looking."""
    serving = _make_repo(tmp_path / "serving", data_roots=[str(tmp_path / "sibling")])
    sibling = _make_repo(tmp_path / "sibling")
    (sibling / "data_lake/sec").mkdir(parents=True)
    (sibling / "data_lake/sec/company_tickers.json").write_text("{}", encoding="utf-8")

    resolved = resolve_data_path_tiered(serving, "data_lake/sec/company_tickers.json")
    assert resolved == (sibling / "data_lake/sec/company_tickers.json").resolve()


def test_unmatched_path_stays_repo_local_so_writes_land_locally(tmp_path):
    """An absent path must still resolve into the serving checkout, not a sibling."""
    serving = _make_repo(tmp_path / "serving", data_roots=[str(tmp_path / "sibling")])
    _make_repo(tmp_path / "sibling")
    resolved = resolve_data_path_tiered(serving, "data_lake/sec/not_procured_yet.json")
    assert resolved == (serving / "data_lake/sec/not_procured_yet.json").resolve()


def test_glob_pattern_resolves_by_its_wildcard_free_prefix(tmp_path):
    """A pattern never exists literally, so testing it sent every glob to the stub."""
    serving = _make_repo(tmp_path / "serving", data_roots=[str(tmp_path / "sibling")])
    sibling = _make_repo(tmp_path / "sibling")
    (sibling / "data_lake/entity_mapping/asia").mkdir(parents=True)

    resolved = resolve_data_path_tiered(serving, "data_lake/entity_mapping/asia/*")
    assert resolved == (sibling / "data_lake/entity_mapping/asia/*").resolve()


def test_absolute_registry_paths_are_untouched(tmp_path):
    serving = _make_repo(tmp_path / "serving")
    target = tmp_path / "elsewhere" / "file.json"
    assert resolve_data_path_tiered(serving, str(target)) == target.resolve()


def test_env_var_extends_search_roots(tmp_path, monkeypatch):
    serving = _make_repo(tmp_path / "serving")
    sibling = _make_repo(tmp_path / "sibling")
    monkeypatch.setenv("RESEARCH_DATA_ROOTS", str(sibling))
    roots = data_lake_search_roots(serving)
    assert roots[0] == serving.resolve()
    assert sibling.resolve() in roots


def test_search_roots_skip_paths_that_do_not_exist(tmp_path):
    serving = _make_repo(tmp_path / "serving", data_roots=[str(tmp_path / "never_created")])
    assert data_lake_search_roots(serving) == [serving.resolve()]


# --- materialization usability ------------------------------------------------

def test_run_directory_with_files_counts_as_materialized(tmp_path):
    """Collections are written as timestamped run dirs; is_file() alone missed them."""
    run = tmp_path / "asia" / "20260521T072629Z"
    run.mkdir(parents=True)
    (run / "mapping.json").write_text('{"a":1}', encoding="utf-8")
    assert _has_bytes(tmp_path / "asia" / "20260521T072629Z")


def test_empty_directory_is_not_materialized(tmp_path):
    empty = tmp_path / "opensea"
    empty.mkdir()
    assert not _has_bytes(empty)


def test_directory_of_empty_files_is_not_materialized(tmp_path):
    """Zero-byte placeholders must not read as held data."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "placeholder.json").write_text("", encoding="utf-8")
    assert not _has_bytes(run)


def test_zero_byte_file_is_not_materialized(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("", encoding="utf-8")
    assert not _has_bytes(path)


def test_missing_path_is_not_materialized(tmp_path):
    assert not _has_bytes(tmp_path / "absent")


def test_directory_walk_is_bounded(tmp_path):
    """A pathological tree must not stall a registry sync."""
    deep = tmp_path / "wide"
    deep.mkdir()
    for i in range(50):
        (deep / f"empty_{i}.json").write_text("", encoding="utf-8")
    assert not _has_bytes(deep, max_entries=10)


# --- query proof ---------------------------------------------------------------
#
# The assessment engine only treats a dimension as verified given "observed query
# proof" (materialization.query_verified / query_smoke.ok). Nothing produced that
# for rows already in the registry -- prove_query_smoke ran only on the promotion
# path for newly acquired datasets -- so every dimension capped at "unverified"
# and a verdict of "covered" was unreachable by construction, independent of
# coverage metadata quality.

def test_unsupported_smoke_backend_yields_no_false_proof(monkeypatch):
    """No smoke path must leave the row honest, not assert a proof never obtained."""
    import scripts.sync_materialized_registry as m

    monkeypatch.setattr(
        "scripts.yzu_cluster.acquisitions.prove_query_smoke",
        lambda *a, **k: {"ok": False, "error": "unsupported smoke backend weird"},
    )
    assert m._prove_smoke(Path("/tmp"), {"dataset_id": "a", "backend": "weird"}) is None


def test_smoke_failure_does_not_break_the_sync(monkeypatch):
    """A prover that raises must not take the whole registry sync down with it."""
    import scripts.sync_materialized_registry as m

    def _boom(*_a, **_k):
        raise RuntimeError("parser exploded")

    monkeypatch.setattr("scripts.yzu_cluster.acquisitions.prove_query_smoke", _boom)
    result = m._prove_smoke(Path("/tmp"), {"dataset_id": "a", "backend": "local_csv_file"})
    assert result == {"ok": False, "error": "parser exploded"}


def test_successful_smoke_is_passed_through(monkeypatch):
    import scripts.sync_materialized_registry as m

    monkeypatch.setattr(
        "scripts.yzu_cluster.acquisitions.prove_query_smoke",
        lambda *a, **k: {"ok": True, "rows": 3},
    )
    assert m._prove_smoke(Path("/tmp"), {"dataset_id": "a", "backend": "local_csv_file"})["ok"] is True
