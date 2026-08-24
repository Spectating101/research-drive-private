#!/usr/bin/env python3
"""Build a derived Asia entity-to-instrument mapping layer from local sources."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import subprocess
from collections import Counter, OrderedDict, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_OUT_ROOT = Path("data_lake/entity_mapping/asia")
DEFAULT_DRIVE_ROOT = "gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/entity_mapping/asia"
DEFAULT_TWSE_ROOT = Path("data_lake/official_disclosures/taiwan_twse")
DEFAULT_YFINANCE_CONFIG = Path("config/markets/asia_yfinance_universes.json")
DEFAULT_YFINANCE_ROOT = Path("data_lake/markets/yfinance_asia")
DEFAULT_SOURCED_ROOTS = [
    Path("data_lake/markets/sourced_universes"),
    Path("data_lake/markets/yfinance_asia_sourced_holdings"),
]
DEFAULT_IDX_DB = Path("data_lake/markets/idx_legacy_restore/historical_data.db")


SUFFIX_MAP = {
    ".TW": ("TWSE", "TWN"),
    ".TWO": ("TPEX", "TWN"),
    ".KS": ("KRX", "KOR"),
    ".KQ": ("KOSDAQ", "KOR"),
    ".T": ("TSE", "JPN"),
    ".JK": ("IDX", "IDN"),
    ".HK": ("HKEX", "HKG"),
    ".SS": ("SSE", "CHN"),
    ".SZ": ("SZSE", "CHN"),
    ".SI": ("SGX", "SGP"),
    ".KL": ("BURSA", "MYS"),
    ".BK": ("SET", "THA"),
    ".NS": ("NSE", "IND"),
    ".BO": ("BSE", "IND"),
    ".AX": ("ASX", "AUS"),
}


COUNTRY_TO_ISO3 = {
    "Taiwan": "TWN",
    "South Korea": "KOR",
    "Korea": "KOR",
    "Japan": "JPN",
    "Indonesia": "IDN",
    "Malaysia": "MYS",
    "Thailand": "THA",
    "Singapore": "SGP",
    "Hong Kong": "HKG",
    "China": "CHN",
    "India": "IND",
    "Australia": "AUS",
    "Vietnam": "VNM",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--drive-root", default=DEFAULT_DRIVE_ROOT)
    parser.add_argument("--run-id", default=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--twse-root", type=Path, default=DEFAULT_TWSE_ROOT)
    parser.add_argument("--yfinance-config", type=Path, default=DEFAULT_YFINANCE_CONFIG)
    parser.add_argument("--yfinance-root", type=Path, default=DEFAULT_YFINANCE_ROOT)
    parser.add_argument("--idx-db", type=Path, default=DEFAULT_IDX_DB)
    parser.add_argument("--copy-drive", action="store_true")
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: OrderedDict[str, None] = OrderedDict()
    for row in rows:
        for key in row:
            fields.setdefault(key, None)
    with path.open("w", encoding="utf-8", newline="") as fh:
        if not fields:
            fh.write("")
            return
        writer = csv.DictWriter(fh, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def append_tag(value: str, tag: str) -> str:
    tags = [item for item in str(value or "").split("|") if item]
    if tag and tag not in tags:
        tags.append(tag)
    return "|".join(tags)


def first_present(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def latest_dir_with_file(root: Path, relative_file: str) -> Path | None:
    if not root.exists():
        return None
    candidates = []
    for path in root.iterdir():
        if path.is_dir() and (path / relative_file).exists():
            candidates.append(path)
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: (p.stat().st_mtime, p.name))[-1]


def latest_file(pattern_roots: list[Path], filename: str) -> Path | None:
    candidates: list[Path] = []
    for root in pattern_roots:
        if root.exists():
            candidates.extend(root.glob(f"*/{filename}"))
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: (p.stat().st_mtime, str(p)))[-1]


def classify_symbol(symbol: str) -> dict[str, str]:
    text = symbol.strip()
    if not text:
        return {"exchange": "", "market_country": "", "local_code": "", "instrument_type": ""}
    if text.startswith("^"):
        return {"exchange": "INDEX", "market_country": "", "local_code": text, "instrument_type": "index"}
    if text.endswith("=X"):
        return {"exchange": "FX", "market_country": "", "local_code": text, "instrument_type": "fx"}
    if text.endswith("=F"):
        return {"exchange": "FUTURES", "market_country": "", "local_code": text, "instrument_type": "future"}
    for suffix, (exchange, country) in sorted(SUFFIX_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        if text.endswith(suffix):
            return {
                "exchange": exchange,
                "market_country": country,
                "local_code": text[: -len(suffix)],
                "instrument_type": "equity_or_fund",
            }
    if "-" in text:
        return {"exchange": "CRYPTO", "market_country": "", "local_code": text, "instrument_type": "crypto"}
    return {"exchange": "US_OR_GLOBAL", "market_country": "USA", "local_code": text, "instrument_type": "equity_or_fund"}


def make_entity_id(exchange: str, local_code: str, yahoo_symbol: str) -> str:
    if exchange and local_code:
        return f"{exchange}:{local_code}"
    if yahoo_symbol:
        return f"YF:{yahoo_symbol}"
    return ""


def merge_entity(master: OrderedDict[str, dict[str, Any]], row: dict[str, Any]) -> None:
    yahoo = str(row.get("yahoo_symbol") or "").strip()
    key = yahoo or str(row.get("entity_id") or "").strip()
    if not key:
        return
    existing = master.get(key)
    if existing is None:
        master[key] = dict(row)
        return
    for key_name, value in row.items():
        if key_name in {"source_tags", "universes", "source_files"}:
            for tag in str(value or "").split("|"):
                existing[key_name] = append_tag(str(existing.get(key_name, "")), tag)
        elif key_name in {"row_count_daily", "row_count_hourly"}:
            old = int(existing.get(key_name) or 0)
            new = int(value or 0)
            if new > old:
                existing[key_name] = new
        elif key_name in {"date_min", "date_max"}:
            old_text = str(existing.get(key_name) or "")
            new_text = str(value or "")
            if key_name == "date_min" and new_text and (not old_text or new_text < old_text):
                existing[key_name] = new_text
            if key_name == "date_max" and new_text and (not old_text or new_text > old_text):
                existing[key_name] = new_text
        elif not str(existing.get(key_name) or "").strip() and str(value or "").strip():
            existing[key_name] = value


def load_tickers_from_config(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    config = read_json(path)
    rows: list[dict[str, str]] = []
    for universe in config.get("universes", []):
        universe_id = str(universe.get("id") or "")
        description = str(universe.get("description") or "")
        tickers = list(universe.get("tickers") or [])
        tickers_file = universe.get("tickers_file")
        if tickers_file:
            file_path = Path(tickers_file)
            if file_path.exists():
                for line in file_path.read_text(encoding="utf-8").splitlines():
                    clean = line.strip()
                    if clean and not clean.startswith("#"):
                        tickers.append(clean)
        for ticker in tickers:
            symbol = str(ticker).strip()
            if symbol:
                rows.append({
                    "yahoo_symbol": symbol,
                    "universe": universe_id,
                    "universe_description": description,
                    "source_file": str(path),
                })
    return rows


def add_yfinance_config(master: OrderedDict[str, dict[str, Any]], path: Path) -> int:
    count = 0
    for cfg_row in load_tickers_from_config(path):
        symbol = cfg_row["yahoo_symbol"]
        info = classify_symbol(symbol)
        local_code = info["local_code"]
        exchange = info["exchange"]
        row = {
            "entity_id": make_entity_id(exchange, local_code, symbol),
            "market_country": info["market_country"],
            "exchange": exchange,
            "local_code": local_code,
            "yahoo_symbol": symbol,
            "name": "",
            "name_local": "",
            "industry": "",
            "instrument_type": info["instrument_type"],
            "source_tags": "yfinance_config",
            "universes": cfg_row["universe"],
            "source_files": cfg_row["source_file"],
            "confidence": "medium",
        }
        merge_entity(master, row)
        count += 1
    return count


def add_twse(master: OrderedDict[str, dict[str, Any]], twse_root: Path) -> tuple[int, str]:
    run_dir = latest_dir_with_file(twse_root, "derived/twse_security_master.csv")
    if run_dir is None:
        return 0, ""
    source_file = run_dir / "derived/twse_security_master.csv"
    count = 0
    with source_file.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            symbol = str(row.get("yahoo_symbol") or "").strip()
            local_code = str(row.get("twse_code") or "").strip()
            merge_entity(master, {
                "entity_id": row.get("entity_id") or make_entity_id("TWSE", local_code, symbol),
                "market_country": "TWN",
                "exchange": "TWSE",
                "local_code": local_code,
                "yahoo_symbol": symbol,
                "name": "",
                "name_local": first_present(row.get("short_name_zh"), row.get("name_zh")),
                "industry": row.get("industry_zh", ""),
                "instrument_type": row.get("security_type_guess", ""),
                "listed_date": row.get("listed_date", ""),
                "source_tags": "official_twse",
                "universes": "",
                "source_files": str(source_file),
                "confidence": "high",
            })
            count += 1
    return count, str(source_file)


def add_yfinance_coverage(master: OrderedDict[str, dict[str, Any]], yfinance_root: Path) -> tuple[list[dict[str, Any]], str]:
    run_dir = latest_dir_with_file(yfinance_root, "manifest.csv")
    if run_dir is None:
        return [], ""
    coverage: dict[tuple[str, str], dict[str, Any]] = {}
    for csv_path in sorted(run_dir.glob("*.csv")):
        if csv_path.name in {"manifest.csv", "failed_tickers.csv"}:
            continue
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                symbol = str(row.get("instrument") or "").strip()
                date = str(row.get("date") or "").strip()
                universe = str(row.get("universe") or csv_path.stem).strip()
                if not symbol:
                    continue
                key = (universe, symbol)
                item = coverage.setdefault(key, {
                    "source": "yfinance",
                    "dataset": run_dir.name,
                    "universe": universe,
                    "yahoo_symbol": symbol,
                    "rows": 0,
                    "date_min": "",
                    "date_max": "",
                    "source_file": str(csv_path),
                })
                item["rows"] += 1
                if date and (not item["date_min"] or date < item["date_min"]):
                    item["date_min"] = date
                if date and (not item["date_max"] or date > item["date_max"]):
                    item["date_max"] = date
    for item in coverage.values():
        symbol = item["yahoo_symbol"]
        info = classify_symbol(symbol)
        merge_entity(master, {
            "entity_id": make_entity_id(info["exchange"], info["local_code"], symbol),
            "market_country": info["market_country"],
            "exchange": info["exchange"],
            "local_code": info["local_code"],
            "yahoo_symbol": symbol,
            "instrument_type": info["instrument_type"],
            "source_tags": "yfinance_prices",
            "universes": item["universe"],
            "source_files": item["source_file"],
            "row_count_daily": item["rows"],
            "date_min": item["date_min"],
            "date_max": item["date_max"],
            "confidence": "medium",
        })
    return list(coverage.values()), str(run_dir)


def add_idx_coverage(master: OrderedDict[str, dict[str, Any]], db_path: Path) -> tuple[list[dict[str, Any]], str]:
    if not db_path.exists():
        return [], ""
    rows: list[dict[str, Any]] = []
    with sqlite3.connect(db_path) as conn:
        for table, row_field in [("historical_data_daily", "row_count_daily"), ("historical_data_hourly", "row_count_hourly")]:
            query = (
                f"SELECT symbol, COUNT(*) AS rows, MIN(timestamp) AS date_min, "
                f"MAX(timestamp) AS date_max FROM {table} GROUP BY symbol ORDER BY symbol"
            )
            for symbol, count, date_min, date_max in conn.execute(query):
                symbol = str(symbol or "").strip()
                local_code = symbol.removesuffix(".JK")
                coverage_row = {
                    "source": "idx_legacy_restore",
                    "dataset": table,
                    "universe": "indonesia_idx_legacy_all",
                    "yahoo_symbol": symbol,
                    "rows": count,
                    "date_min": date_min or "",
                    "date_max": date_max or "",
                    "source_file": str(db_path),
                }
                rows.append(coverage_row)
                merge_entity(master, {
                    "entity_id": make_entity_id("IDX", local_code, symbol),
                    "market_country": "IDN",
                    "exchange": "IDX",
                    "local_code": local_code,
                    "yahoo_symbol": symbol,
                    "instrument_type": "equity_or_fund",
                    "source_tags": "idx_legacy_restore",
                    "universes": "indonesia_idx_legacy_all",
                    "source_files": str(db_path),
                    row_field: count,
                    "date_min": date_min or "",
                    "date_max": date_max or "",
                    "confidence": "medium",
                })
    return rows, str(db_path)


def add_holdings(master: OrderedDict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    source_file = latest_file(DEFAULT_SOURCED_ROOTS, "asia_etf_holdings_mapped.csv")
    if source_file is None:
        return [], ""
    rows: list[dict[str, Any]] = []
    with source_file.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            symbol = str(row.get("yahoo_symbol") or "").strip()
            if not symbol:
                continue
            info = classify_symbol(symbol)
            local_code = first_present(row.get("local_code"), info["local_code"])
            market_country = first_present(COUNTRY_TO_ISO3.get(str(row.get("country") or "")), info["market_country"])
            exchange = first_present(row.get("exchange"), info["exchange"])
            entity_id = make_entity_id(exchange, local_code, symbol)
            link_row = {
                "entity_id": entity_id,
                "etf": row.get("etf", ""),
                "country": row.get("country", ""),
                "market_country": market_country,
                "exchange": exchange,
                "local_code": local_code,
                "yahoo_symbol": symbol,
                "name": row.get("name", ""),
                "weight_pct": row.get("weight_pct", ""),
                "source_url": row.get("source_url", ""),
                "source_file": str(source_file),
            }
            rows.append(link_row)
            merge_entity(master, {
                "entity_id": entity_id,
                "market_country": market_country,
                "exchange": exchange,
                "local_code": local_code,
                "yahoo_symbol": symbol,
                "name": row.get("name", ""),
                "instrument_type": "equity_or_fund",
                "source_tags": "etf_holdings_proxy",
                "universes": row.get("etf", ""),
                "source_files": str(source_file),
                "confidence": "medium",
            })
    return rows, str(source_file)


def write_manifest(out_dir: Path, run_id: str) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(out_dir.rglob("*")):
        if path.is_file() and path.name != "manifest.csv":
            rows.append({
                "run_id": run_id,
                "path": str(path.relative_to(out_dir)),
                "bytes": path.stat().st_size,
            })
    write_csv(out_dir / "manifest.csv", rows)
    return rows


def rclone_copy(src: Path, dst: str) -> None:
    subprocess.run(
        ["rclone", "copy", str(src), dst, "--transfers", "4", "--checkers", "8", "--stats-one-line"],
        check=True,
    )


def main() -> int:
    args = parse_args()
    out_dir = args.out_root / args.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    built_at = datetime.now(UTC).isoformat()

    master: OrderedDict[str, dict[str, Any]] = OrderedDict()
    inputs: dict[str, Any] = {}

    inputs["yfinance_config_rows"] = add_yfinance_config(master, args.yfinance_config)
    twse_rows, twse_file = add_twse(master, args.twse_root)
    inputs["twse_rows"] = twse_rows
    inputs["twse_file"] = twse_file
    yfinance_coverage, yfinance_run = add_yfinance_coverage(master, args.yfinance_root)
    inputs["yfinance_coverage_rows"] = len(yfinance_coverage)
    inputs["yfinance_run"] = yfinance_run
    idx_coverage, idx_file = add_idx_coverage(master, args.idx_db)
    inputs["idx_coverage_rows"] = len(idx_coverage)
    inputs["idx_file"] = idx_file
    holdings_links, holdings_file = add_holdings(master)
    inputs["holdings_links"] = len(holdings_links)
    inputs["holdings_file"] = holdings_file

    entity_rows = list(master.values())
    for row in entity_rows:
        row.setdefault("built_at_utc", built_at)
        if not row.get("entity_id"):
            row["entity_id"] = make_entity_id(str(row.get("exchange", "")), str(row.get("local_code", "")), str(row.get("yahoo_symbol", "")))

    coverage_rows = yfinance_coverage + idx_coverage

    write_csv(out_dir / "asia_entity_master.csv", entity_rows)
    write_csv(out_dir / "asia_instrument_coverage.csv", coverage_rows)
    write_csv(out_dir / "asia_etf_holdings_entity_links.csv", holdings_links)

    country_counts = Counter(str(row.get("market_country") or "UNKNOWN") for row in entity_rows)
    exchange_counts = Counter(str(row.get("exchange") or "UNKNOWN") for row in entity_rows)
    source_counts: Counter[str] = Counter()
    for row in entity_rows:
        for tag in str(row.get("source_tags") or "").split("|"):
            if tag:
                source_counts[tag] += 1

    summary = {
        "run_id": args.run_id,
        "built_at_utc": built_at,
        "out_dir": str(out_dir),
        "entity_rows": len(entity_rows),
        "coverage_rows": len(coverage_rows),
        "holdings_links": len(holdings_links),
        "inputs": inputs,
        "country_counts": dict(country_counts.most_common()),
        "exchange_counts": dict(exchange_counts.most_common()),
        "source_counts": dict(source_counts.most_common()),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_rows = write_manifest(out_dir, args.run_id)
    summary["manifest_rows"] = len(manifest_rows)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)

    if args.copy_drive:
        rclone_copy(out_dir, f"{args.drive_root}/runs/{args.run_id}")
        rclone_copy(out_dir, f"{args.drive_root}/latest")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
