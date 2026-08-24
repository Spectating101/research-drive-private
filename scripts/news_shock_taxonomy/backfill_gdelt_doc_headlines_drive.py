#!/usr/bin/env python3
"""Drive-first GDELT DOC headline/URL backfill for news shock taxonomy.

This stores both:
- raw JSONL gzip records for every country-month-query response
- normalized headline/article-index CSV gzip rows

It is intentionally resumable at the country-month level.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any


DEFAULT_DRIVE_ROOT = "gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/news_shock_taxonomy"
DEFAULT_STAGE_ROOT = Path("/tmp/sharpe_news_shock_taxonomy")
REPO = Path(__file__).resolve().parents[2]
USER_AGENT = "Sharpe-Renaissance news-shock-taxonomy/1.0 research-contact=local@example.invalid"
GDELT_DOC_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"


@dataclass(frozen=True)
class Country:
    iso3: str
    fips: str
    name: str
    terms: tuple[str, ...]


COUNTRIES = [
    Country("USA", "US", "United States", ("United States", "US", "U.S.", "American")),
    Country("DEU", "GM", "Germany", ("Germany", "German")),
    Country("GBR", "UK", "United Kingdom", ("United Kingdom", "UK", "British", "Britain")),
    Country("FRA", "FR", "France", ("France", "French")),
    Country("JPN", "JA", "Japan", ("Japan", "Japanese")),
    Country("KOR", "KS", "South Korea", ("South Korea", "Korea", "Korean")),
    Country("AUS", "AS", "Australia", ("Australia", "Australian")),
    Country("CAN", "CA", "Canada", ("Canada", "Canadian")),
    Country("ESP", "SP", "Spain", ("Spain", "Spanish")),
    Country("ITA", "IT", "Italy", ("Italy", "Italian")),
    Country("CHN", "CH", "China", ("China", "Chinese")),
    Country("BRA", "BR", "Brazil", ("Brazil", "Brazilian")),
    Country("MEX", "MX", "Mexico", ("Mexico", "Mexican")),
    Country("TUR", "TU", "Turkey", ("Turkey", "Turkish")),
    Country("ZAF", "SF", "South Africa", ("South Africa", "South African")),
    Country("COL", "CO", "Colombia", ("Colombia", "Colombian")),
    Country("THA", "TH", "Thailand", ("Thailand", "Thai")),
    Country("MYS", "MY", "Malaysia", ("Malaysia", "Malaysian")),
    Country("ARG", "AR", "Argentina", ("Argentina", "Argentine", "Argentinian")),
    Country("POL", "PL", "Poland", ("Poland", "Polish")),
    Country("RUS", "RS", "Russia", ("Russia", "Russian")),
    Country("CHL", "CI", "Chile", ("Chile", "Chilean")),
    Country("PHL", "RP", "Philippines", ("Philippines", "Philippine", "Filipino")),
    Country("VNM", "VM", "Vietnam", ("Vietnam", "Vietnamese", "Viet Nam")),
    Country("IDN", "ID", "Indonesia", ("Indonesia", "Indonesian")),
    Country("IND", "IN", "India", ("India", "Indian")),
    Country("BGD", "BG", "Bangladesh", ("Bangladesh", "Bangladeshi")),
    Country("PAK", "PK", "Pakistan", ("Pakistan", "Pakistani")),
    Country("NGA", "NI", "Nigeria", ("Nigeria", "Nigerian")),
    Country("EGY", "EG", "Egypt", ("Egypt", "Egyptian")),
    Country("MAR", "MO", "Morocco", ("Morocco", "Moroccan")),
    Country("UKR", "UP", "Ukraine", ("Ukraine", "Ukrainian")),
    Country("GHA", "GH", "Ghana", ("Ghana", "Ghanaian")),
    Country("KEN", "KE", "Kenya", ("Kenya", "Kenyan")),
    Country("ETH", "ET", "Ethiopia", ("Ethiopia", "Ethiopian")),
    Country("SGP", "SN", "Singapore", ("Singapore", "Singaporean")),
]


QUERY_TEMPLATES = [
    {
        "id": "apology_clarification",
        "label": "Apology / clarification cycle",
        "terms": "(apologized OR apologised OR apology OR clarified OR clarification OR retracted OR \"walked back\")",
    },
    {
        "id": "denial_allegation",
        "label": "Denial / allegation cycle",
        "terms": "(denied OR denial OR allegations OR accused OR accusation OR \"hit back\")",
    },
    {
        "id": "corruption_graft",
        "label": "Corruption / graft",
        "terms": "(corruption OR corrupt OR bribery OR bribe OR graft OR embezzlement OR kickback)",
    },
    {
        "id": "policy_reversal_confusion",
        "label": "Policy reversal / confusion",
        "terms": "(\"policy reversal\" OR \"policy U-turn\" OR \"reversed policy\" OR \"delayed policy\" OR \"regulatory uncertainty\" OR \"confusing policy\")",
    },
    {
        "id": "institutional_conflict",
        "label": "Institutional conflict",
        "terms": "(minister OR ministry OR regulator OR parliament OR court OR central bank) (conflict OR clash OR dispute OR contradiction OR criticized)",
    },
    {
        "id": "protest_unrest",
        "label": "Protest / unrest",
        "terms": "(protest OR protests OR unrest OR riot OR riots OR demonstration OR strike OR backlash)",
    },
    {
        "id": "investigation_probe",
        "label": "Investigation / probe",
        "terms": "(investigation OR probe OR inquiry OR audit OR subpoena OR prosecutor OR watchdog)",
    },
    {
        "id": "resignation_dismissal",
        "label": "Resignation / dismissal",
        "terms": "(resigned OR resignation OR dismissed OR fired OR sacked OR removed OR ousted)",
    },
    {
        "id": "financial_fx_stress",
        "label": "Financial / FX stress",
        "terms": "(currency OR bond OR debt OR default OR reserves OR \"capital flight\" OR \"rate hike\" OR \"central bank intervention\")",
    },
    {
        "id": "trade_sanctions",
        "label": "Trade / sanctions",
        "terms": "(tariff OR tariffs OR sanctions OR embargo OR export controls OR import ban OR trade war)",
    },
    {
        "id": "geopolitical_security",
        "label": "Geopolitical / security",
        "terms": "(war OR military OR conflict OR border OR attack OR terrorism OR insurgency OR invasion)",
    },
    {
        "id": "corporate_governance",
        "label": "Corporate governance",
        "terms": "(fraud OR lawsuit OR accounting OR restatement OR governance OR shareholder OR insider OR bankruptcy)",
    },
]


ARTICLE_FIELDS = [
    "country_iso3",
    "country_name",
    "country_fips",
    "year_month",
    "query_id",
    "query_label",
    "query_terms",
    "seendate",
    "title",
    "url",
    "domain",
    "language",
    "sourcecountry",
    "socialimage",
    "article_index",
    "extras_json",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drive-root", default=DEFAULT_DRIVE_ROOT)
    parser.add_argument("--stage-root", type=Path, default=DEFAULT_STAGE_ROOT)
    parser.add_argument("--status-dir", type=Path, default=REPO / "logs/news_shock_taxonomy")
    parser.add_argument("--start-month", default="2015-02")
    parser.add_argument("--end-month", default=datetime.now(UTC).strftime("%Y-%m"))
    parser.add_argument("--countries", default="", help="Comma-separated ISO3 subset. Empty means all default countries.")
    parser.add_argument("--templates", default="", help="Comma-separated template ids. Empty means all templates.")
    parser.add_argument("--maxrecords", type=int, default=250)
    parser.add_argument("--sleep", type=float, default=8.0)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--retries", type=int, default=8)
    parser.add_argument("--max-country-months", type=int, default=0, help="0 means no cap. Useful for smoke tests.")
    return parser.parse_args()


def month_range(start: str, end: str) -> list[str]:
    start_year, start_month = [int(part) for part in start.split("-")]
    end_year, end_month = [int(part) for part in end.split("-")]
    current = date(start_year, start_month, 1)
    stop = date(end_year, end_month, 1)
    months = []
    while current <= stop:
        months.append(current.strftime("%Y-%m"))
        year = current.year + (1 if current.month == 12 else 0)
        month = 1 if current.month == 12 else current.month + 1
        current = date(year, month, 1)
    return months


def month_bounds(year_month: str) -> tuple[str, str]:
    year, month = [int(part) for part in year_month.split("-")]
    start = datetime(year, month, 1, 0, 0, 0)
    if month == 12:
        next_month = datetime(year + 1, 1, 1, 0, 0, 0)
    else:
        next_month = datetime(year, month + 1, 1, 0, 0, 0)
    end = next_month - timedelta(seconds=1)
    return start.strftime("%Y%m%d%H%M%S"), end.strftime("%Y%m%d%H%M%S")


def safe_name(value: str) -> str:
    value = value.strip().replace("/", "__")
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return value.strip("._-") or "unknown"


def rclone(*args: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["rclone", *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def remote_files(remote_dir: str) -> set[str]:
    proc = rclone("lsf", remote_dir, "--files-only", check=False, capture=True)
    if proc.returncode != 0:
        return set()
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def upload_and_unlink(path: Path, remote_path: str) -> int:
    size = path.stat().st_size
    rclone("copyto", str(path), remote_path, "--stats-one-line")
    path.unlink()
    return size


def build_country_query(country: Country, template: dict[str, str]) -> str:
    country_terms = " OR ".join(f'"{term}"' if " " in term or "." in term else term for term in country.terms)
    return f"({country_terms}) {template['terms']}"


def fetch_doc(query: str, start: str, end: str, maxrecords: int, timeout: int, retries: int) -> tuple[dict[str, Any], bytes]:
    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": str(maxrecords),
        "startdatetime": start,
        "enddatetime": end,
        "format": "json",
        "sort": "DateDesc",
    }
    url = GDELT_DOC_BASE + "?" + urllib.parse.urlencode(params)
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    last_error = ""
    for attempt in range(max(1, retries)):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            return json.loads(raw), raw
        except urllib.error.HTTPError as exc:
            body = exc.read(500).decode("utf-8", errors="replace")
            last_error = f"HTTP {exc.code}: {body}"
            if exc.code == 429 and attempt + 1 < retries:
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else min(180, 30 + attempt * 20)
                time.sleep(delay)
                continue
            if exc.code in {500, 502, 503, 504} and attempt + 1 < retries:
                time.sleep(10 + attempt * 10)
                continue
            raise RuntimeError(last_error) from exc
        except (OSError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            if attempt + 1 < retries:
                time.sleep(8 + attempt * 8)
                continue
            raise RuntimeError(last_error) from exc
    raise RuntimeError(last_error or "unknown DOC fetch error")


def write_raw_jsonl_gz(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_articles_csv_gz(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="", compresslevel=6) as fh:
        writer = csv.DictWriter(fh, fieldnames=ARTICLE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: stringify(row.get(field)) for field in ARTICLE_FIELDS})


def stringify(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def normalize_articles(
    country: Country,
    year_month: str,
    template: dict[str, str],
    query: str,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    articles = payload.get("articles", []) if isinstance(payload, dict) else []
    if not isinstance(articles, list):
        return []
    rows = []
    for idx, article in enumerate(articles):
        if not isinstance(article, dict):
            continue
        known = {"url", "title", "seendate", "socialimage", "domain", "language", "sourcecountry"}
        extras = {key: value for key, value in article.items() if key not in known}
        rows.append(
            {
                "country_iso3": country.iso3,
                "country_name": country.name,
                "country_fips": country.fips,
                "year_month": year_month,
                "query_id": template["id"],
                "query_label": template["label"],
                "query_terms": query,
                "seendate": article.get("seendate"),
                "title": article.get("title"),
                "url": article.get("url"),
                "domain": article.get("domain"),
                "language": article.get("language"),
                "sourcecountry": article.get("sourcecountry"),
                "socialimage": article.get("socialimage"),
                "article_index": idx,
                "extras_json": extras,
            }
        )
    return rows


def write_config(args: argparse.Namespace, countries: list[Country], templates: list[dict[str, str]]) -> None:
    config = {
        "generated_at": datetime.now(UTC).isoformat(),
        "drive_root": args.drive_root,
        "start_month": args.start_month,
        "end_month": args.end_month,
        "countries": [country.__dict__ for country in countries],
        "templates": templates,
        "notes": [
            "This is the GDELT DOC headline/URL evidence layer, not the final shock index.",
            "Country matching is by country name/demonym query terms, not sourcecountry.",
            "Use GDELT GKG and later URL-title enrichment for deeper composition checks.",
        ],
    }
    tmp = args.stage_root / "gdelt_doc_headline_backfill_config.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    rclone("copyto", str(tmp), f"{args.drive_root}/config/gdelt_doc_headline_backfill_config.json", "--stats-one-line", check=False)
    tmp.unlink(missing_ok=True)


def select_countries(args: argparse.Namespace) -> list[Country]:
    if not args.countries:
        return COUNTRIES
    wanted = {item.strip().upper() for item in args.countries.split(",") if item.strip()}
    return [country for country in COUNTRIES if country.iso3 in wanted]


def select_templates(args: argparse.Namespace) -> list[dict[str, str]]:
    if not args.templates:
        return QUERY_TEMPLATES
    wanted = {item.strip() for item in args.templates.split(",") if item.strip()}
    return [template for template in QUERY_TEMPLATES if template["id"] in wanted]


def main() -> int:
    args = parse_args()
    args.stage_root.mkdir(parents=True, exist_ok=True)
    args.status_dir.mkdir(parents=True, exist_ok=True)
    status_path = args.status_dir / "gdelt_doc_headline_backfill_status.jsonl"
    countries = select_countries(args)
    templates = select_templates(args)
    months = month_range(args.start_month, args.end_month)
    write_config(args, countries, templates)

    print(
        json.dumps(
            {
                "drive_root": args.drive_root,
                "stage": str(args.stage_root),
                "countries": len(countries),
                "templates": len(templates),
                "months": len(months),
                "country_month_tasks": len(countries) * len(months),
            },
            indent=2,
        ),
        flush=True,
    )

    processed = 0
    for country in countries:
        raw_remote_dir = f"{args.drive_root}/raw/gdelt_doc_headlines/{country.iso3}"
        norm_remote_dir = f"{args.drive_root}/normalized/gdelt_doc_headlines/{country.iso3}"
        raw_existing = remote_files(raw_remote_dir)
        norm_existing = remote_files(norm_remote_dir)
        for year_month in months:
            if args.max_country_months and processed >= args.max_country_months:
                print("max country-month cap reached", flush=True)
                return 0
            processed += 1
            filename = f"{year_month}.jsonl.gz"
            norm_filename = f"{year_month}.csv.gz"
            if filename in raw_existing and norm_filename in norm_existing:
                append_jsonl(
                    status_path,
                    {
                        "ts": datetime.now(UTC).isoformat(),
                        "status": "skipped_present",
                        "country_iso3": country.iso3,
                        "year_month": year_month,
                        "processed": processed,
                    },
                )
                continue

            start, end = month_bounds(year_month)
            raw_records: list[dict[str, Any]] = []
            article_rows: list[dict[str, Any]] = []
            errors = 0
            for template in templates:
                query = build_country_query(country, template)
                try:
                    payload, _raw = fetch_doc(query, start, end, args.maxrecords, args.timeout, args.retries)
                    raw_records.append(
                        {
                            "country_iso3": country.iso3,
                            "country_name": country.name,
                            "year_month": year_month,
                            "query_id": template["id"],
                            "query_label": template["label"],
                            "query_terms": query,
                            "status": "ok",
                            "payload": payload,
                        }
                    )
                    article_rows.extend(normalize_articles(country, year_month, template, query, payload))
                except Exception as exc:
                    errors += 1
                    raw_records.append(
                        {
                            "country_iso3": country.iso3,
                            "country_name": country.name,
                            "year_month": year_month,
                            "query_id": template["id"],
                            "query_label": template["label"],
                            "query_terms": query,
                            "status": "error",
                            "error": str(exc),
                        }
                    )
                time.sleep(max(0.0, args.sleep))

            local_dir = args.stage_root / "gdelt_doc_headlines" / country.iso3 / year_month
            if local_dir.exists():
                shutil.rmtree(local_dir)
            local_dir.mkdir(parents=True, exist_ok=True)
            raw_path = local_dir / filename
            norm_path = local_dir / norm_filename
            write_raw_jsonl_gz(raw_path, raw_records)
            write_articles_csv_gz(norm_path, article_rows)
            raw_size = upload_and_unlink(raw_path, f"{raw_remote_dir}/{filename}")
            norm_size = upload_and_unlink(norm_path, f"{norm_remote_dir}/{norm_filename}")
            raw_existing.add(filename)
            norm_existing.add(norm_filename)
            shutil.rmtree(local_dir, ignore_errors=True)

            status = "partial" if errors else "ok"
            record = {
                "ts": datetime.now(UTC).isoformat(),
                "status": status,
                "country_iso3": country.iso3,
                "country_name": country.name,
                "year_month": year_month,
                "templates": len(templates),
                "errors": errors,
                "article_rows": len(article_rows),
                "raw_gz_bytes": raw_size,
                "normalized_gz_bytes": norm_size,
                "processed": processed,
            }
            append_jsonl(status_path, record)
            if processed % 10 == 0 or errors:
                rclone("copyto", str(status_path), f"{args.drive_root}/manifests/gdelt_doc_headline_backfill_status.jsonl", "--stats-one-line", check=False)
            print(f"[{processed}] {status} {country.iso3} {year_month} articles={len(article_rows)} errors={errors}", flush=True)

    rclone("copyto", str(status_path), f"{args.drive_root}/manifests/gdelt_doc_headline_backfill_status.jsonl", "--stats-one-line", check=False)
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
