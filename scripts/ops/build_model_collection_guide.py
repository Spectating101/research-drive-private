#!/usr/bin/env python3
"""Build model-friendly collection guides from partitions + inventory + semantic config.

Outputs:
  data_lake/collection/_index/MODEL_GUIDE.json  — structured for LLM/tool routing
  data_lake/collection/_index/MODEL_GUIDE.md    — readable explainer
  Enriched per-partition README.md under data_lake/collection/{path}/

Usage:
  python scripts/ops/build_model_collection_guide.py
  python scripts/ops/build_model_collection_guide.py --upload  # also publish to GDrive
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

PARTITIONS_PATH = REPO / "config/collection_partitions.json"
SEMANTIC_PATH = REPO / "config/collection_semantic.json"
MANIFEST_PATH = REPO / "data_lake/collection/_index/manifest_latest.json"
COLLECTION_ROOT = REPO / "data_lake/collection"
OUT_JSON = COLLECTION_ROOT / "_index/MODEL_GUIDE.json"
OUT_MD = COLLECTION_ROOT / "_index/MODEL_GUIDE.md"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _sync_status(manifest_row: dict[str, Any] | None, part: dict[str, Any]) -> dict[str, Any]:
    m = manifest_row or {}
    drive = m.get("drive") or {}
    local = m.get("local") or {}
    drive_bytes = drive.get("bytes")
    local_bytes = int((local or {}).get("bytes") or 0)
    on_drive = bool(m.get("on_drive")) or bool(drive_bytes and int(drive_bytes or 0) > 10_000)
    drive_human = drive.get("human") or part.get("drive_size_hint") or "—"
    local_human = local.get("human") or "—"

    if not on_drive and local_bytes > 0:
        status = "local_only_pending_upload"
        model_note = "Bytes exist on desk/USB but partition folder on Drive is empty or stub — hydrate unavailable until backfill completes."
    elif on_drive and local_bytes > 0 and drive_bytes and int(drive_bytes) < local_bytes * 0.5:
        status = "drive_behind_local"
        model_note = "Drive has data but local cache is larger — incremental backfill may still be running."
    elif on_drive:
        status = "on_drive"
        model_note = "Canonical copy on GDrive. Hydrate to desk only if you need local pandas/SQLite speed."
    elif str(part.get("tier") or "") == "ops" and not part.get("target_drive_path"):
        status = "local_ops_only"
        model_note = "Operator state — never shared; not on professor Drive map."
    else:
        status = "unknown"
        model_note = "Check inventory manifest."

    return {
        "status": status,
        "model_note": model_note,
        "drive_size": drive_human,
        "local_size": local_human,
        "on_drive": on_drive,
        "on_local": bool(local.get("exists")),
        "local_coverage_ratio": m.get("local_coverage_ratio"),
    }


def _semantic_for_partition(semantic_cfg: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    pid = str(part["id"])
    domain = str(part.get("domain") or "")
    dom_tpl = (semantic_cfg.get("domain_templates") or {}).get(domain) or {}
    override = (semantic_cfg.get("partitions") or {}).get(pid) or {}
    return {
        "topics": override.get("topics") or [domain, pid.split(".", 1)[-1]],
        "use_cases": override.get("use_cases") or dom_tpl.get("use_cases") or [],
        "example_questions": override.get("example_questions") or dom_tpl.get("example_questions") or [],
        "key_artifacts": override.get("key_artifacts") or part.get("subfolders") or [],
        "related_partition_ids": override.get("related") or [],
        "registry_handles": override.get("registry_handles") or part.get("registry_dataset_ids") or [],
    }


def _partition_guide_row(
    part: dict[str, Any],
    cfg: dict[str, Any],
    manifest_row: dict[str, Any] | None,
    semantic_cfg: dict[str, Any],
) -> dict[str, Any]:
    sync = _sync_status(manifest_row, part)
    sem = _semantic_for_partition(semantic_cfg, part)
    target = str(part.get("target_drive_path") or "")
    return {
        "id": part["id"],
        "domain": part.get("domain"),
        "path": part.get("path"),
        "title": part.get("title"),
        "professor_label": part.get("professor_label") or part.get("title"),
        "description": part.get("description", ""),
        "tier": part.get("tier"),
        "target_drive_path": target,
        "drive_remote": f"{cfg['canonical_root'].rstrip('/')}/{target}" if target else None,
        "handle": f"partition:{part['id']}",
        "sync": sync,
        "semantic": sem,
        "chat_line": (
            f"{part.get('professor_label') or part.get('title')} ({part.get('domain')}) — "
            f"{sync['status']}: {part.get('description', '')[:180]}"
        ),
        "model_action": (
            "hydrate" if sync["status"] == "on_drive" and not sync["on_local"] else
            "backfill_pending" if sync["status"] in {"local_only_pending_upload", "drive_behind_local"} else
            "query_local" if sync["on_local"] else "info"
        ),
    }


def _render_partition_readme(row: dict[str, Any]) -> str:
    sem = row["semantic"]
    sync = row["sync"]
    lines = [
        f"# {row['professor_label']}",
        "",
        row["description"],
        "",
        "## For AI assistants",
        "",
        f"- **Partition ID:** `{row['id']}`",
        f"- **Drive path:** `{row['target_drive_path'] or '—'}`",
        f"- **Status:** `{sync['status']}` — {sync['model_note']}",
        f"- **Suggested action:** `{row['model_action']}`",
        "",
        "### Good questions to answer from this folder",
        "",
    ]
    for q in sem.get("example_questions") or []:
        lines.append(f"- {q}")
    if sem.get("use_cases"):
        lines.extend(["", "### Use cases", ""])
        for u in sem["use_cases"]:
            lines.append(f"- {u}")
    if sem.get("topics"):
        lines.extend(["", "### Topics", "", ", ".join(f"`{t}`" for t in sem["topics"]), ""])
    if sem.get("key_artifacts"):
        lines.extend(["", "### Key files / subfolders", ""])
        for a in sem["key_artifacts"]:
            lines.append(f"- `{a}`")
    if sem.get("related_partition_ids"):
        lines.extend(["", "### Related partitions", ""])
        for r in sem["related_partition_ids"]:
            lines.append(f"- `{r}`")
    if sync.get("drive_size") or sync.get("local_size"):
        lines.extend(
            [
                "",
                "## Size",
                "",
                f"- Drive: {sync.get('drive_size', '—')}",
                f"- Local staging: {sync.get('local_size', '—')}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def _render_model_guide_md(guide: dict[str, Any]) -> str:
    lines = [
        "# Research collection — model guide",
        "",
        f"_Generated {guide['generated_at']}_",
        "",
        guide.get("system_hint", ""),
        "",
        "## How to route questions",
        "",
        "1. Match the user question to a **partition** below (topics + example questions).",
        "2. Open `collection/{domain}/{folder}/` on GDrive — that is canonical.",
        "3. If `model_action` is `hydrate`, pull bytes to desk before pandas/SQLite work.",
        "4. If `sync.status` is `local_only_pending_upload`, tell the user backfill is pending.",
        "",
        "## Domains",
        "",
    ]
    for domain, blurb in sorted((guide.get("domains") or {}).items()):
        if domain == "backend":
            continue
        lines.append(f"- **{domain}** — {blurb}")
    lines.extend(["", "## Partitions (semantic index)", ""])
    for row in guide.get("partitions") or []:
        if row.get("domain") == "backend":
            continue
        lines.append(f"### {row['professor_label']} (`{row['id']}`)")
        lines.append("")
        lines.append(f"**Path:** `{row.get('target_drive_path') or '—'}` · **Status:** `{row['sync']['status']}` · **Action:** `{row['model_action']}`")
        lines.append("")
        lines.append(row["description"][:400])
        lines.append("")
        qs = row["semantic"].get("example_questions") or []
        if qs:
            lines.append("**Example questions:** " + "; ".join(qs[:3]))
            lines.append("")
    lines.extend(
        [
            "## Machine-readable",
            "",
            "See `MODEL_GUIDE.json` in this folder for the full structured index.",
            "",
        ]
    )
    return "\n".join(lines)


def build_guide(*, write_readmes: bool = True) -> dict[str, Any]:
    cfg = _load_json(PARTITIONS_PATH)
    semantic_cfg = _load_json(SEMANTIC_PATH)
    manifest = _load_json(MANIFEST_PATH)
    by_id = {r.get("id"): r for r in manifest.get("collections") or []}

    rows = [
        _partition_guide_row(part, cfg, by_id.get(str(part["id"])), semantic_cfg)
        for part in cfg.get("partitions") or []
    ]

    guide = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": 1,
        "canonical_root": cfg.get("canonical_root"),
        "professor_share_root": cfg.get("professor_share_root", "collection"),
        "system_hint": semantic_cfg.get("model_system_hint", ""),
        "domains": cfg.get("domains") or {},
        "partition_count": len(rows),
        "summary": {
            "on_drive": sum(1 for r in rows if r["sync"]["status"] == "on_drive"),
            "pending_upload": sum(1 for r in rows if r["sync"]["status"] == "local_only_pending_upload"),
            "drive_behind_local": sum(1 for r in rows if r["sync"]["status"] == "drive_behind_local"),
        },
        "partitions": rows,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(guide, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT_MD.write_text(_render_model_guide_md(guide), encoding="utf-8")

    if write_readmes:
        for part, row in zip(cfg.get("partitions") or [], rows):
            if not part.get("path"):
                continue
            slot = COLLECTION_ROOT / str(part["path"])
            slot.mkdir(parents=True, exist_ok=True)
            (slot / "README.md").write_text(_render_partition_readme(row), encoding="utf-8")

    from scripts.research_data_mcp.collection_dictionary import write_dictionary

    write_dictionary(REPO)
    return guide


def upload_to_gdrive() -> int:
    cfg = _load_json(PARTITIONS_PATH)
    remote_root = str(cfg["canonical_root"]).rstrip("/")
    uploads: list[tuple[Path, str]] = [
        (OUT_JSON, f"{remote_root}/collection/_index"),
        (OUT_MD, f"{remote_root}/collection/_index"),
    ]
    for readme in sorted(COLLECTION_ROOT.rglob("README.md")):
        rel = readme.relative_to(COLLECTION_ROOT)
        if rel.parts and rel.parts[0].startswith("_"):
            continue
        dst = f"{remote_root}/collection/{rel.parent}" if rel.parent.parts else f"{remote_root}/collection"
        uploads.append((readme, dst))

    nav_script = REPO / "scripts/ops/publish_gdrive_partition_nav.py"
    proc = subprocess.run(
        [sys.executable, str(nav_script), "--upload"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return proc.returncode

    for src, dst in uploads:
        subprocess.run(
            ["rclone", "copyto", str(src), f"{dst}/{src.name}", "--drive-acknowledge-abuse"],
            cwd=REPO,
            check=False,
            timeout=120,
        )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--upload", action="store_true", help="Publish MODEL_GUIDE + READMEs to GDrive")
    ap.add_argument("--no-readmes", action="store_true")
    args = ap.parse_args()

    guide = build_guide(write_readmes=not args.no_readmes)
    s = guide["summary"]
    print(f"MODEL_GUIDE: {OUT_JSON.relative_to(REPO)}")
    print(f"  partitions={guide['partition_count']} on_drive={s['on_drive']} pending_upload={s['pending_upload']} drift={s['drive_behind_local']}")

    if args.upload:
        return upload_to_gdrive()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
