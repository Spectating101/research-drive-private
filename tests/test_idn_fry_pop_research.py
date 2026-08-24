from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "alpha" / "scripts"))

from idn_fry_pop_pattern_lib import (  # noqa: E402
    pop_probability_tier,
    score_fry_pop_row,
)
from idn_fry_pop_research_lib import mine_trigger_pop_patterns  # noqa: E402


def test_score_fry_pop_row_deep_dd_vol_spike():
    row = {
        "name_type": "fry",
        "return_1d": -0.02,
        "return_5d": -0.15,
        "vol_ratio_20d": 2.8,
        "dd_60d": -0.35,
        "bandar_lite_label": "squeeze_from_drawdown",
        "rsi14": 25,
        "ihsg_regime": "washout",
        "quiet_acc_score_5d": 1,
        "chase_score_5d": 0,
        "cs_move_pct_rank": 0.2,
    }
    score, matched, cause = score_fry_pop_row(row, catalog={})
    assert cause in ("drawdown_vol_spike", "deep_dd_vol_spike", "other", "both_quiet_and_vol_dd")
    assert score >= 0


def test_pop_tier_high_for_deep_pattern():
    tier = pop_probability_tier(2.1, matched=["deep_dd_vol_spike"])
    assert tier == "high"


def test_mine_trigger_pop_patterns_structure():
    trig = pd.DataFrame(
        {
            "got_pop": [1, 0, 1, 0, 1, 0] * 20,
            "trigger_cause": ["drawdown_vol_spike"] * 120,
            "ihsg_regime": ["washout"] * 120,
            "bandar_lite_label": ["squeeze_from_drawdown"] * 120,
            "return_5d": [-0.15] * 120,
            "vol_ratio_20d": [2.0] * 120,
            "dd_60d": [-0.3] * 120,
            "rsi14": [28.0] * 120,
            "quiet_acc_score_5d": [1] * 120,
            "chase_score_5d": [0] * 120,
            "cs_move_pct_rank": [0.25] * 120,
        }
    )
    patterns = mine_trigger_pop_patterns(trig)
    assert patterns
    assert patterns[0]["pop_lift"] >= 1.0
    assert "pattern" in patterns[0]
