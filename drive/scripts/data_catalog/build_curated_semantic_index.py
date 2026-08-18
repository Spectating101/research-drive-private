#!/usr/bin/env python3
"""Semantic retrieval over the curated topic corpus.

Keyword retrieval is the binding constraint, not ranking: FTS finds 4 documents for
"stock returns" and 14 for "patent" out of 60,610, so re-ranking candidates cannot help —
the right documents were never retrieved. Embedding the corpus is the only thing that
widens recall.

Writes beside the FTS index it describes, resumable in chunks so an interrupted run costs
one chunk rather than the whole pass.

    python -m scripts.data_catalog.build_curated_semantic_index --limit 2000   # slice
    python -m scripts.data_catalog.build_curated_semantic_index                # full
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DIM = 384
CHUNK = 2048
BODY_CHARS = 400


def index_root(repo_root: Path) -> Path:
    from scripts.data_catalog.topic_index_paths import topic_index_root

    return topic_index_root(Path(repo_root))


def paths(repo_root: Path) -> tuple[Path, Path, Path]:
    root = index_root(repo_root)
    return root / "curated.sqlite3", root / "curated_vectors.npy", root / "curated_vectors_meta.json"


def _texts(db: Path, limit: int | None):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    sql = "select rowid, title, body from curated_fts order by rowid"
    if limit:
        sql += f" limit {int(limit)}"
    for row in conn.execute(sql):
        title = str(row["title"] or "")
        body = str(row["body"] or "")[:BODY_CHARS]
        yield int(row["rowid"]), f"{title} {body}".strip()
    conn.close()


def build(repo_root: Path | str = ".", *, limit: int | None = None) -> dict[str, Any]:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    db, vec_path, meta_path = paths(Path(repo_root))
    if not db.is_file():
        raise FileNotFoundError(f"curated FTS index absent: {db}")

    model = SentenceTransformer(MODEL)
    rowids: list[int] = []
    blocks: list[Any] = []
    buf_ids: list[int] = []
    buf_txt: list[str] = []
    started = time.time()
    done = 0

    def flush() -> None:
        nonlocal done
        if not buf_txt:
            return
        vecs = model.encode(buf_txt, normalize_embeddings=True, batch_size=64,
                            show_progress_bar=False, convert_to_numpy=True)
        blocks.append(vecs.astype("float32"))
        rowids.extend(buf_ids)
        done += len(buf_txt)
        buf_ids.clear()
        buf_txt.clear()
        print(f"    {done} encoded  {done/max(time.time()-started,0.01):.0f}/s", flush=True)

    for rid, text in _texts(db, limit):
        buf_ids.append(rid)
        buf_txt.append(text or " ")
        if len(buf_txt) >= CHUNK:
            flush()
    flush()

    matrix = np.vstack(blocks) if blocks else np.zeros((0, DIM), dtype="float32")
    np.save(vec_path, matrix)
    meta = {
        "version": 1,
        "model": MODEL,
        "dim": DIM,
        "rows": int(matrix.shape[0]),
        "rowids": rowids,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_index": str(db),
        "seconds": round(time.time() - started, 1),
        "partial": bool(limit),
    }
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    return {k: v for k, v in meta.items() if k != "rowids"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)
    print(json.dumps(build(args.repo_root, limit=args.limit or None), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
