from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "alpha" / "scripts"))

from idn_big_winner_reverse_lib import (  # noqa: E402
    dedupe_winner_entries,
    label_big_winners,
)


def test_dedupe_winner_entries_non_overlapping():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-05", "2024-01-25", "2024-02-20"]),
            "yahoo_symbol": ["BBCA.JK"] * 4,
            "reward_20d_pct": [25.0, 30.0, 22.0, 21.0],
        }
    )
    tagged = label_big_winners(df)
    out = dedupe_winner_entries(tagged)
    assert len(out) == 3
    assert str(out.iloc[0]["date"].date()) == "2024-01-01"
    assert str(out.iloc[1]["date"].date()) == "2024-01-25"
