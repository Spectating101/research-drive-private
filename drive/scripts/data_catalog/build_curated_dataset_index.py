#!/usr/bin/env python3
"""Build a curated/searchable dataset index from raw harvested metadata.

Raw metadata can be huge and noisy. This script promotes records into tiers and
writes a user-facing JSONL plus summary. It does not delete raw metadata.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

POSITIVE_TERMS = {
    "crypto": 8, "cryptocurrency": 8, "bitcoin": 8, "ethereum": 8, "blockchain": 8, "nft": 8, "stablecoin": 8, "token": 5,
    "finance": 7, "financial": 7, "market": 6, "stock": 6, "trading": 6, "asset": 4, "price": 5, "volatility": 6,
    "economic": 6, "economics": 6, "macro": 6, "inflation": 6, "monetary": 6, "interest rate": 6, "exchange rate": 6,
    "news": 6, "media": 5, "sentiment": 7, "attention": 7, "search": 5, "trend": 5, "social": 5, "twitter": 6, "reddit": 6,
    "consumer": 5, "brand": 5, "survey": 3, "public opinion": 5, "behavior": 4, "adoption": 4,
    "labor": 5, "job": 5, "employment": 5, "platform": 4,
    "policy": 5, "trade": 5, "geopolitical": 5, "election": 4,
    "dataset": 1, "replication": 3, "panel": 5, "time series": 6,
}

NEGATIVE_TERMS = {
    "supplementary": -2, "supplemental": -2, "classroom": -5, "homework": -5, "teaching": -4, "lecture": -4,
    "protein": -4, "genome": -4, "cell": -3, "assay": -4, "microscopy": -4, "chemistry": -3,
    "poem": -5, "translation exercise": -5, "yolo model": -2,
}

PRIORITY_DOMAINS = {"crypto_finance", "finance_economics", "news_media", "social_web"}
PRIORITY_SOURCES = {"bigquery_public_datasets", "openalex", "aws_open_data_registry"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def iter_jsonl(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    mode = "rt" if path.suffix == ".gz" else "r"
    with opener(path, mode, encoding="utf-8", errors="replace") as f:
        while True:
            try:
                line = f.readline()
            except EOFError:
                return
            if not line:
                return
            if line.strip():
                try:
                    yield json.loads(line)
                except Exception:
                    continue


def normalize_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        v = " ".join(str(x) for x in v)
    return re.sub(r"\s+", " ", str(v)).strip()


def text_blob(rec: dict[str, Any]) -> str:
    return " ".join(normalize_text(rec.get(k, "")) for k in ["title", "description", "tags", "domain", "source"]).lower()


def score_record(rec: dict[str, Any]) -> tuple[int, list[str]]:
    text = text_blob(rec)
    score = 0
    reasons: list[str] = []
    domain = rec.get("domain", "")
    source = rec.get("source", "")
    access_mode = rec.get("access_mode", "")
    readiness = rec.get("analysis_readiness", "")

    if domain in PRIORITY_DOMAINS:
        score += 12
        reasons.append(f"priority_domain:{domain}")
    if source in PRIORITY_SOURCES:
        score += 8
        reasons.append(f"priority_source:{source}")
    if access_mode == "query_remote":
        score += 8
        reasons.append("queryable")
    elif access_mode == "sample_probe":
        score += 3
        reasons.append("sample_probe")
    elif access_mode == "reference_only":
        score -= 2
    if "instant" in str(readiness):
        score += 5
        reasons.append("instant_or_minutes")

    for term, weight in POSITIVE_TERMS.items():
        if term in text:
            score += weight
            if weight >= 5:
                reasons.append(f"term:{term}")
    for term, weight in NEGATIVE_TERMS.items():
        if term in text:
            score += weight
            reasons.append(f"downrank:{term}")

    title = normalize_text(rec.get("title", ""))
    desc = normalize_text(rec.get("description", ""))
    if len(title) < 8:
        score -= 5
        reasons.append("weak_title")
    if len(desc) < 40:
        score -= 3
        reasons.append("weak_description")
    if rec.get("url"):
        score += 1
    return score, reasons[:20]


def tier_for(score: int) -> str:
    if score >= 35:
        return "tier_5_must_integrate"
    if score >= 25:
        return "tier_4_priority_probe"
    if score >= 15:
        return "tier_3_research_candidate"
    if score >= 8:
        return "tier_2_searchable"
    if score >= 1:
        return "tier_1_catalogue_visible"
    return "tier_0_raw_only"


def stable_key(rec: dict[str, Any]) -> str:
    for k in ["url", "dataset_id"]:
        v = normalize_text(rec.get(k, "")).lower()
        if v:
            return f"{rec.get('source', '')}::{v}"
    return json.dumps(rec, sort_keys=True)[:200]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", action="append", default=[])
    ap.add_argument("--input-dir", action="append", default=[])
    ap.add_argument("--out-dir", default="data_lake/dataset_catalog/curated")
    ap.add_argument("--min-tier", default="tier_1_catalogue_visible")
    args = ap.parse_args()

    paths: list[Path] = [Path(x) for x in args.input]
    for d in args.input_dir:
        paths.extend(sorted(Path(d).glob("*.jsonl")))
        paths.extend(sorted(Path(d).glob("*.jsonl.gz")))
    tier_order = ["tier_0_raw_only", "tier_1_catalogue_visible", "tier_2_searchable", "tier_3_research_candidate", "tier_4_priority_probe", "tier_5_must_integrate"]
    min_i = tier_order.index(args.min_tier)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "curated_dataset_index.jsonl"
    seen = set()
    counts = Counter()
    kept = 0
    scanned = 0
    examples = []
    with out_path.open("w", encoding="utf-8") as out:
        for path in paths:
            if not path.exists():
                continue
            for rec in iter_jsonl(path):
                scanned += 1
                key = stable_key(rec)
                if key in seen:
                    counts["duplicate"] += 1
                    continue
                seen.add(key)
                score, reasons = score_record(rec)
                tier = tier_for(score)
                counts[tier] += 1
                counts[f"source:{rec.get('source', 'unknown')}"] += 1
                counts[f"domain:{rec.get('domain', 'unknown')}"] += 1
                if tier_order.index(tier) < min_i:
                    continue
                kept += 1
                promoted = {
                    "curated_at": now(),
                    "promotion_score": score,
                    "promotion_tier": tier,
                    "promotion_reasons": reasons,
                    "source": rec.get("source"),
                    "source_kind": rec.get("source_kind"),
                    "dataset_id": rec.get("dataset_id"),
                    "title": rec.get("title"),
                    "description": rec.get("description"),
                    "url": rec.get("url"),
                    "tags": rec.get("tags", []),
                    "domain": rec.get("domain"),
                    "access_mode": rec.get("access_mode"),
                    "analysis_readiness": rec.get("analysis_readiness"),
                }
                out.write(json.dumps(promoted, ensure_ascii=False, sort_keys=True) + "\n")
                if len(examples) < 100 and tier in {"tier_4_priority_probe", "tier_5_must_integrate"}:
                    examples.append(promoted)
    summary = {
        "generated_at": now(),
        "inputs": [str(p) for p in paths],
        "scanned": scanned,
        "kept": kept,
        "min_tier": args.min_tier,
        "counts": dict(counts),
        "output": str(out_path),
        "priority_examples": examples,
    }
    (out_dir / "curated_dataset_index_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    md = ["# Curated Dataset Index", "", f"Generated: `{summary['generated_at']}`", f"Scanned: `{scanned}`", f"Kept: `{kept}`", "", "## Tier counts", ""]
    for tier in tier_order:
        md.append(f"- `{tier}`: `{counts[tier]}`")
    md.extend(["", "## Priority examples", ""])
    for ex in examples[:50]:
        md.append(
            f"- `{ex['promotion_tier']}` `{ex['promotion_score']}` | "
            f"`{ex['source']}` | `{ex['domain']}` | {ex['title']} | {ex.get('url') or ''}"
        )
    (out_dir / "curated_dataset_index_summary.md").write_text("\n".join(md)+"\n", encoding="utf-8")
    print(json.dumps({"scanned": scanned, "kept": kept, "output": str(out_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
