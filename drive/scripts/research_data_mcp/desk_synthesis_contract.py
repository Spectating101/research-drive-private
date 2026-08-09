#!/usr/bin/env python3
"""Synthesis-specific Ask contract.

Discover finds evidence that exists elsewhere. Synthesis reasons about a
research construct that does not yet exist, using held evidence without
silently turning the conversation into procurement or execution.
"""

from __future__ import annotations

import json
from typing import Any

_SYNTHESIS_FALLBACK_THREAD = "__synthesis_session__"


def is_synthesis_context(state: dict[str, Any] | None) -> bool:
    """Return true when Ask is attached to the Synthesis workspace."""
    source = state if isinstance(state, dict) else {}
    rail = source.get("rail_context")
    rail = rail if isinstance(rail, dict) else {}
    entity = rail.get("entity")
    entity = entity if isinstance(entity, dict) else {}

    tab = str(rail.get("tab") or "").strip().lower()
    mode = str(rail.get("mode") or "").strip().lower()
    kind = str(entity.get("kind") or "").strip().lower()
    return (
        tab == "synthesis"
        or tab.startswith("synthesis:")
        or mode == "synthesis"
        or mode.startswith("synthesis:")
        or kind.startswith("synthesis_")
    )


def is_neutral_router_context(state: dict[str, Any] | None) -> bool:
    """Return true for the cross-workspace desk router, not a page-specific Ask.

    The neutral surface is intentionally explicit.  A normal Browse or
    Synthesis rail keeps its existing tool contract; only a rail marked
    ``surface=neutral`` or ``mode=neutral|orchestrate|router`` receives the
    bounded cross-workspace MCP surface.
    """
    source = state if isinstance(state, dict) else {}
    rail = source.get("rail_context")
    rail = rail if isinstance(rail, dict) else {}
    workspace = rail.get("workspace")
    workspace = workspace if isinstance(workspace, dict) else {}
    mode = str(rail.get("mode") or workspace.get("mode") or "").strip().lower()
    surface = str(rail.get("surface") or workspace.get("surface") or "").strip().lower()
    return (
        not is_synthesis_context(source)
        and (surface == "neutral" or mode in {"neutral", "orchestrate", "router"})
    )


def synthesis_starter_prompts() -> list[str]:
    """Prompts that advance construction rather than generic procurement."""
    return [
        "Interpret the construct and identify the highest-value ambiguity",
        "Map the strongest Library evidence to roles in this construct",
        "Compare defensible proxy definitions and their limitations",
        "Design validation and falsification checks before execution",
    ]


def synthesis_thread_key(state: dict[str, Any] | None) -> str:
    """Return the bounded UI thread identity used only for safety phase tracking."""
    source = state if isinstance(state, dict) else {}
    rail = source.get("rail_context")
    rail = rail if isinstance(rail, dict) else {}
    entity = rail.get("entity")
    entity = entity if isinstance(entity, dict) else {}
    raw = rail.get("thread_id") or entity.get("id") or _SYNTHESIS_FALLBACK_THREAD
    value = str(raw or _SYNTHESIS_FALLBACK_THREAD).strip()
    return value[:160] or _SYNTHESIS_FALLBACK_THREAD


def synthesis_turn_count(state: dict[str, Any] | None) -> int:
    source = state if isinstance(state, dict) else {}
    counts = source.get("synthesis_thread_turns")
    if isinstance(counts, dict):
        value = counts.get(synthesis_thread_key(source), 0)
    else:
        value = source.get("synthesis_user_turns", 0)
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def synthesis_first_turn(state: dict[str, Any] | None) -> bool:
    return is_synthesis_context(state) and synthesis_turn_count(state) == 0


