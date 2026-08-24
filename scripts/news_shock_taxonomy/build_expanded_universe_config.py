#!/usr/bin/env python3
"""Merge Asia + global adjunct GDELT universe configs into expanded collection config."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
ASIA = REPO / "config/news_shock_asia_universe.json"
GLOBAL = REPO / "config/news_shock_global_adjunct_universe.json"
OUT = REPO / "config/news_shock_expanded_universe.json"


def _merge_list_unique(base: list[str], extra: list[str]) -> list[str]:
    seen = set(base)
    for item in extra:
        if item not in seen:
            base.append(item)
            seen.add(item)
    return base


def merge_configs(*paths: Path) -> dict[str, Any]:
    docs = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    merged: dict[str, Any] = dict(docs[0])
    merged["description"] = (
        "Asia-Pacific + global financial-center GDELT universe (merged). "
        "Use for expanded news/crypto collections; Asia-only config remains for legacy panels."
    )
    seen_iso3 = {c["iso3"] for c in merged.get("countries", [])}
    for doc in docs[1:]:
        for country in doc.get("countries", []):
            if country["iso3"] not in seen_iso3:
                merged.setdefault("countries", []).append(country)
                seen_iso3.add(country["iso3"])
        for key in ("include_theme_substrings", "exclude_text_substrings"):
            merged[key] = _merge_list_unique(list(merged.get(key) or []), list(doc.get(key) or []))
        for shock, terms in (doc.get("shock_theme_map") or {}).items():
            merged.setdefault("shock_theme_map", {}).setdefault(shock, [])
            merged["shock_theme_map"][shock] = _merge_list_unique(list(merged["shock_theme_map"][shock]), list(terms))
        for tier, domains in (doc.get("source_domain_tiers") or {}).items():
            merged.setdefault("source_domain_tiers", {}).setdefault(tier, [])
            merged["source_domain_tiers"][tier] = _merge_list_unique(list(merged["source_domain_tiers"][tier]), list(domains))
    merged["source_configs"] = [str(p.relative_to(REPO)) for p in paths]
    return merged


def main() -> None:
    payload = merge_configs(ASIA, GLOBAL)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(OUT), "countries": len(payload.get("countries") or [])}, indent=2))


if __name__ == "__main__":
    main()
