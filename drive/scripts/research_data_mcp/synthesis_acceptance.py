#!/usr/bin/env python3
"""Adversarial acceptance batteries for the Synthesis agent.

First-turn cases grade read/reason-only prose. Construction-investigation cases
grade a multi-turn session: initial novel construct, follow-up clarification,
durable thread linkage, proposed construction state, and optional execution
submission that must stop at pending_approval (never auto-approved).

Provider/runtime failures are reported separately from reasoning-contract
failures so an outage cannot be mistaken for a weak answer.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from sharpe_kernel.paths import repo_root_from_file

REPO = repo_root_from_file(__file__)
DEFAULT_CASES = REPO / "drive/config/synthesis_acceptance_cases.json"

WORKFLOW_FIRST_TURN = "first_turn"
WORKFLOW_CONSTRUCTION = "construction_investigation"

_PROVIDER_ACTIONS = frozenset(
    {"composer_error", "composer_unavailable", "composer_pending"}
)
_COMPOSER_POLL_INTERVAL = 0.5
_COMPOSER_POLL_TIMEOUT_CAP = 120.0
_FORBIDDEN_EXECUTION_CLAIMS = (
    re.compile(
        r"\b(?:i|we|the system)\s+(?:have\s+)?(?:collected|executed|materialised|materialized|registered)\b",
        re.I,
    ),
    re.compile(
        r"(?:^|[.!?]\s+)(?:the\s+)?(?:synthesized\s+|synthesised\s+)?"
        r"(?:construct|synthesis|output|result|measure|panel|dataset)\s+"
        r"(?:is|are)(?:\s+now)?\s+query[- ]ready\b",
        re.I | re.M,
    ),
    re.compile(
        r"\b(?:collection|execution|materialisation|materialization)\s+(?:is\s+)?complete\b",
        re.I,
    ),
)
_FOLLOW_UP_STOPWORDS = frozenset(
    {
        "about",
        "after",
        "also",
        "from",
        "into",
        "primary",
        "should",
        "that",
        "their",
        "then",
        "this",
        "treat",
        "using",
        "with",
    }
)


def load_cases(path: Path = DEFAULT_CASES) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"no Synthesis acceptance cases in {path}")
    return [dict(row) for row in cases if isinstance(row, dict)]


def case_workflow(case: dict[str, Any]) -> str:
    workflow = str(case.get("workflow") or WORKFLOW_FIRST_TURN).strip()
    return workflow or WORKFLOW_FIRST_TURN


def select_cases(
    cases: list[dict[str, Any]],
    *,
    workflow: str | None = None,
    case_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    rows = list(cases)
    if workflow:
        rows = [case for case in rows if case_workflow(case) == workflow]
    if case_ids:
        rows = [case for case in rows if str(case.get("id")) in case_ids]
    return rows


def _group_hits(text: str, groups: list[list[str]]) -> list[dict[str, Any]]:
    lowered = text.lower()
    out: list[dict[str, Any]] = []
    for group in groups:
        terms = [str(term).strip().lower() for term in group if str(term).strip()]
        hits = [term for term in terms if term in lowered]
        out.append({"terms": terms, "hits": hits, "ok": bool(hits)})
    return out


def _chat_action(result: dict[str, Any]) -> str:
    artifacts = result.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    return str(result.get("action") or artifacts.get("action") or "").strip()


def _is_composer_pending(result: dict[str, Any]) -> bool:
    return _chat_action(result) == "composer_pending"


def _chat_result_from_assistant_message(
    session: dict[str, Any],
    message: dict[str, Any],
) -> dict[str, Any]:
    artifacts = message.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    action = str(artifacts.get("action") or "composer").strip()
    return {
        "session_id": str(session.get("session_id") or "").strip(),
        "reply": str(message.get("content") or "").strip(),
        "action": action,
        "artifacts": artifacts,
    }


def find_background_completion(
    session: dict[str, Any],
    *,
    pending_reply: str = "",
) -> dict[str, Any] | None:
    """Reconstruct a completed chat turn from session messages after composer_pending clears."""
    messages = session.get("messages")
    if not isinstance(messages, list):
        return None
    pending_reply = pending_reply.strip()
    pending_index = -1
    for index, message in enumerate(messages):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        artifacts = message.get("artifacts")
        artifacts = artifacts if isinstance(artifacts, dict) else {}
        content = str(message.get("content") or "").strip()
        if (
            str(artifacts.get("action") or "").strip() == "composer_pending"
            or (pending_reply and content == pending_reply)
        ):
            pending_index = index

    candidates = messages[pending_index + 1 :] if pending_index >= 0 else messages
    for message in reversed(candidates):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        artifacts = message.get("artifacts")
        artifacts = artifacts if isinstance(artifacts, dict) else {}
        action = str(artifacts.get("action") or "").strip()
        if action == "composer_pending":
            continue
        content = str(message.get("content") or "").strip()
        if pending_reply and content == pending_reply:
            continue
        if artifacts.get("background_completion"):
            return _chat_result_from_assistant_message(session, message)
        if pending_index >= 0 and action in _PROVIDER_ACTIONS - {"composer_pending"}:
            return _chat_result_from_assistant_message(session, message)
        if pending_index >= 0 and action and action not in _PROVIDER_ACTIONS:
            return _chat_result_from_assistant_message(session, message)
    return None


def composer_pending_timeout_result(
    *,
    session_id: str = "",
    error: str = "composer pending polling timed out",
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "action": "composer_error",
        "reply": "The Synthesis agent did not return a usable reasoning turn.",
        "artifacts": {"action": "composer_error", "error": error},
    }


def wait_for_composer_completion(
    client: SynthesisAcceptanceClient,
    pending: dict[str, Any],
    *,
    poll_interval: float = _COMPOSER_POLL_INTERVAL,
    poll_timeout: float | None = None,
) -> dict[str, Any]:
    """Poll session state until a background Composer turn finishes or times out."""
    session_id = str(pending.get("session_id") or client.session_id or "").strip()
    if not session_id:
        return pending
    deadline = time.monotonic() + (
        poll_timeout if poll_timeout is not None else min(client.timeout, _COMPOSER_POLL_TIMEOUT_CAP)
    )
    pending_reply = str(pending.get("reply") or "").strip()
    while time.monotonic() < deadline:
        try:
            session = client.get_chat_session(session_id)
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            time.sleep(poll_interval)
            continue
        state = session.get("state")
        state = state if isinstance(state, dict) else {}
        if state.get("composer_pending"):
            time.sleep(poll_interval)
            continue
        completed = find_background_completion(session, pending_reply=pending_reply)
        if completed:
            return completed
        time.sleep(poll_interval)
    return composer_pending_timeout_result(session_id=session_id)


def _provider_failure(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any] | None:
    reply = str(result.get("reply") or "").strip()
    artifacts = result.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    action = str(result.get("action") or artifacts.get("action") or "").strip()
    if action not in _PROVIDER_ACTIONS:
        return None
    provider_chain = {
        "primary": str(artifacts.get("brain") or "cursor_composer"),
        "primary_error": str(artifacts.get("error") or artifacts.get("reason") or ""),
        "fallback": str(artifacts.get("fallback") or ""),
        "fallback_error_category": str(artifacts.get("fallback_error_category") or ""),
    }
    return {
        "id": case.get("id"),
        "title": case.get("title"),
        "outcome": "provider_failed",
        "action": action,
        "provider_error": provider_chain["primary_error"],
        "provider_chain": provider_chain,
        "reply": reply,
        "checks": [],
    }


def _execution_claim_patterns(reply: str) -> list[str]:
    return [
        pattern.pattern
        for pattern in _FORBIDDEN_EXECUTION_CLAIMS
        if pattern.search(reply)
    ]


def evaluate_response(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Deterministically validate the Synthesis first-turn contract."""
    provider = _provider_failure(case, result)
    if provider:
        return provider

    reply = str(result.get("reply") or "").strip()
    artifacts = result.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    action = str(result.get("action") or artifacts.get("action") or "").strip()

    asset_checks = _group_hits(
        reply,
        [list(group) for group in case.get("expected_asset_groups") or []],
    )
    risk_checks = _group_hits(
        reply,
        [list(group) for group in case.get("required_risk_groups") or []],
    )
    question_count = reply.count("?")
    forbidden = _execution_claim_patterns(reply)
    checks = [
        {"name": "usable_reply", "ok": len(reply) >= 120, "observed": len(reply)},
        {
            "name": "named_held_evidence",
            "ok": bool(asset_checks) and all(row["ok"] for row in asset_checks),
            "groups": asset_checks,
        },
        {
            "name": "explicit_validity_risks",
            "ok": bool(risk_checks) and all(row["ok"] for row in risk_checks),
            "groups": risk_checks,
        },
        {
            "name": "one_clarification_question",
            "ok": question_count == 1,
            "observed": question_count,
        },
        {
            "name": "no_execution_claim",
            "ok": not forbidden,
            "matched_patterns": forbidden,
        },
        {
            "name": "provisional_language",
            "ok": any(
                marker in reply.lower()
                for marker in (
                    "provisional",
                    "propose",
                    "candidate",
                    "proxy",
                    "could",
                    "would",
                    "not a held",
                    "not held",
                    "does not exist",
                    "not a ready-made",
                )
            ),
        },
    ]
    passed = all(bool(check.get("ok")) for check in checks)
    return {
        "id": case.get("id"),
        "title": case.get("title"),
        "outcome": "passed" if passed else "contract_failed",
        "action": action,
        "reply": reply,
        "checks": checks,
    }


