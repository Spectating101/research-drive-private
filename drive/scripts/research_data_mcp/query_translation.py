#!/usr/bin/env python3
"""Turn a research question into queries an external catalogue can actually answer.

External dataset APIs are keyword endpoints: HuggingFace exposes `?search=`, DataCite a
query string. Neither accepts a sentence. The desk was forwarding the question verbatim —
`datacite_supplement_queries` returned its input unchanged — so a detailed patent request
could return nothing from Hugging Face while a concise patent query returns real corpora.

Two layers, deliberately:

  * `search_terms()` is deterministic, so the desk degrades honestly with no model
    available. It strips question scaffolding and emits a backoff ladder, broadest last.
  * `llm_search_terms()` lets a reasoner propose terms instead, which is what the tool loop
    was designed to do. It falls back to the deterministic ladder on any failure.

The deterministic planner is the production floor.  A model may improve a
query plan, but availability of a model must never determine whether Discover
can use a public catalogue at all.
"""

from __future__ import annotations

import re
from typing import Any, Callable

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9\-]{1,}")

# Question scaffolding and words that describe the *asking*, not the subject. Removing them
# is what turns a sentence into a query; keeping them is why the sentence returned nothing.
STOPWORDS = frozenset("""
a an and are as at be by can could do does for from get give has have how i in into is it
its me my need needs of on or our please show that the their there these this those to us
was we what when where which who why will with would you your
data dataset datasets database file files record records source sources
find search look looking available access get obtain acquire collect
any some all best good better most more much many other another
regarding
""".split())

# Words that carry no discriminating power in a dataset catalogue even though they are nouns.
WEAK = frozenset({"study", "studies", "research", "analysis", "information", "report",
                  "reports", "series", "panel", "table", "list", "set", "sets"})

# Keep a small, explicit set here rather than silently stripping a location
# from a request such as "US company fundamentals".  ``US`` needs special
# treatment because lower-case "us" is ordinarily question scaffolding.
GEOGRAPHY = frozenset(
    {
        "us", "usa", "america", "american", "taiwan", "taipei", "china", "chinese",
        "japan", "japanese", "korea", "korean", "india", "indonesia", "singapore",
        "europe", "european", "uk", "britain", "british", "canada", "canadian",
        "australia", "australian", "global", "international",
    }
)
LIGHT_MODIFIERS = frozenset({"annual", "daily", "monthly", "quarterly", "weekly"})
_RETURN_TERMS = frozenset({"return", "returns"})
_LISTED_COMPANY_TERMS = frozenset({"listed", "company", "companies", "firm", "firms", "equity", "equities", "share", "shares"})


