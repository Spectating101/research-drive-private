#!/usr/bin/env python3
"""Small USDT-on-Ethereum transfer-log pilot.

This is intentionally bounded: it proves the RPC -> logs -> decoded rows ->
local files path without attempting a full historical archive.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


USDT_ADDRESS = "0xdac17f958d2ee523a2206206994597c13d831ec7"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
DEFAULT_ENDPOINTS = [
    "https://ethereum-rpc.publicnode.com",
    "https://eth.llamarpc.com",
    "https://rpc.ankr.com/eth",
    "https://cloudflare-eth.com",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rpc(endpoint: str, method: str, params: list[Any], timeout: int) -> Any:
    response = requests.post(
        endpoint,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return payload["result"]


def topic_to_address(topic: str) -> str:
    return "0x" + topic[-40:].lower()


def decode_log(item: dict[str, Any], block_timestamps: dict[int, int], source: str) -> dict[str, Any]:
    block_number = int(item["blockNumber"], 16)
    value_raw = int(item["data"], 16)
    timestamp = block_timestamps.get(block_number)
    return {
        "chain_id": 1,
        "token_address": USDT_ADDRESS,
        "symbol": "USDT",
        "decimals": 6,
        "block_number": block_number,
        "block_timestamp": datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")
        if timestamp
        else None,
        "tx_hash": item["transactionHash"].lower(),
        "log_index": int(item["logIndex"], 16),
        "from_address": topic_to_address(item["topics"][1]),
        "to_address": topic_to_address(item["topics"][2]),
        "value_raw": str(value_raw),
        "value_usdt": value_raw / 1_000_000,
        "source": source,
        "ingested_at": utc_now(),
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def maybe_write_parquet(path: Path, rows: list[dict[str, Any]]) -> bool:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except Exception:
        return False
    if not rows:
        return False
    pq.write_table(pa.Table.from_pylist(rows), path, compression="zstd")
    return True


def maybe_duckdb_summary(parquet_path: Path) -> dict[str, Any] | None:
    try:
        import duckdb
    except Exception:
        return None
    if not parquet_path.exists():
        return None
    con = duckdb.connect()
    try:
        result = con.execute(
            """
            SELECT
              COUNT(*) AS transfer_count,
              MIN(block_number) AS min_block,
              MAX(block_number) AS max_block,
              COUNT(DISTINCT from_address) AS active_senders,
              COUNT(DISTINCT to_address) AS active_receivers,
              SUM(value_usdt) AS gross_volume_usdt,
              SUM(CASE WHEN value_usdt >= 1000000 THEN 1 ELSE 0 END) AS large_transfer_count
            FROM read_parquet(?)
            """,
            [str(parquet_path)],
        ).fetchone()
    finally:
        con.close()
    keys = [
        "transfer_count",
        "min_block",
        "max_block",
        "active_senders",
        "active_receivers",
        "gross_volume_usdt",
        "large_transfer_count",
    ]
    return dict(zip(keys, result))


def choose_endpoint(endpoints: list[str], timeout: int) -> tuple[str, int, list[dict[str, str]]]:
    failures: list[dict[str, str]] = []
    for endpoint in endpoints:
        try:
            latest = int(rpc(endpoint, "eth_blockNumber", [], timeout), 16)
            return endpoint, latest, failures
        except Exception as exc:
            failures.append({"endpoint": endpoint, "error": str(exc)[:300]})
    raise RuntimeError(f"no endpoint worked: {failures}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="data/usdt_catalogue/pilot")
    parser.add_argument("--blocks", type=int, default=50)
    parser.add_argument("--confirmations", type=int, default=64)
    parser.add_argument("--from-block", type=int)
    parser.add_argument("--to-block", type=int)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--endpoint", action="append", default=[])
    args = parser.parse_args()

    endpoints = args.endpoint or DEFAULT_ENDPOINTS
    endpoint, latest_block, endpoint_failures = choose_endpoint(endpoints, args.timeout)

    to_block = args.to_block if args.to_block is not None else latest_block - args.confirmations
    from_block = args.from_block if args.from_block is not None else to_block - args.blocks + 1
    if from_block < 0 or to_block < from_block:
        raise ValueError(f"invalid block range: {from_block}..{to_block}")

    log_filter = {
        "address": USDT_ADDRESS,
        "fromBlock": hex(from_block),
        "toBlock": hex(to_block),
        "topics": [TRANSFER_TOPIC],
    }
    logs = rpc(endpoint, "eth_getLogs", [log_filter], args.timeout)

    block_timestamps: dict[int, int] = {}
    for block_number in sorted({int(item["blockNumber"], 16) for item in logs}):
        block = rpc(endpoint, "eth_getBlockByNumber", [hex(block_number), False], args.timeout)
        block_timestamps[block_number] = int(block["timestamp"], 16)

    rows = [decode_log(item, block_timestamps, endpoint) for item in logs]
    rows.sort(key=lambda row: (row["block_number"], row["log_index"]))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"usdt_transfers_eth_{from_block}_{to_block}"
    jsonl_path = out_dir / f"{stem}.jsonl"
    csv_path = out_dir / f"{stem}.csv"
    parquet_path = out_dir / f"{stem}.parquet"
    manifest_path = out_dir / f"{stem}.manifest.json"

    write_jsonl(jsonl_path, rows)
    write_csv(csv_path, rows)
    parquet_written = maybe_write_parquet(parquet_path, rows)
    summary = maybe_duckdb_summary(parquet_path) if parquet_written else None

    manifest = {
        "status": "ok",
        "chain_id": 1,
        "token_address": USDT_ADDRESS,
        "event": "Transfer(address,address,uint256)",
        "endpoint": endpoint,
        "endpoint_failures_before_success": endpoint_failures,
        "latest_block_seen": latest_block,
        "from_block": from_block,
        "to_block": to_block,
        "block_span": to_block - from_block + 1,
        "transfer_count": len(rows),
        "jsonl_path": str(jsonl_path),
        "csv_path": str(csv_path),
        "parquet_path": str(parquet_path) if parquet_written else None,
        "duckdb_summary": summary,
        "sample_rows": rows[:5],
        "created_at": utc_now(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
