#!/usr/bin/env python3
"""Locally enrich scored GDELT GKG URL queues with page metadata.

This is the lightweight companion to score_gdelt_gkg_asia.py. It fetches only
the prioritized URL queue, extracts titles/snippets, and writes local evidence
files. It is meant for pilots and quality checks before any Drive-scale run.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


REPO = Path(__file__).resolve().parents[2]
DEFAULT_PROCESSED_ROOT = REPO / "data_lake/news_shock_taxonomy/processed"
USER_AGENT = "Sharpe-Renaissance asia-news-shock-url-enrichment/1.0 research-contact=local@example.invalid"

OUT_COLUMNS = [
    "fetched_at",
    "status",
    "http_status",
    "error",
    "country_iso3",
    "source_domain",
    "source_tier",
    "primary_country_confidence",
    "market_relevance_score",
    "collection_decision",
    "url",
    "final_url",
    "content_type",
    "bytes_read",
    "title",
    "og_title",
    "description",
    "h1",
    "text_excerpt",
    "content_sha256",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=None, help="url_enrichment_queue.csv.gz. Defaults to latest processed queue.")
    parser.add_argument("--out-dir", type=Path, default=None, help="Output directory. Defaults to queue parent.")
    parser.add_argument("--decisions", default="enrich_high_priority", help="Comma-separated collection_decision values.")
    parser.add_argument("--max-urls", type=int, default=0, help="0 means all selected URLs.")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--max-bytes", type=int, default=1_000_000)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--per-domain-delay", type=float, default=3.0)
    return parser.parse_args()


def latest_queue() -> Path:
    candidates = sorted(DEFAULT_PROCESSED_ROOT.glob("*/url_enrichment_queue.csv.gz"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"no url_enrichment_queue.csv.gz files under {DEFAULT_PROCESSED_ROOT}")
    return candidates[-1]


def bare_domain(value: str) -> str:
    host = urlsplit(value).netloc if "://" in value else value
    host = (host or "").lower().strip().split("@")[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host[4:] if host.startswith("www.") else host


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def first_regex(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I | re.S)
        if match:
            return clean_text(match.group(1))
    return ""


def extract_page(raw: bytes, final_url: str, content_type: str) -> dict[str, str]:
    encoding = "utf-8"
    match = re.search(r"charset=([A-Za-z0-9._-]+)", content_type or "", flags=re.I)
    if match:
        encoding = match.group(1)
    text = raw.decode(encoding, errors="ignore")
    title = first_regex(text, [r"<title[^>]*>(.*?)</title>"])
    og_title = first_regex(
        text,
        [
            r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)[\"']",
            r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+property=[\"']og:title[\"']",
        ],
    )
    description = first_regex(
        text,
        [
            r"<meta[^>]+name=[\"']description[\"'][^>]+content=[\"']([^\"']+)[\"']",
            r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+name=[\"']description[\"']",
            r"<meta[^>]+property=[\"']og:description[\"'][^>]+content=[\"']([^\"']+)[\"']",
            r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+property=[\"']og:description[\"']",
        ],
    )
    h1 = first_regex(text, [r"<h1[^>]*>(.*?)</h1>"])
    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", text, flags=re.I | re.S)
    excerpt_parts = [clean_text(item) for item in paragraphs]
    excerpt_parts = [item for item in excerpt_parts if len(item) >= 40]
    text_excerpt = " ".join(excerpt_parts)[:1200]
    return {
        "final_url": final_url,
        "title": title,
        "og_title": og_title,
        "description": description,
        "h1": h1,
        "text_excerpt": text_excerpt,
    }


def fetch_url(url: str, timeout: int, max_bytes: int) -> tuple[int, str, str, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content_type = resp.headers.get("content-type", "")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = resp.read(min(65536, max_bytes - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total >= max_bytes:
                break
        return int(resp.status), resp.geturl(), content_type, b"".join(chunks)


def load_queue(path: Path, decisions: set[str], max_urls: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        seen: set[str] = set()
        for row in reader:
            if row.get("collection_decision") not in decisions:
                continue
            url = row.get("document_identifier") or row.get("canonical_url") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            rows.append(row)
            if max_urls > 0 and len(rows) >= max_urls:
                break
    return rows


def main() -> int:
    args = parse_args()
    queue_path = args.queue or latest_queue()
    out_dir = args.out_dir or queue_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    decisions = {item.strip() for item in args.decisions.split(",") if item.strip()}
    seeds = load_queue(queue_path, decisions, args.max_urls)

    stem = "url_enrichment_" + "_".join(sorted(decisions)).replace("/", "_")
    csv_path = out_dir / f"{stem}.csv.gz"
    jsonl_path = out_dir / f"{stem}.jsonl.gz"
    summary_path = out_dir / f"{stem}_summary.json"

    last_domain_at: dict[str, float] = {}
    status_counts: dict[str, int] = {}
    rows_written = 0

    with gzip.open(csv_path, "wt", encoding="utf-8", newline="") as csv_fh, gzip.open(jsonl_path, "wt", encoding="utf-8") as jsonl_fh:
        writer = csv.DictWriter(csv_fh, fieldnames=OUT_COLUMNS)
        writer.writeheader()
        for seed in seeds:
            url = seed.get("document_identifier") or seed.get("canonical_url") or ""
            domain = bare_domain(url)
            now = time.monotonic()
            elapsed = now - last_domain_at.get(domain, 0.0)
            if elapsed < args.per_domain_delay:
                time.sleep(args.per_domain_delay - elapsed)
            if args.sleep > 0:
                time.sleep(args.sleep)
            last_domain_at[domain] = time.monotonic()

            row: dict[str, Any] = {
                "fetched_at": datetime.now(UTC).isoformat(),
                "status": "error",
                "http_status": "",
                "error": "",
                "country_iso3": seed.get("country_iso3", ""),
                "source_domain": seed.get("source_domain", ""),
                "source_tier": seed.get("source_tier", ""),
                "primary_country_confidence": seed.get("primary_country_confidence", ""),
                "market_relevance_score": seed.get("market_relevance_score", ""),
                "collection_decision": seed.get("collection_decision", ""),
                "url": url,
                "final_url": "",
                "content_type": "",
                "bytes_read": 0,
                "title": "",
                "og_title": "",
                "description": "",
                "h1": "",
                "text_excerpt": "",
                "content_sha256": "",
            }
            try:
                http_status, final_url, content_type, raw = fetch_url(url, args.timeout, args.max_bytes)
                row.update(
                    {
                        "status": "downloaded",
                        "http_status": http_status,
                        "final_url": final_url,
                        "content_type": content_type,
                        "bytes_read": len(raw),
                        "content_sha256": hashlib.sha256(raw).hexdigest(),
                    }
                )
                if "html" in content_type.lower() or raw.lstrip().startswith((b"<!DOCTYPE", b"<html", b"<HTML")):
                    row.update(extract_page(raw, final_url, content_type))
                else:
                    row["status"] = "non_html"
            except urllib.error.HTTPError as exc:
                row["status"] = "http_error"
                row["http_status"] = exc.code
                row["error"] = str(exc)[:300]
            except Exception as exc:  # pragma: no cover - network dependent
                row["status"] = "error"
                row["error"] = f"{type(exc).__name__}: {exc}"[:300]

            status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
            writer.writerow({key: row.get(key, "") for key in OUT_COLUMNS})
            jsonl_fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            rows_written += 1
            print(json.dumps({"url": url, "status": row["status"], "http_status": row["http_status"], "title": row["og_title"] or row["title"]}, ensure_ascii=False), flush=True)

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "queue": str(queue_path),
        "decisions": sorted(decisions),
        "selected_urls": len(seeds),
        "rows_written": rows_written,
        "status_counts": status_counts,
        "outputs": {
            "csv": str(csv_path),
            "jsonl": str(jsonl_path),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