def build_synthesis_thread_state_brief(
    gateway: Any, state: dict[str, Any] | None, *, max_chars: int = 5200
) -> str:
    """Load bounded, explicitly observed canvas state for a follow-up turn.

    Conversation history is useful context but is not authoritative state. This
    brief is deliberately assembled from the thread store so Composer cannot
    infer that a proposal was accepted or an output was registered merely because
    a previous turn said so.
    """
    source = state if isinstance(state, dict) else {}
    rail = source.get("rail_context") if isinstance(source.get("rail_context"), dict) else {}
    workspace = rail.get("workspace") if isinstance(rail.get("workspace"), dict) else {}
    entity = rail.get("entity") if isinstance(rail.get("entity"), dict) else {}
    raw_thread_id = (
        rail.get("thread_id")
        or workspace.get("thread_id")
        or source.get("synthesis_thread_id")
        or entity.get("id")
    )
    thread_id = str(raw_thread_id or "").strip()
    if not thread_id or gateway is None:
        return ""
    getter = getattr(gateway, "synthesis_thread_get", None)
    if not callable(getter):
        return "[Observed Synthesis thread state unavailable; do not infer canvas state.]"
    try:
        thread = getter(thread_id)
    except Exception:  # noqa: BLE001 — grounding must never break a conversation turn
        return "[Observed Synthesis thread state unavailable; do not infer canvas state.]"
    if not isinstance(thread, dict):
        return "[Observed Synthesis thread state unavailable; do not infer canvas state.]"
    thread_state = thread.get("state") if isinstance(thread.get("state"), dict) else {}
    lines = [
        "[Observed Synthesis thread state — authoritative for this turn]",
        f"- thread_id: {thread.get('id') or thread_id}",
    ]
    for key in ("title", "objective", "maturity", "maturityLabel"):
        value = thread.get(key) or thread_state.get(key)
        if value:
            label = key.replace("maturityLabel", "maturity_label")
            lines.append(f"- {label}: {str(value)[:700]}")

    nodes = thread_state.get("nodes")
    if isinstance(nodes, list):
        lines.append(f"- nodes_recorded: {len(nodes)}")
        for node in nodes[:8]:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or node.get("node_id") or "").strip()
            label = str(node.get("title") or node.get("label") or node.get("role") or "node").strip()
            status = str(node.get("status") or node.get("state") or "").strip()
            suffix = f" · {status}" if status else ""
            lines.append(f"- node: {label[:240]}{suffix}" + (f" [{node_id[:120]}]" if node_id else ""))

    proposal = thread_state.get("proposal")
    if isinstance(proposal, dict):
        lines.append(
            "- pending_proposal: "
            f"{str(proposal.get('title') or proposal.get('id') or 'untitled')[:300]}"
            " · review required; not applied"
        )
    else:
        lines.append("- pending_proposal: none")
    accepted_hash = thread_state.get("accepted_spec_hash") or thread.get("accepted_spec_hash")
    lines.append(f"- accepted_spec_hash: {str(accepted_hash or 'none')[:180]}")

    materialisation = (
        thread.get("materialisation")
        or thread_state.get("materialisation")
        or "not_materialised"
    )
    lines.append(f"- materialisation: {str(materialisation)[:120]}")
    execution = thread_state.get("execution")
    if isinstance(execution, dict):
        lines.append(
            "- execution: "
            f"status={str(execution.get('status') or 'none')[:100]}"
            f" · job_id={str(execution.get('job_id') or 'none')[:180]}"
        )
    else:
        lines.append("- execution: none recorded")
    lines.append(
        "Do not upgrade any state above. A proposal is not acceptance; completed is "
        "not archived, registered, or query-ready."
    )
    lines.append("[/Observed Synthesis thread state]")
    return "\n".join(lines)[:max_chars]


def _advance_synthesis_phase(state: dict[str, Any]) -> None:
    """Advance only the current Synthesis thread, preserving the legacy counter."""
    key = synthesis_thread_key(state)
    counts = state.get("synthesis_thread_turns")
    if isinstance(counts, dict):
        counts = dict(counts)
    else:
        try:
            legacy_count = max(0, int(state.get("synthesis_user_turns") or 0))
        except (TypeError, ValueError):
            legacy_count = 0
        counts = {key: legacy_count} if legacy_count else {}
    counts[key] = max(0, int(counts.get(key) or 0)) + 1
    state["synthesis_thread_turns"] = counts
    state["synthesis_user_turns"] = sum(
        max(0, int(value or 0)) for value in counts.values()
    )


