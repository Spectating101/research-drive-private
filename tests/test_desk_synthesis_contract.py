"""Synthesis Ask must reason about constructs, not degrade into catalogue copy."""

from __future__ import annotations

import json
import sys
import types


def _state(**rail):
    return {"rail_context": rail}


def test_context_detection_is_scoped_to_synthesis():
    from scripts.research_data_mcp.desk_synthesis_contract import is_synthesis_context

    assert is_synthesis_context(_state(tab="synthesis", mode="detail"))
    assert is_synthesis_context(
        _state(tab="home", mode="detail", entity={"kind": "synthesis_thread"})
    )
    assert not is_synthesis_context(_state(tab="browse", mode="explore"))
    assert not is_synthesis_context({})


def test_first_turn_contract_requires_interpretation_evidence_and_one_question():
    from scripts.research_data_mcp.desk_synthesis_contract import wrap_synthesis_request

    prompt = wrap_synthesis_request(
        "Construct a firm-week coordination proxy.",
        first_user_turn=True,
    )
    assert "provisional interpretation" in prompt
    assert "strongest relevant Library assets" in prompt
    assert "supported facts, proposed proxy choices" in prompt
    assert "exactly one highest-value clarification question" in prompt
    assert "Do not collect, execute, materialise" in prompt
    assert prompt.endswith("Construct a firm-week coordination proxy.")


def test_followup_contract_preserves_context_without_restarting():
    from scripts.research_data_mcp.desk_synthesis_contract import wrap_synthesis_request

    prompt = wrap_synthesis_request(
        "Use a weekly horizon.",
        first_user_turn=False,
    )
    assert "Continue the same Synthesis investigation" in prompt
    assert "first faculty turn" not in prompt
    assert prompt.endswith("Use a weekly horizon.")


def test_synthesis_prompts_are_not_procurement_prompts():
    from scripts.research_data_mcp.desk_brain import _faculty_starter_prompts

    prompts = _faculty_starter_prompts(_state(tab="synthesis", mode="define"))
    blob = " ".join(prompts).lower()
    assert "proxy" in blob
    assert "validation" in blob
    assert "datacite" not in blob
    assert "collect plan" not in blob


def test_synthesis_failure_never_claims_inventory_or_progress():
    from scripts.research_data_mcp.desk_synthesis_contract import synthesis_failure_reply

    reply = synthesis_failure_reply("empty_reply")
    assert "did not return a usable reasoning turn" in reply
    assert "have not inferred a construct" in reply
    assert "vault" not in reply.lower()
    assert "ready now" not in reply.lower()


def test_recorded_proposal_failure_copy_acknowledges_durable_change():
    from scripts.research_data_mcp.desk_synthesis_contract import (
        synthesis_proposal_recorded_reply,
    )

    reply = synthesis_proposal_recorded_reply("Review acceleration method")
    assert "was recorded" in reply
    assert "exact change set" in reply
    assert "Nothing was executed" in reply
    assert "changed the project" not in reply


def test_synthesis_reply_guard_rejects_false_execution_and_question_churn():
    from scripts.research_data_mcp.desk_synthesis_contract import (
        synthesis_reply_violations,
    )

    violations = synthesis_reply_violations(
        (
            "I have collected the final panel. Could this use a week? "
            "Would a month be better?"
        ),
        first_user_turn=True,
    )
    assert "false_execution_claim" in violations
    assert "clarification_question_count" in violations


def test_synthesis_reply_guard_allows_verified_query_ready_input():
    from scripts.research_data_mcp.desk_synthesis_contract import (
        synthesis_reply_violations,
    )

    violations = synthesis_reply_violations(
        (
            "Provisional construction: use the held JKSE panel as the spine. "
            "The JKSE panel is query-ready at instrument-month grain, while the "
            "candidate output would remain unbuilt until explicit approval. "
            "Should the regime use relative ranks?"
        ),
        first_user_turn=True,
    )
    assert "false_execution_claim" not in violations