def evaluate_follow_up_response(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Validate the second-turn clarification contract."""
    provider = _provider_failure(case, result)
    if provider:
        return provider

    reply = str(result.get("reply") or "").strip()
    artifacts = result.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    action = str(result.get("action") or artifacts.get("action") or "").strip()
    follow_up = str(case.get("follow_up") or "").strip().lower()
    advance_checks = _group_hits(
        reply,
        [list(group) for group in case.get("expected_follow_up_groups") or []],
    )
    clarification_terms = [
        token
        for token in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", follow_up)
        if len(token) >= 4 and token not in _FOLLOW_UP_STOPWORDS
    ]
    clarification_hits = [
        token for token in dict.fromkeys(clarification_terms) if token in reply.lower()
    ]
    required_clarification_hits = min(2, len(set(clarification_terms)))
    forbidden = _execution_claim_patterns(reply)
    checks = [
        {"name": "usable_reply", "ok": len(reply) >= 80, "observed": len(reply)},
        {
            "name": "incorporates_clarification",
            "ok": not follow_up
            or (
                bool(clarification_terms)
                and len(clarification_hits) >= required_clarification_hits
            ),
            "follow_up_prefix": follow_up[:120],
            "terms": list(dict.fromkeys(clarification_terms)),
            "hits": clarification_hits,
            "required_hits": required_clarification_hits,
        },
        {
            "name": "construct_advance",
            "ok": not advance_checks or all(row["ok"] for row in advance_checks),
            "groups": advance_checks,
        },
        {
            "name": "no_execution_claim",
            "ok": not forbidden,
            "matched_patterns": forbidden,
        },
    ]
    passed = all(bool(check.get("ok")) for check in checks)
    return {
        "phase": "follow_up",
        "outcome": "passed" if passed else "contract_failed",
        "action": action,
        "reply": reply,
        "checks": checks,
    }


def evaluate_novel_construct(
    case: dict[str, Any],
    *,
    profile_ids: set[str],
) -> dict[str, Any]:
    """Ensure the case is a novel construct, not an existing synthesis profile id."""
    request = str(case.get("request") or "").lower()
    entity_id = str((case.get("entity") or {}).get("id") or f"acceptance:{case.get('id')}")
    checks = [
        {
            "name": "not_existing_profile_id",
            "ok": str(case.get("id") or "") not in profile_ids,
            "observed": case.get("id"),
        },
        {
            "name": "request_not_profile_run",
            "ok": not any(pid in request for pid in profile_ids),
        },
        {
            "name": "entity_not_profile_kind",
            "ok": "synthesis_profile" not in entity_id.lower(),
            "observed": entity_id,
        },
    ]
    passed = all(bool(check.get("ok")) for check in checks)
    return {
        "phase": "novel_construct",
        "outcome": "passed" if passed else "contract_failed",
        "checks": checks,
    }


def _construction_blob(thread: dict[str, Any]) -> str:
    state = thread.get("state") if isinstance(thread.get("state"), dict) else {}
    proposal = state.get("proposal") if isinstance(state.get("proposal"), dict) else {}
    return json.dumps(
        {
            "objective": thread.get("objective"),
            "title": thread.get("title"),
            "nodes": state.get("nodes") or [],
            "edges": state.get("edges") or [],
            "spec": state.get("spec") or {},
            "proposal": proposal,
        },
        ensure_ascii=False,
        default=str,
    )


def evaluate_construction_state(
    case: dict[str, Any],
    thread: dict[str, Any],
) -> dict[str, Any]:
    """Grade durable construction state on a synthesis thread."""
    state = thread.get("state") if isinstance(thread.get("state"), dict) else {}
    proposal = state.get("proposal") if isinstance(state.get("proposal"), dict) else {}
    blob = _construction_blob(thread)
    construction_checks = _group_hits(
        blob,
        [list(group) for group in case.get("required_construction_groups") or []],
    )
    checks = [
        {
            "name": "thread_present",
            "ok": bool(thread.get("id")),
            "thread_id": thread.get("id"),
        },
        {
            "name": "session_linked",
            "ok": bool(str(thread.get("session_id") or "").strip()),
            "session_id": thread.get("session_id"),
        },
        {
            "name": "proposal_recorded",
            "ok": bool(proposal.get("id")),
            "proposal_id": proposal.get("id"),
        },
        {
            "name": "construction_elements",
            "ok": bool(construction_checks)
            and all(row["ok"] for row in construction_checks),
            "groups": construction_checks,
        },
        {
            "name": "honest_materialisation",
            "ok": str(state.get("materialisation") or "not_materialised")
            not in {"materialised", "materialized", "registered", "complete"},
            "observed": state.get("materialisation"),
        },
    ]
    passed = all(bool(check.get("ok")) for check in checks)
    return {
        "phase": "construction_state",
        "outcome": "passed" if passed else "contract_failed",
        "thread_id": thread.get("id"),
        "checks": checks,
    }


def evaluate_execution_submission(submit_result: dict[str, Any]) -> dict[str, Any]:
    """Execution must queue for researcher approval only."""
    job = submit_result.get("job") if isinstance(submit_result.get("job"), dict) else {}
    status = str(job.get("status") or submit_result.get("job_status") or "").strip()
    checks = [
        {
            "name": "job_created",
            "ok": bool(job.get("id")),
            "job_id": job.get("id"),
        },
        {
            "name": "pending_approval",
            "ok": status == "pending_approval",
            "observed": status,
        },
        {
            "name": "never_auto_approved",
            "ok": status != "queued" and not bool(submit_result.get("auto_approved")),
            "observed": status,
        },
        {
            "name": "review_required",
            "ok": bool(submit_result.get("review_required", True)),
        },
    ]
    passed = all(bool(check.get("ok")) for check in checks)
    return {
        "phase": "execution_submission",
        "outcome": "passed" if passed else "contract_failed",
        "checks": checks,
    }


def _workflow_outcome(*parts: dict[str, Any]) -> str:
    outcomes = {str(part.get("outcome") or "") for part in parts}
    if "transport_failed" in outcomes:
        return "transport_failed"
    if "provider_failed" in outcomes:
        return "provider_failed"
    if "contract_failed" in outcomes:
        return "contract_failed"
    return "passed"


class SynthesisAcceptanceClient:
    def __init__(self, base_url: str, *, timeout: float = 150.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar)
        )
        self.origin = self.base_url
        self.session_id = ""

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Origin": self.origin,
            },
        )
        with self.opener.open(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get(self, path: str, query: dict[str, Any]) -> dict[str, Any]:
        encoded = urllib.parse.urlencode(query)
        suffix = f"?{encoded}" if encoded else ""
        request = urllib.request.Request(
            f"{self.base_url}{path}{suffix}",
            method="GET",
            headers={"Origin": self.origin},
        )
        with self.opener.open(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def open_session(self) -> None:
        payload = self._post("/library/desk/session", {})
        session_id = str(payload.get("session_id") or "").strip()
        if session_id:
            self.session_id = session_id

    def ensure_chat_session(self) -> str:
        """Bootstrap a durable procurement chat session id before the first turn."""
        if self.session_id:
            return self.session_id
        result = self._post("/library/desk/warm", {"background": False})
        sid = str(result.get("session_id") or "").strip()
        if sid:
            self.session_id = sid
        return self.session_id

    def get_chat_session(self, session_id: str = "") -> dict[str, Any]:
        sid = str(session_id or self.session_id or "").strip()
        if not sid:
            raise ValueError("session_id is required")
        return self._get(f"/library/chat/{urllib.parse.quote(sid, safe='')}", {})

    def list_profile_ids(self) -> set[str]:
        payload = self._get("/library/synthesis/profiles", {})
        return {
            str(row.get("id") or "").strip()
            for row in payload.get("profiles") or []
            if isinstance(row, dict) and str(row.get("id") or "").strip()
        }

    def _rail_context(
        self,
        case: dict[str, Any],
        *,
        thread_id: str = "",
    ) -> dict[str, Any]:
        entity = {
            "kind": "synthesis_project",
            "id": f"acceptance:{case.get('id')}",
            "title": str(case.get("title") or case.get("id") or ""),
        }
        if thread_id:
            entity = {
                "kind": "synthesis_thread",
                "id": thread_id,
                "title": str(case.get("title") or case.get("id") or ""),
            }
        rail: dict[str, Any] = {
            "tab": "synthesis",
            "mode": "define",
            "entity": entity,
            "actions": [
                "clarify_construct",
                "inspect_library",
                "propose_proxy",
                "propose_state",
            ],
        }
        if self.session_id:
            rail["session_id"] = self.session_id
        if thread_id:
            rail["thread_id"] = thread_id
        return rail

    def run_chat(
        self,
        message: str,
        case: dict[str, Any],
        *,
        thread_id: str = "",
    ) -> dict[str, Any]:
        payload = {
            "message": message,
            "rail_context": self._rail_context(case, thread_id=thread_id),
        }
        if self.session_id:
            payload["session_id"] = self.session_id
        result = self._post("/library/chat", payload)
        sid = str(result.get("session_id") or "").strip()
        if sid:
            self.session_id = sid
        if _is_composer_pending(result):
            result = wait_for_composer_completion(self, result)
        return result

    def run_case(self, case: dict[str, Any], *, thread_id: str = "") -> dict[str, Any]:
        return self.run_chat(
            str(case.get("request") or ""),
            case,
            thread_id=thread_id,
        )

    def run_follow_up(self, case: dict[str, Any], *, thread_id: str = "") -> dict[str, Any]:
        return self.run_chat(
            str(case.get("follow_up") or ""),
            case,
            thread_id=thread_id,
        )

    def list_threads(self, *, session_id: str = "") -> list[dict[str, Any]]:
        payload = self._get(
            "/library/synthesis/threads",
            {"session_id": session_id or self.session_id, "limit": 20, "include_ops": 1},
        )
        rows = payload.get("threads") or []
        return [row for row in rows if isinstance(row, dict)]

    def create_thread(self, case: dict[str, Any]) -> dict[str, Any]:
        return self._post(
            "/library/synthesis/threads",
            {
                "objective": str(case.get("request") or case.get("title") or ""),
                "title": str(case.get("title") or case.get("id") or ""),
                "required_grain": str(case.get("required_grain") or ""),
                "session_id": self.session_id,
            },
        )

    def get_thread(self, thread_id: str) -> dict[str, Any]:
        return self._get(
            f"/library/synthesis/threads/{urllib.parse.quote(thread_id, safe='')}",
            {},
        )

    def link_thread(self, thread_id: str) -> dict[str, Any]:
        return self._post(
            f"/library/synthesis/threads/{urllib.parse.quote(thread_id, safe='')}/conversation",
            {"session_id": self.session_id},
        )

    def set_thread_proposal(self, thread_id: str, proposal: dict[str, Any]) -> dict[str, Any]:
        return self._post(
            f"/library/synthesis/threads/{urllib.parse.quote(thread_id, safe='')}/proposal",
            {"proposal": proposal},
        )

    def accept_thread_proposal(self, thread_id: str, proposal: dict[str, Any]) -> dict[str, Any]:
        return self._post(
            f"/library/synthesis/threads/{urllib.parse.quote(thread_id, safe='')}/patches",
            {
                "decision": "accept",
                "proposal_id": proposal.get("id"),
                "proposal_hash": proposal.get("proposal_hash"),
            },
        )

    def submit_thread_execution(self, thread_id: str) -> dict[str, Any]:
        result = self._post(
            f"/library/synthesis/threads/{urllib.parse.quote(thread_id, safe='')}/execute",
            {},
        )
        result.setdefault("review_required", True)
        result.setdefault("auto_approved", False)
        return result

    def preflight_case(self, case: dict[str, Any]) -> dict[str, Any]:
        query = str(case.get("retrieval_query") or "").strip()
        if not query:
            return {"query": "", "rows": [], "groups": [], "ok": False}
        payload = self._get(
            "/library/search",
            {
                "q": query,
                "limit": 12,
                "include_hf": 0,
                "include_datacite": 0,
                "skip_discover": 1,
            },
        )
        rows = list(payload.get("rows") or [])
        if not rows:
            for section in payload.get("sections") or []:
                rows.extend(section.get("rows") or [])
        rows = [row for row in rows[:12] if isinstance(row, dict)]
        details: list[dict[str, Any]] = []
        for row in rows[:8]:
            dataset_id = str(row.get("dataset_id") or row.get("id") or "").strip()
            if not dataset_id:
                continue
            try:
                detail = self._get(
                    f"/datasets/{urllib.parse.quote(dataset_id, safe='')}",
                    {},
                )
            except (OSError, urllib.error.URLError, json.JSONDecodeError):
                continue
            if isinstance(detail, dict):
                details.append(detail)
        try:
            profile_payload = self._get("/library/synthesis/profiles", {})
            profiles = [
                row
                for row in profile_payload.get("profiles") or []
                if isinstance(row, dict)
            ]
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            profiles = []
        blob = json.dumps(
            {"rows": rows, "details": details, "profiles": profiles},
            ensure_ascii=False,
            default=str,
        )
        groups = _group_hits(
            blob,
            [list(group) for group in case.get("expected_asset_groups") or []],
        )
        return {
            "query": query,
            "row_count": len(rows),
            "detail_count": len(details),
            "profile_count": len(profiles),
            "rows": [
                {
                    "dataset_id": row.get("dataset_id") or row.get("id"),
                    "title": row.get("title") or row.get("name"),
                    "source": row.get("source"),
                }
                for row in rows[:8]
            ],
            "groups": groups,
            "ok": bool(groups) and all(group.get("ok") for group in groups),
        }


def _prepare_construction_thread(
    client: SynthesisAcceptanceClient,
    case: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create and link a synthesis thread before any construction chat turn."""
    client.ensure_chat_session()
    created = client.create_thread(case)
    thread_id = str(created.get("id") or "").strip()
    if not thread_id:
        raise ValueError("could not prepare synthesis thread for construction investigation")

    linkage: dict[str, Any] = {"source": "prepared", "thread_id": thread_id}
    linked = client.link_thread(thread_id)
    linkage["linked_session_id"] = linked.get("session_id") or client.session_id
    thread = client.get_thread(thread_id)
    return thread, linkage


def _resolve_construction_proposal(
    client: SynthesisAcceptanceClient,
    case: dict[str, Any],
    thread: dict[str, Any],
    *,
    proof_mode: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return the thread proposal and a proposal-phase evaluation."""
    state = thread.get("state") if isinstance(thread.get("state"), dict) else {}
    proposal = state.get("proposal") if isinstance(state.get("proposal"), dict) else {}
    thread_id = str(thread.get("id") or "")

    if proposal.get("id"):
        return proposal, {
            "phase": "proposal",
            "outcome": "passed",
            "proof_mode": proof_mode,
            "checks": [
                {
                    "name": "agent_originated_proposal",
                    "ok": True,
                    "proposal_id": proposal.get("id"),
                    "source": "thread_state",
                }
            ],
            "proposal_id": proposal.get("id"),
        }

    if proof_mode == "fixture":
        fixture = case.get("proposal_fixture")
        if not isinstance(fixture, dict):
            return None, {
                "phase": "proposal",
                "outcome": "contract_failed",
                "proof_mode": proof_mode,
                "checks": [
                    {
                        "name": "fixture_proposal_available",
                        "ok": False,
                        "reason": "construction case missing proposal_fixture for fixture proof mode",
                    }
                ],
            }
        updated = client.set_thread_proposal(thread_id, fixture)
        next_state = updated.get("state") if isinstance(updated.get("state"), dict) else {}
        recorded = (
            next_state.get("proposal") if isinstance(next_state.get("proposal"), dict) else {}
        )
        if not recorded.get("id"):
            return None, {
                "phase": "proposal",
                "outcome": "contract_failed",
                "proof_mode": proof_mode,
                "checks": [
                    {
                        "name": "fixture_proposal_recorded",
                        "ok": False,
                        "reason": "failed to record fixture proposal on thread",
                    }
                ],
            }
        return recorded, {
            "phase": "proposal",
            "outcome": "passed",
            "proof_mode": proof_mode,
            "checks": [
                {
                    "name": "fixture_proposal_injected",
                    "ok": True,
                    "proposal_id": recorded.get("id"),
                    "source": "proposal_fixture",
                }
            ],
            "proposal_id": recorded.get("id"),
        }

    return None, {
        "phase": "proposal",
        "outcome": "contract_failed",
        "proof_mode": proof_mode,
        "checks": [
            {
                "name": "agent_originated_proposal",
                "ok": False,
                "reason": (
                    "thread has no agent-originated proposal; "
                    "fixture injection is disabled in provider proof mode"
                ),
                "thread_id": thread_id,
            }
        ],
    }


def _construction_state_blocked(reason: str, thread_id: str) -> dict[str, Any]:
    return {
        "phase": "construction_state",
        "outcome": "contract_failed",
        "thread_id": thread_id,
        "checks": [
            {
                "name": "requires_agent_proposal",
                "ok": False,
                "reason": reason,
            }
        ],
    }


def run_construction_investigation(
    client: SynthesisAcceptanceClient,
    case: dict[str, Any],
    *,
    profile_ids: set[str] | None = None,
    proof_mode: str = "provider",
    allow_execution_submission: bool = False,
) -> dict[str, Any]:
    """Run one multi-turn construction investigation acceptance case."""
    case_started = time.time()
    phases: dict[str, Any] = {}
    profile_ids = profile_ids if profile_ids is not None else client.list_profile_ids()

    phases["novel_construct"] = evaluate_novel_construct(case, profile_ids=profile_ids)

    try:
        preflight = client.preflight_case(case)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        preflight = {
            "query": str(case.get("retrieval_query") or ""),
            "ok": False,
            "error": str(exc),
            "rows": [],
            "groups": [],
        }

    thread_id = ""
    linkage: dict[str, Any] = {}
    recorded_proposal: dict[str, Any] | None = None
    try:
        thread, linkage = _prepare_construction_thread(client, case)
        thread_id = str(thread.get("id") or "")
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
        phases["thread_linkage"] = {
            "phase": "thread_linkage",
            "outcome": "transport_failed",
            "error": str(exc),
            "checks": [],
        }
        return _construction_report(
            case,
            phases=phases,
            proof_mode=proof_mode,
            preflight=preflight,
            started=case_started,
        )

    try:
        first_raw = client.run_case(case, thread_id=thread_id)
        phases["first_turn"] = evaluate_response(case, first_raw)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        phases["first_turn"] = {
            "outcome": "transport_failed",
            "error": str(exc),
            "checks": [],
        }

    if phases["first_turn"].get("outcome") in {"provider_failed", "transport_failed"}:
        return _construction_report(
            case,
            phases=phases,
            proof_mode=proof_mode,
            preflight=preflight,
            started=case_started,
        )

    try:
        follow_raw = client.run_follow_up(case, thread_id=thread_id)
        phases["follow_up"] = evaluate_follow_up_response(case, follow_raw)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        phases["follow_up"] = {
            "outcome": "transport_failed",
            "error": str(exc),
            "checks": [],
        }

    if phases["follow_up"].get("outcome") in {"provider_failed", "transport_failed"}:
        return _construction_report(
            case,
            phases=phases,
            proof_mode=proof_mode,
            preflight=preflight,
            started=case_started,
        )

    try:
        thread = client.get_thread(thread_id)
        phases["thread_linkage"] = {
            "phase": "thread_linkage",
            "outcome": "passed"
            if str(thread.get("session_id") or "") == str(client.session_id)
            else "contract_failed",
            "checks": [
                {
                    "name": "thread_resolved",
                    "ok": bool(thread.get("id")),
                    "thread_id": thread.get("id"),
                    "source": linkage.get("source"),
                },
                {
                    "name": "session_linked",
                    "ok": str(thread.get("session_id") or "") == str(client.session_id),
                    "session_id": thread.get("session_id"),
                    "linked_session_id": linkage.get("linked_session_id"),
                },
                {
                    "name": "no_duplicate_thread",
                    "ok": len(session_threads := client.list_threads()) == 1,
                    "observed": len(session_threads),
                },
            ],
            "linkage": linkage,
        }
        recorded_proposal, phases["proposal"] = _resolve_construction_proposal(
            client,
            case,
            thread,
            proof_mode=proof_mode,
        )
        if phases["proposal"].get("outcome") == "passed" and recorded_proposal:
            thread = client.get_thread(thread_id)
            phases["construction_state"] = evaluate_construction_state(case, thread)
        else:
            blocked_reason = str(
                (phases["proposal"].get("checks") or [{}])[0].get("reason")
                or "missing agent-originated proposal"
            )
            phases["construction_state"] = _construction_state_blocked(
                blocked_reason,
                thread_id,
            )
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        phases["construction_state"] = {
            "phase": "construction_state",
            "outcome": "transport_failed",
            "error": str(exc),
            "checks": [],
        }

    execution_requested = bool(case.get("submit_execution"))
    if execution_requested and not allow_execution_submission:
        phases["execution_submission"] = {
            "phase": "execution_submission",
            "outcome": "contract_failed",
            "checks": [
                {
                    "name": "explicit_execution_opt_in",
                    "ok": False,
                    "reason": (
                        "case requests execution submission, but the runner was not "
                        "started with explicit execution permission"
                    ),
                }
            ],
        }
    elif (
        execution_requested
        and thread_id
        and recorded_proposal
        and recorded_proposal.get("id")
    ):
        try:
            accepted = client.accept_thread_proposal(thread_id, recorded_proposal)
            accepted_proposal = (accepted.get("state") or {}).get("proposal")
            if accepted_proposal:
                raise ValueError("accepted proposal should be cleared from thread state")
            submit_result = client.submit_thread_execution(thread_id)
            phases["execution_submission"] = evaluate_execution_submission(submit_result)
        except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
            phases["execution_submission"] = {
                "phase": "execution_submission",
                "outcome": "transport_failed",
                "error": str(exc),
                "checks": [],
            }
    elif execution_requested:
        phases["execution_submission"] = {
            "phase": "execution_submission",
            "outcome": "contract_failed",
            "checks": [
                {
                    "name": "recorded_proposal_required",
                    "ok": False,
                    "thread_id": thread_id,
                    "reason": "execution submission requires a linked thread proposal",
                }
            ],
        }

    return _construction_report(
        case,
        phases=phases,
        proof_mode=proof_mode,
        preflight=preflight,
        started=case_started,
    )


def _construction_report(
    case: dict[str, Any],
    *,
    phases: dict[str, Any],
    proof_mode: str,
    preflight: dict[str, Any],
    started: float,
) -> dict[str, Any]:
    outcome = _workflow_outcome(*phases.values())
    return {
        "id": case.get("id"),
        "title": case.get("title"),
        "workflow": WORKFLOW_CONSTRUCTION,
        "proof_mode": proof_mode,
        "outcome": outcome,
        "phases": phases,
        "grounding_preflight": preflight,
        "elapsed_ms": int((time.time() - started) * 1000),
    }


def run_battery(
    base_url: str,
    *,
    cases_path: Path = DEFAULT_CASES,
    case_ids: set[str] | None = None,
    timeout: float = 150.0,
    workflow: str = WORKFLOW_FIRST_TURN,
    proof_mode: str = "provider",
    allow_fixture_mutation: bool = False,
    allow_execution_submission: bool = False,
) -> dict[str, Any]:
    if proof_mode == "fixture" and not allow_fixture_mutation:
        raise ValueError(
            "fixture proof mode mutates durable thread state; "
            "set allow_fixture_mutation=True only for a disposable test desk"
        )

    cases = select_cases(load_cases(cases_path), workflow=workflow, case_ids=case_ids)
    if not cases:
        raise ValueError(f"no selected Synthesis acceptance cases for workflow={workflow}")

    client = SynthesisAcceptanceClient(base_url, timeout=timeout)
    started = time.time()
    rows: list[dict[str, Any]] = []
    try:
        client.open_session()
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {
            "contract": workflow,
            "proof_mode": proof_mode,
            "base_url": base_url,
            "outcome": "transport_failed",
            "error": str(exc),
            "cases": [],
        }

    if workflow == WORKFLOW_CONSTRUCTION:
        try:
            profile_ids = client.list_profile_ids()
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            return {
                "contract": workflow,
                "proof_mode": proof_mode,
                "base_url": base_url,
                "outcome": "transport_failed",
                "error": f"could not verify synthesis profile inventory: {exc}",
                "cases": [],
            }
        for case in cases:
            rows.append(
                run_construction_investigation(
                    client,
                    case,
                    profile_ids=profile_ids,
                    proof_mode=proof_mode,
                    allow_execution_submission=allow_execution_submission,
                )
            )
    else:
        for case in cases:
            case_started = time.time()
            preflight: dict[str, Any]
            try:
                preflight = client.preflight_case(case)
            except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
                preflight = {
                    "query": str(case.get("retrieval_query") or ""),
                    "ok": False,
                    "error": str(exc),
                    "rows": [],
                    "groups": [],
                }
            try:
                raw = client.run_case(case)
                evaluated = evaluate_response(case, raw)
            except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
                evaluated = {
                    "id": case.get("id"),
                    "title": case.get("title"),
                    "outcome": "transport_failed",
                    "error": str(exc),
                    "checks": [],
                }
            evaluated["grounding_preflight"] = preflight
            evaluated["elapsed_ms"] = int((time.time() - case_started) * 1000)
            rows.append(evaluated)

    outcomes = {
        name: sum(1 for row in rows if row.get("outcome") == name)
        for name in ("passed", "contract_failed", "provider_failed", "transport_failed")
    }
    return {
        "contract": workflow,
        "proof_mode": proof_mode,
        "base_url": base_url,
        "elapsed_ms": int((time.time() - started) * 1000),
        "selected_cases": len(rows),
        "outcomes": outcomes,
        "outcome": "passed" if outcomes["passed"] == len(rows) else "failed",
        "cases": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Synthesis acceptance batteries (first-turn or construction investigation)"
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=150.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--workflow",
        choices=(WORKFLOW_FIRST_TURN, WORKFLOW_CONSTRUCTION),
        default=WORKFLOW_FIRST_TURN,
        help="Acceptance contract to run",
    )
    parser.add_argument(
        "--proof-mode",
        choices=("provider", "fixture"),
        default="provider",
        help=(
            "provider=agent-originated proposal only; fixture=permit deterministic "
            "proposal injection into a disposable test desk"
        ),
    )
    parser.add_argument(
        "--allow-fixture-mutation",
        action="store_true",
        help="Explicitly permit fixture mode to write proposal state",
    )
    parser.add_argument(
        "--allow-execution-submission",
        action="store_true",
        help=(
            "Permit cases with submit_execution=true to accept a proposal and create "
            "a pending-approval job"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = run_battery(
        args.base_url,
        cases_path=args.cases,
        case_ids=set(args.case) or None,
        timeout=args.timeout,
        workflow=args.workflow,
        proof_mode=args.proof_mode,
        allow_fixture_mutation=args.allow_fixture_mutation,
        allow_execution_submission=args.allow_execution_submission,
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if report.get("outcome") == "passed":
        return 0
    if (report.get("outcomes") or {}).get("provider_failed"):
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
