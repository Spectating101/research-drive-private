"""Deterministic grading for adversarial Synthesis first turns and construction investigations."""

from __future__ import annotations

import json
from pathlib import Path


def _case():
    return {
        "id": "idn",
        "title": "IDN construct",
        "expected_asset_groups": [
            ["jkse pit", "point-in-time jkse"],
            ["microstructure", "idn fry"],
        ],
        "required_risk_groups": [
            ["survivorship"],
            ["entity mapping"],
            ["retail ident", "retail-facing"],
        ],
    }


def _construction_case():
    return {
        "workflow": "construction_investigation",
        "id": "asean_supply_chain_stress",
        "title": "ASEAN supply-chain stress exposure (novel construct)",
        "request": "Design a novel ASEAN supply-chain stress measure. Do not execute.",
        "follow_up": "Use a one-week primary horizon and treat port congestion as a proxy.",
        "expected_asset_groups": [
            ["asean", "trade"],
            ["gdelt", "news"],
        ],
        "required_risk_groups": [
            ["survivorship"],
            ["coverage"],
        ],
        "expected_follow_up_groups": [["one-week", "week"], ["port", "congestion"]],
        "required_construction_groups": [
            ["input", "held"],
            ["proxy", "port"],
            ["transform", "country-week"],
            ["assumption"],
            ["unknown", "coverage"],
        ],
        "proposal_fixture": {
            "id": "fixture-proposal",
            "title": "Fixture proposal",
            "summary": "Recorded construction state.",
            "operations": [
                {
                    "op": "update_spec",
                    "patch": {
                        "construction": [
                            "input: held trade evidence",
                            "proxy: port congestion",
                            "transform: country-week aggregate",
                            "assumption: provisional stress measure",
                            "unknown: coverage gaps remain",
                        ]
                    },
                }
            ],
        },
    }


def _construction_thread():
    return {
        "id": "thread-1",
        "session_id": "sess-1",
        "objective": "Novel construct",
        "state": {
            "materialisation": "not_materialised",
            "proposal": {
                "id": "fixture-proposal",
                "title": "Fixture proposal",
                "summary": "Recorded construction state.",
            },
            "spec": {
                "construction": [
                    "input: held trade evidence",
                    "proxy: port congestion",
                    "transform: country-week aggregate",
                    "assumption: provisional stress measure",
                    "unknown: coverage gaps remain",
                ]
            },
            "nodes": [],
        },
    }


def test_accepts_a_grounded_provisional_first_turn():
    from scripts.research_data_mcp.synthesis_acceptance import evaluate_response

    result = {
        "action": "composer",
        "reply": (
            "Provisionally, this is a latent retail-facing coordination proxy, not an "
            "identity measure. JKSE PIT supplies the historical universe and IDN FRY "
            "microstructure supplies candidate synchronized-flow components. The design "
            "must preserve survivorship limitations and entity mapping uncertainty, and "
            "must not treat retail identities as verified. Which coordination horizon "
            "should be primary: same-day, two-day, or one-week?"
        ),
        "artifacts": {"action": "composer"},
    }
    evaluated = evaluate_response(_case(), result)

    assert evaluated["outcome"] == "passed"
    assert all(check["ok"] for check in evaluated["checks"])


def test_provider_failure_is_not_scored_as_reasoning_failure():
    from scripts.research_data_mcp.synthesis_acceptance import evaluate_response

    result = {
        "action": "composer_error",
        "reply": "The Synthesis agent did not return a usable reasoning turn.",
        "artifacts": {"action": "composer_error", "error": "internal error"},
    }
    evaluated = evaluate_response(_case(), result)

    assert evaluated["outcome"] == "provider_failed"
    assert evaluated["provider_error"] == "internal error"
    assert evaluated["provider_chain"]["primary"] == "cursor_composer"
    assert evaluated["provider_chain"]["fallback"] == ""
    assert evaluated["checks"] == []


def test_provider_failure_reports_the_fallback_chain():
    from scripts.research_data_mcp.synthesis_acceptance import evaluate_response

    result = {
        "action": "composer_error",
        "reply": "The Synthesis agent did not return a usable reasoning turn.",
        "artifacts": {
            "action": "composer_error",
            "brain": "cursor_composer",
            "error": "internal error",
            "fallback": "gemini_failed",
            "fallback_error_category": "authentication",
        },
    }
    evaluated = evaluate_response(_case(), result)

    assert evaluated["outcome"] == "provider_failed"
    assert evaluated["provider_chain"] == {
        "primary": "cursor_composer",
        "primary_error": "internal error",
        "fallback": "gemini_failed",
        "fallback_error_category": "authentication",
    }


