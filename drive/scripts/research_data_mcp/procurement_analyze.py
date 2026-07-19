#!/usr/bin/env python3
"""Bounded data analysis for procured datasets — safe row caps, optional LLM narrative."""

from __future__ import annotations

import json
import os
import statistics
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_ROW_CAP = int(os.getenv("PROCUREMENT_ANALYSIS_ROW_CAP", "2000"))


def _numeric(vals: list[Any]) -> list[float]:
    out: list[float] = []
    for v in vals:
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            out.append(float(v))
        else:
            try:
                out.append(float(str(v).replace(",", "")))
            except (TypeError, ValueError):
                pass
    return out


def compute_stats_from_rows(rows: list[dict[str, Any]], *, sample_cap: int) -> dict[str, Any]:
    if not rows:
        return {"row_count": 0, "columns": [], "column_stats": {}, "capped": True, "sample_cap": sample_cap}
    cols = list(rows[0].keys())
    stats: dict[str, Any] = {
        "row_count": len(rows),
        "columns": cols,
        "column_stats": {},
        "capped": len(rows) >= sample_cap,
        "sample_cap": sample_cap,
    }
    for col in cols[:40]:
        raw = [r.get(col) for r in rows]
        non_null = [v for v in raw if v is not None and str(v).strip() != ""]
        col_stat: dict[str, Any] = {
            "non_null": len(non_null),
            "null_rate": round(1 - len(non_null) / max(len(rows), 1), 4),
        }
        nums = _numeric(non_null)
        if len(nums) >= 2:
            col_stat["numeric"] = {
                "min": min(nums),
                "max": max(nums),
                "mean": round(statistics.fmean(nums), 6),
                "std": round(statistics.pstdev(nums), 6) if len(nums) > 1 else 0.0,
            }
        elif non_null:
            unique = list(dict.fromkeys(str(v) for v in non_null[:50]))
            col_stat["top_values"] = unique[:5]
        stats["column_stats"][col] = col_stat
    return stats


