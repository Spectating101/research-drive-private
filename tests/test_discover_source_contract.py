#!/usr/bin/env python3
"""Discover source-search contract — plain text, identity, exact dedupe, offering taxonomy."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DRIVE = REPO / "drive"


def test_plain_text_description_strips_html_and_entities():
    from scripts.research_data_mcp.discover_source_contract import plain_text_description

    raw = '<p>GDELT <b>events</b> &amp; “news” — see <a href="https://x.test">link</a></p>'
    out = plain_text_description(raw)
    assert "<" not in out
    assert ">" not in out
    assert "&amp;" not in out
    assert "GDELT" in out
    assert "events" in out
    assert "news" in out


def test_classify_offering_distinguishes_collectible_paper_catalogue_metadata():
    from scripts.research_data_mcp.discover_source_contract import classify_offering

    assert (
        classify_offering(
            {
                "kind": "source",
                "source_id": "gdelt",
                "collect_via": ["http_manifest"],
                "access_mode": "live_connector",
            }
        )
        == "collectible_data"
    )
    assert (
        classify_offering(
            {
                "kind": "provider",
                "source_id": "openalex",
                "capabilities": ["scholarly_works"],
            }
        )
        == "paper"
    )
    assert (
        classify_offering(
            {
                "kind": "live_candidate",
                "provider": "DataCite",
                "doi": "10.5281/zenodo.1",
                "capabilities": ["doi_metadata"],
                "inspect_only": True,
            }
        )
        == "catalogue_record"
    )
    assert (
        classify_offering(
            {
                "kind": "live_candidate",
                "provider": "Hugging Face",
                "inspect_only": True,
                "capabilities": ["dataset_cards"],
                "trust_tier": "inspect_only",
            }
        )
        == "metadata_only"
    )


def test_finalize_discover_rows_stable_identity_exact_dedupe_preserves_distinct():
    from scripts.research_data_mcp.discover_source_contract import finalize_discover_rows

    rows = [
        {
            "kind": "source",
            "source_id": "gdelt",
            "provider": "GDELT",
            "label": "GDELT",
            "collect_via": ["http_manifest"],
            "access_mode": "materialized_bulk",
            "notes": "<b>Global</b> events",
            "candidate_key": "source:gdelt:gdelt",
        },
        {
            # exact duplicate of the same candidate_key
            "kind": "source",
            "source_id": "gdelt",
            "provider": "GDELT",
            "label": "GDELT mirror",
            "collect_via": ["http_manifest"],
            "candidate_key": "source:gdelt:gdelt",
            "notes": "duplicate row",
        },
        {
            "kind": "live_candidate",
            "provider": "DataCite",
            "title": "Paper A",
            "doi": "10.5281/zenodo.1",
            "capabilities": ["doi_metadata"],
            "inspect_only": True,
            "notes": "<em>Abstract</em> one",
        },
        {
            "kind": "live_candidate",
            "provider": "DataCite",
            "title": "Paper B",
            "doi": "10.5281/zenodo.2",
            "capabilities": ["doi_metadata"],
            "inspect_only": True,
            "notes": "Abstract two",
        },
    ]
    out = finalize_discover_rows(rows)
    keys = [r["candidate_key"] for r in out]
    assert keys.count("source:gdelt:gdelt") == 1
    assert "doi:10.5281/zenodo.1" in keys
    assert "doi:10.5281/zenodo.2" in keys
    gdelt = next(r for r in out if r["candidate_key"] == "source:gdelt:gdelt")
    assert gdelt["description"] == "Global events"
    assert "<" not in gdelt["description"]
    assert gdelt["offering_kind"] == "collectible_data"
    assert gdelt["candidate_key"]
    paper = next(r for r in out if r["candidate_key"] == "doi:10.5281/zenodo.1")
    assert paper["offering_kind"] == "catalogue_record"
    assert "<" not in (paper.get("description") or "")


def test_search_discover_sources_emits_contract_fields(repo_root=DRIVE):
    from scripts.research_data_mcp.discover_source_search import search_discover_sources

    out = search_discover_sources(repo_root, "gdelt", limit=8, live=False, semantic=False)
    rows = out.get("results") or []
    if not rows:
        pytest.skip("no local catalog hits for gdelt")
    keys = [r.get("candidate_key") for r in rows]
    assert all(keys), rows
    assert len(keys) == len(set(keys))
    for row in rows:
        desc = row.get("description") or row.get("notes") or ""
        assert "<" not in str(desc)
        assert row.get("offering_kind") in {
            "collectible_data",
            "paper",
            "catalogue_record",
            "metadata_only",
        }