def test_synthesis_reply_guard_rejects_query_ready_output_claim():
    from scripts.research_data_mcp.desk_synthesis_contract import (
        synthesis_reply_violations,
    )

    violations = synthesis_reply_violations(
        (
            "Provisional construction: use the held JKSE panel as the spine. "
            "The synthesized output is now query-ready. "
            "Should the regime use relative ranks?"
        ),
        first_user_turn=True,
    )
    assert "false_execution_claim" in violations


def test_synthesis_proposal_request_detection_requires_explicit_proposal_language():
    from scripts.research_data_mcp.desk_synthesis_contract import (
        synthesis_request_requires_proposal,
    )

    assert synthesis_request_requires_proposal(
        "Create one reviewable Synthesis proposal and record the proposal for review."
    )
    assert not synthesis_request_requires_proposal(
        "Compare the available proxy definitions before we decide."
    )


def test_synthesis_history_is_bounded_and_provider_neutral():
    from scripts.research_data_mcp.desk_synthesis_contract import (
        record_synthesis_turn,
        synthesis_history_brief,
    )

    state = {}
    for index in range(10):
        record_synthesis_turn(
            state,
            user=f"faculty-{index}",
            assistant=f"answer-{index}",
            provider="test-provider",
            max_turns=8,
        )

    assert len(state["synthesis_turn_history"]) == 8
    brief = synthesis_history_brief(state, max_turns=2)
    assert "faculty-7" not in brief
    assert "faculty-8" in brief
    assert "faculty-9" in brief
    assert "newly verified evidence" in brief


def test_followup_prompt_includes_selected_thread_durable_state():
    from scripts.research_data_mcp.desk_brain import _prepare_synthesis_fallback_prompt

    thread = {
        "id": "thread-weekly",
        "title": "Weekly trust panel",
        "objective": "Construct a weekly trust measure.",
        "state": {
            "required_grain": "asset-week",
            "nodes": [
                {
                    "id": "held-source",
                    "type": "source",
                    "layer": "evidence",
                    "label": "Trust engagement weekly",
                    "dataset_id": "stablecoin_trust_engagement_weekly",
                    "status": "held",
                    "role": "Core input",
                }
            ],
            "execution": {
                "status": "pending_approval",
                "job_id": "job-1",
                "output_dataset_id": "synthesis_weekly_trust_panel",
            },
        },
    }
    gateway = types.SimpleNamespace(synthesis_thread_get=lambda thread_id: thread if thread_id == "thread-weekly" else None)
    state = {
        "synthesis_user_turns": 1,
        "rail_context": {
            "tab": "synthesis",
            "thread_id": "thread-weekly",
            "entity": {"kind": "synthesis_thread", "id": "thread-weekly"},
        },
    }

    prompt, first_turn = _prepare_synthesis_fallback_prompt(
        gateway, "Use a weekly horizon.", state
    )

    assert first_turn is False
    assert "[Durable Synthesis thread — recorded facts]" in prompt
    assert "Trust engagement weekly [stablecoin_trust_engagement_weekly]" in prompt
    assert "Recorded execution: pending_approval" in prompt
    assert "output registered: no" in prompt
    assert "Continue the same Synthesis investigation" in prompt


def _install_empty_cursor(monkeypatch):
    class EmptyRun:
        status = "success"

        def wait(self):
            return None

        def text(self):
            return ""

        def conversation(self):
            return []

    class EmptyAgent:
        agent_id = "agent-empty"

        @classmethod
        def create(cls, _opts):
            return cls()

        @classmethod
        def resume(cls, _agent_id, _opts):
            return cls()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def send(self, _text, _opts):
            return EmptyRun()

    cursor_sdk = types.ModuleType("cursor_sdk")
    cursor_sdk.Agent = EmptyAgent
    cursor_types = types.ModuleType("cursor_sdk.types")
    cursor_types.AgentOptions = lambda **kwargs: kwargs
    cursor_types.ModelSelection = lambda **kwargs: kwargs
    cursor_types.SendOptions = lambda **kwargs: kwargs
    cursor_types.StdioMcpServerConfig = lambda **kwargs: kwargs
    cursor_types.LocalAgentOptions = lambda **kwargs: kwargs
    cursor_types.CloudAgentOptions = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "cursor_sdk", cursor_sdk)
    monkeypatch.setitem(sys.modules, "cursor_sdk.types", cursor_types)


