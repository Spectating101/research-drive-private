#!/usr/bin/env python3
"""Harvest long-range Ethereum USDT daily flow panels from BigQuery.

Queries year-by-year so jobs are resumable and stay under byte guards.
Output: per-year CSV shards + merged daily panel + manifest.

Example:
  export GOOGLE_CLOUD_PROJECT=search-485108
  python scripts/usdt_catalogue/bigquery_usdt_history_harvest.py \\
    --project search-485108 --start-year 2017
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

USDT = "0xdac17f958d2ee523a2206206994597c13d831ec7"
TABLE = "`bigquery-public-data.goog_blockchain_ethereum_mainnet_us.token_transfers`"

DAILY_SQL = """
SELECT
  DATE(block_timestamp) AS date,
  COUNT(*) AS transfer_count,
  SUM(CAST(quantity AS BIGNUMERIC) / 1000000) AS gross_volume_usdt,
  COUNT(DISTINCT from_address) AS active_senders,
  COUNT(DISTINCT to_address) AS active_receivers,
  SUM(CASE WHEN CAST(quantity AS BIGNUMERIC) / 1000000 >= 1000000 THEN 1 ELSE 0 END)
    AS large_transfer_count,
  SUM(CASE WHEN CAST(quantity AS BIGNUMERIC) / 1000000 >= 1000000
      THEN CAST(quantity AS BIGNUMERIC) / 1000000 ELSE 0 END) AS large_transfer_volume_usdt
FROM {table}
WHERE address = '{token}'
  AND DATE(block_timestamp) BETWEEN '{start}' AND '{end}'
GROUP BY date
ORDER BY date
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def year_bounds(year: int) -> tuple[str, str]:
    start = f"{year}-01-01"
    if year == datetime.now(timezone.utc).year:
        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    else:
        end = f"{year}-12-31"
    return start, end


def write_csv(path: Path, rows) -> int:
    rows = list(rows)
    if not rows:
        path.write_text("", encoding="utf-8")
        return 0
    names = list(rows[0].keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
    return len(rows)


def merge_shards(shard_dir: Path, out_path: Path) -> int:
    shards = sorted(shard_dir.glob("daily_usdt_flows_*.csv"))
    total = 0
    header_written = False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as out:
        writer = None
        for shard in shards:
            with shard.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                if not header_written:
                    writer = csv.DictWriter(out, fieldnames=reader.fieldnames or [])
                    writer.writeheader()
                    header_written = True
                for row in reader:
                    writer.writerow(row)
                    total += 1
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="Harvest USDT daily flow history from BigQuery")
    parser.add_argument("--project", default=os.getenv("GOOGLE_CLOUD_PROJECT", ""))
    parser.add_argument("--location", default="US")
    parser.add_argument("--start-year", type=int, default=2017)
    parser.add_argument("--end-year", type=int, default=datetime.now(timezone.utc).year)
    parser.add_argument(
        "--out-dir",
        default="data/usdt_catalogue/bigquery_history",
        help="Output root (shards + merged panel + manifest)",
    )
    parser.add_argument("--max-bytes-billed", type=int, default=150 * 1024**3)
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument("--force", action="store_true", help="Re-run even if shard CSV exists")
    args = parser.parse_args()

    if not args.project.strip():
        raise SystemExit("Set --project or GOOGLE_CLOUD_PROJECT")

    from google.cloud import bigquery

    out_root = Path(args.out_dir)
    shard_dir = out_root / "shards"
    shard_dir.mkdir(parents=True, exist_ok=True)
    client = bigquery.Client(project=args.project, location=args.location)

    manifest: dict = {
        "created_at": utc_now(),
        "token": "USDT",
        "token_address": USDT,
        "project": args.project,
        "table": "bigquery-public-data.goog_blockchain_ethereum_mainnet_us.token_transfers",
        "years": [],
        "total_days": 0,
        "total_transfers": 0,
        "total_gross_volume_usdt": 0.0,
    }

    for year in range(args.start_year, args.end_year + 1):
        shard = shard_dir / f"daily_usdt_flows_{year}.csv"
        if shard.exists() and args.skip_existing and not args.force:
            manifest["years"].append({"year": year, "status": "skipped_existing", "path": str(shard)})
            continue

        start, end = year_bounds(year)
        sql = DAILY_SQL.format(table=TABLE, token=USDT, start=start, end=end)
        job_config = bigquery.QueryJobConfig(
            use_query_cache=True,
            maximum_bytes_billed=args.max_bytes_billed,
        )
        job = client.query(sql, job_config=job_config, location=args.location)
        rows_written = write_csv(shard, job.result())
        bytes_processed = int(job.total_bytes_processed or 0)
        year_meta = {
            "year": year,
            "status": "ok",
            "start": start,
            "end": end,
            "path": str(shard),
            "rows": rows_written,
            "bytes_processed": bytes_processed,
            "job_id": job.job_id,
        }
        manifest["years"].append(year_meta)
        print(json.dumps(year_meta, sort_keys=True))

    merged = out_root / "daily_usdt_flows_all.csv"
    merged_rows = merge_shards(shard_dir, merged)

    total_transfers = 0
    total_volume = 0.0
    min_date = None
    max_date = None
    with merged.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            total_transfers += int(row["transfer_count"])
            total_volume += float(row["gross_volume_usdt"])
            d = row["date"]
            min_date = d if min_date is None or d < min_date else min_date
            max_date = d if max_date is None or d > max_date else max_date

    manifest.update(
        {
            "merged_path": str(merged),
            "merged_rows": merged_rows,
            "date_min": min_date,
            "date_max": max_date,
            "total_transfers": total_transfers,
            "total_gross_volume_usdt": total_volume,
        }
    )
    manifest_path = out_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), "merged_rows": merged_rows, "date_min": min_date, "date_max": max_date}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
