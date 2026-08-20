"""Whether a first-turn reply said anything, as distinct from sounding like it did.

desk_synthesis_contract already gates the shape of a reply: not empty, no false
execution claim, one clarification question, provisional wording. That gate passes
this text —

    "Provisionally, <title> should be treated as a latent research measure, not as
     an observed field. The mapped Library inputs are candidate evidence: core
     signals support the construct, while validation sources test whether it
     behaves as intended. The main unresolved risk is construct validity and time
     alignment. Which signal should define the primary measure?"

— with zero violations, and passes it identically for two unrelated objectives.
It was written, deliberately or not, to satisfy exactly those markers.

So this asks a different question: did the reply name a grain, a period, and a
dataset that exists? Those are checkable facts rather than judgements of quality,
and a claim missing any of them is not an interpretation the desk should render.

Presence is necessary, not sufficient. A reply naming all three can still be
wrong; a reply naming none of them cannot be right.
"""

from __future__ import annotations

import re
from typing import Any

TIME_UNITS = ("day", "week", "month", "quarter", "year", "daily", "weekly", "monthly", "quarterly")

GRAIN_PATTERNS = (
    re.compile(r"\b[a-z_]+\s*[×x]\s*(?:" + "|".join(TIME_UNITS) + r")\b", re.I),
    re.compile(r"\b[a-z_]+-(?:" + "|".join(TIME_UNITS) + r")\b", re.I),
    re.compile(r"\bper\s+[a-z_]+\s+per\s+(?:" + "|".join(TIME_UNITS) + r")\b", re.I),
    re.compile(r"\b(?:one row per|grain(?:\s+is)?)\s+[a-z_ ]+\b", re.I),
)

PERIOD_PATTERNS = (
    re.compile(r"\b(19|20)\d{2}\s*(?:–|-|to|onward|→)\s*(?:(19|20)\d{2}|present|now)\b", re.I),
    re.compile(r"\b(?:from|since|starting)\s+(19|20)\d{2}\b", re.I),
    re.compile(r"\b(19|20)\d{2}\s+onward", re.I),
)


def _first_match(text: str, patterns) -> str | None:
    for pattern in patterns:
        found = pattern.search(text)
        if found:
            return found.group(0).strip()
    return None


def named_datasets(text: str, dataset_ids) -> list[str]:
    """Dataset ids the reply actually names. Substring, but ids are distinctive."""
    lowered = str(text or "").lower()
    return sorted({str(i) for i in (dataset_ids or []) if str(i) and str(i).lower() in lowered})


def reply_substance(text: str, dataset_ids=None) -> dict[str, Any]:
    reply = str(text or "")
    grain = _first_match(reply, GRAIN_PATTERNS)
    period = _first_match(reply, PERIOD_PATTERNS)
    evidence = named_datasets(reply, dataset_ids)
    missing = [
        name for name, value in
        (("grain", grain), ("period", period), ("evidence", evidence))
        if not value
    ]
    return {
        "grain": grain,
        "period": period,
        "evidence": evidence,
        "missing": missing,
        "complete": not missing,
    }


def substance_violations(text: str, dataset_ids=None) -> list[str]:
    """Names the contract module can append to its own violation list."""
    return [f"no_{name}_named" for name in reply_substance(text, dataset_ids)["missing"]]
