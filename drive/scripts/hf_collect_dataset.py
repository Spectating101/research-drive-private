#!/usr/bin/env python3
"""Download a Hugging Face dataset shard into data_lake/procured/huggingface for registry promotion."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.research_data_mcp.hf_loader import HF_CACHE_ROOT, parquet_splits
from scripts.research_data_mcp import hf_catalog


def _stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def hf_slug(dataset_id: str) -> str:
    return dataset_id.strip().removeprefix("hf:").replace("/", "__")


def registry_dataset_id(dataset_id: str) -> str:
    return f"hf_{hf_slug(dataset_id)}"


def _download_url(url: str, dest: Path, *, max_bytes: int = 500_000_000) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "ResearchDrive/1.0"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"shard exceeds cap ({max_bytes} bytes)")
    dest.write_bytes(data)
    return len(data)


def collect_dataset(
    repo_root: Path,
    dataset_id: str,
    *,
    split: str = "train",
    max_shards: int = 2,
    max_bytes_per_shard: int = 50_000_000,
) -> dict:
    did = dataset_id.strip().removeprefix("hf:")
    meta = hf_catalog.get_dataset(did)
    slug = hf_slug(did)
    out_dir = repo_root / HF_CACHE_ROOT / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    files: list[dict[str, Any]] = []
    splits = parquet_splits(did)
    chosen = [s for s in splits if str(s.get("split") or "") == split or split == "any"]
    if not chosen:
        chosen = splits[:max_shards]
    else:
        chosen = chosen[:max_shards]

    for entry in chosen:
        url = str(entry.get("url") or "")
        if not url:
            continue
        fname = str(entry.get("filename") or entry.get("split") or "data.parquet")
        if not fname.endswith(".parquet"):
            fname = f"{fname}.parquet"
        dest = out_dir / fname
        nbytes = _download_url(url, dest, max_bytes=max_bytes_per_shard)
        files.append(
            {
                "path": str(dest.relative_to(repo_root)),
                "split": entry.get("split"),
                "config": entry.get("config"),
                "bytes": nbytes,
            }
        )

    primary_parquet = ""
    if not files:
        try:
            from datasets import load_dataset  # type: ignore

            ds = load_dataset(did, split=split, streaming=False)
            sample_path = out_dir / f"{split}.jsonl"
            count = 0
            with sample_path.open("w", encoding="utf-8") as fh:
                for row in ds:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    count += 1
                    if count >= 5000:
                        break
            files.append({"path": str(sample_path.relative_to(repo_root)), "split": split, "bytes": sample_path.stat().st_size})
        except Exception as exc:
            raise RuntimeError(f"no parquet splits and datasets library failed: {exc}") from exc
    else:
        primary_parquet = files[0]["path"]

    manifest = {
        "dataset_id": did,
        "registry_dataset_id": registry_dataset_id(did),
        "slug": slug,
        "title": meta.get("title") or did,
        "collected_at": _stamp(),
        "source": "huggingface",
        "files": files,
        "primary_parquet": primary_parquet,
        "canonical_dir": str(out_dir.relative_to(repo_root)),
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return {
        "ok": True,
        "hf_dataset_id": did,
        "dataset_id": manifest["registry_dataset_id"],
        "canonical_dir": manifest["canonical_dir"],
        "manifest_path": str(manifest_path.relative_to(repo_root)),
        "materialized": manifest,
        "files": files,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset-id", required=True, help="HF dataset id org/name")
    ap.add_argument("--split", default="train")
    ap.add_argument("--max-shards", type=int, default=2)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    out = collect_dataset(REPO, args.dataset_id, split=args.split, max_shards=args.max_shards)
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
