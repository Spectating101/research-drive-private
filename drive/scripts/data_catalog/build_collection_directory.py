#!/usr/bin/env python3
"""Scaffold the research collection directory tree under data_lake/collection/.

Reads config/collection_partitions.json and creates:
  - domain folders with human-readable README snippets
  - per-partition meta.json (legacy + target Drive paths, local storage)
  - data_lake/collection/INDEX.json (machine-readable catalog)
  - optional STORAGE symlink to legacy_local_path for navigation

Usage:
  python scripts/data_catalog/build_collection_directory.py
  python scripts/data_catalog/build_collection_directory.py --link-storage
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from sharpe_kernel.paths import repo_root_from_file

REPO = repo_root_from_file(__file__)
PARTITIONS_PATH = REPO / "config/collection_partitions.json"
COLLECTION_ROOT = REPO / "data_lake/collection"
INDEX_DIR = COLLECTION_ROOT / "_index"


def load_partitions() -> dict[str, Any]:
    return json.loads(PARTITIONS_PATH.read_text(encoding="utf-8"))


def _local_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False}
    if path.is_symlink():
        return {"exists": True, "symlink": True, "target": str(path.resolve())}
    return {"exists": True, "symlink": False, "is_dir": path.is_dir()}


def partition_meta(cfg: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    root = str(cfg["canonical_root"]).rstrip("/")
    legacy_drive = part.get("legacy_drive_path")
    target_drive = part.get("target_drive_path")
    legacy_local = part.get("legacy_local_path")
    return {
        "id": part["id"],
        "domain": part["domain"],
        "title": part["title"],
        "description": part.get("description", ""),
        "tier": part.get("tier"),
        "status": part.get("status", "mapped"),
        "drive_size_hint": part.get("drive_size_hint"),
        "subfolders": part.get("subfolders") or [],
        "registry_dataset_ids": part.get("registry_dataset_ids") or [],
        "replaces_legacy_name": part.get("replaces_legacy_name"),
        "canonical": {
            "drive_root": root,
            "legacy_path": legacy_drive,
            "legacy_remote": f"{root}/{legacy_drive}" if legacy_drive else None,
            "target_path": target_drive,
            "target_remote": f"{root}/{target_drive}" if target_drive else None,
        },
        "local": {
            "legacy_path": legacy_local,
            "collection_slot": f"data_lake/collection/{part['path']}",
            "stats": _local_stats(REPO / legacy_local) if legacy_local else {"exists": False},
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def domain_readme(domain: str, blurb: str, parts: list[dict[str, Any]]) -> str:
    lines = [
        f"# {domain.title()}",
        "",
        blurb,
        "",
        "## What's in this folder",
        "",
        "| Folder | What you get |",
        "|--------|----------------|",
    ]
    for p in sorted(parts, key=lambda x: x.get("path", "")):
        label = p.get("professor_label") or p.get("title") or p["id"]
        leaf = p["path"].split("/", 1)[-1]
        desc = (p.get("description") or "").split(".")[0].strip()
        if desc:
            desc = desc + "."
        lines.append(f"| `{leaf}/` | **{label}** — {desc} |")
    lines.extend(["", "## Partitions (detail)", ""])
    for p in sorted(parts, key=lambda x: x.get("path", "")):
        label = p.get("professor_label") or p.get("title")
        lines.append(f"### {label}")
        lines.append("")
        lines.append(p.get("description") or "")
        if p.get("drive_size_hint"):
            lines.append(f"\n_Approx size on Drive: {p['drive_size_hint']}_")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build(*, link_storage: bool) -> dict[str, Any]:
    cfg = load_partitions()
    domains = cfg.get("domains") or {}
    parts: list[dict[str, Any]] = list(cfg.get("partitions") or [])

    COLLECTION_ROOT.mkdir(parents=True, exist_ok=True)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    by_domain: dict[str, list[dict[str, Any]]] = {}
    index_rows: list[dict[str, Any]] = []

    for part in parts:
        domain = str(part["domain"])
        by_domain.setdefault(domain, []).append(part)
        slot = COLLECTION_ROOT / part["path"]
        slot.mkdir(parents=True, exist_ok=True)

        meta = partition_meta(cfg, part)
        (slot / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        label = part.get("professor_label") or part.get("title") or part["id"]
        readme_body = part.get("description") or ""
        if readme_body:
            part_readme = f"# {label}\n\n{readme_body}\n"
            if part.get("drive_size_hint"):
                part_readme += f"\n_Approx size on Drive: {part['drive_size_hint']}_\n"
            (slot / "README.md").write_text(part_readme, encoding="utf-8")

        legacy_local = part.get("legacy_local_path")
        storage_link = slot / "STORAGE"
        if link_storage and legacy_local:
            target = REPO / str(legacy_local)
            if target.exists():
                if storage_link.is_symlink() or storage_link.exists():
                    storage_link.unlink()
                storage_link.symlink_to(target.resolve())

        index_rows.append(
            {
                "id": part["id"],
                "domain": domain,
                "path": part["path"],
                "title": part["title"],
                "legacy_drive_path": part.get("legacy_drive_path"),
                "target_drive_path": part.get("target_drive_path"),
                "legacy_local_path": legacy_local,
                "tier": part.get("tier"),
                "status": part.get("status", "mapped"),
                "drive_size_hint": part.get("drive_size_hint"),
                "shard_manifest": part.get("shard_manifest"),
            }
        )

    shard_rows: list[dict[str, Any]] = []
    try:
        from scripts.research_data_mcp.collection_resolve import list_shards

        for shard in list_shards(REPO):
            slot = COLLECTION_ROOT / "catalog/datacite/harvest/shards" / shard["shard"]
            slot.mkdir(parents=True, exist_ok=True)
            shard_meta = {
                "shard": shard["shard"],
                "parent_partition": "catalog.datacite-harvest",
                "host": shard.get("host"),
                "query": shard.get("query"),
                "target_records": shard.get("target_records"),
                "legacy_local_glob": f"data_lake/dataset_catalog/index_v3/{shard['shard']}",
                "target_drive_glob": f"collection/catalog/datacite/harvest/index_v3/{shard['shard']}",
            }
            (slot / "meta.json").write_text(json.dumps(shard_meta, indent=2), encoding="utf-8")
            shard_rows.append(shard_meta)
    except Exception:
        shard_rows = []

    for domain, domain_parts in sorted(by_domain.items()):
        domain_dir = COLLECTION_ROOT / domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        readme = domain_readme(domain, str(domains.get(domain, "")), domain_parts)
        (domain_dir / "README.md").write_text(readme, encoding="utf-8")

    tree_lines = ["collection/"]
    for domain in sorted(by_domain):
        tree_lines.append(f"├── {domain}/")
        for i, part in enumerate(sorted(by_domain[domain], key=lambda p: p["path"])):
            branch = "└──" if i == len(by_domain[domain]) - 1 else "├──"
            tree_lines.append(f"│   {branch} {part['path'].split('/', 1)[-1]}/")
    tree_text = "\n".join(tree_lines)

    index = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": cfg.get("version"),
        "canonical_root": cfg["canonical_root"],
        "collection_root": cfg["collection_root"],
        "target_drive_prefix": cfg.get("target_drive_prefix"),
        "partition_count": len(index_rows),
        "domains": domains,
        "partitions": index_rows,
        "datacite_shards": shard_rows,
        "tree": tree_text,
    }
    (COLLECTION_ROOT / "INDEX.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    (INDEX_DIR / "partitions.json").write_text(
        PARTITIONS_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    scale_path = REPO / "config/collection_scale.json"
    if scale_path.is_file():
        (INDEX_DIR / "scale.json").write_text(scale_path.read_text(encoding="utf-8"), encoding="utf-8")

    root_readme = f"""# Research data collection

