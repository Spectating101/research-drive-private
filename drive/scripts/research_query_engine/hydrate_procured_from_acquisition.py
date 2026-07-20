#!/usr/bin/env python3
"""Hydrate procured local_path bytes from acquisition staging when missing.

After a remote http_manifest collect, the registration receipt and registry row
may point at ``data_lake/procured/<friendly_id>/`` while bytes still only exist
under ``data_lake/yzu_cluster/acquisitions/<job_id>/raw/``. Query then fails
with an empty tree even though archive+registry proof succeeded.

This helper copies staging files into the registry ``local_path`` without
touching GDrive, tokens, or the job store. It is idempotent and refuses to
overwrite differing existing files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_meta(acquisition_dir: Path) -> dict:
    meta_path = acquisition_dir / "meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"missing acquisition meta: {meta_path}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def hydrate(*, repo_root: Path, job_id: str, dry_run: bool = False) -> dict:
    root = repo_root.resolve()
    acquisition_dir = root / "data_lake/yzu_cluster/acquisitions" / job_id
    meta = _load_meta(acquisition_dir)
    canonical = str(meta.get("canonical_dir") or "").strip()
    if not canonical:
        raise ValueError("meta.canonical_dir is required")

    procured_root = (root / "data_lake/procured").resolve()
    dest = (root / canonical).resolve()
    if procured_root not in dest.parents:
        raise ValueError(f"canonical_dir must resolve under data_lake/procured: {canonical}")

    raw_dir = acquisition_dir / "raw"
    if not raw_dir.is_dir():
        raise FileNotFoundError(f"missing acquisition raw dir: {raw_dir}")

    planned: list[dict] = []
    for src in sorted(p for p in raw_dir.iterdir() if p.is_file()):
        target = dest / src.name
        action = "copy"
        if target.exists():
            if _sha256(target) == _sha256(src):
                action = "skip_identical"
            else:
                action = "refuse_mismatch"
        planned.append(
            {
                "src": str(src.relative_to(root)),
                "dst": str(target.relative_to(root)),
                "action": action,
                "bytes": src.stat().st_size,
            }
        )

    # Optional manifest from meta when absent
    manifest_dst = dest / "manifest.json"
    if not manifest_dst.exists():
        planned.append(
            {
                "src": str((acquisition_dir / "meta.json").relative_to(root)),
                "dst": str(manifest_dst.relative_to(root)),
                "action": "write_manifest_from_meta",
                "bytes": None,
            }
        )

    if any(row["action"] == "refuse_mismatch" for row in planned):
        return {"ok": False, "job_id": job_id, "dest": str(dest.relative_to(root)), "files": planned}

    if not dry_run:
        dest.mkdir(parents=True, exist_ok=True)
        for row in planned:
            if row["action"] == "copy":
                shutil.copy2(root / row["src"], root / row["dst"])
            elif row["action"] == "write_manifest_from_meta":
                payload = {
                    "manifest_id": meta.get("manifest_id"),
                    "dataset_id": meta.get("dataset_id"),
                    "job_id": meta.get("job_id") or job_id,
                    "files": meta.get("files"),
                    "source": "hydrated_from_acquisition_staging",
                }
                manifest_dst.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    return {
        "ok": True,
        "job_id": job_id,
        "dataset_id": meta.get("dataset_id"),
        "dest": str(dest.relative_to(root)),
        "dry_run": dry_run,
        "files": planned,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        result = hydrate(repo_root=args.repo_root, job_id=args.job_id, dry_run=args.dry_run)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())