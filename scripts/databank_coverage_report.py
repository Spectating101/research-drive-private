#!/usr/bin/env python3
"""Inspect databank coverage without the Research Drive UI.

Prints registry, partition, disk, and query-readiness truth to stdout or JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "kernel") not in sys.path:
    sys.path.insert(0, str(REPO / "kernel"))

from sharpe_kernel.paths import repo_root_from_file

ROOT = repo_root_from_file(__file__)


def _stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(rel: str) -> dict[str, Any]:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _bytes_human(n: int) -> str:
    if n >= 1024**3:
        return f"{n / 1024**3:.2f} GiB"
    if n >= 1024**2:
        return f"{n / 1024**2:.1f} MiB"
    if n >= 1024:
        return f"{n / 1024:.0f} KiB"
    return f"{n} B"


def _dir_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def _partition_map(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(p["id"]): p for p in cfg.get("partitions") or [] if p.get("id")}


def _dataset_partition(ds: dict[str, Any], parts: dict[str, dict[str, Any]]) -> str:
    pid = str(ds.get("partition_id") or (ds.get("collection") or {}).get("partition_id") or "")
    if pid:
        return pid
    did = str(ds.get("dataset_id") or "")
    for part_id, part in parts.items():
        ids = {str(x) for x in part.get("registry_dataset_ids") or []}
        if did in ids:
            return part_id
    return "unassigned"


def _panel_resolves(ds: dict[str, Any]) -> tuple[bool, str]:
    if ds.get("backend") != "local_parquet_panel":
        return False, "n/a"
    try:
        from scripts.research_query_engine.engine import ResearchQueryEngine

        engine = ResearchQueryEngine(ROOT / "config/research_query_registry.json", repo_root=ROOT)
        engine._resolve_panel_path(ds, {})
        return True, "ok"
    except Exception as exc:
        return False, str(exc)[:120]


def build_report(*, check_paths: bool = True) -> dict[str, Any]:
    reg = _load_json("config/research_query_registry.json")
    parts_cfg = _load_json("config/collection_partitions.json")
    queue = _load_json("config/data_collection_queue.json")
    desk_sources = _load_json("config/desk_sources.json")

    datasets: list[dict[str, Any]] = list(reg.get("datasets") or [])
    parts = _partition_map(parts_cfg)

    by_readiness = Counter(str(d.get("analysis_readiness") or "unknown") for d in datasets)
    by_backend = Counter(str(d.get("backend") or "unknown") for d in datasets)

    professor_parts = [
        p
        for p in parts_cfg.get("partitions") or []
        if p.get("professor_visible") is not False and str(p.get("domain")) != "backend"
    ]

    lane_rows: list[dict[str, Any]] = []
    for part in sorted(professor_parts, key=lambda x: (x.get("domain", ""), x.get("id", ""))):
        local_rel = str(part.get("legacy_local_path") or "")
        local = ROOT / local_rel if local_rel else None
        local_ok = bool(local and local.exists())
        local_bytes = _dir_bytes(local) if local_ok and local else 0
        reg_ids = list(part.get("registry_dataset_ids") or [])
        lane_rows.append(
            {
                "partition_id": part.get("id"),
                "domain": part.get("domain"),
                "status": part.get("status"),
                "title": part.get("title"),
                "registry_datasets": len(reg_ids),
                "local_present": local_ok,
                "local_bytes": local_bytes,
                "local_human": _bytes_human(local_bytes) if local_bytes else None,
                "registry_dataset_ids": reg_ids,
            }
        )

    per_partition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    instant_rows: list[dict[str, Any]] = []
    remote_rows: list[dict[str, Any]] = []

    remote_backends = {"coingecko_simple_price_api", "usdt_bigquery_catalogue"}

    for ds in datasets:
        pid = _dataset_partition(ds, parts)
        row = {
            "dataset_id": ds.get("dataset_id"),
            "name": ds.get("name"),
            "readiness": ds.get("analysis_readiness"),
            "backend": ds.get("backend"),
            "partition_id": pid,
        }
        per_partition[pid].append(row)
        if str(ds.get("analysis_readiness")) == "instant":
            backend = str(ds.get("backend") or "")
            if backend == "local_parquet_panel":
                resolves, note = (False, "skip") if not check_paths else _panel_resolves(ds)
                instant_rows.append({**row, "query_path_ok": resolves, "path_note": note})
            else:
                instant_rows.append({**row, "query_path_ok": None, "path_note": f"backend={backend}"})
        if str(ds.get("backend")) in remote_backends:
            remote_rows.append(row)

    disk_lanes = [
        ("gdelt_normalized", ROOT / "data_lake/news_shock_taxonomy/normalized"),
        ("research_panels", ROOT / "data_lake/research_panels"),
        ("refinitiv_frozen", ROOT / "data_lake/refinitiv_backfill/2026-07-06-complete"),
        ("refinitiv_rescued", ROOT / "data_lake/refinitiv_backfill/rescued_desktop_20251215"),
        ("procured", ROOT / "data_lake/procured"),
        ("yzu_cluster_jobs", ROOT / "data_lake/yzu_cluster"),
    ]
    disk_summary = []
    for label, path in disk_lanes:
        b = _dir_bytes(path)
        disk_summary.append({"lane": label, "path": str(path.relative_to(ROOT)), "bytes": b, "human": _bytes_human(b)})

    enabled_queue = [t["id"] for t in queue.get("tasks") or [] if t.get("enabled")]
    live_sources = [s.get("id") for s in desk_sources.get("sources") or []]

    unassigned = per_partition.get("unassigned", [])
    refinitiv_ids = [d["dataset_id"] for d in datasets if str(d.get("dataset_id", "")).startswith("refinitiv_")]

    return {
        "generated_at": _stamp(),
        "summary": {
            "registry_datasets": len(datasets),
            "instant_datasets": by_readiness.get("instant", 0),
            "metadata_search": by_readiness.get("metadata_search", 0),
            "professor_partitions": len(professor_parts),
            "refinitiv_datasets": len(refinitiv_ids),
            "refinitiv_share_pct": round(100.0 * len(refinitiv_ids) / max(len(datasets), 1), 1),
            "unassigned_registry_ids": len(unassigned),
            "collection_queue_enabled": len(enabled_queue),
            "live_source_connectors": len(live_sources),
        },
        "readiness": dict(by_readiness),
        "backends_top": by_backend.most_common(12),
        "partitions": lane_rows,
        "datasets_by_partition": {k: len(v) for k, v in sorted(per_partition.items(), key=lambda x: -len(x[1]))},
        "instant_queryable": instant_rows,
        "remote_live_registry": remote_rows,
        "disk_lanes": disk_summary,
        "collection_queue_enabled": enabled_queue,
        "live_sources": live_sources,
        "gaps": [
            f"{len(unassigned)} registry datasets not mapped to a collection partition.",
            "104 metadata_search entries are searchable/procurable, not all instant-query panels.",
            "BigQuery/HF/DataCite live access is via MCP — not fully mirrored in registry instant cards.",
            "GDELT↔market entity bridge thin on US SPX (~62/570 RICs in entity_market_spine).",
        ],
    }


def _print_text(report: dict[str, Any]) -> None:
    s = report["summary"]
    print("=" * 72)
    print("DATABANK COVERAGE REPORT")
    print(report["generated_at"])
    print("=" * 72)
    print()
    print("HEADLINE")
    print(f"  Registry datasets:     {s['registry_datasets']}")
    print(f"  Instant (query-now):   {s['instant_datasets']}")
    print(f"  Metadata/search:       {s['metadata_search']}")
    print(f"  Professor partitions:  {s['professor_partitions']}")
    print(f"  Refinitiv lane:        {s['refinitiv_datasets']} ({s['refinitiv_share_pct']}% of registry)")
    print(f"  Unassigned to partition:{s['unassigned_registry_ids']}")
    print()
    print("DISK LANES (local)")
    for row in report["disk_lanes"]:
        print(f"  {row['lane']:22} {row['human']:>12}  {row['path']}")
    print()
    print("COLLECTION PARTITIONS")
    print(f"  {'domain':10} {'status':16} {'local':5} {'reg':>4}  partition")
    for row in report["partitions"]:
        loc = "Y" if row["local_present"] else "n"
        print(
            f"  {str(row['domain']):10} {str(row['status']):16} {loc:5} {row['registry_datasets']:4}  {row['partition_id']}"
        )
    print()
    print("REGISTRY BY PARTITION (dataset count)")
    for pid, n in report["datasets_by_partition"].items():
        print(f"  {n:4}  {pid}")
    print()
    print("INSTANT / QUERY-READY DATASETS")
    for row in report["instant_queryable"]:
        ok = row.get("query_path_ok")
        if ok is True:
            tag = "OK  "
        elif ok is False:
            tag = "MISS"
        else:
            tag = "other"
        print(f"  [{tag}] {row['dataset_id']}")
    print()
    print("REMOTE LIVE (in registry)")
    for row in report["remote_live_registry"]:
        print(f"  {row['dataset_id']:40} {row['backend']}")
    print()
    print("LIVE SOURCE CONNECTORS (desk_sources.json)")
    print("  " + ", ".join(report["live_sources"]))
    print()
    print("COLLECTION QUEUE (enabled)")
    print("  " + ", ".join(report["collection_queue_enabled"]))
    print()
    print("GAPS")
    for g in report["gaps"]:
        print(f"  - {g}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description="Databank coverage report (no UI)")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    ap.add_argument(
        "--out",
        default="",
        help="Write JSON to path (default: docs/status/generated/databank_coverage_report.json when --json)",
    )
    ap.add_argument("--no-path-check", action="store_true", help="Skip parquet path resolution checks")
    args = ap.parse_args()

    report = build_report(check_paths=not args.no_path_check)
    if args.json or args.out:
        out = Path(args.out) if args.out else ROOT / "docs/status/generated/databank_coverage_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(out)
    if not args.json:
        _print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
