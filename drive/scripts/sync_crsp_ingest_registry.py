#!/usr/bin/env python3
"""Stamp CRSP registry cards from latest ingest manifest (honest bulk vs instant)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "kernel") not in sys.path:
    sys.path.insert(0, str(REPO / "kernel"))
if str(REPO / "drive") not in sys.path:
    sys.path.insert(0, str(REPO / "drive"))

from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)
REGISTRY = ROOT / "config/research_query_registry.json"
INGEST_MANIFEST = ROOT / "data_lake/crsp/processed/ingest_latest.json"


def _stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sync_from_ingest(*, dry_run: bool = False) -> dict:
    if not INGEST_MANIFEST.is_file():
        return {"ok": False, "error": "missing_ingest_manifest"}

    ingest_doc = json.loads(INGEST_MANIFEST.read_text(encoding="utf-8"))
    by_registry: dict[str, dict] = {}
    for row in ingest_doc.get("results") or []:
        rid = str(row.get("registry_dataset_id") or "")
        if rid:
            by_registry[rid] = row

    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    updated: list[str] = []

    for ds in reg.get("datasets") or []:
        did = str(ds.get("dataset_id") or "")
        row = by_registry.get(did)
        if not row:
            continue

        parse = row.get("parse") or {}
        parse_status = str(parse.get("status") or "")
        processed = row.get("processed_file")
        proc_path = ROOT / str(processed) if processed else None
        parquet_ready = bool(proc_path and proc_path.is_file() and proc_path.stat().st_size > 0)

        mat: dict = {
            "query_ready": parquet_ready,
            "probed_at": _stamp(),
            "ingest_zip": row.get("zip"),
            "extracted_to": row.get("extracted_to"),
            "member_count": row.get("member_count"),
            "parse_status": parse_status,
        }
        if processed:
            mat["resolved_path"] = str(processed)
        if parse.get("reason"):
            mat["parse_reason"] = parse.get("reason")
        if parse.get("rows"):
            mat["parse_rows"] = parse.get("rows")

        ds["materialization"] = mat
        if parquet_ready:
            ds["analysis_readiness"] = "instant"
            ds["collection_status"] = "active"
            ds["field_coverage"] = "query-ready"
            ds.pop("known_gap", None)
            ds.pop("promotion_target", None)
        elif str(row.get("status")) != "missing_raw":
            ds["analysis_readiness"] = "metadata_search"
            ds["collection_status"] = "wired"
            ds["field_coverage"] = "extracted_binary" if parse_status == "pending_parse" else "extracted_only"
            ds["known_gap"] = (
                "CADB/binary extracted — parquet parser pending (not query-ready yet)"
                if parse_status == "pending_parse"
                else "Extracted on disk; panel build pending"
            )
            ds["promotion_target"] = "instant"
        updated.append(did)

    if not dry_run and updated:
        reg["updated_at"] = _stamp()
        reg["crsp_ingest_sync_at"] = reg["updated_at"]
        REGISTRY.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return {
        "ok": True,
        "dry_run": dry_run,
        "updated": updated,
        "ingest_at": ingest_doc.get("generated_at"),
    }


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    out = sync_from_ingest(dry_run=args.dry_run)
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
