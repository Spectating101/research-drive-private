#!/usr/bin/env python3
"""Requirement vocabulary derived from the registry, not hardcoded world knowledge.

The previous drafter carried a fixed table of six geographies, four units and
four field terms.  Measured against realistic questions for this faculty, six of
ten drafted nothing at all -- including their own declared domains (Korea,
Indonesia, NFT).  An undrafted dimension becomes ``unspecified``, which means the
assessment never checks it, so a question about Korea could return ``covered``
while ignoring Korea entirely.  That is a silent false positive, and it is worse
than the false negative it hides behind.

This module replaces that table with vocabulary read from the corpus itself:

* ``entity_fields`` and ``grain`` supply real observation units;
* ``tags`` and ``source_system`` supply domain/event terms;
* observed ISO3 values (profiled from stored files) supply the geography universe;
* a small static ISO3 reference resolves names and regions.

Deliberately deterministic and dependency-free.  No model call, no network, no
third-party API -- which also keeps research questions inside the institution
rather than sending them to an external provider.  Vocabulary grows with the
corpus instead of requiring a code change per country.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# Published ISO-3166 reference data (name -> alpha-3) plus the coarse regions the
# assessment needs.  Static reference material, not inferred knowledge.
_ISO3: dict[str, str] = {
    "taiwan": "TWN", "japan": "JPN", "china": "CHN", "hong kong": "HKG",
    "korea": "KOR", "south korea": "KOR", "singapore": "SGP", "malaysia": "MYS",
    "indonesia": "IDN", "india": "IND", "thailand": "THA", "vietnam": "VNM",
    "philippines": "PHL", "australia": "AUS", "new zealand": "NZL",
    "united states": "USA", "usa": "USA", "us": "USA", "united kingdom": "GBR",
    "germany": "DEU", "france": "FRA", "canada": "CAN", "brazil": "BRA",
}
_DEMONYM: dict[str, str] = {
    "taiwanese": "TWN", "japanese": "JPN", "chinese": "CHN", "korean": "KOR",
    "singaporean": "SGP", "malaysian": "MYS", "indonesian": "IDN", "indian": "IND",
    "thai": "THA", "vietnamese": "VNM", "filipino": "PHL", "australian": "AUS",
    "american": "USA", "british": "GBR", "german": "DEU", "french": "FRA",
}
_REGIONS: dict[str, set[str]] = {
    "asia": {"TWN", "JPN", "CHN", "HKG", "KOR", "SGP", "MYS", "IDN", "IND",
             "THA", "VNM", "PHL"},
    "east asia": {"TWN", "JPN", "CHN", "HKG", "KOR"},
    "southeast asia": {"SGP", "MYS", "IDN", "THA", "VNM", "PHL"},
    "asia pacific": {"TWN", "JPN", "CHN", "HKG", "KOR", "SGP", "MYS", "IDN",
                     "IND", "THA", "VNM", "PHL", "AUS", "NZL"},
    "apac": {"TWN", "JPN", "CHN", "HKG", "KOR", "SGP", "MYS", "IDN", "IND",
             "THA", "VNM", "PHL", "AUS", "NZL"},
}

# Frequency is a genuinely closed class -- these are the only cadences the
# registry expresses -- so matching them literally is parsing, not world knowledge.
_FREQUENCY = {
    "daily": "daily", "weekly": "weekly", "monthly": "monthly",
    "quarterly": "quarterly", "annual": "annual", "annually": "annual",
    "yearly": "annual", "intraday": "intraday",
}

# Ingestion artefacts describe how a file arrived, not what a row represents.
_ARTEFACT_GRAINS = {
    "procured_snapshot", "scrape_snapshot", "catalog_harvest", "run_snapshot",
    "dataset_record", "instrument_snapshot", "project_snapshot",
}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", str(text or "").lower()))


def build_vocabulary(datasets: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Derive the drafting vocabulary from registry rows."""
    units: set[str] = set()
    entities: set[str] = set()
    fields: set[str] = set()
    domains: set[str] = set()
    geo_codes: set[str] = set()

    for row in datasets or []:
        if not isinstance(row, dict):
            continue
        grain = str(row.get("grain") or "").strip()
        if grain and grain not in _ARTEFACT_GRAINS:
            units.add(grain)
        for field in row.get("entity_fields") or []:
            entities.add(str(field).strip())
        for tag in row.get("tags") or []:
            domains.add(str(tag).strip().lower())
        # Observed coverage carries the real geography universe.
        coverage = row.get("coverage_metadata")
        if isinstance(coverage, dict):
            claim = coverage.get("universe/geography") or coverage.get("geography")
            if isinstance(claim, dict):
                claim = claim.get("value")
            for value in (claim if isinstance(claim, list) else [claim]):
                token = str(value or "").strip().upper()
                if re.fullmatch(r"[A-Z]{3}", token):
                    geo_codes.add(token)
            observed_fields = coverage.get("fields")
            if isinstance(observed_fields, dict):
                observed_fields = observed_fields.get("value")
            for name in (observed_fields or []):
                if isinstance(name, str) and name.strip():
                    fields.add(name.strip())
    return {"units": units, "entities": entities, "domains": domains,
            "geographies": geo_codes, "fields": fields}


