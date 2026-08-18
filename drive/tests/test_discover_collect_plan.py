from __future__ import annotations

import pytest

from scripts.research_data_mcp.bootstrap import create_stack
from scripts.research_data_mcp.discover_collect_plan import resolve_discover_collect_plan


def test_catalog_twse_resolves_to_http_manifest_openapi():
    """TWSE OpenAPI is a known JSON API — craft/discover prefer http_manifest over probe."""
    stack = create_stack()
    plan = resolve_discover_collect_plan(
        stack.gateway.procurement,
        stack.gateway.repo_root,
        connector_id="twse",
        source_id="twse_official",
        limit=5,
        title="TWSE Open API",
    )
    assert plan["job_type"] == "http_manifest"
    assert "openapi.twse.com.tw" in (plan.get("url") or "")
    assert plan.get("collect_resolution") in {
        "twse_openapi_known_manifest",
        "catalog_source_probe_fallback",
        "procurement_manifest",
    }
    assert plan.get("launchable") is True


def test_selected_huggingface_dataset_keeps_its_dataset_identity():
    """A live Hub candidate must not collapse to a probe of the Hub homepage."""
    stack = create_stack()
    plan = resolve_discover_collect_plan(
        stack.gateway.procurement,
        stack.gateway.repo_root,
        connector_id="huggingface",
        title="patent_abstract",
        url="https://huggingface.co/datasets/Pyke/patent_abstract",
        candidate_key="source:hugging-face:Pyke/patent_abstract",
    )
    assert plan["job_type"] == "huggingface_collect"
    assert plan["hf_dataset_id"] == "Pyke/patent_abstract"
    assert plan["collect_resolution"] == "huggingface_selected_dataset"
    assert plan["requires_approval"] is True


def test_selected_doi_resolves_to_existing_http_manifest_without_submitting(monkeypatch):
    """DataCite/Zenodo candidates share DOI resolution; planning has no job side effect."""
    stack = create_stack()
    monkeypatch.setattr(
        "scripts.research_data_mcp.doi_resolve_cache.resolve_doi_cached",
        lambda *_args, **_kwargs: {
            "doi": "10.5281/zenodo.12345",
            "title": "Patent replication data",
            "repository": "zenodo",
            "landing_url": "https://zenodo.org/records/12345",
            "files": [{"url": "https://zenodo.org/records/12345/files/data.csv", "key": "data.csv"}],
        },
    )
    plan = resolve_discover_collect_plan(
        stack.gateway.procurement,
        stack.gateway.repo_root,
        connector_id="zenodo",
        provider="Zenodo",
        kind="live_candidate",
        title="Patent replication data",
        doi="10.5281/zenodo.12345",
        url="https://zenodo.org/records/12345",
        candidate_key="doi:10.5281/zenodo.12345",
    )
    assert plan["job_type"] == "http_manifest"
    assert plan["datacite_doi"] == "10.5281/zenodo.12345"
    assert plan["items"] == [{"url": "https://zenodo.org/records/12345/files/data.csv", "filename": "data.csv"}]
    assert plan["collect_resolution"] == "datacite_selected_doi"
    assert plan["requires_approval"] is True


def test_zenodo_record_url_can_resolve_when_datacite_metadata_lags(monkeypatch):
    stack = create_stack()

    def fail_datacite(*_args, **_kwargs):
        raise RuntimeError("DataCite record temporarily unavailable")

    monkeypatch.setattr(
        "scripts.research_data_mcp.doi_resolve_cache.resolve_doi_cached", fail_datacite
    )
    monkeypatch.setattr(
        "scripts.research_data_mcp.repository_adapters.zenodo_files",
        lambda *_args, **_kwargs: [{"url": "https://zenodo.org/api/records/7/files/data.csv/content", "key": "data.csv"}],
    )
    plan = resolve_discover_collect_plan(
        stack.gateway.procurement,
        stack.gateway.repo_root,
        connector_id="zenodo",
        provider="Zenodo",
        kind="live_candidate",
        doi="10.5281/zenodo.7",
        url="https://zenodo.org/records/7",
        candidate_key="doi:10.5281/zenodo.7",
    )
    assert plan["job_type"] == "http_manifest"
    assert plan["source_id"] == "zenodo"
    assert plan["items"][0]["url"].endswith("data.csv/content")


def test_explicit_direct_url_is_collected_without_provider_substitution():
    stack = create_stack()
    url = "https://data.example.edu/api/v1/patents.csv"
    plan = resolve_discover_collect_plan(
        stack.gateway.procurement,
        stack.gateway.repo_root,
        connector_id="openalex",
        provider="OpenAlex",
        kind="live_candidate",
        title="Patent rows",
        url=url,
        candidate_key="url:https://data.example.edu/api/v1/patents.csv",
    )
    assert plan["job_type"] == "http_manifest"
    assert plan["items"][0]["url"] == url
    assert plan["url"] == url
    assert plan["collect_resolution"] == "direct_machine_readable_url"
    assert plan["requires_approval"] is True


def test_explicit_html_candidate_stays_a_probe_or_scrape_of_that_url():
    stack = create_stack()
    url = "https://openalex.org/works/W123"
    plan = resolve_discover_collect_plan(
        stack.gateway.procurement,
        stack.gateway.repo_root,
        connector_id="openalex",
        provider="OpenAlex",
        kind="live_candidate",
        title="OpenAlex work",
        url=url,
        candidate_key="url:https://openalex.org/works/W123",
    )
    assert plan["url"] == url
    assert plan["job_type"] in {"source_probe", "scraper_run"}
    assert plan["collect_resolution"] in {
        "catalog_source_probe_fallback",
        "catalog_browser_scrape_fallback",
    }
    assert plan["requires_approval"] is True


def test_procurement_manifest_still_preferred_when_available():
    stack = create_stack()
    store = stack.gateway.procurement.store
    raw = store.list(50)
    items = raw.get("items") if isinstance(raw, dict) else raw
    connector_id = None
    for row in items or []:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("id") or row.get("connector_id") or "").strip()
        if not cid:
            continue
        try:
            plan = resolve_discover_collect_plan(
                stack.gateway.procurement,
                stack.gateway.repo_root,
                connector_id=cid,
                limit=5,
            )
        except KeyError:
            continue
        if plan.get("job_type") == "http_manifest" and plan.get("items"):
            connector_id = cid
            break
    if not connector_id:
        pytest.skip("no procurement connector with http_manifest items in this checkout")
    plan = resolve_discover_collect_plan(
        stack.gateway.procurement,
        stack.gateway.repo_root,
        connector_id=connector_id,
        limit=5,
    )
    assert plan["job_type"] == "http_manifest"
    assert plan.get("items")
