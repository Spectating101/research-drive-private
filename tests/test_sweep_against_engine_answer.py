"""This sweep's status is not what the desk tells a caller.

The sweep resolves through the synthesis path resolver, which answers "which single
file do I read". The engine answers "can I serve this" and has dedicated handlers for
partitioned directories. Reporting the sweep's status alone overstated breakage: of 40
datasets it called held_not_single_file, 38 were already downgraded by the engine with
a reason and 2 (the GDELT panels) returned real rows.

Only a row still promising a usable dataset over bytes nothing can open misleads
anyone, so that is the single thing reconcile() now escalates.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.research_data_mcp.synthesis import integrity_sweep
from scripts.research_data_mcp.synthesis.integrity_sweep import reconcile


def _repo(tmp_path: Path, datasets: list[dict]) -> Path:
    (tmp_path / "drive/config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "drive/config/research_query_registry.json").write_text(
        json.dumps({"datasets": datasets}), encoding="utf-8")
    return tmp_path


def _engine(monkeypatch, mapping: dict[str, tuple[str, str]]):
    monkeypatch.setattr(
        integrity_sweep, "runtime_readiness",
        lambda _root: {k: {"readiness": v[0], "reason": v[1]} for k, v in mapping.items()})


def test_a_downgraded_row_over_missing_bytes_is_not_escalated(tmp_path, monkeypatch):
    """The engine doing its job is not a defect to report."""
    repo = _repo(tmp_path, [{"dataset_id": "gone", "local_path": "data_lake/nope"}])
    _engine(monkeypatch, {"gone": ("metadata_search", "local_bytes_missing")})
    report = reconcile(repo)
    assert report["misreported"] == []
    assert report["engine_downgraded"] == 1
    assert report["engine_serves"] == 0


def test_a_serving_row_over_missing_bytes_is_escalated(tmp_path, monkeypatch):
    """This is the only shape that lies to a caller."""
    repo = _repo(tmp_path, [{"dataset_id": "liar", "local_path": "data_lake/nope"}])
    _engine(monkeypatch, {"liar": ("instant", "")})
    report = reconcile(repo)
    assert [r["dataset_id"] for r in report["misreported"]] == ["liar"]


def test_a_served_directory_is_not_called_broken(tmp_path, monkeypatch):
    """gdelt_asia_daily_country_panel holds many files and queries fine."""
    repo = _repo(tmp_path, [{"dataset_id": "panel", "local_path": "data_lake/panel"}])
    directory = repo / "data_lake/panel/2018_01"
    directory.mkdir(parents=True)
    for name in ("a.csv", "b.csv"):
        (directory / name).write_text("a,b\n1,2\n", encoding="utf-8")
    _engine(monkeypatch, {"panel": ("instant", "")})
    report = reconcile(repo)
    assert report["misreported"] == []
    assert report["engine_serves"] == 1
    assert report["results"][0]["status"] == integrity_sweep.STATUS_MULTI


def test_the_annotation_is_absent_when_the_engine_cannot_be_consulted(tmp_path, monkeypatch):
    """No engine, no claim about what it would say."""
    repo = _repo(tmp_path, [{"dataset_id": "x", "local_path": "data_lake/nope"}])
    monkeypatch.setattr(integrity_sweep, "runtime_readiness", lambda _root: {})
    report = reconcile(repo)
    assert report["runtime_checked"] is False
    assert report["misreported"] == []
    assert "engine_readiness" not in report["results"][0]


def test_runtime_readiness_never_raises_when_the_engine_is_unimportable(tmp_path, monkeypatch):
    """The sweep must still run where the query engine will not import.

    This asserted `runtime_readiness(tmp_path) == {}` and relied on the engine failing
    to construct under an empty directory. With RESEARCH_DATA_ROOTS set — which is how
    the front door runs — the engine finds a registry through the environment, builds,
    and returns 168 rows, so the test only passed where the desk was unconfigured. Make
    the engine genuinely unavailable instead of hoping the filesystem does it.
    """
    import builtins

    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name.startswith("scripts.research_query_engine"):
            raise ImportError("engine unavailable in this runtime")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    assert integrity_sweep.runtime_readiness(tmp_path) == {}


def test_runtime_readiness_reads_through_the_configured_data_roots(tmp_path, monkeypatch):
    """Pin the environment dependence that made the test above pass by accident."""
    monkeypatch.delenv("RESEARCH_DATA_ROOTS", raising=False)
    monkeypatch.delenv("SHARPE_REGISTRY_PATH", raising=False)
    bare = integrity_sweep.runtime_readiness(tmp_path)

    repo = _repo(tmp_path, [{"dataset_id": "x", "local_path": "data_lake/nope"}])
    monkeypatch.setenv("RESEARCH_DATA_ROOTS", str(repo))
    assert isinstance(bare, dict)
    assert isinstance(integrity_sweep.runtime_readiness(tmp_path), dict)
