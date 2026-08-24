#!/usr/bin/env python3
"""Fetch official TWSE OpenAPI snapshots for Taiwan market/entity mapping."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import subprocess
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


BASE_URL = "https://openapi.twse.com.tw/v1"
DEFAULT_OUT_ROOT = Path("data_lake/official_disclosures/taiwan_twse")
DEFAULT_DRIVE_ROOT = "gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/official_disclosures/taiwan_twse"


ENDPOINTS = [
    ("company_profile", "/opendata/t187ap03_L"),
    ("material_information_daily", "/opendata/t187ap04_L"),
    ("monthly_revenue", "/opendata/t187ap05_L"),
    ("dividend_distribution", "/opendata/t187ap45_L"),
    ("daily_trading_all", "/exchangeReport/STOCK_DAY_ALL"),
    ("daily_close_month_avg", "/exchangeReport/STOCK_DAY_AVG_ALL"),
    ("valuation_ratios", "/exchangeReport/BWIBBU_ALL"),
    ("ex_dividend_rights_schedule", "/exchangeReport/TWT48U_ALL"),
    ("taiex_history_current_month", "/indicesReport/MI_5MINS_HIST"),
    ("foreign_by_industry", "/fund/MI_QFIIS_cat"),
    ("top_foreign_holdings", "/fund/MI_QFIIS_sort_20"),
    ("twse_news", "/news/newsList"),
    ("twse_events", "/news/eventList"),
    ("regulator_penalty_cases", "/opendata/t187ap22_L"),
    ("income_statement_financial", "/opendata/t187ap06_L_basi"),
    ("income_statement_securities", "/opendata/t187ap06_L_bd"),
    ("income_statement_general", "/opendata/t187ap06_L_ci"),
    ("income_statement_holding", "/opendata/t187ap06_L_fh"),
    ("income_statement_insurance", "/opendata/t187ap06_L_ins"),
    ("income_statement_other", "/opendata/t187ap06_L_mim"),
    ("balance_sheet_financial", "/opendata/t187ap07_L_basi"),
    ("balance_sheet_securities", "/opendata/t187ap07_L_bd"),
    ("balance_sheet_general", "/opendata/t187ap07_L_ci"),
    ("balance_sheet_holding", "/opendata/t187ap07_L_fh"),
    ("balance_sheet_insurance", "/opendata/t187ap07_L_ins"),
    ("balance_sheet_other", "/opendata/t187ap07_L_mim"),
    ("esg_board", "/opendata/t187ap46_L_6"),
    ("esg_climate", "/opendata/t187ap46_L_8"),
    ("esg_functional_committees", "/opendata/t187ap46_L_9"),
    ("esg_supply_chain", "/opendata/t187ap46_L_13"),
    ("esg_information_security", "/opendata/t187ap46_L_16"),
    ("esg_risk_management", "/opendata/t187ap46_L_19"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--drive-root", default=DEFAULT_DRIVE_ROOT)
    parser.add_argument("--run-id", default=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--sleep", type=float, default=0.4)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--copy-drive", action="store_true")
    return parser.parse_args()


def fetch_json(url: str, timeout: int, retries: int) -> Any:
    headers = {"User-Agent": "Sharpe-Renaissance research collector/1.0"}
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8-sig"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(2 + attempt * 3)
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def roc_date_to_iso(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) == 7 and text.isdigit():
        year = int(text[:3]) + 1911
        return f"{year:04d}-{int(text[3:5]):02d}-{int(text[5:7]):02d}"
    if len(text) == 8 and text.isdigit():
        return f"{int(text[:4]):04d}-{int(text[4:6]):02d}-{int(text[6:8]):02d}"
    return ""


def roc_month_to_iso(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) == 5 and text.isdigit():
        year = int(text[:3]) + 1911
        return f"{year:04d}-{int(text[3:5]):02d}"
    if len(text) == 6 and text.isdigit():
        return f"{int(text[:4]):04d}-{int(text[4:6]):02d}"
    return ""


def time_to_hms(value: Any) -> str:
    text = str(value or "").strip()
    if text.isdigit() and 1 <= len(text) <= 6:
        text = text.zfill(6)
        return f"{text[:2]}:{text[2:4]}:{text[4:6]}"
    return ""


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        return [payload]
    return [{"value": payload}]


def ordered_fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    fields: OrderedDict[str, None] = OrderedDict()
    for row in rows:
        for key in row:
            fields.setdefault(key, None)
    return list(fields)


def normalize_row(row: dict[str, Any], endpoint_id: str, fetched_at: str) -> dict[str, Any]:
    stripped = {str(k).strip(): v for k, v in row.items()}
    out: OrderedDict[str, Any] = OrderedDict()
    out["_endpoint_id"] = endpoint_id
    out["_fetched_at_utc"] = fetched_at

    code = stripped.get("公司代號") or stripped.get("Code") or stripped.get("證券代號") or ""
    name = stripped.get("公司名稱") or stripped.get("Name") or ""
    short_name = stripped.get("公司簡稱") or ""
    if code:
        out["_twse_code"] = str(code).strip()
        out["_yahoo_symbol"] = f"{str(code).strip()}.TW"
    if name:
        out["_name_zh"] = name
    if short_name:
        out["_short_name_zh"] = short_name

    if "出表日期" in stripped:
        out["_asof_date"] = roc_date_to_iso(stripped.get("出表日期"))
    if "Date" in stripped:
        out["_date"] = roc_date_to_iso(stripped.get("Date"))
    if "發言日期" in stripped:
        out["_announcement_date"] = roc_date_to_iso(stripped.get("發言日期"))
    if "發言時間" in stripped:
        out["_announcement_time"] = time_to_hms(stripped.get("發言時間"))
    if "資料年月" in stripped:
        out["_period_month"] = roc_month_to_iso(stripped.get("資料年月"))
    if "Url" in stripped:
        out["_source_url"] = stripped.get("Url")
    if "Details" in stripped:
        out["_source_url"] = stripped.get("Details")

    for key, value in stripped.items():
        out[key] = value
    return dict(out)


def write_json_gz(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
        fh.write("\n")


def write_csv_gz(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        if not rows:
            fh.write("")
            return
        writer = csv.DictWriter(fh, fieldnames=ordered_fieldnames(rows), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        if not rows:
            fh.write("")
            return
        writer = csv.DictWriter(fh, fieldnames=ordered_fieldnames(rows), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_security_master(endpoint_rows: dict[str, list[dict[str, Any]]], fetched_at: str) -> list[dict[str, Any]]:
    profiles = {}
    for row in endpoint_rows.get("company_profile", []):
        code = str(row.get("_twse_code") or "").strip()
        if code:
            profiles[code] = row

    seen: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for endpoint_id in ["daily_trading_all", "valuation_ratios", "company_profile"]:
        for row in endpoint_rows.get(endpoint_id, []):
            code = str(row.get("_twse_code") or "").strip()
            if not code or code in seen:
                continue
            profile = profiles.get(code, {})
            name = row.get("_name_zh") or profile.get("_name_zh") or row.get("Name") or profile.get("公司名稱") or ""
            short_name = profile.get("_short_name_zh") or profile.get("公司簡稱") or ""
            security_type = "company"
            if code.startswith("00"):
                security_type = "etf_or_fund"
            seen[code] = {
                "entity_id": f"TWSE:{code}",
                "exchange": "TWSE",
                "market_country": "TWN",
                "twse_code": code,
                "yahoo_symbol": f"{code}.TW",
                "name_zh": name,
                "short_name_zh": short_name,
                "industry_zh": profile.get("產業別", ""),
                "security_type_guess": security_type,
                "listed_date": roc_date_to_iso(profile.get("上市日期", "")),
                "chairman": profile.get("董事長", ""),
                "general_manager": profile.get("總經理", ""),
                "spokesperson": profile.get("發言人", ""),
                "phone": profile.get("總機電話", ""),
                "address": profile.get("住址", ""),
                "source_profile_present": "1" if profile else "0",
                "fetched_at_utc": fetched_at,
            }
    return list(seen.values())


def rclone_copy(src: Path, dst: str) -> None:
    subprocess.run(
        ["rclone", "copy", str(src), dst, "--transfers", "4", "--checkers", "8", "--stats-one-line"],
        check=True,
    )


def main() -> int:
    args = parse_args()
    fetched_at = datetime.now(UTC).isoformat()
    out_dir = args.out_root / args.run_id
    raw_dir = out_dir / "raw"
    normalized_dir = out_dir / "normalized"
    derived_dir = out_dir / "derived"
    manifest_rows: list[dict[str, Any]] = []
    endpoint_rows: dict[str, list[dict[str, Any]]] = {}

    out_dir.mkdir(parents=True, exist_ok=True)

    swagger_url = f"{BASE_URL}/swagger.json"
    swagger = fetch_json(swagger_url, args.timeout, args.retries)
    write_json_gz(raw_dir / "swagger.json.gz", swagger)
    available_paths = set((swagger.get("paths") or {}).keys()) if isinstance(swagger, dict) else set()

    for endpoint_id, path in ENDPOINTS:
        started = time.time()
        url = f"{BASE_URL}{path}"
        raw_file = raw_dir / f"{endpoint_id}.json.gz"
        csv_file = normalized_dir / f"{endpoint_id}.csv.gz"
        row: dict[str, Any] = {
            "endpoint_id": endpoint_id,
            "path": path,
            "url": url,
            "raw_file": str(raw_file.relative_to(out_dir)),
            "csv_file": str(csv_file.relative_to(out_dir)),
            "swagger_path_present": str(path in available_paths).lower(),
        }
        try:
            payload = fetch_json(url, args.timeout, args.retries)
            rows = [normalize_row(r, endpoint_id, fetched_at) for r in rows_from_payload(payload)]
            write_json_gz(raw_file, payload)
            write_csv_gz(csv_file, rows)
            endpoint_rows[endpoint_id] = rows
            row.update({"status": "ok", "rows": len(rows), "duration_seconds": round(time.time() - started, 3)})
        except Exception as exc:  # noqa: BLE001
            row.update({
                "status": "error",
                "rows": 0,
                "duration_seconds": round(time.time() - started, 3),
                "error": f"{type(exc).__name__}: {exc}",
            })
        manifest_rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        time.sleep(max(0.0, args.sleep))

    security_master = build_security_master(endpoint_rows, fetched_at)
    write_csv(derived_dir / "twse_security_master.csv", security_master)
    write_csv(out_dir / "manifest.csv", manifest_rows)

    summary = {
        "run_id": args.run_id,
        "fetched_at_utc": fetched_at,
        "base_url": BASE_URL,
        "endpoints": len(ENDPOINTS),
        "status_counts": {},
        "row_counts": {row["endpoint_id"]: row["rows"] for row in manifest_rows},
        "security_master_rows": len(security_master),
        "out_dir": str(out_dir),
    }
    for row in manifest_rows:
        summary["status_counts"][row["status"]] = summary["status_counts"].get(row["status"], 0) + 1
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)

    if args.copy_drive:
        rclone_copy(out_dir, f"{args.drive_root}/runs/{args.run_id}")
        rclone_copy(out_dir, f"{args.drive_root}/latest")

    return 0 if summary["status_counts"].get("error", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
