#!/usr/bin/env python3
"""Noise classification for denied / fixture stuck jobs."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "kernel"), str(REPO / "drive")]

from scripts.yzu_cluster.triage_pending_jobs import _noise_reason


def test_noise_reasons_for_denied_and_fixture_jobs():
    assert _noise_reason({"plan": {"job_type": "synthesis_execute"}, "id": "abc"}) == "denied_job_type_remote_worker"
    assert (
        _noise_reason({"plan": {"job_type": "source_probe"}, "id": "probe-no-promotion-deadbeef"})
        == "fixture_probe_no_promotion"
    )
    assert (
        _noise_reason({"plan": {"job_type": "http_manifest"}, "id": "archive-before-promote-1"})
        == "fixture_http_manifest_stuck"
    )
    assert (
        _noise_reason({"plan": {"job_type": "http_manifest"}, "id": "missing-manifest-1"})
        == "fixture_http_manifest_stuck"
    )
    assert _noise_reason({"plan": {"job_type": "http_manifest"}, "id": "01bf070a7e86"}) == ""