def resolve_geography(question: str, vocabulary: dict[str, Any] | None = None) -> list[str] | None:
    """Resolve every geography named in the question to ISO3 codes.

    Unlike the previous table, this does not stop at the first match: a question
    naming Taiwan *and* Japan must constrain on both, otherwise the second
    constraint is silently discarded.
    """
    text = str(question or "").lower()
    found: set[str] = set()
    for phrase, code in sorted(_ISO3.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{re.escape(phrase)}\b", text):
            found.add(code)
    for demonym, code in _DEMONYM.items():
        if re.search(rf"\b{re.escape(demonym)}\b", text):
            found.add(code)
    for region, codes in _REGIONS.items():
        if re.search(rf"\b{re.escape(region)}\b", text):
            known = vocabulary.get("geographies") if vocabulary else None
            # Constrain a region to what the corpus actually holds when known.
            found |= (codes & known) if known else codes
    return sorted(found) or None


def resolve_unit(question: str, vocabulary: dict[str, Any] | None = None) -> str | None:
    """Match an observation unit against units the registry actually uses.

    Matching runs on the original text -- normalising separators to ``_`` first
    would destroy the word boundaries the entity-cadence patterns rely on, since
    ``_`` is itself a word character (``\\bfirm`` cannot match inside
    ``taiwan_firm_day``).
    """
    raw = str(question or "").lower()
    joined = re.sub(r"[ \-]+", "_", raw)

    units = sorted((vocabulary or {}).get("units") or [], key=len, reverse=True)
    for unit in units:
        if unit.lower() in joined:
            return unit

    # entity x cadence, e.g. "issuer quarter" -> issuer_quarter
    entities = sorted((vocabulary or {}).get("entities") or [], key=len, reverse=True)
    cadences = ("day", "week", "month", "quarter", "year")
    for entity in entities:
        base = entity.lower().replace("_id", "").replace("_iso3", "")
        if base and re.search(rf"(?:^|[^a-z0-9]){re.escape(base)}(?:[^a-z0-9]|$)", raw):
            for cadence in cadences:
                if re.search(rf"(?:^|[^a-z0-9]){cadence}(?:[^a-z0-9]|$)", raw):
                    return f"{base}_{cadence}"

    for base in ("firm", "issuer", "exchange", "country", "ticker", "security",
                 "transaction", "household", "fund", "instrument"):
        hit = re.search(rf"(?:^|[^a-z0-9]){base}[ _-]?({'|'.join(cadences)})(?:[^a-z0-9]|$)", raw)
        if hit:
            return f"{base}_{hit.group(1)}"
    return None


# Measures a finance question names, mapped to the canonical field token the
# registry uses. Kept deliberately small: anything richer should come from
# observed column names in the corpus rather than a hand-maintained list.
_MEASURES = (
    (r"returns?", "return"),
    (r"volumes?", "volume"),
    (r"market[ _-]?cap(?:italisation|italization)?", "market_cap"),
    (r"prices?", "price"),
)


def resolve_fields(question: str, vocabulary: dict[str, Any] | None = None) -> list[str] | None:
    """Resolve requested measures, preferring column names the corpus really has."""
    raw = str(question or "").lower()
    found: list[str] = []
    for observed in sorted((vocabulary or {}).get("fields") or [], key=len, reverse=True):
        token = str(observed).lower()
        if len(token) > 3 and re.search(rf"(?:^|[^a-z0-9]){re.escape(token)}(?:[^a-z0-9]|$)", raw):
            found.append(str(observed))
    for pattern, canonical in _MEASURES:
        if re.search(rf"(?:^|[^a-z0-9]){pattern}(?:[^a-z0-9]|$)", raw) and canonical not in found:
            found.append(canonical)
    return found or None


def resolve_frequency(question: str) -> str | None:
    text = str(question or "").lower()
    for word, value in _FREQUENCY.items():
        if re.search(rf"\b{word}\b", text):
            return value
    return None


def resolve_time_range(question: str) -> dict[str, str] | None:
    text = str(question or "")
    span = re.search(r"\b((?:19|20)\d{2})\s*(?:-|–|—|to|through|until)\s*((?:19|20)\d{2})\b", text)
    if span:
        return {"start": span.group(1), "end": span.group(2)}
    since = re.search(r"\b(?:since|from|after)\s+((?:19|20)\d{2})\b", text, flags=re.IGNORECASE)
    if since:
        return {"start": since.group(1), "end": None}
    return None


# Corporate/market event types. A bounded, standard finance taxonomy -- reference
# data like the ISO3 table, not an open-ended vocabulary. Corpus tags extend it;
# they do not replace it, because tags describe provenance ("gdelt", "sec")
# rather than the event a researcher asks about ("earnings", "de-peg").
_EVENTS = (
    (r"de-?pegs?|depegging", "stablecoin_depeg"),
    (r"earnings?", "earnings"),
    (r"filings?", "filing"),
    (r"dividends?", "dividend"),
    (r"mergers?(?:\s+and\s+acquisitions)?|m&a|acquisitions?", "merger"),
    (r"ipos?|initial\s+public\s+offerings?", "ipo"),
    (r"de-?listings?", "delisting"),
    (r"stock\s+splits?", "stock_split"),
    (r"buy-?backs?|share\s+repurchases?", "buyback"),
    (r"governance\s+disclosures?|board\s+composition", "governance_disclosure"),
    (r"news\s+shocks?", "news_shock"),
    (r"earthquakes?", "earthquake"),
    (r"wash\s+trading", "wash_trading"),
)


def resolve_domains(question: str, vocabulary: dict[str, Any] | None = None) -> list[str] | None:
    """Resolve event/topic terms from the standard taxonomy plus corpus tags.

    Every match is collected rather than stopping at the first: a question about
    earnings *and* dividends constrains on both.
    """
    raw = str(question or "").lower()
    hits: set[str] = set()
    for pattern, canonical in _EVENTS:
        if re.search(rf"(?:^|[^a-z0-9]){pattern}(?:[^a-z0-9]|$)", raw):
            hits.add(canonical)
    toks = _tokens(question)
    for domain in (vocabulary or {}).get("domains") or set():
        if domain and (domain in toks or domain.replace("-", "_") in toks):
            hits.add(domain)
    return sorted(hits) or None
