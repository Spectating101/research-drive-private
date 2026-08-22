#!/usr/bin/env python3
"""A crafted pipeline is an asset, not a one-time cost.

craft_collect_plan returns {plan, rationale, doctrine} and stores none of it, and
no registry row across 168 datasets names how anything was obtained. So the
reasoning that paged an undocumented API is discarded and re-derived next time,
and Resources lists a fixed vendor set because a crafted route has nowhere to live.
"""

from __future__ import annotations

import json

import pytest

from scripts.research_data_mcp.crafted_route import (
    DRAFTED,
    FAILING,
    PROVEN,
    crafted_capabilities,
    get_route,
    record_attempt,
    store_path,
)

PLAN = {"steps": [{"fetch": "https://api.example.org/v2/events?cursor="}], "paging": "cursor"}


def test_a_plan_that_has_never_run_is_not_a_capability(tmp_path):
    record_attempt(tmp_path, source_id="opensea", plan=PLAN, succeeded=False)
    assert get_route(tmp_path, "opensea")["state"] == DRAFTED
    assert crafted_capabilities(tmp_path) == [], (
        "an untested recipe presented as a route is how a researcher plans "
        "around something that does not work"
    )


def test_a_successful_run_makes_it_a_capability_with_what_it_produced(tmp_path):
    record_attempt(tmp_path, source_id="opensea", plan=PLAN, rationale="cursor paging, 50/page",
                   succeeded=True, produced=["opensea_collection_sales"])
    caps = crafted_capabilities(tmp_path)
    assert len(caps) == 1
    assert caps[0]["source_id"] == "opensea"
    assert caps[0]["produced"] == ["opensea_collection_sales"]
    assert caps[0]["rationale"] == "cursor paging, 50/page"
    assert caps[0]["successes"] == 1


def test_the_method_survives_so_the_next_need_starts_from_it(tmp_path):
    """The whole point: the reasoning is kept, not just the output."""
    record_attempt(tmp_path, source_id="upwork", plan=PLAN, rationale="why this endpoint",
                   succeeded=True, produced=["upwork_jobs"])
    route = get_route(tmp_path, "upwork")
    assert route["plan"] == PLAN
    assert route["rationale"] == "why this endpoint"


def test_a_route_that_stops_working_says_so_rather_than_staying_green(tmp_path):
    record_attempt(tmp_path, source_id="etherscan", plan=PLAN, succeeded=True, produced=["a"])
    record_attempt(tmp_path, source_id="etherscan", plan=PLAN, succeeded=False)
    route = get_route(tmp_path, "etherscan")
    assert route["state"] == FAILING
    assert route["successes"] == 1 and route["attempts"] == 2
    assert crafted_capabilities(tmp_path) == [], "a failing route is not a current capability"


def test_produced_datasets_accumulate_without_duplicating(tmp_path):
    record_attempt(tmp_path, source_id="s", plan=PLAN, succeeded=True, produced=["a"])
    record_attempt(tmp_path, source_id="s", plan=PLAN, succeeded=True, produced=["a", "b"])
    assert get_route(tmp_path, "s")["produced"] == ["a", "b"]


def test_capabilities_rank_by_how_often_the_route_actually_worked(tmp_path):
    record_attempt(tmp_path, source_id="rare", plan=PLAN, succeeded=True)
    for _ in range(3):
        record_attempt(tmp_path, source_id="workhorse", plan=PLAN, succeeded=True)
    assert [c["source_id"] for c in crafted_capabilities(tmp_path)] == ["workhorse", "rare"]


def test_a_plan_is_required_to_record_a_route(tmp_path):
    assert record_attempt(tmp_path, source_id="x", plan={}, succeeded=True)["ok"] is False
    assert record_attempt(tmp_path, source_id="", plan=PLAN, succeeded=True)["ok"] is False


def test_a_corrupt_store_is_not_overwritten(tmp_path):
    """Losing the record of every crafted route to a bad parse would be worse
    than refusing the write."""
    p = store_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json", encoding="utf-8")
    out = record_attempt(tmp_path, source_id="x", plan=PLAN, succeeded=True)
    assert out["ok"] is False
    assert "unreadable" in out["error"]
    assert p.read_text(encoding="utf-8") == "{not json"


def test_drafted_routes_are_visible_when_asked_for(tmp_path):
    record_attempt(tmp_path, source_id="draft_only", plan=PLAN, succeeded=False)
    assert crafted_capabilities(tmp_path, proven_only=False)[0]["state"] == DRAFTED


def test_the_store_is_written_atomically(tmp_path):
    record_attempt(tmp_path, source_id="x", plan=PLAN, succeeded=True)
    p = store_path(tmp_path)
    assert p.is_file()
    assert not p.with_suffix(".json.tmp").exists(), "temp file must not survive the write"
    json.loads(p.read_text(encoding="utf-8"))


def test_identity_is_the_source_not_the_job():
    """The reusable thing is "this desk can read api.opensea.io", not "job 7cc25
    succeeded once"."""
    from scripts.research_data_mcp.crafted_route import route_identity

    assert route_identity({"url": "https://api.opensea.io/v2/events?cursor=x"}) == "api.opensea.io"
    assert route_identity({"url": "https://www.upwork.com/jobs"}) == "upwork.com"
    assert route_identity({"job_type": "scraper_run"}) == "scraper_run"
    assert route_identity({}) == ""


def test_recording_is_wired_into_the_collection_path():
    """A store nothing writes to is the defect this repo keeps repeating."""
    import inspect

    from scripts.research_data_mcp import bootstrap

    src = inspect.getsource(bootstrap)
    assert "record_attempt" in src, "successful collections must record their route"
    assert "route_identity" in src


def test_recording_never_fails_a_collection_that_worked():
    """A bookkeeping failure must not turn a successful collection into an error.

    Parsed rather than string-matched: the call must sit inside a try whose
    handler swallows the failure.
    """
    import ast
    import inspect

    from scripts.research_data_mcp import bootstrap

    tree = ast.parse(inspect.getsource(bootstrap))
    guarded = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        calls = {
            n.func.id
            for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        if "record_attempt" in calls and node.handlers:
            guarded = True
    assert guarded, "route recording must be wrapped so it cannot fail a collection"
