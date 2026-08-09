#!/usr/bin/env python3
"""Synthesis-specific Ask contract.

Discover finds evidence that exists elsewhere. Synthesis reasons about a
research construct that does not yet exist, using held evidence without
silently turning the conversation into procurement or execution.
"""

from __future__ import annotations

import re
from typing import Any

_SYNTHESIS_FALLBACK_THREAD = "__synthesis_session__"
_FALSE_EXECUTION_CLAIMS = (
    re.compile(
        r"\b(?:i|we|the system)\s+(?:have\s+)?"
        r"(?:collected|executed|materialised|materialized|registered)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:collection|execution|materialisation|materialization)\s+"
        r"(?:is\s+)?complete\b",
        re.I,
    ),
    re.compile(r"\b(?:is|are|now)\s+query[- ]ready\b", re.I),
)
_LIFECYCLE_CLAIMS = (
    re.compile(
        r"\b(?:the|this|your|our|a|an)\s+(?:output|dataset|panel|construct|result)\s+"
        r"(?:is|was|now|has been|became|becomes)\s+"
        r"(?:query[- ]ready|registered|materiali[sz]ed|archive[- ]verified|archived|"
        r"complete|completed)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:i|we|the system)\s+(?:have|has|just|now)?\s*"
        r"(?:registered|materiali[sz]ed|archived|executed|completed)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:query[- ]ready|registered|materiali[sz]ed|archive[- ]verified)\s+"
        r"(?:output|dataset|panel)\b",
        re.I,
    ),
)
_CONSTRUCTION_ADVANCE_CLAIMS = (
    re.compile(
        r"\b(?:i|we|the system)\s+(?:have|has|just|now)?\s*"
        r"(?:updated|changed|applied|recorded|accepted|locked|finali[sz]ed)\s+"
        r"(?:the\s+)?(?:construct|method|recipe|canvas|spec|state|proposal|"
        r"node|edge|proxy|transform|input|column|evidence)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:i|we|the system)\s+(?:have|has|just|now)?\s*"
        r"(?:added|removed)\s+(?:the\s+)?(?:node|edge|proxy|transform|input|"
        r"column|evidence|dataset|role)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:the|this)\s+(?:construct|method|recipe|canvas|spec|state)\s+"
        r"(?:is|was|now|has been)\s+(?:updated|changed|locked|finali[sz]ed|applied)\b",
        re.I,
    ),
)

_SYNTHESIS_CTA = re.compile(
    r"\n+\s*(?:I can|You can)\s+drill into any dataset.*?\bstart a collect\b.*$",
    re.I | re.S,
)
_NUMBERED_SECTION = re.compile(
    # Models often put the first numbered item immediately after an opening
    # sentence ("... below. 1. Input ...") rather than starting a new line.
    # Require whitespace after the marker so decimal values are not sections.
    r"(?<![\w.])(?:#{1,6}\s*)?(?:\*\*)?(\d+)[.)](?:\*\*)?(?=\s)",
)
_NUMBER_WORDS = {
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
}


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


def first_turn_reply_is_acceptable(reply: str) -> bool:
    """Minimal deterministic gate before advancing a Synthesis thread phase."""
    return not synthesis_reply_violations(reply, first_user_turn=True)


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
    return contract + user_text.strip()


def strip_synthesis_procurement_cta(text: str) -> str:
    """Remove the generic catalogue/procurement footer from Synthesis prose.

    Synthesis can expose a deliberate Discover handoff, but a provider's generic
    "I can ... start a collect" footer is not a decision or a valid next action
    for a read-only reasoning turn. Keeping it makes a completed answer look like
    an implicit procurement offer.
    """
    reply = str(text or "").strip()
    if not reply:
        return reply
    return _SYNTHESIS_CTA.sub("", reply).strip()


def expected_synthesis_sections(request: str) -> int:
    """Infer an explicitly requested numbered-brief size, if one exists."""
    source = str(request or "").strip()
    if not source:
        return 0
    exact = re.search(
        r"\bexactly\s+(\d+|two|three|four|five|six|seven|eight)\s+"
        r"(?:numbered\s+)?(?:items|sections|parts|points|bullets)",
        source,
        re.I,
    )
    if exact:
        raw = exact.group(1).lower()
        return max(0, int(raw) if raw.isdigit() else _NUMBER_WORDS[raw])
    tail = source.rsplit("return:", 1)[-1] if "return:" in source.lower() else source
    labels = [int(match.group(1)) for match in re.finditer(r"\(\s*(\d+)\s*\)", tail)]
    if len(labels) >= 2 and labels == list(range(1, max(labels) + 1)):
        return max(labels)
    return 0


def completed_synthesis_sections(reply: str) -> int:
    """Return the highest contiguous numbered section in a provider reply."""
    cleaned = strip_synthesis_procurement_cta(reply)
    labels = {int(match.group(1)) for match in _NUMBERED_SECTION.finditer(cleaned)}
    completed = 0
    while completed + 1 in labels:
        completed += 1
    return completed