def _tokens(question: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in _WORD.findall(str(question or "")):
        word = raw.lower()
        # Preserve the country abbreviation only when the user wrote it as an
        # abbreviation; normal prose such as "send it to us" remains filler.
        keep_uppercase_us = raw == "US"
        if (word in STOPWORDS and not keep_uppercase_us) or (len(word) < 3 and not keep_uppercase_us):
            continue
        if word in seen:
            continue
        seen.add(word)
        out.append(word)
    return out


def content_terms(question: str) -> list[str]:
    """Discriminating terms, most specific first. Weak nouns sink rather than vanish."""
    toks = _tokens(question)
    strong = [t for t in toks if t not in WEAK]
    weak = [t for t in toks if t in WEAK]
    return strong + weak


def catalogue_query_variants(question: str, *, provider: str = "", max_variants: int = 4) -> list[str]:
    """Return a small, transparent plan for a text-oriented catalogue.

    The first item is always the researcher's wording.  Subsequent items are
    shorter alternatives for providers such as Hugging Face and DataCite that
    accept a text query rather than a conversational request.  These are not
    interpretations of relevance or entitlement; callers must still assess
    every returned candidate against the original question.

    ``provider`` is intentionally part of the stable contract.  The current
    public catalogue APIs share a lexical interface; future providers may use
    it to tailor their own query grammar without duplicating call sites.
    """
    del provider
    original = " ".join(str(question or "").split())
    if not original:
        return []
    max_variants = max(1, min(int(max_variants or 4), 4))
    terms = content_terms(original)
    if len(terms) <= 2:
        return [original]

    variants: list[str] = []

    def add(value: str) -> None:
        normalized = " ".join(value.split())
        if normalized and normalized.casefold() not in {item.casefold() for item in variants}:
            variants.append(normalized)

    add(original)
    add(" ".join(terms))

    geography = [term for term in terms if term in GEOGRAPHY]
    subject_terms = [term for term in terms if term not in GEOGRAPHY and term not in LIGHT_MODIFIERS]
    # This is a narrowly-defined vocabulary bridge, not a general reasoning
    # system: market-return requests often say "listed companies", whereas
    # public catalogues label the same material "stock".  Keep the geography
    # so the derived phrase cannot silently broaden a Taiwan request to global
    # equities.
    if geography and (_RETURN_TERMS & set(terms)) and (_LISTED_COMPANY_TERMS & set(terms)):
        add(f"{geography[-1]} stock")
    # The trailing subject pair is often the useful catalogue phrase: it turns
    # "US patent grants and citations" into "patent citations", rather than
    # making the generic first noun the only fallback.
    if len(subject_terms) >= 2:
        add(" ".join(subject_terms[0:1] + subject_terms[-1:]))
    elif geography and subject_terms:
        add(f"{geography[-1]} {subject_terms[-1]}")
    anchor_candidates = subject_terms or [term for term in terms if term not in LIGHT_MODIFIERS] or terms
    add(anchor_candidates[0])
    return variants[:max_variants]


def search_terms(question: str, *, max_variants: int = 4) -> list[str]:
    """A transparent original-to-broader plan for external catalogue calls."""
    return catalogue_query_variants(question, max_variants=max_variants)


def llm_search_terms(
    question: str,
    *,
    propose: Callable[[str], Any] | None = None,
    max_variants: int = 4,
) -> list[str]:
    """Terms proposed by a reasoner, falling back to the deterministic ladder.

    `propose` takes the question and returns terms (list, or newline/comma text). Any
    failure or empty result yields the deterministic ladder, so a dead model degrades to
    honest keyword search rather than to no search.
    """
    fallback = search_terms(question, max_variants=max_variants)
    if propose is None:
        return fallback
    try:
        raw = propose(question)
    except Exception:
        return fallback
    if isinstance(raw, str):
        parts = [p.strip() for p in re.split(r"[\n,;]+", raw)]
    elif isinstance(raw, (list, tuple)):
        parts = [str(p).strip() for p in raw]
    else:
        return fallback
    out: list[str] = []
    for part in parts:
        part = part.strip().strip('"').strip("'")
        if part and part not in out:
            out.append(part)
    return (out or fallback)[:max_variants]


def search_with_backoff(
    question: str,
    fetch: Callable[[str], Any],
    *,
    rows_of: Callable[[Any], list[Any]] = lambda r: list((r or {}).get("rows") or []),
    max_variants: int = 4,
) -> dict[str, Any]:
    """Try each query until one answers. Reports which query worked and what was tried.

    Returning the attempt list matters: a caller that sees zero results should be able to
    tell "the catalogue has nothing" from "we asked badly".
    """
    attempts: list[dict[str, Any]] = []
    for term in search_terms(question, max_variants=max_variants):
        try:
            result = fetch(term)
        except Exception as exc:
            attempts.append({"query": term, "rows": 0, "error": f"{type(exc).__name__}: {exc}"[:120]})
            continue
        rows = rows_of(result)
        attempts.append({"query": term, "rows": len(rows)})
        if rows:
            return {"query_used": term, "rows": rows, "attempts": attempts, "result": result}
    return {"query_used": "", "rows": [], "attempts": attempts, "result": None}
