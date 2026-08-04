#!/usr/bin/env python3
"""Sync registry materialization truth — promote instant when bytes exist; demote when not.

Front-door copy: probe helpers used by consolidated_state live=1 (no sharpe_kernel import).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROBE_BACKENDS = frozenset(
    {
        "local_parquet_panel",
        "local_csv_file",
        "local_json_file",
        "local_json_glob",
        "local_file",
        "local_gdelt_panel_csv",
        "local_gdelt_high_priority_csv",
    }
)


def _stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_repo_root() -> Path:
    """Resolve the checkout root in both front-door and drive script layouts."""
    candidates = (Path.cwd().resolve(), *Path(__file__).resolve().parents)
    for candidate in candidates:
        primary = candidate / "config/research_query_registry.json"
        drive_registry = candidate / "drive/config/research_query_registry.json"
        if (primary.is_file() or drive_registry.is_file()) and (
            (candidate / "drive").is_dir()
            or (candidate / "scripts/research_query_engine").is_dir()
        ):
            return candidate
    raise FileNotFoundError("could not locate repo root containing a research query registry")


def _registry_path(repo_root: Path) -> Path:
    primary = repo_root / "config/research_query_registry.json"
    if primary.is_file():
        return primary
    return repo_root / "drive/config/research_query_registry.json"


def refresh_procurement_catalog(repo_root: Path) -> dict[str, Any]:
    """Rebuild the deterministic collection/procurement search index."""
    from scripts.research_data_mcp.collection_index import build_index

    return build_index(Path(repo_root).resolve())


def _has_bytes(path: Path, *, max_entries: int = 2000) -> bool:
    """Whether a glob match represents real materialized data.

    Many collections are written as timestamped run directories, so the pattern
    ``data_lake/entity_mapping/asia/*`` matches directories rather than files.
    Counting only ``is_file()`` scored those datasets as unmaterialized while
    their bytes sat one level down -- reporting "not held" for data the desk
    does hold, which is the failure this probe exists to prevent.

    The walk stops at the first non-empty file, and is bounded so a pathological
    tree cannot stall a registry sync.
    """
    try:
        if path.is_file():
            return path.stat().st_size > 0
        if not path.is_dir():
            return False
        for index, child in enumerate(path.rglob("*")):
            if index >= max_entries:
                break
            try:
                if child.is_file() and child.stat().st_size > 0:
                    return True
            except OSError:
                continue
    except OSError:
        return False
    return False


def _prove_smoke(repo_root: Path, ds: dict[str, Any]) -> dict[str, Any] | None:
    """Bounded read proving the dataset actually parses and returns rows.

    Reuses the promotion path's prover rather than inventing a second notion of
    proof, so "verified" means the same thing however a dataset arrived.
    Returns None when the backend has no smoke path, leaving the row at its
    honest query_ready_declared state rather than asserting a proof that was
    never obtained.
    """
    try:
        from scripts.yzu_cluster.acquisitions import prove_query_smoke
    except ImportError:
        return None
    try:
        smoke = prove_query_smoke(Path(repo_root), dict(ds), limit=3)
    except Exception as exc:  # noqa: BLE001 - a failed proof must not fail the sync
        return {"ok": False, "error": str(exc)[:200]}
    if isinstance(smoke, dict) and str(smoke.get("error") or "").startswith("unsupported smoke backend"):
        return None
    return smoke if isinstance(smoke, dict) else None


def _probe_dataset(engine, ds: dict[str, Any]) -> dict[str, Any]:
    did = str(ds.get("dataset_id") or "")
    backend = str(ds.get("backend") or "")
    root = Path(getattr(engine, "repo_root", None) or ".")
    out: dict[str, Any] = {"dataset_id": did, "backend": backend, "query_ready": False}
    if backend not in PROBE_BACKENDS:
        out["skipped"] = "backend_not_probed"
        return out
    try:
        if backend == "local_parquet_panel":
            path, run_id = engine._resolve_panel_path(ds, {})
            try:
                resolved = str(path.relative_to(root))
            except ValueError:
                resolved = str(path)
            out.update(
                {
                    "query_ready": path.is_file() and path.stat().st_size > 0,
                    "resolved_path": resolved,
                    "run_id": run_id,
                }
            )
            return out
        if backend in {"local_gdelt_panel_csv", "local_gdelt_high_priority_csv"}:
            gdelt_root = engine._resolve(ds["local_root"])
            month_dirs = list(engine._iter_month_dirs(gdelt_root) or [])
            fname = (
                "daily_country_shock_panel.csv"
                if backend == "local_gdelt_panel_csv"
                else "sample_high_priority.csv"
            )
            hits = sum(1 for d in month_dirs if (d / fname).is_file())
            out.update(
                {
                    "query_ready": hits > 0,
                    "gdelt_month_hits": hits,
                    "resolved_root": str(gdelt_root),
                }
            )
            return out
        if backend == "local_json_file":
            path = engine._resolve(ds.get("local_path") or ds.get("local_file") or "")
            out.update({"query_ready": path.is_file(), "resolved_path": str(path)})
            return out
        if backend == "local_json_glob":
            import glob as globmod

            pattern = str(ds.get("local_path") or ds.get("local_glob") or "").strip()
            if not pattern:
                out["error"] = "missing local_path glob pattern"
                return out
            matches = [Path(p) for p in globmod.glob(str(engine._resolve(pattern)))]
            usable = [p for p in matches if _has_bytes(p)]
            out.update(
                {
                    "query_ready": len(usable) > 0,
                    "matched": len(matches),
                    "usable_files": len(usable),
                    "pattern": pattern,
                }
            )
            return out
        if backend == "local_csv_file":
            path = engine._resolve(ds.get("local_path") or "")
            out.update({"query_ready": path.is_file(), "resolved_path": str(path)})
            return out
        if backend == "local_file":
            path = engine._resolve(ds.get("local_path") or "")
            out.update({"query_ready": path.exists(), "resolved_path": str(path)})
            return out
    except Exception as exc:
        out["error"] = str(exc)[:200]
    return out


def sync_registry(*, dry_run: bool = False, repo_root: Path | None = None) -> dict[str, Any]:
    from scripts.research_query_engine.engine import ResearchQueryEngine

    root = Path(repo_root).resolve() if repo_root else _default_repo_root()
    registry = _registry_path(root)
    doc = json.loads(registry.read_text(encoding="utf-8"))
    engine = ResearchQueryEngine(registry, repo_root=root)
    promoted: list[str] = []
    demoted: list[str] = []
    updated_runs: list[str] = []

    for ds in doc.get("datasets") or []:
        did = str(ds.get("dataset_id") or "")
        backend = str(ds.get("backend") or "")

        if backend == "local_parquet_panel" and did.startswith("ticker_week"):
            panel_root = root / str(ds.get("local_root") or "")
            fname = str(ds.get("local_file") or "")
            if panel_root.is_dir() and fname:
                for run_dir in sorted(
                    [p for p in panel_root.iterdir() if p.is_dir() and not p.name.startswith(".")],
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                ):
                    if (run_dir / fname).is_file():
                        if str(ds.get("default_run_id") or "") != run_dir.name:
                            ds["default_run_id"] = run_dir.name
                            updated_runs.append(did)
                        break

        probe = _probe_dataset(engine, ds)
        if probe.get("query_ready"):
            # query_ready only says bytes exist at the resolved path. The
            # assessment engine will not treat any dimension as verified without
            # "observed query proof", and nothing previously produced that for
            # rows already in the registry -- prove_query_smoke ran only on the
            # promotion path for newly acquired datasets. Without it every
            # dimension caps at "unverified" and a verdict of "covered" is
            # unreachable no matter how good the coverage metadata is.
            smoke = _prove_smoke(root, ds)
            if smoke is not None:
                probe["query_smoke"] = smoke
                probe["query_verified"] = bool(smoke.get("ok"))
        ds["materialization"] = {
            "query_ready": bool(probe.get("query_ready")),
            "probed_at": _stamp(),
            **{k: v for k, v in probe.items() if k not in {"dataset_id", "backend"}},
        }

        if probe.get("skipped"):
            # Unknown / remote backends are not disk-probed here — leave declared readiness.
            continue

        if not probe.get("query_ready"):
            prior = str(ds.get("analysis_readiness") or "")
            # Soft "usable now" labels are product lies when local bytes are missing.
            if prior in {"instant", "sample_now_full_later"}:
                ds["analysis_readiness"] = "metadata_search"
                ds["promotion_target"] = prior
                demoted.append(did)
            if ds.get("source_access_mode") == "materialized_instant":
                ds["source_access_mode"] = "catalog_reference"
            continue

        if ds.get("analysis_readiness") != "instant":
            ds["analysis_readiness"] = "instant"
            promoted.append(did)
        ds["collection_status"] = "active"
        ds["field_coverage"] = "query-ready"
        ds.pop("known_gap", None)
        ds.pop("promotion_target", None)
        if ds.get("source_access_mode") in {"materialized_bulk", "catalog_reference"}:
            ds["source_access_mode"] = "materialized_instant"

    if not dry_run:
        doc["updated_at"] = _stamp()
        doc["materialization_sync_at"] = doc["updated_at"]
        registry.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            index_stats = refresh_procurement_catalog(root)
        except Exception as exc:
            index_stats = {"error": str(exc)[:200]}
    else:
        index_stats = None

    return {
        "generated_at": _stamp(),
        "dry_run": dry_run,
        "promoted_to_instant": promoted,
        "demoted_to_metadata": demoted,
        "updated_default_run_id": updated_runs,
        "registry_total": len(doc.get("datasets") or []),
        "procurement_index": index_stats,
    }


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    out = sync_registry(dry_run=args.dry_run)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
