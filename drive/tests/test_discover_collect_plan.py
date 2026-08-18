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
