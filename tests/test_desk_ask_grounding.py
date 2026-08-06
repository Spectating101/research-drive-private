"""Ask L0 grounding — same desk_check measure as Discover."""

from __future__ import annotations


def test_ask_grounding_lists_taiwan_routes(monkeypatch):
    from scripts.research_data_mcp import desk_ask_grounding

    monkeypatch.setattr(
        "scripts.research_data_mcp.discover_desk.desk_check",
        lambda *_a, **_k: {
            "held": [],
            "routes": [
                {
                    "source_id": "twse_official",
                    "title": "TWSE Open API",
                    "why": "Declared route overlaps query tokens",
                },
                {
                    "source_id": "lseg_workspace",
                    "title": "LSEG Workspace",
                    "why": "YZU seat route",
                },
            ],
            "strong_held": False,
            "held_count": 0,
            "route_count": 2,
            "route_reason": "ok",
        },
    )

    brief = desk_ask_grounding.build_ask_desk_grounding_brief(
        object(),
        "Do we have Taiwan equity prices held locally, and what route if not?",
    )
    assert "[Ask DESK_FACTS]" in brief
    assert "[/Ask DESK_FACTS]" in brief
    assert "TWSE Open API [twse_official]" in brief
    assert "LSEG Workspace [lseg_workspace]" in brief
    assert "Library holdings: none measured" in brief
    assert "name these routes" in brief


def test_ask_grounding_strong_held_skips_routes(monkeypatch):
    from scripts.research_data_mcp import desk_ask_grounding

    monkeypatch.setattr(
        "scripts.research_data_mcp.discover_desk.desk_check",
        lambda *_a, **_k: {
            "held": [{"dataset_id": "stablecoin_panel", "title": "Stablecoin panel"}],
            "routes": [{"source_id": "should_hide", "title": "Hidden"}],
            "strong_held": True,
            "held_count": 1,
            "route_count": 1,
        },
    )

    brief = desk_ask_grounding.build_ask_desk_grounding_brief(object(), "stablecoin")
    assert "held: Stablecoin panel [stablecoin_panel]" in brief
    assert "should_hide" not in brief
    assert "Declared collectable routes" not in brief


def test_measure_strips_context_prefix(monkeypatch):
    from scripts.research_data_mcp import desk_ask_grounding

    seen = {}

    def _fake_check(_gateway, q, **_k):
        seen["q"] = q
        return {
            "held": [],
            "routes": [{"title": "TWSE Open API", "source_id": "twse_official"}],
            "strong_held": False,
            "held_count": 0,
            "route_count": 1,
            "route_reason": "ok",
        }

    monkeypatch.setattr(
        "scripts.research_data_mcp.discover_desk.desk_check",
        _fake_check,
    )
    out = desk_ask_grounding.measure_ask_desk(
        object(),
        "[context: gdelt_asia_daily_country_panel] Do we have Taiwan equity prices?",
    )
    assert seen["q"] == "Do we have Taiwan equity prices?"
    assert out["routes"][0]["source_id"] == "twse_official"
    assert out["query"] == "Do we have Taiwan equity prices?"


def test_measure_prefers_open_discover_query(monkeypatch):
    from scripts.research_data_mcp import desk_ask_grounding

    seen = {}

    def _fake_check(_gateway, q, **_k):
        seen["q"] = q
        return {
            "held": [],
            "routes": [{"title": "TWSE Open API", "source_id": "twse_official"}],
            "strong_held": False,
            "held_count": 0,
            "route_count": 1,
            "route_reason": "ok",
        }

    monkeypatch.setattr(
        "scripts.research_data_mcp.discover_desk.desk_check",
        _fake_check,
    )
    out = desk_ask_grounding.measure_ask_desk(
        object(),
        "What should I collect next?",
        rail_context={
            "tab": "browse",
            "workspace": {"surface": "discover", "query": "Taiwan stock prices"},
        },
    )
    assert seen["q"] == "Taiwan stock prices"
    assert out["query"] == "Taiwan stock prices"


