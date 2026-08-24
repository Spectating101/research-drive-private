#!/usr/bin/env python3
"""Build a small professor-facing USDT research package from transfer Parquet.

Input is the decoded transfer table produced by rpc_usdt_transfer_pilot.py.
Output is a compact catalogue package: research panels, manifest, and notes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_query_csv(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any], path: Path) -> int:
    rows = con.execute(sql, params).fetchall()
    columns = [item[0] for item in con.description]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)
    return len(rows)


def write_readme(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(
        f"""# USDT Research Catalogue Pilot

Generated at: `{manifest["created_at"]}`

This is a small end-to-end pilot package for Ethereum USDT transfer research.
It is not a full Etherscan replica. It demonstrates the intended data shape:
decoded USDT transfer rows, daily/monthly panels, address-day flows, large
transfers, and validation-oriented metadata.

## Source

```text
source parquet: {manifest["source_parquet"]}
rows: {manifest["source_row_count"]}
min block: {manifest["min_block"]}
max block: {manifest["max_block"]}
min timestamp: {manifest["min_timestamp"]}
max timestamp: {manifest["max_timestamp"]}
```

## Files

```text
tables/daily_usdt_flows.csv
tables/monthly_usdt_summary.csv
tables/address_day_usdt_flows_top.csv
tables/large_usdt_transfers.csv
tables/top_addresses_by_volume.csv
manifest.json
README.md
```

## Interpretation

The pilot proves the local research layer. In production, historical data should
come from BigQuery and live updates should come from RPC `eth_getLogs`.

