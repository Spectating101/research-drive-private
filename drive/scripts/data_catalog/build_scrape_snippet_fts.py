#!/usr/bin/env python3
"""FTS5 over web scrape snippets — searchable non-DOI sourced pages."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

INDEX_VERSION = 1


def snippet_index_path(repo_root: Path) -> Path:
    return Path(repo_root).resolve() / "data_lake/dataset_catalog/_topic_index/scrape_snippets.sqlite3"


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def build_scrape_snippet_fts(repo_root: Path) -> dict[str, Any]:
    from scripts.research_data_mcp.scrape_flywheel import snippet_jsonl_path

    repo_root = Path(repo_root).resolve()
    src = snippet_jsonl_path(repo_root)
    out = snippet_index_path(repo_root)
    if not src.is_file():
        return {"built": False, "reason": "no scrape_index.jsonl"}
    if out.is_file():
        out.unlink()
    conn = _connect(out)
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
    with src.open(encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            title = str(row.get("title") or "")
            body = " ".join(
                filter(
                    None,
                    [
                        str(row.get("description") or ""),
                        str(row.get("text_sample") or "")[:4000],
                        str(row.get("host") or ""),
                        " ".join(str(t) for t in (row.get("tags") or [])),
                        str(row.get("search_goal") or ""),
                    ],
                )
            )
            conn.execute(
                "INSERT INTO vault_fts(doi, title, body, payload_json) VALUES (?,?,?,?)",
                (
                    str(row.get("dataset_id") or ""),
                    title[:500],
                    body[:12000],
                    json.dumps(row, ensure_ascii=False),
                ),
            )
            count += 1
    conn.commit()
    conn.close()
    meta = {
        "version": INDEX_VERSION,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "built": True,
        "row_count": count,
        "index_path": str(out),
    }
    (out.parent / "scrape_snippets_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args()
    print(json.dumps(build_scrape_snippet_fts(Path(args.repo_root)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