_LIFECYCLE_STATUSES = {
    "unknown",
    "planned",
    "materialised",
    "materialized",
    "archived",
    "registered",
    "query_ready",
    "query-ready",
    "not_materialised",
    "not_materialized",
}
_CONSTRUCTION_STATUSES = {"proposed", "accepted", "applied", "unknown"}
_VERIFICATION_TOOLS = {
    "research_synthesis_materialisation",
    "research_synthesis_terminal_run",
    "research_synthesis_submit_execution",
}


def parse_synthesis_envelope(text: str) -> dict[str, Any]:
    """Parse the model's optional typed response envelope without parsing prose.

    Plain Composer prose remains usable as an explicitly unstructured draft. It
    never creates a lifecycle or construction claim; only fields in a valid JSON
    envelope can do that.
    """
    raw = str(text or "").strip()
    if not raw:
        return {"structured": False, "reply": "", "claims": [], "sections": []}
    candidate = raw
    if candidate.startswith("```") and candidate.endswith("```"):
        first_newline = candidate.find("\n")
        if first_newline >= 0:
            candidate = candidate[first_newline + 1 : -3].strip()
    try:
        value = json.loads(candidate)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"structured": False, "reply": raw, "claims": [], "sections": []}
    if not isinstance(value, dict) or not isinstance(value.get("reply"), str):
        return {"structured": False, "reply": raw, "claims": [], "sections": []}
    claims = value.get("claims")
    sections = value.get("sections")
    return {
        "structured": True,
        "reply": value["reply"].strip(),
        "clarification": str(value.get("clarification") or "").strip(),
        "claims": [claim for claim in claims if isinstance(claim, dict)]
        if isinstance(claims, list)
        else [],
        "construction": value.get("construction") if isinstance(value.get("construction"), dict) else {},
        "sections": [section for section in sections if isinstance(section, dict)]
        if isinstance(sections, list)
        else [],
    }


def synthesis_envelope_request(*, first_user_turn: bool) -> str:
    """Tell Composer how to return typed claims without constraining its prose."""
    phase = (
        "Include one highest-value clarification in `clarification`. Keep the "
        "construct provisional."
        if first_user_turn
        else "Use `clarification` only when it materially changes the construct."
    )
    return f"""
[Synthesis response envelope]
Return exactly one JSON object after using any needed tools. Do not put markdown
outside the object. Fields:
- `reply`: your normal reasoning prose; discuss evidence, proxies, limitations,
  and alternatives without treating prose as system state.
- `clarification`: one question string or an empty string. {phase}
- `claims`: a list of typed claims. Only include lifecycle or construction claims
  when the matching tool artifact exists in this turn. Each claim must include
  `kind`, `status`, and `evidence_tool`.
- `construction`: an optional object with `status` and `proposal_id`.
- `sections`: optional structured sections with `title` and `content`.

Lifecycle statuses are `planned`, `materialised`, `archived`, `registered`,
`query_ready`, or `unknown`. Construction statuses are `proposed`, `accepted`,
`applied`, or `unknown`. A proposal is not acceptance. Completed execution is
not registration or query readiness. If a tool cannot verify a claim, put
`unknown` in the envelope and explain the limitation in `reply`.
[/Synthesis response envelope]
""".strip()


