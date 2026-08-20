from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts.research_data_mcp.acquisition_handoff import (
    build_acquisition_handoff,
    validate_webfetch_handoff,
)
from scripts.research_data_mcp.acquisition_options import build_acquisition_options
from scripts.research_data_mcp.licensed_sources import (
    ingest_crsp_sas_index,
    inspect_source,
    stage_compustat_export,
)
from scripts.research_data_mcp.procurement_fast import declared_local_path, local_path_has_data


def test_webfetch_requires_cursor_authority_and_does_not_fetch() -> None:
    bad = validate_webfetch_handoff(
        fetched_url="https://catalog.example.org/patents",
        selected_url="https://catalog.example.org/patents.csv",
        links=["https://catalog.example.org/patents.csv"],
        selection_authority="backend_ranker",
    )
    assert bad["ok"] is False
    assert "selection_authority" in bad["errors"][0]

    good = validate_webfetch_handoff(
        fetched_url="https://catalog.example.org/patents",
        selected_url="https://catalog.example.org/patents.csv",
        title="Patent rows",
        provider="Cursor webfetch",
        links=["https://catalog.example.org/patents.csv"],
        content_sha256="a" * 64,
    )
    assert good["ok"] is True
    assert good["candidate"]["url"].endswith("patents.csv")
    assert good["side_effects"].startswith("none")


def test_webfetch_handoff_builds_explicit_http_plan_without_substitution() -> None:
    gateway = SimpleNamespace(
        repo_root=Path(__file__).resolve().parents[1],
        procurement=SimpleNamespace(manifest_plan_from_connector=lambda *_a, **_k: (_ for _ in ()).throw(KeyError("none"))),
    )
    out = build_acquisition_handoff(
        gateway,
        research_need="patent grants",
        title="Selected patent rows",
        provider="Cursor webfetch",
        webfetch={
            "fetched_url": "https://catalog.example.org/patents",
            "selected_url": "https://catalog.example.org/patents.csv",
            "links": ["https://catalog.example.org/patents.csv"],
        },
    )
    assert out["ok"] is True
    assert out["candidate"]["url"] == "https://catalog.example.org/patents.csv"
    assert out["collection"]["plan"]["items"][0]["url"] == "https://catalog.example.org/patents.csv"
    assert out["side_effects"].startswith("none")


def test_webfetch_and_huggingface_share_the_same_explicit_candidate_contract() -> None:
    gateway = SimpleNamespace(
        repo_root=Path(__file__).resolve().parents[1],
        procurement=SimpleNamespace(manifest_plan_from_connector=lambda *_a, **_k: (_ for _ in ()).throw(KeyError("none"))),
    )
    out = build_acquisition_handoff(
        gateway,
        source_id="huggingface",
        connector_id="huggingface",
        provider="Hugging Face",
        webfetch={
            "fetched_url": "https://huggingface.co/datasets",
            "selected_url": "https://huggingface.co/datasets/Pyke/patent_abstract",
            "links": ["https://huggingface.co/datasets/Pyke/patent_abstract"],
        },
    )
    assert out["ok"] is True
    assert out["collection"]["plan"]["job_type"] == "huggingface_collect"
    assert out["collection"]["plan"]["hf_dataset_id"] == "Pyke/patent_abstract"


def test_licensed_status_is_read_only_and_distinguishes_raw_from_queryable(tmp_path: Path) -> None:
    (tmp_path / "data_lake/crsp/raw/stock").mkdir(parents=True)
    (tmp_path / "data_lake/crsp/raw/stock/payload.zip").write_bytes(b"raw")
    result = inspect_source(tmp_path, "crsp_moveit")
    row = result["sources"][0]
    assert row["status"] in {"acquired_pending_parse", "partially_queryable_safe_sas_extract"}
    assert row["raw"]["files"] >= 1
    if row["queryable"]:
        assert "crsp_us_index_history" in row["queryable_dataset_ids"]
    else:
        assert row["queryable_dataset_ids"] == []
    assert row["side_effects"].startswith("none")