def test_rejects_inventory_dump_and_missing_clarification():
    from scripts.research_data_mcp.synthesis_acceptance import evaluate_response

    result = {
        "action": "composer",
        "reply": (
            "Available datasets include JKSE PIT and IDN FRY microstructure. "
            "They are ready to use. Open Library for more details. "
            "This answer has no construct interpretation, survivorship discussion, "
            "entity mapping limitation, or clarification."
        ),
        "artifacts": {"action": "composer"},
    }
    evaluated = evaluate_response(_case(), result)

    assert evaluated["outcome"] == "contract_failed"
    checks = {row["name"]: row for row in evaluated["checks"]}
    assert checks["one_clarification_question"]["ok"] is False
    assert checks["explicit_validity_risks"]["ok"] is False


def test_rejects_false_execution_claim():
    from scripts.research_data_mcp.synthesis_acceptance import evaluate_response

    result = {
        "action": "composer",
        "reply": (
            "Provisionally, JKSE PIT and IDN FRY microstructure could support the proxy. "
            "Survivorship, entity mapping, and unverified retail identities remain risks. "
            "We have materialized the final dataset and it is now query-ready. "
            "Which horizon should be primary?"
        ),
        "artifacts": {"action": "composer"},
    }
    evaluated = evaluate_response(_case(), result)
    checks = {row["name"]: row for row in evaluated["checks"]}

    assert evaluated["outcome"] == "contract_failed"
    assert checks["no_execution_claim"]["ok"] is False


def test_query_ready_input_is_not_mistaken_for_synthesized_output():
    from scripts.research_data_mcp.synthesis_acceptance import _execution_claim_patterns

    assert _execution_claim_patterns("The held Asia panel is query-ready.") == []
    assert _execution_claim_patterns("The synthesized output is now query-ready.")


def test_case_file_is_complete_and_non_mutating():
    from scripts.research_data_mcp.synthesis_acceptance import case_workflow, load_cases

    cases = load_cases()
    assert len(cases) >= 5
    assert len({row["id"] for row in cases}) == len(cases)
    first_turn = [row for row in cases if case_workflow(row) == "first_turn"]
    construction = [row for row in cases if case_workflow(row) == "construction_investigation"]
    assert len(first_turn) >= 5
    assert len(construction) >= 1
    for row in first_turn:
        request = row["request"].lower()
        assert row["retrieval_query"]
        assert row["expected_asset_groups"]
        assert row["required_risk_groups"]
        assert any(term in request for term in ("do not", "don't"))
        assert not any(
            phrase in request
            for phrase in ("approve and run", "auto-approve", "submit execution")
        )
    for row in construction:
        assert row["follow_up"]
        assert row["required_construction_groups"]
        assert row["proposal_fixture"]
        assert "synthesis profile" in row["request"].lower() or "does not exist" in row["request"].lower()


def test_construction_follow_up_passes_with_advancement():
    from scripts.research_data_mcp.synthesis_acceptance import evaluate_follow_up_response

    result = {
        "action": "composer",
        "reply": (
            "With a one-week primary horizon, port congestion can proxy logistics stress while "
            "demand-shock components stay separate. Survivorship and country coverage remain unknown."
        ),
        "artifacts": {"action": "composer"},
    }
    evaluated = evaluate_follow_up_response(_construction_case(), result)

    assert evaluated["outcome"] == "passed"
    assert all(check["ok"] for check in evaluated["checks"])


def test_construction_follow_up_rejects_generic_token_overlap():
    from scripts.research_data_mcp.synthesis_acceptance import evaluate_follow_up_response

    case = _construction_case()
    case["expected_follow_up_groups"] = []
    result = {
        "action": "composer",
        "reply": (
            "This response acknowledges that more detail was supplied, but only repeats "
            "generic planning language and never incorporates the substantive direction."
        ),
        "artifacts": {"action": "composer"},
    }
    evaluated = evaluate_follow_up_response(case, result)
    checks = {row["name"]: row for row in evaluated["checks"]}

    assert evaluated["outcome"] == "contract_failed"
    assert checks["incorporates_clarification"]["ok"] is False


