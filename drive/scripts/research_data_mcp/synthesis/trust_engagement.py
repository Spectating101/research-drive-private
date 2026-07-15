"""Full stablecoin trust ↔ engagement synthesis — multi-source panel cluster."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stablecoin_skynet.research_dataset import (
    DEFAULT_COMMUNITY_DIR,
    DEFAULT_SCRAPES_ROOT,
    DEFAULT_SKYNET_HARVEST,
    publish_research_dataset,
)
from stablecoin_skynet.gdelt_panel import DEFAULT_OVERLAY_ROOT


def _resolve(repo_root: Path, rel: str, default: Path) -> Path:
    if not rel:
        return default
    p = Path(rel)
    return p if p.is_absolute() else repo_root / p


def _read_coverage(package_root: Path) -> list[dict[str, str]]:
    path = package_root / "validation" / "coverage_by_source.csv"
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _cluster_summary(coverage: list[dict[str, str]]) -> dict[str, Any]:
    if not coverage:
        return {}
    rows = [r for r in coverage if r.get("entity_id")]
    src_cols = [
        "has_skynet_governance",
        "has_skynet_score",
        "has_defillama_map",
        "has_peg_weekly",
        "has_supply_weekly",
        "has_wikipedia",
        "has_gdelt_hits",
        "has_incidents",
    ]

    def _count(col: str) -> int:
        return sum(1 for r in rows if str(r.get(col, "")).strip() in {"1", "True", "true"})

    multi = sum(1 for r in rows if int(str(r.get("sources_present") or "0") or 0) >= 5)
    return {
        "entities": len(rows),
        "entities_with_5plus_sources": multi,
        "source_coverage": {col.replace("has_", ""): _count(col) for col in src_cols},
        "top_multi_source": sorted(
            rows,
            key=lambda r: int(str(r.get("sources_present") or "0") or 0),
            reverse=True,
        )[:8],
    }


def _sample_panel_rows(package_root: Path, *, limit: int = 5) -> list[dict[str, Any]]:
    path = package_root / "panels" / "research_panel_weekly.csv"
    if not path.is_file():
        return []
    fields = [
        "entity_id",
        "week",
        "community_growth_index",
        "twitter_followers_wow_pct",
        "holder_wow_pct",
        "code_security_score",
        "skynet_score",
        "gdelt_entity_security_exploit_rows",
        "gdelt_entity_regulation_rows",
        "peg_deviation_mean",
        "supply_growth_wow_pct",
        "wikipedia_pageviews_sum",
        "github_activity_index",
        "incident_count",
    ]
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if not row.get("community_growth_index") and not row.get("code_security_score"):
                if not row.get("gdelt_entity_security_exploit_rows") and not row.get("peg_deviation_mean"):
                    continue
            slim = {k: row.get(k) for k in fields if row.get(k) not in (None, "")}
            if slim:
                out.append(slim)
            if len(out) >= limit:
                break
    return out


def validate_trust_engagement_package(
    repo_root: Path,
    profile: dict[str, Any],
    package_root: Path,
    *,
    preview_limit: int = 8,
) -> dict[str, Any]:
    """Report on an existing trust↔engagement build without rebuilding."""
    manifest_path = package_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    counts = manifest.get("counts") or {}
    coverage = _read_coverage(package_root)
    cluster = _cluster_summary(coverage)
    samples = _sample_panel_rows(package_root, limit=preview_limit)
    rel_out = str(package_root.relative_to(repo_root)) if package_root.is_relative_to(repo_root) else str(package_root)

    summary = {
        "profile_id": profile.get("id"),
        "type": "trust_engagement",
        "mode": "validate_existing",
        "dataset_version": manifest.get("dataset_version"),
        "leaderboard_entities": counts.get("leaderboard_entities"),
        "research_weekly_rows": counts.get("research_weekly_rows"),
        "engagement_weekly_rows": counts.get("engagement_weekly_rows"),
        "with_code_security_score": counts.get("with_code_security_score"),
        "with_skynet_score": counts.get("with_skynet_score"),
        "entities_with_gdelt_hits": counts.get("entities_with_gdelt_hits"),
        "entities_with_github_activity": counts.get("entities_with_github_activity"),
        "defillama_mapped_entities": counts.get("defillama_mapped_entities"),
        "week_range": f"{counts.get('engagement_week_min')} → {counts.get('engagement_week_max')}",
        "sources_clustered": cluster.get("source_coverage"),
        "entities_with_5plus_sources": cluster.get("entities_with_5plus_sources"),
        "unified_both_skynet_etherscan": (manifest.get("unified_manifest") or {}).get("counts", {}).get("both_sources"),
    }

    return {
        "profile_id": profile.get("id"),
        "title": profile.get("title"),
        "type": "trust_engagement",
        "generated_at": manifest.get("generated_at") or datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "cluster": cluster,
        "panel_samples": samples,
        "research_questions": profile.get("research_questions") or [],
        "artifacts": {
            "package_root": rel_out,
            "panel_weekly": f"{rel_out}/panels/research_panel_weekly.csv",
            "panel_latest": f"{rel_out}/panel_latest.csv",
            "entities": f"{rel_out}/entities.csv",
            "coverage_by_source": f"{rel_out}/validation/coverage_by_source.csv",
            "manifest_json": f"{rel_out}/manifest.json",
        },
        "manifest": manifest,
    }


def run_trust_engagement_synthesis(
    repo_root: Path,
    profile: dict[str, Any],
    *,
    refresh_external: bool = False,
    refresh_github: bool = False,
    include_gdelt: bool = True,
    include_external: bool = True,
    include_github: bool = True,
    preview_limit: int = 8,
    validate_existing: bool = False,
) -> dict[str, Any]:
    paths = profile.get("paths") or {}
    existing = repo_root / "data" / "datasets" / "stablecoin_trust_engagement" / "latest"
    if validate_existing and (existing / "manifest.json").is_file():
        return validate_trust_engagement_package(
            repo_root, profile, existing.resolve(), preview_limit=preview_limit
        )

    skynet_harvest = _resolve(repo_root, str(paths.get("skynet_harvest", "")), DEFAULT_SKYNET_HARVEST)
    scrapes_root = _resolve(repo_root, str(paths.get("scrapes_root", "")), DEFAULT_SCRAPES_ROOT)
    community_dir = _resolve(repo_root, str(paths.get("community_dir", "")), DEFAULT_COMMUNITY_DIR)
    gdelt_overlay = _resolve(repo_root, str(paths.get("gdelt_overlay", "")), DEFAULT_OVERLAY_ROOT)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    subdir = profile.get("output_subdir") or profile.get("id") or "stablecoin_trust_engagement"
    out_dir = repo_root / "data_lake" / "synthesis" / subdir / stamp

    manifest = publish_research_dataset(
        out_dir,
        skynet_harvest_dir=skynet_harvest,
        scrapes_root=scrapes_root,
        community_dir=community_dir,
        gdelt_overlay_root=gdelt_overlay,
        include_gdelt=include_gdelt,
        include_external=include_external,
        refresh_external=refresh_external,
        include_github=include_github,
        refresh_github=refresh_github,
    )
    counts = manifest.get("counts") or {}
    coverage = _read_coverage(out_dir)
    cluster = _cluster_summary(coverage)
    samples = _sample_panel_rows(out_dir, limit=preview_limit)

    latest_pointer = repo_root / "data_lake" / "synthesis" / subdir / "latest.json"
    latest_pointer.parent.mkdir(parents=True, exist_ok=True)
    rel_out = str(out_dir.relative_to(repo_root)) if out_dir.is_relative_to(repo_root) else str(out_dir)
    latest_pointer.write_text(
        json.dumps(
            {
                "profile_id": profile.get("id"),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "run_dir": rel_out,
                "counts": counts,
                "cluster": cluster,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # Symlink desk package latest for professor handoff
    desk_latest = repo_root / "data" / "datasets" / "stablecoin_trust_engagement" / "latest"
    try:
        if desk_latest.is_symlink() or desk_latest.is_file():
            desk_latest.unlink()
        desk_latest.symlink_to(out_dir.resolve(), target_is_directory=True)
    except OSError:
        pass

    summary = {
        "profile_id": profile.get("id"),
        "type": "trust_engagement",
        "dataset_version": manifest.get("dataset_version"),
        "leaderboard_entities": counts.get("leaderboard_entities"),
        "research_weekly_rows": counts.get("research_weekly_rows"),
        "engagement_weekly_rows": counts.get("engagement_weekly_rows"),
        "with_code_security_score": counts.get("with_code_security_score"),
        "with_skynet_score": counts.get("with_skynet_score"),
        "entities_with_gdelt_hits": counts.get("entities_with_gdelt_hits"),
        "entities_with_github_activity": counts.get("entities_with_github_activity"),
        "defillama_mapped_entities": counts.get("defillama_mapped_entities"),
        "week_range": f"{counts.get('engagement_week_min')} → {counts.get('engagement_week_max')}",
        "sources_clustered": cluster.get("source_coverage"),
        "entities_with_5plus_sources": cluster.get("entities_with_5plus_sources"),
        "unified_both_skynet_etherscan": (manifest.get("unified_manifest") or {}).get("counts", {}).get("both_sources"),
    }

    return {
        "profile_id": profile.get("id"),
        "title": profile.get("title"),
        "type": "trust_engagement",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "cluster": cluster,
        "panel_samples": samples,
        "research_questions": profile.get("research_questions") or [],
        "artifacts": {
            "package_root": rel_out,
            "panel_weekly": f"{rel_out}/panels/research_panel_weekly.csv",
            "panel_latest": f"{rel_out}/panel_latest.csv",
            "entities": f"{rel_out}/entities.csv",
            "coverage_by_source": f"{rel_out}/validation/coverage_by_source.csv",
            "manifest_json": f"{rel_out}/manifest.json",
            "latest_pointer": str(latest_pointer.relative_to(repo_root))
            if latest_pointer.is_relative_to(repo_root)
            else str(latest_pointer),
        },
        "manifest": manifest,
    }
