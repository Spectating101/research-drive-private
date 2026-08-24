#!/usr/bin/env python3
"""Taiwan MOPS-adjacent governance panel via official TWSE OpenAPI (no scrape)."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.fetch_twse_openapi_taiwan_market_layer import (
    BASE_URL,
    fetch_json,
    normalize_row,
    rows_from_payload,
    write_csv,
    write_csv_gz,
    write_json_gz,
)

DEFAULT_OUT_ROOT = Path("data_lake/official_disclosures/taiwan_mops")
DEFAULT_DRIVE_ROOT = (
    "gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/collection/official/mops-disclosures"
)

# Official TWSE OpenAPI feeds that map to MOPS governance / misconduct research.
GOVERNANCE_ENDPOINTS = [
    ("company_profile", "/opendata/t187ap03_L"),
    ("material_information_daily", "/opendata/t187ap04_L"),
    ("regulator_penalty_cases", "/opendata/t187ap22_L"),
    ("esg_board", "/opendata/t187ap46_L_6"),
    ("esg_functional_committees", "/opendata/t187ap46_L_9"),
    ("esg_risk_management", "/opendata/t187ap46_L_19"),
    ("twse_events", "/news/eventList"),
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


def build_governance_panel(
    endpoint_rows: dict[str, list[dict[str, Any]]],
    fetched_at: str,
) -> list[dict[str, Any]]:
    """Flatten penalty / material-info rows for misconduct-governance panels."""
    profiles: dict[str, dict[str, Any]] = {}
    for row in endpoint_rows.get("company_profile", []):
        code = str(row.get("_twse_code") or "").strip()
        if code:
            profiles[code] = row

    panel: list[dict[str, Any]] = []
    for endpoint_id in ("regulator_penalty_cases", "material_information_daily"):
        for row in endpoint_rows.get(endpoint_id, []):
            code = str(row.get("_twse_code") or row.get("公司代號") or "").strip()
            profile = profiles.get(code, {})
            panel.append(
                {
                    "event_type": endpoint_id,
                    "twse_code": code,
                    "yahoo_symbol": f"{code}.TW" if code else "",
                    "name_zh": row.get("_name_zh") or profile.get("_name_zh") or row.get("公司名稱") or "",
                    "industry_zh": profile.get("產業別", ""),
                    "announcement_date": row.get("_announcement_date") or row.get("_date") or "",
                    "announcement_time": row.get("_announcement_time") or "",
                    "title_zh": row.get("標題") or row.get("主旨") or row.get("Title") or "",
                    "body_zh": row.get("內容") or row.get("說明") or row.get("Content") or "",
                    "source_url": row.get("_source_url") or "",
                    "fetched_at_utc": fetched_at,
                }
            )
    return panel


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

    swagger = fetch_json(f"{BASE_URL}/swagger.json", args.timeout, args.retries)
    write_json_gz(raw_dir / "swagger.json.gz", swagger)
    available_paths = set((swagger.get("paths") or {}).keys()) if isinstance(swagger, dict) else set()

    for endpoint_id, path in GOVERNANCE_ENDPOINTS:
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
            row.update(
                {
                    "status": "error",
                    "rows": 0,
                    "duration_seconds": round(time.time() - started, 3),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        manifest_rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        time.sleep(max(0.0, args.sleep))

    governance_panel = build_governance_panel(endpoint_rows, fetched_at)
    write_csv(derived_dir / "governance_misconduct_panel.csv", governance_panel)
    write_csv(out_dir / "manifest.csv", manifest_rows)

    summary = {
        "run_id": args.run_id,
        "fetched_at_utc": fetched_at,
        "source": "twse_openapi_mops_governance",
        "endpoints": len(GOVERNANCE_ENDPOINTS),
        "status_counts": {},
        "row_counts": {row["endpoint_id"]: row["rows"] for row in manifest_rows},
        "governance_panel_rows": len(governance_panel),
        "out_dir": str(out_dir),
    }
    for row in manifest_rows:
        summary["status_counts"][row["status"]] = summary["status_counts"].get(row["status"], 0) + 1
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)

    if args.copy_drive:
        from scripts.fetch_twse_openapi_taiwan_market_layer import rclone_copy

        rclone_copy(out_dir, f"{args.drive_root}/runs/{args.run_id}")
        rclone_copy(out_dir, f"{args.drive_root}/latest")

    return 0 if summary["status_counts"].get("error", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
