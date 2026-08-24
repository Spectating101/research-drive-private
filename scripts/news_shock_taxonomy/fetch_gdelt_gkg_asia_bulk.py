#!/usr/bin/env python3
"""Fetch and filter GDELT GKG bulk files for Asia news-shock research.

This is a local-first collector. It uses GDELT bulk GKG files rather than the
DOC API, so it is suitable as the broad backbone for political/macro/universal
news shock collection.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


UTC = timezone.utc

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO / "config/news_shock_asia_universe.json"
DEFAULT_RAW_ROOT = REPO / "data_lake/news_shock_taxonomy/raw/gdelt_gkg_asia_bulk"
DEFAULT_OUT_ROOT = REPO / "data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk"
MASTER_URL = "http://data.gdeltproject.org/gdeltv2/masterfilelist.txt"
USER_AGENT = "Sharpe-Renaissance asia-news-shock-gkg/1.0 research-contact=local@example.invalid"


def raise_csv_field_limit() -> None:
    limit = sys.maxsize
    while limit > 131072:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit = int(limit / 10)


raise_csv_field_limit()


GKG_COLUMNS = {
    "gkg_record_id": 0,
    "date": 1,
    "source_collection_id": 2,
    "source_common_name": 3,
    "document_identifier": 4,
    "counts": 5,
    "v2_counts": 6,
    "themes": 7,
    "v2_themes": 8,
    "locations": 9,
    "v2_locations": 10,
    "persons": 11,
    "v2_persons": 12,
    "organizations": 13,
    "v2_organizations": 14,
    "v2_tone": 15
}


OUT_COLUMNS = [
    "run_id",
    "source_file",
    "gkg_record_id",
    "published_at",
    "date",
    "country_iso3",
    "country_name",
    "country_fips",
    "matched_country_terms",
    "source_common_name",
    "document_identifier",
    "themes",
    "shock_hints",
    "tone_avg",
    "tone_positive",
    "tone_negative",
    "tone_polarity",
    "locations",
    "persons",
    "organizations",
    "quality_flags"
]


@dataclass(frozen=True)
class GdeltFile:
    ts: datetime
    url: str
    size: int
    name: str


def now_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def request_bytes(url: str, timeout: int) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_masterfilelist(cache_path: Path, timeout: int, refresh_seconds: int = 3600) -> Path:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists() and time.time() - cache_path.stat().st_mtime < refresh_seconds:
        return cache_path
    cache_path.write_bytes(request_bytes(MASTER_URL, timeout))
    return cache_path


def parse_datetime_arg(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("empty datetime")
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            pass
    if text.endswith("Z"):
        return datetime.fromisoformat(text[:-1] + "+00:00").astimezone(UTC)
    return datetime.fromisoformat(text).astimezone(UTC)


def parse_masterfilelist(path: Path, since: datetime, until: datetime | None = None) -> list[GdeltFile]:
    pattern = re.compile(
        r"^(?P<size>\d+)\s+[0-9a-f]+\s+(?P<url>https?://data\.gdeltproject\.org/gdeltv2/(?P<stamp>\d{14})\.gkg\.csv\.zip)$"
    )
    files: list[GdeltFile] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        ts = datetime.strptime(match.group("stamp"), "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        if ts < since:
            continue
        if until is not None and ts >= until:
            continue
        url = match.group("url")
        files.append(GdeltFile(ts=ts, url=url, size=int(match.group("size")), name=url.rsplit("/", 1)[-1]))
    files.sort(key=lambda f: f.ts)
    return files


def safe_get(row: list[str], name: str) -> str:
    idx = GKG_COLUMNS[name]
    if idx >= len(row):
        return ""
    return row[idx].strip()


def parse_tone(value: str) -> tuple[str, str, str, str]:
    parts = [part.strip() for part in value.split(",")]
    while len(parts) < 4:
        parts.append("")
    return parts[0], parts[1], parts[2], parts[3]


def normalize_date(value: str) -> tuple[str, str]:
    if len(value) < 8:
        return "", ""
    date_text = value[:8]
    try:
        dt = datetime.strptime(date_text, "%Y%m%d").replace(tzinfo=UTC)
    except ValueError:
        return "", ""
    return dt.isoformat(), dt.strftime("%Y-%m-%d")


def build_shock_hints(themes_text: str, shock_map: dict[str, list[str]]) -> str:
    upper = themes_text.upper()
    hints = []
    for label, needles in shock_map.items():
        if any(needle.upper() in upper for needle in needles):
            hints.append(label)
    return "|".join(hints)


def excluded(text: str, exclusions: Iterable[str]) -> bool:
    lower = text.lower()
    return any(term.lower() in lower for term in exclusions)


def relevant_theme(themes_text: str, includes: Iterable[str]) -> bool:
    upper = themes_text.upper()
    return any(term.upper() in upper for term in includes)


def iter_location_parts(locations_text: str) -> Iterable[list[str]]:
    for block in re.split(r"[;|]", locations_text):
        parts = block.split("#")
        if len(parts) >= 3:
            yield parts


def matched_countries(locations_text: str, countries: list[dict[str, Any]]) -> list[tuple[dict[str, Any], list[str]]]:
    location_parts = list(iter_location_parts(locations_text))
    hits: list[tuple[dict[str, Any], list[str]]] = []
    for country in countries:
        terms: list[str] = []
        fips = str(country.get("fips", "")).strip().upper()
        for parts in location_parts:
            full_name = parts[1] if len(parts) > 1 else ""
            country_code = parts[2].strip().upper() if len(parts) > 2 else ""
            if fips and country_code == fips:
                terms.append(f"fips:{fips}")
            full_name_lower = full_name.lower()
            for term in country.get("terms", []):
                term_text = str(term).strip()
                if not term_text:
                    continue
                escaped = re.escape(term_text.lower())
                pattern = rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"
                if re.search(pattern, full_name_lower):
                    terms.append(term_text)
        if terms:
            hits.append((country, sorted(set(terms))))
    return hits


def iter_clean_lines(text: Iterable[str], stats: dict[str, Any]) -> Iterable[str]:
    for line in text:
        if "\x00" in line:
            stats["nul_lines"] = int(stats.get("nul_lines", 0)) + 1
            stats["nul_chars_removed"] = int(stats.get("nul_chars_removed", 0)) + line.count("\x00")
            line = line.replace("\x00", "")
        yield line


def iter_zip_rows(path: Path, stats: dict[str, Any] | None = None) -> Iterable[list[str]]:
    row_stats: dict[str, Any] = stats if stats is not None else {}
    row_stats.setdefault("nul_lines", 0)
    row_stats.setdefault("nul_chars_removed", 0)
    row_stats.setdefault("csv_errors", 0)
    row_stats.setdefault("csv_error_samples", [])
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        if not names:
            return
        with zf.open(names[0], "r") as fh:
            text = io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline="")
            reader = csv.reader(iter_clean_lines(text, row_stats), delimiter="\t")
            while True:
                try:
                    yield next(reader)
                except StopIteration:
                    break
                except csv.Error as exc:
                    row_stats["csv_errors"] = int(row_stats.get("csv_errors", 0)) + 1
                    samples = row_stats.setdefault("csv_error_samples", [])
                    if len(samples) < 5:
                        samples.append(str(exc))
                    continue


def download_file(item: GdeltFile, raw_path: Path, timeout: int, retries: int, sleep: float) -> str:
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_path.exists() and raw_path.stat().st_size > 0:
        return "present"
    tmp = raw_path.with_suffix(raw_path.suffix + ".part")
    last_error = ""
    for attempt in range(max(1, retries)):
        try:
            tmp.write_bytes(request_bytes(item.url, timeout))
            tmp.replace(raw_path)
            if sleep > 0:
                time.sleep(sleep)
            return "downloaded"
        except urllib.error.HTTPError as exc:  # pragma: no cover - network dependent
            if exc.code == 404:
                if tmp.exists():
                    tmp.unlink()
                return "missing_404"
            last_error = str(exc)
            if tmp.exists():
                tmp.unlink()
            time.sleep(min(60.0, 2.0 * (attempt + 1)))
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = str(exc)
            if tmp.exists():
                tmp.unlink()
            time.sleep(min(60.0, 2.0 * (attempt + 1)))
    raise RuntimeError(f"failed {item.url}: {last_error}")


def filter_file(
    item: GdeltFile,
    raw_path: Path,
    writer: csv.DictWriter,
    config: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    file_summary, rows = filter_file_rows(item, raw_path, config, run_id)
    for out_row in rows:
        writer.writerow(out_row)
    return file_summary


def filter_file_rows(
    item: GdeltFile,
    raw_path: Path,
    config: dict[str, Any],
    run_id: str,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    countries = config["countries"]
    includes = config["include_theme_substrings"]
    exclusions = config.get("exclude_text_substrings", [])
    shock_map = config.get("shock_theme_map", {})
    rows_seen = 0
    rows_kept = 0
    country_counts: dict[str, int] = {}
    rows: list[dict[str, str]] = []
    row_quality: dict[str, Any] = {}
    for row in iter_zip_rows(raw_path, row_quality):
        rows_seen += 1
        date_raw = safe_get(row, "date")
        source_common_name = safe_get(row, "source_common_name")
        document_identifier = safe_get(row, "document_identifier")
        themes = "|".join(part for part in [safe_get(row, "themes"), safe_get(row, "v2_themes")] if part)
        locations = "|".join(part for part in [safe_get(row, "locations"), safe_get(row, "v2_locations")] if part)
        persons = "|".join(part for part in [safe_get(row, "persons"), safe_get(row, "v2_persons")] if part)
        organizations = "|".join(part for part in [safe_get(row, "organizations"), safe_get(row, "v2_organizations")] if part)
        candidate_text = " ".join([document_identifier, source_common_name, themes, locations, persons, organizations])
        if excluded(candidate_text, exclusions):
            continue
        if not relevant_theme(themes, includes):
            continue
        # Use GDELT's geocoded location fields for country attribution. Searching
        # all article text produces bad false positives like "Indian" matching
        # "Indiana" or currency words appearing inside unrelated names.
        country_hits = matched_countries(locations, countries)
        if not country_hits:
            continue
        published_at, date_text = normalize_date(date_raw)
        tone_avg, tone_positive, tone_negative, tone_polarity = parse_tone(safe_get(row, "v2_tone"))
        shock_hints = build_shock_hints(themes, shock_map)
        flags = []
        if not shock_hints:
            flags.append("theme_relevant_no_specific_hint")
        for country, terms in country_hits:
            iso3 = str(country["iso3"])
            rows.append(
                {
                    "run_id": run_id,
                    "source_file": item.name,
                    "gkg_record_id": safe_get(row, "gkg_record_id"),
                    "published_at": published_at,
                    "date": date_text,
                    "country_iso3": iso3,
                    "country_name": country["name"],
                    "country_fips": country["fips"],
                    "matched_country_terms": "|".join(terms),
                    "source_common_name": source_common_name,
                    "document_identifier": document_identifier,
                    "themes": themes,
                    "shock_hints": shock_hints,
                    "tone_avg": tone_avg,
                    "tone_positive": tone_positive,
                    "tone_negative": tone_negative,
                    "tone_polarity": tone_polarity,
                    "locations": locations,
                    "persons": persons,
                    "organizations": organizations,
                    "quality_flags": "|".join(flags),
                }
            )
            rows_kept += 1
            country_counts[iso3] = country_counts.get(iso3, 0) + 1
    return {
        "file": item.name,
        "rows_seen": rows_seen,
        "rows_kept": rows_kept,
        "country_counts": country_counts,
        "row_quality": row_quality,
    }, rows


def _safe_unlink(path: Path) -> None:
    if not path.exists():
        return
    for attempt in range(5):
        try:
            path.unlink()
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.5 * (attempt + 1))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--run-id", default=now_run_id())
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--start-date", default="", help="Inclusive UTC start: YYYY-MM-DD, ISO datetime, or YYYYMMDDHHMMSS.")
    parser.add_argument("--end-date", default="", help="Exclusive UTC end: YYYY-MM-DD, ISO datetime, or YYYYMMDDHHMMSS.")
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument("--workers", type=int, default=1, help="Concurrent GDELT file download/filter workers.")
    parser.add_argument("--master-refresh-seconds", type=int, default=3600)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-keep-raw", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    if args.start_date:
        since = parse_datetime_arg(args.start_date)
        until = parse_datetime_arg(args.end_date) if args.end_date else None
    else:
        since = datetime.now(UTC) - timedelta(hours=args.hours)
        until = None
    master_path = args.raw_root / "_masterfilelist.txt"
    master = fetch_masterfilelist(master_path, args.timeout, refresh_seconds=args.master_refresh_seconds)
    files = parse_masterfilelist(master, since, until)
    if args.max_files > 0:
        files = files[-args.max_files:]

    run_raw = args.raw_root / args.run_id
    run_out = args.out_root / args.run_id
    run_out.mkdir(parents=True, exist_ok=True)
    out_csv = run_out / "asia_gkg_filtered.csv.gz"
    out_csv_tmp = Path(str(out_csv) + ".part")
    manifest_path = run_out / "manifest.json"
    manifest_tmp = Path(str(manifest_path) + ".part")

    summary: dict[str, Any] = {
        "run_id": args.run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "config": str(args.config),
        "hours": args.hours,
        "start_date": since.isoformat(),
        "end_date": until.isoformat() if until else "",
        "selected_files": len(files),
        "raw_root": str(run_raw),
        "out_csv": str(out_csv),
        "dry_run": args.dry_run,
        "files": [],
        "total_rows_seen": 0,
        "total_rows_kept": 0,
        "country_counts": {},
    }

    if args.dry_run:
        summary["files"] = [{"name": item.name, "url": item.url, "size": item.size, "ts": item.ts.isoformat()} for item in files]
        manifest_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    def process_file(index_item: tuple[int, GdeltFile]) -> tuple[int, dict[str, Any], list[dict[str, str]]]:
        index, item = index_item
        raw_path = run_raw / item.name
        status = download_file(item, raw_path, args.timeout, args.retries, args.sleep)
        if status == "missing_404":
            file_summary = {
                "file": item.name,
                "rows_seen": 0,
                "rows_kept": 0,
                "country_counts": {},
                "row_quality": {},
            }
            rows = []
        else:
            file_summary, rows = filter_file_rows(item, raw_path, config, args.run_id)
        file_summary.update({"url": item.url, "size": item.size, "status": status, "index": index})
        if args.no_keep_raw and raw_path.exists():
            raw_path.unlink()
        return index, file_summary, rows

    if out_csv_tmp.exists():
        _safe_unlink(out_csv_tmp)
    if manifest_tmp.exists():
        _safe_unlink(manifest_tmp)

    def iter_processed_files() -> Iterable[tuple[int, dict[str, Any], list[dict[str, str]]]]:
        if args.workers <= 1:
            for index_item in enumerate(files, start=1):
                yield process_file(index_item)
            return

        max_workers = max(1, args.workers)
        max_in_flight = max_workers * 2
        pending_iter = iter(enumerate(files, start=1))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = set()
            for _ in range(max_in_flight):
                try:
                    futures.add(executor.submit(process_file, next(pending_iter)))
                except StopIteration:
                    break
            while futures:
                done, futures = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    yield future.result()
                    try:
                        futures.add(executor.submit(process_file, next(pending_iter)))
                    except StopIteration:
                        pass

    with gzip.open(out_csv_tmp, "wt", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUT_COLUMNS)
        writer.writeheader()

        for _, file_summary, rows in iter_processed_files():
            for out_row in rows:
                writer.writerow(out_row)
            summary["files"].append(file_summary)
            summary["total_rows_seen"] += int(file_summary["rows_seen"])
            summary["total_rows_kept"] += int(file_summary["rows_kept"])
            for iso3, count in file_summary["country_counts"].items():
                summary["country_counts"][iso3] = summary["country_counts"].get(iso3, 0) + count
            print(json.dumps(file_summary, sort_keys=True), flush=True)

    summary["files"].sort(key=lambda item: item.get("index", 0))
    out_csv_tmp.replace(out_csv)
    manifest_tmp.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest_tmp.replace(manifest_path)
    print(json.dumps({k: summary[k] for k in ["run_id", "selected_files", "total_rows_seen", "total_rows_kept", "country_counts", "out_csv"]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
