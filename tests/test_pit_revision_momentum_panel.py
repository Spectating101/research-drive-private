from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
PANEL = REPO / "data_lake/research_panels/pit_revision_momentum/pit_index_revision_momentum.parquet"


@pytest.mark.skipif(not PANEL.is_file(), reason="panel not built")
def test_pit_revision_momentum_covers_six_indices():
    df = pd.read_parquet(PANEL)
    assert set(df["index_ric"].unique()) == {".SPX", ".JKSE", ".TWII", ".N225", ".KS11", ".STI"}
    assert len(df) > 500_000
    assert "est_revision_1m" in df.columns