def validate_synthesis_envelope(
    envelope: dict[str, Any], artifacts: dict[str, Any] | None = None
) -> list[str]:
    """Validate typed claims against same-turn artifacts, never against prose."""
    if not isinstance(envelope, dict) or not envelope.get("structured"):
        return []
    violations: list[str] = []
    source = artifacts if isinstance(artifacts, dict) else {}
    verification_rows = source.get("synthesis_verifications")
    verification_rows = (
        [row for row in verification_rows if isinstance(row, dict)]
        if isinstance(verification_rows, list)
        else []
    )
    proposal = source.get("synthesis_proposal")
    proposal_id = str((proposal or {}).get("id") or "") if isinstance(proposal, dict) else ""

    for claim in envelope.get("claims") or []:
        if not isinstance(claim, dict):
            violations.append("invalid_claim_shape")
            continue
        kind = str(claim.get("kind") or "").strip().lower()
        status = str(claim.get("status") or "").strip().lower()
        evidence_tool = str(claim.get("evidence_tool") or "").strip()
        if kind in {"lifecycle", "materialisation", "materialization"}:
            if status not in _LIFECYCLE_STATUSES:
                violations.append("invalid_lifecycle_status")
                continue
            if status in {"unknown", "not_materialised", "not_materialized"}:
                continue
            if evidence_tool not in _VERIFICATION_TOOLS:
                violations.append("lifecycle_evidence_tool_missing")
                continue
            matching = [row for row in verification_rows if row.get("tool") == evidence_tool]
            if not matching:
                violations.append("lifecycle_artifact_missing")
                continue
            if status in {"registered", "query_ready", "query-ready"} and not any(
                row.get("output_registered") is True
                or row.get("query_ready") is True
                or str(row.get("materialisation") or "").lower() == "registered"
                for row in matching
            ):
                violations.append("lifecycle_artifact_mismatch")
        elif kind in {"construction", "state"}:
            if status not in _CONSTRUCTION_STATUSES:
                violations.append("invalid_construction_status")
                continue
            if status == "unknown":
                continue
            if status == "proposed":
                requested_id = str(claim.get("proposal_id") or envelope.get("construction", {}).get("proposal_id") or "")
                if not proposal_id or (requested_id and requested_id != proposal_id):
                    violations.append("construction_proposal_missing")
            else:
                # Acceptance/application is a thread-store decision, not a Composer claim.
                violations.append("construction_decision_not_model_owned")
        else:
            # Other claim kinds (observation, evidence, proxy, limitation) are
            # reasoning annotations. They do not assert durable system state and
            # therefore do not require a lifecycle/construction artifact here.
            continue
    clarification = envelope.get("clarification")
    if clarification is not None and not isinstance(clarification, str):
        violations.append("invalid_clarification_shape")
    return violations


def synthesis_envelope_repair_request(
    *,
    original_request: str,
    previous_reply: str,
    violations: list[str],
) -> str:
    """Give Composer one tool-enabled chance to repair a typed response."""
    return (
        "[Synthesis envelope repair]\n"
        "Your previous response did not satisfy the typed response contract. "
        "Use the appropriate Synthesis verification or proposal tool now; tools "
        "are allowed on this repair turn. Then return exactly one JSON envelope "
        "with `reply`, `clarification`, `claims`, `construction`, and `sections`. "
        "Do not claim a lifecycle state without matching tool evidence. Do not "
        "claim acceptance or application; those belong to the researcher and the "
        "thread store. If verification is unavailable, use status `unknown`.\n"
        f"Contract issues: {', '.join(violations) or 'missing_or_unstructured_envelope'}\n"
        f"Original request:\n{str(original_request or '').strip()}\n"
        f"Previous response:\n{str(previous_reply or '').strip()[-6000:]}"
    )


def first_turn_reply_is_acceptable(
    reply: str, *, envelope: dict[str, Any] | None = None
) -> bool:
    """Advance a first-turn phase only after Composer returns the typed envelope."""
    parsed = envelope or parse_synthesis_envelope(reply)
    return bool(
        parsed.get("structured")
        and str(parsed.get("reply") or "").strip()
        and str(parsed.get("clarification") or "").strip()
    )


