"""Zenodo mints a DOI per version, so one work arrives as several rows.

The search for container shipping freight rates returned "Shipping Container
Chassis in the U. S." twice, as zenodo.3675419 and .3675420. They are not
duplicates of one row — they are two DOIs DataCite itself links with
IsVersionOf. Fold on that declared link, and say what was folded.
"""

from __future__ import annotations

from scripts.research_data_mcp.datacite_client import datacite_row, version_family
from scripts.research_data_mcp.datacite_prefetch import _merge_datacite_rows


def _attrs(doi: str, related: list[tuple[str, str, str]] | None = None) -> dict:
    return {
        "doi": doi,
        "titles": [{"title": "Shipping Container Chassis in the U. S."}],
        "relatedIdentifiers": [
            {"relationType": rel, "relatedIdentifier": ident, "relatedIdentifierType": kind}
            for rel, ident, kind in (related or [])
        ],
    }


def _row(doi: str, version_of: list[str] | None = None, score: float = 1.0) -> dict:
    return {"doi": doi, "title": "t", "score": score, "version_of": version_of or []}


def test_a_declared_version_link_is_extracted():
    attrs = _attrs("10.5281/zenodo.3675420", [("IsVersionOf", "10.5281/zenodo.3675419", "DOI")])
    assert version_family(attrs) == ["10.5281/zenodo.3675419"]


def test_a_record_declaring_itself_a_version_of_itself_is_ignored():
    """zenodo.20625754 does exactly this in live DataCite data."""
    attrs = _attrs("10.5281/zenodo.20625754",
                   [("IsVersionOf", "10.5281/zenodo.20625754", "DOI")])
    assert version_family(attrs) == []


def test_a_related_url_is_not_treated_as_a_version():
    attrs = _attrs("10.5281/zenodo.1", [("IsIdenticalTo", "https://example.org/ep/1", "URL")])
    assert version_family(attrs) == []


def test_an_unrelated_relation_is_not_a_version():
    attrs = _attrs("10.5281/zenodo.1", [("IsPartOf", "2965-9302", "ISSN")])
    assert version_family(attrs) == []


def test_a_doi_url_is_normalised_before_comparison():
    attrs = _attrs("10.5281/zenodo.2", [("HasVersion", "https://doi.org/10.5281/ZENODO.3", "DOI")])
    assert version_family(attrs) == ["10.5281/zenodo.3"]


def test_datacite_row_carries_the_family():
    row = datacite_row({"attributes": _attrs(
        "10.5281/zenodo.3675420", [("IsVersionOf", "10.5281/zenodo.3675419", "DOI")])})
    assert row["version_of"] == ["10.5281/zenodo.3675419"]


def test_two_versions_of_one_work_collapse_to_one_row():
    merged = _merge_datacite_rows(
        [_row("10.5281/zenodo.3675420", ["10.5281/zenodo.3675419"], score=3.70),
         _row("10.5281/zenodo.3675419", ["10.5281/zenodo.3675420"], score=3.55)],
        limit=8,
    )
    assert len(merged) == 1
    assert merged[0]["doi"] == "10.5281/zenodo.3675420"
    assert merged[0]["version_siblings"] == ["10.5281/zenodo.3675419"]


def test_the_folded_doi_is_kept_not_discarded():
    merged = _merge_datacite_rows(
        [_row("10.5281/zenodo.a", ["10.5281/zenodo.b"]), _row("10.5281/zenodo.b")],
        limit=8,
    )
    assert merged[0]["version_siblings"] == ["10.5281/zenodo.b"]


def test_folding_works_when_only_the_later_row_declares_the_link():
    merged = _merge_datacite_rows(
        [_row("10.5281/zenodo.a"), _row("10.5281/zenodo.b", ["10.5281/zenodo.a"])],
        limit=8,
    )
    assert len(merged) == 1
    assert merged[0]["doi"] == "10.5281/zenodo.a"


def test_unrelated_records_are_never_folded():
    merged = _merge_datacite_rows(
        [_row("10.5281/zenodo.a"), _row("10.5281/zenodo.b")], limit=8,
    )
    assert [r["doi"] for r in merged] == ["10.5281/zenodo.a", "10.5281/zenodo.b"]


def test_the_same_doi_twice_still_dedupes_without_claiming_a_version():
    merged = _merge_datacite_rows(
        [_row("10.5281/zenodo.a"), _row("10.5281/zenodo.a")], limit=8,
    )
    assert len(merged) == 1
    assert merged[0].get("version_siblings") is None


def test_a_row_with_no_doi_is_skipped():
    assert _merge_datacite_rows([_row(""), _row("10.5281/zenodo.a")], limit=8)[0]["doi"] == "10.5281/zenodo.a"