def test_serialize_desk_facts_ui_is_rows_not_prose(monkeypatch):
    from scripts.research_data_mcp.desk_ask_grounding import serialize_desk_facts_ui

    ui = serialize_desk_facts_ui(
        {
            "query": "Taiwan equity",
            "strong_held": False,
            "held_count": 0,
            "route_count": 1,
            "held": [],
            "routes": [
                {"title": "TWSE Open API", "source_id": "twse_official"},
            ],
        }
    )
    assert ui["routes"][0]["source_id"] == "twse_official"
    assert "TWSE Open API" in ui["routes"][0]["title"]
    # no conversational answer field
    assert "reply" not in ui
    assert "summary" not in ui


def test_serialize_hides_routes_when_strong_held():
    from scripts.research_data_mcp.desk_ask_grounding import serialize_desk_facts_ui

    ui = serialize_desk_facts_ui(
        {
            "strong_held": True,
            "held": [{"title": "Panel", "dataset_id": "x"}],
            "routes": [{"title": "Hidden", "source_id": "nope"}],
        }
    )
    assert ui["held"][0]["dataset_id"] == "x"
    assert ui["routes"] == []


def test_measure_prefers_open_synthesis_objective(monkeypatch):
    from scripts.research_data_mcp import desk_ask_grounding

    seen = {}

    def _fake_check(_gateway, q, **_k):
        seen["q"] = q
        return {
            "held": [{"title": "Trust panel", "dataset_id": "trust"}],
            "routes": [],
            "strong_held": True,
            "held_count": 1,
            "route_count": 0,
            "route_reason": "ok",
        }

    monkeypatch.setattr(
        "scripts.research_data_mcp.discover_desk.desk_check",
        _fake_check,
    )
    out = desk_ask_grounding.measure_ask_desk(
        object(),
        "What should we do next?",
        rail_context={
            "tab": "synthesis",
            "surface": "synthesis",
            "workspace": {
                "surface": "synthesis",
                "objective": "Join trust and engagement panels at weekly grain",
            },
        },
    )
    assert seen["q"] == "Join trust and engagement panels at weekly grain"
    assert out["query"] == "Join trust and engagement panels at weekly grain"


def test_dual_measure_when_typed_ask_diverges(monkeypatch):
    from scripts.research_data_mcp import desk_ask_grounding

    seen = []

    def _fake_check(_gateway, q, **_k):
        seen.append(q)
        if "Taiwan" in q:
            return {
                "held": [],
                "routes": [{"title": "TWSE", "source_id": "twse_official"}],
                "strong_held": False,
                "held_count": 0,
                "route_count": 1,
                "route_reason": "ok",
            }
        return {
            "held": [{"title": "IDX panel", "dataset_id": "idx_panel", "analysis_readiness": "registered"}],
            "routes": [],
            "strong_held": True,
            "held_count": 1,
            "route_count": 0,
            "route_reason": "ok",
        }

    monkeypatch.setattr(
        "scripts.research_data_mcp.discover_desk.desk_check",
        _fake_check,
    )
    out = desk_ask_grounding.measure_ask_desk(
        object(),
        "Compare this to Indonesia equities coverage",
        rail_context={
            "tab": "browse",
            "workspace": {"surface": "discover", "query": "Taiwan stock prices"},
        },
    )
    assert seen[0] == "Taiwan stock prices"
    assert "Indonesia" in seen[1]
    assert out["secondary_query"]
    assert any(r.get("source_id") == "twse_official" for r in out["routes"])
    assert any(r.get("dataset_id") == "idx_panel" for r in out["held"])
    ui = desk_ask_grounding.serialize_desk_facts_ui(out)
    assert ui["secondary_query"]
    assert any(r.get("analysis_readiness") == "registered" for r in ui["held"])


