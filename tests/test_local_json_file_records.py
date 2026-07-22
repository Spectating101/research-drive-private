"""local_json_file: object-values maps become limited rows; documents stay one row."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.research_query_engine.engine import ResearchQueryEngine


def _engine(tmp_path: Path, datasets: list[dict]) -> ResearchQueryEngine:
    reg = tmp_path / "config" / "research_query_registry.json"
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(json.dumps({"datasets": datasets}), encoding="utf-8")
    return ResearchQueryEngine(reg, repo_root=tmp_path)


def test_object_values_map_honors_limit_and_fields(tmp_path: Path) -> None:
    payload = {
        "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
        "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "2": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
    }
    path = tmp_path / "data_lake" / "sec" / "company_tickers.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")

    eng = _engine(
        tmp_path,
        [{"dataset_id": "sec_company_tickers", "backend": "local_json_file", "local_path": "data_lake/sec/company_tickers.json"}],
    )

    limited = eng.query("sec_company_tickers", limit=2)
    assert limited.meta.get("record_shape") == "object_values"
    assert limited.meta.get("returned") == 2
    assert [row["ticker"] for row in limited.rows] == ["NVDA", "AAPL"]

    projected = eng.query("sec_company_tickers", limit=2, fields="ticker,title")
    assert projected.rows == [{"ticker": "NVDA", "title": "NVIDIA CORP"}, {"ticker": "AAPL", "title": "Apple Inc."}]


def test_document_json_remains_single_row_with_optional_fields(tmp_path: Path) -> None:
    payload = {"status": "ok", "warnings": ["late"], "gates": {"ready": True}}
    path = tmp_path / "reports" / "doc.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    eng = _engine(tmp_path, [{"dataset_id": "sample_document", "backend": "local_json_file", "local_path": "reports/doc.json"}])

    full = eng.query("sample_document", limit=1)
    assert len(full.rows) == 1
    assert full.rows[0]["gates"] == {"ready": True}
    assert full.meta.get("record_shape") is None
    assert eng.query("sample_document", fields="status,warnings").rows == [{"status": "ok", "warnings": ["late"]}]


def test_mixed_scalar_map_is_not_treated_as_records(tmp_path: Path) -> None:
    payload = {"network": "sepolia", "contracts": {"token": "0xabc"}}
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    eng = _engine(tmp_path, [{"dataset_id": "runtime_doc", "backend": "local_json_file", "local_path": "runtime.json"}])

    result = eng.query("runtime_doc", limit=50)
    assert result.rows == [payload]
    assert result.meta.get("record_shape") is None
