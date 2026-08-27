"""Two boundaries that wiring buried capability can silently cross:

1. Reporting status must not advance work. Asking a question is not an action.
2. A supplementary layer must never displace an authoritative one just because
   it finished first. Semantic is the fastest layer once resident, so ordering
   by completion silently inverted precedence.
"""

import time

import pytest


class _Calls:
    """advance_workers swallows exceptions, so a raising stub would be silently
    caught and the test would pass vacuously. Count the calls instead."""

    def __init__(self):
        self.tick = 0
        self.tick_campaigns = 0
        self.archive = 0


class _Jobs:
    def __init__(self, calls):
        self._calls = calls

    def tick(self):
        self._calls.tick += 1


class _Gateway:
    class orchestrator:
        cfg: dict = {}

        class store:
            @staticmethod
            def get(_jid):
                return {"status": "completed"}

    def __init__(self, calls, phase="ready"):
        self.calls = calls
        self.jobs = _Jobs(calls)
        self._phase = phase
        self.repo_root = "."

    def tick_campaigns(self, limit=3):
        self.calls.tick_campaigns += 1

    def archive_to_gdrive(self, *a, **k):
        self.calls.archive += 1
        return {"job": {"id": "arch1"}}

    def get_campaign(self, _cid):
        return {"phase": self._phase, "status": self._phase, "goal": "g", "payload": {"promoted": []}}

    def list_campaign_artifacts(self, _cid):
        return {"artifacts": [{"name": "rows.parquet", "download_path": "/d/rows.parquet"}]}

    def get_dataset_card(self, _h):
        return {"handle": "campaign:c1", "title": "Delivered", "dataset_id": "ds_1"}

    def get_yzu_job(self, _jid):
        return {"status": "completed", "plan": {"job_type": "api_collect", "title": "t"}, "result": {}}

    def cluster_status(self, live=False):
        return {}


def _status(gw):
    from scripts.research_data_mcp.desk_direct_turns import try_direct_status_turn

    return try_direct_status_turn(gw, "status", {"campaign_id": "c1", "job_ids": []})


def test_status_turn_advances_nothing():
    calls = _Calls()
    turn = _status(_Gateway(calls))
    assert turn is not None
    assert calls.tick == 0, "status ticked job workers"
    assert calls.tick_campaigns == 0, "status advanced campaigns"


def test_status_turn_queues_no_archive():
    calls = _Calls()
    turn = _status(_Gateway(calls))
    assert calls.archive == 0, "status queued an archive job"
    assert "auto_archive" not in turn.action_result
    assert "Auto-archive" not in turn.reply


def test_status_still_reports_the_delivery():
    turn = _status(_Gateway(_Calls()))
    assert "Delivered" in turn.reply


def test_non_read_only_path_keeps_advancing():
    """read_only is opt-in, so deliberate actions retain their behaviour."""
    from scripts.research_data_mcp.procurement_delivery import format_campaign_status

    calls = _Calls()
    format_campaign_status(_Gateway(calls, phase="collect"), "c1", {}, read_only=False)
    assert calls.tick > 0 and calls.tick_campaigns > 0


def test_semantic_cannot_displace_authoritative_rows(monkeypatch):
    from scripts.research_data_mcp import datacite_prefetch as dp
    from scripts.research_data_mcp import datacite_vault_search as dvs

    def slow_api(*a, **k):
        time.sleep(0.30)
        return [{"doi": f"10.1/api{i}", "title": f"api {i}"} for i in range(6)]

    def instant_semantic(*a, **k):
        return [{"doi": f"10.1/sem{i}", "title": f"sem {i}", "match_type": "semantic"} for i in range(6)]

    monkeypatch.setattr(dp, "search_datacite_api", slow_api)
    monkeypatch.setattr(dvs, "search_curated_semantic", instant_semantic)
    monkeypatch.setattr(dvs, "search_scrape_snippets_fts", lambda *a, **k: [])
    monkeypatch.setattr(dvs, "search_curated_fts", lambda *a, **k: [])
    monkeypatch.setattr(dp, "search_curated_datasets", lambda *a, **k: [])
    monkeypatch.setenv("RESEARCH_SEMANTIC_FILL", "1")

    rows = dp.prefetch_datacite_layer(".", "q", limit=6, budget_seconds=5)
    dois = [r.get("doi") for r in rows]
    assert any(str(d).startswith("10.1/api") for d in dois), (
        f"the slower authoritative layer was displaced by semantic: {dois}"
    )


def test_semantic_still_fills_when_authoritative_layers_are_empty(monkeypatch):
    from scripts.research_data_mcp import datacite_prefetch as dp
    from scripts.research_data_mcp import datacite_vault_search as dvs

    monkeypatch.setattr(dp, "search_datacite_api", lambda *a, **k: [])
    monkeypatch.setattr(dvs, "search_scrape_snippets_fts", lambda *a, **k: [])
    monkeypatch.setattr(dvs, "search_curated_fts", lambda *a, **k: [])
    monkeypatch.setattr(dp, "search_curated_datasets", lambda *a, **k: [])
    monkeypatch.setattr(
        dvs, "search_curated_semantic",
        lambda *a, **k: [{"doi": "10.1/sem", "title": "sem", "match_type": "semantic"}],
    )
    monkeypatch.setenv("RESEARCH_SEMANTIC_FILL", "1")

    rows = dp.prefetch_datacite_layer(".", "q", limit=6, budget_seconds=5)
    assert [r.get("match_type") for r in rows] == ["semantic"]