def synthesis_reply_needs_continuation(request: str, reply: str) -> bool:
    """Detect a provider that stopped before an explicitly requested brief ended."""
    expected = expected_synthesis_sections(request)
    return expected >= 2 and completed_synthesis_sections(reply) < expected


def synthesis_continuation_request(request: str, reply: str) -> str:
    """Ask the same Composer session for only the missing numbered sections."""
    expected = expected_synthesis_sections(request)
    completed = completed_synthesis_sections(reply)
    next_section = completed + 1
    return (
        "[Synthesis continuation]\n"
        f"Your previous answer stopped after section {completed} of {expected}. "
        f"Continue with sections {next_section}–{expected} only; do not repeat "
        "completed sections. Finish the requested brief in numbered form. Keep "
        "observed evidence, proposed transformations, and unknowns distinct. "
        "Write every missing section even when its answer is Unknown. Do not call "
        "tools on this continuation; use the verified evidence already in the "
        "previous answer. This is read-only: do not propose, collect, approve, "
        "execute, materialise, or append a generic catalogue/procurement offer.\n\n"
        f"Original request:\n{str(request or '').strip()}\n\n"
        f"Previous answer:\n{strip_synthesis_procurement_cta(reply)[-6000:]}"
    )


def synthesis_incomplete_reply(reply: str, request: str) -> str:
    """Surface a bounded, honest draft when Composer still stops early."""
    expected = expected_synthesis_sections(request)
    completed = completed_synthesis_sections(reply)
    cleaned = strip_synthesis_procurement_cta(reply)
    if expected < 2:
        return synthesis_failure_reply("response_contract")
    missing = f"sections {completed + 1}–{expected}"
    return (
        f"{cleaned}\n\n**Synthesis draft incomplete.** The agent returned {completed} "
        f"of {expected} requested sections; {missing} are still missing. No "
        "proposal, collection, approval, execution, or materialisation was "
        "created. Continue this Synthesis thread to finish the brief."
    ).strip()


def synthesis_failure_reply(status: str = "") -> str:
    """Honest failure copy; never substitute a catalogue list for reasoning."""
    detail = f" ({status})" if status and status != "empty_reply" else ""
    return (
        "The Synthesis agent did not return a usable reasoning turn"
        f"{detail}. I have not inferred a construct, selected proxies, or changed "
        "the project. Please retry; the same research context remains attached."
    )


def synthesis_claim_failure_reply() -> str:
    """Explain why an unverified lifecycle claim was not accepted."""
    return (
        "The Synthesis reply made a lifecycle claim without a verifying tool result. "
        "I have not treated the output as materialised, archived, registered, or "
        "query-ready. Nothing was executed or changed; inspect the thread or run "
        "the appropriate verification tool before making that claim."
    )


def synthesis_advance_failure_reply() -> str:
    """Explain why prose cannot advance the durable construction state by itself."""
    return (
        "The Synthesis reply described a construction change, but no reviewable "
        "state artifact was recorded in this turn. I have not changed the canvas. "
        "Record a proposal through the Synthesis tool, then review it before any "
        "acceptance or execution."
    )


def _verification_records(artifacts: dict[str, Any] | None) -> list[dict[str, Any]]:
    source = artifacts if isinstance(artifacts, dict) else {}
    rows = source.get("synthesis_verifications")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _positive_bool(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() in {"true", "yes", "1"})


def synthesis_lifecycle_claim_violations(
    text: str, artifacts: dict[str, Any] | None = None
) -> list[str]:
    """Fail closed when prose claims output lifecycle state without same-turn proof."""
    reply = str(text or "").strip()
    if not reply or not any(pattern.search(reply) for pattern in _LIFECYCLE_CLAIMS):
        return []
    records = _verification_records(artifacts)
    materialised = False
    executed = False
    registered = False
    archived = False
    query_ready = False
    for record in records:
        status = str(record.get("materialisation") or record.get("status") or "").lower()
        materialised = materialised or status in {"materialised", "materialized", "registered"}
        executed = executed or _positive_bool(record.get("executed")) or status in {"completed", "registered"}
        registered = (
            registered
            or _positive_bool(record.get("output_registered"))
            or _positive_bool(record.get("registered"))
            or status == "registered"
        )
        archived = (
            archived
            or _positive_bool(record.get("archive_verified"))
            or status in {"archived", "archive_verified"}
        )
        query_ready = query_ready or _positive_bool(record.get("query_ready"))
    violations: list[str] = []
    positive_claim = reply.lower()
    if re.search(r"\bquery[- ]ready\b", positive_claim) and not (query_ready or registered):
        violations.append("unverified_query_ready_claim")
    if re.search(r"\bregistered\b", positive_claim) and not registered:
        violations.append("unverified_registration_claim")
    if re.search(r"archive[- ]verified|\barchived\b", positive_claim) and not archived:
        violations.append("unverified_archive_claim")
    if re.search(r"materiali[sz]ed|\bexecuted\b|\bcompleted\b", positive_claim) and not (materialised or executed):
        violations.append("unverified_execution_claim")
    return violations


