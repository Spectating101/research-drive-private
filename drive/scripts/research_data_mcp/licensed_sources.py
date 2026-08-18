"""Read-only readiness and staging utilities for licensed research sources.

This module deliberately does not log in, download, mutate the registry, or promote
files.  It gives Composer one honest view of the licensed lanes (CRSP, Compustat,
and LSEG) and provides an isolated Compustat export normalizer.  A later, explicitly
approved job may consume the returned plan.

Public adapters and Cursor webfetch use the same handoff contract, but they are not
treated as local holdings.  In particular, the presence of a CRSP archive is not the
same fact as a queryable CRSP table, and an empty Compustat raw directory is not an
entitlement failure.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


_CRSP_EXPECTED = {
    "crsp_us_stock_daily_ciz": "data_lake/crsp/processed/us_stock_daily_ciz.parquet",
    "crsp_us_index_history": "data_lake/crsp/processed/us_index_history.parquet",
    "crsp_compustat_ccm_link": "data_lake/crsp/processed/ccm_link.parquet",
}
_COMPUSTAT_EXPECTED = {
    "compustat_na_fundamentals_annual": "data_lake/compustat/processed/na_fundamentals_annual.parquet",
}
_LICENSED_IDS = frozenset({"crsp_moveit", "capital_iq_compustat", "compustat", "lseg_edp", "lseg_desktop_rescue"})
_PUBLIC_IDS = frozenset({"huggingface", "datacite", "zenodo", "openalex", "webfetch", "cursor_webfetch"})
_TABLE_SUFFIXES = (".csv", ".csv.gz", ".txt", ".xlsx", ".xls", ".zip", ".parquet")


def _config_path(repo_root: Path, name: str) -> Path:
    for path in (repo_root / "config" / name, repo_root / "drive" / "config" / name):
        if path.is_file():
            return path
    return repo_root / "config" / name


def _roots(repo_root: Path) -> list[Path]:
    """Return data roots without requiring a deployment-specific env var."""
    from scripts.research_data_mcp.data_paths import bulk_storage_root
    from scripts.research_data_mcp.synthesis.dataset_paths import data_roots

    roots = list(data_roots(repo_root))
    bulk = bulk_storage_root()
    if bulk and bulk not in roots:
        roots.append(bulk)
    return roots


def _relative(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except (ValueError, OSError):
        return str(path)


def _tree_stats(path: Path, *, cap: int = 5000) -> dict[str, Any]:
    """Count files/bytes without opening licensed payloads."""
    files = 0
    bytes_total = 0
    suffixes: dict[str, int] = {}
    if not path.exists():
        return {"exists": False, "files": 0, "bytes": 0, "suffixes": {}}
    if path.is_file():
        return {
            "exists": True,
            "files": 1,
            "bytes": path.stat().st_size,
            "suffixes": {path.suffix.lower() or "[none]": 1},
        }
    for dirpath, _dirnames, filenames in os.walk(path):
        for name in filenames:
            files += 1
            if files > cap:
                return {"exists": True, "files": files - 1, "bytes": bytes_total, "suffixes": suffixes, "capped": True}
            item = Path(dirpath) / name
            try:
                size = item.stat().st_size
            except OSError:
                size = 0
            bytes_total += size
            suffix = item.suffix.lower() or "[none]"
            suffixes[suffix] = suffixes.get(suffix, 0) + 1
    return {"exists": True, "files": files, "bytes": bytes_total, "suffixes": suffixes}


def _find_relative(repo_root: Path, relative: str) -> list[Path]:
    return [root / relative for root in _roots(repo_root) if (root / relative).exists()]


def _base(source_id: str, *, label: str, capabilities: Iterable[str], roots: list[Path]) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "label": label,
        "capabilities": list(capabilities),
        "selection_authority": "cursor_composer",
        "data_roots": [str(p) for p in roots],
    }


def _crsp_status(repo_root: Path) -> dict[str, Any]:
    roots = _roots(repo_root)
    out = _base(
        "crsp_moveit",
        label="CRSP MOVEit Cloud",
        capabilities=("daily_prices", "index_pit_survivorship", "identifier_links"),
        roots=roots,
    )
    manifests = _find_relative(repo_root, "data_lake/crsp/manifest_latest.json")
    raw = _find_relative(repo_root, "data_lake/crsp/raw")
    extracted = _find_relative(repo_root, "data_lake/crsp/extracted")
    processed = _find_relative(repo_root, "data_lake/crsp/processed")
    expected: dict[str, dict[str, Any]] = {}
    for dataset_id, rel in _CRSP_EXPECTED.items():
        matches = _find_relative(repo_root, rel)
        expected[dataset_id] = {
            "path": rel,
            "queryable": bool(matches and any(p.is_file() and p.stat().st_size > 0 for p in matches)),
            "matches": [str(p) for p in matches],
        }
    raw_stats = _tree_stats(raw[0]) if raw else {"exists": False, "files": 0, "bytes": 0, "suffixes": {}}
    extracted_stats = _tree_stats(extracted[0]) if extracted else {"exists": False, "files": 0, "bytes": 0, "suffixes": {}}
    processed_stats = _tree_stats(processed[0]) if processed else {"exists": False, "files": 0, "bytes": 0, "suffixes": {}}
    queryable = [did for did, row in expected.items() if row["queryable"]]
    if len(queryable) == len(expected):
        phase = "queryable"
        next_action = "query_or_join"
    elif raw_stats["files"] or extracted_stats["files"]:
        phase = "acquired_pending_parse"
        next_action = "run_crsp_parser_after_format_review"
    elif manifests:
        phase = "manifest_only"
        next_action = "run_crsp_moveit_sync_after_approval"
    else:
        phase = "not_materialized"
        next_action = "run_crsp_moveit_manifest_then_sync_after_approval"
    out.update(
        {
            "status": phase,
            "queryable": bool(queryable),
            "queryable_dataset_ids": queryable,
            "expected_datasets": expected,
            "manifest_paths": [str(p) for p in manifests],
            "raw": raw_stats,
            "extracted": extracted_stats,
            "processed": processed_stats,
            "next_action": next_action,
            "side_effects": "none — readiness inspection only",
        }
    )
    return out


def _compustat_status(repo_root: Path) -> dict[str, Any]:
    roots = _roots(repo_root)
    out = _base(
        "capital_iq_compustat",
        label="S&P Capital IQ / Compustat",
        capabilities=("fundamentals", "annual_company_financials"),
        roots=roots,
    )
    raw = _find_relative(repo_root, "data_lake/compustat/raw")
    processed = _find_relative(repo_root, "data_lake/compustat/processed/na_fundamentals_annual.parquet")
    raw_stats = _tree_stats(raw[0]) if raw else {"exists": False, "files": 0, "bytes": 0, "suffixes": {}}
    queryable = bool(processed and any(p.is_file() and p.stat().st_size > 0 for p in processed))
    if queryable:
        phase = "queryable"
        next_action = "query_or_join"
    elif raw_stats["files"]:
        phase = "export_staged_pending_normalization"
        next_action = "stage_compustat_export_in_isolated_root"
    else:
        phase = "entitled_not_materialized"
        next_action = "export_compustat_fundamentals_to_staging_after_approval"
    out.update(
        {
            "status": phase,
            "queryable": queryable,
            "queryable_dataset_ids": ["compustat_na_fundamentals_annual"] if queryable else [],
            "expected_datasets": {
                "compustat_na_fundamentals_annual": {
                    "path": _COMPUSTAT_EXPECTED["compustat_na_fundamentals_annual"],
                    "queryable": queryable,
                    "matches": [str(p) for p in processed],
                }
            },
            "raw": raw_stats,
            "processed": {"paths": [str(p) for p in processed], "queryable": queryable},
            "next_action": next_action,
            "side_effects": "none — readiness inspection only",
        }
    )
    return out


def _lseg_status(repo_root: Path) -> dict[str, Any]:
    roots = _roots(repo_root)
    out = _base(
        "lseg_edp",
        label="LSEG Workspace / EDP",
        capabilities=("security_master", "index_membership_pit", "estimates_revisions", "fundamentals"),
        roots=roots,
    )
    registry_path = _config_path(repo_root, "research_query_registry.json")
    rows: list[dict[str, Any]] = []
    if registry_path.is_file():
        try:
            rows = [r for r in json.loads(registry_path.read_text(encoding="utf-8")).get("datasets") or [] if str(r.get("source_id") or "") in {"lseg_edp", "lseg_desktop_rescue"}]
        except (OSError, json.JSONDecodeError):
            rows = []
    from scripts.research_data_mcp.synthesis.dataset_paths import resolve_dataset_file

    resolved: list[dict[str, Any]] = []
    for row in rows:
        path, reason = resolve_dataset_file(repo_root, row, roots=_roots(repo_root))
        resolved.append({"dataset_id": row.get("dataset_id"), "queryable": bool(path), "path": str(path) if path else None, "reason": reason})
    queryable = [r["dataset_id"] for r in resolved if r["queryable"]]
    out.update(
        {
            "status": "queryable" if queryable else "live_connector",
            "queryable": bool(queryable),
            "queryable_dataset_ids": queryable,
            "expected_datasets": resolved,
            "next_action": "query_or_targeted_entitlement_probe" if queryable else "targeted_lseg_entitlement_probe",
            "side_effects": "none — readiness inspection only",
        }
    )
    return out


def inspect_source(repo_root: str | Path, source_id: str = "") -> dict[str, Any]:
    """Return one source status or all sources; never touches the network."""
    root = Path(repo_root).resolve()
    sid = str(source_id or "").strip().lower()
    if sid in {"compustat", "capitaliq", "capital_iq", "capital_iq_compustat"}:
        rows = [_compustat_status(root)]
    elif sid in {"crsp", "moveit", "crsp_moveit"}:
        rows = [_crsp_status(root)]
    elif sid in {"lseg", "refinitiv", "lseg_edp", "lseg_desktop_rescue"}:
        rows = [_lseg_status(root)]
    elif sid in _PUBLIC_IDS:
        rows = [{
            "source_id": sid,
            "label": "Cursor-selected public/web source",
            "status": "live_connector" if sid != "webfetch" else "model_owned",
            "queryable": False,
            "selection_authority": "cursor_composer",
            "next_action": "model_select_candidate_then_build_handoff",
            "side_effects": "none — source status only",
        }]
    elif sid:
        rows = [{
            "source_id": sid,
            "label": sid,
            "status": "unknown_source",
            "queryable": False,
            "selection_authority": "cursor_composer",
            "next_action": "research_discover_source_search",
            "side_effects": "none — source status only",
        }]
    else:
        rows = [_lseg_status(root), _crsp_status(root), _compustat_status(root)] + [
            inspect_source(root, public_id) for public_id in ("huggingface", "datacite", "zenodo", "openalex", "webfetch")
        ]
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "repo_root": str(root),
        "sources": rows,
        "total": len(rows),
        "network_used": False,
        "selection_policy": "Composer/Cursor selects; backend validates and stages only the selected source",
    }


def _schema_path(repo_root: Path) -> Path:
    return _config_path(repo_root, "compustat_export_schema.json")


def _read_export(path: Path):
    import pandas as pd

    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path), [path.name]
    if suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            tables = [
                name
                for name in sorted(zf.namelist())
                if name.lower().endswith((".csv", ".txt")) and not name.endswith("/")
            ]
            if not tables:
                raise ValueError("zip contains no CSV/TXT export")
            frames = []
            for name in tables:
                with zf.open(name) as handle:
                    frames.append(pd.read_csv(handle, low_memory=False))
        return pd.concat(frames, ignore_index=True), tables
    if suffix not in {".csv", ".txt", ".csv.gz"}:
        raise ValueError(f"unsupported Compustat export type: {suffix or '[none]'}")
    return pd.read_csv(path, low_memory=False), [path.name]


def stage_compustat_export(
    repo_root: str | Path,
    input_path: str | Path,
    staging_root: str | Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Validate and write one Compustat export to an isolated staging root.

    This never writes the canonical ``data_lake/compustat/processed`` path and never
    edits the registry.  Promotion remains a separate reviewed operation.
    """
    root = Path(repo_root).resolve()
    source = Path(input_path).expanduser().resolve()
    stage = Path(staging_root).expanduser().resolve()
    if not source.is_file():
        return {"ok": False, "status": "missing_input", "input": str(source), "side_effects": "none"}
    try:
        schema = json.loads(_schema_path(root).read_text(encoding="utf-8"))
        frame, members = _read_export(source)
    except Exception as exc:  # noqa: BLE001 - report a bounded operator error
        return {"ok": False, "status": "invalid_export", "input": str(source), "error": str(exc)[:240], "side_effects": "none"}
    aliases = schema.get("column_aliases") or {}
    lower = {str(c).strip().lower(): c for c in frame.columns}
    mapping: dict[str, str] = {}
    for canonical, names in aliases.items():
        for name in names:
            if str(name).strip().lower() in lower:
                mapping[canonical] = lower[str(name).strip().lower()]
                break
    required = [str(x).lower() for x in (schema.get("required_columns_any") or ["gvkey"])]
    if not any(item in mapping for item in required):
        return {"ok": False, "status": "schema_mismatch", "input": str(source), "columns": [str(c) for c in frame.columns], "required_any": required, "side_effects": "none"}
    import pandas as pd

    normalized = pd.DataFrame({key: frame[column] for key, column in mapping.items()})
    if "datadate" in normalized.columns:
        normalized["datadate"] = pd.to_datetime(normalized["datadate"], errors="coerce")
    normalized = normalized.drop_duplicates().reset_index(drop=True)
    output = stage / "na_fundamentals_annual.parquet"
    if output.exists() and not overwrite:
        return {"ok": False, "status": "staging_exists", "output": str(output), "side_effects": "none"}
    stage.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="compustat-", suffix=".parquet", dir=stage, delete=False) as handle:
        temp_output = Path(handle.name)
    try:
        normalized.to_parquet(temp_output, index=False)
        os.replace(temp_output, output)
    finally:
        temp_output.unlink(missing_ok=True)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    manifest = {
        "status": "staged",
        "dataset_id": "compustat_na_fundamentals_annual",
        "input": str(source),
        "source_members": members,
        "output": str(output),
        "rows": int(len(normalized)),
        "columns": [str(c) for c in normalized.columns],
        "sha256": digest,
        "promotion": "not performed — reviewed promotion required",
    }
    (stage / "STAGING.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, **manifest, "side_effects": "isolated staging root only"}