def test_construction_state_requires_linked_thread_and_elements():
    from scripts.research_data_mcp.synthesis_acceptance import evaluate_construction_state

    evaluated = evaluate_construction_state(_construction_case(), _construction_thread())

    assert evaluated["outcome"] == "passed"
    checks = {row["name"]: row for row in evaluated["checks"]}
    assert checks["session_linked"]["ok"] is True
    assert checks["construction_elements"]["ok"] is True


def test_novel_construct_rejects_profile_id_collision():
    from scripts.research_data_mcp.synthesis_acceptance import evaluate_novel_construct

    evaluated = evaluate_novel_construct(
        {"id": "skynet_etherscan_stablecoin", "request": "run skynet_etherscan_stablecoin"},
        profile_ids={"skynet_etherscan_stablecoin"},
    )

    assert evaluated["outcome"] == "contract_failed"


def test_execution_submission_must_stop_at_pending_approval():
    from scripts.research_data_mcp.synthesis_acceptance import evaluate_execution_submission

    passed = evaluate_execution_submission(
        {
            "job": {"id": "job-1", "status": "pending_approval"},
            "review_required": True,
            "auto_approved": False,
        }
    )
    failed = evaluate_execution_submission(
        {
            "job": {"id": "job-2", "status": "queued"},
            "review_required": True,
            "auto_approved": False,
        }
    )

    assert passed["outcome"] == "passed"
    assert failed["outcome"] == "contract_failed"
    assert failed["checks"][1]["name"] == "pending_approval"


def test_construction_workflow_fixture_proof(monkeypatch, tmp_path: Path):
    from scripts.research_data_mcp import synthesis_acceptance

    case_path = tmp_path / "cases.json"
    case_path.write_text(
        json.dumps({"cases": [_case(), _construction_case()]}),
        encoding="utf-8",
    )

    class FakeClient(synthesis_acceptance.SynthesisAcceptanceClient):
        def open_session(self):
            self.session_id = "sess-fixture"

        def ensure_chat_session(self):
            self.session_id = "sess-fixture"
            return self.session_id

        def list_profile_ids(self):
            return {"skynet_etherscan_stablecoin"}

        def preflight_case(self, case):
            return {"ok": True, "query": case.get("retrieval_query"), "groups": []}

        def run_case(self, case, *, thread_id=""):
            self.session_id = "sess-fixture"
            return {
                "session_id": "sess-fixture",
                "reply": (
                    "Provisionally, held ASEAN trade and GDELT news could support a latent stress proxy. "
                    "Survivorship, timing leakage, and country coverage remain risks. "
                    "Which horizon should be primary?"
                ),
                "action": "composer",
                "artifacts": {"action": "composer"},
            }

        def run_follow_up(self, case, thread_id=""):
            return {
                "session_id": "sess-fixture",
                "reply": (
                    "A one-week horizon keeps port congestion as a logistics proxy while demand shocks "
                    "stay separate. Coverage gaps remain unknown."
                ),
                "action": "composer",
                "artifacts": {"action": "composer"},
            }

        def list_threads(self, session_id=""):
            return [{"id": "thread-fixture"}]

        def create_thread(self, case):
            return {"id": "thread-fixture"}

        def link_thread(self, thread_id):
            return {"id": thread_id, "session_id": self.session_id}

        def get_thread(self, thread_id):
            return _construction_thread() | {"id": thread_id, "session_id": self.session_id}

        def set_thread_proposal(self, thread_id, proposal):
            thread = self.get_thread(thread_id)
            thread["state"]["proposal"] = proposal | {"proposal_hash": "abc123"}
            return thread

    monkeypatch.setattr(
        synthesis_acceptance,
        "SynthesisAcceptanceClient",
        FakeClient,
    )
    report = synthesis_acceptance.run_battery(
        "http://127.0.0.1:9",
        cases_path=case_path,
        workflow="construction_investigation",
        proof_mode="fixture",
        allow_fixture_mutation=True,
    )

    assert report["contract"] == "construction_investigation"
    assert report["proof_mode"] == "fixture"
    assert report["selected_cases"] == 1
    assert report["cases"][0]["outcome"] == "passed"
    assert report["cases"][0]["phases"]["first_turn"]["outcome"] == "passed"
    assert report["cases"][0]["phases"]["construction_state"]["outcome"] == "passed"


