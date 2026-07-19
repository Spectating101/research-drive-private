"""Durable synthesis thread state — persistence, patches, Discover handoff."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1] / "drive"


@pytest.fixture()
def store(tmp_path: Path):
    from scripts.research_data_mcp.synthesis_thread_store import SynthesisThreadStore

    return SynthesisThreadStore(tmp_path / "synthesis_threads.sqlite3")


def _seed_state():
    return {
        "title": "Historical stablecoin attention",
        "objective": "Construct a defensible longitudinal attention signal.",
        "required_grain": "asset-week",
        "materialisation": "not_materialised",
        "nodes": [
            {
                "id": "trends",
                "type": "source",
                "layer": "evidence",
                "label": "Google Trends weekly panel",
                "status": "held",
                "role": "Core component",
                "dataset_id": "google_trends_stablecoin_weekly",
                "grain": "asset-week",
            },
            {
                "id": "x_followers",
                "type": "source",
                "layer": "evidence",
                "label": "Historical X follower growth",
                "status": "missing",
                "role": "Ideal measure",
                "candidate_key": "src:x:followers:historical",
                "source_identity": "X / third-party archives",
                "grain": "account-date",
            },
            {
                "id": "gdelt",
                "type": "source",
                "layer": "evidence",
                "label": "GDELT crypto news",
                "status": "proposed",
                "role": "Candidate validation signal",
                "proposalId": "gdelt-validation",
            },
            {
                "id": "attention_proxy",
                "type": "output",
                "layer": "output",
                "label": "attention_proxy_index",
                "status": "derived",
                "materialisation": "not_materialised",
            },
        ],
        "edges": [
            {"id": "attention-gdelt", "source": "attention", "target": "gdelt", "relation": "proposed"},
            {"id": "gdelt-output", "source": "gdelt", "target": "attention_proxy", "relation": "proposed"},
        ],
        "proposal": {
            "id": "gdelt-validation",
            "title": "Use GDELT as a validation signal",
            "nodeId": "gdelt",
            "operations": [
                {
                    "op": "update_node",
                    "id": "gdelt",
                    "patch": {
                        "status": "queryable",
                        "role": "Validation signal",
                        "proposalId": None,
                    },
                },
                {
                    "op": "update_edge",
                    "id": "gdelt-output",
                    "patch": {"relation": "validates", "label": "validates"},
                },
                {"op": "append_activity", "message": "GDELT approved as a validation signal."},
            ],
        },
        "activity": [],
        "spec": {"grain": "asset-week", "validation": []},
    }


def test_create_list_get_persists_and_reloads(store):
    created = store.create(
        objective="Construct a defensible longitudinal attention signal.",
        title="Historical stablecoin attention",
        session_id="sess-abc",
        conversation_id="conv-xyz",
        required_grain="asset-week",
        state=_seed_state(),
    )
    tid = created["id"]
    assert tid
    assert created["session_id"] == "sess-abc"
    assert created["conversation_id"] == "conv-xyz"
    assert created["objective"].startswith("Construct")
    assert created["created_at"]
    assert created["updated_at"]
    assert created["state"]["required_grain"] == "asset-week"
    assert created["materialisation"] == "not_materialised"

    listed = store.list(session_id="sess-abc")
    assert any(row["id"] == tid for row in listed)

    reloaded = store.get(tid)
    assert reloaded["id"] == tid
    assert reloaded["state"]["nodes"][0]["dataset_id"] == "google_trends_stablecoin_weekly"
    assert reloaded["state"]["proposal"]["id"] == "gdelt-validation"


def test_accept_proposal_persists_on_reload(store):
    thread = store.create(
        objective="Construct a defensible longitudinal attention signal.",
        required_grain="asset-week",
        state=_seed_state(),
    )
    tid = thread["id"]
    proposal = store.get(tid)["state"]["proposal"]
    accepted = store.apply_patch_decision(tid, decision="accept", proposal_id=proposal["id"], proposal_hash=proposal["proposal_hash"])
    gdelt = next(n for n in accepted["state"]["nodes"] if n["id"] == "gdelt")
    assert gdelt["status"] == "queryable"
    assert gdelt["role"] == "Validation signal"
    assert accepted["state"]["proposal"] is None
    edge = next(e for e in accepted["state"]["edges"] if e["id"] == "gdelt-output")
    assert edge["relation"] == "validates"

    reloaded = store.get(tid)
    gdelt2 = next(n for n in reloaded["state"]["nodes"] if n["id"] == "gdelt")
    assert gdelt2["status"] == "queryable"
    assert reloaded["state"]["proposal"] is None
    log = store.patch_log(tid)
    assert log and log[0]["decision"] == "accepted"


def test_reject_proposal_removes_candidate(store):
    thread = store.create(
        objective="Construct a defensible longitudinal attention signal.",
        state=_seed_state(),
    )
    proposal = store.get(thread["id"])["state"]["proposal"]
    rejected = store.apply_patch_decision(thread["id"], decision="reject", proposal_id=proposal["id"], proposal_hash=proposal["proposal_hash"])
    assert all(n["id"] != "gdelt" for n in rejected["state"]["nodes"])
    assert all(
        e.get("source") != "gdelt" and e.get("target") != "gdelt"
        for e in rejected["state"]["edges"]
    )
    assert rejected["state"]["proposal"] is None
    reloaded = store.get(thread["id"])
    assert all(n["id"] != "gdelt" for n in reloaded["state"]["nodes"])


def test_dishonest_materialisation_rejected(store):
    thread = store.create(
        objective="Construct a proxy without claiming output.",
        state=_seed_state(),
    )
    with pytest.raises(ValueError, match="Dishonest materialisation"):
        store.apply_patch_decision(
            thread["id"],
            decision="apply",
            operations=[
                {
                    "op": "update_node",
                    "id": "attention_proxy",
                    "patch": {"materialisation": "registered"},
                }
            ],
        )
    view = store.materialisation(thread["id"])
    assert view["materialisation"] == "not_materialised"
    assert view["executed"] is False
    assert view["output_registered"] is False


def test_composer_proposal_is_validated_and_never_auto_applied(store):
    thread = store.create(
        objective="Construct a defensible longitudinal attention signal.",
        state=_seed_state(),
    )
    proposal = {
        "id": "composer-add-limitations",
        "title": "Record the historical coverage limitation",
        "summary": "Keep the proxy provisional until the missing X history is independently resolved.",
        "operations": [
            {
                "op": "update_spec",
                "patch": {"limitations": ["Historical X follower growth is unavailable."]},
            },
            {"op": "append_activity", "message": "Composer proposed a limitation note."},
        ],
    }
    proposed = store.set_proposal(thread["id"], proposal)
    assert proposed["state"]["proposal"]["id"] == "composer-add-limitations"
    # A proposal is visible, but its operations have not touched durable state.
    assert proposed["state"]["spec"].get("limitations") is None
    assert store.patch_log(thread["id"])[0]["decision"] == "proposed"

    with pytest.raises(ValueError, match="Dishonest materialisation"):
        store.set_proposal(
            thread["id"],
            {
                "id": "fake-output",
                "title": "Pretend the asset exists",
                "summary": "This must fail.",
                "operations": [
                    {
                        "op": "update_node",
                        "id": "attention_proxy",
                        "patch": {"materialisation": "registered"},
                    }
                ],
            },
        )


def test_acceptance_rejects_inline_and_stale_proposals(store):
    thread = store.create(objective="Review an evidence proposal.", state=_seed_state())
    with pytest.raises(ValueError, match="proposal_id and proposal_hash"):
        store.apply_patch_decision(thread["id"], decision="accept")
    stale = store.get(thread["id"])["state"]["proposal"]
    store.set_proposal(
        thread["id"],
        {
            "id": "replacement",
            "title": "Replacement proposal",
            "summary": "A newer proposal supersedes the opened review.",
            "operations": [{"op": "append_activity", "message": "Replacement proposed."}],
        },
    )
    with pytest.raises(ValueError, match="changed"):
        store.apply_patch_decision(
            thread["id"],
            decision="accept",
            proposal_id=stale["id"],
            proposal_hash=stale["proposal_hash"],
        )


def test_accepted_proposal_persists_validated_execution_spec(store):
    thread = store.create(objective="Aggregate a held panel.", state=_seed_state())
    proposal = {
        "id": "bounded-aggregate",
        "title": "Aggregate the held panel",
        "summary": "Create one daily count output from a registered local source.",
        "operations": [{"op": "append_activity", "message": "Aggregate proposed."}],
        "execution_spec": {
            "input_dataset_id": "stablecoin_trust_engagement_weekly",
            "output_dataset_id": "synthesis_stablecoin_trust_weekly_counts",
            "group_by": ["week"],
            "metrics": [{"function": "count", "as": "row_count"}],
        },
    }
    store.set_proposal(thread["id"], proposal)
    pending = store.get(thread["id"])
    assert "execution_spec" not in pending["state"]
    proposal = store.get(thread["id"])["state"]["proposal"]
    accepted = store.apply_patch_decision(thread["id"], decision="accept", proposal_id=proposal["id"], proposal_hash=proposal["proposal_hash"])
    assert accepted["state"]["execution_spec"]["output_dataset_id"] == "synthesis_stablecoin_trust_weekly_counts"


def test_worker_evidence_can_mark_registered_output(store):
    thread = store.create(objective="Aggregate a held panel.", state=_seed_state())
    recorded = store.record_execution(
        thread["id"],
        {
            "id": "job-synthesis-1",
            "result": {
                "rows": 12,
                    "materialized": {"dataset_id": "synthesis_weekly_asset_score"},
                    "registry_promotion": [{"dataset_id": "synthesis_weekly_asset_score"}],
                "drive_finalize": {"ok": True},
            },
        },
        verified=True,
    )
    assert recorded["state"]["execution"]["status"] == "registered"
    view = store.materialisation(thread["id"])
    assert view["materialisation"] == "registered"
    assert view["output_registered"] is True
    assert view["job_id"] == "job-synthesis-1"


def test_failed_execution_is_visible_on_the_thread(store):
    thread = store.create(objective="Aggregate a held panel.", state=_seed_state())
    state = thread["state"]
    state["execution"] = {"status": "running", "job_id": "job-fail", "output_dataset_id": "synthesis_failed_asset"}
    store._save_state(thread["id"], state)
    failed = store.record_execution_failure(thread["id"], "job-fail", "Drive verification failed")
    assert failed["state"]["execution"]["status"] == "failed"
    assert "Drive verification failed" in failed["state"]["execution"]["error"]


def test_synthesis_approval_boundaries(stack):
    """Desk can approve synthesis; agents and approve-safe cannot."""
    job = stack.orchestrator.store.create(
        "Synthesis approval boundary",
        {},
        {"job_type": "synthesis_execute", "launchable": True, "title": "Synthesis boundary"},
        status="pending_approval",
    )
    with pytest.raises(PermissionError, match="researcher confirmation"):
        stack.tools.yzu_approve_job(job["id"])
    safe = stack.gateway.approve_safe_pending_jobs(limit=50)
    assert job["id"] not in (safe.get("approved") or [])
    approved = stack.gateway.approve_yzu_job(job["id"])
    assert isinstance(approved, dict)
    got = stack.gateway.jobs.get(job["id"])
    assert got.get("status") in {"queued", "running", "completed"}


def test_discover_handoff_preserves_identities_only(store):
    thread = store.create(
        objective="Construct a defensible longitudinal attention signal.",
        required_grain="asset-week",
        state=_seed_state(),
    )
    handoff = store.discover_handoff(thread["id"])
    assert handoff["thread_id"] == thread["id"]
    assert handoff["objective"].startswith("Construct")
    assert handoff["required_grain"] == "asset-week"
    assert handoff["collection"] is None
    assert handoff["fake_collection"] is False
    assert isinstance(handoff.get("collect_intents"), list)
    assert len(handoff["collect_intents"]) == 1
    intent = handoff["collect_intents"][0]
    assert intent["evidence_id"] == "x_followers"
    assert intent["candidate_key"] == "src:x:followers:historical"
    assert intent["resolvable_hint"] is True
    assert intent["status"] == "intent_only"

    held_ids = {row["id"] for row in handoff["held_evidence"]}
    missing_ids = {row["id"] for row in handoff["missing_evidence"]}
    assert held_ids == {"trends"}
    assert missing_ids == {"x_followers"}
    held = handoff["held_evidence"][0]
    assert held["dataset_id"] == "google_trends_stablecoin_weekly"
    missing = handoff["missing_evidence"][0]
    assert missing["candidate_key"] == "src:x:followers:historical"
    assert missing["source_identity"] == "X / third-party archives"
    # proposed / output nodes are not inventively collected
    assert "gdelt" not in held_ids | missing_ids
    assert "job_id" not in handoff
    assert "plan" not in handoff


@pytest.fixture(scope="module")
def stack():
    from scripts.research_data_mcp.bootstrap import create_stack

    return create_stack(repo_root=REPO)


def test_http_thread_routes_roundtrip(stack, tmp_path: Path, monkeypatch):
    from scripts.research_data_mcp.http_router import handle_get, handle_post
    from scripts.research_data_mcp.synthesis_thread_store import SynthesisThreadStore

    isolated = SynthesisThreadStore(tmp_path / "http_threads.sqlite3")
    monkeypatch.setattr(stack.gateway, "_synthesis_threads_store", isolated, raising=False)

    created = handle_post(
        "/library/synthesis/threads",
        {
            "objective": "Construct a defensible longitudinal attention signal.",
            "title": "Attention proxy",
            "session_id": "chat-1",
            "required_grain": "asset-week",
            "state": _seed_state(),
        },
        stack,
    )
    assert created["status"] == 200
    tid = created["body"]["id"]

    listed = handle_get("/library/synthesis/threads", {"session_id": "chat-1"}, stack)
    assert listed["status"] == 200
    assert any(t["id"] == tid for t in listed["body"]["threads"])

    got = handle_get(f"/library/synthesis/threads/{tid}", {}, stack)
    assert got["status"] == 200
    assert got["body"]["state"]["proposal"]["id"] == "gdelt-validation"

    proposal = got["body"]["state"]["proposal"]
    accepted = handle_post(
        f"/library/synthesis/threads/{tid}/patches",
        {"decision": "accept", "proposal_id": proposal["id"], "proposal_hash": proposal["proposal_hash"]},
        stack,
    )
    assert accepted["status"] == 200
    assert accepted["body"]["state"]["proposal"] is None

    handoff = handle_get(f"/library/synthesis/threads/{tid}/discover-handoff", {}, stack)
    assert handoff["status"] == 200
    assert handoff["body"]["required_grain"] == "asset-week"
    assert {r["id"] for r in handoff["body"]["held_evidence"]} == {"trends", "gdelt"}
    assert handoff["body"]["collection"] is None

    mat = handle_get(f"/library/synthesis/threads/{tid}/materialisation", {}, stack)
    assert mat["status"] == 200
    assert mat["body"]["materialisation"] == "not_materialised"
    assert mat["body"]["executed"] is False

    # threads must not be swallowed by /library/synthesis/{id}
    profiles = handle_get("/library/synthesis/profiles", {}, stack)
    assert profiles["status"] == 200
    assert "profiles" in profiles["body"]

def test_link_conversation_persists_session_and_optional_conversation(store):
    created = store.create(
        objective="Construct a defensible longitudinal attention signal.",
        title="Historical stablecoin attention",
        state=_seed_state(),
    )
    tid = created["id"]
    assert created["session_id"] == ""
    assert created["conversation_id"] == ""
    before = created["updated_at"]

    linked = store.link_conversation(tid, session_id="sess-link-1")
    assert linked["session_id"] == "sess-link-1"
    assert linked["conversation_id"] == ""
    assert linked["updated_at"] >= before

    linked2 = store.link_conversation(
        tid,
        session_id="sess-link-2",
        conversation_id="conv-link-9",
    )
    assert linked2["session_id"] == "sess-link-2"
    assert linked2["conversation_id"] == "conv-link-9"
    reloaded = store.get(tid)
    assert reloaded["session_id"] == "sess-link-2"
    assert reloaded["conversation_id"] == "conv-link-9"


def test_link_conversation_rejects_empty_ids(store):
    created = store.create(
        objective="Construct a defensible longitudinal attention signal.",
        title="Historical stablecoin attention",
        state=_seed_state(),
    )
    tid = created["id"]
    with pytest.raises(ValueError, match="session_id"):
        store.link_conversation(tid, session_id="  ")
    with pytest.raises(ValueError, match="conversation_id"):
        store.link_conversation(tid, session_id="sess-ok", conversation_id="   ")
    with pytest.raises(KeyError):
        store.link_conversation("missing-thread", session_id="sess-ok")


def test_http_link_conversation_route(stack, tmp_path: Path, monkeypatch):
    from scripts.research_data_mcp.http_router import handle_post, handle_get
    from scripts.research_data_mcp.synthesis_thread_store import SynthesisThreadStore

    isolated = SynthesisThreadStore(tmp_path / "http_link_threads.sqlite3")
    monkeypatch.setattr(stack.gateway, "_synthesis_threads_store", isolated, raising=False)

    created = handle_post(
        "/library/synthesis/threads",
        {
            "objective": "Construct a defensible longitudinal attention signal.",
            "title": "Attention proxy",
            "state": _seed_state(),
        },
        stack,
    )
    assert created["status"] == 200
    tid = created["body"]["id"]

    before_bad = handle_get(f"/library/synthesis/threads/{tid}", {}, stack)
    assert before_bad["status"] == 200

    bad = handle_post(
        f"/library/synthesis/threads/{tid}/conversation",
        {"session_id": ""},
        stack,
    )
    assert bad["status"] == 400
    assert "session_id" in str(bad["body"].get("message") or "")

    after_bad = handle_get(f"/library/synthesis/threads/{tid}", {}, stack)
    assert after_bad["status"] == 200
    assert after_bad["body"]["session_id"] == before_bad["body"]["session_id"]
    assert after_bad["body"]["conversation_id"] == before_bad["body"]["conversation_id"]

    linked = handle_post(
        f"/library/synthesis/threads/{tid}/conversation",
        {"session_id": "chat-continuity-1", "conversation_id": "conv-continuity-1"},
        stack,
    )
    assert linked["status"] == 200
    assert linked["body"]["session_id"] == "chat-continuity-1"
    assert linked["body"]["conversation_id"] == "conv-continuity-1"
    assert linked["body"]["updated_at"]

    got = handle_get(f"/library/synthesis/threads/{tid}", {}, stack)
    assert got["status"] == 200
    assert got["body"]["session_id"] == "chat-continuity-1"
    assert got["body"]["conversation_id"] == "conv-continuity-1"