def _install_proposal_then_invalid_reply_cursor(monkeypatch):
    proposal = {
        "id": "proposal-1",
        "title": "Review acceleration method",
        "summary": "Review-only proposed construction.",
        "operations": [{"op": "update_spec", "value": {"grain": "month"}}],
    }

    class ProposalRun:
        status = "success"

        def wait(self):
            return None

        def text(self):
            return "I collected the final panel."

        def conversation(self):
            message = types.SimpleNamespace(
                type="tool_call",
                name="research_synthesis_propose_state",
                result=json.dumps(
                    {
                        "thread_id": "thread-a",
                        "synthesis_proposal": proposal,
                    }
                ),
            )
            return [types.SimpleNamespace(steps=[types.SimpleNamespace(message=message)])]

    class ProposalAgent:
        agent_id = "agent-proposal"

        @classmethod
        def create(cls, _opts):
            return cls()

        @classmethod
        def resume(cls, _agent_id, _opts):
            return cls()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def send(self, _text, _opts):
            return ProposalRun()

    cursor_sdk = types.ModuleType("cursor_sdk")
    cursor_sdk.Agent = ProposalAgent
    cursor_types = types.ModuleType("cursor_sdk.types")
    cursor_types.AgentOptions = lambda **kwargs: kwargs
    cursor_types.ModelSelection = lambda **kwargs: kwargs
    cursor_types.SendOptions = lambda **kwargs: kwargs
    cursor_types.StdioMcpServerConfig = lambda **kwargs: kwargs
    cursor_types.LocalAgentOptions = lambda **kwargs: kwargs
    cursor_types.CloudAgentOptions = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "cursor_sdk", cursor_sdk)
    monkeypatch.setitem(sys.modules, "cursor_sdk.types", cursor_types)


def test_contract_failure_reports_proposal_that_tool_already_recorded(monkeypatch, tmp_path):
    from scripts.research_data_mcp import desk_brain, desk_synthesis_fallback

    _install_proposal_then_invalid_reply_cursor(monkeypatch)
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(desk_brain, "_desk_composer_models", lambda: ["test"])
    monkeypatch.setattr(desk_brain, "_mcp_stdio_config", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        desk_brain, "_desk_agent_runtime_kwargs", lambda _root, **_kwargs: {}
    )
    monkeypatch.setattr(
        desk_synthesis_fallback,
        "run_gemini_synthesis_turn",
        lambda _prompt: (_ for _ in ()).throw(
            AssertionError("a recorded proposal must not be hidden by fallback prose")
        ),
    )

    state = {
        "desk_primed": True,
        "rail_context": {
            "tab": "synthesis",
            "mode": "define",
            "thread_id": "thread-a",
            "entity": {"kind": "synthesis_thread", "id": "thread-a"},
        },
    }
    turn = desk_brain.run_cursor_composer_turn(
        types.SimpleNamespace(repo_root=tmp_path),
        "Persist the review proposal.",
        state,
    )

    assert turn.action_result["action"] == "synthesis_proposal_recorded_response_error"
    assert turn.action_result["proposal_recorded"] is True
    assert turn.action_result["synthesis_thread_id"] == "thread-a"
    assert turn.action_result["synthesis_proposal"]["id"] == "proposal-1"
    assert "was recorded" in turn.reply
    assert "Nothing was executed" in turn.reply


def test_synthesis_timeout_continues_through_grounded_fallback(monkeypatch, tmp_path):
    from scripts.research_data_mcp import desk_brain, desk_synthesis_fallback

    _install_empty_cursor(monkeypatch)
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(desk_brain, "_desk_composer_models", lambda: ["test"])
    monkeypatch.setattr(desk_brain, "_mcp_stdio_config", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(desk_brain, "_desk_agent_runtime_kwargs", lambda _root, **_kwargs: {})
    monkeypatch.setattr(
        desk_brain,
        "_wait_run_bounded",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()),
    )
    monkeypatch.setattr(
        desk_synthesis_fallback,
        "run_gemini_synthesis_turn",
        lambda _prompt: (
            "A provisional monthly proxy could combine the verified Library inputs while keeping the missing construct explicit. Which validation horizon matters most?",
            {"provider": "gemini-test"},
        ),
    )
    state = {
        "desk_primed": True,
        "rail_context": {"tab": "synthesis", "mode": "define"},
    }
    turn = desk_brain.run_cursor_composer_turn(
        types.SimpleNamespace(repo_root=tmp_path), "Build a monthly proxy", state
    )
    assert turn.action_result["brain"] == "gemini_synthesis"
    assert turn.action_result["fallback_from"] == "cursor_composer_timeout"
    assert "provisional monthly proxy" in turn.reply
    assert state["synthesis_turn_history"][-1]["provider"] == "gemini"


