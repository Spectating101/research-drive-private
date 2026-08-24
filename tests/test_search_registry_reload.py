import os
import time
from pathlib import Path

from scripts.research_data_mcp.search import SearchService
from scripts.research_query_engine.engine import ResearchQueryEngine


def test_search_service_reloads_registry_when_file_changes(tmp_path: Path) -> None:
    reg = tmp_path / "registry.json"
    reg.write_text('{"datasets": [{"dataset_id": "alpha", "name": "Alpha"}]}', encoding="utf-8")
    engine = ResearchQueryEngine(registry_path=reg, repo_root=tmp_path)
    svc = SearchService(engine, reg, tmp_path)
    assert len(engine.datasets) == 1

    reg.write_text(
        '{"datasets": [{"dataset_id": "alpha", "name": "Alpha"}, {"dataset_id": "beta", "name": "Beta"}]}',
        encoding="utf-8",
    )
    time.sleep(0.01)
    os.utime(reg, (reg.stat().st_atime, reg.stat().st_mtime + 1))
    svc.ensure_registry_fresh()
    assert "beta" in engine.datasets
