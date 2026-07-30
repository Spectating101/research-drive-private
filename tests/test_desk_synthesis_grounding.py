"""First-turn grounding combines Library candidates with prior synthesis patterns."""

from __future__ import annotations


def test_grounding_is_bounded_and_does_not_claim_fit_or_readiness(monkeypatch):
    from scripts.research_data_mcp import desk_synthesis_grounding

    monkeypatch.setattr(
        "scripts.research_data_mcp.procurement_fast.local_search",
        lambda *_args, **_kwargs: {
            "candidates": [
                {
                    "dataset_id": "jkse_pit_panel",
                    "title": "JKSE PIT panel",
                    "analysis_readiness": "instant",
                    "description": "Point-in-time membership history.",
                },
                {
                    "dataset_id": "idn_microstructure",
                    "title": "IDN microstructure",
                    "analysis_readiness": "",
                    "description": "Candidate market-behaviour components.",
                },
            ]
        },
    )

    class Gateway:
        def synthesis_list_profiles(self):
            return {
                "profiles": [
                    {
                        "id": "idn_pattern",
                        "title": "JKSE PIT × IDN microstructure",
                        "description": "Prior regional construction pattern.",
                        "sources": [
                            {"dataset_id": "jkse_pit_panel"},
                            {"dataset_id": "idn_microstructure"},
                        ],
                    },
                    {
                        "id": "unrelated",
                        "title": "Stablecoin trust",
                        "description": "Unrelated crypto pattern.",
                    },
                ]
            }

    brief = desk_synthesis_grounding.build_synthesis_grounding_brief(
        Gateway(),
        "Construct an Indonesia JKSE microstructure proxy.",
    )
    assert "JKSE PIT panel [jkse_pit_panel]" in brief
    assert "IDN microstructure [idn_microstructure]" in brief
    assert "JKSE PIT × IDN microstructure" in brief
    assert "Stablecoin trust" not in brief
    assert "not proof of fit, coverage, readiness" in brief
    assert "Do not turn this list into an inventory dump" in brief


def test_grounding_survives_search_failures():
    from scripts.research_data_mcp.desk_synthesis_grounding import (
        build_synthesis_grounding_brief,
    )

    class Gateway:
        def synthesis_list_profiles(self):
            raise RuntimeError("profile store unavailable")

    brief = build_synthesis_grounding_brief(
        Gateway(),
        "Construct a new measure.",
    )
    assert "no local candidates were returned" in brief
    assert brief.endswith("[/Synthesis grounding candidates]")
