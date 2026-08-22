"""Capability that exists but nothing calls is indistinguishable from a missing
feature. These pin the direct-turn handlers to the formatters they were built
to use, so a rich answer cannot silently regress to a truncated identifier."""

import ast
from pathlib import Path

import pytest

DRIVE = Path(__file__).resolve().parents[1]
TURNS = DRIVE / "scripts/research_data_mcp/desk_direct_turns.py"


def _fn(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name), None
    )


def _names(node):
    out = set()
    for c in ast.walk(node):
        if isinstance(c, ast.Call):
            out.add(c.func.id if isinstance(c.func, ast.Name) else getattr(c.func, "attr", ""))
        elif isinstance(c, ast.ImportFrom):
            out |= {a.name for a in c.names}
    return out


def test_status_turn_reports_real_campaign_state():
    fn = _fn(TURNS, "try_direct_status_turn")
    assert fn is not None
    assert "format_campaign_status" in _names(fn)


class _Store:
    def get(self, _jid):
        return {"status": "completed"}


class _Orch:
    cfg: dict = {}
    store = _Store()


class _Gateway:
    orchestrator = _Orch()

    def get_campaign(self, _cid):
        return {
            "phase": "collect",
            "status": "running",
            "goal": "OpenSea NFT trade history",
            "payload": {
                "collect_job_ids": ["c1234567890ab"],
                "recommendations": [{"recommended_action": "collect", "url": "https://x/y"}],
            },
        }

    def get_yzu_job(self, _jid):
        return {
            "status": "completed",
            "plan": {"job_type": "api_collect", "title": "OpenSea events"},
            "result": {"registry_promotion": [{"dataset_id": "opensea_events_daily"}]},
        }

    def cluster_status(self, live=False):
        return {"nodes": 1}


def _status_turn(state):
    from scripts.research_data_mcp.desk_direct_turns import try_direct_status_turn

    return try_direct_status_turn(_Gateway(), "status", state)


def test_status_reply_carries_phase_jobs_and_promotions():
    turn = _status_turn({"campaign_id": "camp_abc123", "job_ids": []})
    assert turn is not None
    for expected in ("collect", "OpenSea NFT trade history", "opensea_events_daily"):
        assert expected in turn.reply, f"status reply lost {expected!r}"


def test_status_reply_is_more_than_a_truncated_id():
    turn = _status_turn({"campaign_id": "camp_abc123", "job_ids": []})
    assert turn.reply.strip() != "Active campaign: `camp_abc123…`"
    assert len(turn.reply.splitlines()) > 3


def test_status_turn_propagates_state_patch():
    turn = _status_turn({"campaign_id": "camp_abc123", "job_ids": []})
    assert isinstance(turn.action_result.get("state_patch"), dict)


def test_status_turn_survives_a_broken_campaign_lookup():
    from scripts.research_data_mcp.desk_direct_turns import try_direct_status_turn

    class Broken(_Gateway):
        def get_campaign(self, _cid):
            raise RuntimeError("campaign store offline")

    turn = try_direct_status_turn(Broken(), "status", {"campaign_id": "camp_abc123"})
    assert turn is not None
    assert "camp_abc123" in turn.reply


def test_no_campaign_still_answers():
    turn = _status_turn({})
    assert turn is not None and turn.reply.strip()
