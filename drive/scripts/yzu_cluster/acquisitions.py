#!/usr/bin/env python3
"""Stage, validate, and promote downloaded procurement artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def remote_collect_script(repo_root: Path) -> Path:
    """Resolve remote_collect.py for both monorepo roots and drive/ roots.

    Desk processes use a monorepo root (kernel/ + drive/ siblings), so the
    collector lives at drive/scripts/cluster_agent/. Worker-control and some
    CLIs pass --repo-root .../drive, where scripts/cluster_agent/ is correct.
    """
    candidates = (
        repo_root / "drive/scripts/cluster_agent/remote_collect.py",
        repo_root / "scripts/cluster_agent/remote_collect.py",
    )
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def repo_relpath(path: Path, repo_root: Path) -> str:
    """Return a path relative to repo_root, tolerating runtime bind symlinks.

    Front-door checkouts symlink data_lake/procured and data_lake/yzu_cluster into
    YZU_RUNTIME_DRIVE_ROOT. Path.resolve() jumps outside the checkout, so a naive
    relative_to(repo_root) raises during materialize/promote.
    """
    path = Path(path)
    repo_root = Path(repo_root)
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        pass
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        pass
    for logical in ("data_lake/procured", "data_lake/yzu_cluster", "data_lake"):
        bind = repo_root / logical
        if not (bind.exists() or bind.is_symlink()):
            continue
        try:
            rel = resolved.relative_to(bind.resolve())
            return str(Path(logical) / rel)
        except ValueError:
            continue
    return str(resolved)


def acquisitions_root(repo_root: Path, cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or {}
    storage = cfg.get("storage") or {}
    rel = str(storage.get("acquisitions_root") or "data_lake/yzu_cluster/acquisitions")
    path = (repo_root / rel).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def procured_root(repo_root: Path, cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or {}
    storage = cfg.get("storage") or {}
    rel = str(storage.get("procured_root") or "data_lake/procured")
    path = (repo_root / rel).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def dataset_id_for_plan(plan: dict[str, Any], job_id: str) -> str:
    cid = str(plan.get("connector_id") or plan.get("dataset_id") or "").strip()
    if cid.startswith("src_"):
        return f"procured_{cid}"
    if cid:
        return cid
    slug = hashlib.sha256(str(plan.get("url") or job_id).encode()).hexdigest()[:10]
    return f"procured_{slug}"


def canonical_dir(repo_root: Path, plan: dict[str, Any], job_id: str, cfg: dict[str, Any] | None = None) -> Path:
    dest = plan.get("destination")
    if dest:
        return (repo_root / str(dest)).resolve()
    ds_id = dataset_id_for_plan(plan, job_id)
    return procured_root(repo_root, cfg) / ds_id


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unzip_artifact(zip_path: Path, raw_dir: Path) -> list[dict[str, Any]]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    with zipfile.ZipFile(zip_path, "r") as archive:
        for name in archive.namelist():
            if not name.startswith("raw/") or name.endswith("/"):
                continue
            target = raw_dir / Path(name).name
            with archive.open(name) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            if target.is_file() and target.stat().st_size > 0:
                files.append(
                    {
                        "name": target.name,
                        "path": str(target),
                        "bytes": target.stat().st_size,
                        "sha256": _sha256_file(target),
                    }
                )
    return files


def collect_local_manifest(
    repo_root: Path,
    job_id: str,
    plan: dict[str, Any],
    *,
    jobs_root: Path | None = None,
) -> dict[str, Any]:
    """Download http_manifest items on the controller (optiplex) when workers unavailable."""
    items = list(plan.get("items") or [])
    if not items:
        raise ValueError("http_manifest has no items to collect")
    jobs_root = jobs_root or (repo_root / "data_lake/yzu_cluster/jobs")
    job_dir = jobs_root / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    manifest = job_dir / f"local_{job_id}.json"
    artifact = job_dir / f"local_{job_id}.zip"
    manifest.write_text(json.dumps({"job_id": job_id, "shard": 0, "items": items}, indent=2), encoding="utf-8")
    script = remote_collect_script(repo_root)
    if not script.is_file():
        raise FileNotFoundError(f"remote collector not found (tried drive/ and scripts/): {script}")
    python = repo_root / ".venv/bin/python"
    if not python.exists():
        python = Path("python3")
    cmd = [
        str(python),
        str(script),
        "--manifest",
        str(manifest),
        "--artifact",
        str(artifact),
        "--workers",
        str(min(int(plan.get("per_node_workers", 2)), 4)),
        "--timeout",
        str(min(int(plan.get("request_timeout", 90)), 300)),
        "--retries",
        str(min(int(plan.get("retries", 3)), 5)),
        "--delay",
        str(max(float(plan.get("delay_seconds", 0.25)), 0.1)),
    ]
    proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, timeout=int(plan.get("timeout_seconds", 7200)), check=False)
    if proc.returncode not in {0, 2}:
        raise RuntimeError(f"local collect failed ({proc.returncode}): {(proc.stderr or proc.stdout)[-800:]}")
    if not artifact.exists():
        raise RuntimeError("local collect produced no artifact zip")
    return {
        "artifacts": [
            {
                "shard": 0,
                "worker": "local",
                "artifact": repo_relpath(artifact, repo_root),
                "bytes": artifact.stat().st_size,
                "worker_exit": proc.returncode,
                "collect_report": proc.stdout.strip()[-500:],
            }
        ],
        "output_dir": repo_relpath(job_dir, repo_root),
        "collect_mode": "local",
    }


def materialize_job(
    repo_root: Path,
    job_id: str,
    plan: dict[str, Any],
    result: dict[str, Any],
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract downloaded files into acquisitions staging and promote to canonical data_lake path."""
    cfg = cfg or {}
    staging = acquisitions_root(repo_root, cfg) / job_id
    raw_dir = staging / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    staged_files: list[dict[str, Any]] = []

    for row in result.get("artifacts") or []:
        rel = str(row.get("artifact") or "")
        if not rel:
            continue
        zip_path = (repo_root / rel).resolve()
        if zip_path.suffix.lower() == ".zip" and zip_path.exists():
            staged_files.extend(unzip_artifact(zip_path, raw_dir))

    # Direct writes (future local paths)
    job_output = result.get("output_dir")
    if job_output:
        candidate_raw = (repo_root / job_output / "raw").resolve()
        if candidate_raw.exists():
            for path in candidate_raw.rglob("*"):
                if path.is_file():
                    target = raw_dir / path.name
                    if not target.exists():
                        shutil.copy2(path, target)
                    staged_files.append(
                        {
                            "name": target.name,
                            "path": str(target),
                            "bytes": target.stat().st_size,
                            "sha256": _sha256_file(target),
                        }
                    )

    staged_files = _dedupe_files(staged_files)
    validation = validate_staging(staging, staged_files, plan)
    canonical = canonical_dir(repo_root, plan, job_id, cfg)
    promoted_files: list[dict[str, Any]] = []
    if validation.get("ok") and staged_files:
        canonical.mkdir(parents=True, exist_ok=True)
        for row in staged_files:
            src = Path(row["path"])
            dst = canonical / src.name
            shutil.copy2(src, dst)
            promoted_files.append(
                {
                    "name": dst.name,
                    "path": repo_relpath(dst, repo_root),
                    "bytes": dst.stat().st_size,
                    "sha256": _sha256_file(dst),
                }
            )

    meta = {
        "job_id": job_id,
        "materialized_at": _now(),
        "plan": {
            "job_type": plan.get("job_type"),
            "connector_id": plan.get("connector_id"),
            "url": plan.get("url"),
            "title": plan.get("title"),
        },
        "staging_dir": repo_relpath(staging, repo_root),
        "canonical_dir": repo_relpath(canonical, repo_root) if canonical.exists() else "",
        "dataset_id": dataset_id_for_plan(plan, job_id),
        "files": promoted_files or staged_files,
        "validation": validation,
        "collect_mode": result.get("collect_mode", "remote"),
    }
    if validation.get("ok") and canonical.exists() and promoted_files:
        manifest_id = f"collection_manifest_{job_id}"
        manifest = {
            "manifest_id": manifest_id,
            "job_id": job_id,
            "output": {"dataset_id": meta["dataset_id"], "canonical_dir": meta["canonical_dir"]},
            "files": promoted_files,
            "validation": validation,
            "plan": meta["plan"],
            "created_at": meta["materialized_at"],
        }
        manifest_path = canonical / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        meta["manifest_id"] = manifest_id
        meta["manifest_path"] = repo_relpath(manifest_path, repo_root)
    (staging / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    out = dict(result)
    out["materialized"] = meta
    out["staging_dir"] = meta["staging_dir"]
    out["canonical_dir"] = meta["canonical_dir"]
    out["dataset_id"] = meta["dataset_id"]
    if meta.get("manifest_id"):
        out["output_manifest_id"] = meta["manifest_id"]
        out["manifest_id"] = meta["manifest_id"]
    return out


def _dedupe_files(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        name = row.get("name") or Path(str(row.get("path", ""))).name
        if name in seen:
            continue
        seen.add(name)
        out.append(row)
    return out


def validate_staging(staging: Path, files: list[dict[str, Any]], plan: dict[str, Any]) -> dict[str, Any]:
    min_bytes = int((plan.get("validation") or {}).get("min_total_bytes", 1))
    min_files = int((plan.get("validation") or {}).get("min_files", 1))
    total_bytes = sum(int(f.get("bytes") or 0) for f in files)
    ok = total_bytes >= min_bytes and len(files) >= min_files
    return {
        "ok": ok,
        "file_count": len(files),
        "total_bytes": total_bytes,
        "min_files": min_files,
        "min_total_bytes": min_bytes,
    }


def registry_spec_from_materialized(
    repo_root: Path,
    job: dict[str, Any],
    materialized: dict[str, Any],
    *,
    campaign_id: str = "",
) -> dict[str, Any] | None:
    plan = job.get("plan") or {}
    dataset_id = str(materialized.get("dataset_id") or dataset_id_for_plan(plan, str(job.get("id", ""))))
    canonical = materialized.get("canonical_dir") or materialized.get("staging_dir")
    if not canonical:
        return None
    files = materialized.get("files") or []
    if not files:
        return None
    if len(files) == 1:
        local_path = str(Path(canonical) / str(files[0].get("name") or "artifact"))
    else:
        local_path = f"{canonical}/*"
    suffix = Path(files[0]["name"]).suffix.lower()
    readiness = "metadata_search"
    if suffix in {".csv", ".tsv"}:
        backend = "local_csv_glob" if "*" in local_path else "local_csv_file"
        if "*" not in local_path:
            readiness = "instant"
    elif suffix in {".json", ".jsonl"}:
        backend = "local_json_glob" if "*" in local_path else "local_json_file"
        if "*" not in local_path and int(files[0].get("bytes") or 0) <= 50_000_000:
            readiness = "instant"
    elif suffix == ".parquet":
        backend = "local_parquet_panel"
        readiness = "instant"
    else:
        backend = "local_json_glob" if "*" in local_path else "local_file"
    title = str(plan.get("title") or dataset_id)
    spec: dict[str, Any] = {
        "dataset_id": dataset_id,
        "name": title[:240],
        "backend": backend,
        "access_shape": "local_file_tree" if "*" in local_path else "local_file",
        "analysis_readiness": readiness,
        "grain": "procured_snapshot",
        "local_path": local_path,
        "description": (
            f"Materialised by synthesis execution job `{job.get('id', '')}`."
            if plan.get("job_type") == "synthesis_execute"
            else f"Procured via http_manifest job `{job.get('id', '')}` from {plan.get('url') or plan.get('connector_id', 'web')}."
        ),
        "capabilities": ["limit", "export_json"],
        "recommended_use": f"Inspect files under {local_path}",
        "domain": plan.get("domain") or "procured",
    }
    if campaign_id:
        spec["lineage"] = {"campaign_id": campaign_id, "alpha_ready": True}
    if plan.get("job_type") == "synthesis_execute":
        # Honest derived mapping: synthesis outputs are not raw vendor cards.
        spec["source_id"] = "derived_synthesis"
        spec["source_system"] = "In-house synthesis thread outputs"
        spec["source_access_mode"] = "derived_internal"
        exec_spec = plan.get("execution_spec") or {}
        upstream = str(exec_spec.get("input_dataset_id") or "").strip()
        lineage = dict(spec.get("lineage") or {})
        if upstream:
            lineage["upstream_dataset_ids"] = [upstream]
        lineage["derived_via"] = "synthesis_execute"
        spec["lineage"] = lineage
    return spec


def enrich_http_manifest_plan(plan: dict[str, Any], procurement: Any, *, domain_packs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Fill empty manifest items from connector probe metadata."""
    if plan.get("job_type") != "http_manifest":
        return plan
    if plan.get("items"):
        return plan
    cid = str(plan.get("connector_id") or "")
    source_url = str(plan.get("url") or "")
    if cid:
        try:
            connector = procurement.store.get(cid)
            spec = connector.get("spec") or {}
            source_url = source_url or str(spec.get("source_url") or "")
            if spec.get("access_mode") == "direct_file":
                plan["items"] = [{"url": spec["source_url"]}]
            else:
                discovered = spec.get("discovered_files") or []
                if discovered:
                    plan["items"] = [{"url": row["url"]} for row in discovered[: int(plan.get("limit", 50))]]
            if not plan.get("url"):
                plan["url"] = spec.get("source_url")
        except KeyError:
            pass
    if not plan.get("items") and domain_packs and source_url:
        from scripts.research_data_mcp.domain_packs import pack_direct_downloads

        plan["items"] = list(pack_direct_downloads(domain_packs, source_url))
    if not plan.get("items") and plan.get("url"):
        plan["items"] = [{"url": str(plan["url"])}]
    plan.setdefault("shards", min(4, max(1, len(plan.get("items") or []))))
    plan.setdefault("launchable", True)
    return plan