def test_queries_diverge_on_shared_domain_different_subject():
    from scripts.research_data_mcp.desk_ask_grounding import queries_diverge, resolve_ask_measure_queries

    assert queries_diverge(
        "Taiwan stock prices",
        "Also compare Indonesia stock prices coverage vs what is open.",
    )
    assert not queries_diverge(
        "Taiwan stock prices",
        "What should I collect next?",
    )
    primary, secondary = resolve_ask_measure_queries(
        "Also compare Indonesia stock prices coverage vs what is open.",
        {
            "tab": "browse",
            "workspace": {"surface": "discover", "query": "Taiwan stock prices"},
        },
    )
    assert primary == "Taiwan stock prices"
    assert "Indonesia" in (secondary or "")


def test_library_selected_asset_labels_injected(monkeypatch):
    from scripts.research_data_mcp import desk_ask_grounding

    monkeypatch.setattr(
        "scripts.research_data_mcp.discover_desk.desk_check",
        lambda *_a, **_k: {
            "held": [],
            "routes": [],
            "strong_held": False,
            "held_count": 0,
            "route_count": 0,
            "route_reason": "ok",
        },
    )
    out = desk_ask_grounding.measure_ask_desk(
        object(),
        "Can I query this?",
        rail_context={
            "tab": "library",
            "dataset_id": "stablecoin_trust_engagement_weekly",
            "entity": {
                "kind": "dataset",
                "id": "stablecoin_trust_engagement_weekly",
                "title": "Stablecoin Trust-Engagement Weekly Panel",
            },
            "selected": {
                "dataset_id": "stablecoin_trust_engagement_weekly",
                "title": "Stablecoin Trust-Engagement Weekly Panel",
                "analysis_readiness": "query_ready",
                "grain": "week",
                "local_ready": True,
            },
            "workspace": {
                "surface": "library",
                "dataset_id": "stablecoin_trust_engagement_weekly",
            },
        },
    )
    assert out["held"][0]["dataset_id"] == "stablecoin_trust_engagement_weekly"
    assert out["held"][0]["analysis_readiness"] == "query_ready"
    brief = desk_ask_grounding.format_ask_desk_grounding_brief(out)
    assert "readiness=query_ready" in brief
    assert "grain=week" in brief


def test_synthesis_mapped_evidence_injected(monkeypatch):
    from scripts.research_data_mcp import desk_ask_grounding

    monkeypatch.setattr(
        "scripts.research_data_mcp.discover_desk.desk_check",
        lambda *_a, **_k: {
            "held": [],
            "routes": [],
            "strong_held": False,
            "held_count": 0,
            "route_count": 0,
            "route_reason": "ok",
        },
    )
    out = desk_ask_grounding.measure_ask_desk(
        object(),
        "What maps to this construct?",
        rail_context={
            "tab": "synthesis",
            "workspace": {
                "surface": "synthesis",
                "objective": "Keeling acceleration",
                "mapped_evidence": [
                    {
                        "dataset_id": "craft_raw_githubuserconten_2eb2f7cf1f",
                        "title": "Mauna Loa monthly CO2",
                        "grain": "month",
                        "coverage": "1958-03 to 2026-06",
                        "status": "held",
                    }
                ],
            },
        },
    )
    assert out["held"][0]["dataset_id"] == "craft_raw_githubuserconten_2eb2f7cf1f"
    assert out["held"][0]["grain"] == "month"


