"""Registry hydrate + Hugging Face collect flywheel."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1] / "drive"


def _enable_drive_first(repo: Path) -> None:
    """Give isolated promotion tests the same storage policy as production."""
    config = repo / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "storage_tiers.json").write_text(
        json.dumps({"rules": {"drive_first": True}}),
        encoding="utf-8",
    )


def test_dataset_needs_hydrate_when_remote_only(tmp_path: Path) -> None:
    from scripts.research_data_mcp.registry_hydrate import dataset_needs_hydrate

    spec = {
        "dataset_id": "demo_tickers",
        "local_path": "data_lake/demo/missing_tickers.json",
        "canonical_remote": "gdrive:Machine_Archive/x/collection/acquired/procured/demo_tickers",
        "source_of_truth": "gdrive",
    }
    assert dataset_needs_hydrate(tmp_path, spec) is True


def test_dataset_needs_hydrate_false_when_local_present(tmp_path: Path):
    from scripts.research_data_mcp.registry_hydrate import dataset_needs_hydrate

    local = tmp_path / "tickers.json"
    local.write_text('{"0": {"ticker": "AAPL"}}', encoding="utf-8")
    spec = {
        "local_path": str(local.relative_to(REPO)) if str(local).startswith(str(REPO)) else "x",
        "canonical_remote": "gdrive:foo/bar",
    }
    # Use absolute path under tmp_path
    spec = {
        "local_path": "data_lake/sec/company_tickers.json",
        "canonical_remote": "gdrive:foo/bar",
    }
    tick = REPO / "data_lake/sec/company_tickers.json"
    if tick.is_file():
        assert dataset_needs_hydrate(REPO, spec) is False
    else:
        pytest.skip("sec tickers not on disk")


def test_hf_slug_and_registry_id():
    from scripts.hf_collect_dataset import hf_slug, registry_dataset_id

    assert hf_slug("financial_phrasebank") == "financial_phrasebank"
    assert hf_slug("hf:org/name") == "org__name"
    assert registry_dataset_id("org/name") == "hf_org__name"


def test_promote_huggingface_collect_with_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from scripts.research_data_mcp.registry_promotion import RegistryPromoter

    repo = tmp_path
    reg = repo / "config/research_query_registry.json"
    reg.parent.mkdir(parents=True)
    reg.write_text(json.dumps({"datasets": []}), encoding="utf-8")
    _enable_drive_first(repo)

    slug = "org__demo"
    out_dir = repo / "data_lake/procured/huggingface" / slug
    out_dir.mkdir(parents=True)
    parquet = out_dir / "train.parquet"
    parquet.write_bytes(b"PAR1")  # minimal stub
    manifest = {
        "dataset_id": "org/demo",
        "registry_dataset_id": "hf_org__demo",
        "primary_parquet": f"data_lake/procured/huggingface/{slug}/train.parquet",
        "canonical_dir": f"data_lake/procured/huggingface/{slug}",
        "files": [{"path": f"data_lake/procured/huggingface/{slug}/train.parquet"}],
        "title": "Demo HF",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    promoter = RegistryPromoter(repo, reg)
    job = {
        "id": "job1",
        "status": "completed",
        "plan": {"job_type": "huggingface_collect", "hf_dataset_id": "org/demo"},
        "result": {"materialized": manifest},
    }
    promoted = promoter.promote_huggingface_collect(job, hf_dataset_id="org/demo")
    assert len(promoted) == 1
    assert promoted[0]["dataset_id"] == "hf_org__demo"

    doc = json.loads(reg.read_text(encoding="utf-8"))
    row = next(d for d in doc["datasets"] if d["dataset_id"] == "hf_org__demo")
    assert row["backend"] == "local_parquet_panel"
    assert row["partition_id"] == "acquired.procured"
    assert row["source_id"] == "huggingface"


def test_query_dataset_attempts_hydrate(monkeypatch: pytest.MonkeyPatch):
    from scripts.research_data_mcp.search import SearchService
    from scripts.research_query_engine.engine import ResearchQueryEngine

    reg = REPO / "config/research_query_registry.json"
    engine = ResearchQueryEngine(reg, repo_root=REPO)
    svc = SearchService(engine, reg, REPO)

    calls: list[tuple[str, bool]] = []

    def fake_ensure(repo_root, spec, **kwargs):
        calls.append((str(spec.get("dataset_id")), bool(kwargs.get("dry_run"))))
        return {"skipped": True}

    monkeypatch.setattr(
        "scripts.research_data_mcp.registry_hydrate.ensure_registry_local_bytes",
        fake_ensure,
    )
    svc.query_dataset("collection_queue_status", {"limit": 1})
    assert ("collection_queue_status", True) in calls
