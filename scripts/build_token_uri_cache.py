#!/usr/bin/env python3
"""Build tokenURI cache CSVs with JSON-RPC batch eth_call requests."""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path
from typing import Any

import requests
from web3 import Web3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True, help="Collection slug for cache filename.")
    parser.add_argument("--contract", required=True, help="ERC-721 contract address.")
    parser.add_argument("--out-root", required=True, help="Metadata sidecar output root.")
    parser.add_argument("--start", type=int, default=0, help="First token id.")
    parser.add_argument("--end", type=int, required=True, help="Last token id, inclusive.")
    parser.add_argument("--rpc-url", default="https://ethereum-rpc.publicnode.com")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--pause", type=float, default=0.15, help="Delay between batch requests.")
    return parser.parse_args()


def read_existing(path: Path) -> dict[int, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return {int(row["token_id"]): row for row in csv.DictReader(fh) if str(row.get("token_id", "")).isdigit()}


def write_cache(path: Path, rows: dict[int, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    fields = ["token_id", "token_uri", "status", "error"]
    with tmp_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for token_id in sorted(rows):
            writer.writerow({field: rows[token_id].get(field, "") for field in fields})
    tmp_path.replace(path)


def token_uri_call_data(token_id: int) -> str:
    selector = Web3.keccak(text="tokenURI(uint256)")[:4].hex()
    return "0x" + selector + int(token_id).to_bytes(32, byteorder="big").hex()


def decode_string_result(w3: Web3, result: str) -> str:
    if not result or result == "0x":
        raise RuntimeError("empty eth_call result")
    return str(w3.codec.decode(["string"], bytes.fromhex(result.removeprefix("0x")))[0])


def main() -> int:
    args = parse_args()
    out_path = Path(args.out_root).resolve() / "token_uri_cache" / f"{args.slug}.csv"
    rows = read_existing(out_path)
    wanted = [token_id for token_id in range(args.start, args.end + 1) if rows.get(token_id, {}).get("status") != "ok"]
    if not wanted:
        print(f"cache already complete: {out_path}")
        return 0

    w3 = Web3()
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "User-Agent": "Sharpe-Renaissance tokenURI cache"})
    contract = Web3.to_checksum_address(args.contract)
    batch_size = max(1, int(args.batch_size or 1))

    for offset in range(0, len(wanted), batch_size):
        token_ids = wanted[offset : offset + batch_size]
        batch: list[dict[str, Any]] = []
        for token_id in token_ids:
            batch.append(
                {
                    "jsonrpc": "2.0",
                    "id": token_id,
                    "method": "eth_call",
                    "params": [{"to": contract, "data": token_uri_call_data(token_id)}, "latest"],
                }
            )
        try:
            resp = session.post(args.rpc_url, json=batch, timeout=(10, 120))
            resp.raise_for_status()
            payload = resp.json()
            by_id = {int(item["id"]): item for item in payload}
            for token_id in token_ids:
                item = by_id.get(token_id, {})
                if "result" in item:
                    try:
                        rows[token_id] = {
                            "token_id": str(token_id),
                            "token_uri": decode_string_result(w3, str(item["result"])),
                            "status": "ok",
                            "error": "",
                        }
                    except Exception as exc:  # noqa: BLE001 - retained in cache for resume.
                        rows[token_id] = {"token_id": str(token_id), "token_uri": "", "status": "error", "error": str(exc)}
                else:
                    rows[token_id] = {
                        "token_id": str(token_id),
                        "token_uri": "",
                        "status": "error",
                        "error": str(item.get("error", "missing response")),
                    }
        except Exception as exc:  # noqa: BLE001 - retained in cache for resume.
            for token_id in token_ids:
                rows[token_id] = {"token_id": str(token_id), "token_uri": "", "status": "error", "error": str(exc)}

        write_cache(out_path, rows)
        done = sum(1 for row in rows.values() if row.get("status") == "ok")
        errors = sum(1 for row in rows.values() if row.get("status") == "error")
        print(f"batch {offset + len(token_ids)}/{len(wanted)} cache_ok={done} errors={errors}", flush=True)
        if args.pause:
            time.sleep(args.pause)

    errors = sum(1 for row in rows.values() if row.get("status") == "error")
    print(f"wrote {out_path} rows={len(rows)} errors={errors}")
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
