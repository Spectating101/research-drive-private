#!/usr/bin/env python3
"""Synthesis-specific Ask contract.

Discover finds evidence that exists elsewhere. Synthesis reasons about a
research construct that does not yet exist, using held evidence without
silently turning the conversation into procurement or execution.
"""

from __future__ import annotations

import re
from typing import Any


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
)


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


def synthesis_failure_reply(status: str = "") -> str:
    """Honest failure copy; never substitute a catalogue list for reasoning."""
    detail = f" ({status})" if status and status != "empty_reply" else ""
    return (
        "The Synthesis agent did not return a usable reasoning turn"
        f"{detail}. I have not inferred a construct, selected proxies, or changed "
        "the project. Please retry; the same research context remains attached."
    )


def synthesis_reply_violations(text: str, *, first_user_turn: bool) -> list[str]:
    """Return contract violations that make a model reply unsafe to surface."""
    reply = str(text or "").strip()
    violations: list[str] = []
    if not reply:
        return ["empty_reply"]
    if any(pattern.search(reply) for pattern in _FALSE_EXECUTION_CLAIMS):
        violations.append("false_execution_claim")
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
    user: str,
    assistant: str,
    provider: str,
    max_turns: int = 8,
) -> None:
    """Persist a bounded provider-neutral transcript for failover continuity."""
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
