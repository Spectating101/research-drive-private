from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.research.fingerprint import make_fingerprint, stamp


def test_fingerprint_has_required_fields():
    fp = make_fingerprint(config={"a": 1})
    for key in ("schema", "timestamp_utc", "python_version", "platform", "hostname"):
        assert key in fp
    assert fp["schema"] == "sharpe-renaissance/fingerprint/v1"
    # git fields may be None outside a repo, but inside this repo they should resolve
    assert fp["git_commit"] is None or isinstance(fp["git_commit"], str)


def test_fingerprint_config_hash_is_deterministic():
    fp1 = make_fingerprint(config={"a": 1, "b": [2, 3]})
    fp2 = make_fingerprint(config={"b": [2, 3], "a": 1})  # different key order
    assert fp1["config_sha256"] == fp2["config_sha256"]


def test_fingerprint_config_hash_changes_with_content():
    fp1 = make_fingerprint(config={"a": 1})
    fp2 = make_fingerprint(config={"a": 2})
    assert fp1["config_sha256"] != fp2["config_sha256"]


def test_fingerprint_panel_hash(tmp_path: Path):
    p = tmp_path / "panel.csv"
    p.write_bytes(b"date,close\n2026-01-01,100\n")
    fp = make_fingerprint(panel_path=p)
    assert fp["panel_sha256"] is not None
    assert fp["panel_size_bytes"] == p.stat().st_size

    # content change → hash change
    p.write_bytes(b"date,close\n2026-01-01,101\n")
    fp2 = make_fingerprint(panel_path=p)
    assert fp["panel_sha256"] != fp2["panel_sha256"]


def test_fingerprint_missing_panel_yields_none(tmp_path: Path):
    missing = tmp_path / "nope.csv"
    fp = make_fingerprint(panel_path=missing)
    assert fp["panel_sha256"] is None


def test_stamp_mutates_payload_under_key():
    payload = {"weights": {"BIL": 1.0}}
    out = stamp(payload, config={"k": 1})
    assert out is payload
    assert "fingerprint" in payload
    assert payload["fingerprint"]["config_sha256"]


def test_stamp_custom_key():
    payload = {"x": 1}
    stamp(payload, config={"k": 1}, key="provenance")
    assert "provenance" in payload
    assert "fingerprint" not in payload


def test_stamp_in_signal_payload_is_json_serializable():
    payload = {"weights": {"BIL": 1.0}, "strategy": "test"}
    stamp(payload, config={"lambda": 0.01})
    # Must round-trip through json (sort_keys + indent path used by alpha_live_cycle)
    s = json.dumps(payload, indent=2, sort_keys=True)
    rt = json.loads(s)
    assert rt["fingerprint"]["config_sha256"] == payload["fingerprint"]["config_sha256"]