def _load_local_sample(repo_root: Path, rel_path: str, row_cap: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = (repo_root / rel_path).resolve()
    if not path.is_file():
        return [], {"error": f"file not found: {rel_path}"}
    suffix = path.suffix.lower()
    meta: dict[str, Any] = {"path": rel_path, "bytes": path.stat().st_size}
    if suffix == ".csv":
        try:
            import pandas as pd  # type: ignore

            df = pd.read_csv(path, nrows=row_cap)
            meta["loader"] = "pandas_csv"
            meta["shape"] = list(df.shape)
            return df.to_dict(orient="records"), meta
        except Exception as exc:
            return [], {"error": str(exc), "path": rel_path}
    if suffix == ".parquet":
        try:
            import pyarrow.parquet as pq  # type: ignore

            table = pq.read_table(path)
            n = min(row_cap, table.num_rows)
            df = table.slice(0, n).to_pandas()
            meta["loader"] = "pyarrow_parquet"
            meta["shape"] = [n, table.num_columns]
            return df.to_dict(orient="records"), meta
        except Exception as exc:
            return [], {"error": str(exc), "path": rel_path}
    if suffix == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return [r for r in payload[:row_cap] if isinstance(r, dict)], {"loader": "json_list"}
        except Exception as exc:
            return [], {"error": str(exc)}
    return [], {"error": f"unsupported file type for analysis: {suffix}", "path": rel_path}


def format_analysis_report(
    *,
    handle: str,
    question: str,
    stats: dict[str, Any],
    meta: dict[str, Any],
    llm_note: str = "",
) -> str:
    lines = [f"**Analysis** (`{handle}`)"]
    if question.strip():
        lines.append(f"_Question: {question.strip()[:200]}_")
    if meta.get("shape"):
        lines.append(f"- Loaded sample shape: **{meta['shape'][0]}** rows × **{meta['shape'][1]}** columns")
    elif stats.get("row_count"):
        lines.append(f"- Rows in sample: **{stats['row_count']}**")
    if stats.get("capped"):
        lines.append(f"- _(Capped at {stats.get('sample_cap')} rows — not the full dataset.)_")
    if meta.get("error"):
        lines.append(f"- Load note: {meta['error']}")
    lines.append(f"- Columns ({len(stats.get('columns') or [])}): {', '.join(str(c) for c in (stats.get('columns') or [])[:12])}")
    for col, cs in list((stats.get("column_stats") or {}).items())[:8]:
        bit = f"{col}: {cs.get('non_null')} non-null"
        if "numeric" in cs:
            n = cs["numeric"]
            bit += f", mean {n['mean']:.4g}, range [{n['min']:.4g}, {n['max']:.4g}]"
        elif cs.get("top_values"):
            bit += f", examples: {', '.join(cs['top_values'][:3])}"
        lines.append(f"  - {bit}")
    if llm_note:
        lines.extend(["", "**Interpretation**", llm_note])
    else:
        lines.append("\n_Composer interprets these stats — pass a question only when you want legacy LLM narrative (PROCUREMENT_LLM_ANALYZE=1)._")
    return "\n".join(lines)


def llm_interpret_analysis(question: str, stats: dict[str, Any], sample_rows: list[dict[str, Any]]) -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/chat/completions")
    if not api_key and "localhost" not in base_url:
        return ""
    system = (
        "You are a quantitative data analyst. Answer the user's question using ONLY the provided "
        "column statistics and sample rows. If the sample is too small for the question, say so. "
        "Be concise, concrete, and avoid inventing columns or values not in the payload."
    )
    payload = {
        "question": question,
        "stats": stats,
        "sample_rows": sample_rows[:12],
    }
    body = json.dumps(
        {
            "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)[:12000]},
            ],
        }
    ).encode()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(base_url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    return str(data["choices"][0]["message"]["content"]).strip()


def analyze_procured(
    gateway: Any,
    *,
    handle: str,
    question: str = "",
    row_cap: int = DEFAULT_ROW_CAP,
) -> dict[str, Any]:
    """Load a bounded sample, compute stats, optionally LLM-interpret."""
    from scripts.research_data_mcp.procured_dataset import parse_handle

    row_cap = max(10, min(int(row_cap), 10_000))
    parsed = parse_handle(handle)
    rows: list[dict[str, Any]] = []
    meta: dict[str, Any] = {"handle": handle}
    opened: dict[str, Any] = {}

    if parsed.get("kind") == "dataset":
        q = gateway.query_dataset(parsed["dataset_id"], {"limit": min(row_cap, 500)})
        rows = [r for r in (q.get("rows") or q.get("data") or []) if isinstance(r, dict)]
        meta["loader"] = "registry_query"
        meta["dataset_id"] = parsed["dataset_id"]
    else:
        opened = gateway.open_dataset(handle, preview_limit=min(row_cap, 50), load="auto")
        rel = str(opened.get("path") or "")
        if rel:
            rows, file_meta = _load_local_sample(gateway.repo_root, rel, row_cap)
            meta.update(file_meta)
        if not rows:
            pandas_block = opened.get("pandas") or {}
            rows = [r for r in (pandas_block.get("rows") or []) if isinstance(r, dict)]
            if pandas_block.get("shape"):
                meta["shape"] = pandas_block["shape"]
                meta["loader"] = meta.get("loader") or "pandas_preview"
        if not rows:
            prev = opened.get("preview") or {}
            rows = [r for r in (prev.get("rows") or []) if isinstance(r, dict)]
            meta["loader"] = meta.get("loader") or "schema_preview"

    stats = compute_stats_from_rows(rows, sample_cap=row_cap)
    llm_note = ""
    if question.strip() and os.getenv("PROCUREMENT_LLM_ANALYZE", "").strip().lower() in {"1", "true", "yes"}:
        try:
            llm_note = llm_interpret_analysis(question, stats, rows)
        except Exception as exc:
            llm_note = f"_LLM interpretation unavailable ({exc}). Stats below are still valid._"

    narrative = format_analysis_report(
        handle=handle,
        question=question,
        stats=stats,
        meta=meta,
        llm_note=llm_note,
    )
    return {
        "handle": handle,
        "stats": stats,
        "meta": meta,
        "sample_rows": rows[:20],
        "narrative": narrative,
        "llm_interpretation": llm_note,
        "opened": opened,
        "row_cap": row_cap,
    }