def test_construction_workflow_prepares_thread_before_chat(monkeypatch, tmp_path: Path):
    from scripts.research_data_mcp import synthesis_acceptance

    case_path = tmp_path / "cases.json"
    case_path.write_text(
        json.dumps({"cases": [_construction_case()]}),
        encoding="utf-8",
    )
    call_order: list[str] = []
    chat_thread_ids: list[str] = []

    class FakeClient(synthesis_acceptance.SynthesisAcceptanceClient):
        def open_session(self):
            self.session_id = "sess-order"

        def ensure_chat_session(self):
            call_order.append("ensure_chat_session")
            self.session_id = "sess-order"
            return self.session_id

        def list_profile_ids(self):
            return set()

        def preflight_case(self, case):
            return {"ok": True, "query": "", "groups": []}

        def create_thread(self, case):
            call_order.append("create_thread")
            return {"id": "thread-order"}

        def link_thread(self, thread_id):
            call_order.append("link_thread")
            return {"id": thread_id, "session_id": self.session_id}

        def run_case(self, case, *, thread_id=""):
            call_order.append("run_case")
            chat_thread_ids.append(thread_id)
            return {
                "reply": (
                    "Provisionally, ASEAN trade and GDELT news could support a latent stress proxy. "
                    "Survivorship and coverage remain risks. Which horizon should be primary?"
                ),
                "action": "composer",
                "artifacts": {"action": "composer"},
            }

        def run_follow_up(self, case, thread_id=""):
            call_order.append("run_follow_up")
            chat_thread_ids.append(thread_id)
            return {
                "reply": (
                    "A one-week horizon keeps port congestion as a logistics proxy while demand shocks "
                    "stay separate. Coverage gaps remain unknown."
                ),
                "action": "composer",
                "artifacts": {"action": "composer"},
            }

        def list_threads(self, session_id=""):
            return [{"id": "thread-order"}]

        def get_thread(self, thread_id):
            return _construction_thread() | {"id": thread_id, "session_id": self.session_id}

        def set_thread_proposal(self, thread_id, proposal):
            thread = self.get_thread(thread_id)
            thread["state"]["proposal"] = proposal | {"proposal_hash": "abc123"}
            return thread

    monkeypatch.setattr(synthesis_acceptance, "SynthesisAcceptanceClient", FakeClient)
    report = synthesis_acceptance.run_battery(
        "http://127.0.0.1:9",
        cases_path=case_path,
        workflow="construction_investigation",
        proof_mode="fixture",
    )

    assert call_order[:4] == [
        "ensure_chat_session",
        "create_thread",
        "link_thread",
        "run_case",
    ]
    assert chat_thread_ids == ["thread-order", "thread-order"]
    linkage = report["cases"][0]["phases"]["thread_linkage"]
    assert linkage["linkage"]["source"] == "prepared"
    assert linkage["checks"][2]["name"] == "no_duplicate_thread"
    assert linkage["checks"][2]["ok"] is True