Google Drive should be used as cold archive/delivery storage, not as the query
engine. DuckDB or BigQuery should be used for research queries.
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-parquet", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--large-threshold-usdt", type=float, default=1_000_000)
    parser.add_argument("--address-limit", type=int, default=5000)
    args = parser.parse_args()

    source = Path(args.input_parquet)
    out_dir = Path(args.out_dir)
    tables_dir = out_dir / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    try:
        source_stats = con.execute(
            """
            SELECT
              COUNT(*) AS row_count,
              MIN(block_number) AS min_block,
              MAX(block_number) AS max_block,
              MIN(block_timestamp) AS min_timestamp,
              MAX(block_timestamp) AS max_timestamp,
              COUNT(DISTINCT tx_hash || ':' || CAST(log_index AS VARCHAR)) AS distinct_primary_keys,
              COUNT(*) - COUNT(DISTINCT tx_hash || ':' || CAST(log_index AS VARCHAR)) AS duplicate_primary_keys
            FROM read_parquet(?)
            """,
            [str(source)],
        ).fetchone()

        daily_rows = write_query_csv(
            con,
            """
            SELECT
              CAST(block_timestamp AS DATE) AS date,
              COUNT(*) AS transfer_count,
              SUM(value_usdt) AS gross_volume_usdt,
              COUNT(DISTINCT from_address) AS active_senders,
              COUNT(DISTINCT to_address) AS active_receivers,
              COUNT(DISTINCT from_address) + COUNT(DISTINCT to_address) AS sender_receiver_distinct_sum,
              SUM(CASE WHEN value_usdt >= ? THEN 1 ELSE 0 END) AS large_transfer_count,
              SUM(CASE WHEN value_usdt >= ? THEN value_usdt ELSE 0 END) AS large_transfer_volume_usdt
            FROM read_parquet(?)
            GROUP BY 1
            ORDER BY 1
            """,
            [args.large_threshold_usdt, args.large_threshold_usdt, str(source)],
            tables_dir / "daily_usdt_flows.csv",
        )

        monthly_rows = write_query_csv(
            con,
            """
            SELECT
              DATE_TRUNC('month', CAST(block_timestamp AS DATE)) AS month,
              COUNT(*) AS transfer_count,
              SUM(value_usdt) AS gross_volume_usdt,
              COUNT(DISTINCT from_address) AS active_senders,
              COUNT(DISTINCT to_address) AS active_receivers,
              SUM(CASE WHEN value_usdt >= ? THEN 1 ELSE 0 END) AS large_transfer_count,
              SUM(CASE WHEN value_usdt >= ? THEN value_usdt ELSE 0 END) AS large_transfer_volume_usdt
            FROM read_parquet(?)
            GROUP BY 1
            ORDER BY 1
            """,
            [args.large_threshold_usdt, args.large_threshold_usdt, str(source)],
            tables_dir / "monthly_usdt_summary.csv",
        )

        address_rows = write_query_csv(
            con,
            """
            WITH sent AS (
              SELECT
                CAST(block_timestamp AS DATE) AS date,
                from_address AS address,
                COUNT(*) AS sent_count,
                SUM(value_usdt) AS sent_value_usdt,
                COUNT(DISTINCT to_address) AS sent_counterparties
              FROM read_parquet(?)
              GROUP BY 1, 2
            ),
            received AS (
              SELECT
                CAST(block_timestamp AS DATE) AS date,
                to_address AS address,
                COUNT(*) AS received_count,
                SUM(value_usdt) AS received_value_usdt,
                COUNT(DISTINCT from_address) AS received_counterparties
              FROM read_parquet(?)
              GROUP BY 1, 2
            )
            SELECT
              COALESCE(s.date, r.date) AS date,
              COALESCE(s.address, r.address) AS address,
              COALESCE(sent_count, 0) AS sent_count,
              COALESCE(received_count, 0) AS received_count,
              COALESCE(sent_value_usdt, 0) AS sent_value_usdt,
              COALESCE(received_value_usdt, 0) AS received_value_usdt,
              COALESCE(received_value_usdt, 0) - COALESCE(sent_value_usdt, 0) AS net_value_usdt,
              COALESCE(sent_counterparties, 0) AS sent_counterparties,
              COALESCE(received_counterparties, 0) AS received_counterparties
            FROM sent s
            FULL OUTER JOIN received r
              ON s.date = r.date
             AND s.address = r.address
            ORDER BY ABS(COALESCE(received_value_usdt, 0) - COALESCE(sent_value_usdt, 0)) DESC
            LIMIT ?
            """,
            [str(source), str(source), args.address_limit],
            tables_dir / "address_day_usdt_flows_top.csv",
        )

        large_rows = write_query_csv(
            con,
            """
            SELECT
              block_timestamp,
              CAST(block_timestamp AS DATE) AS date,
              block_number,
              tx_hash,
              log_index,
              from_address,
              to_address,
              value_usdt
            FROM read_parquet(?)
            WHERE value_usdt >= ?
            ORDER BY value_usdt DESC, block_timestamp
            """,
            [str(source), args.large_threshold_usdt],
            tables_dir / "large_usdt_transfers.csv",
        )

        top_address_rows = write_query_csv(
            con,
            """
            WITH address_values AS (
              SELECT from_address AS address, SUM(value_usdt) AS sent_value_usdt, 0::DOUBLE AS received_value_usdt
              FROM read_parquet(?)
              GROUP BY 1
              UNION ALL
              SELECT to_address AS address, 0::DOUBLE AS sent_value_usdt, SUM(value_usdt) AS received_value_usdt
              FROM read_parquet(?)
              GROUP BY 1
            )
            SELECT
              address,
              SUM(sent_value_usdt) AS sent_value_usdt,
              SUM(received_value_usdt) AS received_value_usdt,
              SUM(received_value_usdt) - SUM(sent_value_usdt) AS net_value_usdt,
              SUM(sent_value_usdt) + SUM(received_value_usdt) AS gross_activity_usdt
            FROM address_values
            GROUP BY 1
            ORDER BY gross_activity_usdt DESC
            LIMIT ?
            """,
            [str(source), str(source), args.address_limit],
            tables_dir / "top_addresses_by_volume.csv",
        )
    finally:
        con.close()

    manifest = {
        "created_at": utc_now(),
        "source_parquet": str(source),
        "source_sha256": sha256_file(source),
        "source_row_count": source_stats[0],
        "min_block": source_stats[1],
        "max_block": source_stats[2],
        "min_timestamp": str(source_stats[3]),
        "max_timestamp": str(source_stats[4]),
        "distinct_primary_keys": source_stats[5],
        "duplicate_primary_keys": source_stats[6],
        "large_threshold_usdt": args.large_threshold_usdt,
        "outputs": {
            "daily_usdt_flows.csv": daily_rows,
            "monthly_usdt_summary.csv": monthly_rows,
            "address_day_usdt_flows_top.csv": address_rows,
            "large_usdt_transfers.csv": large_rows,
            "top_addresses_by_volume.csv": top_address_rows,
        },
        "known_limitations": [
            "Pilot sample only; not full historical coverage.",
            "No exchange/entity address labels.",
            "No internal transactions/traces.",
            "Historical production source should be BigQuery once GCP credentials are available.",
        ],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    write_readme(out_dir / "README.md", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
