#!/usr/bin/env python3
"""Harvest external dataset metadata into a local catalogue seed.

This intentionally downloads metadata only, not dataset payloads.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


USER_AGENT = "research-data-hub-catalogue/0.1"


def fetch_json(url: str, timeout: int = 30) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def clean_text(value: Any, limit: int = 2000) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        value = " ".join(str(x) for x in value if x is not None)
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text[:limit]


def classify_readiness(access_mode: str, size_hint: str = "") -> str:
    if access_mode in {"instant_query", "query_remote"}:
        return "instant_or_minutes"
    if access_mode == "api_live":
        return "minutes_rate_limited"
    if access_mode == "sample_probe":
        return "sample_now_full_later"
    if access_mode == "download_archive":
        return "hours_or_days"
    return "metadata_only"


def base_record(
    *,
    source: str,
    source_kind: str,
    dataset_id: str,
    title: str,
    url: str,
    description: str = "",
    tags: list[str] | None = None,
    license_name: str = "",
    access_mode: str = "reference_only",
    domain: str = "general",
    size_hint: str = "",
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "catalogue_version": "0.1",
        "harvested_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "source_kind": source_kind,
        "dataset_id": dataset_id,
        "title": clean_text(title, 300),
        "description": clean_text(description, 2500),
        "url": url,
        "tags": tags or [],
        "license": clean_text(license_name, 200),
        "domain": domain,
        "access_mode": access_mode,
        "analysis_readiness": classify_readiness(access_mode, size_hint),
        "size_hint": size_hint,
        "recommended_action": recommend_action(access_mode, title, description, tags or []),
        "raw_metadata": raw or {},
    }


def recommend_action(access_mode: str, title: str, description: str, tags: list[str]) -> str:
    text = " ".join([title, description, " ".join(tags)]).lower()
    priority_terms = [
        "crypto",
        "cryptocurrency",
        "ethereum",
        "bitcoin",
        "nft",
        "blockchain",
        "market",
        "finance",
        "financial",
        "news",
        "economic",
        "trade",
        "policy",
    ]
    if any(t in text for t in priority_terms):
        if access_mode in {"query_remote", "api_live"}:
            return "probe_query_and_cache_derived"
        return "sample_probe_high_priority"
    if access_mode == "reference_only":
        return "catalogue_only"
    return "sample_probe"


def infer_domain(text: str, tags: list[str]) -> str:
    hay = (" ".join([text] + tags)).lower()
    buckets = [
        ("crypto_finance", ["crypto", "cryptocurrency", "bitcoin", "ethereum", "nft", "blockchain", "token"]),
        ("finance_economics", ["finance", "financial", "market", "stock", "econom", "trade", "bank"]),
        ("news_media", ["news", "media", "gdelt", "journalism"]),
        ("social_web", ["twitter", "reddit", "social", "web"]),
        ("health_bio", ["health", "medical", "clinical", "genome", "biology"]),
        ("climate_geo", ["climate", "weather", "geospatial", "earth", "satellite"]),
        ("machine_learning", ["machine learning", "benchmark", "nlp", "computer vision", "language model"]),
    ]
    for domain, terms in buckets:
        if any(term in hay for term in terms):
            return domain
    return "general"


def harvest_zenodo(limit: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page_size = min(25, limit)
    url = "https://zenodo.org/api/records?" + urllib.parse.urlencode(
        {"type": "dataset", "size": page_size, "sort": "mostrecent"}
    )
    data = fetch_json(url)
    for item in data.get("hits", {}).get("hits", [])[:limit]:
        meta = item.get("metadata", {})
        tags = [str(x) for x in meta.get("keywords", [])]
        title = meta.get("title", "")
        desc = meta.get("description", "")
        records.append(
            base_record(
                source="zenodo",
                source_kind="repository",
                dataset_id=str(item.get("id", "")),
                title=title,
                description=desc,
                url=item.get("links", {}).get("html", ""),
                tags=tags,
                license_name=(meta.get("license") or {}).get("id", "") if isinstance(meta.get("license"), dict) else "",
                access_mode="sample_probe",
                domain=infer_domain(title + " " + desc, tags),
                raw=item,
            )
        )
    return records


def harvest_huggingface(limit: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    url = "https://huggingface.co/api/datasets?" + urllib.parse.urlencode({"limit": limit, "full": "true"})
    data = fetch_json(url)
    for item in data[:limit]:
        tags = [str(x) for x in item.get("tags", [])]
        dataset_id = item.get("id", "")
        title = dataset_id
        desc = item.get("description") or item.get("cardData", {}).get("description", "")
        records.append(
            base_record(
                source="huggingface",
                source_kind="ml_dataset_repository",
                dataset_id=dataset_id,
                title=title,
                description=desc,
                url=f"https://huggingface.co/datasets/{dataset_id}",
                tags=tags,
                license_name=str(item.get("cardData", {}).get("license", "")),
                access_mode="query_remote",
                domain=infer_domain(title + " " + desc, tags),
                raw=item,
            )
        )
    return records


def harvest_harvard_dataverse(limit: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    url = "https://dataverse.harvard.edu/api/search?" + urllib.parse.urlencode(
        {"q": "*", "type": "dataset", "per_page": min(100, limit), "sort": "date", "order": "desc"}
    )
    data = fetch_json(url)
    for item in data.get("data", {}).get("items", [])[:limit]:
        tags = [str(x) for x in item.get("subjects", [])]
        title = item.get("name", "")
        desc = item.get("description", "")
        records.append(
            base_record(
                source="harvard_dataverse",
                source_kind="repository",
                dataset_id=str(item.get("global_id") or item.get("id", "")),
                title=title,
                description=desc,
                url=item.get("url", ""),
                tags=tags,
                license_name="",
                access_mode="sample_probe",
                domain=infer_domain(title + " " + desc, tags),
                raw=item,
            )
        )
    return records


def harvest_aws_open_data(limit: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    url = "https://api.github.com/repos/awslabs/open-data-registry/contents/datasets"
    data = fetch_json(url)
    for item in data[:limit]:
        name = item.get("name", "")
        if not name.endswith(".yaml"):
            continue
        dataset_id = name[:-5]
        records.append(
            base_record(
                source="aws_open_data_registry",
                source_kind="cloud_open_data_registry",
                dataset_id=dataset_id,
                title=dataset_id.replace("-", " "),
                description="AWS Open Data Registry metadata entry. Fetch YAML detail before use.",
                url=item.get("html_url", ""),
                tags=["aws", "open-data"],
                license_name="varies",
                access_mode="reference_only",
                domain=infer_domain(dataset_id, ["aws", "open-data"]),
                raw=item,
            )
        )
    return records


def static_reference_records() -> list[dict[str, Any]]:
    refs = [
        {
            "source": "google_dataset_search",
            "source_kind": "dataset_search_engine",
            "dataset_id": "google_dataset_search",
            "title": "Google Dataset Search",
            "url": "https://datasetsearch.research.google.com/",
            "description": "Broad dataset search engine. No general public API; use for discovery and manual/source-specific follow-up.",
            "access_mode": "reference_only",
        },
        {
            "source": "re3data",
            "source_kind": "repository_registry",
            "dataset_id": "re3data_registry",
            "title": "Registry of Research Data Repositories",
            "url": "https://www.re3data.org/",
            "description": "Global registry of research data repositories. Use to discover trusted domain repositories.",
            "access_mode": "reference_only",
        },
        {
            "source": "bigquery_public_datasets",
            "source_kind": "cloud_query_catalogue",
            "dataset_id": "bigquery_public_datasets",
            "title": "BigQuery Public Datasets",
            "url": "https://docs.cloud.google.com/bigquery/public-data",
            "description": "Public datasets hosted in BigQuery. Best used through remote SQL and cached derived outputs.",
            "access_mode": "query_remote",
        },
        {
            "source": "kaggle",
            "source_kind": "dataset_repository",
            "dataset_id": "kaggle_datasets",
            "title": "Kaggle Datasets",
            "url": "https://www.kaggle.com/datasets",
            "description": "Large dataset repository and competition platform. Requires API credentials for systematic metadata/download.",
            "access_mode": "sample_probe",
        },
        {
            "source": "openalex",
            "source_kind": "literature_metadata",
            "dataset_id": "openalex",
            "title": "OpenAlex",
            "url": "https://openalex.org/",
            "description": "Open scholarly metadata graph. Useful for paper-to-dataset and field discovery.",
            "access_mode": "query_remote",
        },
    ]
    return [
        base_record(
            source=x["source"],
            source_kind=x["source_kind"],
            dataset_id=x["dataset_id"],
            title=x["title"],
            url=x["url"],
            description=x["description"],
            tags=[],
            access_mode=x["access_mode"],
            domain="discovery",
            raw={},
        )
        for x in refs
    ]


def write_outputs(records: list[dict[str, Any]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl = out_dir / "external_dataset_catalog_seed.jsonl"
    with jsonl.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")

    by_source: dict[str, int] = {}
    by_mode: dict[str, int] = {}
    by_readiness: dict[str, int] = {}
    by_domain: dict[str, int] = {}
    for rec in records:
        by_source[rec["source"]] = by_source.get(rec["source"], 0) + 1
        by_mode[rec["access_mode"]] = by_mode.get(rec["access_mode"], 0) + 1
        by_readiness[rec["analysis_readiness"]] = by_readiness.get(rec["analysis_readiness"], 0) + 1
        by_domain[rec["domain"]] = by_domain.get(rec["domain"], 0) + 1

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "records": len(records),
        "by_source": by_source,
        "by_access_mode": by_mode,
        "by_analysis_readiness": by_readiness,
        "by_domain": by_domain,
        "jsonl": str(jsonl),
    }
    (out_dir / "external_dataset_catalog_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    md = out_dir / "external_dataset_catalog_summary.md"
    lines = [
        "# External Dataset Catalogue Seed",
        "",
        f"Generated at: `{summary['generated_at']}`",
        f"Records: `{len(records)}`",
        "",
        "## By source",
        "",
    ]
    for k, v in sorted(by_source.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- `{k}`: `{v}`")
    lines.extend(["", "## By access mode", ""])
    for k, v in sorted(by_mode.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- `{k}`: `{v}`")
    lines.extend(["", "## By analysis readiness", ""])
    for k, v in sorted(by_readiness.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- `{k}`: `{v}`")
    lines.extend(["", "## By domain", ""])
    for k, v in sorted(by_domain.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- `{k}`: `{v}`")
    lines.extend(["", "## High-priority candidates", ""])
    high = [r for r in records if r["recommended_action"] == "sample_probe_high_priority"][:50]
    for r in high:
        lines.append(f"- `{r['source']}` | `{r['domain']}` | {r['title']} | {r['url']}")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="data_lake/dataset_catalog")
    parser.add_argument("--limit-per-source", type=int, default=100)
    args = parser.parse_args()

    harvesters = [
        ("zenodo", harvest_zenodo),
        ("huggingface", harvest_huggingface),
        ("harvard_dataverse", harvest_harvard_dataverse),
        ("aws_open_data_registry", harvest_aws_open_data),
    ]
    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for name, fn in harvesters:
        try:
            batch = fn(args.limit_per_source)
            records.extend(batch)
            print(f"{name}: {len(batch)}")
        except Exception as exc:
            errors.append({"source": name, "error": repr(exc)})
            print(f"{name}: ERROR {exc}", file=sys.stderr)
        time.sleep(0.5)
    records.extend(static_reference_records())
    if errors:
        records.append(
            base_record(
                source="harvest_errors",
                source_kind="internal_report",
                dataset_id="harvest_errors",
                title="Harvest errors",
                url="",
                description=json.dumps(errors),
                access_mode="reference_only",
                raw={"errors": errors},
            )
        )
    write_outputs(records, Path(args.out_dir))
    print(f"records_total: {len(records)}")
    print(f"out_dir: {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