def test_synthesis_timeout_reports_proposal_already_recorded(monkeypatch, tmp_path):
    from scripts.research_data_mcp import desk_brain, desk_synthesis_fallback

    _install_proposal_then_invalid_reply_cursor(monkeypatch)
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(desk_brain, "_desk_composer_models", lambda: ["test"])
    monkeypatch.setattr(desk_brain, "_mcp_stdio_config", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(desk_brain, "_desk_agent_runtime_kwargs", lambda _root, **_kwargs: {})
    monkeypatch.setattr(
        desk_brain,
        "_wait_run_bounded",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()),
    )
    monkeypatch.setattr(
        desk_synthesis_fallback,
        "run_gemini_synthesis_turn",
        lambda _prompt: (_ for _ in ()).throw(
            AssertionError("recorded proposal must not be replaced")
        ),
    )
    state = {
        "desk_primed": True,
        "rail_context": {"tab": "synthesis", "mode": "define", "thread_id": "thread-a"},
    }
    turn = desk_brain.run_cursor_composer_turn(
        types.SimpleNamespace(repo_root=tmp_path), "Persist the review proposal", state
    )
    assert turn.action_result["reason"] == "composer_timeout"
    assert turn.action_result["proposal_recorded"] is True
    assert turn.action_result["synthesis_proposal"]["id"] == "proposal-1"
    assert "was recorded" in turn.reply


def test_synthesis_timeout_reports_both_provider_failures_without_state_churn(monkeypatch, tmp_path):
    from scripts.research_data_mcp import desk_brain, desk_synthesis_fallback

    _install_empty_cursor(monkeypatch)
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(desk_brain, "_desk_composer_models", lambda: ["test"])
    monkeypatch.setattr(desk_brain, "_mcp_stdio_config", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(desk_brain, "_desk_agent_runtime_kwargs", lambda _root, **_kwargs: {})
    monkeypatch.setattr(
        desk_brain,
        "_wait_run_bounded",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()),
    )
    monkeypatch.setattr(
        desk_synthesis_fallback,
        "run_gemini_synthesis_turn",
        lambda _prompt: (_ for _ in ()).throw(
            desk_synthesis_fallback.SynthesisFallbackError("provider_timeout")
        ),
    )
    state = {
        "desk_primed": True,
        "rail_context": {"tab": "synthesis", "mode": "define"},
    }
    turn = desk_brain.run_cursor_composer_turn(
        types.SimpleNamespace(repo_root=tmp_path), "Build a monthly proxy", state
    )
    assert turn.action_result["action"] == "composer_timeout"
    assert turn.action_result["fallback"] == "gemini_failed"
    assert turn.action_result["fallback_error_category"] == "provider_timeout"
    assert state.get("synthesis_turn_history") is None
    assert "No collection or approval was started" in turn.reply


