#!/usr/bin/env python3
"""Stream-build FTS topic indexes — full_index monolith + per-shard index_v3 pieces."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterator

from scripts.data_catalog.topic_index_paths import index_v3_root, shard_index_dir, topic_index_root

INDEX_VERSION = 3
SHARD_GLOB = "datacite_*.jsonl.gz"
COMPACT_PAYLOAD = os.environ.get("DATACITE_COMPACT_FTS_PAYLOAD", "1") != "0"
COMMIT_EVERY = int(os.environ.get("DATACITE_FTS_COMMIT_EVERY", "25000"))


def topic_root(repo_root: Path) -> Path:
    return topic_index_root(repo_root)


def shard_index_path(repo_root: Path, shard: str) -> Path:
    safe = shard.replace("/", "_")
    return shard_index_dir(repo_root) / f"{safe}.sqlite3"


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _compact_payload(raw: dict[str, Any]) -> dict[str, Any]:
    attrs = raw.get("attributes") if isinstance(raw.get("attributes"), dict) else {}
    tags = raw.get("tags") or raw.get("subjects") or []
    if not tags and attrs:
        tags = [s.get("subject") for s in (attrs.get("subjects") or []) if isinstance(s, dict)]
    doi = str(raw.get("doi") or raw.get("id") or raw.get("dataset_id") or "").removeprefix("doi:")
    title = str(raw.get("title") or "")
    if not title and attrs.get("titles"):
        t0 = attrs["titles"][0]
        if isinstance(t0, dict):
            title = str(t0.get("title") or "")
    return {
        "doi": doi,
        "title": title[:500],
        "domain": raw.get("domain"),
        "tags": tags[:40] if isinstance(tags, list) else tags,
        "dataset_id": raw.get("dataset_id") or doi,
    }


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" or path.name.endswith(".jsonl.gz") else open
    mode = "rt"
    try:
        with opener(path, mode, encoding="utf-8", errors="replace") as fh:  # type: ignore[arg-type]
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except (OSError, EOFError, gzip.BadGzipFile):
        return


def _record_fields(row: dict[str, Any]) -> tuple[str, str, str, dict[str, Any]]:
    attrs = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
    titles = attrs.get("titles") or []
    title = str(row.get("title") or "")
    if not title and titles and isinstance(titles[0], dict):
        title = str(titles[0].get("title") or "")
    doi = str(row.get("doi") or row.get("id") or row.get("dataset_id") or "").removeprefix("doi:").strip()
    if doi.lower().startswith("https://doi.org/"):
        doi = doi.split("doi.org/", 1)[-1]
    tags = row.get("tags") or row.get("subjects") or []
    if not tags and attrs:
        tags = [s.get("subject") for s in (attrs.get("subjects") or []) if isinstance(s, dict)]
    if isinstance(tags, list):
        subjects = " ".join(str(t) for t in tags[:40] if t)
    else:
        subjects = str(tags)
    body = " ".join(
        filter(
            None,
            [str(row.get("description") or "")[:1500], str(row.get("domain") or ""), subjects],
        )
    )
    if attrs.get("publisher"):
        body = f"{body} {attrs.get('publisher')}".strip()
    return doi, title[:500], body, row


def build_sqlite_from_jsonl_paths(
    jsonl_paths: list[Path],
    out_path: Path,
    *,
    max_rows: int = 0,
) -> dict[str, Any]:
    if out_path.is_file():
        out_path.unlink()
    conn = _connect(out_path)
    conn.execute(
        """CREATE VIRTUAL TABLE vault_fts USING fts5(
            doi UNINDEXED,
            title,
            body,
            payload_json UNINDEXED,
            tokenize='porter unicode61'
        )"""
    )
    count = 0
    sources: list[str] = []
    for jsonl_path in jsonl_paths:
        if not jsonl_path.is_file():
            continue
        sources.append(str(jsonl_path.name))
        for row in _iter_jsonl(jsonl_path):
            doi, title, body, raw = _record_fields(row)
            if not title and not doi:
                continue
            payload = _compact_payload(raw) if COMPACT_PAYLOAD else raw
            conn.execute(
                "INSERT INTO vault_fts(doi, title, body, payload_json) VALUES (?,?,?,?)",
                (doi, title, body, json.dumps(payload, ensure_ascii=False, default=str)),
            )
            count += 1
            if count % COMMIT_EVERY == 0:
                conn.commit()
            if max_rows and count >= max_rows:
                break
        if max_rows and count >= max_rows:
            break
    conn.commit()
    conn.close()
    return {"row_count": count, "source_files": sources, "index_path": str(out_path)}


def discover_shard_jsonl(repo_root: Path, shard: str) -> list[Path]:
    base = index_v3_root(repo_root) / shard
    if not base.is_dir():
        return []
    return sorted(p for p in base.glob(SHARD_GLOB) if p.is_file() and p.stat().st_size > 0)


def discover_shards_with_local_jsonl(repo_root: Path) -> list[str]:
    root = index_v3_root(repo_root)
    if not root.is_dir():
        return []
    shards: list[str] = []
    for shard_dir in sorted(root.iterdir()):
        if not shard_dir.is_dir():
            continue
        if discover_shard_jsonl(repo_root, shard_dir.name):
            shards.append(shard_dir.name)
    return shards


def shard_index_stale(repo_root: Path, shard: str) -> bool:
    paths = discover_shard_jsonl(repo_root, shard)
    if not paths:
        return False
    out = shard_index_path(repo_root, shard)
    if not out.is_file():
        return True
    idx_mtime = out.stat().st_mtime
    newest = max(p.stat().st_mtime for p in paths)
    return newest > idx_mtime


def _write_shard_manifest(repo_root: Path, entries: list[dict[str, Any]]) -> None:
    out_dir = shard_index_dir(repo_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "version": INDEX_VERSION,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "shard_count": len(entries),
        "total_rows": sum(int(e.get("row_count") or 0) for e in entries),
        "shards": entries,
    }
    (out_dir / "INDEX.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    (topic_root(repo_root) / "shards_meta.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")


def build_shard_topic_index(
    repo_root: Path,
    shard: str,
    *,
    max_rows: int = 0,
    force: bool = False,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    paths = discover_shard_jsonl(repo_root, shard)
    if not paths:
        return {"built": False, "shard": shard, "reason": "no local datacite_*.jsonl.gz"}
    out = shard_index_path(repo_root, shard)
    if not force and not shard_index_stale(repo_root, shard):
        return {"built": False, "shard": shard, "skipped": True, "reason": "index fresh", "index_path": str(out)}
    stats = build_sqlite_from_jsonl_paths(paths, out, max_rows=max_rows)
    entry = {
        "shard": shard,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "built": True,
        "piece_count": len(paths),
        **stats,
    }
    return entry


def build_all_shard_indexes(
    repo_root: Path,
    *,
    only_stale: bool = True,
    shards: list[str] | None = None,
    max_rows: int = 0,
    force: bool = False,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    target = shards or discover_shards_with_local_jsonl(repo_root)
    built: list[dict[str, Any]] = []
    skipped: list[str] = []
    for shard in target:
        if only_stale and not force and not shard_index_stale(repo_root, shard):
            skipped.append(shard)
            continue
        result = build_shard_topic_index(repo_root, shard, max_rows=max_rows, force=force)
        if result.get("built"):
            built.append(result)
        elif result.get("skipped"):
            skipped.append(shard)
    existing = []
    idx_dir = shard_index_dir(repo_root)
    if idx_dir.is_dir():
        for path in sorted(idx_dir.glob("*.sqlite3")):
            shard_name = path.stem
            meta_path = idx_dir / f"{shard_name}.meta.json"
            if meta_path.is_file():
                try:
                    existing.append(json.loads(meta_path.read_text(encoding="utf-8")))
                    continue
                except (OSError, json.JSONDecodeError):
                    pass
            if not any(e.get("shard") == shard_name for e in built):
                existing.append(
                    {
                        "shard": shard_name,
                        "row_count": 0,
                        "index_path": str(path),
                        "built": True,
                        "from_disk": True,
                    }
                )
    entries = built + [e for e in existing if e.get("shard") not in {b.get("shard") for b in built}]
    for entry in built:
        meta = idx_dir / f"{entry['shard']}.meta.json"
        meta.write_text(json.dumps(entry, indent=2), encoding="utf-8")
    _write_shard_manifest(repo_root, entries)
    return {
        "version": INDEX_VERSION,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "shards_built": len(built),
        "shards_skipped": len(skipped),
        "built": built,
        "skipped": skipped,
        "total_shard_rows": sum(int(b.get("row_count") or 0) for b in built),
    }


def build_full_index_topic(repo_root: Path) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    src = repo_root / "data_lake/dataset_catalog/full_index/datacite.jsonl.gz"
    out = topic_root(repo_root) / "full_index.sqlite3"
    if not src.is_file():
        return {"built": False, "reason": "no full_index datacite.jsonl.gz"}
    stats = build_sqlite_from_jsonl_paths([src], out)
    meta = {
        "version": INDEX_VERSION,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "built": True,
        **stats,
    }
    (topic_root(repo_root) / "full_index_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def build_all_topic_indexes(
    repo_root: Path,
    *,
    only_stale: bool = True,
    max_rows: int = 0,
    force: bool = False,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    from scripts.data_catalog.build_curated_topic_fts import build_curated_topic_fts

    curated = build_curated_topic_fts(repo_root)
    full = build_full_index_topic(repo_root)
    shards = build_all_shard_indexes(repo_root, only_stale=only_stale, max_rows=max_rows, force=force)
    return {
        "curated": curated,
        "full_index": full,
        "shards": shards,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Build DataCite vault topic FTS indexes")
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--shard", default="", help="Single index_v3 shard name e.g. y2025_q1")
    ap.add_argument("--all-shards", action="store_true")
    ap.add_argument("--all", action="store_true", help="curated + full_index + shards")
    ap.add_argument("--only-stale", action="store_true", default=False)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--max-rows", type=int, default=0)
    args = ap.parse_args()
    root = Path(args.repo_root)
    if args.all:
        print(json.dumps(build_all_topic_indexes(root, only_stale=args.only_stale or not args.force, force=args.force), indent=2))
        return 0
    if args.all_shards:
        print(
            json.dumps(
                build_all_shard_indexes(root, only_stale=args.only_stale or not args.force, max_rows=args.max_rows, force=args.force),
                indent=2,
            )
        )
        return 0
    if args.shard:
        print(json.dumps(build_shard_topic_index(root, args.shard, max_rows=args.max_rows, force=args.force), indent=2))
        return 0
    print(json.dumps(build_full_index_topic(root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
