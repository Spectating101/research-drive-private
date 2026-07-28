"""Bounded row previews for Library/UI — local files first, light GDrive sample fallback."""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

TABULAR_SUFFIXES = {".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".parquet"}


def _as_records(rows: list[Any], *, limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows[:limit]:
        if isinstance(row, dict):
            out.append(row)
        elif isinstance(row, (list, tuple)):
            out.append({f"c{i}": value for i, value in enumerate(row)})
        else:
            out.append({"value": row})
    return out


def _skip_name(name: str) -> bool:
    lower = name.lower()
    return any(
        token in lower
        for token in ("manifest", "receipt", "registration", "checksum", "readme", "license")
    ) or lower.endswith(".md")


def sample_file(path: Path, *, limit: int = 25) -> dict[str, Any] | None:
    if not path.is_file() or _skip_name(path.name):
        return None
    suffix = path.suffix.lower()
    try:
        if suffix in {".csv", ".tsv"}:
            delim = "\t" if suffix == ".tsv" else ","
            with path.open(encoding="utf-8", errors="replace", newline="") as fh:
                reader = csv.DictReader(fh, delimiter=delim)
                rows = []
                for i, row in enumerate(reader):
                    rows.append(dict(row))
                    if i + 1 >= limit:
                        break
            return {"kind": suffix.lstrip("."), "path": str(path), "rows": rows} if rows else None
        if suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace")[:2_000_000])
            if isinstance(payload, list):
                rows = _as_records(payload, limit=limit)
                return {"kind": "json", "path": str(path), "rows": rows} if rows else None
            if isinstance(payload, dict):
                for key in ("data", "rows", "items", "results", "records", "fields"):
                    if isinstance(payload.get(key), list) and payload[key]:
                        return {
                            "kind": "json",
                            "path": str(path),
                            "rows": _as_records(payload[key], limit=limit),
                        }
                values = list(payload.values())
                if values and all(isinstance(v, dict) for v in values[:8]):
                    sample_keys = set().union(*(v.keys() for v in values[:8] if isinstance(v, dict)))
                    if sample_keys & {"ticker", "title", "cik", "cik_str", "name", "exchange", "symbol"}:
                        rows = [{"key": k, **v} for k, v in list(payload.items())[:limit]]
                        return {"kind": "json_object", "path": str(path), "rows": rows}
                # Job/metadata JSON — not a table preview.
                if {"manifest_id", "job_id", "output", "files", "status", "plan"} & set(payload.keys()):
                    return None
            return None
        if suffix in {".jsonl", ".ndjson"}:
            rows = []
            with path.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    rows.append(json.loads(line))
                    if len(rows) >= limit:
                        break
            return {"kind": "jsonl", "path": str(path), "rows": _as_records(rows, limit=limit)} if rows else None
        if suffix == ".parquet":
            import pandas as pd

            df = pd.read_parquet(path)
            rows = json.loads(df.head(limit).to_json(orient="records"))
            return {"kind": "parquet", "path": str(path), "rows": rows} if rows else None
    except Exception as exc:  # noqa: BLE001
        return {"kind": "error", "path": str(path), "rows": [], "error": str(exc)}
    return None


def _candidate_local_paths(repo_root: Path, spec: dict[str, Any]) -> list[Path]:
    out: list[Path] = []
    did = str(spec.get("dataset_id") or "").strip()
    for key in ("local_path", "local_root"):
        raw = str(spec.get(key) or "").strip()
        if not raw:
            continue
        path = Path(raw)
        if not path.is_absolute():
            path = repo_root / path
        out.append(path)
    if did:
        out.append(repo_root / "data_lake" / "procured" / did)
        out.append(repo_root / "data_lake" / "preview_cache" / did)
    seen: set[str] = set()
    uniq: list[Path] = []
    for path in out:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(path)
    return uniq


def _rank_file(path: Path) -> tuple[int, int, str]:
    name = path.name.lower()
    suffix = path.suffix.lower()
    score = 0
    if "company_tickers" in name:
        score += 100
    if suffix in {".csv", ".tsv", ".parquet"}:
        score += 80
    if suffix in {".jsonl", ".ndjson"}:
        score += 70
    if suffix == ".json":
        score += 40
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return (-score, -size, str(path))


def _iter_tabular_files(root: Path, *, max_files: int = 12) -> list[Path]:
    if root.is_file():
        return [] if _skip_name(root.name) else [root]
    if not root.is_dir():
        return []
    files = [
        path
        for path in root.rglob("*")
        if path.is_file() and not _skip_name(path.name) and path.suffix.lower() in TABULAR_SUFFIXES
    ]
    files.sort(key=_rank_file)
    return files[:max_files]


def _rclone_lsf(remote: str) -> list[str]:
    if not remote.startswith("gdrive:") or not shutil.which("rclone"):
        return []
    try:
        proc = subprocess.run(
            ["rclone", "lsf", remote, "--files-only", "-R"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _pick_remote_name(names: list[str]) -> str:
    ranked: list[tuple[int, str]] = []
    for name in names:
        base = Path(name).name
        if _skip_name(base):
            continue
        suffix = Path(name).suffix.lower()
        if suffix not in TABULAR_SUFFIXES:
            continue
        score = 0
        lower = base.lower()
        if "company_tickers" in lower:
            score += 100
        if suffix in {".csv", ".tsv", ".parquet"}:
            score += 80
        if suffix in {".jsonl", ".ndjson"}:
            score += 70
        if suffix == ".json":
            score += 40
        ranked.append((-score, name))
    ranked.sort()
    return ranked[0][1] if ranked else ""


def _hydrate_remote_sample(repo_root: Path, remote: str, *, dataset_id: str) -> Path | None:
    pick = _pick_remote_name(_rclone_lsf(remote))
    if not pick:
        return None
    dest_dir = repo_root / "data_lake" / "preview_cache" / dataset_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / Path(pick).name
    if dest.is_file() and dest.stat().st_size > 0 and not _skip_name(dest.name):
        return dest
    src = remote.rstrip("/") + "/" + pick
    try:
        proc = subprocess.run(
            ["rclone", "copyto", src, str(dest), "--max-transfer", "32M", "--retries", "1"],
            check=False,
            capture_output=True,
            text=True,
            timeout=6,
        )
    except Exception:
        return None
    if proc.returncode != 0 or not dest.is_file():
        return None
    return dest


def preview_dataset_rows(
    repo_root: str | Path,
    spec: dict[str, Any],
    *,
    limit: int = 25,
    allow_remote: bool = True,
) -> dict[str, Any]:
    """Return up to ``limit`` sample rows for UI preview."""
    repo_root = Path(repo_root).resolve()
    limit = max(1, min(int(limit or 25), 100))
    dataset_id = str(spec.get("dataset_id") or "").strip() or "unknown"
    tried: list[str] = []

    for root in _candidate_local_paths(repo_root, spec):
        tried.append(str(root))
        for path in _iter_tabular_files(root):
            sample = sample_file(path, limit=limit)
            if sample and sample.get("rows"):
                return {
                    "dataset_id": dataset_id,
                    "rows": sample["rows"],
                    "meta": {
                        "preview": True,
                        "preview_kind": sample.get("kind"),
                        "source_path": sample.get("path"),
                        "returned": len(sample["rows"]),
                        "limit": limit,
                        "mode": "local_sample",
                    },
                }

    remote = str(
        spec.get("vault_path")
        or spec.get("canonical_remote")
        or (spec.get("lineage") or {}).get("canonical_remote")
        or ""
    ).strip()
    if allow_remote and remote.startswith("gdrive:"):
        tried.append(remote)
        local = _hydrate_remote_sample(repo_root, remote, dataset_id=dataset_id)
        if local:
            sample = sample_file(local, limit=limit)
            if sample and sample.get("rows"):
                return {
                    "dataset_id": dataset_id,
                    "rows": sample["rows"],
                    "meta": {
                        "preview": True,
                        "preview_kind": sample.get("kind"),
                        "source_path": sample.get("path"),
                        "canonical_remote": remote,
                        "returned": len(sample["rows"]),
                        "limit": limit,
                        "mode": "gdrive_sample",
                    },
                }

    return {
        "dataset_id": dataset_id,
        "rows": [],
        "meta": {
            "preview": True,
            "queryable": False,
            "returned": 0,
            "limit": limit,
            "tried": tried[:12],
            "error": "preview_unavailable",
            "message": "No local or GDrive sample file found for preview.",
        },
    }
