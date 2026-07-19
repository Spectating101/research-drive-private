#!/usr/bin/env python3
"""Hugging Face dataset bridge — metadata, parquet preview, optional local cache."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from scripts.research_data_mcp import hf_catalog

USER_AGENT = "ResearchDrive/1.0"
HF_CACHE_ROOT = "data_lake/procured/huggingface"
PREVIEW_MAX_PARQUET_BYTES = 25_000_000


def _fetch_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parquet_splits(dataset_id: str) -> list[dict[str, Any]]:
    did = dataset_id.strip().removeprefix("hf:").removeprefix("https://huggingface.co/datasets/")
    url = f"https://huggingface.co/api/datasets/{urllib.parse.quote(did, safe='/')}/parquet"
    try:
        payload = _fetch_json(url)
    except Exception:
        return []
    rows: list[dict[str, Any]] = []

    def _append(split: str, entry: Any, *, config: str = "default") -> None:
        if isinstance(entry, str):
            rows.append(
                {
                    "config": config,
                    "split": split,
                    "url": entry,
                    "filename": entry.rsplit("/", 1)[-1],
                }
            )
        elif isinstance(entry, dict):
            rows.append(
                {
                    "config": config,
                    "split": split,
                    "url": entry.get("url"),
                    "filename": entry.get("filename") or split,
                    "size": entry.get("size"),
                }
            )

    if not isinstance(payload, dict):
        return rows

    for key, value in payload.items():
        if isinstance(value, list):
            for entry in value:
                _append(str(key), entry)
            continue
        if isinstance(value, dict):
            for split, files in value.items():
                if not isinstance(files, list):
                    continue
                for entry in files:
                    _append(str(split), entry, config=str(key))
    return rows


def _download_bytes(url: str, *, max_bytes: int = PREVIEW_MAX_PARQUET_BYTES) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"parquet shard exceeds preview cap ({max_bytes} bytes)")
    return data


def _parquet_preview(url: str, *, preview_limit: int) -> dict[str, Any]:
    import io

    import pyarrow.parquet as pq  # type: ignore

    table = pq.read_table(io.BytesIO(_download_bytes(url)))
    df = table.slice(0, preview_limit).to_pydict()
    columns = list(df.keys())
    rows = [
        {columns[j]: df[columns[j]][i] for j in range(len(columns))}
        for i in range(min(preview_limit, table.num_rows))
    ]
    return {"kind": "parquet", "columns": columns, "rows": rows, "row_count": table.num_rows}


def build_hf_card(dataset_id: str) -> dict[str, Any]:
    meta = hf_catalog.get_dataset(dataset_id)
    splits = parquet_splits(meta["id"])
    return {
        "id": f"procured://hf:{meta['id']}",
        "handle": f"hf:{meta['id']}",
        "title": meta.get("title") or meta["id"],
        "source": "huggingface",
        "dataset_id": meta["id"],
        "status": "external_hub",
        "badges": ["huggingface_reference"],
        "badge_labels": ["On Hugging Face"],
        "tone": "blue",
        "url": meta.get("url"),
        "load_hint": meta.get("load_hint"),
        "tags": meta.get("tags") or [],
        "description": meta.get("description"),
        "parquet_splits": splits[:12],
        "open_paths": {
            "card": f"/library/datasets/card/hf:{meta['id']}",
            "open": f"/library/datasets/open?handle=hf:{urllib.parse.quote(meta['id'], safe='')}",
            "hub": meta.get("url"),
        },
    }


def open_hf_dataset(
    repo_root: Path,
    dataset_id: str,
    *,
    split: str = "train",
    preview_limit: int = 5,
    cache: bool = True,
) -> dict[str, Any]:
    did = dataset_id.strip().removeprefix("hf:")
    card = build_hf_card(did)
    result: dict[str, Any] = {
        "handle": f"hf:{did}",
        "card": card,
        "loader": "huggingface",
        "preview": None,
    }

    # Prefer datasets library when installed
    try:
        from datasets import load_dataset  # type: ignore

        cache_dir = str((repo_root / HF_CACHE_ROOT / did.replace("/", "__")).resolve()) if cache else None
        ds = load_dataset(did, split=split, streaming=True, cache_dir=cache_dir)
        rows = []
        for i, row in enumerate(ds):
            rows.append(row)
            if i + 1 >= preview_limit:
                break
        columns = list(rows[0].keys()) if rows else []
        result["preview"] = {"kind": "hf_dataset", "split": split, "columns": columns, "rows": rows}
        result["loader"] = "datasets_streaming"
        result["cache_dir"] = cache_dir
        return result
    except Exception as exc:
        result["datasets_error"] = str(exc)

    # Fallback: parquet row-group preview via pyarrow
    splits = card.get("parquet_splits") or []
    chosen = next((s for s in splits if s.get("split") == split), None)
    if chosen is None:
        chosen = next((s for s in splits if str(s.get("split") or "").startswith(split)), None)
    if chosen is None and splits:
        chosen = splits[0]
    if chosen and chosen.get("url"):
        try:
            preview = _parquet_preview(str(chosen["url"]), preview_limit=preview_limit)
            preview["split"] = chosen.get("split")
            preview["config"] = chosen.get("config")
            result["preview"] = preview
            result["loader"] = "pyarrow_parquet"
            result["parquet_url"] = chosen.get("url")
            return result
        except Exception as exc2:
            result["parquet_error"] = str(exc2)

    result["preview"] = {"kind": "metadata_only", "load_hint": card.get("load_hint")}
    return result
