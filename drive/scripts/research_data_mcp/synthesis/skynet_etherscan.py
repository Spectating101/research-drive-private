"""Skynet + Etherscan stablecoin synthesis (entity-level join)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stablecoin_skynet.unified_dataset import (
    build_unified_dataset,
    write_unified_csv,
)


def _resolve_path(repo_root: Path, rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else (repo_root / p)


def _gap_rows(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("in_skynet_leaderboard"):
            continue
        if row.get("in_etherscan_stablecoin_list"):
            continue
        addr = str(row.get("primary_ethereum_address") or "").strip()
        slug = row.get("skynet_slug") or row.get("entity_id")
        item: dict[str, Any] = {
            "entity_id": row.get("entity_id"),
            "skynet_slug": slug,
            "canonical_name": row.get("canonical_name"),
            "primary_ethereum_address": addr or None,
            "missing_source": "etherscan",
            "coverage_score": row.get("coverage_score"),
            "skynet_score": row.get("skynet_score"),
            "recommended_action": "queue_etherscan_token_scrape" if addr else "resolve_ethereum_address",
        }
        if addr:
            item["procure_url"] = f"https://etherscan.io/token/{addr}"
        gaps.append(item)
        if len(gaps) >= limit:
            break
    return gaps


def _entity_preview(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    for row in rows:
        if not (row.get("in_skynet_leaderboard") and row.get("in_etherscan_stablecoin_list")):
            continue
        preview.append(
            {
                "entity_id": row.get("entity_id"),
                "canonical_name": row.get("canonical_name"),
                "primary_ethereum_address": row.get("primary_ethereum_address"),
                "coverage_score": row.get("coverage_score"),
                "skynet_score": row.get("skynet_score"),
                "etherscan_holders": row.get("etherscan_holders"),
                "etherscan_onchain_mcap_usd": row.get("etherscan_onchain_mcap_usd"),
                "join_method": row.get("join_method"),
                "sources": row.get("sources"),
            }
        )
        if len(preview) >= limit:
            break
    return preview


def _research_insights(summary: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    linked = [r for r in rows if r.get("in_skynet_leaderboard") and r.get("in_etherscan_stablecoin_list")]
    insights: list[dict[str, Any]] = []

    high_sec_low_adopt = []
    for r in linked:
        score = r.get("skynet_score")
        holders = r.get("etherscan_holders")
        if score is not None and holders is not None and float(score) >= 80 and int(holders) < 5000:
            high_sec_low_adopt.append(r)
    if high_sec_low_adopt:
        insights.append(
            {
                "kind": "security_vs_adoption",
                "count": len(high_sec_low_adopt),
                "label": "High Skynet score (≥80) but <5k Etherscan holders",
                "sample_entities": [x.get("entity_id") for x in high_sec_low_adopt[:5]],
            }
        )

    skynet_only = summary.get("skynet_only_count") or 0
    if skynet_only:
        insights.append(
            {
                "kind": "procurement_gap",
                "count": skynet_only,
                "label": "Skynet leaderboard coins without Etherscan scrape match",
                "recommended_action": "run submit_skynet_etherscan_backfill.py or yzu_submit_job scrape",
            }
        )

    return insights


def run_skynet_etherscan_synthesis(
    repo_root: Path,
    profile: dict[str, Any],
    *,
    out_dir: Path | None = None,
    preview_limit: int = 50,
    gap_limit: int = 100,
) -> dict[str, Any]:
    paths = profile.get("paths") or {}
    skynet_harvest = _resolve_path(repo_root, str(paths.get("skynet_harvest", "")))
    scrapes_root = _resolve_path(repo_root, str(paths.get("scrapes_root", "")))
    community_dir = _resolve_path(repo_root, str(paths.get("community_dir", "")))

    rows, manifest = build_unified_dataset(
        skynet_harvest_dir=skynet_harvest,
        scrapes_root=scrapes_root,
        community_dir=community_dir,
    )
    counts = manifest.get("counts") or {}

    summary = {
        "profile_id": profile.get("id"),
        "type": "skynet_etherscan",
        "join_keys": profile.get("join_keys") or ["primary_ethereum_address"],
        "left_source": "skynet",
        "right_source": "etherscan",
        "left_count": counts.get("skynet_projects", 0),
        "right_count": counts.get("etherscan_tokens_indexed", 0),
        "both_count": counts.get("both_sources", 0),
        "left_only_count": counts.get("skynet_only", 0),
        "right_only_count": counts.get("etherscan_only", 0),
        "entity_count": counts.get("unified_rows", len(rows)),
        "with_skynet_score": counts.get("with_skynet_score", 0),
        "with_etherscan_holders": counts.get("with_etherscan_holders", 0),
        "skynet_only_count": counts.get("skynet_only", 0),
        "etherscan_only_count": counts.get("etherscan_only", 0),
        "overlap_pct": round(
            100 * (counts.get("both_sources") or 0) / max(counts.get("skynet_projects") or 1, 1),
            1,
        ),
        "join_methods": manifest.get("join_methods") or {},
    }

    subdir = profile.get("output_subdir") or profile.get("id") or "skynet_etherscan"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = out_dir or (repo_root / "data_lake" / "synthesis" / subdir / stamp)
    base.mkdir(parents=True, exist_ok=True)

    panel_path = base / "stablecoin_unified_panel.csv"
    write_unified_csv(panel_path, rows)
    manifest_path = base / "manifest.json"
    manifest["synthesis"] = summary
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    gaps = _gap_rows(rows, limit=gap_limit)
    gaps_path = base / "gaps.json"
    gaps_path.write_text(json.dumps({"gaps": gaps, "total": len(gaps)}, indent=2) + "\n", encoding="utf-8")

    preview = _entity_preview(rows, limit=preview_limit)
    insights = _research_insights(summary, rows)

    latest_pointer = repo_root / "data_lake" / "synthesis" / subdir / "latest.json"
    latest_pointer.parent.mkdir(parents=True, exist_ok=True)
    latest_pointer.write_text(
        json.dumps(
            {
                "profile_id": profile.get("id"),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "run_dir": str(base.relative_to(repo_root)) if base.is_relative_to(repo_root) else str(base),
                "summary": summary,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "profile_id": profile.get("id"),
        "title": profile.get("title"),
        "type": "skynet_etherscan",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "entities": preview,
        "gaps": gaps,
        "insights": insights,
        "research_questions": profile.get("research_questions") or [],
        "artifacts": {
            "panel_csv": str(panel_path.relative_to(repo_root)) if panel_path.is_relative_to(repo_root) else str(panel_path),
            "manifest_json": str(manifest_path.relative_to(repo_root)) if manifest_path.is_relative_to(repo_root) else str(manifest_path),
            "gaps_json": str(gaps_path.relative_to(repo_root)) if gaps_path.is_relative_to(repo_root) else str(gaps_path),
            "latest_pointer": str(latest_pointer.relative_to(repo_root)) if latest_pointer.is_relative_to(repo_root) else str(latest_pointer),
        },
        "inputs": {
            "skynet_harvest": str(skynet_harvest),
            "scrapes_root": str(scrapes_root),
            "skynet_harvest_exists": skynet_harvest.is_dir(),
            "scrapes_root_exists": scrapes_root.is_dir(),
        },
    }