**Share this folder with professors.** Everything lives under `collection/` on Drive.

- **Vault:** `{cfg['canonical_root']}`
- **Layout:** `{cfg.get('target_drive_prefix', 'collection')}/{{domain}}/{{dataset}}/`

Each domain folder has a **README** explaining what's inside. Open the domain that matches your research question (markets, news, official, …).

Regenerate local navigation tree:

```bash
python scripts/data_catalog/build_collection_directory.py --link-storage
python scripts/ops/publish_gdrive_partition_nav.py --upload
```

## Domain tree

```
{tree_text}
```

## Quick picks (common asks)

| You want… | Open |
|-----------|------|
| Taiwan stocks / TWSE | `official/exchange-disclosures/` |
| USDT / stablecoin on-chain | `markets/ethereum-usdt/` |
| Asia stock prices | `markets/equities-asia/` |
| News shocks / GDELT | `news/gdelt-asia/` |
| Something the desk downloaded | `acquired/procured/` |
| NFT metadata | `markets/nft-opensea/` (local) or procured |
"""
    (COLLECTION_ROOT / "README.md").write_text(root_readme, encoding="utf-8")

    return index


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--link-storage",
        action="store_true",
        help="Symlink each partition's STORAGE -> legacy_local_path when present",
    )
    args = ap.parse_args()
    index = build(link_storage=args.link_storage)
    print(json.dumps({"partition_count": index["partition_count"], "root": str(COLLECTION_ROOT)}, indent=2))
    print(f"Wrote {COLLECTION_ROOT.relative_to(REPO)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
