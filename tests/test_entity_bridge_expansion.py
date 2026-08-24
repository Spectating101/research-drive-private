"""Entity bridge expansion — global master should lift coverage above legacy 11%."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def bridge_stats():
    from scripts.build_us_entity_mapping_layer import build_us_master
    from scripts.build_global_entity_master import build_global
    from scripts.build_gdelt_entity_bridge_expansion import expand_spine

    build_us_master()
    build_global()
    return expand_spine()


def test_entity_bridge_coverage_above_half(bridge_stats):
    assert bridge_stats["bridge_pct"] >= 50.0
    assert bridge_stats["bridged_after"] >= 285


def test_us_entity_master_has_sp500_symbols():
    from scripts.build_us_entity_mapping_layer import build_us_master

    out = build_us_master()
    assert out["us_symbols"] >= 400
