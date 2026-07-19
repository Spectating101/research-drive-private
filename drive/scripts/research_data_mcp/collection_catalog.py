#!/usr/bin/env python3
"""Torrent-style collection catalog — swarms, pieces, trackers (magnet index for chat)."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.collection_dictionary import build_dictionary, dictionary_path
from scripts.research_data_mcp.collection_resolve import canonical_remote, list_shards, load_partitions, partition_by_id
from scripts.research_data_mcp.data_paths import bulk_data_lake_root, resolve_data_path
from scripts.research_data_mcp.datacite_client import datacite_url
from scripts.research_data_mcp.procurement_fast import local_path_has_data
from scripts.research_data_mcp.storage_tiers import canonical_drive_root

CATALOG_VERSION = 1
PIECE_NAME_RE = re.compile(r"datacite_(\d+)\.jsonl\.gz$")


def catalog_root(repo_root: Path) -> Path:
    return Path(repo_root).resolve() / "data_lake/collection/_index/catalog"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _piece_name(chunk_index: int) -> str:
    return f"datacite_{chunk_index:06d}.jsonl.gz"


def _local_piece_path(repo_root: Path, local_logical: str, piece: str) -> Path:
    return resolve_data_path(repo_root, f"{local_logical}/{piece}")


def _pieces_from_manifest(
    manifest: dict[str, Any],
    *,
    remote_base: str,
    local_logical: str,
    repo_root: Path,
) -> list[dict[str, Any]]:
    pieces: list[dict[str, Any]] = []
    for row in manifest.get("files") or []:
        path = str(row.get("path") or "")
        name = Path(path).name
        m = PIECE_NAME_RE.match(name)
        chunk_index = int(m.group(1)) if m else len(pieces)
        local_p = _local_piece_path(repo_root, local_logical, name)
        on_local = local_p.is_file() and local_p.stat().st_size > 0
        pieces.append(
            {
                "piece_id": f"{local_logical}/{name}",
                "name": name,
                "chunk_index": chunk_index,
                "bytes": int(row.get("bytes") or 0),
                "sha256": row.get("sha256"),
                "records": row.get("records"),
                "remote": f"{remote_base.rstrip('/')}/{name}",
                "local_logical": f"{local_logical}/{name}",
                "have_local": on_local,
                "fetch": f"rclone copyto {remote_base.rstrip('/')}/{name} {local_p}",
            }
        )
    pieces.sort(key=lambda p: int(p.get("chunk_index") or 0))
    return pieces


def _pieces_from_checkpoint(
    checkpoint: dict[str, Any],
    *,
    remote_base: str,
    local_logical: str,
    repo_root: Path,
) -> list[dict[str, Any]]:
    next_idx = int(checkpoint.get("next_chunk_index") or 0)
    last = checkpoint.get("last_chunk") or {}
    pieces: list[dict[str, Any]] = []
    for i in range(max(next_idx, 1)):
        name = _piece_name(i)
        local_p = _local_piece_path(repo_root, local_logical, name)
        on_local = local_p.is_file() and local_p.stat().st_size > 0
        row: dict[str, Any] = {
            "piece_id": f"{local_logical}/{name}",
            "name": name,
            "chunk_index": i,
            "bytes": None,
            "sha256": None,
            "records": None,
            "remote": f"{remote_base.rstrip('/')}/{name}",
            "local_logical": f"{local_logical}/{name}",
            "have_local": on_local,
            "fetch": f"rclone copyto {remote_base.rstrip('/')}/{name} {local_p}",
        }
        if int(last.get("chunk_index") or -1) == i:
            row["bytes"] = last.get("bytes")
            row["sha256"] = last.get("sha256")
            row["records"] = last.get("records")
        pieces.append(row)
    return pieces


def _scan_local_pieces(local_logical: str, repo_root: Path) -> dict[str, dict[str, Any]]:
    """Pieces discovered on disk (cache or NVMe) not listed in checkpoint."""
    base = resolve_data_path(repo_root, local_logical)
    found: dict[str, dict[str, Any]] = {}
    if not base.is_dir():
        return found
    for path in sorted(base.glob("datacite_*.jsonl.gz"))[:2000]:
        m = PIECE_NAME_RE.match(path.name)
        if not m:
            continue
        found[path.name] = {
            "chunk_index": int(m.group(1)),
            "bytes": path.stat().st_size,
            "have_local": True,
            "local_logical": f"{local_logical}/{path.name}",
        }
    return found


def _swarm_status(complete: dict[str, Any], checkpoint: dict[str, Any], row: dict[str, Any] | None) -> str:
    if complete.get("completed_at"):
        return "complete"
    if checkpoint.get("committed_records"):
        return "partial"
    av = (row or {}).get("availability") or {}
    if av.get("missing") and "no_status_files" in av["missing"]:
        return "absent"
    return "unknown"


def build_datacite_swarms(repo_root: Path, *, dictionary: dict[str, Any] | None = None) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    doc = dictionary or build_dictionary(repo_root)
    part = partition_by_id(repo_root, "catalog.datacite-harvest") or {}
    drive_root = canonical_drive_root(repo_root) or _load_json(repo_root / "config/yzu_cluster.json").get("storage", {}).get("drive_root", "")
    legacy_drive = str(part.get("legacy_drive_path") or "dataset_catalog/datacite/index_v3").strip("/")
    legacy_local = str(part.get("legacy_local_path") or "data_lake/dataset_catalog/index_v3").strip("/")

    dict_by_shard = {r.get("shard"): r for r in (doc.get("tables") or {}).get("datacite_shards") or [] if r.get("shard")}
    operator_by_shard = {r["shard"]: r for r in list_shards(repo_root)}

    swarms: list[dict[str, Any]] = []
    index_v3 = repo_root / legacy_local
    shard_dirs = sorted(index_v3.iterdir()) if index_v3.is_dir() else []

    for shard_dir in shard_dirs:
        if not shard_dir.is_dir():
            continue
        shard = shard_dir.name
        remote_base = f"{drive_root.rstrip('/')}/{legacy_drive}/{shard}"
        local_logical = f"{legacy_local}/{shard}"

        complete = _load_json(shard_dir / "datacite.complete.json")
        checkpoint = _load_json(shard_dir / "datacite.checkpoint.json")
        manifest = _load_json(shard_dir / "full_index_manifest.json")
        drow = dict_by_shard.get(shard) or {}
        op = operator_by_shard.get(shard) or {}

        if manifest.get("files"):
            pieces = _pieces_from_manifest(manifest, remote_base=remote_base, local_logical=local_logical, repo_root=repo_root)
        else:
            pieces = _pieces_from_checkpoint(checkpoint, remote_base=remote_base, local_logical=local_logical, repo_root=repo_root)

        local_scan = _scan_local_pieces(local_logical, repo_root)
        for name, scan in local_scan.items():
            if any(p.get("name") == name for p in pieces):
                for p in pieces:
                    if p.get("name") == name:
                        p["have_local"] = True
                        if not p.get("bytes"):
                            p["bytes"] = scan.get("bytes")
            else:
                pieces.append(
                    {
                        "piece_id": f"{local_logical}/{name}",
                        "name": name,
                        "chunk_index": scan["chunk_index"],
                        "bytes": scan.get("bytes"),
                        "sha256": None,
                        "records": None,
                        "remote": f"{remote_base}/{name}",
                        "local_logical": scan["local_logical"],
                        "have_local": True,
                        "fetch": f"rclone copyto {remote_base}/{name} {_local_piece_path(repo_root, local_logical, name)}",
                    }
                )
        pieces.sort(key=lambda p: int(p.get("chunk_index") or 0))

        status = _swarm_status(complete, checkpoint, drow)
        records = int(complete.get("committed_records") or checkpoint.get("committed_records") or 0)
        piece_bytes = sum(int(p.get("bytes") or 0) for p in pieces)
        local_pieces = sum(1 for p in pieces if p.get("have_local"))
        target = int(op.get("target_records") or 0) if str(op.get("target_records") or "").isdigit() else 0

        superseded_by: list[str] = []
        if shard == "y2025":
            superseded_by = ["y2025_q1", "y2025_q2", "y2025_q3", "y2025_q4"]
        if shard.startswith("y2025_monolith"):
            superseded_by = ["y2025_q1", "y2025_q2", "y2025_q3", "y2025_q4"]

        chat_bits = [
            f"{records:,} records" if records else "no records",
            f"{len(pieces)} pieces" if pieces else "pieces unknown",
            f"{local_pieces} local" if local_pieces else "Drive only",
        ]
        if status == "partial":
            chat_bits.append("incomplete lane")
        if superseded_by:
            chat_bits.append(f"use {superseded_by[0]} instead")

        swarms.append(
            {
                "swarm_id": f"datacite:{shard}",
                "kind": "datacite_swarm",
                "shard": shard,
                "partition_id": "catalog.datacite-harvest",
                "title": f"DataCite harvest {shard}",
                "status": status,
                "superseded_by": superseded_by,
                "records_committed": records,
                "target_records": target or None,
                "piece_count": len(pieces),
                "pieces_local": local_pieces,
                "bytes_manifest": piece_bytes,
                "remote": remote_base,
                "local_logical": local_logical,
                "operator": op,
                "completed_at": complete.get("completed_at"),
                "chat_line": f"DataCite swarm {shard} — {' · '.join(chat_bits)}",
                "action": "hydrate" if status == "complete" and local_pieces < len(pieces) else ("info" if superseded_by else "collect"),
                "action_label": "Hydrate swarm" if status == "complete" else "Legacy/incomplete lane",
                "fetch": {
                    "hydrate_shard": f"collection_hydrate partition catalog.datacite-harvest shard {shard}",
                    "hydrate_metadata": [f"{remote_base}/{n}" for n in (
                        "datacite.complete.json",
                        "datacite.checkpoint.json",
                        "full_index_manifest.json",
                    )],
                    "piece_template": f"rclone copyto {remote_base}/{{piece}} <local>/{{piece}}",
                },
                "pieces": pieces,
            }
        )

    return {
        "version": CATALOG_VERSION,
        "kind": "datacite_swarms",
        "canonical_root": drive_root,
        "partition_id": "catalog.datacite-harvest",
        "legacy_drive_prefix": legacy_drive,
        "legacy_local_prefix": legacy_local,
        "swarm_count": len(swarms),
        "records_committed_total": sum(int(s.get("records_committed") or 0) for s in swarms if not s.get("superseded_by")),
        "swarms": swarms,
    }


def build_trackers(repo_root: Path) -> dict[str, Any]:
    drive = canonical_drive_root(repo_root) or ""
    return {
        "version": CATALOG_VERSION,
        "trackers": [
            {
                "id": "tracker:canonical_gdrive",
                "kind": "tracker",
                "title": "Canonical GDrive vault",
                "role": "primary_swarm",
                "remote_root": drive,
                "say": "hydrate partition …",
                "when": "partition on Drive, not local",
            },
            {
                "id": "tracker:datacite_api_search",
                "kind": "tracker",
                "title": "DataCite live search API",
                "role": "vault_miss_supplement",
                "url": datacite_url(),
                "url_template": datacite_url(query="{query}", created="{created}"),
                "say": "source this for me",
                "when": "DOI or topic not in local swarm index",
            },
            {
                "id": "tracker:datacite_api_get",
                "kind": "tracker",
                "title": "DataCite DOI lookup",
                "role": "doi_resolver",
                "url_template": "https://api.datacite.org/dois/{doi}",
                "say": "collect DOI …",
                "when": "known DOI, any coverage gap",
            },
            {
                "id": "tracker:collection_hydrate",
                "kind": "tracker",
                "title": "Hydrate job (rclone pull)",
                "role": "fetch_executor",
                "job_type": "collection_hydrate",
                "say": "hydrate #N or hydrate shard y2025_q1",
                "when": "swarm on Drive, need local piece or shard",
            },
        ],
    }


def build_locators(repo_root: Path, *, limit: int = 5000) -> dict[str, Any]:
    """Sparse DOI → swarm/piece locators from curated catalog + registry + flywheel pins."""
    repo_root = Path(repo_root).resolve()
    locators: list[dict[str, Any]] = []
    seen: set[str] = set()

    existing = _load_json(catalog_root(repo_root) / "locators.json")
    for row in existing.get("locators") or []:
        doi = str(row.get("doi") or "").strip().lower()
        if not doi or doi in seen:
            continue
        seen.add(doi)
        locators.append(dict(row))

    curated = repo_root / "data_lake/dataset_catalog/curated_live/curated_dataset_index.jsonl"
    if curated.is_file():
        with curated.open(encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if len(locators) >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                did = str(row.get("doi") or row.get("dataset_id") or "")
                did = did.removeprefix("doi:").strip()
                if not did.startswith("10.") or did.lower() in seen:
                    continue
                seen.add(did.lower())
                local_path = str(row.get("local_path") or "")
                on_disk = bool(local_path) and (repo_root / local_path).exists()
                locators.append(
                    {
                        "locator_id": f"doi:{did}",
                        "doi": did,
                        "title": row.get("title"),
                        "in_vault": True,
                        "on_disk": on_disk,
                        "tracker": "tracker:datacite_api_get",
                        "say": f"collect DOI {did}",
                        "source": str(row.get("source") or "curated_live"),
                        "search_goal": (row.get("procurement") or {}).get("search_goal"),
                    }
                )

    reg_path = repo_root / "config/research_query_registry.json"
    if reg_path.is_file():
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        for row in reg.get("datasets") or []:
            if len(locators) >= limit:
                break
            did = str(row.get("doi") or row.get("dataset_id") or "")
            if did.startswith("datacite_"):
                did = did.replace("datacite_", "", 1)
            if not did.startswith("10."):
                continue
            if did.lower() in seen:
                continue
            seen.add(did.lower())
            local_path = str(row.get("local_path") or "")
            on_disk = bool(local_path) and not local_path.endswith("*")
            if on_disk:
                probe = repo_root / local_path
                on_disk = probe.is_file() or (probe.is_dir() and any(probe.iterdir()) if probe.is_dir() else False)
            locators.append(
                {
                    "locator_id": f"doi:{did}",
                    "doi": did,
                    "title": row.get("name"),
                    "in_vault": True,
                    "on_disk": on_disk,
                    "tracker": "tracker:datacite_api_get",
                    "handle": f"dataset:{row.get('dataset_id')}",
                    "say": f"preview dataset:{row.get('dataset_id')}" if on_disk else f"collect DOI {did}",
                    "source": "registry",
                }
            )

    return {"version": CATALOG_VERSION, "locator_count": len(locators), "locators": locators}


def build_catalog(repo_root: Path) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    out_root = catalog_root(repo_root)
    out_root.mkdir(parents=True, exist_ok=True)

    dictionary = build_dictionary(repo_root)
    datacite = build_datacite_swarms(repo_root, dictionary=dictionary)
    trackers = build_trackers(repo_root)
    locators = build_locators(repo_root)

    (out_root / "datacite_swarms.json").write_text(json.dumps(datacite, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_root / "trackers.json").write_text(json.dumps(trackers, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_root / "locators.json").write_text(json.dumps(locators, indent=2, ensure_ascii=False), encoding="utf-8")

    index = {
        "version": CATALOG_VERSION,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "purpose": "Torrent-style magnet catalog — swarms, pieces, trackers (bytes stay on Drive).",
        "dictionary_path": str(dictionary_path(repo_root).relative_to(repo_root)),
        "files": {
            "datacite_swarms": "catalog/datacite_swarms.json",
            "trackers": "catalog/trackers.json",
            "locators": "catalog/locators.json",
        },
        "summary": {
            "datacite_swarms": datacite.get("swarm_count"),
            "datacite_records_committed": datacite.get("records_committed_total"),
            "trackers": len(trackers.get("trackers") or []),
            "locators": locators.get("locator_count"),
            "pieces_cataloged": sum(int(s.get("piece_count") or 0) for s in datacite.get("swarms") or []),
        },
        "how_to_read": [
            "swarm = harvest lane (y2025_q1); pieces = datacite_NNNNNN.jsonl.gz chunks on canonical Drive",
            "have_local=false means magnet only — use fetch.hydrate_shard or tracker:datacite_api_get",
            "superseded_by means prefer quarterly shards over monolith lanes",
            "locators = sparse DOI pins from curated/registry; vault bulk DOI map is future work",
        ],
    }
    (out_root / "INDEX.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    chat_desk = {
        "version": CATALOG_VERSION,
        "catalog_index": "data_lake/collection/_index/catalog/INDEX.json",
        "quick_actions": {
            "swarm_on_drive": "hydrate shard {shard}",
            "single_piece": "rclone copyto {remote} {local}",
            "vault_miss": "source this for me (tracker:datacite_api_search)",
            "known_doi": "collect DOI {doi}",
        },
        "swarm_ids": [s["swarm_id"] for s in datacite.get("swarms") or [] if not s.get("superseded_by")],
    }
    (out_root / "chat_catalog_desk.json").write_text(json.dumps(chat_desk, indent=2), encoding="utf-8")

    return {
        "catalog_root": str(out_root),
        "index_path": str(out_root / "INDEX.json"),
        "summary": index["summary"],
    }


def flatten_for_search_index(repo_root: Path) -> list[dict[str, Any]]:
    """Catalog rows for FTS — DOI locators + API trackers (not harvest swarms)."""
    root = catalog_root(repo_root)
    items: list[dict[str, Any]] = []

    # datacite_swarms.json is ops/hydrate-only — excluded from research FTS.

    trackers_doc = _load_json(root / "trackers.json")
    for tr in trackers_doc.get("trackers") or []:
        tid = str(tr.get("id") or "")
        items.append(
            {
                "id": tid,
                "kind": "tracker",
                "domain": "catalog",
                "title": tr.get("title"),
                "chat_line": f"{tr.get('title')} — {tr.get('when')} · say: {tr.get('say')}",
                "body": " ".join(str(tr.get(k) or "") for k in ("role", "when", "say", "url", "url_template")),
                "action": "search_datacite" if "api" in tid else "info",
                "action_label": "External tracker",
                "partition_id": "",
                "partition_path": "",
                "handle": "",
                "score_boost": 1.0,
                "availability": {"have": True, "on_local": True, "on_drive": "n/a", "missing": []},
                "payload": {"tracker": tr},
            }
        )

    loc_doc = _load_json(root / "locators.json")
    for loc in (loc_doc.get("locators") or [])[:200]:
        lid = str(loc.get("locator_id") or "")
        items.append(
            {
                "id": lid,
                "kind": "doi_locator",
                "domain": "catalog",
                "title": loc.get("title") or loc.get("doi"),
                "chat_line": f"DOI {loc.get('doi')} — {loc.get('say')}",
                "body": f"{loc.get('doi')} {loc.get('title')} {loc.get('tracker')}",
                "action": "query_now" if loc.get("in_vault") else "collect",
                "action_label": "Curated DOI" if loc.get("source") == "curated_live" else "Registry DOI",
                "partition_id": "catalog.curated-index",
                "partition_path": "catalog/curated",
                "handle": loc.get("handle") or f"doi:{loc.get('doi')}",
                "score_boost": 2.0 if loc.get("in_vault") else 1.3,
                "availability": {
                    "have": bool(loc.get("in_vault")),
                    "on_local": bool(loc.get("in_vault")),
                    "on_drive": "unknown",
                    "missing": [] if loc.get("in_vault") else ["not_in_vault_locator"],
                },
                "payload": {"locator": loc},
            }
        )

    return items


def ensure_catalog(repo_root: Path) -> Path:
    index = catalog_root(repo_root) / "INDEX.json"
    dict_p = dictionary_path(repo_root)
    if not index.is_file():
        build_catalog(repo_root)
    elif dict_p.is_file() and dict_p.stat().st_mtime > index.stat().st_mtime:
        build_catalog(repo_root)
    return index


def get_swarm(repo_root: Path, shard: str) -> dict[str, Any] | None:
    """Lookup one DataCite swarm by shard name."""
    doc = _load_json(catalog_root(repo_root) / "datacite_swarms.json")
    return next((s for s in doc.get("swarms") or [] if s.get("shard") == shard), None)
