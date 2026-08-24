#!/usr/bin/env python3
"""Export raw Ethereum USDT transfers from BigQuery, month by month.

Streams each month to Parquet, optionally uploads to GDrive via rclone, then
deletes the local shard to save disk. Resumable via manifest.json.

Example:
  export GOOGLE_CLOUD_PROJECT=search-485108
  python scripts/usdt_catalogue/bigquery_usdt_raw_harvest.py \\
    --project search-485108 \\
    --upload-remote 'gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/collection/markets/ethereum-usdt/raw_transfers'
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

USDT = "0xdac17f958d2ee523a2206206994597c13d831ec7"
TABLE = "bigquery-public-data.goog_blockchain_ethereum_mainnet_us.token_transfers"

RAW_SQL = """
SELECT
  block_timestamp,
  transaction_hash AS tx_hash,
  event_index AS log_index,
  from_address,
  to_address,
  CAST(quantity AS STRING) AS quantity_raw,
  CAST(quantity AS BIGNUMERIC) / 1000000 AS value_usdt
FROM `{table}`
WHERE address = '{token}'
  AND DATE(block_timestamp) BETWEEN '{start}' AND '{end}'
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def month_range(start: str, end: str) -> list[str]:
    y0, m0 = map(int, start.split("-"))
    y1, m1 = map(int, end.split("-"))
    out: list[str] = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y += 1
            m = 1
    return out


def month_bounds(month: str) -> tuple[str, str]:
    y, m = map(int, month.split("-"))
    start = date(y, m, 1)
    if m == 12:
        end = date(y, 12, 31)
    else:
        end = date(y, m + 1, 1).replace(day=1)
        end = date.fromordinal(end.toordinal() - 1)
    today = datetime.now(timezone.utc).date()
    if end > today:
        end = today
    return start.isoformat(), end.isoformat()


def load_manifest(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"months": {}, "created_at": utc_now()}


def save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = utc_now()
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def normalize_batch(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in batch:
        item = dict(row)
        ts = item.get("block_timestamp")
        if ts is not None:
            item["block_timestamp"] = ts.isoformat()
        value = item.get("value_usdt")
        if value is not None:
            item["value_usdt"] = float(value)
        out.append(item)
    return out


def iter_row_dicts(rows_iter, batch_size: int) -> Iterator[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    for row in rows_iter:
        batch.append(dict(row))
        if len(batch) >= batch_size:
            yield normalize_batch(batch)
            batch = []
    if batch:
        yield normalize_batch(batch)


def write_parquet(path: Path, rows_iter, batch_size: int) -> int:
    import pyarrow as pa
    import pyarrow.parquet as pq

    path.parent.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    total = 0
    try:
        for batch in iter_row_dicts(rows_iter, batch_size):
            table = pa.Table.from_pylist(batch)
            if writer is None:
                writer = pq.ParquetWriter(path, table.schema, compression="zstd")
            writer.write_table(table)
            total += len(batch)
    finally:
        if writer is not None:
            writer.close()
    return total


def rclone_upload(local: Path, remote_dir: str) -> None:
    remote = remote_dir.rstrip("/") + "/" + local.name
    cmd = ["rclone", "copyto", str(local), remote, "-v"]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Harvest raw USDT transfers month-by-month")
    parser.add_argument("--project", default=os.getenv("GOOGLE_CLOUD_PROJECT", ""))
    parser.add_argument("--location", default="US")
    parser.add_argument("--start-month", default="2017-11")
    parser.add_argument("--end-month", default=datetime.now(timezone.utc).strftime("%Y-%m"))
    parser.add_argument("--out-dir", default="data/usdt_catalogue/raw_transfers")
    parser.add_argument("--upload-remote", default="", help="rclone remote dir; upload+delete local after each month")
    parser.add_argument("--batch-size", type=int, default=50_000)
    parser.add_argument("--max-bytes-billed", type=int, default=160 * 1024**3)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.project.strip():
        raise SystemExit("Set --project or GOOGLE_CLOUD_PROJECT")

    from google.cloud import bigquery

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    manifest = load_manifest(manifest_path)
    client = bigquery.Client(project=args.project, location=args.location)

    for month in month_range(args.start_month, args.end_month):
        start, end = month_bounds(month)
        parquet = out_dir / f"usdt_transfers_{month}.parquet"
        prior = manifest["months"].get(month, {})

        if prior.get("status") == "ok" and not args.force:
            if args.upload_remote and not prior.get("uploaded"):
                pass
            elif parquet.exists() or prior.get("uploaded"):
                print(json.dumps({"month": month, "status": "skipped"}))
                continue

        sql = RAW_SQL.format(table=TABLE, token=USDT, start=start, end=end)
        job_config = bigquery.QueryJobConfig(maximum_bytes_billed=args.max_bytes_billed)
        job = client.query(sql, job_config=job_config, location=args.location)
        row_count = write_parquet(parquet, job.result(page_size=10_000), args.batch_size)
        bytes_processed = int(job.total_bytes_processed or 0)
        file_bytes = parquet.stat().st_size

        entry = {
            "month": month,
            "status": "ok",
            "start": start,
            "end": end,
            "rows": row_count,
            "bytes_processed": bytes_processed,
            "file_bytes": file_bytes,
            "local_path": str(parquet),
            "job_id": job.job_id,
            "uploaded": False,
        }

        if args.upload_remote:
            rclone_upload(parquet, args.upload_remote)
            entry["uploaded"] = True
            entry["remote_path"] = f"{args.upload_remote.rstrip('/')}/{parquet.name}"
            parquet.unlink()

        manifest["months"][month] = entry
        save_manifest(manifest_path, manifest)
        print(json.dumps(entry, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
