from __future__ import annotations

from scripts.research_data_mcp.faculty_profile import profile_score_adjustment


def test_registry_dataset_match_boosts_without_crashing() -> None:
    row = {
        "dataset_id": "held_panel",
        "title": "Held panel",
        "description": "A controlled research asset",
    }
    profile = {
        "registry_dataset_ids": ["held_panel"],
        "domain_tags": [],
    }

    assert profile_score_adjustment(row, "", profile) == 0.5


def test_nonmatching_registry_dataset_id_is_neutral() -> None:
    row = {
        "dataset_id": "candidate_panel",
        "title": "Candidate panel",
    }
    profile = {
        "registry_dataset_ids": ["different_panel"],
        "domain_tags": [],
    }

    assert profile_score_adjustment(row, "", profile) == 0.0
