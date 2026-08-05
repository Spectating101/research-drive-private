#!/usr/bin/env python3
"""Vault partition status cards — NOT acquisition/product capability lanes.

Drive partitions are organizational folders. Desk capability is AI identify +
custom procure.

The original rule here was "surface only partitions holding local bytes". That
measured the wrong store: ``collection_partitions.json`` declares the canonical
holding to be Drive and calls ``legacy_local_path`` staging/hydrate only, so 14
professor-visible partitions holding real data -- 156 GiB of GDELT, 2.0 GiB of
Asia equities, Reddit, derived panels -- all reported zero and vanished. Two of
25 partitions reached the endpoint.

Holding is now judged against the canonical stores, strongest evidence first:

1. registry datasets in this partition that are ``materialization.query_ready``
   -- bytes something actually opened, not a claim about them;
2. an authored ``drive_size_hint`` -- a migrated Drive holding;
3. local staging bytes -- the old signal, kept, now merely one of three.

The docstring's original promise still holds: an empty vendor-named slot is
never sold as a holding. But it is no longer hidden either. A declared route
with nothing behind it yet (CRSP awaiting export, Compustat pending) surfaces
as ``held=False`` with ``action="request_access"`` and an amount that says so.
Hiding it loses the thing no catalog competitor can offer -- "we don't hold
this, here is the route" -- while showing it as held would be the lie the
original rule was written to prevent. Only the third case, a slot with no
holding *and* no route, is still dropped: it has nothing to say.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=4)
def _load_partitions(repo_root: str) -> dict[str, Any]:
    path = Path(repo_root).resolve() / "config/collection_partitions.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_remote(repo_root: Path, part: dict[str, Any], *, use_target: bool = False) -> str | None:
    root = str(_load_partitions(str(repo_root)).get("canonical_root", "")).rstrip("/")
    if not root:
        return None
    rel = part.get("target_drive_path") if use_target else part.get("legacy_drive_path")
    if not rel:
        return None
    return f"{root}/{rel}"


def _local_storage_path(repo_root: Path, part: dict[str, Any]) -> Path | None:
    raw = part.get("legacy_local_path")
    if not raw:
        return None
    return Path(repo_root).resolve() / str(raw)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _local_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


_SIZE_UNITS = {"b": 1, "kib": 1024, "mib": 1024**2, "gib": 1024**3, "tib": 1024**4}


def _drive_bytes_hint(part: dict[str, Any]) -> int:
    """Bytes implied by an authored ``drive_size_hint`` such as ``"156 GiB"``.

    The hint is operator-authored rather than measured, so it is evidence that a
    holding exists, not an accurate size. It is used as a boolean signal and
    reported verbatim; it is never summed into a total that would imply
    precision the field does not have.
    """
    raw = str(part.get("drive_size_hint") or "").strip()
    if not raw:
        return 0
    number, _, unit = raw.partition(" ")
    try:
        value = float(number)
    except ValueError:
        return 0
    return int(value * _SIZE_UNITS.get(unit.strip().lower(), 0))


@lru_cache(maxsize=4)
def _registry_holdings(repo_root: str) -> dict[str, dict[str, int]]:
    """Per-partition registry counts, keyed by ``partition_id``.

    ``query_ready`` lives under ``materialization`` and means a probe opened the
    bytes. That makes it the only holding signal on this list that cannot be
    satisfied by an assertion in a config file, which is why it outranks the
    authored size hint.
    """
    path = Path(repo_root).resolve() / "config/research_query_registry.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8")).get("datasets") or []
    except (OSError, ValueError):
        return {}
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("partition_id") or "")
        if not pid:
            continue
        mat = row.get("materialization") or {}
        bucket = out.setdefault(pid, {"datasets": 0, "query_ready": 0, "verified": 0, "visible": 0})
        bucket["datasets"] += 1
        bucket["visible"] += 1 if row.get("professor_visible") else 0
        bucket["query_ready"] += 1 if mat.get("query_ready") else 0
        bucket["verified"] += 1 if mat.get("query_verified") else 0
    return out


def _holding(repo_root: Path, part: dict[str, Any], *, local_bytes: int) -> dict[str, Any]:
    """What this partition actually holds, and on what evidence."""
    pid = str(part.get("id") or "")
    counts = _registry_holdings(str(repo_root)).get(pid) or {}
    query_ready = int(counts.get("query_ready") or 0)
    drive_bytes = _drive_bytes_hint(part)
    if query_ready:
        basis = "query_ready_datasets"
    elif drive_bytes:
        basis = "drive_size_hint"
    elif local_bytes:
        basis = "local_bytes"
    else:
        basis = "none"
    return {
        "held": basis != "none",
        "holding_basis": basis,
        "registry_datasets": int(counts.get("datasets") or 0),
        "query_ready_datasets": query_ready,
        "query_verified_datasets": int(counts.get("verified") or 0),
        "drive_size_hint": str(part.get("drive_size_hint") or "") or None,
        "local_bytes": local_bytes,
    }


def _stage_for_status(status: str, *, local_ok: bool) -> tuple[str, str]:
    s = (status or "unknown").lower()
    if s in {"frozen_release", "complete", "migrated", "synced"} and local_ok:
        return "complete", "green"
    if s in {"active", "procurement_wired", "running"}:
        return "running" if local_ok else "idle", "blue" if local_ok else "amber"
    if s == "local_only":
        return "idle", "amber"
    return "idle", "amber" if not local_ok else "green"


def _release_meta(repo_root: Path, part: dict[str, Any]) -> dict[str, Any] | None:
    local = _local_storage_path(repo_root, part)
    if not local or not local.is_dir():
        return None
    for child in sorted(local.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        rel = child / "RELEASE.json"
        if rel.is_file():
            try:
                return json.loads(rel.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None
    return None


def _should_surface(part: dict[str, Any], *, holding: dict[str, Any]) -> bool:
    """Never sell empty/example vendor folders as desk capabilities.

    Surfacing is not the same as claiming a holding. A partition earns a card by
    having something true to say -- held bytes, or a declared collection route
    -- and the card says which. What is excluded here is what a researcher can
    neither query nor request.
    """
    if part.get("professor_visible") is False:
        return False
    domain = str(part.get("domain") or "")
    if domain == "backend":
        return False
    status = str(part.get("status") or "").lower()
    if status in {"example_slot", "example_reference", "catalog_only"}:
        return False
    pid = str(part.get("id") or "")
    # Generic land zone is always a valid desk surface.
    if pid == "acquired.procured" or domain == "acquired":
        return True
    if holding.get("held"):
        return True
    # No bytes, but registry datasets name this partition as their destination:
    # a route a researcher can request. Shown as unheld, never as a holding.
    return int(holding.get("registry_datasets") or 0) > 0


# Storage domain → shelf, for partitions holding no registry dataset to inherit
# a shelf from. Without this they collect in an "(unshelved)" bucket, which is
# not a place anybody browses to.
_DOMAIN_SHELF = {
    "news": "news_events",
    "markets": "asia_stocks",
    "official": "filings_disclosures",
    "reference": "lookups_ids",
    "social": "news_events",
    "catalog": "find_datasets",
    "acquired": "project_downloads",
    "derived": "analysis_ready",
}


@lru_cache(maxsize=4)
def _derived_shelf_index(repo_root: str) -> dict[str, dict[str, Any]]:
    """Map partition_id → shelf when the taxonomy comes from the registry.

    A partition can hold datasets from several shelves -- ``acquired.procured``
    is a landing zone for anything -- so it is filed under the shelf holding the
    most of its datasets, with the rest reported in ``shelf_ids``. The lane is a
    storage card; the authoritative shelf membership is the dataset's, via
    :func:`shelf_datasets`.
    """
    tally: dict[str, dict[str, int]] = {}
    for hint, rows in shelf_datasets(repo_root).items():
        for row in rows:
            pid = str(row.get("partition_id") or "")
            if pid:
                tally.setdefault(pid, {})[hint] = tally.setdefault(pid, {}).get(hint, 0) + 1
    out: dict[str, dict[str, Any]] = {}
    for pid, hints in tally.items():
        best = max(sorted(hints), key=lambda h: hints[h])
        out[pid] = {**_shelf_meta(best), "shelf_ids": sorted(hints)}
    return out


def _shelf_meta(shelf_id: str) -> dict[str, Any]:
    label, blurb, sort = _SHELF_LABELS.get(
        shelf_id, (shelf_id.replace("_", " ").title(), "", 950)
    )
    return {
        "shelf_id": shelf_id,
        "shelf_label": label,
        "shelf_blurb": blurb,
        "shelf_sort": sort,
        "shelf_visible": True,
    }


def _shelf_index(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map partition_id → shelf metadata for professor navigation."""
    out: dict[str, dict[str, Any]] = {}
    nav = cfg.get("professor_nav") or {}
    for shelf in nav.get("shelves") or []:
        shelf_meta = {
            "shelf_id": shelf.get("id"),
            "shelf_label": shelf.get("label"),
            "shelf_blurb": shelf.get("blurb"),
            "shelf_sort": shelf.get("sort", 500),
            "shelf_visible": shelf.get("professor_visible", True) is not False,
        }
        for pid in shelf.get("partition_ids") or []:
            out[str(pid)] = shelf_meta
    return out


