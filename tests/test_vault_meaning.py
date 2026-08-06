#!/usr/bin/env python3
"""Vault meaning contract — show vs store fields."""

from __future__ import annotations

import pytest

from scripts.research_data_mcp.vault_meaning import (
    apply_meaning_to_row,
    is_ops_face,
    meaning_match_blob,
    normalize_meaning_payload,
)


def test_ops_face_detects_jargon():
    assert is_ops_face("Custom collect · raw.githubusercontent.com")
    assert is_ops_face("Route prove · TWSE BWIBBU_ALL")
    assert is_ops_face("Synthesis: Using the Library asset Custom collect · x")
    assert not is_ops_face("Mauna Loa monthly CO₂")
    assert not is_ops_face("Taiwan stock P/E, P/B, dividend yield")


def test_faculty_objective_rewrites_custom_collect():
    from scripts.research_data_mcp.vault_meaning import faculty_objective

    faces = {
        "craft_raw_githubuserconten_2eb2f7cf1f": {"title": "Mauna Loa Monthly CO₂ Concentrations"},
    }
    raw = (
        "Using the Library asset Custom collect · raw.githubusercontent.com "
        "(dataset_id craft_raw_githubuserconten_2eb2f7cf1f), build a monthly "
        "Keeling Curve acceleration indicator."
    )
    out = faculty_objective(raw, faces)
    assert "Custom collect" not in out
    assert "dataset_id" not in out
    assert "Mauna Loa Monthly CO₂ Concentrations" in out
    assert "Keeling Curve acceleration" in out


def test_enrich_synthesis_thread_faces_objective_and_query_ready():
    from scripts.research_data_mcp.vault_meaning import enrich_synthesis_thread_face

    catalog = {
        "craft_raw_githubuserconten_2eb2f7cf1f": {
            "dataset_id": "craft_raw_githubuserconten_2eb2f7cf1f",
            "display_name": "Mauna Loa Monthly CO₂ Concentrations",
            "analysis_readiness": "instant",
        },
        "synthesis_keeling_accel_monthly_v1": {
            "dataset_id": "synthesis_keeling_accel_monthly_v1",
            "display_name": "Monthly Keeling Curve acceleration",
            "analysis_readiness": "query_ready",
        },
        "keeling_mlo_monthly_clean": {
            "dataset_id": "keeling_mlo_monthly_clean",
            "display_name": "Mauna Loa Monthly CO₂ Record",
            "analysis_readiness": "query_ready",
        },
    }

    thread = {
        "id": "t1",
        "title": "Monthly Keeling Curve acceleration",
        "objective": (
            "Using the Library asset Custom collect · raw.githubusercontent.com "
            "(dataset_id craft_raw_githubuserconten_2eb2f7cf1f), build a monthly "
            "Keeling Curve acceleration indicator."
        ),
        "materialisation": "registered",
        "state": {
            "objective": (
                "Using the Library asset Custom collect · raw.githubusercontent.com "
                "(dataset_id craft_raw_githubuserconten_2eb2f7cf1f), build a monthly "
                "Keeling Curve acceleration indicator."
            ),
            "nodes": [
                {
                    "id": "mlo",
                    "type": "source",
                    "layer": "evidence",
                    "dataset_id": "craft_raw_githubuserconten_2eb2f7cf1f",
                    "label": "raw",
                    "status": "held",
                },
                {
                    "id": "keeling_accel_monthly",
                    "type": "output",
                    "layer": "output",
                    "dataset_id": "synthesis_keeling_accel_monthly_v1",
                    "label": "accel",
                },
            ],
            "execution_spec": {
                "input_dataset_id": "keeling_mlo_monthly_clean",
                "output_dataset_id": "synthesis_keeling_accel_monthly_v1",
                "transforms": [{"op": "diff", "column": "sa_ppm", "periods": 12}],
            },
            "execution": {
                "status": "registered",
                "output_dataset_id": "synthesis_keeling_accel_monthly_v1",
                "rows": 820,
            },
        },
    }
    out = enrich_synthesis_thread_face(thread, catalog.get)
    assert "Custom collect" not in out["objective"]
    assert "Mauna Loa" in out["objective"]
    assert out["state"]["execution"]["status"] == "query_ready"
    assert out["state"]["execution"]["query_ready"] is True
    assert out["materialisation"] == "query_ready"
    labels = [n.get("label") for n in out["state"]["nodes"]]
    assert "Mauna Loa Monthly CO₂ Concentrations" in labels
    assert "Monthly Keeling Curve acceleration" in labels


def test_normalize_and_apply_meaning():
    meaning = normalize_meaning_payload(
        {
            "title": "Mauna Loa monthly CO₂",
            "description": (
                "Monthly carbon dioxide measurements from the Mauna Loa observatory since 1958 "
                "— the classic Keeling Curve record of rising atmospheric CO₂."
            ),
            "recommended_use": "Track long-term atmospheric CO₂ month by month.",
            "aliases": ["Charles Keeling CO2 monthly", "Keeling Curve"],
            "keywords": ["carbon dioxide", "mauna loa", "keeling"],
            "meaning_about": "Also known as the Keeling Curve / Charles Keeling monthly CO2 series.",
        }
    )
    row = apply_meaning_to_row(
        {
            "dataset_id": "keeling_mlo_monthly_clean",
            "name": "Custom collect · raw.githubusercontent.com",
        },
        meaning,
        labeled_by="copilot-ly",
        model="copilot-ly",
    )
    assert row["dataset_id"] == "keeling_mlo_monthly_clean"
    assert row["title"] == "Mauna Loa monthly CO₂"
    assert row["name"] == row["title"]
    assert "Charles Keeling CO2 monthly" in row["aliases"]
    assert "keeling" in row["keywords"]
    assert row["ops_title"].startswith("Custom collect")
    blob = meaning_match_blob(row)
    assert "charles keeling" in blob
    assert "mauna loa" in blob


def test_rejects_ops_title_from_model():
    with pytest.raises(ValueError):
        normalize_meaning_payload(
            {
                "title": "Custom collect · raw.githubusercontent.com",
                "description": "Procured via http_manifest",
            }
        )
