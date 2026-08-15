"""metadata_overlap describes declared names. It must never imply a join works."""

from __future__ import annotations

from scripts.research_data_mcp.synthesis.registry_pair import metadata_overlap


def _ds(dataset_id, keys, grain, entity=None):
    return {
        "dataset_id": dataset_id,
        "name": dataset_id,
        "join_keys": keys,
        "entity_fields": entity or [],
        "grain": grain,
    }


def test_matching_grain_no_longer_invents_35_percent():
    """The retired floor read: overlap = max(key_pct, 35.0) when grains matched."""
    left = _ds("a", [], "country_week")
    right = _ds("b", [], "country_week")
    out = metadata_overlap(left, right)
    assert out["grain_match"] is True
    assert out["overlap_pct"] == 0.0


def test_field_overlap_is_reported_as_itself():
    left = _ds("a", ["ric", "date"], "instrument_day")
    right = _ds("b", ["ric"], "instrument_day")
    out = metadata_overlap(left, right)
    assert out["field_overlap_pct"] == out["overlap_pct"]
    assert out["overlap_pct"] == 50.0


def test_metadata_never_returns_a_viability_verdict():
    left = _ds("a", ["ric"], "instrument_day")
    right = _ds("b", ["ric"], "instrument_day")
    out = metadata_overlap(left, right)
    assert out["synthesis_viable"] is False
    assert out["verdict"] == "requires_probe"


def test_shared_key_recommends_a_probe_and_names_the_key():
    left = _ds("a", ["ric", "date"], "instrument_day")
    right = _ds("b", ["ric"], "instrument_snapshot")
    out = metadata_overlap(left, right)
    assert out["probe_recommended"] is True
    assert out["probe_keys"] == ["ric"]


def test_grain_match_alone_does_not_recommend_a_probe():
    """country_day x country_week previously greenlit on grain+union alone."""
    left = _ds("a", [], "country_week", entity=["country_iso3"])
    right = _ds("b", [], "country_week", entity=["country_iso3"])
    out = metadata_overlap(left, right)
    assert out["probe_recommended"] is False
    assert out["synthesis_viable"] is False


def test_note_points_the_caller_at_the_probe():
    out = metadata_overlap(_ds("a", ["ric"], "g"), _ds("b", ["ric"], "g"))
    assert "probe_pair" in out["note"]