def test_provider_mode_never_injects_proposal_fixture(monkeypatch, tmp_path: Path):
    from scripts.research_data_mcp import synthesis_acceptance

    case_path = tmp_path / "cases.json"
    case_path.write_text(
        json.dumps({"cases": [_construction_case()]}),
        encoding="utf-8",
    )
    set_proposal_calls: list[tuple[str, dict]] = []
    create_thread_calls: list[dict] = []
    chat_thread_ids: list[str] = []

    class FakeClient(synthesis_acceptance.SynthesisAcceptanceClient):
        def open_session(self):
            self.session_id = "sess-provider"

        def ensure_chat_session(self):
            self.session_id = "sess-provider"
            return self.session_id

        def list_profile_ids(self):
            return {"skynet_etherscan_stablecoin"}

        def preflight_case(self, case):
            return {"ok": True, "query": case.get("retrieval_query"), "groups": []}

        def run_case(self, case, *, thread_id=""):
            chat_thread_ids.append(thread_id)
            self.session_id = "sess-provider"
            return {
                "session_id": "sess-provider",
                "reply": (
                    "Provisionally, held ASEAN trade and GDELT news could support a latent stress proxy. "
                    "Survivorship, timing leakage, and country coverage remain risks. "
                    "Which horizon should be primary?"
                ),
                "action": "composer",
                "artifacts": {"action": "composer"},
            }

        def run_follow_up(self, case, thread_id=""):
            chat_thread_ids.append(thread_id)
            return {
                "session_id": "sess-provider",
                "reply": (
                    "A one-week horizon keeps port congestion as a logistics proxy while demand shocks "
                    "stay separate. Coverage gaps remain unknown."
                ),
                "action": "composer",
                "artifacts": {"action": "composer"},
            }

        def list_threads(self, session_id=""):
            return [{"id": "thread-provider"}]

        def create_thread(self, case):
            create_thread_calls.append(case)
            return {"id": "thread-provider"}

        def link_thread(self, thread_id):
            return {"id": thread_id, "session_id": self.session_id}

        def get_thread(self, thread_id):
            return {
                "id": thread_id,
                "session_id": self.session_id,
                "objective": "Novel construct",
                "state": {
                    "materialisation": "not_materialised",
                    "proposal": None,
                    "spec": {},
                    "nodes": [],
                },
            }

        def set_thread_proposal(self, thread_id, proposal):
            set_proposal_calls.append((thread_id, proposal))
            thread = self.get_thread(thread_id)
            thread["state"]["proposal"] = proposal
            return thread

    monkeypatch.setattr(
        synthesis_acceptance,
        "SynthesisAcceptanceClient",
        FakeClient,
    )
    report = synthesis_acceptance.run_battery(
        "http://127.0.0.1:9",
        cases_path=case_path,
        workflow="construction_investigation",
        proof_mode="provider",
    )

    assert set_proposal_calls == []
    assert len(create_thread_calls) == 1
    assert chat_thread_ids == ["thread-provider", "thread-provider"]
    assert report["proof_mode"] == "provider"
    assert report["outcome"] == "failed"
    case_report = report["cases"][0]
    assert case_report["outcome"] == "contract_failed"
    proposal_phase = case_report["phases"]["proposal"]
    assert proposal_phase["outcome"] == "contract_failed"
    assert proposal_phase["checks"][0]["name"] == "agent_originated_proposal"
    assert "fixture injection is disabled" in proposal_phase["checks"][0]["reason"]
    construction_phase = case_report["phases"]["construction_state"]
    assert construction_phase["outcome"] == "contract_failed"
    assert construction_phase["checks"][0]["name"] == "requires_agent_proposal"
    assert construction_phase["outcome"] != "transport_failed"


def test_fixture_proof_requires_explicit_mutation_permission(tmp_path: Path):
    from scripts.research_data_mcp import synthesis_acceptance

    case_path = tmp_path / "cases.json"
    case_path.write_text(
        json.dumps({"cases": [_construction_case()]}),
        encoding="utf-8",
    )

    try:
        synthesis_acceptance.run_battery(
            "http://127.0.0.1:9",
            cases_path=case_path,
            workflow="construction_investigation",
            proof_mode="fixture",
        )
    except ValueError as exc:
        assert "fixture proof mode mutates durable thread state" in str(exc)
    else:
        raise AssertionError("fixture proof mode should require explicit mutation permission")


def test_construction_inventory_failure_is_transport_failure(monkeypatch, tmp_path: Path):
    from scripts.research_data_mcp import synthesis_acceptance

    case_path = tmp_path / "cases.json"
    case_path.write_text(
        json.dumps({"cases": [_construction_case()]}),
        encoding="utf-8",
    )

    class FakeClient(synthesis_acceptance.SynthesisAcceptanceClient):
        def open_session(self):
            self.session_id = "sess-profile-failure"

        def list_profile_ids(self):
            raise OSError("profile inventory offline")

    monkeypatch.setattr(synthesis_acceptance, "SynthesisAcceptanceClient", FakeClient)
    report = synthesis_acceptance.run_battery(
        "http://127.0.0.1:9",
        cases_path=case_path,
        workflow="construction_investigation",
    )

    assert report["outcome"] == "transport_failed"
    assert report["cases"] == []
    assert "profile inventory offline" in report["error"]


