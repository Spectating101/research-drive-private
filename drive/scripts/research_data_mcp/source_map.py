"""Canonical databank source map — resolve registry cards to research sources."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

SOURCE_MAP_REL = "config/databank_source_map.json"
DESK_SOURCES_REL = "config/desk_sources.json"


def _repo(repo_root: Path) -> Path:
    return Path(repo_root).resolve()


@lru_cache(maxsize=8)
def _load_json(repo_root: str, rel: str) -> dict[str, Any]:
    path = _repo(Path(repo_root)) / rel
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def source_map_path(repo_root: Path) -> Path:
    root = _repo(repo_root)
    for candidate in (root / "config/databank_source_map.json", root / "drive/config/databank_source_map.json"):
        if candidate.is_file():
            return candidate
    return root / SOURCE_MAP_REL


def load_source_map(repo_root: Path) -> dict[str, Any]:
    path = source_map_path(repo_root)
    if not path.is_file():
        return {"version": 0, "sources": [], "error": f"missing {path}"}
    return json.loads(path.read_text(encoding="utf-8"))


def load_desk_connectors(repo_root: Path) -> dict[str, dict[str, Any]]:
    doc = _load_json(str(repo_root), DESK_SOURCES_REL)
    return {str(s["id"]): s for s in doc.get("sources") or [] if s.get("id")}


def _rule_match(ds: dict[str, Any], rules: dict[str, Any], *, partition_ids: set[str]) -> bool:
    did = str(ds.get("dataset_id") or "")
    if not did:
        return False
    if did in set(rules.get("dataset_ids") or []):
        return True
    if did in set(rules.get("exclude_dataset_ids") or []):
        return False
    prefix = rules.get("dataset_id_prefix")
    if prefix and did.startswith(str(prefix)):
        return True
    for pfx in rules.get("dataset_id_prefixes") or []:
        if did.startswith(str(pfx)):
            return True
    for needle in rules.get("dataset_id_contains") or []:
        if str(needle).lower() in did.lower():
            return True
    backend = str(ds.get("backend") or "")
    if backend and backend in set(rules.get("backends") or []):
        return True
    pid = str(ds.get("partition_id") or (ds.get("collection") or {}).get("partition_id") or "")
    rule_parts = set(rules.get("partition_ids") or [])
    if pid and pid in rule_parts:
        return True
    proc = ds.get("procurement") or {}
    if isinstance(proc, dict):
        src = str(proc.get("source") or proc.get("collect_via") or "")
        proc_rules = rules.get("procurement_source")
        if proc_rules:
            allowed = {proc_rules} if isinstance(proc_rules, str) else set(proc_rules)
            if src and src in allowed:
                return True
    return False


def resolve_dataset_source(
    ds: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    partition_ids: set[str] | None = None,
) -> str | None:
    """Return source id for a registry row; explicit source_id wins."""
    explicit = str(ds.get("source_id") or "").strip()
    if explicit:
        return explicit
    parts = partition_ids or set()
    pid = str(ds.get("partition_id") or (ds.get("collection") or {}).get("partition_id") or "")
    if pid:
        parts = parts | {pid}

    # Priority: derived internal and specific sources before broad catalogs
    priority = [
        "lseg_edp",
        "lseg_desktop_rescue",
        "derived_synthesis",
        "derived_research_panels",
        "gdelt",
        "crsp_moveit",
        "capital_iq_compustat",
        "wrds_crsp_compustat",
        "bigquery_public",
        "datacite_harvest",
        "datacite_procured",
        "sec_edgar",
        "twse_official",
        "mops_taiwan",
        "yfinance_public",
        "coingecko",
        "ethereum_onchain",
        "nft_opensea",
        "reddit_social",
        "public_macro",
        "ops_investment_platform",
        "huggingface",
        "open_research_catalogs",
        "procured_misc",
        "web_scrape_catalog",
    ]
    by_id = {str(s["id"]): s for s in sources if s.get("id")}
    ordered = [by_id[sid] for sid in priority if sid in by_id]
    for src in ordered:
        rules = src.get("registry_rules") or {}
        if _rule_match(ds, rules, partition_ids=parts):
            if did := str(ds.get("dataset_id") or ""):
                excluded = set(rules.get("exclude_dataset_ids") or [])
                if did in excluded:
                    continue
            return str(src["id"])
    return None


def _local_exists(repo_root: Path, rel: str) -> bool:
    if not rel:
        return False
    p = repo_root / rel
    return p.exists()


def _source_materialization(repo_root: Path, src: dict[str, Any]) -> dict[str, Any]:
    mode = str(src.get("access_mode") or "")
    roots = [str(r) for r in src.get("local_roots") or []]
    local_ok = any(_local_exists(repo_root, r) for r in roots)
    if src.get("expected_local_root"):
        local_ok = local_ok or _local_exists(repo_root, str(src["expected_local_root"]))
    out: dict[str, Any] = {
        "access_mode": mode,
        "status": src.get("status"),
        "local_present": local_ok if roots or src.get("expected_local_root") else None,
    }
    if mode == "planned":
        out["ingested"] = False
    elif mode == "live_connector":
        out["ingested"] = None
        out["mirror_note"] = "Live at request time; registry may have partial catalogue cards only"
    elif mode == "materialized_bulk":
        out["ingested"] = local_ok
    else:
        out["ingested"] = local_ok if roots else None
    return out


def build_source_map_audit(repo_root: Path) -> dict[str, Any]:
    root = _repo(repo_root)
    doc = load_source_map(root)
    sources_cfg = list(doc.get("sources") or [])
    reg_doc = json.loads((root / "config/research_query_registry.json").read_text(encoding="utf-8"))
    datasets = list(reg_doc.get("datasets") or [])
    connectors = load_desk_connectors(root)

    by_source: dict[str, list[str]] = {str(s["id"]): [] for s in sources_cfg if s.get("id")}
    unmapped: list[str] = []

    for ds in datasets:
        did = str(ds.get("dataset_id") or "")
        if not did:
            continue
        sid = resolve_dataset_source(ds, sources_cfg)
        if sid:
            by_source.setdefault(sid, []).append(did)
        else:
            unmapped.append(did)

    source_rows: list[dict[str, Any]] = []
    for src in sources_cfg:
        sid = str(src.get("id") or "")
        if not sid:
            continue
        desk_id = str(src.get("desk_connector_id") or "")
        desk = connectors.get(desk_id) if desk_id else None
        cards = sorted(by_source.get(sid, []))
        instant_n = sum(
            1
            for ds in datasets
            if str(ds.get("dataset_id")) in cards and str(ds.get("analysis_readiness")) == "instant"
        )
        mat = _source_materialization(root, src)
        row = {
            "id": sid,
            "label": src.get("label"),
            "provider": src.get("provider"),
            "desk_connector_id": desk_id or None,
            "desk_connector_label": (desk or {}).get("label"),
            "access_mode": src.get("access_mode"),
            "license": src.get("license"),
            "status": src.get("status"),
            "capabilities": src.get("capabilities") or [],
            "geographies": src.get("geographies") or [],
            "partition_ids": src.get("partition_ids") or [],
            "professor_visible": src.get("professor_visible", True),
            "registry_dataset_count": len(cards),
            "instant_dataset_count": instant_n,
            "registry_dataset_ids": cards,
            "materialization": mat,
            "known_gaps": src.get("known_gaps") or [],
            "notes": src.get("notes"),
            "bulk_note": src.get("bulk_note"),
            "mcp_routes": src.get("mcp_routes") or [],
            "canonical_run": src.get("canonical_run"),
            "queue_task_id": src.get("queue_task_id"),
        }
        source_rows.append(row)

    # Connector coverage: desk_sources without source_map entry
    mapped_connectors = {str(s.get("desk_connector_id")) for s in sources_cfg if s.get("desk_connector_id")}
    orphan_connectors = sorted(set(connectors) - mapped_connectors - {"gdrive_vault"})

    by_mode: dict[str, int] = {}
    for row in source_rows:
        mode = str(row.get("access_mode") or "unknown")
        by_mode[mode] = by_mode.get(mode, 0) + row.get("registry_dataset_count", 0)

    return {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "source_map_version": doc.get("version"),
        "summary": {
            "registry_datasets": len(datasets),
            "mapped_datasets": len(datasets) - len(unmapped),
            "unmapped_datasets": len(unmapped),
            "source_systems": len(source_rows),
            "live_connectors_desk": len(connectors),
            "orphan_desk_connectors": orphan_connectors,
            "registry_cards_by_access_mode": by_mode,
        },
        "access_modes": doc.get("access_modes") or {},
        "capabilities_glossary": doc.get("capabilities_glossary") or {},
        "sources": source_rows,
        "unmapped_registry_ids": sorted(unmapped),
        "documentation": {
            "canonical_config": "drive/config/databank_source_map.json",
            "desk_connectors": "config/desk_sources.json",
            "regenerate": "python3 scripts/databank_source_map.py --json",
        },
    }


def stamp_registry_sources(repo_root: Path, *, dry_run: bool = False) -> dict[str, Any]:
    root = _repo(repo_root)
    doc = load_source_map(root)
    sources_cfg = list(doc.get("sources") or [])
    reg_path = root / "config/research_query_registry.json"
    reg_doc = json.loads(reg_path.read_text(encoding="utf-8"))
    stamped = 0
    for ds in reg_doc.get("datasets") or []:
        sid = resolve_dataset_source(ds, sources_cfg)
        if not sid:
            continue
        src = next((s for s in sources_cfg if s.get("id") == sid), {})
        if str(ds.get("source_id") or "") != sid:
            stamped += 1
            if not dry_run:
                ds["source_id"] = sid
                ds["source_system"] = str(src.get("label") or sid)
                ds["source_access_mode"] = str(src.get("access_mode") or "")
    if not dry_run and stamped:
        reg_path.write_text(json.dumps(reg_doc, indent=2) + "\n", encoding="utf-8")
    return {"stamped": stamped, "dry_run": dry_run}
