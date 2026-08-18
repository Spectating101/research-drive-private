"""Small, inspectable query variants for live dataset catalogues.

External catalogue APIs are not conversational search engines.  Preserve the
researcher's words, but also try a few shorter catalogue queries when a long
natural-language request would otherwise be sent verbatim and return nothing.
This module deliberately does not decide relevance or entitlement: it only
creates bounded alternatives, which callers must report back to the user.
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]*", re.I)

# Request framing adds little to a catalogue query.  Domain, geography, period,
# and measure words are kept; this is not a stop-word list for result ranking.
_FRAMING = frozenset(
    {
        "a", "an", "and", "any", "available", "can", "data", "dataset", "datasets",
        "do", "find", "for", "get", "give", "have", "i", "in", "is", "looking", "me",
        "need", "of", "on", "please", "show", "that", "the", "to", "want", "with", "you",
    }
)
_LIGHT_MODIFIERS = frozenset({"annual", "daily", "monthly", "quarterly", "weekly"})
_GEO_PREFIXES = frozenset({"america", "american", "britain", "china", "europe", "eu", "uk", "us", "usa"})


def _append_unique(out: list[str], value: str, *, cap: int) -> None:
    value = " ".join(str(value or "").split())
    if value and value.casefold() not in {item.casefold() for item in out} and len(out) < cap:
        out.append(value)


def live_query_variants(query: str, *, provider: str, cap: int = 4) -> list[str]:
    """Return the original query plus up to ``cap - 1`` transparent alternatives.

    The original query always comes first.  A short query is not expanded.  For
    a longer request, the alternatives are a compact form, a focused two-term
    phrase, and the central catalogue term.  For example, ``US patent grants
    and citations`` includes ``patent citations`` and ``patent``.
    """
    del provider  # Kept in the contract: providers can diverge without changing callers.
    original = " ".join(str(query or "").split())
    if not original:
        return []
    cap = max(1, min(int(cap or 4), 4))
    out = [original]
    tokens = [token.casefold() for token in _TOKEN_RE.findall(original)]
    content = [token for token in tokens if token not in _FRAMING]
    if len(content) <= 2:
        return out

    _append_unique(out, " ".join(content), cap=cap)
    anchor_candidates = [
        token for token in content
        if token not in _LIGHT_MODIFIERS and token not in _GEO_PREFIXES
    ]
    anchor = anchor_candidates[0] if anchor_candidates else content[0]
    tail_candidates = [token for token in reversed(content) if token != anchor]
    if tail_candidates:
        _append_unique(out, f"{anchor} {tail_candidates[0]}", cap=cap)
    _append_unique(out, anchor, cap=cap)
    return out
