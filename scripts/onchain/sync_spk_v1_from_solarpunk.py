#!/usr/bin/env python3
"""Copy SPK v1 runtime + payment ledger from Solarpunk-bitcoin into Sharpe data lake."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def default_solarpunk_root() -> Path:
    # Sharpe-Renaissance lives under project_portfolio/Molina-Optiplex/; Solarpunk is a sibling repo.
    return Path(__file__).resolve().parents[4] / "Solarpunk-bitcoin"


def sync_spk_v1(
    solarpunk_root: Path,
    out_root: Path,
    *,
    dry_run: bool = False,
) -> dict:
    runtime_src = solarpunk_root / "state/runtime/spk_v1.json"
    ops_src = solarpunk_root / "state/runtime/spk_v1_operations.jsonl"

    if not runtime_src.exists():
        raise FileNotFoundError(f"SPK runtime not found: {runtime_src}")

    out_root.mkdir(parents=True, exist_ok=True)
    runtime_dst = out_root / "spk_v1_runtime.json"
    ledger_dst = out_root / "spk_v1_payment_ledger.jsonl"
    manifest_dst = out_root / "manifest.json"

    runtime = json.loads(runtime_src.read_text(encoding="utf-8"))
    ledger = runtime.get("chain_index", {}).get("payment_ledger", [])

    summary = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "source_repo": str(solarpunk_root),
        "source_runtime": str(runtime_src),
        "network": runtime.get("network"),
        "chain_id": runtime.get("chain_id"),
        "spk_address": runtime.get("contracts", {}).get("solar_punk_coin"),
        "currency_address": runtime.get("contracts", {}).get("currency_system"),
        "total_supply_spk": runtime.get("on_chain", {}).get("total_supply_spk"),
        "network_payment_count": runtime.get("genesis", {}).get("metrics", {}).get("network_payment_count"),
        "payment_ledger_rows": len(ledger),
        "runtime_synced_at": runtime.get("synced_at"),
    }

    if dry_run:
        return {"dry_run": True, **summary}

    shutil.copy2(runtime_src, runtime_dst)
    with ledger_dst.open("w", encoding="utf-8") as f:
        for row in ledger:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if ops_src.exists():
        shutil.copy2(ops_src, out_root / "spk_v1_operations.jsonl")

    manifest_dst.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync SPK v1 Sepolia runtime into Sharpe data lake")
    parser.add_argument(
        "--solarpunk-root",
        type=Path,
        default=default_solarpunk_root(),
        help="Path to Solarpunk-bitcoin repo",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=Path("data_lake/spk_v1"),
        help="Sharpe data lake destination",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    summary = sync_spk_v1(args.solarpunk_root.resolve(), args.out_root.resolve(), dry_run=args.dry_run)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
