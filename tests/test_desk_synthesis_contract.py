"""Synthesis Ask must reason about constructs, not degrade into catalogue copy."""

from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock


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


def test_followup_thread_state_brief_is_observed_and_bounded():
    from scripts.research_data_mcp.desk_synthesis_contract import (
        build_synthesis_thread_state_brief,
    )

    class Gateway:
        def synthesis_thread_get(self, thread_id):
            assert thread_id == "thread-42"
            return {
                "id": thread_id,
                "title": "Trust and engagement panel",
                "objective": "Construct issuer-week trust proxy",
                "materialisation": "planned",
                "state": {
                    "maturity": "exploring",
                    "nodes": [{"id": "n1", "role": "trust input", "status": "observed"}],
                    "proposal": {"id": "p1", "title": "Use security + news proxy"},
                    "accepted_spec_hash": "none",
                    "execution": {"status": "pending_approval", "job_id": "job-1"},
                },
            }

    brief = build_synthesis_thread_state_brief(
        Gateway(),
        {"rail_context": {"tab": "synthesis", "thread_id": "thread-42"}},
    )
    assert "authoritative for this turn" in brief
    assert "objective: Construct issuer-week trust proxy" in brief
    assert "pending_proposal: Use security + news proxy" in brief
    assert "execution: status=pending_approval" in brief
    assert "proposal is not acceptance" in brief


def test_synthesis_envelope_is_typed_and_prose_is_not_parsed():
    from scripts.research_data_mcp.desk_synthesis_contract import (
        parse_synthesis_envelope,
        synthesis_reply_violations,
    )

    plain = "The output is query-ready, but that sentence is only prose."
    parsed_plain = parse_synthesis_envelope(plain)
    assert parsed_plain["structured"] is False
    assert synthesis_reply_violations(plain, first_user_turn=False) == []

    envelope = parse_synthesis_envelope(
        json.dumps(
            {
                "reply": "The output is query-ready.",
                "clarification": "Which validation horizon should we use?",
                "claims": [
                    {
                        "kind": "lifecycle",
                        "status": "query_ready",
                        "evidence_tool": "research_synthesis_materialisation",
                    }
                ],
            }
        )
    )
    assert envelope["structured"] is True
    assert "lifecycle_artifact_missing" in synthesis_reply_violations(
        envelope["reply"],
        first_user_turn=False,
        envelope=envelope,
        artifacts={},
    )


def test_synthesis_envelope_accepts_tool_backed_claims_only():
    from scripts.research_data_mcp.desk_synthesis_contract import (
        parse_synthesis_envelope,
        synthesis_reply_violations,
    )

    envelope = parse_synthesis_envelope(
        json.dumps(
            {
                "reply": "The output is query-ready.",
                "clarification": "",
                "claims": [
                    {
                        "kind": "lifecycle",
                        "status": "query_ready",
                        "evidence_tool": "research_synthesis_materialisation",
                    }
                ],
            }
        )
    )
    artifacts = {
        "synthesis_verifications": [
            {
                "tool": "research_synthesis_materialisation",
                "materialisation": "registered",
                "output_registered": True,
                "query_ready": True,
            }
        ]
    }
    assert synthesis_reply_violations(
        envelope["reply"],
        first_user_turn=False,
        envelope=envelope,
        artifacts=artifacts,
    ) == []


def test_construction_envelope_requires_proposal_artifact():
    from scripts.research_data_mcp.desk_synthesis_contract import (
        parse_synthesis_envelope,
        synthesis_reply_violations,
    )

    envelope = parse_synthesis_envelope(
        json.dumps(
            {
                "reply": "I propose adding the proxy node.",
                "clarification": "",
                "claims": [
                    {
                        "kind": "construction",
                        "status": "proposed",
                        "proposal_id": "p1",
                    }
                ],
                "construction": {"status": "proposed", "proposal_id": "p1"},
            }
        )
    )
    assert "construction_proposal_missing" in synthesis_reply_violations(
        envelope["reply"], first_user_turn=False, envelope=envelope, artifacts={}
    )
    assert synthesis_reply_violations(
        envelope["reply"],
        first_user_turn=False,
        envelope=envelope,
        artifacts={"synthesis_proposal": {"id": "p1"}},
    ) == []


def test_synthesis_envelope_repair_turn_is_tool_enabled():
    from scripts.research_data_mcp.desk_synthesis_contract import (
        synthesis_envelope_repair_request,
    )

    prompt = synthesis_envelope_repair_request(
        original_request="Verify the output",
        previous_reply="The output is query-ready.",
        violations=["lifecycle_artifact_missing"],
    )
    assert "tools are allowed" in prompt
    assert "researcher and the thread store" in prompt
    assert "exactly one JSON envelope" in prompt


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