def test_crsp_sas_ingest_is_bounded_and_excludes_daily_ciz(tmp_path: Path, monkeypatch) -> None:
    import pandas as pd

    source = tmp_path / "data_lake/crsp/extracted/package/dsp500.sas7bdat"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"test fixture")

    def fake_read_sas(path, **_kwargs):
        assert str(path).endswith("dsp500.sas7bdat")
        return pd.DataFrame({"CALDT": ["2024-01-02"], "SPINDX": [4700.0]})

    monkeypatch.setattr(pd, "read_sas", fake_read_sas)
    dry = ingest_crsp_sas_index(tmp_path)
    assert dry["ok"] is True
    assert dry["status"] == "validated"
    assert dry["daily_ciz_included"] is False
    assert dry["output"] is None

    destination = tmp_path / "materialized"
    written = ingest_crsp_sas_index(tmp_path, destination_root=destination, write=True)
    assert written["ok"] is True
    assert written["status"] == "staged"
    assert (destination / "data_lake/crsp/processed/us_index_history.parquet").is_file()
    assert (destination / "data_lake/crsp/processed/crsp_index_ingest.json").is_file()
    assert written["promotion"].startswith("not performed")


def test_acquisition_options_combines_evidence_but_never_selects(tmp_path: Path) -> None:
    gateway = SimpleNamespace(
        repo_root=tmp_path,
        discover_search=lambda *_a, **_k: {
            "sections": [{"rows": [{"dataset_id": "held_x", "title": "Held evidence"}]}]
        },
        discover_source_search=lambda *_a, **_k: {
            "results": [{"source_id": "huggingface", "candidate_key": "source:huggingface:hf"}],
            "sources_tried": ["source_map"],
            "remote_search": {"attempted": False},
        },
    )
    out = build_acquisition_options(gateway, "patent data", live=False)
    assert out["ok"] is True
    assert {section["id"] for section in out["sections"]} == {"library_evidence", "source_options"}
    assert out["selection_policy"]["model_selects"] is True
    assert out["selection_policy"]["backend_selects"] is False
    assert out["side_effects"].startswith("none")


def test_acquisition_options_requires_a_research_need(tmp_path: Path) -> None:
    out = build_acquisition_options(SimpleNamespace(repo_root=tmp_path), "")
    assert out["ok"] is False
    assert out["sections"] == []
    assert out["side_effects"] == "none"


def test_all_source_status_returns_flat_model_rows(tmp_path: Path) -> None:
    result = inspect_source(tmp_path)
    assert result["total"] == len(result["sources"])
    assert {row["source_id"] for row in result["sources"]} >= {
        "crsp_moveit",
        "capital_iq_compustat",
        "lseg_edp",
        "huggingface",
        "datacite",
        "zenodo",
        "openalex",
        "webfetch",
    }
    assert all("status" in row and "next_action" in row for row in result["sources"])


def test_procurement_ready_flag_uses_configured_bulk_roots(tmp_path: Path, monkeypatch) -> None:
    bulk = tmp_path / "bulk"
    (bulk / "data_lake/crsp/processed").mkdir(parents=True)
    (bulk / "data_lake/crsp/processed/us_index_history.parquet").write_bytes(b"PAR1")
    monkeypatch.setenv("RESEARCH_DATA_ROOTS", str(bulk))
    assert local_path_has_data(tmp_path, "data_lake/crsp/processed/us_index_history.parquet") is True
    assert declared_local_path(
        {"local_root": "data_lake/crsp", "local_file": "processed/us_index_history.parquet"}
    ) == "data_lake/crsp/processed/us_index_history.parquet"


def test_compustat_staging_normalizes_to_isolated_root(tmp_path: Path) -> None:
    import pandas as pd

    source = tmp_path / "export.csv"
    pd.DataFrame(
        [
            {"GVKEY": 1, "Data Date": "2024-12-31", "Ticker": "AAA", "SALE": 10},
            {"GVKEY": 1, "Data Date": "2024-12-31", "Ticker": "AAA", "SALE": 10},
        ]
    ).to_csv(source, index=False)
    stage = tmp_path / "isolated-stage"
    result = stage_compustat_export(Path(__file__).resolve().parents[1], source, stage)
    assert result["ok"] is True
    assert result["rows"] == 1
    assert (stage / "na_fundamentals_annual.parquet").is_file()
    assert not (tmp_path / "data_lake/compustat/processed/na_fundamentals_annual.parquet").exists()
    assert result["promotion"].startswith("not performed")
