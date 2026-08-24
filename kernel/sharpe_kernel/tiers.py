"""Tier-aware resolution of data_lake paths for the alpha side.

Drive owns the procurement machinery (`research_data_mcp.storage_tiers`,
`collection_hydrate`); kernel must not import it. This module reads the same
`storage_tiers.json` *config* — not Drive code — so alpha can resolve a
registry path across hot/cache tiers and explain itself when it cannot.

Tier roles (see storage_tiers.json):
    hot        NVMe desk            latency; anything a scheduled job touches
    cache      Transcend bulk       bulk analysis reads
    canonical  Google Drive vault   durability only, never queried directly
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, NamedTuple

_CONFIG_NAME = "storage_tiers.json"
_MARKER = ".sharpe_research_bulk"

# Fallbacks used only when storage_tiers.json omits cache.default_candidates.
_FALLBACK_BULK_CANDIDATES = (
    "/mnt/research-data/sharpe-renaissance",
    "/media/phyrexian/Transcend1/sharpe-renaissance",
    "/media/phyrexian/Transcend/sharpe-renaissance",
)


class Candidate(NamedTuple):
    """One tier's guess at where a relative data_lake path lives."""

    tier: str
    path: Path
    exists: bool
    note: str = ""


def tiers_config_path(repo_root: Path) -> Path:
    """storage_tiers.json, preferring the root config/ symlink over drive/."""
    candidate = repo_root / "config" / _CONFIG_NAME
    if candidate.is_file():
        return candidate
    return repo_root / "drive" / "config" / _CONFIG_NAME


def load_tiers(repo_root: Path) -> dict[str, Any]:
    """Storage tier config, or {} when absent — resolution must still work."""
    path = tiers_config_path(repo_root)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _cache_candidates(cfg: dict[str, Any]) -> tuple[str, ...]:
    cache = ((cfg.get("tiers") or {}).get("cache") or {})
    configured = cache.get("default_candidates") or []
    out: list[str] = [str(c) for c in configured if c]
    for fallback in _FALLBACK_BULK_CANDIDATES:
        if fallback not in out:
            out.append(fallback)
    return tuple(out)


def bulk_root(repo_root: Path) -> Path | None:
    """Root of the mounted bulk cache, or None when unplugged.

    Prefers a directory carrying MARKER so an empty remount stub (data_lake
    present, no bytes) cannot shadow the real drive — the failure that took
    the alpha cycle down for six weeks.
    """
    cfg = load_tiers(repo_root)
    env = (os.environ.get("RESEARCH_BULK_ROOT") or "").strip()
    candidates: list[str] = [env] if env else []
    candidates.extend(_cache_candidates(cfg))

    seen: set[str] = set()
    marked: Path | None = None
    lake_only: Path | None = None
    for raw in candidates:
        if not raw or raw in seen:
            continue
        seen.add(raw)
        root = Path(raw).expanduser()
        if not root.is_dir():
            continue
        resolved = root.resolve()
        if (resolved / _MARKER).is_file():
            if marked is None:
                marked = resolved
            continue
        if lake_only is None and (resolved / "data_lake").is_dir():
            lake_only = resolved
    return marked or lake_only


def vault_root(repo_root: Path) -> str:
    """Canonical GDrive rclone root — for diagnostics, never for reads."""
    cfg = load_tiers(repo_root)
    tier = ((cfg.get("tiers") or {}).get("canonical") or {})
    return str(tier.get("drive_root") or "")


def _norm_rel(value: str | Path) -> str:
    return str(value).strip().lstrip("/").replace("\\", "/")


def _broken_link_note(path: Path) -> str:
    """Name the first dangling symlink at or above `path`.

    A stale external mount usually breaks a parent directory link, not the
    file itself, so reporting only the leaf hides the actual cause.
    """
    if path.exists():
        return ""
    for node in (path, *path.parents):
        if node.is_symlink() and not node.exists():
            target = os.readlink(node)
            if node == path:
                return f"dangling symlink -> {target}"
            return f"dangling parent {node.name} -> {target}"
    return ""


def candidates_for(repo_root: Path, rel: str | Path) -> list[Candidate]:
    """Ordered tiers to try for a repo-relative path, with existence flags."""
    relative = _norm_rel(rel)
    out: list[Candidate] = []

    hot = repo_root / relative
    out.append(Candidate("hot", hot, hot.exists(), _broken_link_note(hot)))

    if relative == "data_lake" or relative.startswith("data_lake/"):
        suffix = relative.removeprefix("data_lake/").removeprefix("data_lake")
        root = bulk_root(repo_root)
        if root is None:
            out.append(Candidate("cache", Path("<bulk cache not mounted>"), False, "unplugged or unset"))
        else:
            target = (root / "data_lake" / suffix) if suffix else (root / "data_lake")
            out.append(Candidate("cache", target, target.exists()))
    return out


def resolve(repo_root: Path, rel: str | Path) -> Path | None:
    """First tier that actually holds the path, or None."""
    for candidate in candidates_for(repo_root, rel):
        if candidate.exists:
            return candidate.path
    return None


def explain(repo_root: Path, rel: str | Path, *, subject: str = "") -> str:
    """Multi-line diagnostic naming every tier tried and what to do next."""
    relative = _norm_rel(rel)
    header = f"missing {subject or relative}"
    lines = [header]
    for candidate in candidates_for(repo_root, rel):
        mark = "present" if candidate.exists else "absent"
        detail = f" [{candidate.note}]" if candidate.note else ""
        lines.append(f"  {candidate.tier:<6}: {candidate.path} ({mark}){detail}")
    vault = vault_root(repo_root)
    if vault:
        lines.append(f"  vault : {vault} (canonical archive — hydrate to a local tier, do not query directly)")
    return "\n".join(lines)
