#!/usr/bin/env python3
"""URL collect planning — HTTP-first (manifest) before browser scrape."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlparse

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)

_DIRECT_EXTENSIONS = (
    ".json",
    ".csv",
    ".tsv",
    ".xml",
    ".zip",
    ".gz",
    ".pdf",
    ".parquet",
    ".feather",
    ".ndjson",
    ".geojson",
    ".txt",
    ".dat",
    ".xlsx",
    ".xls",
)

_DIRECT_PATH_MARKERS = (
    "/files/",
    "/content",
    "/download",
    "/api/records/",
    "/raw/",
    "/static/",
)

_PUBLIC_HOST_SUFFIXES = (
    ".gov",
    ".edu",
    "zenodo.org",
    "data.gov",
    "europa.eu",
    "worldbank.org",
    "fred.stlouisfed.org",
)


def extract_urls(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;)'\"]")
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _host_blob(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.netloc or "").lower()


def is_public_host(url: str) -> bool:
    host = _host_blob(url)
    if not host:
        return False
    if host.endswith(".gov") or host == "gov.uk":
        return True
    return any(host == suffix or host.endswith(f".{suffix}") or host.endswith(suffix) for suffix in _PUBLIC_HOST_SUFFIXES)


def _looks_like_json_api(url: str) -> bool:
    """Heuristic: host/path/query that usually answer with JSON over plain GET."""
    parsed = urlparse(url.strip())
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    query = (parsed.query or "").lower()
    if host.startswith("api.") or host.startswith("api-") or ".api." in host:
        return True
    if "/api/" in path or path.startswith("/api") or "/v1/" in path or "/v2/" in path or "/v3/" in path:
        return True
    if any(tok in query for tok in ("format=json", "output=json", "per-page=", "per_page=", "includeprices")):
        return True
    if path.endswith(".geojson") or path.endswith("/json"):
        return True
    return False


def classify_url(url: str) -> str:
    """Return ``direct_http`` when a plain GET should work; else ``browser``."""
    url = url.strip()
    if not url.startswith("http"):
        return "browser"
    parsed = urlparse(url)
    path = (parsed.path or "").lower()
    query = (parsed.query or "").lower()
    if any(path.endswith(ext) for ext in _DIRECT_EXTENSIONS):
        return "direct_http"
    if any(marker in path for marker in _DIRECT_PATH_MARKERS):
        return "direct_http"
    if path.endswith("/json") or "format=json" in query or "output=json" in query:
        return "direct_http"
    if _looks_like_json_api(url):
        return "direct_http"
    if is_public_host(url) and any(ext in path for ext in (".json", ".csv", ".xml", ".zip", ".pdf", ".geojson")):
        return "direct_http"
    return "browser"


def suggest_filename(url: str) -> str:
    parsed = urlparse(url)
    name = (parsed.path or "").rstrip("/").split("/")[-1] or "download.bin"
    if "?" in name:
        name = name.split("?", 1)[0]
    if not name or name in {".", ".."}:
        digest = hashlib.sha1(url.encode()).hexdigest()[:10]
        return f"download_{digest}.json" if _looks_like_json_api(url) else f"download_{digest}.bin"
    if "." not in name and _looks_like_json_api(url):
        name = f"{name}.json"
    return name[:180]


def _procured_slug(url: str) -> str:
    host = _host_blob(url).replace(".", "_")[:40] or "url"
    digest = hashlib.sha1(url.encode()).hexdigest()[:10]
    return f"{host}_{digest}"


def build_http_manifest_plan_for_url(
    url: str,
    *,
    title: str = "",
    timeout_seconds: int = 900,
) -> dict[str, Any]:
    url = url.strip()
    host = urlparse(url).netloc or url[:40]
    filename = suggest_filename(url)
    public = is_public_host(url)
    return {
        "title": title or f"Download {host}",
        "job_type": "http_manifest",
        "url": url,
        "items": [{"url": url, "filename": filename}],
        "destination": f"data_lake/procured/url_{_procured_slug(url)}",
        "launchable": True,
        "timeout_seconds": timeout_seconds,
        "public_direct_url": public or classify_url(url) == "direct_http",
        "local_collect": True,
        "collect_class": "public_government" if public else "public_unknown",
    }


def build_generic_scrape_plan(
    url: str,
    *,
    mode: str = "page",
    title: str = "",
    timeout_seconds: int = 3600,
    catalog_max_pages: int | None = None,
    catalog_max_tokens: int | None = None,
    catalog_pause_ms: int | None = None,
    agent_initiated: bool = False,
) -> dict[str, Any]:
    """Playwright scrape — pool order from spectator_engine (optiplex before windows_lab)."""
    url = url.strip()
    host = urlparse(url).netloc or url[:40]
    plan: dict[str, Any] = {
        "title": title or f"Scrape {host}",
        "job_type": "scraper_run",
        "script_key": "generic_url_scrape",
        "url": url,
        "scrape_mode": mode,
        "launchable": True,
        "timeout_seconds": timeout_seconds,
    }
    if mode == "catalog":
        plan["timeout_seconds"] = max(timeout_seconds, 7200)
        if catalog_max_pages is not None:
            plan["catalog_max_pages"] = int(catalog_max_pages)
        if catalog_max_tokens is not None:
            plan["catalog_max_tokens"] = int(catalog_max_tokens)
        if catalog_pause_ms is not None:
            plan["catalog_pause_ms"] = int(catalog_pause_ms)
    if agent_initiated:
        plan["agent_initiated"] = True
    return plan


def plan_for_url(
    url: str,
    *,
    mode: str = "",
    title: str = "",
) -> dict[str, Any]:
    """Pick the strongest collect plan for a URL (HTTP manifest before browser)."""
    if classify_url(url) == "direct_http":
        return build_http_manifest_plan_for_url(url, title=title)
    scrape_mode = mode or infer_scrape_mode(url)
    return build_generic_scrape_plan(url, mode=scrape_mode, title=title)


def probe_spec(probe: dict[str, Any] | None) -> dict[str, Any]:
    if not probe:
        return {}
    connector = probe.get("connector") or {}
    if isinstance(connector, dict) and isinstance(connector.get("spec"), dict):
        return dict(connector["spec"])
    if isinstance(probe.get("spec"), dict):
        return dict(probe["spec"])
    return {}


def apply_probe_catalog_hints(plan: dict[str, Any], probe: dict[str, Any] | None) -> dict[str, Any]:
    """Upgrade to catalog crawl when probe reports paginated HTML catalog (structured only)."""
    if str(plan.get("scrape_mode") or "") == "catalog" and str(plan.get("job_type") or "") == "scraper_run":
        return plan
    spec = probe_spec(probe)
    pagination = spec.get("pagination") if isinstance(spec.get("pagination"), dict) else {}
    if not pagination.get("detected"):
        return plan
    if str(spec.get("access_mode") or "") != "html_catalog":
        return plan
    url = str(plan.get("url") or "").strip()
    if not url.startswith("http"):
        return plan
    return build_generic_scrape_plan(
        url,
        mode="catalog",
        title=str(plan.get("title") or f"Catalog scrape {urlparse(url).netloc}"),
        catalog_max_pages=int(plan.get("catalog_max_pages") or 2),
        catalog_max_tokens=int(plan.get("catalog_max_tokens") or 5),
        catalog_pause_ms=int(plan.get("catalog_pause_ms") or 350),
        agent_initiated=bool(plan.get("agent_initiated")),
    )


_LISTING_HINTS = (
    "/search",
    "?q=",
    "dataset",
    "catalog",
    "browse",
    "zenodo.org",
    "data.gov",
    "opendata",
    "records?",
    "/datasets",
    "figshare.com",
    "dryad",
)


def infer_scrape_mode(url: str) -> str:
    """Listing/search/SPA portals need full page extract — not datasets-only filter."""
    u = (url or "").lower()
    if classify_url(url) == "direct_http":
        return "page"
    if any(hint in u for hint in _LISTING_HINTS):
        return "page"
    return "page"


def candidate_from_url(url: str, index: int, *, score: float = 3.0) -> dict[str, Any]:
    host = urlparse(url).netloc
    kind = classify_url(url)
    if kind == "direct_http":
        return {
            "index": index,
            "kind": "web_url",
            "title": f"Direct download: {host}",
            "doi": "",
            "dataset_id": "",
            "url": url,
            "handle": "",
            "source": "url",
            "can_collect": True,
            "collect_via": "http_manifest",
            "script_key": "",
            "badges": ["Direct HTTP", "No browser", "optiplex"],
            "status": "runnable",
            "score": score + 0.5,
        }
    return {
        "index": index,
        "kind": "web_url",
        "title": f"Browser scrape: {host}",
        "doi": "",
        "dataset_id": "",
        "url": url,
        "handle": "",
        "source": "url",
        "can_collect": True,
        "collect_via": "web_scrape",
        "script_key": "generic_url_scrape",
        "badges": ["Playwright", "optiplex first"],
        "status": "runnable",
        "score": score,
    }
