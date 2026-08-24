from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "alpha" / "scripts"))

from idn_winner_pattern_lib import (  # noqa: E402
    load_pattern_catalog,
    pattern_matches_row,
    pattern_rationale,
    score_row,
)


def test_pattern_matches_categorical_and_numeric():
    row = {
        "bandar_lite_label": "squeeze_from_drawdown",
        "dd_60d": -0.25,
        "rsi14": 28.0,
        "is_ara_day": 0,
        "return_5d": -0.12,
        "vol_ratio_20d": 2.8,
        "ihsg_regime": "washout",
    }
    assert pattern_matches_row("bandar_lite_label=squeeze_from_drawdown", row)
    assert pattern_matches_row("dd_60d:x<-0.2", row)
    assert pattern_matches_row("return_5d:x<-0.1", row)
    assert pattern_matches_row("vol_ratio_20d:x>=2.5", row)
    assert pattern_matches_row("ihsg_regime=washout", row)
    assert not pattern_matches_row("is_ara_day==1", row)


def test_pattern_matches_range_bucket():
    row = {"chase_score_5d": 1.5}
    assert pattern_matches_row("chase_score_5d:1<=x<2", row)
    assert not pattern_matches_row("chase_score_5d:x>=2", row)


def test_retail_catalog_excludes_fry_chase():
    catalog = load_pattern_catalog(min_oos_lift=1.5, sleeve="retail_tilt")
    patterns = {r.pattern for r in catalog}
    assert "bandar_lite_label=chase_into_spike" not in patterns
    assert "is_ara_day==1" not in patterns
    assert any("squeeze_from_drawdown" in p or "dd_60d" in p for p in patterns)


def test_score_row_sums_matched_patterns():
    catalog = load_pattern_catalog(min_oos_lift=1.15, sleeve="retail_tilt")
    if not catalog:
        return
    row = {
        "bandar_lite_label": "squeeze_from_drawdown",
        "dd_60d": -0.25,
        "return_5d": -0.12,
        "vol_ratio_20d": 2.8,
        "ihsg_regime": "washout",
        "rsi14": 28.0,
        "is_ara_day": 0,
        "name_type": "standard",
    }
    score, matched = score_row(row, catalog, min_matches=1)
    assert score > 0
    assert matched


def test_pattern_rationale_shortens_labels():
    txt = pattern_rationale(
        ["dd_60d:x<-0.2", "bandar_lite_label=squeeze_from_drawdown", "ihsg_regime=washout"]
    )
    assert "washout" in txt
    assert len(txt) < 80


def test_rank_on_synthetic_panel_if_big_winner_json_exists():
    from idn_winner_pattern_lib import BIG_WINNER_JSON, rank_symbols_by_winner_patterns

    if not BIG_WINNER_JSON.exists():
        return
    idx = pd.date_range("2026-05-01", periods=5, freq="B")
    close = pd.DataFrame(
        {
            "AAA.JK": [100, 99, 98, 97, 96],
            "BBB.JK": [50, 51, 52, 53, 54],
        },
        index=idx,
    )
    vol = pd.DataFrame(1_000_000, index=idx, columns=close.columns)
    ranked = rank_symbols_by_winner_patterns(
        close,
        vol,
        idx[-1],
        list(close.columns),
        max_n=2,
        min_pattern_matches=0,
    )
    assert isinstance(ranked, list)