def test_missing_chat_thread_creates_fresh_thread():
    from scripts.research_data_mcp.synthesis_acceptance import _ensure_thread

    class FakeClient:
        session_id = "sess-fresh"

        def create_thread(self, case):
            return {"id": "thread-fresh"}

        def link_thread(self, thread_id):
            return {"id": thread_id, "session_id": self.session_id}

        def get_thread(self, thread_id):
            return {"id": thread_id, "session_id": self.session_id, "state": {}}

        def list_threads(self, session_id=""):
            raise AssertionError("must not inherit an arbitrary existing thread")

    thread, linkage = _ensure_thread(FakeClient(), _construction_case(), chat_results=[{}])

    assert thread["id"] == "thread-fresh"
    assert linkage["source"] == "created"


def test_execution_submission_requires_explicit_runner_permission():
    from scripts.research_data_mcp import synthesis_acceptance

    case = _construction_case() | {"submit_execution": True}

    class FakeClient:
        session_id = "sess-execution-gate"

        def list_profile_ids(self):
            return set()

        def preflight_case(self, case):
            return {"ok": True, "groups": []}

        def run_case(self, case):
            return {
                "reply": (
                    "Provisionally, held ASEAN trade and GDELT news could support a latent stress "
                    "proxy. Survivorship, timing leakage, and country coverage remain risks. "
                    "Which horizon should be primary?"
                ),
                "action": "composer",
                "artifacts": {"action": "composer", "thread_id": "thread-gated"},
            }

        def run_follow_up(self, case, thread_id=""):
            return {
                "reply": (
                    "A one-week horizon keeps port congestion as a logistics proxy while demand "
                    "shocks stay separate. Coverage gaps remain unknown."
                ),
                "action": "composer",
                "artifacts": {"action": "composer", "thread_id": thread_id},
            }

        def link_thread(self, thread_id):
            return {"id": thread_id, "session_id": self.session_id}

        def get_thread(self, thread_id):
            return _construction_thread() | {
                "id": thread_id,
                "session_id": self.session_id,
            }

        def accept_thread_proposal(self, thread_id, proposal):
            raise AssertionError("execution must remain gated")

    report = synthesis_acceptance.run_construction_investigation(
        FakeClient(),
        case,
        profile_ids=set(),
    )

    phase = report["phases"]["execution_submission"]
    assert phase["outcome"] == "contract_failed"
    assert phase["checks"][0]["name"] == "explicit_execution_opt_in"


def test_battery_classifies_transport_failure(monkeypatch, tmp_path: Path):
    from scripts.research_data_mcp import synthesis_acceptance

    case_path = tmp_path / "cases.json"
    case_path.write_text(
        json.dumps({"cases": [{**_case(), "request": "Do not execute."}]}),
        encoding="utf-8",
    )

    def fail_session(self):
        raise OSError("offline")

    monkeypatch.setattr(
        synthesis_acceptance.SynthesisAcceptanceClient,
        "open_session",
        fail_session,
    )
    report = synthesis_acceptance.run_battery(
        "http://127.0.0.1:9",
        cases_path=case_path,
    )

    assert report["outcome"] == "transport_failed"
    assert report["cases"] == []


def test_preflight_combines_search_details_and_synthesis_profiles(monkeypatch):
    from scripts.research_data_mcp.synthesis_acceptance import (
        SynthesisAcceptanceClient,
    )

    client = SynthesisAcceptanceClient("http://example.test")

    def fake_get(path, query):
        if path == "/library/search":
            return {
                "rows": [
                    {
                        "dataset_id": "mops_governance_panel",
                        "title": "Taiwan MOPS governance misconduct panel",
                    }
                ]
            }
        if path == "/datasets/mops_governance_panel":
            return {
                "dataset_id": "mops_governance_panel",
                "description": "Official governance filings and disclosures.",
            }
        if path == "/library/synthesis/profiles":
            return {
                "profiles": [
                    {
                        "title": "Governance intervention pattern",
                        "description": "Point-in-time filing-date construction.",
                    }
                ]
            }
        raise AssertionError(path)

    monkeypatch.setattr(client, "_get", fake_get)
    preflight = client.preflight_case(
        {
            "retrieval_query": "Taiwan MOPS governance",
            "expected_asset_groups": [
                ["mops"],
                ["filing", "disclosure"],
                ["point-in-time"],
            ],
        }
    )
    assert preflight["ok"] is True
    assert preflight["detail_count"] == 1
    assert preflight["profile_count"] == 1
