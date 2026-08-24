#!/usr/bin/env python3
"""Drive-first URL enrichment for the news shock taxonomy dataset.

This consumes the GDELT DOC normalized headline/URL CSVs created by
backfill_gdelt_doc_headlines_drive.py, fetches article pages politely, and
stores an extracted metadata/evidence layer on Google Drive.

The extraction is intentionally modeled after the sibling Oversight content
extractor, but runs standalone and Drive-first instead of requiring Redis,
Docker, or the full Oversight service stack.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup


DEFAULT_DRIVE_ROOT = "gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/news_shock_taxonomy"
DEFAULT_STAGE_ROOT = Path("/tmp/sharpe_news_shock_url_enrichment")
REPO = Path(__file__).resolve().parents[2]
NORMALIZED_PREFIX = "normalized/gdelt_doc_headlines"
ENRICHED_PREFIX = "enriched/url_pages/by_country_month"
FAILURE_PREFIX = "enriched/url_pages_failures/by_country_month"
USER_AGENT = (
    "Sharpe-Renaissance news-shock-taxonomy-url-enrichment/1.0 "
    "research-contact=local@example.invalid"
)
HIGH_TRUST_DOMAINS = {
    "sec.gov",
    "fda.gov",
    "ftc.gov",
    "justice.gov",
    "europa.eu",
    "oecd.org",
    "imf.org",
    "worldbank.org",
    "bis.org",
    "adb.org",
}
TRUSTED_JOURNALISM_DOMAINS = {
    "apnews.com",
    "axios.com",
    "bbc.com",
    "bloomberg.com",
    "economist.com",
    "ft.com",
    "nikkei.com",
    "npr.org",
    "nytimes.com",
    "politico.com",
    "reuters.com",
    "theguardian.com",
    "washingtonpost.com",
    "wsj.com",
}
SOCIAL_DOMAINS = {
    "reddit.com",
    "linkedin.com",
    "x.com",
    "twitter.com",
    "facebook.com",
    "youtube.com",
}


@dataclass
class UrlSeed:
    url: str
    country_iso3: str
    country_name: str
    year_month: str
    first_seen: str = ""
    original_titles: set[str] = field(default_factory=set)
    query_ids: set[str] = field(default_factory=set)
    query_labels: set[str] = field(default_factory=set)
    gdelt_domains: set[str] = field(default_factory=set)
    languages: set[str] = field(default_factory=set)
    sourcecountries: set[str] = field(default_factory=set)
    row_count: int = 0


class DomainLimiter:
    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last_started: dict[str, float] = defaultdict(float)

    async def wait(self, domain: str) -> None:
        async with self._locks[domain]:
            now = time.monotonic()
            elapsed = now - self._last_started[domain]
            if elapsed < self.delay_seconds:
                await asyncio.sleep(self.delay_seconds - elapsed)
            self._last_started[domain] = time.monotonic()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drive-root", default=DEFAULT_DRIVE_ROOT)
    parser.add_argument("--stage-root", type=Path, default=DEFAULT_STAGE_ROOT)
    parser.add_argument("--status-dir", type=Path, default=REPO / "logs/news_shock_taxonomy")
    parser.add_argument("--countries", default="", help="Comma-separated ISO3 subset. Empty means all.")
    parser.add_argument("--start-month", default="", help="YYYY-MM lower bound. Empty means no bound.")
    parser.add_argument("--end-month", default="", help="YYYY-MM upper bound. Empty means no bound.")
    parser.add_argument("--max-files", type=int, default=0, help="0 means no cap.")
    parser.add_argument("--max-urls-per-file", type=int, default=0, help="0 means all deduped URLs in each file.")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--per-domain-delay", type=float, default=3.0)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-html-bytes", type=int, default=2_000_000)
    parser.add_argument("--text-char-limit", type=int, default=2500)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def rclone(*args: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["rclone", *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def list_remote_files(remote_dir: str) -> list[str]:
    proc = rclone("lsf", remote_dir, "--recursive", "--files-only", check=False, capture=True)
    if proc.returncode != 0:
        return []
    return sorted(line.strip() for line in proc.stdout.splitlines() if line.strip())


def copy_remote_to_local(remote_path: str, local_path: Path) -> bool:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    proc = rclone("copyto", remote_path, str(local_path), "--stats-one-line", check=False)
    return proc.returncode == 0 and local_path.exists()


def upload_and_unlink(path: Path, remote_path: str) -> int:
    size = path.stat().st_size
    rclone("copyto", str(path), remote_path, "--stats-one-line")
    path.unlink()
    return size


def filter_rel_paths(paths: list[str], args: argparse.Namespace) -> list[str]:
    countries = {item.strip().upper() for item in args.countries.split(",") if item.strip()}
    out = []
    for rel in paths:
        if not rel.endswith(".csv.gz"):
            continue
        parts = rel.split("/")
        if len(parts) != 2:
            continue
        country, filename = parts
        year_month = filename.removesuffix(".csv.gz")
        if countries and country.upper() not in countries:
            continue
        if args.start_month and year_month < args.start_month:
            continue
        if args.end_month and year_month > args.end_month:
            continue
        out.append(rel)
    return out


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return url


def bare_domain(url_or_host: str) -> str:
    host = urlparse(url_or_host).netloc if "://" in url_or_host else url_or_host
    host = (host or "").lower().strip()
    return host[4:] if host.startswith("www.") else host


def domain_matches(host: str, candidates: set[str]) -> bool:
    host = bare_domain(host)
    if not host:
        return False
    if host in candidates:
        return True
    return any(host.endswith("." + item) for item in candidates)


def source_class(url_or_host: str) -> str:
    host = bare_domain(url_or_host)
    if not host:
        return "other"
    if domain_matches(host, HIGH_TRUST_DOMAINS) or host.endswith(".gov") or ".go." in host:
        return "official"
    if domain_matches(host, TRUSTED_JOURNALISM_DOMAINS):
        return "journalism"
    if domain_matches(host, SOCIAL_DOMAINS):
        return "social"
    return "other"


def load_url_seeds(path: Path, max_urls: int) -> list[UrlSeed]:
    by_url: dict[str, UrlSeed] = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            url = normalize_url(row.get("url", ""))
            if not url:
                continue
            seed = by_url.get(url)
            if seed is None:
                seed = UrlSeed(
                    url=url,
                    country_iso3=row.get("country_iso3", ""),
                    country_name=row.get("country_name", ""),
                    year_month=row.get("year_month", ""),
                    first_seen=row.get("seendate", ""),
                )
                by_url[url] = seed
            seed.row_count += 1
            for attr, key in (
                ("original_titles", "title"),
                ("query_ids", "query_id"),
                ("query_labels", "query_label"),
                ("gdelt_domains", "domain"),
                ("languages", "language"),
                ("sourcecountries", "sourcecountry"),
            ):
                value = (row.get(key) or "").strip()
                if value:
                    getattr(seed, attr).add(value)
            seen = row.get("seendate") or ""
            if seen and (not seed.first_seen or seen < seed.first_seen):
                seed.first_seen = seen
    seeds = list(by_url.values())
    if max_urls > 0:
        return seeds[:max_urls]
    return seeds


def clean_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    return value


def meta_content(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return clean_text(tag["content"])
    return ""


def extract_html(html: str, final_url: str, text_char_limit: int) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    title_tag = soup.find("title")
    canonical = ""
    canonical_tag = soup.find("link", attrs={"rel": lambda value: value and "canonical" in value})
    if canonical_tag and canonical_tag.get("href"):
        canonical = canonical_tag["href"].strip()

    h1s = [clean_text(h.get_text(" ", strip=True)) for h in soup.find_all("h1")]
    h1s = [h for h in h1s if h][:5]
    paragraphs = [clean_text(p.get_text(" ", strip=True)) for p in soup.find_all("p")]
    paragraphs = [p for p in paragraphs if len(p) >= 25]
    full_text = "\n\n".join(paragraphs)
    if not full_text:
        body = soup.find("body")
        full_text = clean_text(body.get_text(" ", strip=True)) if body else ""
    excerpt = full_text[:text_char_limit] if text_char_limit > 0 else ""

    html_tag = soup.find("html")
    return {
        "extracted_title": clean_text(title_tag.get_text(" ", strip=True)) if title_tag else "",
        "og_title": meta_content(soup, "og:title", "twitter:title"),
        "meta_description": meta_content(soup, "description", "og:description", "twitter:description"),
        "canonical_url": canonical,
        "html_lang": html_tag.get("lang", "") if html_tag else "",
        "h1": h1s[0] if h1s else "",
        "h1s": h1s,
        "text_excerpt": excerpt,
        "text_char_count_estimate": len(full_text),
        "final_domain": urlparse(final_url).netloc.lower(),
    }


def seed_base(seed: UrlSeed) -> dict[str, Any]:
    url_hash = hashlib.sha256(seed.url.encode("utf-8")).hexdigest()
    source_domain = bare_domain(seed.url)
    return {
        "url_hash": url_hash,
        "url": seed.url,
        "source_domain": source_domain,
        "source_class": source_class(source_domain),
        "country_iso3": seed.country_iso3,
        "country_name": seed.country_name,
        "year_month": seed.year_month,
        "first_seen": seed.first_seen,
        "gdelt_original_titles": sorted(seed.original_titles)[:10],
        "query_ids": sorted(seed.query_ids),
        "query_labels": sorted(seed.query_labels),
        "gdelt_domains": sorted(seed.gdelt_domains),
        "languages": sorted(seed.languages),
        "sourcecountries": sorted(seed.sourcecountries),
        "deduped_from_rows": seed.row_count,
    }


async def read_limited_response(resp: aiohttp.ClientResponse, max_bytes: int) -> tuple[bytes, bool, int]:
    chunks = []
    total = 0
    truncated = False
    async for chunk in resp.content.iter_chunked(65536):
        total += len(chunk)
        remaining = max_bytes - sum(len(part) for part in chunks)
        if remaining > 0:
            chunks.append(chunk[:remaining])
        if total >= max_bytes:
            truncated = True
            break
    return b"".join(chunks), truncated, total


async def enrich_one(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    limiter: DomainLimiter,
    seed: UrlSeed,
    args: argparse.Namespace,
) -> dict[str, Any]:
    base = seed_base(seed)
    domain = urlparse(seed.url).netloc.lower()
    fetched_at = datetime.now(UTC).isoformat()
    async with semaphore:
        await limiter.wait(domain)
        try:
            timeout = aiohttp.ClientTimeout(total=args.timeout)
            async with session.get(seed.url, timeout=timeout, allow_redirects=True) as resp:
                content_type = resp.headers.get("content-type", "")
                raw, truncated, bytes_seen = await read_limited_response(resp, args.max_html_bytes)
                final_url = str(resp.url)
                common = {
                    **base,
                    "status": "ok" if resp.status < 400 else "http_error",
                    "http_status": resp.status,
                    "content_type": content_type,
                    "final_url": final_url,
                    "fetched_at": fetched_at,
                    "html_bytes_kept": len(raw),
                    "response_bytes_seen": bytes_seen,
                    "html_truncated": truncated,
                    "html_sha256": hashlib.sha256(raw).hexdigest() if raw else "",
                }
                if "html" not in content_type.lower():
                    return {**common, "status": "non_html"}
                charset = resp.charset or "utf-8"
                html = raw.decode(charset, errors="replace")
                return {**common, **extract_html(html, final_url, args.text_char_limit)}
        except Exception as exc:
            return {
                **base,
                "status": "fetch_error",
                "error": f"{type(exc).__name__}: {exc}",
                "domain": domain,
                "fetched_at": fetched_at,
            }


async def enrich_seeds(seeds: list[UrlSeed], args: argparse.Namespace) -> list[dict[str, Any]]:
    connector = aiohttp.TCPConnector(limit=max(args.concurrency * 2, args.concurrency), ssl=False)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.7"}
    semaphore = asyncio.Semaphore(args.concurrency)
    limiter = DomainLimiter(args.per_domain_delay)
    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        tasks = [enrich_one(session, semaphore, limiter, seed, args) for seed in seeds]
        return await asyncio.gather(*tasks)


def write_jsonl_gz(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_run_config(args: argparse.Namespace, files: list[str]) -> None:
    config = {
        "generated_at": datetime.now(UTC).isoformat(),
        "drive_root": args.drive_root,
        "input_prefix": NORMALIZED_PREFIX,
        "output_prefix": ENRICHED_PREFIX,
        "failure_prefix": FAILURE_PREFIX,
        "files_selected": len(files),
        "concurrency": args.concurrency,
        "per_domain_delay": args.per_domain_delay,
        "timeout": args.timeout,
        "max_html_bytes": args.max_html_bytes,
        "text_char_limit": args.text_char_limit,
        "oversight_bridge": {
            "sibling_path": str((REPO.parent / "crates/oversight").resolve()),
            "note": "This standalone extractor mirrors Oversight's aiohttp + BeautifulSoup extraction style, but writes permanent Drive evidence instead of short-lived Redis records.",
        },
    }
    tmp = args.stage_root / "gdelt_doc_url_enrichment_config.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    rclone("copyto", str(tmp), f"{args.drive_root}/config/gdelt_doc_url_enrichment_config.json", "--stats-one-line", check=False)
    tmp.unlink(missing_ok=True)


def process_file(rel_path: str, args: argparse.Namespace, status_path: Path) -> dict[str, Any]:
    input_remote = f"{args.drive_root}/{NORMALIZED_PREFIX}/{rel_path}"
    output_remote = f"{args.drive_root}/{ENRICHED_PREFIX}/{rel_path.removesuffix('.csv.gz')}.jsonl.gz"
    failure_remote = f"{args.drive_root}/{FAILURE_PREFIX}/{rel_path.removesuffix('.csv.gz')}.jsonl.gz"
    local_dir = args.stage_root / rel_path.removesuffix(".csv.gz")
    if local_dir.exists():
        shutil.rmtree(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)
    local_input = local_dir / Path(rel_path).name
    local_output = local_dir / "enriched.jsonl.gz"
    local_failures = local_dir / "failures.jsonl.gz"

    if not copy_remote_to_local(input_remote, local_input):
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "status": "input_copy_failed",
            "rel_path": rel_path,
        }
        append_jsonl(status_path, record)
        shutil.rmtree(local_dir, ignore_errors=True)
        return record

    seeds = load_url_seeds(local_input, args.max_urls_per_file)
    if not seeds:
        rows: list[dict[str, Any]] = []
    else:
        rows = asyncio.run(enrich_seeds(seeds, args))
    failures = [row for row in rows if row.get("status") != "ok"]
    write_jsonl_gz(local_output, rows)
    write_jsonl_gz(local_failures, failures)
    output_size = upload_and_unlink(local_output, output_remote)
    failure_size = upload_and_unlink(local_failures, failure_remote)
    shutil.rmtree(local_dir, ignore_errors=True)

    ok_count = sum(1 for row in rows if row.get("status") == "ok")
    record = {
        "ts": datetime.now(UTC).isoformat(),
        "status": "ok",
        "rel_path": rel_path,
        "urls": len(seeds),
        "ok": ok_count,
        "failed_or_non_html": len(failures),
        "output_gz_bytes": output_size,
        "failure_gz_bytes": failure_size,
    }
    append_jsonl(status_path, record)
    return record


def main() -> int:
    args = parse_args()
    args.stage_root.mkdir(parents=True, exist_ok=True)
    args.status_dir.mkdir(parents=True, exist_ok=True)
    status_path = args.status_dir / "gdelt_doc_url_enrichment_status.jsonl"

    input_files = filter_rel_paths(list_remote_files(f"{args.drive_root}/{NORMALIZED_PREFIX}"), args)
    existing_outputs = set(list_remote_files(f"{args.drive_root}/{ENRICHED_PREFIX}"))
    todo = []
    for rel in input_files:
        expected = f"{rel.removesuffix('.csv.gz')}.jsonl.gz"
        if not args.overwrite and expected in existing_outputs:
            continue
        todo.append(rel)
    if args.max_files > 0:
        todo = todo[: args.max_files]

    write_run_config(args, todo)
    print(
        json.dumps(
            {
                "drive_root": args.drive_root,
                "input_files": len(input_files),
                "existing_outputs": len(existing_outputs),
                "todo": len(todo),
                "stage": str(args.stage_root),
            },
            indent=2,
        ),
        flush=True,
    )

    for idx, rel_path in enumerate(todo, start=1):
        record = process_file(rel_path, args, status_path)
        rclone("copyto", str(status_path), f"{args.drive_root}/manifests/gdelt_doc_url_enrichment_status.jsonl", "--stats-one-line", check=False)
        print(f"[{idx}/{len(todo)}] {record}", flush=True)

    rclone("copyto", str(status_path), f"{args.drive_root}/manifests/gdelt_doc_url_enrichment_status.jsonl", "--stats-one-line", check=False)
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
