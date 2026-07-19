#!/usr/bin/env python3
"""Fast local vault brief — preloads inventory so Composer skips a cold discovery pass."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_vault_brief(repo_root: Path, faculty_profile: dict[str, Any] | None = None) -> str:
    from scripts.research_data_mcp.collection_dictionary import build_dictionary, dictionary_path
    from scripts.research_data_mcp.collection_hydrate import collection_status_summary

    repo_root = Path(repo_root).resolve()
    vault = collection_status_summary(repo_root)
    path = dictionary_path(repo_root)
    doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else build_dictionary(repo_root)
    tables = doc.get("tables") or {}
    profile = faculty_profile or {}

    ready: list[str] = []
    ready_ids: list[str] = []
    for row in tables.get("registry_datasets") or []:
        if not (row.get("availability") or {}).get("have"):
            continue
        line = str(row.get("chat_line") or row.get("title") or row.get("id") or "").strip()
        rid = str(row.get("id") or "").strip()
        if line:
            ready.append(line)
            ready_ids.append(rid)

    for row in tables.get("partitions") or []:
        av = row.get("availability") or {}
        if not (av.get("on_local") or av.get("on_drive") == "yes"):
            continue
        line = str(row.get("chat_line") or row.get("title") or row.get("id") or "").strip()
        if line and line not in ready:
            ready.append(line)
            ready_ids.append("")

    def _score(line: str, rid: str = "") -> int:
        blob = f"{line} {rid}".lower()
        score = 0
        for grant in profile.get("research_grants") or []:
            title = (grant.get("title") if isinstance(grant, dict) else str(grant)).lower()
            for token in title.split():
                if len(token) > 4 and token in blob:
                    score += 5
        for track in profile.get("research_tracks") or []:
            title = (track.get("title") if isinstance(track, dict) else str(track)).lower()
            for token in title.split():
                if len(token) > 4 and token in blob:
                    score += 3
        for item in profile.get("lab_fintech_stack") or []:
            prompt = str(item.get("prompt") or item.get("title") or "").lower()
            for token in prompt.split():
                if len(token) > 4 and token in blob:
                    score += 2
        return score

    ranked = sorted(
        zip(ready, ready_ids, strict=False),
        key=lambda pair: (-_score(pair[0], pair[1]), pair[0]),
    )
    ready = [line for line, _rid in ranked]

    lines = [
        "Desk vault brief (already loaded for this chat — trust this for inventory questions).",
        (
            f"On disk: {vault.get('registry_on_disk', '?')} registered datasets, "
            f"{vault.get('partitions_with_local_data', '?')} collection partitions with local bytes."
        ),
    ]

    for key in ("research_grants", "research_tracks"):
        items = profile.get(key) or []
        if not items:
            continue
        item = items[0]
        title = item.get("title") if isinstance(item, dict) else str(item)
        if title:
            label = "Active grant" if key == "research_grants" else "Research focus"
            lines.append(f"{label}: {title[:140]}")
            break

    if ready:
        lines.append("Ready now:")
        lines.extend(f"- {line}" for line in ready[:10])

    missing: list[str] = []
    for gap in vault.get("top_gaps") or []:
        if gap.get("gap") not in {"not_on_disk", "local_cache"}:
            continue
        line = str(gap.get("chat_line") or gap.get("id") or "").strip()
        if line:
            missing.append(line)
    if missing:
        lines.append("Not local yet:")
        lines.extend(f"- {line}" for line in missing[:5])

    # Cached desk snapshot — entitlement gaps Composer should not confuse with query-ready
    for rel in (
        "drive/docs/status/generated/consolidated_state.json",
        "docs/status/generated/consolidated_state.json",
    ):
        cons_path = repo_root / rel
        if not cons_path.is_file():
            continue
        try:
            from scripts.research_data_mcp.consolidated_state import composer_procurement_snapshot

            snap = composer_procurement_snapshot(json.loads(cons_path.read_text(encoding="utf-8")))
            hl = snap.get("headline") or {}
            inst = snap.get("instant_query_ready")
            inst_t = snap.get("instant_total")
            if inst is not None and inst_t:
                lines.append(f"Registry instant query-ready: {inst}/{inst_t}.")
            gap_cells = snap.get("gap_cells")
            if gap_cells:
                lines.append(
                    f"Licensed entitlement gaps: {gap_cells} source cells not fully materialized — "
                    "use collection queue / yzu_submit_job, not research_query_dataset."
                )
            pgaps = snap.get("priority_access_gaps") or []
            if pgaps:
                labels = [
                    str(g.get("source_id") or g.get("gap") or "")[:40]
                    for g in pgaps[:4]
                    if isinstance(g, dict)
                ]
                labels = [x for x in labels if x]
                if labels:
                    lines.append(f"Priority gaps: {', '.join(labels)}.")
        except (json.JSONDecodeError, OSError, TypeError):
            pass
        break

    lines.append(
        "Procure lane: Hugging Face datasets, DataCite DOI, and public URLs → collect once → Google Drive vault "
        "(collection/). Multi-source synthesis (joining held datasets) is assistant-driven when the user asks."
    )

    lines.append(
        "Reply in normal conversational prose (≤8 sentences on the first answer). "
        "No file paths or registry ids unless the user asks for technical detail. "
        "Do not re-survey the vault on this turn — use tools only for samples, query, collect, or hydrate."
    )
    return "\n".join(lines)


def wrap_first_turn_message(brief: str, user_message: str) -> str:
    msg = user_message.strip()
    b = brief.strip()
    if not b:
        return msg
    return f"{b}\n\n---\n\n{msg}"
