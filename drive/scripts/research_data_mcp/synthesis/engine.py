"""Synthesis orchestration — run profiles and serve latest artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from scripts.research_data_mcp.synthesis.profiles import get_profile, list_profile_summaries


def list_synthesis_profiles(repo_root: Path) -> dict[str, Any]:
    profiles = list_profile_summaries(repo_root)
    latest: dict[str, Any] = {}
    for row in profiles:
        pid = row.get("id")
        if not pid:
            continue
        hit = get_latest_synthesis(repo_root, str(pid))
        if hit:
            latest[str(pid)] = {
                "generated_at": hit.get("generated_at"),
                "summary": hit.get("summary"),
            }
    return {"profiles": profiles, "latest": latest, "count": len(profiles)}


def get_latest_synthesis(repo_root: Path, profile_id: str) -> dict[str, Any] | None:
    profile = get_profile(repo_root, profile_id)
    if not profile:
        return None
    subdir = profile.get("output_subdir") or profile_id
    pointer = repo_root / "data_lake" / "synthesis" / subdir / "latest.json"
    if not pointer.is_file():
        return None
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    run_dir = data.get("run_dir")
    manifest_path = repo_root / str(run_dir) / "manifest.json" if run_dir else None
    out = dict(data)
    if manifest_path and manifest_path.is_file():
        try:
            out["manifest"] = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    gaps_path = repo_root / str(run_dir) / "gaps.json" if run_dir else None
    if gaps_path and gaps_path.is_file():
        try:
            gaps_payload = json.loads(gaps_path.read_text(encoding="utf-8"))
            out["gap_count"] = gaps_payload.get("total")
        except json.JSONDecodeError:
            pass
    return out



def _run_registry_dataset(repo_root: Path, profile: dict[str, Any]) -> dict[str, Any]:
    """Hydrate (if needed) and summarize one registered / held tabular dataset."""
    import pandas as pd
    from scripts.research_data_mcp.registry_hydrate import ensure_dataset_hydrated

    dataset_id = str(profile.get("registry_dataset_id") or "").strip()
    fallback = str(profile.get("fallback_local_path") or "").strip()
    hydrate: dict[str, Any] = {}
    file_path: Path | None = None
    if dataset_id:
        hydrate = ensure_dataset_hydrated(repo_root, dataset_id)
        reg = json.loads((repo_root / "config/research_query_registry.json").read_text(encoding="utf-8"))
        row = next((r for r in reg.get("datasets") or [] if r.get("dataset_id") == dataset_id), None) or {}
        local = str(row.get("local_path") or "").strip()
        if local and "*" not in local:
            candidate = repo_root / local
            if candidate.is_file():
                file_path = candidate
            elif candidate.is_dir():
                hits = sorted(
                    p
                    for p in candidate.rglob("*")
                    if p.is_file() and (p.suffix.lower() in {".csv", ".json", ".parquet"} or p.name in {"STOCK_DAY_ALL", "STOCK_DAY_AVG_ALL", "company_tickers.json"})
                )
                file_path = hits[0] if hits else None
    if file_path is None and fallback:
        candidate = repo_root / fallback
        if candidate.is_file():
            file_path = candidate
    if file_path is None:
        raise ValueError(
            f"registry_dataset profile {profile.get('id')!r} has no local bytes"
            + (f" (hydrate={hydrate.get('error') or hydrate.get('reason')})" if hydrate else "")
        )

    suffix = file_path.suffix.lower()
    if suffix == ".parquet":
        frame = pd.read_parquet(file_path)
    elif suffix == ".csv":
        frame = pd.read_csv(file_path)
    else:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            frame = pd.DataFrame(raw)
        elif isinstance(raw, dict) and all(isinstance(v, dict) for v in raw.values()):
            frame = pd.DataFrame(list(raw.values()))
        else:
            frame = pd.json_normalize(raw)

    rel = str(file_path.relative_to(repo_root)) if file_path.is_relative_to(repo_root) else str(file_path)
    summary = {
        "profile_id": profile.get("id"),
        "type": "registry_dataset",
        "registry_dataset_id": dataset_id or None,
        "path": rel,
        "rows": int(len(frame)),
        "columns": list(map(str, frame.columns)),
        "hydrate": {k: hydrate.get(k) for k in ("ok", "skipped", "reason", "error", "dataset_id") if k in hydrate},
    }
    preview_cols = list(frame.columns)[:8]
    preview = frame[preview_cols].head(int(profile.get("preview_limit") or 5)).fillna("").astype(str).to_dict("records")
    return {
        "profile_id": profile.get("id"),
        "title": profile.get("title"),
        "type": "registry_dataset",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "preview": preview,
        "research_questions": profile.get("research_questions") or [],
        "artifacts": {"input_path": rel},
        "note": "Held/registry snapshot — hydrate-first; no invented joins.",
    }


def _run_published_panel(repo_root: Path, profile: dict[str, Any]) -> dict[str, Any]:
    paths = profile.get("paths") or {}
    package_root = repo_root / str(paths.get("package_root", ""))
    manifest_path = package_root / "manifest.json"
    entities_path = package_root / "entities.csv"
    summary: dict[str, Any] = {
        "profile_id": profile.get("id"),
        "type": "published_panel",
        "package_root": str(package_root.relative_to(repo_root)) if package_root.is_relative_to(repo_root) else str(package_root),
        "package_exists": package_root.is_dir(),
        "manifest_exists": manifest_path.is_file(),
        "entities_exists": entities_path.is_file(),
    }
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        summary["entity_count"] = (manifest.get("counts") or {}).get("entities")
        summary["panel_weekly_rows"] = (manifest.get("counts") or {}).get("panel_weekly_rows")
    return {
        "profile_id": profile.get("id"),
        "title": profile.get("title"),
        "type": "published_panel",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "research_questions": profile.get("research_questions") or [],
        "artifacts": {
            "package_root": summary["package_root"],
            "manifest_json": str((package_root / "manifest.json").relative_to(repo_root))
            if manifest_path.is_relative_to(repo_root)
            else str(manifest_path),
        },
        "note": "Curated research package — run build_stablecoin_research_dataset.py to refresh.",
    }


def run_synthesis(
    repo_root: Path,
    profile_id: str,
    *,
    preview_limit: int = 50,
    gap_limit: int = 100,
) -> dict[str, Any]:
    profile = get_profile(repo_root, profile_id)
    if not profile:
        raise ValueError(f"unknown synthesis profile: {profile_id}")

    ptype = profile.get("type") or ""
    if ptype == "skynet_etherscan":
        from scripts.research_data_mcp.synthesis.skynet_etherscan import (
            run_skynet_etherscan_synthesis,
        )

        return run_skynet_etherscan_synthesis(
            repo_root,
            profile,
            preview_limit=preview_limit,
            gap_limit=gap_limit,
        )
    if ptype == "trust_engagement":
        from scripts.research_data_mcp.synthesis.trust_engagement import (
            run_trust_engagement_synthesis,
        )

        opts = profile.get("options") or {}
        return run_trust_engagement_synthesis(
            repo_root,
            profile,
            refresh_external=bool(opts.get("refresh_external")),
            refresh_github=bool(opts.get("refresh_github")),
            include_gdelt=opts.get("include_gdelt", True),
            include_external=opts.get("include_external", True),
            include_github=opts.get("include_github", True),
            preview_limit=preview_limit,
            validate_existing=bool(opts.get("validate_existing")),
        )
    if ptype == "jkse_pit_idn":
        from scripts.research_data_mcp.synthesis.jkse_pit_idn import run_jkse_pit_idn_synthesis

        return run_jkse_pit_idn_synthesis(repo_root, profile, preview_limit=preview_limit)
    if ptype == "published_panel":
        return _run_published_panel(repo_root, profile)
    if ptype == "registry_dataset":
        return _run_registry_dataset(repo_root, profile)
    raise ValueError(f"unsupported synthesis profile type: {ptype}")


def run_synthesis_pair(
    repo_root: Path,
    left_dataset_id: str,
    right_dataset_id: str,
    *,
    describe_fn: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    from scripts.research_data_mcp.synthesis.registry_pair import run_registry_pair

    return run_registry_pair(
        repo_root,
        left_dataset_id,
        right_dataset_id,
        describe_fn=describe_fn,
    )
