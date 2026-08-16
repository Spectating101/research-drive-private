"""Find the bytes a registry entry actually names.

The registry addresses a dataset three ways and they are not interchangeable:

    local_path                          a concrete file, relative to a data root
    local_root + default_run_id + local_file
                                        a run-stamped file inside a shared root
    local_root                          a directory, only unambiguous when it
                                        holds exactly one tabular file

Ten datasets share `data_lake/refinitiv_backfill`, so resolving `local_root`
alone and taking the first file found returns a different dataset than the one
asked for. That is worse than failing, so ambiguity is refused by name.

Data can also live outside the repo being served. RESEARCH_DATA_ROOTS (colon
separated, absolute) lists additional roots to search, in order. Unset, this
behaves exactly as before: repo_root, then repo_root/drive.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

TABULAR_SUFFIXES = (".parquet", ".csv", ".csv.gz")
AMBIGUITY_SCAN_CAP = 64


def data_roots(repo_root: Path | str, extra: list[str] | None = None) -> list[Path]:
    """Search order for dataset bytes. repo_root first so local wins."""
    repo_root = Path(repo_root).resolve()
    roots: list[Path] = [repo_root, repo_root / "drive"]
    configured = extra if extra is not None else _configured_roots()
    for item in configured:
        p = Path(item).expanduser()
        if p.is_absolute() and p not in roots:
            roots.append(p)
    return [r for r in roots if r.exists()]


def _configured_roots() -> list[str]:
    raw = (os.getenv("RESEARCH_DATA_ROOTS") or "").strip()
    return [part for part in raw.split(":") if part.strip()] if raw else []


def _tabular_files(directory: Path, cap: int = AMBIGUITY_SCAN_CAP) -> list[Path]:
    found: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(directory):
        for name in sorted(filenames):
            if name.endswith(TABULAR_SUFFIXES):
                found.append(Path(dirpath) / name)
                if len(found) >= cap:
                    return found
    return found


def resolve_dataset_file(
    repo_root: Path | str,
    source: dict[str, Any],
    *,
    roots: list[Path] | None = None,
) -> tuple[Path | None, str | None]:
    """Return (path, None) or (None, reason).

    A reason is always specific enough to act on: a missing root, a named file
    that is not there, or an ambiguous directory naming how many candidates it
    found. It never guesses which of several files was meant.
    """
    dataset_id = str(source.get("dataset_id") or "dataset")
    search = roots if roots is not None else data_roots(repo_root)
    if not search:
        return None, "no data roots exist"

    local_path = str(source.get("local_path") or "").strip()
    local_root = str(source.get("local_root") or "").strip().rstrip("/*")
    local_file = str(source.get("local_file") or "").strip()
    run_id = str(source.get("default_run_id") or "").strip()

    # 1. A concrete local_path wins wherever it resolves.
    if local_path and "*" not in local_path:
        for base in search:
            candidate = base / local_path
            if candidate.is_file():
                return candidate, None

    base_rel = local_root or (local_path.rstrip("/*") if local_path else "")
    if not base_rel:
        return None, f"{dataset_id}: registry declares no local_path or local_root"

    roots_seen: list[Path] = []
    for base in search:
        root = base / base_rel
        if not root.exists():
            continue
        roots_seen.append(root)

        # 2. The registry named a file — use it, run-stamped first.
        if local_file:
            candidates = ([root / run_id / local_file] if run_id else []) + [root / local_file]
            for candidate in candidates:
                if candidate.is_file():
                    return candidate, None
            continue

        # 3. A directory is only unambiguous with exactly one tabular file.
        if root.is_file():
            return root, None
        files = _tabular_files(root)
        if len(files) == 1:
            return files[0], None
        if len(files) > 1:
            return None, (
                f"{dataset_id}: {base_rel} holds {len(files)}{'+' if len(files) >= AMBIGUITY_SCAN_CAP else ''} "
                "tabular files and the registry names no local_file; refusing to guess which is meant"
            )

    if not roots_seen:
        return None, (
            f"{dataset_id}: {base_rel} is not under any data root "
            f"({', '.join(str(r) for r in search)}); set RESEARCH_DATA_ROOTS if the bytes live elsewhere"
        )
    if local_file:
        return None, f"{dataset_id}: {base_rel} exists but does not contain {local_file}"
    return None, f"{dataset_id}: {base_rel} contains no parquet or csv files"
