#!/usr/bin/env python3
"""Procured dataset cards, pins, open/load, and schema preview."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from scripts.research_data_mcp.campaign_artifacts import list_campaign_artifacts
from scripts.research_data_mcp.procureability import (
    BADGE_DOWNLOADABLE,
    BADGE_PROMOTED,
    BADGE_READY,
    badge_label,
    badge_tone,
    registry_procureability,
)

PIN_HANDLE_RE = re.compile(r"^doi:(?P<doi>10\.\d{4,9}/[^\s@]+)(?:@file:(?P<file>[^@]+))?$", re.I)
HF_HANDLE_RE = re.compile(r"^hf:(?P<dataset_id>.+)$", re.I)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def pins_path(repo_root: Path) -> Path:
    return repo_root / "data_lake/procurement_memory/pins.json"


def load_pins(repo_root: Path) -> dict[str, Any]:
    path = pins_path(repo_root)
    if not path.exists():
        return {"pins": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_pins(repo_root: Path, payload: dict[str, Any]) -> None:
    path = pins_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def make_handle(*, doi: str = "", file_name: str = "", campaign_id: str = "", scrape_job_id: str = "") -> str:
    if scrape_job_id:
        return f"scrape:{scrape_job_id}"
    if doi and file_name:
        return f"doi:{doi}@file:{file_name}"
    if doi:
        return f"doi:{doi}"
    if campaign_id:
        return f"campaign:{campaign_id}"
    raise ValueError("doi or campaign_id required")


def parse_handle(handle: str) -> dict[str, str]:
    handle = handle.strip().removeprefix("procured://")
    if handle.startswith("campaign:"):
        return {"kind": "campaign", "campaign_id": handle.split(":", 1)[1]}
    if handle.startswith("scrape:"):
        return {"kind": "scrape", "job_id": handle.split(":", 1)[1]}
    match = PIN_HANDLE_RE.match(handle)
    if match:
        out = {"kind": "doi", "doi": match.group("doi")}
        if match.group("file"):
            out["file"] = match.group("file")
        return out
    if handle.startswith("dataset:"):
        return {"kind": "dataset", "dataset_id": handle.split(":", 1)[1]}
    hf_match = HF_HANDLE_RE.match(handle)
    if hf_match or handle.startswith("hf:"):
        did = hf_match.group("dataset_id") if hf_match else handle.split(":", 1)[1]
        return {"kind": "hf", "dataset_id": did}
    return {"kind": "raw", "raw": handle}


def file_checksum(path: Path, *, algo: str = "sha256") -> str:
    h = hashlib.new(algo)
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return f"{algo}:{h.hexdigest()}"


def schema_preview(path: Path, *, limit: int = 5) -> dict[str, Any]:
    if not path.is_file():
        return {"kind": "missing"}
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            with path.open(encoding="utf-8", errors="replace", newline="") as fh:
                reader = csv.reader(fh)
                rows = []
                for i, row in enumerate(reader):
                    if i >= limit + 1:
                        break
                    rows.append(row)
            if not rows:
                return {"kind": "csv", "columns": [], "rows": []}
            return {"kind": "csv", "columns": rows[0], "rows": rows[1 : limit + 1]}
        if suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace")[:200_000])
            if isinstance(payload, list):
                return {"kind": "json", "rows": payload[:limit]}
            return {"kind": "json", "object_keys": list(payload.keys())[:20], "sample": str(payload)[:400]}
        if suffix in {".jsonl", ".ndjson"}:
            rows = []
            with path.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    rows.append(json.loads(line))
                    if len(rows) >= limit:
                        break
            return {"kind": "jsonl", "rows": rows}
    except Exception as exc:
        return {"kind": "binary", "error": str(exc), "preview": path.read_text(encoding="utf-8", errors="replace")[:300]}
    return {"kind": "binary", "preview": path.read_text(encoding="utf-8", errors="replace")[:300]}


def remote_schema_preview(
    url: str,
    *,
    limit: int = 5,
    max_bytes: int = 32_768,
    filename: str = "",
) -> dict[str, Any]:
    """Fetch a small HTTP range sample for metadata-only DOI previews."""
    import urllib.error
    import urllib.request

    if not url.startswith("http"):
        return {"kind": "remote_unavailable", "error": "invalid url"}
    name_hint = (filename or url).lower()
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "YZU-ResearchDesk/1.0",
            "Range": f"bytes=0-{max_bytes - 1}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read(max_bytes)
    except urllib.error.HTTPError as exc:
        if exc.code != 416:
            return {"kind": "remote_unavailable", "error": str(exc)}
        with urllib.request.urlopen(url, timeout=20) as resp:
            raw = resp.read(max_bytes)
    except Exception as exc:
        return {"kind": "remote_unavailable", "error": str(exc)}

    lower_url = url.lower()
    is_csv = name_hint.endswith(".csv") or lower_url.endswith(".csv") or ".csv?" in lower_url
    if is_csv:
        text = raw.decode("utf-8", errors="replace")
        rows: list[list[str]] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            rows.append(next(csv.reader([line])))
            if len(rows) > limit:
                break
        if not rows:
            return {"kind": "remote_sample", "columns": [], "rows": [], "source_url": url}
        return {
            "kind": "remote_sample",
            "columns": rows[0],
            "rows": [{rows[0][i]: row[i] if i < len(row) else "" for i in range(len(rows[0]))} for row in rows[1 : limit + 1]],
            "source_url": url,
        }
    if lower_url.endswith(".json") or ".json?" in lower_url:
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace"))
            if isinstance(payload, list):
                return {"kind": "remote_sample", "rows": payload[:limit], "source_url": url}
            return {"kind": "remote_sample", "object_keys": list(payload.keys())[:20], "source_url": url}
        except Exception as exc:
            return {"kind": "remote_unavailable", "error": str(exc), "source_url": url}
    return {
        "kind": "remote_text",
        "preview": raw.decode("utf-8", errors="replace")[:400],
        "source_url": url,
    }


def _preview_from_resolved_files(resolved: dict[str, Any], *, limit: int = 5) -> dict[str, Any] | None:
    files = resolved.get("files") or resolved.get("all_files") or []
    if not files:
        return None
    chosen = files[0]
    url = str(chosen.get("url") or "")
    if not url:
        return None
    fname = str(chosen.get("key") or chosen.get("filename") or "")
    preview = remote_schema_preview(url, limit=limit, filename=fname)
    if preview.get("kind") == "remote_unavailable":
        return {
            "kind": "files_list",
            "columns": ["file", "size"],
            "rows": [
                {"file": str(f.get("key") or f.get("filename") or ""), "size": f.get("size")}
                for f in files[:limit]
            ],
            "primary_file": str(chosen.get("key") or chosen.get("filename") or ""),
            "source_url": url,
        }
    preview["primary_file"] = str(chosen.get("key") or chosen.get("filename") or "")
    return preview


def pin_dataset(
    repo_root: Path,
    *,
    handle: str,
    campaign_id: str = "",
    file_path: str = "",
    checksum: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    store = load_pins(repo_root)
    pins: list[dict[str, Any]] = store.setdefault("pins", [])
    row = {
        "handle": handle,
        "campaign_id": campaign_id,
        "file_path": file_path,
        "checksum": checksum,
        "pinned_at": _utc_now(),
        "metadata": metadata or {},
    }
    pins = [p for p in pins if p.get("handle") != handle]
    pins.insert(0, row)
    store["pins"] = pins[:200]
    save_pins(repo_root, store)
    return row


def list_pins(repo_root: Path, *, limit: int = 50) -> list[dict[str, Any]]:
    return list(load_pins(repo_root).get("pins") or [])[:limit]


def get_pin(repo_root: Path, handle: str) -> dict[str, Any] | None:
    for row in load_pins(repo_root).get("pins") or []:
        if row.get("handle") == handle:
            return row
    return None


def try_reuse_pinned_collect(
    repo_root: Path,
    *,
    doi: str,
    file_index: int,
    resolved: dict[str, Any],
    get_campaign: Callable[[str], dict[str, Any]],
) -> dict[str, Any] | None:
    """Skip re-download when a pinned file still exists and checksum matches."""
    files = resolved.get("files") or []
    if file_index < 0 or file_index >= len(files):
        return None
    file_name = str(files[file_index].get("key") or "")
    if not file_name:
        return None
    handle = make_handle(doi=doi, file_name=file_name)
    pin = get_pin(repo_root, handle)
    if not pin:
        return None
    campaign_id = str(pin.get("campaign_id") or "")
    rel_path = str(pin.get("file_path") or "")
    if not campaign_id or not rel_path:
        return None
    abs_path = repo_root / rel_path
    if not abs_path.is_file():
        return None
    pin_checksum = str(pin.get("checksum") or "")
    if pin_checksum.startswith("sha256:"):
        if file_checksum(abs_path) != pin_checksum:
            return None
    try:
        campaign = get_campaign(campaign_id)
    except Exception:
        return None
    return {
        "reused": True,
        "campaign_id": campaign_id,
        "executed": False,
        "job": {"status": "completed", "id": "reused-pin"},
        "plan": {
            "datacite_doi": doi,
            "datacite_file": file_name,
            "datacite_checksum": pin_checksum,
            "repository": resolved.get("repository"),
        },
        "phase": campaign.get("phase"),
        "message": "reused pinned collect — checksum verified",
    }


def build_card_from_campaign(
    repo_root: Path,
    campaign: dict[str, Any],
    *,
    job_get: Callable[[str], dict[str, Any]],
    registry_path: Path | None = None,
) -> dict[str, Any]:
    arts = list_campaign_artifacts(repo_root, campaign, job_get=job_get, registry_path=registry_path)
    payload = campaign.get("payload") or {}
    doi = str(payload.get("doi") or "")
    file_name = str(payload.get("datacite_file") or "")
    handle = make_handle(doi=doi, file_name=file_name) if doi else make_handle(campaign_id=str(campaign.get("id")))
    files = []
    primary = None
    for art in arts.get("artifacts") or []:
        frow = {
            "name": art.get("name"),
            "path": art.get("path"),
            "bytes": art.get("bytes"),
            "content_type": art.get("content_type"),
            "checksum": "",
            "download_path": art.get("download_path"),
        }
        path = repo_root / str(art.get("path") or "")
        if path.is_file() and path.stat().st_size <= 5_000_000:
            frow["checksum"] = file_checksum(path)
        files.append(frow)
        if primary is None and art.get("source") == "materialized":
            primary = frow
    preview = schema_preview(repo_root / primary["path"]) if primary and primary.get("path") else None
    badges = [BADGE_READY] if campaign.get("phase") == "ready" else [BADGE_DOWNLOADABLE]
    if arts.get("registry_datasets"):
        badges.append(BADGE_PROMOTED)
    return {
        "id": f"procured://{handle}",
        "handle": handle,
        "title": campaign.get("goal") or file_name or doi or campaign.get("id"),
        "source": "datacite" if doi else "procurement",
        "doi": doi,
        "campaign_id": campaign.get("id"),
        "phase": campaign.get("phase"),
        "status": "ready" if campaign.get("phase") == "ready" else str(campaign.get("phase") or "active"),
        "badges": badges,
        "badge_labels": [badge_label(b) for b in badges],
        "tone": badge_tone(badges[0]),
        "files": files,
        "primary_file": primary,
        "schema_preview": preview,
        "registry_datasets": arts.get("registry_datasets") or [],
        "lineage": {
            "campaign_id": campaign.get("id"),
            "collect_job_ids": payload.get("collect_job_ids") or [],
            "doi": doi,
            "file": file_name,
        },
        "open_paths": {
            "card": f"/library/datasets/card/{campaign.get('id')}",
            "open": f"/library/datasets/open?handle={handle}",
        },
    }


def build_card_from_registry(repo_root: Path, dataset: dict[str, Any]) -> dict[str, Any]:
    proc = registry_procureability(dataset)
    dataset_id = str(dataset.get("dataset_id") or dataset.get("id") or "")
    local_path = str(dataset.get("local_path") or "")
    files = []
    preview = None
    if local_path and "*" not in local_path:
        path = repo_root / local_path
        if path.is_file():
            files.append(
                {
                    "name": path.name,
                    "path": local_path,
                    "bytes": path.stat().st_size,
                    "checksum": file_checksum(path) if path.stat().st_size <= 5_000_000 else "",
                }
            )
            preview = schema_preview(path)
    return {
        "id": f"procured://dataset:{dataset_id}",
        "handle": f"dataset:{dataset_id}",
        "title": dataset.get("name") or dataset_id,
        "source": "registry",
        "dataset_id": dataset_id,
        "status": proc.get("status"),
        "badges": proc.get("badges") or [],
        "badge_labels": proc.get("badge_labels") or [],
        "tone": proc.get("tone"),
        "files": files,
        "schema_preview": preview,
        "lineage": dataset.get("lineage") or {},
        "procurement": dataset.get("procurement") or {},
        "open_paths": {
            "card": f"/library/datasets/card/{dataset_id}",
            "open": f"/library/datasets/open?handle=dataset:{dataset_id}",
            "query": f"/query/{dataset_id}?limit=5",
        },
    }


def open_dataset(
    repo_root: Path,
    handle: str,
    *,
    gateway: Any,
    preview_limit: int = 5,
    load: str = "auto",
) -> dict[str, Any]:
    """Open a procured dataset — returns paths, preview, and optional pandas load."""
    parsed = parse_handle(handle)
    repo_root = repo_root.resolve()
    pin = None

    if parsed.get("kind") == "campaign":
        campaign = gateway.get_campaign(parsed["campaign_id"])
        card = build_card_from_campaign(
            repo_root,
            campaign,
            job_get=gateway.get_yzu_job,
            registry_path=gateway.registry_path,
        )
    elif parsed.get("kind") == "dataset":
        dataset = gateway.describe_dataset(parsed["dataset_id"])
        card = build_card_from_registry(repo_root, dataset)
    elif parsed.get("kind") == "hf":
        from scripts.research_data_mcp.hf_loader import open_hf_dataset

        hf_out = open_hf_dataset(repo_root, parsed["dataset_id"], preview_limit=preview_limit, cache=True)
        return hf_out
    elif parsed.get("kind") == "scrape":
        from scripts.research_data_mcp.procurement_delivery import build_scrape_card

        card = build_scrape_card(gateway, parsed["job_id"])
        if not card:
            raise ValueError(f"scrape output not found for job {parsed['job_id']}")
        path = repo_root / "data_lake/spectator_engine/scrapes" / parsed["job_id"] / "extract.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        links = payload.get("dataset_links") or payload.get("links") or []
        preview_rows = links[:preview_limit] if isinstance(links, list) else []
        return {
            "handle": card["handle"],
            "card": card,
            "path": str(path.relative_to(repo_root)),
            "preview": {
                "kind": "scrape_json",
                "columns": ["href", "text"] if preview_rows and isinstance(preview_rows[0], dict) else ["summary"],
                "rows": preview_rows[:preview_limit] if preview_rows else [{"summary": payload.get("title") or payload.get("url")}],
            },
            "scrape": payload,
        }
    elif parsed.get("kind") == "doi":
        pin = get_pin(repo_root, make_handle(doi=parsed["doi"], file_name=parsed.get("file", "")))
        if pin and pin.get("campaign_id"):
            try:
                campaign = gateway.get_campaign(pin["campaign_id"])
                card = build_card_from_campaign(
                    repo_root,
                    campaign,
                    job_get=gateway.get_yzu_job,
                    registry_path=gateway.registry_path,
                )
            except KeyError:
                pin = None
        if not pin or not pin.get("campaign_id"):
            resolved = gateway.datacite_resolve_repository(parsed["doi"])
            card = {
                "id": f"procured://doi:{parsed['doi']}",
                "handle": make_handle(doi=parsed["doi"], file_name=parsed.get("file", "")),
                "title": resolved.get("title"),
                "doi": parsed["doi"],
                "status": "not_collected",
                "files": resolved.get("files") or [],
                "schema_preview": _preview_from_resolved_files(resolved, limit=preview_limit),
            }
    else:
        raise ValueError(f"unsupported handle: {handle}")

    primary = card.get("primary_file") or ((card.get("files") or [{}])[0])
    rel = str(primary.get("path") or "")
    abs_path = (repo_root / rel).resolve() if rel else None
    result: dict[str, Any] = {
        "handle": card.get("handle") or handle,
        "card": card,
        "path": rel,
        "absolute_path": str(abs_path) if abs_path else "",
        "preview": card.get("schema_preview") or (schema_preview(abs_path) if abs_path and abs_path.is_file() else None),
    }

    if load in {"pandas", "auto", "pyarrow"} and abs_path and abs_path.is_file():
        suffix = abs_path.suffix.lower()
        if suffix == ".csv":
            try:
                import pandas as pd  # type: ignore

                df = pd.read_csv(abs_path, nrows=preview_limit if load == "auto" else None)
                result["pandas"] = {
                    "columns": list(df.columns),
                    "rows": df.head(preview_limit).to_dict(orient="records"),
                    "shape": list(df.shape),
                }
                result["loader"] = "pandas"
            except Exception as exc:
                result["pandas_error"] = str(exc)
        elif suffix == ".parquet":
            try:
                import pyarrow.parquet as pq  # type: ignore

                table = pq.read_table(abs_path)
                df = table.slice(0, preview_limit).to_pydict()
                columns = list(df.keys())
                rows = [{columns[j]: df[columns[j]][i] for j in range(len(columns))} for i in range(min(preview_limit, table.num_rows))]
                result["preview"] = {"kind": "parquet", "columns": columns, "rows": rows}
                result["loader"] = "pyarrow"
            except Exception as exc:
                result["parquet_error"] = str(exc)

    if pin and rel and abs_path and abs_path.is_file():
        pin_checksum = str(pin.get("checksum") or "")
        if pin_checksum.startswith("sha256:"):
            live = file_checksum(abs_path)
            result["checksum_ok"] = live == pin_checksum
            result["checksum"] = live

    return result
