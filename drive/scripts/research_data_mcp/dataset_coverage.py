"""Dataset-level coverage profiles, collection bulk mapping, proxy/synthetic paths."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

PROXIES_REL = "config/databank_coverage_proxies.json"
SYNTHESIS_REL = "config/synthesis_profiles.json"


def _repo(repo_root: Path) -> Path:
    return Path(repo_root).resolve()


@lru_cache(maxsize=8)
def _load_json(repo_root: str, rel: str) -> dict[str, Any]:
    path = _repo(Path(repo_root)) / rel
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_coverage_proxies(repo_root: Path) -> dict[str, Any]:
    root = _repo(repo_root)
    for candidate in (root / PROXIES_REL, root / f"drive/{PROXIES_REL}"):
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
    return {"version": 0, "capability_proxies": [], "collection_bulk_profiles": {}}


def _dir_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def _probe_parquet(path: Path, time_field: str | None, entity_fields: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"path": str(path), "bytes": path.stat().st_size if path.exists() else 0}
    try:
        import pyarrow.parquet as pq

        meta = pq.read_metadata(path)
        out["row_count"] = meta.num_rows
        out["columns"] = [meta.schema.column(i).name for i in range(meta.num_columns)]
    except Exception as exc:
        out["probe_error"] = str(exc)[:120]
        return out

    if not time_field or time_field not in out.get("columns", []):
        return out

    try:
        import pandas as pd

        ts = pd.read_parquet(path, columns=[time_field])
        col = ts[time_field]
        out["time_min"] = str(col.min())
        out["time_max"] = str(col.max())
        if hasattr(col, "nunique"):
            out["time_periods"] = int(col.nunique())
    except Exception as exc:
        out["time_probe_error"] = str(exc)[:120]

    ent_cols = [c for c in entity_fields if c in out.get("columns", [])]
    if ent_cols:
        try:
            import pandas as pd

            sample = pd.read_parquet(path, columns=ent_cols[:3])
            for c in ent_cols[:3]:
                if c in sample.columns:
                    out[f"{c}_unique"] = int(sample[c].nunique())
        except Exception:
            pass

    return out


def _probe_csv(path: Path, time_field: str | None, entity_fields: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"path": str(path), "bytes": path.stat().st_size if path.exists() else 0}
    try:
        import pandas as pd

        usecols = [c for c in ([time_field] if time_field else []) + entity_fields if c]
        df = pd.read_csv(path, usecols=usecols or None, nrows=50000)
        out["row_count_sampled"] = len(df)
        out["columns"] = list(df.columns)
        if time_field and time_field in df.columns:
            out["time_min"] = str(df[time_field].min())
            out["time_max"] = str(df[time_field].max())
        for c in entity_fields:
            if c in df.columns:
                out[f"{c}_unique_sampled"] = int(df[c].nunique())
    except Exception as exc:
        out["probe_error"] = str(exc)[:120]
    return out


def _resolve_dataset_path(repo_root: Path, ds: dict[str, Any]) -> Path | None:
    try:
        from scripts.research_query_engine.engine import ResearchQueryEngine

        engine = ResearchQueryEngine(repo_root / "config/research_query_registry.json", repo_root=repo_root)
        path, _ = engine._resolve_panel_path(ds, {})
        return path
    except Exception:
        root_rel = str(ds.get("local_root") or "")
        file_rel = str(ds.get("local_file") or "")
        if not root_rel:
            return None
        p = repo_root / root_rel
        if file_rel:
            candidate = p / file_rel
            if candidate.exists():
                return candidate
        run_id = str(ds.get("default_run_id") or "")
        if run_id:
            candidate = p / run_id / (file_rel or f"{ds['dataset_id']}.parquet")
            if candidate.exists():
                return candidate
        return p if p.exists() else None


def _infer_capabilities(dataset_id: str, ds: dict[str, Any], proxies_doc: dict[str, Any]) -> list[str]:
    explicit = (proxies_doc.get("dataset_capability_map") or {}).get(dataset_id)
    if explicit is not None:
        return list(explicit)
    caps: list[str] = []
    grain = str(ds.get("grain") or "")
    did = dataset_id.lower()
    if "pit" in did or "membership" in did or "survivorship" in grain:
        caps.append("index_pit_survivorship")
    if "estimate" in did or "revision" in did or "consensus" in did:
        caps.append("estimates_revisions")
    if "fundamental" in did:
        caps.append("fundamentals")
    if "risk" in did or "vol" in did:
        caps.append("risk_overlay")
    if "gdelt" in did and "country" in did:
        caps.append("country_news_shocks")
    if "shock" in did or "entity" in grain:
        caps.extend(["entity_news_shocks", "entity_join_gdelt_ric"])
    if "sec" in did or "mops" in did or "twse" in did:
        caps.append("governance_regulatory")
    if "coingecko" in did or "ethereum" in did or "usdt" in did:
        caps.append("onchain_crypto")
    if "reddit" in did:
        caps.append("social_sentiment")
    return sorted(set(caps))


def profile_instant_datasets(repo_root: Path, proxies_doc: dict[str, Any]) -> list[dict[str, Any]]:
    reg = json.loads((repo_root / "config/research_query_registry.json").read_text(encoding="utf-8"))
    geo_hints = proxies_doc.get("dataset_geography_hints") or {}
    rows: list[dict[str, Any]] = []

    for ds in reg.get("datasets") or []:
        did = str(ds.get("dataset_id") or "")
        if not did:
            continue
        readiness = str(ds.get("analysis_readiness") or "")
        backend = str(ds.get("backend") or "")
        profile: dict[str, Any] = {
            "dataset_id": did,
            "name": ds.get("name"),
            "source_id": ds.get("source_id"),
            "partition_id": ds.get("partition_id") or (ds.get("collection") or {}).get("partition_id"),
            "analysis_readiness": readiness,
            "backend": backend,
            "grain": ds.get("grain"),
            "time_field": ds.get("time_field"),
            "entity_fields": ds.get("entity_fields") or [],
            "join_keys": ds.get("join_keys") or [],
            "research_capabilities": _infer_capabilities(did, ds, proxies_doc),
            "geographies": geo_hints.get(did) or [],
            "field_coverage": ds.get("field_coverage"),
            "known_gap": ds.get("known_gap"),
            "entitlement_status": ds.get("entitlement_status"),
            "limitations": ds.get("limitations"),
        }

        if readiness == "instant" and backend in {
            "local_parquet_panel",
            "local_gdelt_panel_csv",
            "local_gdelt_high_priority_csv",
        }:
            path = _resolve_dataset_path(repo_root, ds)
            if path and path.is_file():
                time_f = str(ds.get("time_field") or "date")
                ents = [str(x) for x in ds.get("entity_fields") or []]
                if path.suffix.lower() == ".parquet":
                    profile["disk_probe"] = _probe_parquet(path, time_f, ents)
                else:
                    profile["disk_probe"] = _probe_csv(path, time_f, ents)
                profile["materialized"] = True
            else:
                profile["materialized"] = False
                profile["disk_probe"] = {"resolve_error": "path not found"}
        elif readiness == "instant":
            profile["materialized"] = None
        else:
            profile["materialized"] = False
            profile["surface"] = "metadata_or_catalogue"

        rows.append(profile)
    return rows


def profile_collections(
    repo_root: Path, proxies_doc: dict[str, Any], dataset_profiles: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    parts_cfg = json.loads((repo_root / "config/collection_partitions.json").read_text(encoding="utf-8"))
    bulk_profiles = proxies_doc.get("collection_bulk_profiles") or {}

    by_partition: dict[str, list[str]] = {}
    instant_by_partition: dict[str, int] = {}
    for p in dataset_profiles:
        pid = str(p.get("partition_id") or "")
        if pid:
            by_partition.setdefault(pid, []).append(str(p["dataset_id"]))
        if p.get("analysis_readiness") == "instant" and pid:
            instant_by_partition[pid] = instant_by_partition.get(pid, 0) + 1

    rows: list[dict[str, Any]] = []
    for part in parts_cfg.get("partitions") or []:
        pid = str(part.get("id") or "")
        if not pid:
            continue
        local_rel = str(part.get("legacy_local_path") or "")
        local = repo_root / local_rel if local_rel else None
        local_bytes = _dir_bytes(local) if local else 0
        bulk = bulk_profiles.get(pid) or {}
        reg_ids = list(part.get("registry_dataset_ids") or [])
        rows.append(
            {
                "partition_id": pid,
                "domain": part.get("domain"),
                "title": part.get("title"),
                "status": part.get("status"),
                "source_id": bulk.get("source_id"),
                "local_path": local_rel or None,
                "local_bytes": local_bytes,
                "local_bytes_human": _human_bytes(local_bytes),
                "drive_size_hint": part.get("drive_size_hint"),
                "registry_dataset_ids": reg_ids,
                "registry_card_count": len(by_partition.get(pid, [])),
                "instant_card_count": instant_by_partition.get(pid, 0),
                "bulk_profile": {
                    "bulk_grain": bulk.get("bulk_grain"),
                    "time_span": bulk.get("time_span"),
                    "geographies": bulk.get("geographies") or [],
                    "latent_capabilities": bulk.get("latent_capabilities") or [],
                    "registry_surface": bulk.get("registry_surface"),
                    "surface_vs_bulk": bulk.get("surface_vs_bulk"),
                    "synthetic_paths": bulk.get("synthetic_paths") or [],
                },
                "professor_visible": part.get("professor_visible", True),
            }
        )
    return rows


def _human_bytes(n: int) -> str:
    if n >= 1024**3:
        return f"{n / 1024**3:.2f} GiB"
    if n >= 1024**2:
        return f"{n / 1024**2:.1f} MiB"
    if n >= 1024:
        return f"{n / 1024:.0f} KiB"
    return f"{n} B"


def _effective_rank(paths: list[dict[str, Any]]) -> int:
    rank = 0
    for p in paths:
        r = int(p.get("rank") or 0)
        status = str(p.get("status") or "")
        if status in ("materialized", "built", "live", "bulk_metadata", "catalogue") and r > rank:
            rank = r
        elif status in ("thin", "proxy", "recipe", "bulk_latent", "on_demand", "per_doi") and r > rank:
            rank = max(rank, r - 1)
    return rank


def build_proxy_coverage(proxies_doc: dict[str, Any], synthesis_doc: dict[str, Any]) -> list[dict[str, Any]]:
    synth_by_id = {str(s["id"]): s for s in synthesis_doc.get("profiles") or [] if s.get("id")}
    rows: list[dict[str, Any]] = []
    for block in proxies_doc.get("capability_proxies") or []:
        target = block.get("target") or {}
        paths = list(block.get("paths") or [])
        enriched_paths = []
        for p in paths:
            ep = dict(p)
            rid = str(p.get("recipe_id") or "")
            if rid and rid in synth_by_id:
                ep["recipe_title"] = synth_by_id[rid].get("title")
                ep["recipe_status"] = synth_by_id[rid].get("type")
            enriched_paths.append(ep)
        rows.append(
            {
                "id": block.get("id"),
                "target_capability": target.get("capability"),
                "target_geography": target.get("geography"),
                "paths": enriched_paths,
                "effective_rank": _effective_rank(enriched_paths),
                "has_materialized_path": any(
                    str(p.get("status")) in ("materialized", "built", "live", "bulk_metadata", "catalogue")
                    for p in paths
                ),
                "has_latent_path": any(
                    str(p.get("status")) in ("not_wired", "bulk_latent", "recipe", "on_demand", "per_doi")
                    for p in paths
                ),
            }
        )
    return rows


def build_dataset_coverage_audit(repo_root: Path) -> dict[str, Any]:
    root = _repo(repo_root)
    proxies_doc = load_coverage_proxies(root)
    synthesis_doc = _load_json(str(root), SYNTHESIS_REL)

    dataset_profiles = profile_instant_datasets(root, proxies_doc)
    collection_profiles = profile_collections(root, proxies_doc, dataset_profiles)
    proxy_coverage = build_proxy_coverage(proxies_doc, synthesis_doc)

    instant_n = sum(1 for d in dataset_profiles if d.get("analysis_readiness") == "instant")
    probed_n = sum(1 for d in dataset_profiles if (d.get("disk_probe") or {}).get("row_count") or (d.get("disk_probe") or {}).get("row_count_sampled"))
    materialized_instant = sum(1 for d in dataset_profiles if d.get("materialized") is True)

    # Collections where bulk >> registry surface
    bulk_rich = [
        c["partition_id"]
        for c in collection_profiles
        if (c.get("local_bytes") or 0) > 500_000_000 and (c.get("instant_card_count") or 0) <= 3
    ]

    return {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "proxies_version": proxies_doc.get("version"),
        "principle": proxies_doc.get("principle"),
        "summary": {
            "registry_datasets_profiled": len(dataset_profiles),
            "instant_datasets": instant_n,
            "materialized_instant": materialized_instant,
            "disk_probed": probed_n,
            "collection_partitions": len(collection_profiles),
            "bulk_rich_thin_surface": bulk_rich,
            "proxy_blocks": len(proxy_coverage),
            "synthesis_profiles": len(synthesis_doc.get("profiles") or []),
        },
        "dataset_profiles": dataset_profiles,
        "collection_profiles": collection_profiles,
        "proxy_coverage": proxy_coverage,
        "synthesis_profiles": [
            {
                "id": s.get("id"),
                "title": s.get("title"),
                "type": s.get("type"),
                "status": "built",
                "sources": [x.get("registry_dataset_id") or x.get("id") for x in s.get("sources") or []],
                "join_keys": s.get("join_keys") or [],
                "assumptions": s.get("assumptions") or [],
            }
            for s in synthesis_doc.get("profiles") or []
        ],
        "documentation": {
            "proxies_config": "drive/config/databank_coverage_proxies.json",
            "synthesis_profiles": "config/synthesis_profiles.json",
            "regenerate": "python3 scripts/databank_dataset_coverage.py --json",
        },
    }
