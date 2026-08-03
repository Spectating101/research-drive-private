"""Regression: query-ready selected Library assets must not be grounded as unknown + DOI collect."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "kernel"), str(REPO / "drive")]

from scripts.research_data_mcp.desk_asset_grounding import (
    enrich_rail_context,
    format_asset_grounding_block,
    ground_from_dataset_row,
    normalize_canonical_readiness,
    sanitize_grounded_reply,
    sanitize_next_steps,
    sanitize_suggested_prompts,
    suggested_prompts_for_asset,
)
from scripts.research_data_mcp.desk_brain import AgentTurn, _format_rail_context
from scripts.research_data_mcp.procurement_chat import ProcurementChatOrchestrator


GDELT_ASIA = "gdelt_asia_daily_country_panel"


def _gdelt_registry_row() -> dict:
    return {
        "dataset_id": GDELT_ASIA,
        "name": "GDELT Asia Daily Country News Shock Panel",
        "analysis_readiness": "instant",
        "access_shape": "local_derived_tables",
        "backend": "local_gdelt_panel_csv",
        "description": "Country-day news shock panel for Asia.",
        "local_root": "data_lake/news_shock_taxonomy/processed",
    }


def test_canonical_readiness_maps_instant_to_query_ready():
    assert normalize_canonical_readiness("instant") == "query_ready"
    assert normalize_canonical_readiness("Query-ready") == "query_ready"
    assert normalize_canonical_readiness("") == ""


def test_gdelt_row_grounds_query_ready_without_inventing_archive_proof():
    grounding = ground_from_dataset_row(_gdelt_registry_row())
    assert grounding["dataset_id"] == GDELT_ASIA
    assert grounding["canonical_readiness"] == "query_ready"
    assert grounding["query_ready"] is True
    assert grounding["asset_identity"]["dataset_id"] == GDELT_ASIA
    assert grounding["asset_identity"]["backend"] == "local_gdelt_panel_csv"
    proof = grounding["registry_proof"]
    assert proof["registry_row_loaded"] is True
    # Absent facts stay unknown — do not fabricate archive verification.
    assert proof["archive_verified"] is None
    assert proof["registry_readback"] is None
    assert "doi_collect" not in grounding["valid_next_actions"]
    assert "query_sample" in grounding["valid_next_actions"]


def test_enrich_rail_and_composer_context_include_grounding():
    rail = {
        "tab": "library",
        "mode": "ask",
        "dataset_id": GDELT_ASIA,
        "entity": {"kind": "dataset", "id": GDELT_ASIA, "title": "GDELT Asia"},
        "readiness": "Query-ready",
        "actions": ["preview_rows", "ask_about"],
    }
    enriched = enrich_rail_context(rail, _gdelt_registry_row())
    assert enriched["readiness"] == "query_ready"
    assert enriched["analysis_readiness"] == "instant"
    assert enriched["asset_identity"]["dataset_id"] == GDELT_ASIA
    assert enriched["registry_proof"]["registry_row_loaded"] is True
    assert "doi_collect" not in (enriched.get("valid_next_actions") or [])

    block = format_asset_grounding_block(enriched)
    assert "canonical_readiness: query_ready" in block
    assert GDELT_ASIA in block
    assert "Do not say readiness is unknown" in block
    assert "Do not offer DOI collection" in block

    formatted = _format_rail_context(enriched)
    assert "[Selected asset grounding" in formatted
    assert "query_ready" in formatted


def test_sanitize_strips_unknown_and_doi_for_query_ready():
    dirty = (
        f"**GDELT** (`{GDELT_ASIA}`) — readiness: unknown" + "\n"
        "You could Queue DOI collect for this asset next."
    )
    clean = sanitize_grounded_reply(dirty, "query_ready", dataset_id=GDELT_ASIA)
    assert "unknown" not in clean.lower()
    assert "readiness: query_ready" in clean
    assert "doi" not in clean.lower()

    prompts = sanitize_suggested_prompts(
        [f"Query sample rows from {GDELT_ASIA}", f"Queue DOI collect for {GDELT_ASIA}"],
        "query_ready",
    )
    assert prompts == [f"Query sample rows from {GDELT_ASIA}"]
    assert "DOI" not in " ".join(suggested_prompts_for_asset(GDELT_ASIA, "instant")).upper()

    steps = sanitize_next_steps(
        [
            {"label": "Query sample", "prompt": f"Query sample rows from {GDELT_ASIA}", "kind": "chat"},
            {"label": "Queue DOI collect", "prompt": f"Queue DOI collect for {GDELT_ASIA}", "kind": "chat"},
        ],
        "query_ready",
    )
    assert len(steps) == 1
    assert "DOI" not in steps[0]["label"].upper()


def test_absent_readiness_preserves_unknown_and_allows_doi():
    grounding = ground_from_dataset_row({"dataset_id": "mystery_panel"})
    assert grounding["canonical_readiness"] is None
    assert grounding["registry_proof"]["archive_verified"] is None
    prompts = suggested_prompts_for_asset("mystery_panel", None)
    assert any("DOI" in p.upper() for p in prompts)
    dirty = "readiness: unknown — Queue DOI collect for mystery_panel"
    assert sanitize_grounded_reply(dirty, None) == dirty


def test_build_next_steps_sanitizes_doi_for_grounded_query_ready():
    steps = ProcurementChatOrchestrator._build_next_steps(
        {
            "rail_context": enrich_rail_context(
                {"dataset_id": GDELT_ASIA},
                _gdelt_registry_row(),
            )
        },
        {},
        [f"Query sample rows from {GDELT_ASIA}", f"Queue DOI collect for {GDELT_ASIA}"],
    )
    blob = " ".join(f"{s.get('label')} {s.get('prompt')}" for s in steps)
    assert "DOI" not in blob.upper()
    assert "Query sample" in blob


def test_chat_pipeline_sanitizes_model_reply_for_selected_query_ready_asset(tmp_path: Path):
    gateway = MagicMock()
    gateway.repo_root = tmp_path
    gateway.describe_dataset.return_value = _gdelt_registry_row()
    chat = ProcurementChatOrchestrator(tmp_path)
    raw_turn = AgentTurn(
        plan={"action": "composer"},
        action_result={"action": "composer"},
        reply="GDELT readiness: unknown. Queue DOI collect for this asset.",
        suggested_prompts=["Queue DOI collect for gdelt_asia_daily_country_panel"],
    )

    with patch.object(chat, "_run_agent_turn", return_value=raw_turn):
        events = list(
            chat.chat_events(
                gateway,
                "status",
                rail_context={"dataset_id": GDELT_ASIA, "entity": {"kind": "dataset", "id": GDELT_ASIA}},
            )
        )

    complete = next(event["result"] for event in events if event.get("type") == "complete")
    assert "unknown" not in complete["reply"].lower()
    assert "doi" not in complete["reply"].lower()
    assert "query_ready" in complete["reply"]
    assert "doi" not in " ".join(complete["suggested_prompts"]).lower()
