#!/usr/bin/env python3
"""Inventory GDrive canonical collection vs local hot/cache paths.

GDrive is listed first (source of truth), then each mapped local path is measured.
Output: data_lake/collection/_index/manifest_latest.json (+ optional --pretty summary).

Usage:
  python scripts/data_catalog/inventory_canonical_collection.py --pretty
  python scripts/data_catalog/inventory_canonical_collection.py --quick --pretty
  python scripts/data_catalog/inventory_canonical_collection.py --drive-only
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from sharpe_kernel.paths import repo_root_from_file

REPO = repo_root_from_file(__file__)
sys.path.insert(0, str(REPO))

from scripts.research_data_mcp.collection_resolve import parse_size_hint
PARTITIONS_PATH = REPO / "config/collection_partitions.json"
LAYOUT_PATH = REPO / "config/collection_layout.json"
COLLECTION_ROOT = REPO / "data_lake/collection"
INDEX_DIR = COLLECTION_ROOT / "_index"
MANIFEST_PATH = INDEX_DIR / "manifest_latest.json"

SIZE_RE = re.compile(
    r"Total size:\s*(?P<bytes>\d+(?:\.\d+)?)\s*(?P<unit>MiB|GiB|TiB|KiB|Mib|Gib|Tib|Kib|MB|GB|TB|KB|Byte|Bytes)",
    re.I,
)
OBJECTS_RE = re.compile(r"Total objects:\s*(?P<objects>\d+)", re.I)
UNIT_BYTES = {
    "b": 1,
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "tib": 1024**4,
    "kb": 1000,
    "mb": 1000**2,
    "gb": 1000**3,
    "tb": 1000**4,
}


def _run(cmd: list[str], *, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def parse_rclone_size(stdout: str) -> dict[str, Any]:
    m = SIZE_RE.search(stdout)
    if not m:
        return {"objects": 0, "bytes": 0, "human": "0 B", "error": "parse_failed"}
    om = OBJECTS_RE.search(stdout)
    objects = int(om.group("objects")) if om else 0
    raw = float(m.group("bytes"))
    unit = m.group("unit").lower()
    if unit.startswith("byte"):
        nbytes = int(raw)
    else:
        mult = UNIT_BYTES.get(unit, 1)
        nbytes = int(raw * mult)
    return {
        "objects": objects,
        "bytes": nbytes,
        "human": f"{m.group('bytes')} {m.group('unit')}",
    }


def rclone_remote_size(remote: str, *, fast: bool = False) -> dict[str, Any]:
    cmd = ["rclone", "size", remote]
    if fast:
        cmd.append("--fast")
    proc = _run(cmd, timeout=900)
    if proc.returncode != 0:
        return {"objects": 0, "bytes": 0, "human": "0 B", "error": (proc.stderr or proc.stdout or "rclone failed")[:240]}
    out = parse_rclone_size(proc.stdout)
    out["remote"] = remote
    return out


def rclone_list_dirs(remote_root: str) -> list[dict[str, str]]:
    proc = _run(["rclone", "lsd", remote_root], timeout=120)
    rows: list[dict[str, str]] = []
    if proc.returncode != 0:
        return rows
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        name = parts[-1]
        rows.append({"name": name, "remote": f"{remote_root}/{name}"})
    return rows


def local_dir_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "bytes": 0, "human": "0 B", "resolved": str(path)}
    if path.is_symlink():
        resolved = path.resolve()
        return {
            "exists": True,
            "symlink": True,
            "resolved": str(resolved),
            **local_dir_stats(resolved),
        }
    proc = _run(["du", "-sb", str(path)], timeout=300)
    if proc.returncode != 0:
        return {"exists": True, "bytes": 0, "human": "?", "resolved": str(path), "error": "du_failed"}
    nbytes = int(proc.stdout.split()[0])
    return {
        "exists": True,
        "bytes": nbytes,
        "human": _human_bytes(nbytes),
        "resolved": str(path),
    }


def _human_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    units = ["KiB", "MiB", "GiB", "TiB"]
    value = float(n)
    for unit in units:
        value /= 1024.0
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
    return f"{n} B"


def load_layout() -> dict[str, Any]:
    path = PARTITIONS_PATH if PARTITIONS_PATH.exists() else LAYOUT_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    if "partitions" in raw:
        collections = []
        for part in raw["partitions"]:
            legacy_drive = part.get("legacy_drive_path") or ""
            drive_path = legacy_drive.split("/")[0] if legacy_drive else ""
            collections.append(
                {
                    "id": part["id"],
                    "label": part.get("title"),
                    "drive_path": drive_path or None,
                    "drive_subpath": legacy_drive,
                    "local_path": part.get("legacy_local_path"),
                    "tier": part.get("tier"),
                    "registry_dataset_ids": part.get("registry_dataset_ids") or [],
                    "legacy_local_names": [],
                    "partition_path": part.get("path"),
                    "drive_size_hint": part.get("drive_size_hint"),
                }
            )
        return {
            "version": raw.get("version"),
            "canonical_root": raw["canonical_root"],
            "collections": [c for c in collections if c.get("drive_path") or c.get("local_path")],
            "local_only": [
                {
                    "id": p["id"],
                    "local_path": p.get("legacy_local_path"),
                    "tier": p.get("tier"),
                    "notes": p.get("description"),
                }
                for p in raw["partitions"]
                if p.get("status") == "local_only" and p.get("legacy_local_path")
            ],
        }
    return raw


def build_manifest(
    *,
    quick: bool,
    drive_only: bool,
) -> dict[str, Any]:
    layout = load_layout()
    root = str(layout["canonical_root"]).rstrip("/")
    now = datetime.now(timezone.utc).isoformat()

    drive_dirs = {row["name"]: row for row in rclone_list_dirs(root)}
    collections_out: list[dict[str, Any]] = []
    drive_total = 0

    for coll in layout.get("collections") or []:
        cid = str(coll["id"])
        drive_path = str(coll.get("drive_path") or "")
        drive_subpath = str(coll.get("drive_subpath") or drive_path)
        legacy_local = coll.get("local_path")

        if drive_path:
            remote = f"{root}/{drive_subpath}"
            on_drive_folder = drive_path in drive_dirs or drive_subpath.split("/")[0] in drive_dirs
            if quick:
                hint = parse_size_hint(str(coll.get("drive_size_hint") or ""))
                drive_stat = {
                    "objects": None,
                    "bytes": hint or None,
                    "human": coll.get("drive_size_hint") or "—",
                    "remote": remote,
                    "measured": False,
                }
            else:
                drive_stat = rclone_remote_size(remote, fast=False)
                drive_stat["measured"] = True
            drive_total += int(drive_stat.get("bytes") or parse_size_hint(str(coll.get("drive_size_hint") or "")))
        else:
            remote = None
            on_drive_folder = False
            drive_stat = {"objects": None, "bytes": None, "human": "—", "measured": False}

        local_stat: dict[str, Any] | None = None
        if legacy_local and not drive_only:
            local_stat = local_dir_stats(REPO / str(legacy_local))

        drive_bytes = int(drive_stat.get("bytes") or 0)
        local_bytes = int((local_stat or {}).get("bytes") or 0)
        coverage = None
        if drive_bytes > 0 and local_stat and local_stat.get("exists"):
            coverage = round(min(1.0, local_bytes / drive_bytes), 3)

        collections_out.append(
            {
                "id": cid,
                "label": coll.get("label"),
                "tier": coll.get("tier"),
                "partition_path": coll.get("partition_path"),
                "drive_size_hint": coll.get("drive_size_hint"),
                "drive_path": drive_subpath,
                "drive_remote": remote,
                "drive": drive_stat,
                "local_path": legacy_local,
                "local": local_stat,
                "legacy_local_names": coll.get("legacy_local_names") or [],
                "registry_dataset_ids": coll.get("registry_dataset_ids") or [],
                "local_coverage_ratio": coverage,
                "on_drive": on_drive_folder or bool(drive_stat.get("bytes")),
                "on_local": bool(local_stat and local_stat.get("exists") and local_bytes > 0),
            }
        )

    unmapped_drive = sorted(
        name for name in drive_dirs if name not in {c["drive_path"] for c in layout.get("collections") or []}
    )

    local_only_out: list[dict[str, Any]] = []
    if not drive_only:
        for row in layout.get("local_only") or []:
            lp = row.get("local_path")
            if not lp:
                continue
            local_only_out.append(
                {
                    "id": row.get("id"),
                    "local_path": lp,
                    "tier": row.get("tier"),
                    "notes": row.get("notes"),
                    "local": local_dir_stats(REPO / str(lp)),
                }
            )

    return {
        "generated_at": now,
        "canonical_root": root,
        "layout_version": layout.get("version"),
        "layout_path": str((PARTITIONS_PATH if PARTITIONS_PATH.exists() else LAYOUT_PATH).relative_to(REPO)),
        "drive_account": _run(["rclone", "about", "gdrive:"], timeout=60).stdout.strip()[:500],
        "collections": collections_out,
        "local_only": local_only_out,
        "unmapped_drive_folders": unmapped_drive,
        "summary": {
            "collection_count": len(collections_out),
            "drive_total_bytes": drive_total,
            "drive_total_human": _human_bytes(drive_total),
            "on_drive_count": sum(1 for c in collections_out if c.get("on_drive")),
            "on_local_count": sum(1 for c in collections_out if c.get("on_local")),
            "canonical_only_count": sum(1 for c in collections_out if c.get("tier") == "canonical_only"),
        },
    }


def print_summary(manifest: dict[str, Any]) -> None:
    s = manifest["summary"]
    print(f"Canonical: {manifest['canonical_root']}")
    print(f"Generated: {manifest['generated_at']}")
    print(f"Mapped collections: {s['collection_count']} | on Drive: {s['on_drive_count']} | local copy: {s['on_local_count']}")
    print(f"Drive total (mapped): {s['drive_total_human']}")
    if manifest.get("unmapped_drive_folders"):
        print(f"Unmapped Drive folders: {', '.join(manifest['unmapped_drive_folders'])}")
    print()
    print(f"{'ID':<24} {'DRIVE':>12} {'LOCAL':>12} {'COV':>6}  tier")
    for row in sorted(
        manifest["collections"],
        key=lambda r: -int((r.get("drive") or {}).get("bytes") or 0),
    ):
        drive_h = (row.get("drive") or {}).get("human", "—")
        if drive_h in {"0 B", "—"} and row.get("drive_size_hint"):
            drive_h = str(row["drive_size_hint"])
        local = row.get("local") or {}
        local_h = local.get("human", "—") if local.get("exists") else "missing"
        cov = row.get("local_coverage_ratio")
        cov_s = f"{cov:.0%}" if cov is not None else "—"
        print(f"{row['id']:<24} {drive_h:>12} {local_h:>12} {cov_s:>6}  {row.get('tier')}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pretty", action="store_true", help="Print table summary to stdout")
    ap.add_argument("--quick", action="store_true", help="Skip slow rclone size (folder list + local du only)")
    ap.add_argument("--drive-only", action="store_true", help="Skip local du measurements")
    ap.add_argument("-o", "--output", type=Path, default=MANIFEST_PATH)
    args = ap.parse_args()
    output = args.output if args.output.is_absolute() else (REPO / args.output).resolve()

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(quick=args.quick, drive_only=args.drive_only)
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (INDEX_DIR / "layout.json").write_text(PARTITIONS_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    if args.pretty:
        print_summary(manifest)
        print(f"\nWrote {output.relative_to(REPO)}")
    else:
        print(json.dumps(manifest["summary"], indent=2))
        print(f"manifest: {output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
