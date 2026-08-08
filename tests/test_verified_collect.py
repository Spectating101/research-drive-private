#!/usr/bin/env python3
"""A collect proposal needs a recorded submit call. Prose alone is not evidence.

Same rule as verified_answer, but the stakes are higher — a fabricated
job_id would tell a researcher a real collection job exists to approve when
it doesn't.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drive"))

from scripts.research_data_mcp.discover_composer import verified_collect  # noqa: E402

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
