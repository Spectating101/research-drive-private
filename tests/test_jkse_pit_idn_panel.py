"""Tests for JKSE PIT × IDN microstructure × estimate revisions panel."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
PANEL = REPO / "data_lake/research_panels/jkse_pit_idn/jkse_pit_idn_microstructure_revisions.parquet"
MANIFEST = REPO / "data_lake/research_panels/jkse_pit_idn/manifest.json"


@pytest.mark.skipif(not PANEL.is_file(), reason="panel not built")
def test_jkse_panel_exists_with_expected_columns():
    df = pd.read_parquet(PANEL)
    required = {
        "index_ric",
        "as_of_month",
        "ric",
        "yahoo_symbol",
        "has_idn_features",
        "has_estimates",
        "idn_mean_return_1d",
        "est_revision_1m",
    }
    missing = required - set(df.columns)
    assert not missing, f"missing columns: {missing}"
    assert (df["index_ric"] == ".JKSE").all()
    assert len(df) > 100_000


@pytest.mark.skipif(not MANIFEST.is_file(), reason="manifest not built")
def test_jkse_manifest_summary():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    summary = manifest["summary"]
    assert summary["unique_rics"] > 500
    assert summary["idn_feature_rate_pct"] > 10
    assert summary["as_of_month_min"] <= "2019-01"


def test_build_panel_dry_run():
    from scripts.build_jkse_pit_idn_microstructure_revisions import build_panel

    run = "2026-07-06-complete"
    pit = REPO / f"data_lake/refinitiv_backfill/{run}/processed/index_membership_pit.parquet"
    spine = REPO / f"data_lake/research_panels/refinitiv/{run}/entity_market_spine.parquet"
    est = REPO / f"data_lake/research_panels/refinitiv/{run}/estimate_revision_panel.parquet"
    idn = REPO / "data_lake/research_panels/idn_fry_episode/daily_cross_section.parquet"
    if not all(p.is_file() for p in (pit, spine, est, idn)):
        pytest.skip("input panels missing")
    panel = build_panel(pit_path=pit, spine_path=spine, est_path=est, idn_path=idn)
    assert panel["has_idn_features"].sum() > 0
    assert panel["has_estimates"].sum() > 0