def synthesis_construction_claim_violations(
    text: str,
    *,
    artifacts: dict[str, Any] | None = None,
    first_user_turn: bool = False,
) -> list[str]:
    """Require a durable review artifact when a later turn claims canvas progress."""
    if first_user_turn:
        return []
    reply = str(text or "").strip()
    if not reply or not any(pattern.search(reply) for pattern in _CONSTRUCTION_ADVANCE_CLAIMS):
        return []
    source = artifacts if isinstance(artifacts, dict) else {}
    if isinstance(source.get("synthesis_proposal"), dict):
        # A proposal is a reviewable state artifact. It is not treated as applied.
        return []
    if isinstance(source.get("synthesis_state_artifact"), dict):
        return []
    return ["construction_advance_without_artifact"]


def synthesis_proposal_recorded_reply(title: str = "") -> str:
    """Truthful fallback when a tool persisted a proposal before prose failed."""
    named = f" “{str(title).strip()}”" if str(title).strip() else ""
    return (
        f"A review proposal{named} was recorded, but the agent explanation did not "
        "pass the response contract. Review the exact change set in the Synthesis "
        "canvas before accepting or rejecting it. Nothing was executed, materialised, "
        "or registered."
    )


_CLARIFICATION_FALLBACK = (
    "What is the single highest-value ambiguity we should resolve before locking this construct?"
)


def normalize_synthesis_clarification(text: str) -> str:
    """Hands repair: keep Composer prose, enforce exactly one clarification question."""
    reply = str(text or "").strip()
    if not reply:
        return reply
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", reply) if p and p.strip()]
    if not parts:
        return reply
    questions = [p for p in parts if "?" in p]
    statements = [p for p in parts if "?" not in p]
    if len(questions) == 1 and reply.count("?") == 1:
        return reply
    if not questions:
        return f"{reply.rstrip()}\n\n{_CLARIFICATION_FALLBACK}"
    chosen = questions[-1]
    q_idx = chosen.find("?")
    if q_idx >= 0:
        chosen = chosen[: q_idx + 1].strip()
    body = " ".join(statements).strip()
    if body:
        return f"{body}\n\n{chosen}"
    return chosen


def maybe_repair_synthesis_reply(text: str, *, first_user_turn: bool) -> str:
    """Repair only clarification-count misses; never paper over false execution claims."""
    reply = str(text or "").strip()
    if not first_user_turn or not reply:
        return reply
    violations = synthesis_reply_violations(reply, first_user_turn=True)
    if "clarification_question_count" not in violations:
        return reply
    if "false_execution_claim" in violations or "empty_reply" in violations:
        return reply
    repaired = normalize_synthesis_clarification(reply)
    repaired_violations = synthesis_reply_violations(repaired, first_user_turn=True)
    if "clarification_question_count" in repaired_violations:
        return reply
    if "false_execution_claim" in repaired_violations:
        return reply
    return repaired


def _has_lifecycle_evidence(artifacts: dict[str, Any] | None) -> bool:
    for record in _verification_records(artifacts):
        status = str(record.get("materialisation") or record.get("status") or "").lower()
        if (
            _positive_bool(record.get("executed"))
            or _positive_bool(record.get("execution_recorded"))
            or _positive_bool(record.get("output_registered"))
            or _positive_bool(record.get("query_ready"))
            or _positive_bool(record.get("archive_verified"))
            or _positive_bool(record.get("registered"))
            or status in {"completed", "materialised", "materialized", "registered"}
        ):
            return True
    return False


def synthesis_reply_violations(
    text: str,
    *,
    first_user_turn: bool,
    artifacts: dict[str, Any] | None = None,
) -> list[str]:
    """Return contract violations that make a model reply unsafe to surface."""
    reply = str(text or "").strip()
    violations: list[str] = []
    if not reply:
        return ["empty_reply"]
    if any(pattern.search(reply) for pattern in _FALSE_EXECUTION_CLAIMS) and (
        first_user_turn or not _has_lifecycle_evidence(artifacts)
    ):
        violations.append("false_execution_claim")
    if first_user_turn and len(reply) < 40:
        violations.append("insufficient_substance")
    if first_user_turn and reply.count("?") != 1:
        violations.append("clarification_question_count")
    if first_user_turn and not any(
        marker in reply.lower()
        for marker in ("provisional", "propose", "candidate", "proxy", "could", "would")
    ):
        violations.append("missing_provisional_language")
    return violations


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