def test_synthesis_related_holdings_expand_upstream(monkeypatch):
    from scripts.research_data_mcp import desk_ask_grounding

    monkeypatch.setattr(
        "scripts.research_data_mcp.discover_desk.desk_check",
        lambda *_a, **_k: {
            "held": [
                {
                    "dataset_id": "synthesis_keeling_accel_monthly_v1",
                    "title": "Keeling accel",
                    "analysis_readiness": "query_ready",
                    "local_ready": True,
                }
            ],
            "routes": [],
            "strong_held": True,
            "held_count": 1,
            "route_count": 0,
            "route_reason": "ok",
        },
    )

    class _GW:
        def describe_dataset(self, dataset_id: str):
            catalog = {
                "synthesis_keeling_accel_monthly_v1": {
                    "dataset_id": "synthesis_keeling_accel_monthly_v1",
                    "title": "Keeling accel",
                    "analysis_readiness": "query_ready",
                    "lineage": {"upstream_dataset_ids": ["keeling_mlo_monthly_clean"]},
                },
                "keeling_mlo_monthly_clean": {
                    "dataset_id": "keeling_mlo_monthly_clean",
                    "title": "Keeling clean",
                    "analysis_readiness": "query_ready",
                    "source_dataset_id": "craft_raw_githubuserconten_2eb2f7cf1f",
                    "grain": "month",
                },
                "craft_raw_githubuserconten_2eb2f7cf1f": {
                    "dataset_id": "craft_raw_githubuserconten_2eb2f7cf1f",
                    "title": "Raw MLO",
                    "analysis_readiness": "instant",
                },
            }
            return catalog[dataset_id]

    out = desk_ask_grounding.measure_ask_desk(_GW(), "Keeling acceleration")
    ids = [r["dataset_id"] for r in out["held"]]
    assert "synthesis_keeling_accel_monthly_v1" in ids
    assert "keeling_mlo_monthly_clean" in ids
    assert "craft_raw_githubuserconten_2eb2f7cf1f" in ids


def test_synthesis_related_holdings_reverse_from_input(monkeypatch):
    from scripts.research_data_mcp import desk_ask_grounding

    monkeypatch.setattr(
        "scripts.research_data_mcp.discover_desk.desk_check",
        lambda *_a, **_k: {
            "held": [
                {
                    "dataset_id": "keeling_mlo_monthly_clean",
                    "title": "Keeling clean",
                    "analysis_readiness": "query_ready",
                    "local_ready": True,
                }
            ],
            "routes": [],
            "strong_held": True,
            "held_count": 1,
            "route_count": 0,
            "route_reason": "ok",
        },
    )

    catalog = {
        "keeling_mlo_monthly_clean": {
            "dataset_id": "keeling_mlo_monthly_clean",
            "title": "Keeling clean",
            "analysis_readiness": "query_ready",
            "source_dataset_id": "craft_raw_githubuserconten_2eb2f7cf1f",
        },
        "craft_raw_githubuserconten_2eb2f7cf1f": {
            "dataset_id": "craft_raw_githubuserconten_2eb2f7cf1f",
            "title": "Raw MLO",
            "analysis_readiness": "instant",
        },
        "synthesis_keeling_accel_monthly_v1": {
            "dataset_id": "synthesis_keeling_accel_monthly_v1",
            "title": "Keeling accel",
            "analysis_readiness": "query_ready",
            "lineage": {"upstream_dataset_ids": ["keeling_mlo_monthly_clean"]},
        },
    }

    class _GW:
        def describe_dataset(self, dataset_id: str):
            return catalog[dataset_id]

        def list_datasets(self, q: str = "", limit: int = 16, **_kw):
            ql = (q or "").lower()
            rows = []
            for row in catalog.values():
                blob = f"{row.get('dataset_id','')} {row.get('title','')} {row.get('lineage','')}".lower()
                if ql and ql not in blob and ql not in str(row.get("lineage") or {}).lower():
                    # Still surface synthesis that cites this seed
                    up = (row.get("lineage") or {}).get("upstream_dataset_ids") or []
                    if q not in up and q not in str(row.get("dataset_id") or ""):
                        continue
                rows.append(row)
            return {"datasets": rows[:limit]}

    out = desk_ask_grounding.measure_ask_desk(_GW(), "Keeling")
    ids = [r["dataset_id"] for r in out["held"]]
    assert "keeling_mlo_monthly_clean" in ids
    assert "synthesis_keeling_accel_monthly_v1" in ids
    assert "craft_raw_githubuserconten_2eb2f7cf1f" in ids