def test_empty_synthesis_turn_never_uses_inventory_fallback(monkeypatch, tmp_path):
    from scripts.research_data_mcp import (
        desk_brain,
        desk_catalog_fallback,
        desk_synthesis_fallback,
    )

    _install_empty_cursor(monkeypatch)
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(desk_brain, "_desk_composer_models", lambda: ["test"])
    monkeypatch.setattr(desk_brain, "_mcp_stdio_config", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        desk_brain, "_desk_agent_runtime_kwargs", lambda _root, **_kwargs: {}
    )
    monkeypatch.setattr(
        desk_synthesis_fallback,
        "run_gemini_synthesis_turn",
        lambda _prompt: (_ for _ in ()).throw(
            desk_synthesis_fallback.SynthesisFallbackError("not_configured")
        ),
    )
    monkeypatch.setattr(
        desk_catalog_fallback,
        "try_inventory_fallback",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("inventory fallback must not run in Synthesis")
        ),
    )

    gateway = types.SimpleNamespace(repo_root=tmp_path)
    state = {
        "desk_primed": True,
        "vault_brief": "Ready now:\n- Generic dataset",
        "rail_context": {"tab": "synthesis", "mode": "define"},
    }
    turn = desk_brain.run_cursor_composer_turn(gateway, "Build a proxy", state)

    assert turn.action_result["action"] == "composer_error"
    assert turn.action_result["fallback"] == "gemini_failed"
    assert turn.action_result["fallback_error_category"] == "not_configured"
    assert turn.action_result["mode"] == "synthesis"
    assert "did not return a usable reasoning turn" in turn.reply
    assert state.get("synthesis_user_turns") is None


def test_empty_discover_turn_keeps_existing_inventory_fallback(monkeypatch, tmp_path):
    from scripts.research_data_mcp import desk_brain, desk_catalog_fallback

    _install_empty_cursor(monkeypatch)
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(desk_brain, "_desk_composer_models", lambda: ["test"])
    monkeypatch.setattr(desk_brain, "_mcp_stdio_config", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        desk_brain, "_desk_agent_runtime_kwargs", lambda _root, **_kwargs: {}
    )
    monkeypatch.setattr(
        desk_catalog_fallback,
        "try_inventory_fallback",
        lambda *_args, **_kwargs: "Known Library holdings.",
    )

    gateway = types.SimpleNamespace(repo_root=tmp_path)
    state = {
        "desk_primed": True,
        "vault_brief": "Ready now:\n- Generic dataset",
        "rail_context": {"tab": "browse", "mode": "explore"},
    }
    turn = desk_brain.run_cursor_composer_turn(gateway, "What do we have?", state)

    assert turn.action_result["action"] == "composer"
    assert turn.action_result["fallback"] == "vault_inventory"
    assert turn.reply == "Known Library holdings."


def test_chat_persists_rail_context_before_background_warm(monkeypatch, tmp_path):
    from scripts.research_data_mcp import desk_brain, desk_warm
    from scripts.research_data_mcp.procurement_chat import ProcurementChatOrchestrator

    gateway = types.SimpleNamespace(repo_root=tmp_path)
    orchestrator = ProcurementChatOrchestrator(tmp_path)
    observed = {}

    monkeypatch.setattr(desk_brain, "cursor_composer_available", lambda: True)
    monkeypatch.setattr(desk_brain, "desk_brain_mode", lambda _root: "cursor_composer")
    monkeypatch.setattr(
        "scripts.research_data_mcp.desk_vault_brief.build_vault_brief",
        lambda *_args, **_kwargs: "brief",
    )

    def fake_warm(_gateway, *, session_id, **_kwargs):
        observed.update(orchestrator.sessions.get(session_id).get("state") or {})
        return {"session_id": session_id, "primed": False, "priming": False}

    monkeypatch.setattr(desk_warm, "warm_desk_session", fake_warm)
    monkeypatch.setattr(
        orchestrator,
        "_wait_for_prime_events",
        lambda *_args, **_kwargs: iter([{"type": "progress", "phase": "priming"}]),
    )

    events = orchestrator.chat_events(
        gateway,
        "Define a proxy",
        rail_context={"tab": "synthesis", "mode": "define"},
    )
    next(events)

    assert observed["rail_context"]["tab"] == "synthesis"