def partition_lane(
    repo_root: Path,
    part: dict[str, Any],
    *,
    shelf_by_pid: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    local = _local_storage_path(repo_root, part)
    local_ok = bool(local and local.exists())
    local_bytes = _local_bytes(local) if local_ok and local else 0
    holding = _holding(repo_root, part, local_bytes=local_bytes)
    if not _should_surface(part, holding=holding):
        return None
    held = bool(holding["held"])

    domain = str(part.get("domain") or "")
    pid = str(part.get("id") or "")
    registry_ids = list(part.get("registry_dataset_ids") or [])
    status = str(part.get("status") or "unknown")
    # Staging presence used to stand in for "has data". Held is the real test:
    # a partition whose bytes sit on Drive is complete, not idle.
    stage, tone = _stage_for_status(status, local_ok=held)
    release = _release_meta(repo_root, part) if status == "frozen_release" else None
    shelf = (shelf_by_pid or {}).get(pid) or {}
    if not shelf.get("shelf_id"):
        # Holds no registry dataset to inherit a shelf from; file it by domain.
        fallback = _DOMAIN_SHELF.get(domain)
        if fallback:
            shelf = {**_shelf_meta(fallback), "shelf_ids": [fallback], "shelf_inferred": True}

    # The amount line is the card's honesty: it leads with what was proven
    # queryable, falls back to the authored Drive size, and when neither exists
    # says outright that nothing is held yet rather than going quiet.
    amount_bits: list[str] = []
    ready = int(holding["query_ready_datasets"])
    if ready:
        amount_bits.append(f"{ready} queryable dataset{'s' if ready != 1 else ''}")
    elif registry_ids and not held:
        # "Declared" only reads as a caveat next to nothing held. Beside a real
        # Drive holding it just looks like a smaller, contradictory number.
        amount_bits.append(f"{len(registry_ids)} dataset{'s' if len(registry_ids) != 1 else ''} declared")
    if holding["drive_size_hint"]:
        amount_bits.append(f"{holding['drive_size_hint']} on Drive")
    elif local_bytes:
        gib = local_bytes / (1024**3)
        amount_bits.append(f"{gib:.2f} GiB local" if gib >= 0.1 else f"{local_bytes / (1024**2):.0f} MiB local")
    if not held:
        amount_bits.append("not yet held — request export")

    progress = 100.0 if (stage == "complete" and held) else (50.0 if held else 0.0)
    if not held:
        # An unheld route is never green, whatever its config status says.
        stage, tone = "idle", "amber"
    if release:
        progress = 100.0
        stage = "complete"
        tone = "green"

    remote = _canonical_remote(repo_root, part, use_target=True) or _canonical_remote(repo_root, part)
    subtitle = str(part.get("professor_label") or part.get("title") or pid)
    scope = str(part.get("professor_blurb") or part.get("description") or "")[:200]
    detail: dict[str, Any] = {
        "partition_id": pid,
        "domain": domain,
        "status": status,
        "local_path": str(local) if local else None,
        "local_present": local_ok,
        "registry_dataset_ids": registry_ids,
        "target_drive_path": part.get("target_drive_path"),
        "canonical_remote": remote,
        "role": "vault_holding" if held else "declared_route",
        "shelf_id": shelf.get("shelf_id"),
        "professor_sort": part.get("professor_sort"),
        **holding,
        # What the card's button may honestly offer. An unheld route can be
        # requested but not queried, and saying so here stops the UI promising
        # a download that has nothing behind it.
        "action": "query" if held else "request_access",
    }
    if release:
        detail["release"] = {
            "release_id": release.get("release_id"),
            "frozen_at": release.get("frozen_at"),
            "platform_readiness": release.get("platform_readiness"),
            "bulk_harvest_policy": release.get("bulk_harvest_policy"),
        }

    return {
        "id": f"partition_{pid.replace('.', '_')}",
        "partition_id": pid,
        "name": subtitle,
        "subtitle": subtitle,
        "professor_label": subtitle,
        "professor_blurb": scope,
        "professor_sort": int(part.get("professor_sort") or shelf.get("shelf_sort") or 500),
        "professor_visible": True,
        "shelf_id": shelf.get("shelf_id"),
        "shelf_label": shelf.get("shelf_label"),
        "shelf_ids": list(shelf.get("shelf_ids") or ([shelf["shelf_id"]] if shelf.get("shelf_id") else [])),
        "scope": scope,
        "stage": stage,
        "tone": tone,
        "progress": progress,
        "amount": " · ".join(amount_bits) if amount_bits else "partition",
        "worker": "cluster archive",
        "destination": remote or str(part.get("target_drive_path") or ""),
        "updated_at": (release or {}).get("frozen_at") or _now(),
        "detail": detail,
        # Kept kind for FE back-compat; role clarifies these are not product lanes.
        "kind": "collection_partition",
        "role": detail["role"],
        # Surfaced alongside detail so a card can be rendered without reaching
        # into it -- the distinction between held and merely routed is the one
        # thing the UI must not get wrong.
        "held": held,
        "holding_basis": holding["holding_basis"],
        "query_ready_datasets": holding["query_ready_datasets"],
        "action": detail["action"],
    }


_SHELF_LABELS: dict[str, tuple[str, str, int]] = {
    # shelf_hint -> (label, blurb, sort). Wording is the professor's, not the
    # storage layer's: nobody browses for "reference.crsp-moveit".
    "news_events": ("News & events", "What happened — news graphs and country shock panels", 100),
    "us_markets": ("US markets", "US equity history, fundamentals and index membership", 200),
    "asia_stocks": ("Asia markets", "Taiwan and Asia stock panels and exchange data", 300),
    "crypto_onchain": ("Crypto & on-chain", "Token market history, DeFi and on-chain flows", 400),
    "filings_disclosures": ("Filings & disclosures", "Official filings, governance and regulatory records", 500),
    "analysis_ready": ("Analysis-ready panels", "Joined, cleaned panels built in-house for direct use", 600),
    "lookups_ids": ("Lookups & identifiers", "Join keys, ticker maps and entity crosswalks", 700),
    "find_datasets": ("Dataset catalogues", "Browsable indexes of datasets the desk can reach", 800),
    "project_downloads": ("Project downloads", "One-off collections procured for a specific project", 900),
}


@lru_cache(maxsize=4)
def shelf_datasets(repo_root: str) -> dict[str, list[dict[str, Any]]]:
    """Professor-visible datasets grouped by ``shelf_hint``.

    Browsing is dataset-first, not partition-first, and the crypto shelf is why.
    ``markets.crypto-coingecko`` is an ops holding slot with
    ``professor_visible: false``, yet it carries 26 professor-visible crypto
    datasets. Navigating through partitions therefore hid the largest shelf on
    the desk entirely. Partitions are storage folders whose visibility is an
    operator concern; the dataset is what a researcher came for, and its own
    visibility flag is the one that should decide.
    """
    path = Path(repo_root).resolve() / "config/research_query_registry.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8")).get("datasets") or []
    except (OSError, ValueError):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("professor_visible"):
            continue
        hint = str(row.get("shelf_hint") or "").strip()
        if not hint:
            continue
        mat = row.get("materialization") or {}
        out.setdefault(hint, []).append(
            {
                "dataset_id": row.get("dataset_id"),
                "name": row.get("display_name") or row.get("name"),
                "one_line": row.get("one_line") or row.get("description"),
                "grain": row.get("grain"),
                "partition_id": row.get("partition_id"),
                "source_system": row.get("source_system"),
                "query_ready": bool(mat.get("query_ready")),
                "query_verified": bool(mat.get("query_verified")),
                "tags": list(row.get("tags") or [])[:6],
            }
        )
    for rows_ in out.values():
        # Queryable first: a researcher scanning a shelf should meet what they
        # can open now before what still needs procuring.
        rows_.sort(key=lambda r: (not r["query_ready"], str(r.get("name") or "")))
    return out


