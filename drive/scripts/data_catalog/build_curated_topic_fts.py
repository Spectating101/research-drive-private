#!/usr/bin/env python3
"""Build SQLite FTS5 over curated DataCite catalogs — fast topic search (~100k rows)."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{2,}")
INDEX_VERSION = 1

CURATED_DIRS = ("curated_live", "curated", "curated_strict")


def topic_index_path(repo_root: Path) -> Path:
    return Path(repo_root).resolve() / "data_lake/dataset_catalog/_topic_index/curated.sqlite3"


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _normalize_doi(raw: str) -> str:
    text = str(raw or "").strip().removeprefix("doi:").removeprefix("https://doi.org/")
    return text.strip()


def _body(row: dict[str, Any]) -> str:
    tags = " ".join(str(t) for t in (row.get("tags") or []))
    goal = str((row.get("procurement") or {}).get("search_goal") or "")
    return " ".join(
        filter(
            None,
            [
                str(row.get("description") or "")[:2000],
                str(row.get("domain") or ""),
                tags,
                goal,
            ],
        )
    )


def _iter_curated_rows(repo_root: Path) -> list[dict[str, Any]]:
    root = Path(repo_root).resolve() / "data_lake/dataset_catalog"
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for subdir in CURATED_DIRS:
        jsonl = root / subdir / "curated_dataset_index.jsonl"
        if not jsonl.is_file():
            continue
        with jsonl.open(encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                did = _normalize_doi(str(row.get("doi") or row.get("dataset_id") or ""))
                key = did.lower() if did.startswith("10.") else str(row.get("dataset_id") or row.get("title") or "").lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                row = dict(row)
                row["doi"] = did
                row["_source_dir"] = subdir
                rows.append(row)
    return rows


def build_curated_topic_fts(repo_root: Path) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    out = topic_index_path(repo_root)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.is_file():
        out.unlink()

    rows = _iter_curated_rows(repo_root)
    conn = _connect(out)
    conn.execute(
        """CREATE VIRTUAL TABLE curated_fts USING fts5(
            doi UNINDEXED,
            dataset_id UNINDEXED,
            source_dir UNINDEXED,
            title,
            body,
            payload_json UNINDEXED,
            tokenize='porter unicode61'
        )"""
    )
    for row in rows:
        doi = _normalize_doi(str(row.get("doi") or ""))
        dataset_id = str(row.get("dataset_id") or doi or "")
        conn.execute(
            """INSERT INTO curated_fts(doi, dataset_id, source_dir, title, body, payload_json)
               VALUES (?,?,?,?,?,?)""",
            (
                doi,
                dataset_id,
                str(row.get("_source_dir") or ""),
                str(row.get("title") or "")[:500],
                _body(row),
                json.dumps(row, ensure_ascii=False, default=str),
            ),
        )
    conn.commit()
    meta = {
        "version": INDEX_VERSION,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "row_count": len(rows),
        "index_path": str(out.relative_to(repo_root)),
        "sources": list(CURATED_DIRS),
    }
    (out.parent / "curated_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    conn.close()
    return meta


def index_is_stale(repo_root: Path) -> bool:
    out = topic_index_path(repo_root)
    if not out.is_file():
        return True
    mtime = out.stat().st_mtime
    root = Path(repo_root).resolve() / "data_lake/dataset_catalog"
    for subdir in CURATED_DIRS:
        jsonl = root / subdir / "curated_dataset_index.jsonl"
        if jsonl.is_file() and jsonl.stat().st_mtime > mtime:
            return True
    keys = root / "curated_live" / "flywheel_keys.json"
    if keys.is_file() and keys.stat().st_mtime > mtime:
        return True
    return False


def ensure_curated_topic_fts(repo_root: Path) -> Path:
    if index_is_stale(repo_root):
        build_curated_topic_fts(repo_root)
    return topic_index_path(repo_root)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build curated topic FTS index")
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args()
    meta = build_curated_topic_fts(Path(args.repo_root))
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
