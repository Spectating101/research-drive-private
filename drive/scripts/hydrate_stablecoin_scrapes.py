#!/usr/bin/env python3
"""Pull archived Etherscan backfill scrapes from GDrive back to local staging for unified merge."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.research_data_mcp.collection_hydrate import execute_hydrate

REPO = Path(__file__).resolve().parents[1]


def backfill_scrape_entries(registry: dict) -> list[dict]:
    out: list[dict] = []
    for row in registry.get("datasets") or []:
        if not str(row.get("dataset_id") or "").startswith("scrape_"):
            continue
        name = str(row.get("name") or "")
        meta = row.get("metadata") or {}
        if "Etherscan token backfill" not in name and not meta.get("skynet_slug"):
            continue
        remote = str(row.get("canonical_remote") or (row.get("storage") or {}).get("canonical_remote") or "")
        local = str(row.get("local_path") or "")
        if not remote or not local:
            continue
        out.append({"dataset_id": row["dataset_id"], "remote_path": remote, "local_path": local, "name": name})
    return out


def needs_hydrate(repo_root: Path, local_rel: str) -> bool:
    base = repo_root / local_rel
    tokens = base / "tokens"
    if tokens.is_dir() and any(tokens.glob("*.json")):
        return False
    manifest = base / "manifest.json"
    return not manifest.is_file()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    registry = json.loads((REPO / "config/research_query_registry.json").read_text(encoding="utf-8"))
    entries = backfill_scrape_entries(registry)
    todo = [e for e in entries if needs_hydrate(REPO, e["local_path"])]
    print(f"backfill_scrapes_in_registry={len(entries)} need_hydrate={len(todo)}")

    hydrated = 0
    errors: list[str] = []
    for item in todo:
        print(f"hydrate {item['dataset_id']} -> {item['local_path']}")
        plan = {
            "remote_path": item["remote_path"],
            "local_path": item["local_path"],
            "local_abs": str((REPO / item["local_path"]).resolve()),
            "scope": "full",
            "verify": True,
            "timeout_seconds": 600,
        }
        if args.dry_run:
            continue
        try:
            execute_hydrate(REPO, plan)
            hydrated += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{item['dataset_id']}: {exc}")
            print(f"  FAILED: {exc}")

    print(json.dumps({"hydrated": hydrated, "skipped": len(entries) - len(todo), "errors": errors}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
