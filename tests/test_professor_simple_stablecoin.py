"""Tests for professor-simple stablecoin exports."""

from __future__ import annotations

from pathlib import Path

from stablecoin_skynet.professor_simple import LATEST_FIELDS, WEEKLY_FIELDS, publish_professor_simple


def test_professor_simple_from_frozen_package():
    pkg = Path("data/datasets/stablecoin_trust_engagement/20260707")
    if not (pkg / "panel_weekly.csv").is_file():
        return
    counts = publish_professor_simple(pkg)
    out = pkg / "professor_simple"
    assert counts["stablecoin_simple_latest"] == 71
    assert counts["stablecoin_simple_weekly"] == 18673
    assert (out / "README_FOR_PROFESSOR.md").is_file()
    assert (out / "COLUMN_GUIDE.md").is_file()
    latest = (out / "stablecoin_simple_latest.csv").read_text(encoding="utf-8").splitlines()
    weekly = (out / "stablecoin_simple_weekly.csv").read_text(encoding="utf-8").splitlines()
    assert latest[0].split(",") == LATEST_FIELDS
    assert weekly[0].split(",") == WEEKLY_FIELDS
    assert "etherscan_join_suspect" not in latest[0]