def test_plain_prose_remains_a_draft_without_state_side_effects():
    from scripts.research_data_mcp.desk_synthesis_contract import synthesis_reply_violations

    assert synthesis_reply_violations(
        "I have collected the final panel. Could grain be week?", first_user_turn=True
    ) == []


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


def test_followup_composer_prompt_includes_authoritative_thread_state(monkeypatch, tmp_path):
    from scripts.research_data_mcp import desk_brain

    class Run:
        status = "success"

        def wait(self):
            return None

        def text(self):
            return "The construct remains provisional; the next question is which proxy to test."

        def conversation(self):
            return []

    class Agent:
        agent_id = "agent-followup"
        prompts = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def send(self, text, _opts):
            Agent.prompts.append(text)
            return Run()

    agent_api = types.SimpleNamespace(create=lambda _opts: Agent(), resume=lambda _id, _opts: Agent())
    bindings = desk_brain._CursorSdkBindings(
        agent=agent_api,
        agent_options=lambda **kwargs: kwargs,
        model_selection=lambda **kwargs: kwargs,
        send_options=lambda **kwargs: kwargs,
        stdio_mcp_server_config=lambda **kwargs: kwargs,
        local_agent_options=lambda **kwargs: kwargs,
        cloud_agent_options=lambda **kwargs: kwargs,
    )
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(desk_brain, "_load_cursor_sdk_bindings", lambda: bindings)
    monkeypatch.setattr(desk_brain, "_desk_composer_models", lambda: ["test"])
    monkeypatch.setattr(desk_brain, "_mcp_stdio_config", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(desk_brain, "_desk_agent_runtime_kwargs", lambda *_args, **_kwargs: {})

    class Gateway:
        repo_root = tmp_path

        def synthesis_thread_get(self, thread_id):
            return {
                "id": thread_id,
                "objective": "Issuer-week trust proxy",
                "materialisation": "not_materialised",
                "state": {
                    "nodes": [{"role": "trust input"}],
                    "proposal": None,
                    "accepted_spec_hash": "none",
                    "execution": {},
                },
            }

    state = {
        "desk_primed": True,
        "synthesis_user_turns": 1,
        "rail_context": {"tab": "synthesis", "mode": "define", "thread_id": "thread-42"},
    }
    turn = desk_brain.run_cursor_composer_turn(Gateway(), "Review the current construct", state)
    joined_prompts = "\n".join(Agent.prompts)
    assert "Observed Synthesis thread state" in joined_prompts
    assert "Issuer-week trust proxy" in joined_prompts
    assert "not_materialised" in joined_prompts
    assert turn.action_result["action"] == "composer"


def test_unstructured_lifecycle_prose_is_not_parsed_or_blocked(monkeypatch, tmp_path):
    from scripts.research_data_mcp import desk_brain

    class Run:
        status = "success"

        def wait(self):
            return None

        def text(self):
            return "The output is query-ready and registered."

        def conversation(self):
            return []

    class Agent:
        agent_id = "agent-claim"

        calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def send(self, _text, _opts):
            Agent.calls += 1
            return Run()

    agent_api = types.SimpleNamespace(create=lambda _opts: Agent(), resume=lambda _id, _opts: Agent())
    bindings = desk_brain._CursorSdkBindings(
        agent=agent_api,
        agent_options=lambda **kwargs: kwargs,
        model_selection=lambda **kwargs: kwargs,
        send_options=lambda **kwargs: kwargs,
        stdio_mcp_server_config=lambda **kwargs: kwargs,
        local_agent_options=lambda **kwargs: kwargs,
        cloud_agent_options=lambda **kwargs: kwargs,
    )
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(desk_brain, "_load_cursor_sdk_bindings", lambda: bindings)
    monkeypatch.setattr(desk_brain, "_desk_composer_models", lambda: ["test"])
    monkeypatch.setattr(desk_brain, "_mcp_stdio_config", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(desk_brain, "_desk_agent_runtime_kwargs", lambda *_args, **_kwargs: {})
    gateway = types.SimpleNamespace(repo_root=tmp_path, synthesis_thread_get=lambda _id: {})
    state = {
        "desk_primed": True,
        "synthesis_user_turns": 1,
        "rail_context": {"tab": "synthesis", "mode": "define", "thread_id": "thread-42"},
    }
    turn = desk_brain.run_cursor_composer_turn(gateway, "Check the output", state)
    assert turn.action_result["action"] == "composer"
    assert turn.action_result["synthesis_unstructured_draft"] is True
    assert Agent.calls == 2
    assert "query-ready" in turn.reply


def test_verified_lifecycle_reply_can_pass_with_materialisation_artifact(monkeypatch, tmp_path):
    from scripts.research_data_mcp import desk_brain

    class Run:
        status = "success"

        def wait(self):
            return None

        def text(self):
            return "The output is query-ready and registered."

        def conversation(self):
            message = types.SimpleNamespace(
                type="tool_call",
                name="research_synthesis_materialisation",
                result=json.dumps(
                    {
                        "thread_id": "thread-42",
                        "materialisation": "registered",
                        "output_registered": True,
                        "query_ready": True,
                        "executed": True,
                    }
                ),
            )
            return [types.SimpleNamespace(steps=[types.SimpleNamespace(message=message)])]

    class Agent:
        agent_id = "agent-verified"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def send(self, _text, _opts):
            return Run()

    agent_api = types.SimpleNamespace(create=lambda _opts: Agent(), resume=lambda _id, _opts: Agent())
    bindings = desk_brain._CursorSdkBindings(
        agent=agent_api,
        agent_options=lambda **kwargs: kwargs,
        model_selection=lambda **kwargs: kwargs,
        send_options=lambda **kwargs: kwargs,
        stdio_mcp_server_config=lambda **kwargs: kwargs,
        local_agent_options=lambda **kwargs: kwargs,
        cloud_agent_options=lambda **kwargs: kwargs,
    )
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(desk_brain, "_load_cursor_sdk_bindings", lambda: bindings)
    monkeypatch.setattr(desk_brain, "_desk_composer_models", lambda: ["test"])
    monkeypatch.setattr(desk_brain, "_mcp_stdio_config", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(desk_brain, "_desk_agent_runtime_kwargs", lambda *_args, **_kwargs: {})
    gateway = types.SimpleNamespace(repo_root=tmp_path, synthesis_thread_get=lambda _id: {})
    state = {
        "desk_primed": True,
        "synthesis_user_turns": 1,
        "rail_context": {"tab": "synthesis", "mode": "define", "thread_id": "thread-42"},
    }
    turn = desk_brain.run_cursor_composer_turn(gateway, "Verify the output", state)
    assert turn.action_result["action"] == "composer"
    assert turn.action_result["synthesis_verifications"][0]["output_registered"] is True


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


def test_unstructured_synthesis_turn_gets_one_tool_enabled_envelope_repair(monkeypatch, tmp_path):
    from scripts.research_data_mcp import desk_brain

    class Run:
        status = "success"

        def __init__(self, text):
            self._text = text

        def wait(self):
            return None

        def text(self):
            return self._text

        def conversation(self):
            return []

    class Agent:
        agent_id = "agent-continuation"

        def __init__(self):
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def send(self, text, _opts):
            self.calls.append(text)
            if len(self.calls) == 1:
                return Run("The construct remains provisional; I need to verify its inputs.")
            return Run(
                json.dumps(
                    {
                        "reply": "The construct remains provisional; its inputs need verification.",
                        "clarification": "Which validation horizon should we use?",
                        "claims": [],
                        "construction": {"status": "unknown"},
                        "sections": [],
                    }
                )
            )

    agent_instance = Agent()
    agent = SimpleNamespace(
        create=MagicMock(return_value=agent_instance),
        resume=MagicMock(return_value=agent_instance),
    )
    bindings = desk_brain._CursorSdkBindings(
        agent=agent,
        agent_options=lambda **kwargs: kwargs,
        model_selection=lambda **kwargs: kwargs,
        send_options=lambda **kwargs: kwargs,
        stdio_mcp_server_config=lambda **kwargs: kwargs,
        local_agent_options=lambda **kwargs: kwargs,
        cloud_agent_options=lambda **kwargs: kwargs,
    )
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(desk_brain, "_load_cursor_sdk_bindings", lambda: bindings)
    monkeypatch.setattr(desk_brain, "_desk_composer_models", lambda: ["test"])
    monkeypatch.setattr(desk_brain, "_mcp_stdio_config", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(desk_brain, "_desk_agent_runtime_kwargs", lambda *_args, **_kwargs: {})

    state = {
        "desk_primed": True,
        "synthesis_user_turns": 1,
        "rail_context": {"tab": "synthesis", "mode": "define"},
    }
    turn = desk_brain.run_cursor_composer_turn(
        types.SimpleNamespace(repo_root=tmp_path),
        "Review the current construct and return the typed Synthesis response.",
        state,
    )

    assert len(agent_instance.calls) == 2
    assert "tools are allowed" in agent_instance.calls[1]
    assert "typed Synthesis response" in agent_instance.calls[0]
    assert turn.action_result["synthesis_envelope_valid"] is True
    assert turn.action_result["action"] == "composer"


def test_unstructured_synthesis_draft_survives_without_scripted_answer(
    monkeypatch, tmp_path
):
    from scripts.research_data_mcp import desk_brain

    class Run:
        status = "success"

        def wait(self):
            return None

        def text(self):
            return "1. Input: held panel. 2. Grain: entity-week. 3. Transform: aggregate."

        def conversation(self):
            return []

    class Agent:
        agent_id = "agent-partial"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def send(self, _text, _opts):
            return Run()

    agent_instance = Agent()
    agent = SimpleNamespace(
        create=MagicMock(return_value=agent_instance),
        resume=MagicMock(return_value=agent_instance),
    )
    bindings = desk_brain._CursorSdkBindings(
        agent=agent,
        agent_options=lambda **kwargs: kwargs,
        model_selection=lambda **kwargs: kwargs,
        send_options=lambda **kwargs: kwargs,
        stdio_mcp_server_config=lambda **kwargs: kwargs,
        local_agent_options=lambda **kwargs: kwargs,
        cloud_agent_options=lambda **kwargs: kwargs,
    )
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(desk_brain, "_load_cursor_sdk_bindings", lambda: bindings)
    monkeypatch.setattr(desk_brain, "_desk_composer_models", lambda: ["test"])
    monkeypatch.setattr(desk_brain, "_mcp_stdio_config", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(desk_brain, "_desk_agent_runtime_kwargs", lambda *_args, **_kwargs: {})

    state = {
        "desk_primed": True,
        "synthesis_user_turns": 1,
        "rail_context": {"tab": "synthesis", "mode": "define"},
    }
    turn = desk_brain.run_cursor_composer_turn(
        types.SimpleNamespace(repo_root=tmp_path),
        "Answer exactly five numbered items: 1) input, 2) grain, 3) transform, "
        "4) blocker, 5) next action.",
        state,
    )

    assert turn.action_result["action"] == "composer"
    assert turn.action_result["synthesis_unstructured_draft"] is True
    assert "Input: held panel" in turn.reply


def test_unstructured_reply_preserves_proposal_artifact_without_scripted_failure(
    monkeypatch, tmp_path
):
    from scripts.research_data_mcp import desk_brain

    _install_proposal_then_invalid_reply_cursor(monkeypatch)
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(desk_brain, "_desk_composer_models", lambda: ["test"])
    monkeypatch.setattr(desk_brain, "_mcp_stdio_config", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        desk_brain, "_desk_agent_runtime_kwargs", lambda _root, **_kwargs: {}
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

    assert turn.action_result["action"] == "composer"
    assert turn.action_result["synthesis_unstructured_draft"] is True
    assert turn.action_result["synthesis_thread_id"] == "thread-a"
    assert turn.action_result["synthesis_proposal"]["id"] == "proposal-1"
    assert "collected the final panel" in turn.reply


def test_synthesis_timeout_fails_closed_without_gemini(monkeypatch, tmp_path):
    from scripts.research_data_mcp import desk_brain

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
    state = {
        "desk_primed": True,
        "rail_context": {"tab": "synthesis", "mode": "define"},
    }
    turn = desk_brain.run_cursor_composer_turn(
        types.SimpleNamespace(repo_root=tmp_path), "Build a monthly proxy", state
    )
    assert turn.action_result["action"] == "composer_timeout"
    assert turn.action_result.get("fallback") == "none"
    assert turn.action_result.get("brain") == "cursor_composer"
    assert state.get("synthesis_turn_history") is None
    assert "No collection or approval was started" in turn.reply


def test_synthesis_timeout_reports_proposal_already_recorded(monkeypatch, tmp_path):
    from scripts.research_data_mcp import desk_brain

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


def test_empty_synthesis_turn_fails_closed_composer_only(monkeypatch, tmp_path):
    from scripts.research_data_mcp import (
        desk_brain,
        desk_catalog_fallback,
    )

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
    assert turn.action_result.get("fallback") == "none"
    assert turn.action_result["mode"] == "synthesis"
    assert turn.action_result.get("brain") == "cursor_composer"
    assert "did not return a usable reasoning turn" in turn.reply or "usable" in turn.reply.lower()
    assert state.get("synthesis_user_turns") is None


def test_empty_discover_turn_no_inventory_script_brain(monkeypatch, tmp_path):
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
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("inventory script brain must not run")
        ),
    )

    gateway = types.SimpleNamespace(repo_root=tmp_path)
    state = {
        "desk_primed": True,
        "vault_brief": "Ready now:\n- Generic dataset",
        "rail_context": {"tab": "browse", "mode": "explore"},
    }
    turn = desk_brain.run_cursor_composer_turn(gateway, "What do we have?", state)

    assert turn.action_result["action"] == "composer_error"
    assert turn.action_result.get("brain") == "cursor_composer"
    assert "did not return a usable answer" in turn.reply or "No dataset candidates" in turn.reply


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
            return json.dumps(
                {
                    "reply": "A provisional construct with one clarification question.",
                    "clarification": "Which horizon matters most?",
                    "claims": [],
                    "construction": {"status": "unknown"},
                    "sections": [],
                }
            )

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


def test_empty_reply_retries_fallback_model(monkeypatch, tmp_path):
    """After send returns empty, desk must try DESK_COMPOSER_MODEL_FALLBACK — not stop."""
    from scripts.research_data_mcp import desk_brain

    sends = {"n": 0}

    class EmptyRun:
        status = "finished"

        def wait(self):
            return None

        def text(self):
            return ""

        def conversation(self):
            return []

    class GoodRun:
        status = "finished"

        def wait(self):
            return None

        def text(self):
            return "TWSE Open API is the strongest first pull for Taiwan prices."

        def conversation(self):
            return []

    class Agent:
        def __init__(self, model_id):
            self.agent_id = f"agent-{model_id}"
            self.model_id = model_id

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def send(self, _text, _opts):
            sends["n"] += 1
            return EmptyRun() if self.model_id == "primary" else GoodRun()

    class AgentAPI:
        @classmethod
        def resume(cls, _id, opts):
            raise AssertionError("should create fresh agent for fallback")

        @classmethod
        def create(cls, opts):
            model = (opts.get("model") or {}).get("id") or "unknown"
            return Agent(model)

    cursor_sdk = types.ModuleType("cursor_sdk")
    cursor_sdk.Agent = AgentAPI
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
    monkeypatch.setattr(desk_brain, "_mcp_stdio_config", lambda *_a, **_k: {})
    monkeypatch.setattr(desk_brain, "_desk_agent_runtime_kwargs", lambda *_a, **_k: {})
    monkeypatch.setattr(desk_brain, "_wait_run_bounded", lambda *_a, **_k: None)

    turn = desk_brain.run_cursor_composer_turn(
        types.SimpleNamespace(repo_root=tmp_path),
        "What should I collect for Taiwan stock prices?",
        {"desk_primed": True, "rail_context": {"tab": "browse", "workspace": {"query": "Taiwan"}}},
    )
    assert sends["n"] >= 2
    assert "TWSE" in turn.reply
    assert turn.action_result["composer_model"] == "backup"
    assert turn.action_result.get("action") != "composer_error"


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


def test_synthesis_mcp_registration_is_construction_surface(monkeypatch):
    from scripts.research_data_mcp.mcp_register import registered_tool_names

    monkeypatch.setenv("RESEARCH_MCP_SYNTHESIS_READ_ONLY", "1")
    names = set(registered_tool_names())
    assert "research_query_dataset" in names
    assert "research_synthesis_pair" in names
    assert "bigquery_dry_run" in names
    assert "research_synthesis_run" not in names
    assert "research_synthesis_propose_state" in names
    assert "research_synthesis_submit_execution" in names
    assert "research_synthesis_discover_handoff" in names
    assert "research_synthesis_collect_missing" in names
    assert "research_synthesis_terminal_list" in names
    assert "research_synthesis_terminal_run" in names
    assert "datacite_collect_doi" not in names
    # Quant is a downstream consumer of Drive, not a Drive procurement tool.
    assert "research_quant_brief" not in names
    assert "yzu_submit_job" not in names
    assert "yzu_approve_job" not in names
    assert "procurement_approve_job" not in names


def test_synthesis_construction_instructions_require_tools(monkeypatch):
    from scripts.research_data_mcp.mcp_instructions import mcp_server_instructions

    monkeypatch.setenv("RESEARCH_MCP_DESK", "1")
    monkeypatch.setenv("RESEARCH_MCP_SYNTHESIS_READ_ONLY", "1")
    text = mcp_server_instructions()
    assert "propose_state" in text
    assert "submit_execution" in text
    assert "terminal_run" in text
    assert "never applies" in text.lower() or "never applies" in text
    assert "yzu_approve_job" in text.lower() or "Never call yzu_approve_job" in text
    assert "cannot run panels" not in text.lower()
    assert "tell the researcher to use the Synthesis UI" not in text
