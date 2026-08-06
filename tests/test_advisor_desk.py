"""Advise = measured Ask DESK_FACTS; no catalog fit ranking."""

from __future__ import annotations

from scripts.research_data_mcp.advisor import DatasetAdvisor


def test_advise_strong_held():
    class Gw:
        repo_root = "/tmp"

        def discover_search_lexical(self, query, email="", limit=12):
            return {
                "sections": [
                    {
                        "id": "held",
                        "rows": [
                            {
                                "title": "Stablecoin panel",
                                "dataset_id": "stablecoin.demo",
                                "score": 4.0,
                                "local_ready": True,
                            }
                        ],
                    }
                ]
            }

    out = DatasetAdvisor(Gw()).advise("stablecoin", limit=5)
    assert out["engine"] == "ask_desk_facts"
    assert out["desk_verdict"] == "use_held"
    assert out["strong_held"] is True
    assert out["recommended"][0]["id"] == "stablecoin.demo"
    assert "catalog fit ranking" in (out.get("advisor_note") or "").lower() or "Measured" in out.get("advisor_note", "")


def test_advise_polling_miss_no_gdelt_wallpaper(monkeypatch):
    class Gw:
        repo_root = "/tmp"

        def discover_search_lexical(self, query, email="", limit=12):
            return {"sections": []}

    monkeypatch.setattr(
        "scripts.research_data_mcp.gap_routes.routes_for_query",
        lambda *_a, **_k: {"routes": [], "reason": "no_route_found"},
    )
    out = DatasetAdvisor(Gw()).advise("US Polling data", limit=5)
    assert out["desk_verdict"] == "ask_composer"
    assert out["recommended"] == []
    ids = " ".join(r.get("id", "") for r in out.get("recommended") or []).lower()
    assert "gdelt" not in ids
    assert "coingecko" not in (out.get("message") or "").lower()


def test_legacy_llm_gated_by_default(monkeypatch):
    monkeypatch.delenv("DESK_LEGACY_LLM", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    from scripts.research_data_mcp.llm_client import llm_configured, legacy_llm_enabled

    assert legacy_llm_enabled() is False
    assert llm_configured() is False
    monkeypatch.setenv("DESK_LEGACY_LLM", "1")
    assert legacy_llm_enabled() is True
    assert llm_configured() is True
