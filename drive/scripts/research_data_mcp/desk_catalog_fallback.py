#!/usr/bin/env python3
"""Vault-brief fallback when Composer returns empty on inventory-style questions."""

from __future__ import annotations

import re
from typing import Any

_INVENTORY_TRIGGERS = (
    "what do we have",
    "what data",
    "already have",
    "in the vault",
    "in our vault",
    "holdings",
    "library",
    "inventory",
    "ready now",
    "what twse",
    "twse data",
)

_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "you",
        "our",
        "have",
        "what",
        "from",
        "that",
        "this",
        "with",
        "your",
        "give",
        "short",
        "plain",
        "answer",
        "already",
        "vault",
        "data",
        "show",
        "sample",
        "rows",
        "can",
    }
)


def _ready_lines(vault_brief: str) -> list[str]:
    lines: list[str] = []
    in_ready = False
    for raw in (vault_brief or "").splitlines():
        line = raw.strip()
        if line.startswith("Ready now:"):
            in_ready = True
            continue
        if in_ready and (line.startswith("Not local yet:") or line.startswith("Procure lane:")):
            break
        if in_ready and line.startswith("- "):
            text = line[2:].strip()
            if text:
                lines.append(text)
    return lines


def _tokens(message: str) -> list[str]:
    return [
        tok
        for tok in re.findall(r"[a-z0-9]{3,}", message.lower())
        if tok not in _STOPWORDS
    ]


def _looks_like_inventory(message: str) -> bool:
    msg = message.lower()
    if any(trigger in msg for trigger in _INVENTORY_TRIGGERS):
        return True
    tokens = _tokens(message)
    return bool(tokens) and any(tok in msg for tok in ("twse", "mops", "taiwan", "stablecoin", "refinitiv", "ethereum"))


def try_inventory_fallback(
    message: str,
    vault_brief: str,
    *,
    repo_root: Any = None,
) -> str | None:
    """Plain-language holdings summary from the preloaded vault brief."""
    del repo_root  # reserved for future query/sample fallback
    if not _looks_like_inventory(message):
        return None

    ready = _ready_lines(vault_brief)
    if not ready:
        return None

    tokens = _tokens(message)
    if tokens:
        hits = [line for line in ready if any(tok in line.lower() for tok in tokens)]
        if hits:
            ready = hits

    if len(ready) == 1:
        return (
            f"We already hold material you can work with: {ready[0]}. "
            "Open Library to browse folders, or Ask me to preview rows or plan a join."
        )

    shown = ready[:5]
    joined = "; ".join(shown)
    extra = f" There are {len(ready) - len(shown)} more related holdings in the vault." if len(ready) > len(shown) else ""
    return (
        f"From the lab vault, here is what matches your question: {joined}.{extra} "
        "These are on-disk or query-ready holdings — use Library to drill down, or Ask for samples and procurement next steps."
    )
