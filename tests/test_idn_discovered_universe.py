from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "alpha" / "scripts"))

from idn_discovered_universe_lib import (  # noqa: E402
    BIG_WINNER_JSON,
    discovered_oos_losers,
    discovered_pattern_tilt_candidates,
    discovered_tilt_candidates,
    load_winner_patterns_report,
)


def test_discovered_pattern_tilt_uses_profile_not_fixed_winners():
    if not BIG_WINNER_JSON.exists():
        return
    idx = pd.bdate_range("2026-05-01", periods=30)
    close = pd.DataFrame({f"S{i}.JK": [100.0 - i] * len(idx) for i in range(8)}, index=idx)
    vol = pd.DataFrame(500_000, index=idx, columns=close.columns)
    symbols = list(close.columns)
    tilt, avoid, meta = discovered_pattern_tilt_candidates(
        close,
        vol,
        idx[-1],
        symbols,
        max_n=5,
        min_oos_lift=1.15,
    )
    assert meta["selection_mode"] == "pattern_profile"
    assert meta["pattern_catalog_size"] > 0
    assert isinstance(avoid, set)
    if tilt:
        assert meta["pattern_rationales"].get(tilt[0])


def test_discovered_tilt_prefers_pattern_when_panel_provided():
    if not BIG_WINNER_JSON.exists():
        return
    idx = pd.bdate_range("2026-05-01", periods=30)
    close = pd.DataFrame({"AAA.JK": range(100, 130)}, index=idx)
    vol = pd.DataFrame(1_000_000, index=idx, columns=["AAA.JK"])
    tilt, _, meta = discovered_tilt_candidates(
        close,
        vol,
        idx[-1],
        ["AAA.JK"],
        max_n=3,
        selection_mode="pattern_profile",
    )
    assert meta.get("selection_mode") in ("pattern_profile", "named_tickers")


def test_named_tilt_fallback_still_available():
    wp = load_winner_patterns_report()
    if not wp:
        return
    tilt, avoid, meta = discovered_tilt_candidates(
        selection_mode="named_tickers",
        max_n=12,
    )
    assert meta["selection_mode"] == "named_tickers"
    assert meta["tilt_candidates"] == tilt
    assert avoid == discovered_oos_losers()


def test_platform_integration_discover_flags():
    cfg = json.loads((REPO / "alpha" / "config" / "platform_integration.json").read_text(encoding="utf-8"))
    idn = cfg["idn_sleeve"]
    assert idn.get("discover_universe_from_data") is True
    assert idn.get("tilt_selection_mode") == "pattern_profile"
    assert idn.get("min_pattern_oos_lift") == 1.15
    assert idn.get("refresh_winner_patterns_days") == 7
