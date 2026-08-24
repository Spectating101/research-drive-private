#!/usr/bin/env python3
"""Dry-run or execute bounded BigQuery USDT pilot SQL.

Requires Application Default Credentials or another google-auth mechanism:

    gcloud auth application-default login
    python scripts/usdt_catalogue/bigquery_usdt_pilot.py --project YOUR_PROJECT \
      --sql sql/bigquery/usdt/01_daily_usdt_flows_recent.sql

Default mode is dry-run only. Use --run to execute and optionally write CSV.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def import_bigquery():
    try:
        from google.cloud import bigquery
        from google.auth.exceptions import DefaultCredentialsError
    except Exception as exc:  # pragma: no cover - dependency check path
        raise SystemExit(
            "Missing dependency. Install with: python -m pip install google-cloud-bigquery"
        ) from exc
    return bigquery, DefaultCredentialsError


def bytes_to_tib(value: int) -> float:
    return value / float(1024**4)


def estimated_usd(bytes_processed: int) -> float:
    return bytes_to_tib(bytes_processed) * 6.25


def write_csv(path: Path, rows) -> int:
    rows = list(rows)
    if not rows:
        path.write_text("", encoding="utf-8")
        return 0
    names = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, help="Billing project that can create BigQuery jobs.")
    parser.add_argument("--sql", required=True, help="SQL file to dry-run or execute.")
    parser.add_argument("--location", default="US")
    parser.add_argument("--run", action="store_true", help="Actually run the query. Default is dry-run only.")
    parser.add_argument("--out-csv", help="Optional CSV output path when --run is set.")
    parser.add_argument("--out-report", help="Optional JSON path for the dry-run/run report.")
    parser.add_argument("--max-results", type=int, default=10000)
    parser.add_argument("--max-bytes-billed", type=int, default=100 * 1024**3)
    args = parser.parse_args()

    bigquery, DefaultCredentialsError = import_bigquery()
    sql = Path(args.sql).read_text(encoding="utf-8")

    try:
        client = bigquery.Client(project=args.project, location=args.location)
    except DefaultCredentialsError as exc:
        raise SystemExit(
            "No Google credentials found. Run `gcloud auth application-default login` "
            "or provide service-account credentials via GOOGLE_APPLICATION_CREDENTIALS."
        ) from exc

    dry_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    dry_job = client.query(sql, job_config=dry_config, location=args.location)
    dry_report = {
        "mode": "dry_run",
        "project": args.project,
        "sql": args.sql,
        "location": args.location,
        "total_bytes_processed": dry_job.total_bytes_processed,
        "estimated_tib_processed": bytes_to_tib(dry_job.total_bytes_processed),
        "estimated_usd_on_demand_before_free_tier": estimated_usd(dry_job.total_bytes_processed),
        "free_tier_note": "The first 1 TiB per month is free in aggregate; remaining monthly allowance is account-specific.",
        "maximum_bytes_billed": args.max_bytes_billed,
        "within_execution_guard": dry_job.total_bytes_processed <= args.max_bytes_billed,
    }

    if not args.run:
        if args.out_report:
            report_path = Path(args.out_report)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(dry_report, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(dry_report, indent=2, sort_keys=True))
        return 0

    run_config = bigquery.QueryJobConfig(use_query_cache=True, maximum_bytes_billed=args.max_bytes_billed)
    query_job = client.query(sql, job_config=run_config, location=args.location)
    rows_iter = query_job.result(max_results=args.max_results)
    result_report = {
        **dry_report,
        "mode": "run",
        "job_id": query_job.job_id,
        "actual_bytes_processed": query_job.total_bytes_processed,
        "actual_tib_processed": bytes_to_tib(query_job.total_bytes_processed or 0),
    }
    if args.out_csv:
        out_path = Path(args.out_csv)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        result_report["csv_rows_written"] = write_csv(out_path, rows_iter)
        result_report["csv_path"] = str(out_path)
    else:
        result_report["rows"] = [dict(row) for row in rows_iter]

    if args.out_report:
        report_path = Path(args.out_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result_report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(result_report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
