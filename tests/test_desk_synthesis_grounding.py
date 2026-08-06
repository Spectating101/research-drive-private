"""Synthesis Ask grounding — measured desk_check, no catalog wallpaper."""

from __future__ import annotations


def test_grounding_uses_desk_facts_not_local_search(monkeypatch):
    from scripts.research_data_mcp import desk_synthesis_grounding

    monkeypatch.setattr(
        "scripts.research_data_mcp.discover_desk.desk_check",
        lambda *_args, **_kwargs: {
            "held": [
                {
                    "dataset_id": "jkse_pit_panel",
                    "title": "JKSE PIT panel",
                }
            ],
            "routes": [],
            "strong_held": True,
            "held_count": 1,
            "route_count": 0,
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
    assert "[Synthesis DESK_FACTS]" in brief
    assert "JKSE PIT panel [jkse_pit_panel]" in brief
    assert "JKSE PIT × IDN microstructure" in brief
    # Unrelated profile must not be claimed as "relevant"
    assert "Relevant prior synthesis" not in brief
    assert "Stablecoin trust" not in brief or "Ids:" in brief
    assert "not ranked for fit" in brief.lower() or "Not ranked for fit" in brief
    assert "Composer owns fit judgment" in brief


def test_grounding_polling_miss_does_not_wallpaper_crypto(monkeypatch):
    from scripts.research_data_mcp import desk_synthesis_grounding

    monkeypatch.setattr(
        "scripts.research_data_mcp.discover_desk.desk_check",
        lambda *_args, **_kwargs: {
            "held": [],
            "routes": [],
            "strong_held": False,
            "held_count": 0,
            "route_count": 0,
        },
    )

    class Gateway:
        def synthesis_list_profiles(self):
            return {
                "profiles": [
                    {"id": "stablecoin_trust", "title": "Stablecoin trust", "sources": []},
                    {"id": "skynet_etherscan", "title": "Skynet etherscan", "sources": []},
                ]
            }

    brief = desk_synthesis_grounding.build_synthesis_grounding_brief(
        Gateway(),
        "US Polling data",
    )
    assert "Library holdings: none measured" in brief
    assert "none cite measured holdings" in brief
    assert "do not invent relevance from names" in brief
    # Must not present crypto profiles as Indexed evidence / candidates
    assert "Indexed evidence" not in brief
    assert "[/Synthesis DESK_FACTS]" in brief


def test_grounding_survives_desk_and_profile_failures(monkeypatch):
    from scripts.research_data_mcp.desk_synthesis_grounding import (
        build_synthesis_grounding_brief,
    )

    def _boom(*_a, **_k):
        raise RuntimeError("desk down")

    monkeypatch.setattr(
        "scripts.research_data_mcp.discover_desk.desk_check",
        _boom,
    )

    class Gateway:
        def synthesis_list_profiles(self):
            raise RuntimeError("profile store unavailable")

    brief = build_synthesis_grounding_brief(Gateway(), "Construct a new measure.")
    assert "Library holdings: none measured" in brief
    assert "Declared synthesis profiles: unavailable or empty" in brief
    assert brief.endswith("[/Synthesis DESK_FACTS]")
