#!/usr/bin/env python3
"""Master collection dictionary — mini-schema + availability for every known asset."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.collection_resolve import (
    canonical_remote,
    list_shards,
    load_partitions,
    local_storage_path,
    parse_size_hint,
)
from scripts.research_data_mcp.procurement_fast import local_path_has_data, queue_output_on_disk

DICT_VERSION = 1


def dictionary_path(repo_root: Path) -> Path:
    return Path(repo_root).resolve() / "data_lake/collection/_index/collection_dictionary.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _human_bytes(n: int) -> str:
    if n <= 0:
        return "0 B"
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    v = float(n)
    for unit in units:
        if v < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(v)} B"
            return f"{v:.2f} {unit}"
        v /= 1024
    return f"{n} B"


def _chat_line(title: str, domain: str, action_label: str, note: str = "") -> str:
    base = f"{title} ({domain}) — {action_label}"
    return f"{base}. {note}".strip().rstrip(".")


def _action_for_availability(
    *,
    on_local_data: bool,
    harvest_complete: bool,
    on_drive_expected: bool,
    metadata_only: bool,
) -> tuple[str, str]:
    if on_local_data:
        return "query_now", "Query now"
    if harvest_complete and on_drive_expected:
        return "hydrate", "Hydrate from Drive"
    if metadata_only and harvest_complete:
        return "search_datacite", "Metadata on Drive"
    if harvest_complete:
        return "search_datacite", "Harvest complete"
    return "collect", "Harvest incomplete"


MINI_SCHEMA: dict[str, Any] = {
    "chat_hit": {
        "description": "Procurement search hit — what the chatbot reads first.",
        "fields": {
            "id": "stable key (partition id, registry:dataset_id, queue:task_id, datacite_shard:name)",
            "kind": "partition | registry_dataset | queue_task | datacite_shard | curated_catalog",
            "title": "human label",
            "domain": "markets | news | catalog | registry | …",
            "chat_line": "one-sentence summary for replies",
            "action": "query_now | hydrate | refresh | collect | search_datacite | info",
            "action_label": "short badge",
            "availability": "nested have/miss flags — see availability object",
            "paths": "legacy_local, drive_remote, handle",
        },
    },
    "availability": {
        "description": "Uniform have/miss block for every table row.",
        "fields": {
            "on_local": "bytes or rows present on this machine",
            "on_drive": "yes | expected | unknown | no",
            "have": "true when actionable without new collection",
            "missing": "list of short gap strings",
        },
    },
    "datacite_record": {
        "description": "One line in datacite_*.jsonl.gz harvest chunks.",
        "fields": {
            "catalogue_version": "full-index-0.1",
            "source": "datacite",
            "dataset_id": "DOI string",
            "title": "dataset title",
            "description": "text",
            "url": "landing URL",
            "tags": "subject keywords",
            "domain": "inferred topic bucket",
            "access_mode": "query_remote",
            "raw": "optional full DataCite API item",
        },
    },
    "datacite_shard": {
        "description": "One harvest lane under index_v3/{shard}/.",
        "fields": {
            "shard": "directory name (y2025_q1, y2023_2024, …)",
            "records_committed": "from datacite.complete.json",
            "jsonl_chunks": "count of datacite_*.jsonl.gz on disk",
            "operator": "host, created_years, datacite_query from shard manifest list",
        },
    },
    "registry_dataset": {
        "description": "config/research_query_registry.json entry.",
        "fields": {
            "dataset_id": "stable id",
            "name": "display name",
            "backend": "local_json_file | datacite_search | …",
            "local_path": "glob or file under repo",
            "analysis_readiness": "instant | sample_now_full_later | …",
            "handle": "dataset:{dataset_id}",
        },
    },
    "curated_row": {
        "description": "curated_dataset_index.jsonl promotion record.",
        "fields": {
            "dataset_id": "source-native id or DOI",
            "title": "title",
            "source": "huggingface | zenodo | datacite | openml | …",
            "promotion_tier": "tier_0 … tier_5",
            "domain": "inferred domain",
            "access_mode": "query_remote | sample_probe | …",
        },
    },
}


def _scan_datacite_shard(repo_root: Path, shard_dir: Path, operator: dict[str, str]) -> dict[str, Any]:
    shard = shard_dir.name
    complete = _load_json(shard_dir / "datacite.complete.json")
    checkpoint = _load_json(shard_dir / "datacite.checkpoint.json")
    heartbeat = _load_json(shard_dir / "datacite.heartbeat.json")
    manifest = _load_json(shard_dir / "full_index_manifest.json")

    jsonl_files = sorted(shard_dir.glob("datacite_*.jsonl*"))
    jsonl_bytes = sum(p.stat().st_size for p in jsonl_files if p.is_file())
    manifest_files = list((manifest.get("files") or []))
    manifest_bytes = sum(int(f.get("bytes") or 0) for f in manifest_files)

    records = int(complete.get("committed_records") or checkpoint.get("committed_records") or 0)
    harvest_complete = bool(complete.get("completed_at"))
    target_records = int(operator.get("target_records") or 0) if operator.get("target_records", "").isdigit() else 0

    on_local_data = jsonl_bytes > 0
    metadata_only = bool(complete or checkpoint or heartbeat) and not on_local_data
    on_drive_expected = harvest_complete and (manifest_bytes > 0 or records > 0)
    on_drive = "expected" if on_drive_expected else ("unknown" if metadata_only else "no")

    action, action_label = _action_for_availability(
        on_local_data=on_local_data,
        harvest_complete=harvest_complete,
        on_drive_expected=on_drive_expected,
        metadata_only=metadata_only,
    )

    missing: list[str] = []
    if harvest_complete and not on_local_data:
        missing.append("local_jsonl")
    if target_records and records < target_records * 0.99:
        missing.append("record_count_below_target")
    if not harvest_complete and records > 0:
        missing.append("harvest_not_marked_complete")
    if not complete and not checkpoint:
        missing.append("no_status_files")

    title = f"DataCite harvest {shard}"
    years = operator.get("created_years") or ""
    note_parts = []
    if records:
        note_parts.append(f"{records:,} records")
    if on_local_data:
        note_parts.append(f"{_human_bytes(jsonl_bytes)} local")
    elif on_drive_expected:
        note_parts.append("bulk on Drive — local metadata only")
    if years:
        note_parts.append(f"years={years}")

    part_id = "catalog.datacite-harvest"
    cfg = load_partitions(repo_root)
    part = next((p for p in cfg.get("partitions") or [] if p.get("id") == part_id), {})
    legacy_local = str(part.get("legacy_local_path") or "data_lake/dataset_catalog/index_v3")
    drive_remote = canonical_remote(repo_root, part) if part else ""

    return {
        "id": f"datacite_shard:{shard}",
        "kind": "datacite_shard",
        "shard": shard,
        "title": title,
        "domain": "catalog",
        "partition_id": part_id,
        "chat_line": _chat_line(title, "catalog", action_label, " · ".join(note_parts)),
        "action": action,
        "action_label": action_label,
        "operator": operator,
        "availability": {
            "have": on_local_data or (harvest_complete and on_drive_expected),
            "on_local": on_local_data,
            "on_local_jsonl_bytes": jsonl_bytes,
            "on_local_jsonl_chunks": len(jsonl_files),
            "local_metadata_only": metadata_only,
            "on_drive": on_drive,
            "harvest_complete": harvest_complete,
            "records_committed": records,
            "target_records": target_records or None,
            "manifest_chunk_count": len(manifest_files),
            "manifest_bytes": manifest_bytes,
            "missing": missing,
        },
        "paths": {
            "legacy_local": f"{legacy_local}/{shard}",
            "drive_remote": f"{drive_remote}/{shard}" if drive_remote else "",
            "status_files": [
                name
                for name in ("datacite.complete.json", "datacite.checkpoint.json", "datacite.heartbeat.json")
                if (shard_dir / name).is_file()
            ],
        },
        "timestamps": {
            "completed_at": complete.get("completed_at"),
            "checkpoint_updated_at": checkpoint.get("updated_at"),
            "heartbeat_at": heartbeat.get("updated_at") or heartbeat.get("ts"),
        },
    }


def _scan_datacite_shards(repo_root: Path) -> list[dict[str, Any]]:
    root = Path(repo_root).resolve() / "data_lake/dataset_catalog/index_v3"
    operator_map = {row["shard"]: row for row in list_shards(repo_root)}
    rows: list[dict[str, Any]] = []
    if not root.is_dir():
        return rows
    for shard_dir in sorted(root.iterdir()):
        if not shard_dir.is_dir() or shard_dir.name.startswith("."):
            continue
        op = operator_map.get(shard_dir.name, {})
        rows.append(_scan_datacite_shard(repo_root, shard_dir, op))
    return rows


def _load_semantic(repo_root: Path) -> dict[str, Any]:
    path = Path(repo_root).resolve() / "config/collection_semantic.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _semantic_block(semantic_cfg: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    pid = str(part["id"])
    domain = str(part.get("domain") or "")
    dom_tpl = (semantic_cfg.get("domain_templates") or {}).get(domain) or {}
    override = (semantic_cfg.get("partitions") or {}).get(pid) or {}
    return {
        "topics": override.get("topics") or [domain],
        "use_cases": override.get("use_cases") or dom_tpl.get("use_cases") or [],
        "example_questions": override.get("example_questions") or dom_tpl.get("example_questions") or [],
        "related_partition_ids": override.get("related") or [],
    }


def _scan_partition_row(repo_root: Path, part: dict[str, Any], manifest_row: dict[str, Any] | None) -> dict[str, Any]:
    pid = str(part["id"])
    domain = str(part.get("domain") or "")
    title = str(part.get("title") or pid)
    local_path = part.get("legacy_local_path")
    on_local = local_path_has_data(repo_root, str(local_path)) if local_path else False
    mrow = manifest_row or {}
    drive_info = mrow.get("drive") or {}
    local_info = mrow.get("local") or {}
    drive_bytes = int(drive_info.get("bytes") or 0)
    local_bytes = int(local_info.get("bytes") or 0)
    on_drive = bool(mrow.get("on_drive")) or drive_bytes > 10_000
    if drive_bytes > 0 and local_bytes > drive_bytes * 2:
        sync_status = "drive_behind_local"
    elif not on_drive and local_bytes > 0:
        sync_status = "local_only_pending_upload"
    elif on_drive:
        sync_status = "on_drive"
    else:
        sync_status = "unknown"
    cov = mrow.get("local_coverage_ratio")
    drive_h = drive_info.get("human") or part.get("drive_size_hint") or ""
    local_h = local_info.get("human") or ""

    action, action_label = _action_for_availability(
        on_local_data=on_local,
        harvest_complete=on_drive,
        on_drive_expected=on_drive,
        metadata_only=on_drive and not on_local,
    )
    if str(part.get("tier") or "") == "ops":
        action, action_label = "info", "Ops only"

    missing: list[str] = []
    if on_drive and not on_local and str(part.get("tier") or "") in {"hot", "cache"}:
        missing.append("local_cache")
    if not on_drive and not on_local:
        missing.append("no_bytes_anywhere")

    note = " · ".join(
        x
        for x in [
            drive_h and f"{drive_h} Drive",
            local_h and f"{local_h} local",
            cov is not None and f"{int(cov * 100)}% cached",
            sync_status,
        ]
        if x
    )
    semantic_cfg = _load_semantic(repo_root)

    return {
        "id": pid,
        "kind": "partition",
        "title": title,
        "domain": domain,
        "partition_id": pid,
        "partition_path": part.get("path"),
        "chat_line": _chat_line(title, domain, action_label, note),
        "action": action,
        "action_label": action_label,
        "tier": part.get("tier"),
        "registry_dataset_ids": part.get("registry_dataset_ids") or [],
        "replaces_legacy_name": part.get("replaces_legacy_name"),
        "semantic": _semantic_block(semantic_cfg, part),
        "sync_status": sync_status,
        "description": part.get("description", ""),
        "professor_label": part.get("professor_label") or title,
        "availability": {
            "have": on_local or on_drive,
            "on_local": on_local,
            "on_drive": "yes" if on_drive else "no",
            "local_coverage_ratio": cov,
            "missing": missing,
        },
        "paths": {
            "legacy_local": local_path,
            "legacy_drive": part.get("legacy_drive_path"),
            "target_drive": part.get("target_drive_path"),
            "drive_remote": mrow.get("drive_remote") or canonical_remote(repo_root, part),
        },
    }


def _scan_registry(repo_root: Path, partitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    path = Path(repo_root).resolve() / "config/research_query_registry.json"
    if not path.is_file():
        return []
    reg = json.loads(path.read_text(encoding="utf-8"))
    part_by_reg: dict[str, str] = {}
    for part in partitions:
        for rid in part.get("registry_dataset_ids") or []:
            part_by_reg[str(rid)] = str(part["id"])

    rows: list[dict[str, Any]] = []
    for row in reg.get("datasets") or []:
        did = str(row.get("dataset_id") or "")
        if not did:
            continue
        local_path = str(row.get("local_path") or row.get("local_root") or "")
        on_disk = local_path_has_data(repo_root, local_path) if local_path else False
        action = "query_now" if on_disk else "collect"
        action_label = "Query now" if on_disk else "Not on disk"
        missing = [] if on_disk else ["local_bytes"]
        title = str(row.get("name") or did)
        rows.append(
            {
                "id": f"registry:{did}",
                "kind": "registry_dataset",
                "dataset_id": did,
                "title": title,
                "domain": part_by_reg.get(did, "registry"),
                "partition_id": part_by_reg.get(did, ""),
                "chat_line": _chat_line(title, "registry", action_label, f"dataset:{did}"),
                "action": action,
                "action_label": action_label,
                "handle": f"dataset:{did}",
                "backend": row.get("backend"),
                "analysis_readiness": row.get("analysis_readiness"),
                "local_path": local_path or None,
                "availability": {
                    "have": on_disk,
                    "on_local": on_disk,
                    "on_drive": "unknown",
                    "missing": missing,
                },
            }
        )
    return rows


def _scan_queue(repo_root: Path) -> list[dict[str, Any]]:
    path = Path(repo_root).resolve() / "config/data_collection_queue.json"
    if not path.is_file():
        return []
    tasks = json.loads(path.read_text(encoding="utf-8")).get("tasks") or []
    rows: list[dict[str, Any]] = []
    for task in tasks:
        tid = str(task.get("id") or "")
        if not tid:
            continue
        on_disk = queue_output_on_disk(repo_root, task)
        enabled = bool(task.get("enabled", True))
        action = "refresh" if on_disk else "collect"
        action_label = "Refresh (queue)" if on_disk else "Collect (queue)"
        title = str(task.get("title") or tid)
        missing = [] if on_disk else ["output_not_on_disk"]
        rows.append(
            {
                "id": f"queue:{tid}",
                "kind": "queue_task",
                "task_id": tid,
                "title": title,
                "domain": "ops",
                "chat_line": _chat_line(title, "collection queue", action_label),
                "action": action,
                "action_label": action_label,
                "enabled": enabled,
                "credential_required": bool(task.get("credential_required")),
                "output_hint": task.get("output_hint"),
                "estimated_runtime": task.get("estimated_runtime"),
                "availability": {
                    "have": on_disk,
                    "on_local": on_disk,
                    "on_drive": "unknown",
                    "missing": missing if enabled else missing + ["disabled"],
                },
            }
        )
    return rows


def _count_jsonl_rows(path: Path, *, max_lines: int = 0) -> int:
    if not path.is_file():
        return 0
    count = 0
    opener: Any
    if path.suffix == ".gz":
        import gzip

        opener = gzip.open(path, "rt", encoding="utf-8", errors="ignore")
    else:
        opener = path.open(encoding="utf-8", errors="ignore")
    with opener as fh:
        for line in fh:
            if line.strip():
                count += 1
                if max_lines and count >= max_lines:
                    break
    return count


def _scan_curated_catalogs(repo_root: Path) -> list[dict[str, Any]]:
    root = Path(repo_root).resolve() / "data_lake/dataset_catalog"
    specs = [
        ("curated_live", "Curated dataset index (live)", "catalog.curated-index"),
        ("curated_strict", "Curated dataset index (strict)", "catalog.curated-index"),
        ("curated", "Curated dataset index (base)", "catalog.curated-index"),
    ]
    rows: list[dict[str, Any]] = []
    for subdir, label, part_id in specs:
        base = root / subdir
        jsonl = base / "curated_dataset_index.jsonl"
        summary = _load_json(base / "curated_dataset_index_summary.json")
        if not jsonl.is_file() and not summary:
            continue
        jsonl_bytes = jsonl.stat().st_size if jsonl.is_file() else 0
        row_count = _count_jsonl_rows(jsonl) if jsonl.is_file() else 0
        counts = summary.get("counts") or {}
        tier5 = int(counts.get("tier_5_must_integrate") or 0)
        rows.append(
            {
                "id": f"curated:{subdir}",
                "kind": "curated_catalog",
                "catalog_id": subdir,
                "title": label,
                "domain": "catalog",
                "partition_id": part_id,
                "chat_line": _chat_line(
                    label,
                    "catalog",
                    "Query now" if jsonl_bytes else "Missing",
                    f"{row_count:,} rows · tier_5={tier5}",
                ),
                "action": "query_now" if jsonl_bytes else "collect",
                "action_label": "Query now" if jsonl_bytes else "Rebuild curated index",
                "availability": {
                    "have": jsonl_bytes > 0,
                    "on_local": jsonl_bytes > 0,
                    "on_drive": "unknown",
                    "jsonl_bytes": jsonl_bytes,
                    "row_count": row_count,
                    "summary_counts": counts,
                    "missing": [] if jsonl_bytes else ["curated_jsonl"],
                },
                "paths": {"local_jsonl": str(jsonl.relative_to(repo_root)) if jsonl.is_file() else ""},
            }
        )

    seed = root / "external_dataset_catalog_seed.jsonl"
    if seed.is_file():
        rows.append(
            {
                "id": "curated:external_seed",
                "kind": "curated_catalog",
                "catalog_id": "external_seed",
                "title": "External dataset catalog seed",
                "domain": "catalog",
                "partition_id": "catalog.curated-index",
                "chat_line": _chat_line("External dataset seed", "catalog", "Query now", _human_bytes(seed.stat().st_size)),
                "action": "query_now",
                "action_label": "Query now",
                "availability": {
                    "have": True,
                    "on_local": True,
                    "on_drive": "unknown",
                    "jsonl_bytes": seed.stat().st_size,
                    "row_count": _count_jsonl_rows(seed),
                    "missing": [],
                },
                "paths": {"local_jsonl": str(seed.relative_to(repo_root))},
            }
        )
    return rows


def _legacy_catalog_layers(repo_root: Path) -> list[dict[str, Any]]:
    root = Path(repo_root).resolve() / "data_lake/dataset_catalog"
    layers = [
        ("index_v2", "DataCite harvest index_v2 (legacy)"),
        ("full_index", "Full index monolith checkpoint"),
        ("full_index_probe", "Full index probe run"),
    ]
    rows: list[dict[str, Any]] = []
    for subdir, label in layers:
        base = root / subdir
        if not base.is_dir():
            continue
        manifest = _load_json(base / "full_index_manifest.json")
        checkpoint = _load_json(base / "datacite.checkpoint.json")
        jsonl = list(base.glob("**/*.jsonl*"))
        jsonl_bytes = sum(p.stat().st_size for p in jsonl if p.is_file())
        rows.append(
            {
                "id": f"legacy_catalog:{subdir}",
                "kind": "legacy_catalog",
                "title": label,
                "domain": "catalog",
                "chat_line": _chat_line(label, "catalog", "Reference only", _human_bytes(jsonl_bytes) or "checkpoints only"),
                "action": "info",
                "action_label": "Legacy layer",
                "availability": {
                    "have": bool(jsonl_bytes or checkpoint or manifest),
                    "on_local": bool(jsonl_bytes),
                    "on_drive": "unknown",
                    "jsonl_bytes": jsonl_bytes,
                    "missing": ["superseded_by_index_v3"] if subdir != "full_index_probe" else [],
                },
            }
        )
    return rows


def _build_gaps(tables: dict[str, list[dict[str, Any]]]) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    for row in tables.get("datacite_shards") or []:
        for miss in row.get("availability", {}).get("missing") or []:
            gaps.append(
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "gap": miss,
                    "chat_line": row.get("chat_line", ""),
                    "suggested_action": row.get("action_label", ""),
                }
            )
    for row in tables.get("registry_datasets") or []:
        if not row.get("availability", {}).get("have"):
            gaps.append(
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "gap": "not_on_disk",
                    "chat_line": row.get("chat_line", ""),
                    "suggested_action": "collect or hydrate",
                }
            )
    for row in tables.get("partitions") or []:
        for miss in row.get("availability", {}).get("missing") or []:
            if miss == "local_cache":
                gaps.append(
                    {
                        "id": row["id"],
                        "kind": row["kind"],
                        "gap": miss,
                        "chat_line": row.get("chat_line", ""),
                        "suggested_action": "hydrate partition",
                    }
                )
    return gaps


def build_dictionary(repo_root: Path) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    cfg = load_partitions(repo_root)
    partitions_cfg = list(cfg.get("partitions") or [])
    manifest = _load_json(repo_root / "data_lake/collection/_index/manifest_latest.json")
    manifest_by_id = {row.get("id"): row for row in manifest.get("collections") or []}

    datacite_shards = _scan_datacite_shards(repo_root)
    partitions = [
        _scan_partition_row(repo_root, part, manifest_by_id.get(str(part["id"])))
        for part in partitions_cfg
    ]
    registry_datasets = _scan_registry(repo_root, partitions_cfg)
    queue_tasks = _scan_queue(repo_root)
    curated_catalogs = _scan_curated_catalogs(repo_root)
    legacy_catalog_layers = _legacy_catalog_layers(repo_root)

    tables = {
        "datacite_shards": datacite_shards,
        "partitions": partitions,
        "registry_datasets": registry_datasets,
        "queue_tasks": queue_tasks,
        "curated_catalogs": curated_catalogs,
        "legacy_catalog_layers": legacy_catalog_layers,
    }
    gaps = _build_gaps(tables)

    dc_records = sum(int(r.get("availability", {}).get("records_committed") or 0) for r in datacite_shards)
    dc_complete = sum(1 for r in datacite_shards if r.get("availability", {}).get("harvest_complete"))
    dc_local_jsonl = sum(int(r.get("availability", {}).get("on_local_jsonl_bytes") or 0) for r in datacite_shards)

    return {
        "version": DICT_VERSION,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "purpose": "Single table dictionary: mini-schema + what we have vs miss (DataCite first, then partitions/registry/queue/curated).",
        "canonical_root": cfg.get("canonical_root"),
        "mini_schema": MINI_SCHEMA,
        "summary": {
            "datacite_shards": len(datacite_shards),
            "datacite_shards_complete": dc_complete,
            "datacite_records_committed": dc_records,
            "datacite_local_jsonl_bytes": dc_local_jsonl,
            "datacite_local_jsonl_human": _human_bytes(dc_local_jsonl),
            "partitions_total": len(partitions),
            "partitions_with_local_data": sum(1 for r in partitions if r.get("availability", {}).get("on_local")),
            "partitions_on_drive": sum(1 for r in partitions if r.get("availability", {}).get("on_drive") == "yes"),
            "registry_total": len(registry_datasets),
            "registry_on_disk": sum(1 for r in registry_datasets if r.get("availability", {}).get("have")),
            "queue_total": len(queue_tasks),
            "queue_with_output": sum(1 for r in queue_tasks if r.get("availability", {}).get("have")),
            "curated_catalogs": len(curated_catalogs),
            "gap_count": len(gaps),
        },
        "tables": tables,
        "gaps": gaps,
    }


def write_dictionary(repo_root: Path) -> dict[str, Any]:
    payload = build_dictionary(repo_root)
    out = dictionary_path(repo_root)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    payload["output_path"] = str(out)
    return payload


SEARCH_INDEX_TABLES = (
    "registry_datasets",
    "curated_catalogs",
    "partitions",
    "queue_tasks",
    "legacy_catalog_layers",
    "datacite_shards",
)


def score_boost_for_row(row: dict[str, Any]) -> float:
    """FTS ranking boost from dictionary action + availability."""
    action = str(row.get("action") or "")
    av = row.get("availability") or {}
    if action == "query_now" and av.get("have"):
        return 3.2 if row.get("kind") == "registry_dataset" else 3.0
    if action == "hydrate":
        return 2.2
    if action == "search_datacite":
        records = int(av.get("records_committed") or 0)
        if row.get("kind") == "datacite_shard":
            return 0.15
        if records > 10_000_000:
            return 1.4
        return 1.1
    if action == "refresh":
        return 0.55
    if action == "collect":
        return 1.1 if row.get("kind") == "queue_task" else 1.5
    if action == "info":
        return 0.35 if row.get("kind") == "legacy_catalog" else 0.5
    return 0.8


def _body_for_row(row: dict[str, Any]) -> str:
    av = row.get("availability") or {}
    parts = [
        row.get("title"),
        row.get("domain"),
        row.get("chat_line"),
        row.get("dataset_id"),
        row.get("task_id"),
        row.get("shard"),
        row.get("partition_id"),
        row.get("replaces_legacy_name"),
        " ".join(str(x) for x in (row.get("registry_dataset_ids") or [])),
        " ".join(str(x) for x in (av.get("missing") or [])),
    ]
    if av.get("records_committed"):
        parts.append(f"records {av['records_committed']}")
    if row.get("operator"):
        op = row["operator"]
        parts.extend([op.get("query"), op.get("created_years")])
    return " ".join(str(p) for p in parts if p)


def dictionary_row_to_index_item(row: dict[str, Any]) -> dict[str, Any]:
    """Map one dictionary table row → FTS insert row."""
    av = row.get("availability") or {}
    payload = {k: v for k, v in row.items() if k not in {"chat_line", "action", "action_label"}}
    return {
        "id": row["id"],
        "kind": row.get("kind"),
        "domain": row.get("domain") or "",
        "title": row.get("title") or row["id"],
        "chat_line": row.get("chat_line") or "",
        "body": _body_for_row(row),
        "action": row.get("action") or "info",
        "action_label": row.get("action_label") or "",
        "partition_id": row.get("partition_id") or "",
        "partition_path": row.get("partition_path") or "",
        "handle": row.get("handle") or "",
        "score_boost": score_boost_for_row(row),
        "availability": av,
        "payload": payload,
    }


def flatten_for_search_index(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """All dictionary rows indexed for procurement FTS search."""
    tables = doc.get("tables") or {}
    items: list[dict[str, Any]] = []
    for table_name in SEARCH_INDEX_TABLES:
        for row in tables.get(table_name) or []:
            if row.get("kind") == "queue_task" and not row.get("enabled", True):
                continue
            items.append(dictionary_row_to_index_item(row))
    return items
