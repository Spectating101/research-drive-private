"""MODEL_GUIDE builder smoke tests."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_build_model_guide():
    from scripts.ops.build_model_collection_guide import build_guide

    guide = build_guide(write_readmes=False)
    assert guide["partition_count"] >= 20
    assert "partitions" in guide
    row = next(r for r in guide["partitions"] if r["id"] == "markets.ethereum-usdt")
    assert row["semantic"]["example_questions"]
    assert "sync" in row