def test_first_synthesis_turn_retries_fresh_model_after_resume_error(monkeypatch, tmp_path):
    from scripts.research_data_mcp import desk_brain

    class SuccessfulRun:
        status = "success"

        def wait(self):
            return None

        def text(self):
            return "A provisional construct with one clarification question?"

        def conversation(self):
            return []

    class RecoveringAgent:
        agent_id = "agent-backup"

        @classmethod
        def resume(cls, _agent_id, _opts):
            raise RuntimeError("primary resume failed")

        @classmethod
        def create(cls, _opts):
            return cls()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def send(self, _text, _opts):
            return SuccessfulRun()

    cursor_sdk = types.ModuleType("cursor_sdk")
    cursor_sdk.Agent = RecoveringAgent
    cursor_types = types.ModuleType("cursor_sdk.types")
    cursor_types.AgentOptions = lambda **kwargs: kwargs
    cursor_types.ModelSelection = lambda **kwargs: kwargs
    cursor_types.SendOptions = lambda **kwargs: kwargs
    cursor_types.StdioMcpServerConfig = lambda **kwargs: kwargs
    cursor_types.LocalAgentOptions = lambda **kwargs: kwargs
    cursor_types.CloudAgentOptions = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "cursor_sdk", cursor_sdk)
    monkeypatch.setitem(sys.modules, "cursor_sdk.types", cursor_types)
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(desk_brain, "_desk_composer_models", lambda: ["primary", "backup"])
    monkeypatch.setattr(desk_brain, "_mcp_stdio_config", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        desk_brain, "_desk_agent_runtime_kwargs", lambda _root, **_kwargs: {}
    )

    gateway = types.SimpleNamespace(repo_root=tmp_path)
    state = {
        "desk_primed": True,
        "cursor_agent_id": "agent-primary",
        "rail_context": {"tab": "synthesis", "mode": "define"},
    }
    turn = desk_brain.run_cursor_composer_turn(gateway, "Define a construct", state)

    assert turn.reply.startswith("A provisional construct")
    assert turn.action_result["composer_model"] == "backup"
    assert turn.action_result["cursor_agent_id"] == "agent-backup"
    assert state["synthesis_user_turns"] == 1


def test_synthesis_phase_is_tracked_per_thread():
    from scripts.research_data_mcp.desk_synthesis_contract import (
        record_synthesis_turn,
        synthesis_first_turn,
    )

    state = _state(
        tab="synthesis",
        mode="define",
        thread_id="thread-a",
        entity={"kind": "synthesis_thread", "id": "thread-a"},
    )
    assert synthesis_first_turn(state)
    record_synthesis_turn(state)
    assert not synthesis_first_turn(state)

    state["rail_context"]["thread_id"] = "thread-b"
    state["rail_context"]["entity"]["id"] = "thread-b"
    assert synthesis_first_turn(state)


def test_first_synthesis_turn_blocks_direct_collection(monkeypatch, tmp_path):
    from scripts.research_data_mcp import desk_brain

    called = {"collect": 0, "composer": 0}

    class Gateway:
        repo_root = tmp_path

        def collect_datacite_doi(self, *_args, **_kwargs):
            called["collect"] += 1
            raise AssertionError("first-turn Synthesis must not collect")

    def fake_composer(*_args, **_kwargs):
        called["composer"] += 1
        return desk_brain.AgentTurn(
            plan={"action": "composer"},
            action_result={"action": "composer"},
            reply="I would propose a provisional proxy. Which horizon matters most?",
        )

    monkeypatch.setattr(desk_brain, "run_cursor_composer_turn", fake_composer)
    state = _state(
        tab="synthesis",
        mode="define",
        thread_id="thread-a",
        entity={"kind": "synthesis_thread", "id": "thread-a"},
    )
    turn = desk_brain.run_desk_agent_turn(
        None,
        Gateway(),
        "Collect DOI 10.5281/zenodo.12345",
        state,
    )

    assert turn.action_result["action"] == "composer"
    assert called == {"collect": 0, "composer": 1}


def test_synthesis_mcp_registration_is_read_only(monkeypatch):
    from scripts.research_data_mcp.mcp_register import registered_tool_names

    monkeypatch.setenv("RESEARCH_MCP_SYNTHESIS_READ_ONLY", "1")
    names = set(registered_tool_names())
    assert "research_query_dataset" in names
    assert "research_synthesis_pair" in names
    assert "research_synthesis_propose_state" in names
    assert "bigquery_dry_run" in names
    assert "research_synthesis_run" not in names
    assert "datacite_collect_doi" not in names
    assert "yzu_submit_job" not in names
    assert "procurement_approve_job" not in names
