#!/usr/bin/env python3
"""A collect proposal needs a recorded submit call. Prose alone is not evidence.

Same rule as verified_answer, but the stakes are higher — a fabricated
job_id would tell a researcher a real collection job exists to approve when
it doesn't.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drive"))

from scripts.research_data_mcp.discover_composer import (  # noqa: E402
    _deterministic_collect_fallback,
    verified_collect,
)

PROPOSAL = {
    "collect_proposed": {
        "job_id": "job-abc123",
        "url": "https://opensea.io/collection/boredapeyachtclub",
        "message": "Pending collect job `job-abc123` proposed. Researcher approval required.",
    }
}


def test_collect_survives_when_the_submit_tool_actually_ran():
    out = verified_collect(PROPOSAL, ["research_discover_desk", "research_propose_pending_collect"])
    assert out is not None
    assert out["job_id"] == "job-abc123"
    assert out["url"] == "https://opensea.io/collection/boredapeyachtclub"


def test_collect_is_dropped_when_no_submit_tool_ran():
    assert verified_collect(PROPOSAL, ["research_discover_desk", "cursor_composer"]) is None


def test_collect_is_dropped_when_the_model_just_narrated_a_job_id():
    # A model that writes a plausible-looking job_id into JSON without ever
    # calling the tool is not a source to trust for a queued-job claim.
    assert verified_collect(PROPOSAL, []) is None
    assert verified_collect(PROPOSAL, ["research_web_discover"]) is None


def test_empty_or_missing_proposal_is_none():
    assert verified_collect({}, ["research_propose_pending_collect"]) is None
    assert verified_collect(None, ["research_propose_pending_collect"]) is None
    blank = {"collect_proposed": {"job_id": "   ", "url": "https://x.example/"}}
    assert verified_collect(blank, ["research_propose_pending_collect"]) is None


def test_message_is_truncated_and_url_defaults_empty():
    long_msg = {
        "collect_proposed": {
            "job_id": "job-1",
            "message": "x" * 1000,
        }
    }
    out = verified_collect(long_msg, ["research_propose_pending_collect"])
    assert out is not None
    assert out["url"] == ""
    assert len(out["message"]) == 400


CONTEXT = [{"title": "OpenSea", "url": "https://opensea.io/collection/boredapeyachtclub"}]


def test_fallback_proposes_a_collect_when_composer_named_a_url_but_never_called_the_tool():
    # The exact failure mode this exists for: Composer's own summary said a
    # collect "would be possible" without ever invoking the tool.
    with patch(
        "scripts.research_data_mcp.job_first_procure.propose_pending_collect",
        return_value={"ok": True, "job_id": "job-fallback-1", "message": "Pending collect job proposed."},
    ) as mocked:
        out = _deterministic_collect_fallback(
            gateway=object(), query="q", held=[], routes=[], context=CONTEXT
        )
    assert out is not None
    assert out["job_id"] == "job-fallback-1"
    assert out["url"] == "https://opensea.io/collection/boredapeyachtclub"
    mocked.assert_called_once()


def test_fallback_does_nothing_when_anything_is_held_or_routed():
    with patch("scripts.research_data_mcp.job_first_procure.propose_pending_collect") as mocked:
        assert _deterministic_collect_fallback(
            gateway=object(), query="q", held=[{"dataset_id": "x"}], routes=[], context=CONTEXT
        ) is None
        assert _deterministic_collect_fallback(
            gateway=object(), query="q", held=[], routes=[{"source_id": "y"}], context=CONTEXT
        ) is None
    mocked.assert_not_called()


def test_fallback_refuses_to_invent_a_url():
    with patch("scripts.research_data_mcp.job_first_procure.propose_pending_collect") as mocked:
        out = _deterministic_collect_fallback(
            gateway=object(), query="q", held=[], routes=[], context=[{"title": "no url here"}]
        )
    assert out is None
    mocked.assert_not_called()


def test_fallback_returns_none_when_the_underlying_call_fails():
    with patch(
        "scripts.research_data_mcp.job_first_procure.propose_pending_collect",
        return_value={"ok": False, "action": "already_held"},
    ):
        out = _deterministic_collect_fallback(
            gateway=object(), query="q", held=[], routes=[], context=CONTEXT
        )
    assert out is None
