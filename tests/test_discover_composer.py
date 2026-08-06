"""Discover Explore — lexical fast path + Composer packaging (no toolbox agent)."""

from __future__ import annotations

from scripts.research_data_mcp.discover_composer import (
    is_keyword_fast_path,
    is_question_like,
    package_from_composer,
    parse_composer_discover_json,
    strong_held_hits,
)


def test_keyword_fast_path_for_identifiers():
    assert is_keyword_fast_path("stablecoin")
    assert is_keyword_fast_path("CRSP daily")
    assert not is_keyword_fast_path("what data can I use to study de-pegs")


def test_us_polling_keyword_shaped_but_empty_escalates_via_composer_path():
    # Keyword-shaped; empty held means discover_turn escalates to Composer.
    assert is_keyword_fast_path("US Polling data")
    assert not is_keyword_fast_path("what US polling data can I get")
    assert is_question_like("daily country-level news shock data for Taiwan and Japan")


def test_strong_held_hits_requires_score_or_ready():
    assert not strong_held_hits([])
    assert strong_held_hits([{"score": 8.0}])
    assert strong_held_hits([{"score": 3.0, "local_ready": True}])
    assert not strong_held_hits([{"score": 3.0}])
    assert not strong_held_hits([{"score": 0.5, "local_ready": True}])
    assert not strong_held_hits([{"score": 0.5}])


def test_strong_held_never_skips_l1_enrich():
    from scripts.research_data_mcp.discover_composer import should_skip_l1_enrich

    held = [{"dataset_id": "x", "score": 20, "local_ready": True}]
    for q in (
        "Taiwan valuation",
        "how should I construct PE PB screening for TWSE",
        "earnings revision momentum Taiwan",
    ):
        skip, reason = should_skip_l1_enrich(
            q, strong_held=True, held=held, routes=[]
        )
        assert skip is False
        assert reason == ""


def test_parse_and_package_composer_reply():
    reply = """```json
{"held":[],"route":[],"context":[{"title":"Gallup","url":"https://news.gallup.com/poll/","why":"US polling"}],"next_action":"probe_url","summary":"Probe Gallup."}
```"""
    parsed = parse_composer_discover_json(reply)
    assert parsed is not None
    out = package_from_composer("US Polling data", parsed)
    assert out["engine"] == "composer_only"
    assert out["context_count"] == 1
    assert out["next_action"] == "probe_url"
    assert out["weak_match"] is False
    assert "CoinGecko" not in str(out)
    row = out["sections"][0]["rows"][0]
    assert row["placement"] == "context"
    assert row["selected_by"] == "composer_only"


def test_package_empty_miss():
    out = package_from_composer(
        "US Polling data",
        {"held": [], "route": [], "context": [], "summary": "Nothing found."},
    )
    assert out["next_action"] == "paste_url"
    assert out["total"] == 0


def test_package_held_is_use_held():
    out = package_from_composer(
        "stablecoin",
        {
            "held": [{"dataset_id": "a", "title": "A", "local_ready": True}],
            "next_action": "use_held",
            "summary": "Held.",
        },
    )
    assert out["next_action"] == "use_held"
    assert out["held_count"] == 1


def test_hybrid_always_runs_l1_even_with_routes(monkeypatch):
    from scripts.research_data_mcp import discover_composer

    monkeypatch.setattr(
        "scripts.research_data_mcp.discover_desk.desk_check",
        lambda *_a, **_k: {
            "held": [],
            "routes": [
                {
                    "source_id": "twse_official",
                    "title": "TWSE Open API",
                    "actionable": True,
                }
            ],
            "strong_held": False,
            "held_count": 0,
            "route_count": 1,
            "route_reason": "ok",
            "timing_ms": {"total": 12},
        },
    )

    called = {"composer": 0}

    def _fake(*_a, **_k):
        called["composer"] += 1
        return (
            [{"title": "TWSE", "url": "https://openapi.twse.com.tw/", "why": "official"}],
            "Routes exist; confirm TWSE OpenAPI for prices.",
            "collect_route",
            ["cursor_composer", "mcp"],
        )

    monkeypatch.setattr(discover_composer, "_composer_mcp_grounded", _fake)

    class Gateway:
        repo_root = "."

        def faculty_profile(self, **_k):
            return {}

    out = discover_composer.run_hybrid_discover(Gateway(), "Taiwan stock prices")
    assert called["composer"] == 1
    assert out["engine"] == "composer_mcp_grounded"
    assert out["layers"]["L1_enrich"].get("reason") == "always_enrich"
    assert out["next_action"] == "collect_route"
    assert out["route_count"] == 1


def test_hybrid_runs_l1_on_strong_held_keyword(monkeypatch):
    from scripts.research_data_mcp import discover_composer

    monkeypatch.setattr(
        "scripts.research_data_mcp.discover_desk.desk_check",
        lambda *_a, **_k: {
            "held": [
                {
                    "dataset_id": "twse",
                    "title": "TWSE valuation",
                    "score": 24,
                    "local_ready": True,
                }
            ],
            "routes": [],
            "strong_held": True,
            "held_count": 1,
            "route_count": 0,
            "route_reason": "",
            "timing_ms": {"total": 8},
        },
    )

    def _fake(*_a, **_k):
        return (
            [],
            "Held TWSE valuation ratios answer PE/PB screening; use the local asset.",
            "use_held",
            ["cursor_composer", "mcp"],
        )

    monkeypatch.setattr(discover_composer, "_composer_mcp_grounded", _fake)

    class Gateway:
        repo_root = "."

        def faculty_profile(self, **_k):
            return {}

    out = discover_composer.run_hybrid_discover(Gateway(), "Taiwan valuation")
    assert out["engine"] == "composer_mcp_grounded"
    assert out["layers"]["L1_enrich"]["strong_held_signal"] is True
    assert out["layers"]["L1_enrich"].get("skipped") is not True
    assert "TWSE" in (out.get("summary") or "")