@lru_cache(maxsize=4)
def _shelves_from_registry(repo_root: str) -> list[dict[str, Any]]:
    """Derive shelves from the ``shelf_hint`` authored on every registry row.

    ``collection_partitions.json`` has no ``professor_nav`` block, so the
    endpoint advertised ``nav_mode: professor_shelves`` and returned zero
    shelves -- navigation that named itself and then wasn't there. The taxonomy
    was never missing, only stored elsewhere: each registry dataset carries a
    ``shelf_hint``. This reads that rather than inventing a second taxonomy to
    drift from it.
    """
    grouped = shelf_datasets(repo_root)
    shelves = []
    for hint, rows in grouped.items():
        label, blurb, sort = _SHELF_LABELS.get(
            hint, (hint.replace("_", " ").title(), "", 950)
        )
        shelves.append(
            {
                "id": hint,
                "label": label,
                "blurb": blurb,
                "sort": sort,
                "partition_ids": sorted({str(r["partition_id"]) for r in rows if r.get("partition_id")}),
                "dataset_count": len(rows),
                "query_ready_count": sum(1 for r in rows if r["query_ready"]),
                "derived_from": "registry_shelf_hint",
            }
        )
    return shelves


def professor_shelves(repo_root: Path) -> list[dict[str, Any]]:
    """Professor-facing shelf map (logical nav; physical paths unchanged)."""
    _load_partitions.cache_clear()
    _shelves_from_registry.cache_clear()
    cfg = _load_partitions(str(repo_root))
    nav = cfg.get("professor_nav") or {}
    if not (nav.get("shelves") or []):
        # No authored nav block; fall back to the registry's own taxonomy.
        derived = _shelves_from_registry(str(repo_root))
        derived.sort(key=lambda s: (s.get("sort", 500), s.get("label") or ""))
        return derived
    shelves = []
    for shelf in nav.get("shelves") or []:
        if shelf.get("professor_visible") is False:
            continue
        shelves.append(
            {
                "id": shelf.get("id"),
                "label": shelf.get("label"),
                "blurb": shelf.get("blurb"),
                "sort": shelf.get("sort", 500),
                "partition_ids": list(shelf.get("partition_ids") or []),
            }
        )
    shelves.sort(key=lambda s: (s.get("sort", 500), s.get("label") or ""))
    return shelves


def partition_lanes(repo_root: Path) -> list[dict[str, Any]]:
    # Config edits must win over process lifetime — drop stale cache.
    _load_partitions.cache_clear()
    _registry_holdings.cache_clear()
    _derived_shelf_index.cache_clear()
    cfg = _load_partitions(str(repo_root))
    shelf_by_pid = _shelf_index(cfg) or _derived_shelf_index(str(repo_root))
    lanes: list[dict[str, Any]] = []
    for part in cfg.get("partitions") or []:
        row = partition_lane(repo_root, part, shelf_by_pid=shelf_by_pid)
        if row:
            lanes.append(row)
    lanes.sort(
        key=lambda r: (
            int(r.get("professor_sort") or 500),
            r.get("shelf_label") or "",
            r.get("professor_label") or r.get("name") or "",
        )
    )
    return lanes
