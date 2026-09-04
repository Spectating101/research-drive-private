#!/usr/bin/env python3
"""Evidence-aware retrieval over held/registered Library assets.

The primary retriever stays deterministic and explainable. Semantic retrieval may
widen a research-language query, but a Library result must still be grounded in
recorded asset metadata rather than a title-only or embedding-only similarity.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable


STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "could",
        "data",
        "dataset",
        "datasets",
        "do",
        "evidence",
        "file",
        "files",
        "find",
        "for",
        "from",
        "have",
        "i",
        "in",
        "is",
        "it",
        "library",
        "me",
        "my",
        "of",
        "on",
        "or",
        "research",
        "show",
        "that",
        "the",
        "this",
        "to",
        "used",
        "using",
        "want",
        "what",
        "where",
        "which",
        "with",
    }
)

ALIAS_GROUPS = (
    ("day", "daily"),
    ("week", "weekly"),
    ("month", "monthly"),
    ("quarter", "quarterly"),
    ("year", "yearly", "annual", "annually"),
    ("paper", "papers", "article", "articles", "literature", "scholarly"),
    ("source", "sources", "connector", "connectors", "api", "apis"),
    ("equity", "equities", "stock", "stocks"),
)
ALIASES: dict[str, frozenset[str]] = {}
for _group in ALIAS_GROUPS:
    group = frozenset(_group)
    for _term in group:
        ALIASES[_term] = group


@dataclass(frozen=True)
class FieldGroup:
    key: str
    label: str
    weight: int
    fields: tuple[str, ...]


FIELD_GROUPS = (
    FieldGroup("identity", "name", 13, ("dataset_id", "registry_id", "name", "display_name", "title", "doi")),
    FieldGroup(
        "topic",
        "topic",
        8,
        (
            "description",
            "one_line",
            "summary",
            "meaning_about",
            "recommended_use",
            "research_use",
            "keywords",
            "tags",
            "limitations",
            "domain",
        ),
    ),
    FieldGroup(
        "structure",
        "field",
        10,
        (
            "grain",
            "join_keys",
            "keys",
            "primary_key",
            "fields",
            "columns",
            "schema",
            "declared_fields",
            "declared_schema",
            "response_shape",
        ),
    ),
    FieldGroup(
        "coverage",
        "coverage",
        9,
        (
            "coverage",
            "date_range",
            "temporal_coverage",
            "geography",
            "geographies",
            "countries",
            "country",
            "market",
            "markets",
        ),
    ),
    FieldGroup(
        "source",
        "source",
        9,
        (
            "source",
            "publisher",
            "source_system",
            "source_route",
            "collect_via",
            "backend",
            "source_url",
            "provenance",
            "procurement",
        ),
    ),
    FieldGroup(
        "organization",
        "collection",
        6,
        ("partition_id", "shelf_hint", "collection", "collections", "project", "projects"),
    ),
    FieldGroup(
        "state",
        "state",
        4,
        (
            "analysis_readiness",
            "collection_status",
            "verification_state",
            "verification",
            "access_shape",
            "access_mode",
            "asset_kind",
            "object_type",
            "kind",
        ),
    ),
)


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char)).lower()
    text = re.sub(r"[_/\\|:;,.()\[\]{}]+", " ", text)
    text = re.sub(r"[–—-]+", " ", text)
    text = re.sub(r"[^a-z0-9+]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def singular(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def query_concepts(query: str) -> list[tuple[str, frozenset[str]]]:
    # A researcher who remembers a schema identifier such as ``country_iso3``
    # is not issuing two vague topic terms. Preserve the identifier as the
    # visible match term while also carrying its human-tokenized form so it
    # matches the normalized evidence document below.
    raw = str(query or "").strip().lower()
    if "_" in raw and re.fullmatch(r"[a-z0-9_]+", raw):
        normalized = normalize(raw)
        return [(raw, frozenset({raw, normalized}))]

    seen: set[tuple[str, ...]] = set()
    concepts: list[tuple[str, frozenset[str]]] = []
    for token in normalize(query).split():
        if token in STOPWORDS or (len(token) < 2 and not re.fullmatch(r"\d{4}", token)):
            continue
        root = singular(token)
        variants = {token, root}
        for candidate in (token, root):
            variants.update(ALIASES.get(candidate, ()))
        frozen = frozenset(variants)
        key = tuple(sorted(frozen))
        if key in seen:
            continue
        seen.add(key)
        concepts.append((token, frozen))
    return concepts


def flatten(value: Any, *, depth: int = 0, limit: int = 80) -> list[str]:
    if value is None or depth > 4 or limit <= 0:
        return []
    if isinstance(value, (str, int, float, bool)):
        text = str(value).strip()
        return [text] if text else []
    if isinstance(value, dict):
        out: list[str] = []
        for key, item in value.items():
            if len(out) >= limit:
                break
            out.append(str(key))
            out.extend(flatten(item, depth=depth + 1, limit=limit - len(out)))
        return out[:limit]
    if isinstance(value, (list, tuple, set)):
        out = []
        for item in value:
            if len(out) >= limit:
                break
            out.extend(flatten(item, depth=depth + 1, limit=limit - len(out)))
        return out[:limit]
    return []


def field_values(row: dict[str, Any], fields: Iterable[str]) -> list[str]:
    out: list[str] = []
    for field in fields:
        out.extend(flatten(row.get(field), limit=max(0, 80 - len(out))))
        if len(out) >= 80:
            break
    return out[:80]


def _concept_matches(variants: frozenset[str], blob: str) -> bool:
    tokens = set(blob.split())
    return any(variant in tokens or variant in blob for variant in variants)


def _first_matching_value(values: list[str], variants: frozenset[str]) -> str:
    for value in values:
        text = normalize(value)
        if _concept_matches(variants, text):
            return str(value).strip()
    return str(values[0] if values else "").strip()


def registry_search_document(row: dict[str, Any]) -> str:
    """Bounded text used by semantic widening; includes the same evidence dimensions as lexical retrieval."""
    pieces: list[str] = []
    for group in FIELD_GROUPS:
        pieces.extend(field_values(row, group.fields))
    return " ".join(pieces[:240])


def score_registry_asset(row: dict[str, Any], query: str) -> dict[str, Any]:
    normalized_query = normalize(query)
    concepts = query_concepts(query)
    if not normalized_query or not concepts:
        return {
            "score": 0,
            "coverage": 0.0,
            "confidence": "none",
            "matched_terms": [],
            "match_evidence": [],
            "phrase_match": False,
        }

    matched_terms: set[str] = set()
    evidence: list[dict[str, Any]] = []
    score = 0
    phrase_match = False

    for group in FIELD_GROUPS:
        values = field_values(row, group.fields)
        if not values:
            continue
        blob = normalize(" ".join(values))
        matched = [(token, variants) for token, variants in concepts if _concept_matches(variants, blob)]
        if not matched:
            continue
        matched_terms.update(token for token, _variants in matched)
        score += group.weight * len(matched)
        if len(normalized_query) >= 3 and normalized_query in blob:
            phrase_match = True
            score += group.weight * 4 + (45 if group.key == "identity" else 20)
        if len(matched) == len(concepts):
            score += group.weight * 2

        token, variants = matched[0]
        value = re.sub(r"\s+", " ", _first_matching_value(values, variants)).strip()
        if len(value) > 96:
            value = value[:93] + "…"
        evidence.append(
            {
                "kind": group.key,
                "field_group": group.label,
                "value": value,
                "terms": [token],
                "weight": group.weight,
            }
        )

    coverage = len(matched_terms) / len(concepts)
    score += round(coverage * 50)
    # Lexical registry retrieval is an evidence-producing ranker, not the final
    # federation relevance gate. Preserve partial exact evidence for short
    # research queries so callers can compare one-of-N matches and inspect richer
    # metadata downstream. For longer compound queries, however, one incidental
    # word is too weak to constitute a candidate: require at least one third of
    # the concepts unless the complete query phrase itself matched. This keeps
    # useful one-of-three evidence while rejecting one-of-four noise such as a
    # generic cadence term embedded in an otherwise unrelated request.
    if len(concepts) >= 4 and coverage < (1 / 3) and not phrase_match:
        score = 0

    confidence = "none"
    if score > 0:
        if phrase_match or (coverage >= 0.8 and score >= 70):
            confidence = "high"
        elif coverage >= 0.5 or score >= 45:
            confidence = "medium"
        else:
            confidence = "low"

    evidence.sort(key=lambda item: (-int(item["weight"]), item["field_group"]))
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in evidence:
        if item["kind"] in seen:
            continue
        seen.add(item["kind"])
        clean = dict(item)
        clean.pop("weight", None)
        unique.append(clean)
        if len(unique) >= 4:
            break

    # Preserve the researcher's query order in the receipt. A set/sort is fine
    # for scoring, but reordering "earthquake seismic activity" into alphabetical
    # order makes the explanation harder to compare with the original request.
    ordered_matched_terms = [token for token, _variants in concepts if token in matched_terms]

    return {
        "score": int(score),
        "coverage": round(float(coverage), 4),
        "confidence": confidence,
        "matched_terms": ordered_matched_terms,
        "match_evidence": unique,
        "phrase_match": bool(phrase_match),
    }


def rank_registry_assets(rows: Iterable[dict[str, Any]], query: str, *, limit: int = 50) -> list[dict[str, Any]]:
    q = str(query or "").strip()
    if not q:
        return [dict(row) for row in list(rows)[: max(1, limit)]]

    ranked: list[tuple[int, float, str, dict[str, Any]]] = []
    concepts_total = len(query_concepts(q))
    for row in rows:
        match = score_registry_asset(row, q)
        if not match["score"]:
            continue
        out = dict(row)
        out["match_score"] = match["score"]
        out["match_coverage"] = match["coverage"]
        out["match_confidence"] = match["confidence"]
        out["match_terms"] = list(match["matched_terms"])
        out["match_terms_total"] = concepts_total
        out["match_evidence"] = list(match["match_evidence"])
        out["match_phrase"] = match["phrase_match"]
        ranked.append(
            (
                int(match["score"]),
                float(match["coverage"]),
                str(row.get("dataset_id") or ""),
                out,
            )
        )
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [row for _score, _coverage, _id, row in ranked[: max(1, limit)]]
