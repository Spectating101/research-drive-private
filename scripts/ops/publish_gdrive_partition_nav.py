#!/usr/bin/env python3
"""Publish START_HERE.md + PARTITION_MAP.json to the GDrive vault root.

When you open Google Drive in the browser you still see *legacy* folder names
(news_shock_taxonomy, market_data, …). This file is the human map at the vault
root so you know what each folder means and where the clean layout will land.

Usage:
  python scripts/ops/publish_gdrive_partition_nav.py
  python scripts/ops/publish_gdrive_partition_nav.py --dry-run
  python scripts/ops/publish_gdrive_partition_nav.py --upload
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
PARTITIONS_PATH = REPO / "config/collection_partitions.json"
OUT_DIR = REPO / "data_lake/collection/_index/gdrive_nav"

# Folders on Drive that are not in collection_partitions.json yet.
EXTRA_DRIVE_FOLDERS: list[dict[str, str]] = [
    {
        "legacy_drive_path": "collection_queue",
        "title": "Collection queue job outputs (new)",
        "description": "Per-task archives from data_collection_queue jobs (e.g. sec_company_tickers). "
        "Target: collection/ops/collection-queue/{task_id}/ when migrated.",
        "domain": "ops",
    },
]


def _load_partitions() -> dict[str, Any]:
    return json.loads(PARTITIONS_PATH.read_text(encoding="utf-8"))


def _rclone_lsd(remote_root: str) -> list[str]:
    proc = subprocess.run(
        ["rclone", "lsd", remote_root],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        return []
    names: list[str] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if parts:
            names.append(parts[-1])
    return sorted(names)


def _build_map(cfg: dict[str, Any], drive_folders: list[str]) -> dict[str, Any]:
    parts = list(cfg.get("partitions") or [])
    rows: list[dict[str, Any]] = []
    legacy_on_drive: dict[str, dict[str, Any]] = {}

    for part in parts:
        legacy = part.get("legacy_drive_path")
        row = {
            "id": part["id"],
            "domain": part["domain"],
            "title": part["title"],
            "professor_label": part.get("professor_label"),
            "description": part.get("description", ""),
            "legacy_drive_path": legacy,
            "target_drive_path": part.get("target_drive_path"),
            "drive_size_hint": part.get("drive_size_hint"),
            "on_drive_now": bool(legacy and legacy.split("/")[0] in drive_folders),
            "status": part.get("status", "mapped"),
        }
        rows.append(row)
        if legacy:
            top = legacy.split("/")[0]
            legacy_on_drive[top] = row

    extras: list[dict[str, Any]] = []
    for extra in EXTRA_DRIVE_FOLDERS:
        path = extra["legacy_drive_path"]
        extras.append(
            {
                **extra,
                "on_drive_now": path.split("/")[0] in drive_folders,
                "target_drive_path": None,
            }
        )

    unmapped = [
        name
        for name in drive_folders
        if name not in legacy_on_drive
        and name not in {e["legacy_drive_path"].split("/")[0] for e in EXTRA_DRIVE_FOLDERS}
        and name not in ("START_HERE.md", "PARTITION_MAP.json", "collection")
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "canonical_root": cfg["canonical_root"],
        "browser_path": "My Drive → Machine_Archive → molina_workbench → Sharpe-Renaissance-data",
        "drive_folder_count": len(drive_folders),
        "drive_folders": drive_folders,
        "migration_note": (
            "Physical folders on Drive still use legacy names. "
            "The clean tree collection/{domain}/… exists locally under data_lake/collection/ "
            "and is the target after rclone migrate. Open START_HERE.md here first."
        ),
        "partitions": rows,
        "extra_drive_folders": extras,
        "unmapped_drive_folders": unmapped,
    }


def _migration_complete(cfg: dict[str, Any]) -> bool:
    parts = cfg.get("partitions") or []
    with_legacy = [p for p in parts if p.get("legacy_drive_path") and p.get("target_drive_path")]
    if not with_legacy:
        return True
    pending = [p for p in with_legacy if p.get("status") != "migrated"]
    return len(pending) == 0


def _render_start_here(cfg: dict[str, Any], manifest: dict[str, Any]) -> str:
    migrated = _migration_complete(cfg)
    lines = [
        "# Sharpe-Renaissance research data — START HERE",
        "",
        f"_Generated {manifest['generated_at']}_",
        "",
        "## Where to browse",
        "",
        f"**Google Drive:** `{manifest['browser_path']}` → open **`collection/`**",
        "",
        f"**Rclone:** `{cfg['canonical_root']}/collection`",
        "",
    ]

    if migrated:
        lines.extend(
            [
                "All research data is under **`collection/{domain}/{dataset}/`**. "
                "Each domain folder has a README. Legacy root folders have been retired.",
                "",
                "## Share link",
                "",
                "Right-click **`collection`** → Share. That single link covers markets, news, official filings, procured downloads, etc.",
                "",
                "## What's inside (by domain)",
                "",
                "| Domain folder | What's in it |",
                "|---------------|----------------|",
            ]
        )
        by_domain: dict[str, list[dict[str, Any]]] = {}
        for part in cfg.get("partitions") or []:
            if part.get("status") in {"local_only"} or not part.get("target_drive_path"):
                continue
            if part.get("professor_visible") is False:
                continue
            dom = str(part.get("domain") or "")
            by_domain.setdefault(dom, []).append(part)
        for domain in sorted(by_domain):
            blurb = (cfg.get("domains") or {}).get(domain, "")
            lines.append(f"| `collection/{domain}/` | {blurb} |")
        lines.extend(["", "## Datasets (open these folders)", ""])
        lines.append("| Path under `collection/` | Label | Size |")
        lines.append("|--------------------------|-------|------|")
        for part in sorted(
            [p for p in cfg.get("partitions") or [] if p.get("target_drive_path") and p.get("professor_visible") is not False],
            key=lambda r: (r.get("domain", ""), r.get("path", "")),
        ):
            if part.get("status") == "local_only":
                continue
            rel = str(part.get("target_drive_path") or "").replace("collection/", "", 1)
            label = part.get("professor_label") or part.get("title") or part["id"]
            size = part.get("drive_size_hint") or "—"
            lines.append(f"| `{rel}/` | {label} | {size} |")
    else:
        lines.extend(
            [
                "Migration in progress — some data may still appear under **legacy** root names. "
                "Prefer **`collection/`** when present.",
                "",
                "## Folder map",
                "",
                "| Legacy (old) | Size | Label | New path under collection/ |",
                "|--------------|------|-------|----------------------------|",
            ]
        )
        for part in sorted(manifest["partitions"], key=lambda r: (r["domain"], r.get("legacy_drive_path") or "")):
            legacy = part.get("legacy_drive_path")
            if not legacy or part.get("status") == "local_only":
                continue
            size = part.get("drive_size_hint") or "—"
            target = (part.get("target_drive_path") or "").replace("collection/", "", 1) or "—"
            label = part.get("title") or part["id"]
            on = "✓" if part.get("status") == "migrated" else "…"
            lines.append(f"| `{legacy}` {on} | {size} | {label} | `{target}/` |")

    lines.extend(["", "## Domains", ""])
    for domain, blurb in sorted((cfg.get("domains") or {}).items()):
        if domain == "backend":
            continue
        lines.append(f"- **`{domain}/`** — {blurb}")

    lines.extend(
        [
            "",
            "## Backend (do not share)",
            "",
            "`datacite_catalog/` at vault root — operator DataCite bulk harvest only.",
            "",
            "## Machine-readable map",
            "",
            "- `PARTITION_MAP.json` — folder layout",
            "- `collection/_index/MODEL_GUIDE.json` — **semantic index for AI assistants** (topics, example questions, sync status)",
            "- `collection/_index/MODEL_GUIDE.md` — readable version of the same",
            "",
            "Source: `config/collection_partitions.json` + `config/collection_semantic.json`",
            "",
            "## Regenerate",
            "",
            "```bash",
            "python scripts/ops/apply_partition_professor_labels.py",
            "python scripts/ops/build_model_collection_guide.py",
            "python scripts/data_catalog/build_collection_directory.py --link-storage",
            "python scripts/ops/publish_gdrive_partition_nav.py --upload",
            "```",
            "",
        ]
    )

    if manifest.get("unmapped_drive_folders"):
        lines.append("## Unmapped Drive folders")
        lines.append("")
        for name in manifest["unmapped_drive_folders"]:
            lines.append(f"- `{name}`")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Write local files only")
    ap.add_argument("--upload", action="store_true", help="rclone copy to canonical vault root")
    args = ap.parse_args()

    cfg = _load_partitions()
    remote_root = str(cfg["canonical_root"]).rstrip("/")
    drive_folders = _rclone_lsd(remote_root)

    manifest = _build_map(cfg, drive_folders)
    start_here = _render_start_here(cfg, manifest)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    start_path = OUT_DIR / "START_HERE.md"
    map_path = OUT_DIR / "PARTITION_MAP.json"
    start_path.write_text(start_here, encoding="utf-8")
    map_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Wrote {start_path.relative_to(REPO)}")
    print(f"Wrote {map_path.relative_to(REPO)}")
    print(f"Drive folders ({len(drive_folders)}): {', '.join(drive_folders) or '(rclone failed)'}")

    if args.dry_run or not args.upload:
        if not args.upload:
            print("Pass --upload to copy nav files to GDrive vault root + collection/.", file=sys.stderr)
        return 0

    uploads: list[tuple[Path, str]] = [
        (start_path, remote_root),
        (map_path, remote_root),
    ]
    coll_readme = REPO / "data_lake/collection/README.md"
    if coll_readme.is_file():
        uploads.append((coll_readme, f"{remote_root}/collection"))
    for readme in sorted((REPO / "data_lake/collection").rglob("README.md")):
        rel = readme.relative_to(REPO / "data_lake/collection")
        if rel.parts and rel.parts[0].startswith("_"):
            continue
        dst = f"{remote_root}/collection/{rel.parent}" if rel.parent.parts else f"{remote_root}/collection"
        uploads.append((readme, dst))

    for src, dst in uploads:
        proc = subprocess.run(
            ["rclone", "copy", str(src), dst, "-v"],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if proc.returncode != 0:
            print(proc.stderr or proc.stdout, file=sys.stderr)
            return proc.returncode
        print(f"Uploaded {src.name} → {dst}/")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
