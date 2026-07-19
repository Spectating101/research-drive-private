#!/usr/bin/env python3
"""Light post-processing so first desk replies stay conversational, not ops dumps."""

from __future__ import annotations

import re


_PATH_LINE = re.compile(r"data_lake/|/home/|registry_datasets|`\w+_\w+`", re.I)


def sanitize_desk_reply(text: str, *, first_turn: bool = False) -> str:
    if not text or not first_turn:
        return text

    kept: list[str] = []
    for line in text.splitlines():
        if _PATH_LINE.search(line):
            continue
        kept.append(line)
    out = "\n".join(kept).strip()
    out = re.sub(r"\n{3,}", "\n\n", out)

    words = out.split()
    if len(words) > 200:
        chunk = " ".join(words[:160])
        if "." in chunk:
            chunk = chunk.rsplit(".", 1)[0] + "."
        out = (
            f"{chunk}\n\n"
            "I can drill into any dataset, run a sample query, or start a collect — just say which market or topic."
        )
    return out