def wrap_synthesis_request(user_text: str, *, first_user_turn: bool) -> str:
    """Attach the Synthesis operating contract to one Composer turn."""
    phase = (
        """
This is the first faculty turn for this Synthesis project. Your answer must:
1. Give a provisional interpretation of the requested construct.
2. Use tools to verify and name the strongest relevant Library assets; state the
   role each could play instead of dumping an inventory.
3. Separate supported facts, proposed proxy choices, and unresolved limitations.
4. End with exactly one highest-value clarification question.

Do not present a final recipe on this turn. Do not collect, execute, materialise,
register, or submit anything. A first-turn proposal remains provisional.
"""
        if first_user_turn
        else """
Continue the same Synthesis investigation. Incorporate the faculty's latest
answer, preserve previously stated limitations, and make the next smallest
defensible advance. Ask one clarification only when it materially changes the
construct or validation plan.
"""
    )
    contract = f"""
[Synthesis workspace contract]
You are operating Research Drive Synthesis, not catalogue search or generic
procurement. The goal is to define and eventually construct a research dataset
that does not directly exist from held evidence, proxies, transformations, and
explicit reasoning.

Use Library evidence as the starting material. Verify material claims with the
research tools. Prefer Synthesis, dataset description, query, comparison, and
coverage tools. The generic vault brief is orientation only and its instruction
not to re-survey inventory does not prevent targeted verification here.

Never imply that a proposed construct already exists. Keep proposed,
materialised, archive-verified, registered, and query-ready states distinct.
Never silently procure or execute. Mutating actions require an explicit,
reviewable proposal and user approval.
{phase.strip()}
[/Synthesis workspace contract]

"""
    return contract + synthesis_envelope_request(first_user_turn=first_user_turn) + "\n\n" + user_text.strip()


def synthesis_failure_reply(status: str = "") -> str:
    """Honest failure copy; never substitute a catalogue list for reasoning."""
    detail = f" ({status})" if status and status != "empty_reply" else ""
    return (
        "The Synthesis agent did not return a usable reasoning turn"
        f"{detail}. I have not inferred a construct, selected proxies, or changed "
        "the project. Please retry; the same research context remains attached."
    )


def synthesis_proposal_recorded_reply(title: str = "") -> str:
    """Truthful fallback when a tool persisted a proposal before prose failed."""
    named = f" “{str(title).strip()}”" if str(title).strip() else ""
    return (
        f"A review proposal{named} was recorded, but the agent explanation did not "
        "pass the response contract. Review the exact change set in the Synthesis "
        "canvas before accepting or rejecting it. Nothing was executed, materialised, "
        "or registered."
    )


def synthesis_reply_violations(
    text: str,
    *,
    first_user_turn: bool,
    artifacts: dict[str, Any] | None = None,
    envelope: dict[str, Any] | None = None,
) -> list[str]:
    """Validate only typed envelope fields; never inspect prose for claims."""
    parsed = envelope or parse_synthesis_envelope(text)
    violations: list[str] = []
    if not str(parsed.get("reply") or "").strip():
        return ["empty_reply"]
    if parsed.get("structured"):
        violations.extend(validate_synthesis_envelope(parsed, artifacts))
        if first_user_turn and not str(parsed.get("clarification") or "").strip():
            violations.append("clarification_missing")
    return list(dict.fromkeys(violations))


def synthesis_history_brief(
    state: dict[str, Any],
    *,
    max_turns: int = 6,
    max_chars: int = 9000,
) -> str:
    """Render bounded prior turns when a stateless provider must take over."""
    rows = state.get("synthesis_turn_history")
    if not isinstance(rows, list) or not rows:
        return ""
    lines = [
        "[Prior Synthesis turns]",
        "Treat this transcript as project context, not as newly verified evidence.",
    ]
    for row in rows[-max(max_turns, 1) :]:
        if not isinstance(row, dict):
            continue
        user = str(row.get("user") or "").strip()
        assistant = str(row.get("assistant") or "").strip()
        if user:
            lines.append(f"Faculty: {user[:900]}")
        if assistant:
            lines.append(f"Synthesis: {assistant[:1800]}")
    lines.append("[/Prior Synthesis turns]")
    return "\n".join(lines)[:max_chars]


def record_synthesis_turn(
    state: dict[str, Any],
    *,
    user: str = "",
    assistant: str = "",
    provider: str = "",
    max_turns: int = 8,
) -> None:
    """Advance the current thread and optionally retain bounded failover context."""
    _advance_synthesis_phase(state)
    if not (user or assistant or provider):
        return
    rows = state.get("synthesis_turn_history")
    history = list(rows) if isinstance(rows, list) else []
    history.append(
        {
            "user": str(user or "")[:1200],
            "assistant": str(assistant or "")[:2600],
            "provider": str(provider or "")[:80],
        }
    )
    state["synthesis_turn_history"] = history[-max(max_turns, 1) :]
