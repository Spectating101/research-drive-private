#!/usr/bin/env python3
"""Build reproducible, authority-safe research packages from held Library assets.

A package is an export of evidence the Library can actually prove it holds. It
is not a claim that the selected evidence is sufficient for a research design.
Registered/queryable/reference-only assets remain explicit when no local file
can be exported; they are never silently upgraded into data bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.procured_dataset import build_card_from_registry, file_checksum

PACKAGE_SCHEMA_VERSION = 1
DEFAULT_MAX_DATASETS = 40
DEFAULT_MAX_TOTAL_BYTES = 2_000_000_000
_SAFE_PART = re.compile(r"[^A-Za-z0-9._-]+")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_part(value: str, fallback: str = "asset") -> str:
    cleaned = _SAFE_PART.sub("_", str(value or "").strip()).strip("._")
    return cleaned[:120] or fallback


def _package_root(repo_root: Path) -> Path:
    configured = str(os.getenv("RESEARCH_PACKAGE_ROOT") or "").strip()
    root = Path(configured).expanduser() if configured else repo_root / "data_lake/research_packages"
    if not root.is_absolute():
        root = repo_root / root
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _bounded_file(repo_root: Path, rel_path: str) -> Path | None:
    rel = str(rel_path or "").strip()
    if not rel or "*" in rel:
        return None
    path = (repo_root / rel).resolve()
    try:
        path.relative_to(repo_root.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def _dataset_fact(dataset: dict[str, Any], key: str, *aliases: str) -> Any:
    for name in (key, *aliases):
        value = dataset.get(name)
        if value not in (None, "", [], {}):
            return value
    return None


def _metadata_record(dataset: dict[str, Any], card: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset_id": str(dataset.get("dataset_id") or dataset.get("id") or ""),
        "name": dataset.get("name") or dataset.get("display_name") or card.get("title"),
        "source": _dataset_fact(dataset, "source", "source_system", "publisher"),
        "source_url": _dataset_fact(dataset, "source_url", "url", "homepage"),
        "grain": dataset.get("grain"),
        "coverage": dataset.get("coverage"),
        "analysis_readiness": _dataset_fact(dataset, "analysis_readiness", "readiness"),
        "access_mode": _dataset_fact(dataset, "source_access_mode", "access_mode", "access_shape"),
        "join_keys": dataset.get("join_keys") or [],
        "fields": dataset.get("fields") or dataset.get("columns") or [],
        "limitations": _dataset_fact(dataset, "limitations", "caveats"),
        "lineage": dataset.get("lineage") or card.get("lineage") or {},
        "procurement": dataset.get("procurement") or card.get("procurement") or {},
        "open_paths": card.get("open_paths") or {},
        "status": card.get("status"),
        "badges": card.get("badges") or [],
    }


def _manifest_identity(research_need: str, requested_ids: list[str], resolved: list[dict[str, Any]]) -> str:
    identity = {
        "research_need": str(research_need or "").strip(),
        "dataset_ids": requested_ids,
        "resolved": [
            {
                "dataset_id": row.get("dataset_id"),
                "files": [
                    {
                        "path": item.get("source_path"),
                        "bytes": item.get("bytes"),
                        "checksum": item.get("checksum"),
                    }
                    for item in row.get("files") or []
                ],
            }
            for row in resolved
        ],
    }
    raw = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def _readme(manifest: dict[str, Any]) -> str:
    lines = [
        "# Research Drive Library package",
        "",
        f"Research request: {manifest.get('research_need') or 'Not specified'}",
        "",
        "This package contains evidence that Research Drive could prove was held and exportable when the package was prepared.",
        "It does not establish that the evidence is complete, sufficient, unbiased, or appropriate for every research design.",
        "",
        "## Package summary",
        "",
        f"- Data assets included: {len(manifest.get('included') or [])}",
        f"- Metadata/access-only holdings: {len(manifest.get('metadata_only') or [])}",
        f"- Excluded requests: {len(manifest.get('excluded') or [])}",
        f"- Data files: {manifest.get('data_file_count') or 0}",
        f"- Source bytes packaged: {manifest.get('data_bytes') or 0}",
        "",
        "## Authority boundary",
        "",
        "- Matched does not mean included.",
        "- Held does not mean downloadable.",
        "- Query-ready does not mean a local file exists.",
        "- Reference-only records are never converted into data files.",
        "- `manifest.json` is the canonical record of what was included, metadata-only, or excluded and why.",
        "",
    ]
    if manifest.get("metadata_only"):
        lines.extend(["## Metadata/access-only holdings", ""])
        for row in manifest["metadata_only"]:
            lines.append(f"- {row.get('dataset_id')}: {row.get('reason')}")
        lines.append("")
    if manifest.get("excluded"):
        lines.extend(["## Excluded", ""])
        for row in manifest["excluded"]:
            lines.append(f"- {row.get('dataset_id')}: {row.get('reason')}")
        lines.append("")
    return "\n".join(lines)


def prepare_library_package(
    gateway: Any,
    *,
    research_need: str = "",
    dataset_ids: list[str] | None = None,
    max_datasets: int = DEFAULT_MAX_DATASETS,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> dict[str, Any]:
    repo_root = Path(gateway.repo_root).resolve()
    requested: list[str] = []
    for raw in dataset_ids or []:
        dataset_id = str(raw or "").strip()
        if dataset_id and dataset_id not in requested:
            requested.append(dataset_id)
    if not requested:
        raise ValueError("dataset_ids must contain at least one Library dataset")
    if len(requested) > max(1, int(max_datasets)):
        raise ValueError(f"package is limited to {max_datasets} datasets")

    resolved: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    data_bytes = 0

    for dataset_id in requested:
        try:
            dataset = gateway.describe_dataset(dataset_id)
        except Exception as exc:
            excluded.append({
                "dataset_id": dataset_id,
                "reason": "not_registered",
                "detail": str(exc)[:240],
            })
            continue
        if not isinstance(dataset, dict) or not dataset.get("dataset_id"):
            excluded.append({"dataset_id": dataset_id, "reason": "not_registered"})
            continue

        card = build_card_from_registry(repo_root, dataset)
        metadata = _metadata_record(dataset, card)
        files: list[dict[str, Any]] = []
        for file_row in card.get("files") or []:
            rel_path = str(file_row.get("path") or "")
            path = _bounded_file(repo_root, rel_path)
            if path is None:
                continue
            size = path.stat().st_size
            if data_bytes + size > max(0, int(max_total_bytes)):
                continue
            checksum = str(file_row.get("checksum") or "") or file_checksum(path)
            files.append({
                "source_path": rel_path,
                "name": path.name,
                "bytes": size,
                "checksum": checksum,
                "absolute_path": str(path),
            })
            data_bytes += size
        resolved.append({
            **metadata,
            "files": files,
            "package_state": "data_included" if files else "metadata_only",
            "package_reason": "local_file_verified" if files else "no_exportable_local_file",
        })

    package_id = _manifest_identity(str(research_need or "").strip(), requested, resolved)
    root = _package_root(repo_root)
    package_dir = root / package_id
    package_dir.mkdir(parents=True, exist_ok=True)
    zip_path = package_dir / f"research-drive-package-{package_id}.zip"
    manifest_path = package_dir / "manifest.json"

    included_manifest: list[dict[str, Any]] = []
    metadata_only: list[dict[str, Any]] = []
    for row in resolved:
        clean = {key: value for key, value in row.items() if key != "files"}
        clean["files"] = [
            {key: value for key, value in item.items() if key != "absolute_path"}
            for item in row.get("files") or []
        ]
        if row.get("files"):
            included_manifest.append(clean)
        else:
            metadata_only.append({
                **clean,
                "reason": row.get("package_reason") or "no_exportable_local_file",
            })

    manifest: dict[str, Any] = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "package_id": package_id,
        "prepared_at": _utc_now(),
        "research_need": str(research_need or "").strip(),
        "requested_dataset_ids": requested,
        "included": included_manifest,
        "metadata_only": metadata_only,
        "excluded": excluded,
        "data_file_count": sum(len(row.get("files") or []) for row in resolved),
        "data_bytes": data_bytes,
        "sufficiency_claim": False,
        "authority_note": (
            "This package reflects current Library holdings and verified local export paths; "
            "it does not establish analytical sufficiency."
        ),
    }

    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    manifest_path.write_text(manifest_text, encoding="utf-8")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        zf.writestr("README.md", _readme(manifest))
        zf.writestr("manifest.json", manifest_text)
        for row in resolved:
            dataset_id = _safe_part(str(row.get("dataset_id") or "dataset"), "dataset")
            metadata = {key: value for key, value in row.items() if key not in {"files", "absolute_path"}}
            zf.writestr(
                f"metadata/{dataset_id}.json",
                json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            )
            zf.writestr(
                f"access/{dataset_id}.json",
                json.dumps(
                    {
                        "dataset_id": row.get("dataset_id"),
                        "analysis_readiness": row.get("analysis_readiness"),
                        "access_mode": row.get("access_mode"),
                        "open_paths": row.get("open_paths") or {},
                        "package_state": row.get("package_state"),
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ) + "\n",
            )
            for item in row.get("files") or []:
                path = Path(item["absolute_path"])
                zf.write(path, f"data/{dataset_id}/{_safe_part(path.name, 'data')}")

    zip_checksum = file_checksum(zip_path)
    return {
        "package_id": package_id,
        "status": "ready",
        "research_need": manifest["research_need"],
        "included": manifest["included"],
        "metadata_only": manifest["metadata_only"],
        "excluded": manifest["excluded"],
        "data_file_count": manifest["data_file_count"],
        "data_bytes": manifest["data_bytes"],
        "sufficiency_claim": False,
        "manifest": manifest,
        "archive": {
            "name": zip_path.name,
            "bytes": zip_path.stat().st_size,
            "checksum": zip_checksum,
        },
        "download_path": f"/library/packages/{package_id}/download",
    }


def get_library_package(repo_root: Path, package_id: str) -> dict[str, Any]:
    safe_id = _safe_part(package_id, "")
    if not safe_id or safe_id != str(package_id or "").strip():
        raise KeyError(package_id)
    root = _package_root(Path(repo_root).resolve())
    package_dir = (root / safe_id).resolve()
    try:
        package_dir.relative_to(root)
    except ValueError as exc:
        raise KeyError(package_id) from exc
    manifest_path = package_dir / "manifest.json"
    zip_path = package_dir / f"research-drive-package-{safe_id}.zip"
    if not manifest_path.is_file() or not zip_path.is_file():
        raise KeyError(package_id)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "package_id": safe_id,
        "status": "ready",
        "manifest": manifest,
        "archive": {
            "name": zip_path.name,
            "bytes": zip_path.stat().st_size,
            "checksum": file_checksum(zip_path),
        },
        "download_path": f"/library/packages/{safe_id}/download",
        "_archive_file": str(zip_path),
    }
