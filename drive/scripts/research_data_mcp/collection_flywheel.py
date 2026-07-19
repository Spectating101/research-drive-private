#!/usr/bin/env python3
"""Post-collect flywheel — registry → curated index → locators → search FTS."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{2,}")
DOI_PREFIX_RE = re.compile(r"^doi:\s*", re.I)

CURATED_LIVE = "data_lake/dataset_catalog/curated_live"
CATALOG_LOCATORS = "data_lake/collection/_index/catalog/locators.json"
FLYWHEEL_KEYS = "flywheel_keys.json"

DOMAIN_HINTS: tuple[tuple[frozenset[str], str], ...] = (
    (frozenset({"election", "polling", "survey", "vote"}), "social_web"),
    (frozenset({"climate", "temperature", "calibration", "fair"}), "climate_geo"),
    (frozenset({"taiwan", "twse", "taipei"}), "asia_markets"),
    (frozenset({"crypto", "bitcoin", "ethereum", "nft"}), "crypto_finance"),
    (frozenset({"news", "gdelt", "headline"}), "news_media"),
    (frozenset({"sec", "edgar", "filing"}), "finance_economics"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_doi(raw: str) -> str:
    text = DOI_PREFIX_RE.sub("", str(raw or "").strip())
    return text.removeprefix("https://doi.org/").strip()


def _stable_key(row: dict[str, Any]) -> str:
    doi = _normalize_doi(str(row.get("doi") or row.get("dataset_id") or ""))
    if doi.startswith("10."):
        return f"doi:{doi.lower()}"
    did = str(row.get("dataset_id") or "").strip().lower()
    if did:
        return f"id:{did}"
    url = str(row.get("url") or "").strip().lower()
    if url:
        return f"url:{url}"
    title = str(row.get("title") or row.get("name") or "").strip().lower()
    return f"title:{title[:120]}"


def _goal_tags(goal: str) -> list[str]:
    return list(dict.fromkeys(TOKEN_RE.findall(goal.lower())))[:16]


def _infer_domain(*blobs: str) -> str:
    words = set(TOKEN_RE.findall(" ".join(blobs).lower()))
    for hints, domain in DOMAIN_HINTS:
        if words & hints:
            return domain
    return "acquired"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class CollectionFlywheel:
    """Promote successful collects into curated catalog + locators + collection FTS."""

    def __init__(self, repo_root: Path, registry_path: Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.registry_path = Path(registry_path).resolve()

    def curated_live_dir(self) -> Path:
        return self.repo_root / CURATED_LIVE

    def curated_jsonl(self) -> Path:
        return self.curated_live_dir() / "curated_dataset_index.jsonl"

    def keys_path(self) -> Path:
        return self.curated_live_dir() / FLYWHEEL_KEYS

    def _load_keys(self) -> set[str]:
        doc = _load_json(self.keys_path())
        return {str(k) for k in (doc.get("keys") or [])}

    def _save_keys(self, keys: set[str]) -> None:
        _write_json(
            self.keys_path(),
            {"version": 1, "updated_at": _now(), "keys": sorted(keys)},
        )

    def _registry_row(self, dataset_id: str) -> dict[str, Any] | None:
        reg = _load_json(self.registry_path)
        for row in reg.get("datasets") or []:
            if str(row.get("dataset_id") or "") == dataset_id:
                return dict(row)
        return None

    def _curated_row_from_sources(
        self,
        *,
        registry_row: dict[str, Any],
        job: dict[str, Any],
        promoted: dict[str, Any],
        search_goal: str = "",
        campaign_id: str = "",
    ) -> dict[str, Any] | None:
        plan = job.get("plan") or {}
        result = job.get("result") or {}
        materialized = result.get("materialized") or {}

        doi = _normalize_doi(
            str(plan.get("datacite_doi") or registry_row.get("doi") or "")
        )
        dataset_id = str(registry_row.get("dataset_id") or promoted.get("dataset_id") or "")
        title = str(
            registry_row.get("name")
            or plan.get("title")
            or job.get("title")
            or dataset_id
        )[:500]
        if not title:
            return None

        local_path = str(registry_row.get("local_path") or materialized.get("canonical_dir") or "")
        readiness = str(registry_row.get("analysis_readiness") or "metadata_search")
        instant = readiness == "instant" or bool(local_path and Path(self.repo_root / local_path.split("*")[0]).is_file())

        goal = search_goal.strip()
        tags = list(registry_row.get("tags") or registry_row.get("keywords") or [])
        tags.extend(_goal_tags(goal))
        tags = list(dict.fromkeys(t for t in tags if t))[:20]

        domain = str(registry_row.get("domain") or _infer_domain(goal, title, registry_row.get("description") or ""))
        description = str(registry_row.get("description") or registry_row.get("recommended_use") or "")
        if goal and goal.lower() not in description.lower():
            description = f"{description} Sourced for: {goal[:240]}.".strip()

        url = str(plan.get("url") or "")
        if doi and not url:
            url = f"https://doi.org/{doi}"

        curated_id = f"doi:{doi}" if doi else dataset_id
        tier = "tier_4_priority_probe" if instant else "tier_3_research_candidate"
        score = 18 if instant else 14

        return {
            "curated_at": _now(),
            "promotion_score": score,
            "promotion_tier": tier,
            "promotion_reasons": ["procurement_collect", "bytes_on_disk" if instant else "registry_promoted"],
            "source": "datacite" if doi else str(registry_row.get("domain") or "procured"),
            "source_kind": "procured",
            "dataset_id": curated_id,
            "doi": doi,
            "title": title,
            "description": description[:4000],
            "url": url,
            "tags": tags,
            "domain": domain,
            "access_mode": "query_now" if instant else "sample_probe",
            "analysis_readiness": readiness,
            "local_path": local_path,
            "procurement": {
                "job_id": str(job.get("id") or ""),
                "campaign_id": campaign_id,
                "search_goal": goal[:500],
                "promoted_at": promoted.get("promoted_at"),
                "registry_dataset_id": dataset_id,
            },
        }

    def append_curated_row(self, row: dict[str, Any]) -> bool:
        key = _stable_key(row)
        keys = self._load_keys()
        if key in keys:
            return False
        live = self.curated_live_dir()
        live.mkdir(parents=True, exist_ok=True)
        jsonl = self.curated_jsonl()
        with jsonl.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        keys.add(key)
        self._save_keys(keys)
        return True

    def append_locator(self, row: dict[str, Any], *, registry_row: dict[str, Any] | None = None) -> bool:
        doi = _normalize_doi(str(row.get("doi") or row.get("dataset_id") or ""))
        reg = registry_row or {}
        dataset_id = str(reg.get("dataset_id") or row.get("dataset_id") or "")
        domain = str(reg.get("domain") or row.get("domain") or "")

        local_path = str(row.get("local_path") or reg.get("local_path") or "")
        on_disk = bool(local_path) and not local_path.endswith("*")
        if on_disk:
            full = self.repo_root / local_path
            on_disk = full.is_file() or (full.is_dir() and any(full.iterdir()) if full.is_dir() else False)

        if doi.startswith("10."):
            locator_id = f"doi:{doi}"
            tracker = "tracker:datacite_api_get"
            handle = f"dataset:{dataset_id}" if dataset_id else f"doi:{doi}"
            say = f"preview dataset:{dataset_id}" if on_disk and dataset_id else f"collect DOI {doi}"
        elif domain == "web_scrape" and dataset_id:
            locator_id = f"scrape:{dataset_id}"
            tracker = "tracker:scrape_snapshot"
            handle = f"dataset:{dataset_id}"
            say = f"preview dataset:{dataset_id}" if on_disk else f"open dataset:{dataset_id}"
            doi = ""
        elif dataset_id:
            locator_id = f"dataset:{dataset_id}"
            tracker = "tracker:registry_dataset"
            handle = f"dataset:{dataset_id}"
            say = f"query dataset:{dataset_id}" if on_disk else f"refresh dataset:{dataset_id}"
            doi = ""
        else:
            return False

        path = self.repo_root / CATALOG_LOCATORS
        doc = _load_json(path)
        locators: list[dict[str, Any]] = list(doc.get("locators") or [])
        if any(str(loc.get("locator_id") or "") == locator_id for loc in locators):
            return False
        if doi and any(_normalize_doi(str(loc.get("doi") or "")).lower() == doi.lower() for loc in locators):
            return False

        locators.append(
            {
                "locator_id": locator_id,
                "doi": doi or None,
                "title": row.get("title"),
                "in_vault": bool(doi),
                "on_disk": on_disk,
                "tracker": tracker,
                "handle": handle,
                "say": say,
                "source": "flywheel",
                "domain": domain or ("datacite" if doi else "web_scrape"),
                "search_goal": (row.get("procurement") or {}).get("search_goal"),
                "promoted_at": _now(),
            }
        )
        doc["locator_count"] = len(locators)
        doc["version"] = doc.get("version") or 2
        doc["locators"] = locators
        _write_json(path, doc)
        self._patch_catalog_index_summary(len(locators))
        return True

    def _patch_catalog_index_summary(self, locator_count: int) -> None:
        index_path = self.repo_root / "data_lake/collection/_index/catalog/INDEX.json"
        doc = _load_json(index_path)
        if not doc:
            return
        summary = dict(doc.get("summary") or {})
        summary["locators"] = locator_count
        doc["summary"] = summary
        doc["built_at"] = _now()
        _write_json(index_path, doc)

    def rebuild_search_index(self) -> dict[str, Any] | None:
        try:
            from scripts.research_data_mcp.collection_index import build_index

            return build_index(self.repo_root)
        except Exception:
            return None

    def _clear_prefetch_caches(self) -> None:
        try:
            from scripts.research_data_mcp.datacite_prefetch import _load_locator_dois

            _load_locator_dois.cache_clear()
        except Exception:
            pass

    def promote_after_collect(
        self,
        job: dict[str, Any],
        registry_promoted: list[dict[str, Any]],
        *,
        campaign_id: str = "",
        search_goal: str = "",
        rebuild_index: bool | None = None,
    ) -> dict[str, Any]:
        """Append curated + locator rows for each registry promotion; refresh FTS."""
        if job.get("status") != "completed" or not registry_promoted:
            return {"curated_added": 0, "locators_added": 0, "index_rebuilt": False}

        from scripts.research_data_mcp.magic_config import load_magic_config

        fly_cfg = load_magic_config(self.repo_root).get("flywheel") or {}
        if fly_cfg.get("auto_promote_curated") is False:
            return {"curated_added": 0, "locators_added": 0, "index_rebuilt": False, "skipped": True}
        if rebuild_index is None:
            rebuild_index = bool(fly_cfg.get("rebuild_search_index", True))

        curated_added = 0
        locators_added = 0
        curated_rows: list[dict[str, Any]] = []

        for promo in registry_promoted:
            dataset_id = str(promo.get("dataset_id") or "")
            if not dataset_id:
                continue
            registry_row = self._registry_row(dataset_id)
            if not registry_row:
                continue
            row = self._curated_row_from_sources(
                registry_row=registry_row,
                job=job,
                promoted=promo,
                search_goal=search_goal,
                campaign_id=campaign_id,
            )
            if not row:
                continue
            if self.append_curated_row(row):
                curated_added += 1
                curated_rows.append(row)
            if self.append_locator(row, registry_row=registry_row):
                locators_added += 1

        index_stats = None
        if rebuild_index and (curated_added or locators_added):
            index_stats = self.rebuild_search_index()
            self._clear_prefetch_caches()
            try:
                from scripts.data_catalog.build_curated_topic_fts import build_curated_topic_fts

                build_curated_topic_fts(self.repo_root)
            except Exception:
                pass

        return {
            "curated_added": curated_added,
            "locators_added": locators_added,
            "index_rebuilt": bool(index_stats),
            "index_item_count": (index_stats or {}).get("item_count"),
            "curated_rows": [{"doi": r.get("doi"), "title": r.get("title")} for r in curated_rows],
        }
