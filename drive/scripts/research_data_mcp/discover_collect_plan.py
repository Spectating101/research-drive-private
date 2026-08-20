"""Resolve Discover catalog / rail IDs into a launchable collect plan.

Catalog connectors (e.g. ``twse``) are logical desk IDs. Procurement connectors
are probed ``src_*`` rows. When no bounded HTTP file manifest exists yet, fall
back to a ``source_probe`` plan so Discover Collect still creates a durable,
Discover-linked pending job in History — without inventing a harvest.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote, urlparse


def _https_url(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        return text
    # bare host / endpoint
    if "/" not in text and "." in text:
        return f"https://{text}"
    if text.startswith("//"):
        return f"https:{text}"
    return text


def _host_of(url_or_host: str) -> str:
    text = str(url_or_host or "").strip().lower()
    if not text:
        return ""
    if "://" not in text and "/" not in text:
        return text.removeprefix("www.")
    try:
        return (urlparse(_https_url(text)).hostname or "").lower().removeprefix("www.")
    except Exception:  # noqa: BLE001
        return ""


def _huggingface_dataset_id_from_url(value: str) -> str:
    """Return ``owner/name`` only for a concrete Hugging Face dataset URL.

    A Hub search result is a selected dataset, not the generic Hugging Face
    homepage.  Preserve that distinction all the way into the collection plan.
    """
    try:
        parsed = urlparse(_https_url(value))
    except Exception:  # noqa: BLE001
        return ""
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host != "huggingface.co":
        return ""
    parts = [unquote(part).strip() for part in (parsed.path or "").split("/") if part.strip()]
    if len(parts) < 3 or parts[0].lower() != "datasets":
        return ""
    owner, name = parts[1:3]
    if not owner or not name or owner in {"search", "viewer"}:
        return ""
    return f"{owner}/{name}"


_DOI_RE = re.compile(r"(?:https?://(?:dx\.)?doi\.org/|doi:\s*)?(10\.\d{4,9}/[^\s<>\"']+)", re.I)


def _doi_from_value(value: str) -> str:
    """Extract a canonical DOI from a selected candidate or its URL."""
    text = str(value or "").strip()
    if not text:
        return ""
    match = _DOI_RE.search(text)
    if not match:
        return ""
    return match.group(1).rstrip(".,;)/")


def _canonical_live_connector(*values: str) -> str:
    """Map display/provider names to the connector IDs used by collectors."""
    for raw in values:
        value = str(raw or "").strip().lower().replace("_", " ").replace("-", " ")
        if not value:
            continue
        if "hugging face" in value or value in {"hf", "huggingface"}:
            return "huggingface"
        if "data cite" in value or value == "datacite":
            return "datacite"
        if value == "zenodo" or "zenodo" in value:
            return "zenodo"
        if value == "openalex" or "open alex" in value:
            return "openalex"
    return ""


def _selected_doi_plan(
    *,
    repo_root: Any,
    doi: str,
    title: str,
    url: str,
    connector_id: str,
    source_id: str,
    candidate_key: str,
    catalog_connector_id: str,
) -> dict[str, Any] | None:
    """Resolve a selected DOI to the existing generic HTTP collector.

    Resolution is metadata-only: it discovers the repository file and builds a
    pending plan. No download, job submission, or registry mutation occurs here.
    """
    resolution_error = ""
    try:
        from scripts.research_data_mcp.doi_resolve_cache import resolve_doi_cached
        from scripts.research_data_mcp.datacite_repository import build_http_manifest_plan

        resolved = resolve_doi_cached(repo_root, doi)
        plan = dict(build_http_manifest_plan(resolved))
    except Exception as exc:  # noqa: BLE001 - preserve a durable unresolved handoff
        resolution_error = str(exc)
        plan = None
        # Zenodo's public record API is a valid repository resolver in its own
        # right. DataCite metadata can lag or reject a DOI even when the exact
        # record URL supplied by the model is downloadable.
        if _host_of(url) == "zenodo.org" and "/records/" in str(url):
            try:
                from scripts.research_data_mcp.datacite_repository import build_http_manifest_plan
                from scripts.research_data_mcp.repository_adapters import zenodo_files

                files = zenodo_files(url)
                if files:
                    plan = dict(
                        build_http_manifest_plan(
                            {
                                "doi": doi,
                                "title": title or doi,
                                "repository": "zenodo",
                                "landing_url": url,
                                "files": files,
                            }
                        )
                    )
            except Exception as zenodo_exc:  # noqa: BLE001
                resolution_error = f"{resolution_error}; zenodo: {zenodo_exc}"
        if plan is None:
            return {
                "title": title or f"Resolve DOI {doi}",
                "job_type": "source_probe",
                "url": url or f"https://doi.org/{doi}",
                "doi": doi,
                "datacite_doi": doi,
                "launchable": True,
                "requires_approval": True,
                "connector_id": connector_id or "datacite",
                "catalog_connector_id": catalog_connector_id or connector_id or "datacite",
                "source_id": source_id or connector_id or "datacite",
                "candidate_key": candidate_key,
                "collect_resolution": "doi_resolution_required",
                "collect_note": (
                    "Selected DOI is preserved, but repository-file resolution must complete "
                    f"before an HTTP manifest can be built: {resolution_error[:240]}"
                ),
            }
    plan.update(
        {
            "title": title or plan.get("title") or f"Collect DOI {doi}",
            "doi": doi,
            "datacite_doi": doi,
            "connector_id": connector_id or plan.get("connector_id") or "datacite",
            "catalog_connector_id": catalog_connector_id or connector_id or "datacite",
            "source_id": source_id or str(plan.get("datacite_repository") or connector_id or "datacite"),
            "candidate_key": candidate_key,
            "requires_approval": True,
            "collect_resolution": "datacite_selected_doi",
            "collect_note": (
                "Selected DOI resolved to a bounded repository file manifest. "
                "Approval is still required before download."
            ),
        }
    )
    return _stamp_public_collect_plan(plan)


def _direct_url_manifest_plan(
    *,
    url: str,
    title: str,
    connector_id: str,
    source_id: str,
    candidate_key: str,
    catalog_connector_id: str,
) -> dict[str, Any]:
    """Use the shared URL planner for concrete file/API candidates."""
    from scripts.research_data_mcp.scrape_plan import build_http_manifest_plan_for_url

    plan = dict(build_http_manifest_plan_for_url(url, title=title or "Discover direct download"))
    plan.update(
        {
            "connector_id": connector_id or catalog_connector_id,
            "catalog_connector_id": catalog_connector_id or connector_id,
            "source_id": source_id,
            "candidate_key": candidate_key,
            "requires_approval": True,
            "collect_resolution": "direct_machine_readable_url",
            "collect_note": (
                "Selected candidate is a concrete file/API URL; the generic HTTP "
                "manifest collector will fetch it after approval."
            ),
        }
    )
    return _stamp_public_collect_plan(plan)


def _huggingface_collect_plan(
    *,
    dataset_id: str,
    title: str,
    url: str,
    connector_id: str,
    source_id: str,
    candidate_key: str,
    catalog_connector_id: str,
) -> dict[str, Any]:
    """Plan the existing specialised collector for one selected Hub dataset."""
    return {
        "title": title or f"Collect Hugging Face {dataset_id}",
        "job_type": "huggingface_collect",
        "hf_dataset_id": dataset_id,
        "split": "train",
        "max_shards": 2,
        "partition_id": "acquired.procured",
        "launchable": True,
        "requires_approval": True,
        "timeout_seconds": 3600,
        "url": url,
        "connector_id": connector_id or "huggingface",
        "catalog_connector_id": catalog_connector_id or connector_id or "huggingface",
        "source_id": source_id or "huggingface",
        "candidate_key": candidate_key,
        "collect_resolution": "huggingface_selected_dataset",
        "collect_note": (
            "Selected Hugging Face dataset ID is preserved for the specialised "
            "collector; approval is still required before any download."
        ),
    }



_PUBLIC_GOV_HOSTS = frozenset(
    {
        "www.sec.gov",
        "sec.gov",
        "data.sec.gov",
        "www.data.gov",
        "data.gov",
        "openapi.twse.com.tw",
        "www.twse.com.tw",
        "mops.twse.com.tw",
        "api.worldbank.org",
        "databank.worldbank.org",
    }
)


def _stamp_public_collect_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Mark clearly public HTTP manifests so approve-safe policy can launch them."""
    if not isinstance(plan, dict):
        return plan
    if str(plan.get("job_type") or "") != "http_manifest":
        return plan
    urls: list[str] = []
    if plan.get("url"):
        urls.append(str(plan.get("url")))
    for item in plan.get("items") or []:
        if isinstance(item, dict) and item.get("url"):
            urls.append(str(item["url"]))
        elif isinstance(item, str):
            urls.append(item)
    hosts = {_host_of(u) for u in urls if u}
    hosts.discard("")
    if hosts and hosts <= _PUBLIC_GOV_HOSTS:
        plan = dict(plan)
        plan.setdefault("public_direct_url", True)
        plan.setdefault("collect_class", "public_government")
        plan.setdefault("requires_approval", True)  # still explicit unless auto-approve policy says otherwise
    return plan


# Curated official TWSE OpenAPI feeds for Discover refresh / collect.
# Portal root (Swagger UI) is NOT a dataset — never scrape it as the harvest.
TWSE_OPENAPI_REFRESH_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("daily_trading_all", "/exchangeReport/STOCK_DAY_ALL"),
    ("daily_close_month_avg", "/exchangeReport/STOCK_DAY_AVG_ALL"),
    ("valuation_ratios", "/exchangeReport/BWIBBU_ALL"),
    ("company_profile", "/opendata/t187ap03_L"),
    ("material_information_daily", "/opendata/t187ap04_L"),
    ("monthly_revenue", "/opendata/t187ap05_L"),
    ("twse_news", "/news/newsList"),
    ("twse_events", "/news/eventList"),
)


def _twse_openapi_manifest_plan(
    *,
    limit: int = 8,
    title: str = "",
    connector_id: str = "",
    source_id: str = "",
    candidate_key: str = "",
    catalog_connector_id: str = "",
) -> dict[str, Any]:
    base = "https://openapi.twse.com.tw/v1"
    n = min(max(int(limit or 8), 1), len(TWSE_OPENAPI_REFRESH_ENDPOINTS))
    items = [
        {
            "url": f"{base}{path}",
            "name": f"{name}.json",
            "dataset_key": name,
        }
        for name, path in TWSE_OPENAPI_REFRESH_ENDPOINTS[:n]
    ]
    label = title or source_id or "TWSE OpenAPI"
    title_out = title if str(title).lower().startswith("collect") else f"Collect {label}"
    plan: dict[str, Any] = {
        "title": title_out or f"Collect {label}",
        "job_type": "http_manifest",
        "items": items,
        "url": "https://openapi.twse.com.tw/v1",
        "launchable": True,
        "requires_approval": True,
        "public_direct_url": True,
        "collect_class": "public_government",
        "local_collect": True,
        "shards": 1,
        "per_node_workers": 2,
        "request_timeout": 90,
        "retries": 3,
        "delay_seconds": 0.35,
        "timeout_seconds": 1800,
        "connector_id": connector_id or catalog_connector_id,
        "catalog_connector_id": catalog_connector_id or connector_id,
        "source_id": source_id or "twse_official",
        "candidate_key": candidate_key,
        "collect_resolution": "twse_openapi_known_manifest",
        "collect_note": (
            "Official TWSE OpenAPI JSON feeds (bounded manifest). "
            "Not a Swagger UI page scrape."
        ),
    }
    return _stamp_public_collect_plan(plan)



SEC_EDGAR_REFRESH_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("company_tickers", "https://www.sec.gov/files/company_tickers.json"),
    ("company_tickers_exchange", "https://www.sec.gov/files/company_tickers_exchange.json"),
)

WORLDBANK_REFRESH_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("countries", "https://api.worldbank.org/v2/country?format=json&per_page=300"),
    ("indicators_sample", "https://api.worldbank.org/v2/indicator?format=json&per_page=100"),
)


def _sec_edgar_manifest_plan(
    *,
    limit: int = 2,
    title: str = "",
    connector_id: str = "",
    source_id: str = "",
    candidate_key: str = "",
    catalog_connector_id: str = "",
) -> dict[str, Any]:
    n = min(max(int(limit or 2), 1), len(SEC_EDGAR_REFRESH_ENDPOINTS))
    items = [
        {"url": url, "name": f"{name}.json", "dataset_key": name}
        for name, url in SEC_EDGAR_REFRESH_ENDPOINTS[:n]
    ]
    label = title or source_id or "SEC EDGAR"
    title_out = title if str(title).lower().startswith("collect") else f"Collect {label}"
    plan: dict[str, Any] = {
        "title": title_out,
        "job_type": "http_manifest",
        "items": items,
        "url": "https://www.sec.gov/files/company_tickers.json",
        "launchable": True,
        "requires_approval": True,
        "public_direct_url": True,
        "collect_class": "public_government",
        "local_collect": True,
        "shards": 1,
        "request_timeout": 90,
        "retries": 3,
        "delay_seconds": 0.4,
        "timeout_seconds": 1200,
        "connector_id": connector_id or catalog_connector_id,
        "catalog_connector_id": catalog_connector_id or connector_id,
        "source_id": source_id or "sec_edgar",
        "candidate_key": candidate_key,
        "collect_resolution": "sec_edgar_known_manifest",
        "collect_note": "Official SEC company ticker JSON feeds (bounded manifest).",
        "headers": {"User-Agent": "Sharpe-Renaissance research collector faculty@yzu.edu.tw"},
    }
    return _stamp_public_collect_plan(plan)


def _worldbank_manifest_plan(
    *,
    limit: int = 2,
    title: str = "",
    connector_id: str = "",
    source_id: str = "",
    candidate_key: str = "",
    catalog_connector_id: str = "",
) -> dict[str, Any]:
    n = min(max(int(limit or 2), 1), len(WORLDBANK_REFRESH_ENDPOINTS))
    items = [
        {"url": url, "name": f"{name}.json", "dataset_key": name}
        for name, url in WORLDBANK_REFRESH_ENDPOINTS[:n]
    ]
    label = title or source_id or "World Bank"
    title_out = title if str(title).lower().startswith("collect") else f"Collect {label}"
    plan: dict[str, Any] = {
        "title": title_out,
        "job_type": "http_manifest",
        "items": items,
        "url": "https://api.worldbank.org/v2/country?format=json",
        "launchable": True,
        "requires_approval": True,
        "public_direct_url": True,
        "collect_class": "public_government",
        "local_collect": True,
        "shards": 1,
        "request_timeout": 90,
        "retries": 3,
        "delay_seconds": 0.3,
        "timeout_seconds": 1200,
        "connector_id": connector_id or catalog_connector_id,
        "catalog_connector_id": catalog_connector_id or connector_id,
        "source_id": source_id or "worldbank",
        "candidate_key": candidate_key,
        "collect_resolution": "worldbank_known_manifest",
        "collect_note": "World Bank API JSON feeds (bounded manifest).",
    }
    return _stamp_public_collect_plan(plan)


def _known_source_manifest_plan(
    *,
    source_id: str = "",
    connector_id: str = "",
    catalog: dict[str, Any] | None = None,
    url: str = "",
    limit: int = 8,
    title: str = "",
    candidate_key: str = "",
) -> dict[str, Any] | None:
    """Bounded http_manifest for well-known public APIs when probe manifests are empty."""
    catalog = catalog or {}
    sid = str(source_id or catalog.get("source_id") or "").strip().lower()
    cid = str(connector_id or catalog.get("connector_id") or catalog.get("desk_connector_id") or "").strip().lower()
    host = _host_of(url) or _host_of(str(catalog.get("endpoint") or catalog.get("url") or ""))
    if host.startswith("mops."):
        return None
    twse_hit = (
        sid in {"twse_official", "twse", "twse_openapi"}
        or cid in {"twse", "twse_openapi"}
        or host in {"openapi.twse.com.tw", "www.twse.com.tw"}
        or sid.startswith("twse_")
    )
    if twse_hit:
        return _twse_openapi_manifest_plan(
            limit=limit,
            title=title or str(catalog.get("title") or "TWSE OpenAPI"),
            connector_id=connector_id,
            source_id=source_id or str(catalog.get("source_id") or "twse_official"),
            candidate_key=candidate_key,
            catalog_connector_id=str(catalog.get("connector_id") or connector_id or "twse"),
        )

    sec_hit = (
        sid in {"sec_edgar", "sec", "sec_company_tickers", "edgar"}
        or cid in {"sec", "sec_edgar", "edgar"}
        or host in {"www.sec.gov", "sec.gov", "data.sec.gov"}
        or "sec" in sid
        or "edgar" in sid
    )
    if sec_hit and not host.startswith("mops."):
        return _sec_edgar_manifest_plan(
            limit=min(limit, 2),
            title=title or str(catalog.get("title") or "SEC EDGAR"),
            connector_id=connector_id,
            source_id=source_id or str(catalog.get("source_id") or "sec_edgar"),
            candidate_key=candidate_key,
            catalog_connector_id=str(catalog.get("connector_id") or connector_id or "sec_edgar"),
        )

    wb_hit = (
        sid in {"worldbank", "world_bank", "wb_api"}
        or cid in {"worldbank", "world_bank"}
        or host in {"api.worldbank.org", "databank.worldbank.org", "data.worldbank.org"}
        or "worldbank" in sid
        or "world_bank" in sid
    )
    if wb_hit:
        return _worldbank_manifest_plan(
            limit=min(limit, 2),
            title=title or str(catalog.get("title") or "World Bank"),
            connector_id=connector_id,
            source_id=source_id or str(catalog.get("source_id") or "worldbank"),
            candidate_key=candidate_key,
            catalog_connector_id=str(catalog.get("connector_id") or connector_id or "worldbank"),
        )
    return None


def _lookup_catalog_source(repo_root: Any, *, connector_id: str = "", source_id: str = "") -> dict[str, Any]:
    from pathlib import Path

    from scripts.research_data_mcp.discover_source_search import search_discover_sources

    root = Path(repo_root)
    needles: list[str] = []
    for raw in (source_id, connector_id):
        token = str(raw or "").strip()
        if token and token not in needles:
            needles.append(token)
    if not needles:
        return {}
    for needle in needles:
        payload = search_discover_sources(root, needle, limit=12)
        for row in payload.get("results") or []:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("source_id") or "").strip()
            cid = str(row.get("connector_id") or row.get("desk_connector_id") or "").strip()
            if source_id and sid == source_id:
                return row
            if connector_id and cid == connector_id:
                return row
            if needle in {sid, cid}:
                return row
    return {}


def _match_procurement_id(store: Any, *, host: str = "", url: str = "") -> str:
    want_host = _host_of(host) or _host_of(url)
    want_url = _https_url(url).rstrip("/")
    if not want_host and not want_url:
        return ""
    try:
        rows = store.list() or []
    except Exception:  # noqa: BLE001
        return ""
    # Prefer approved with matching host, then any host match.
    ranked: list[tuple[int, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("id") or row.get("connector_id") or "").strip()
        if not cid:
            continue
        spec = row.get("spec") if isinstance(row.get("spec"), dict) else {}
        row_url = str(row.get("source_url") or spec.get("source_url") or "").rstrip("/")
        row_host = str(spec.get("host") or _host_of(row_url) or "").lower().removeprefix("www.")
        score = 0
        if want_url and row_url and want_url == row_url:
            score += 40
        if want_host and row_host and want_host == row_host:
            score += 20
        if want_host and row_url and want_host in row_url.lower():
            score += 10
        if score <= 0:
            continue
        if str(row.get("status") or "") == "approved":
            score += 5
        ranked.append((score, cid))
    if not ranked:
        return ""
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ranked[0][1]


def _probe_fallback_plan(
    *,
    url: str,
    title: str,
    connector_id: str,
    source_id: str,
    candidate_key: str,
    catalog_connector_id: str,
    prefer_browser: bool = True,
) -> dict[str, Any]:
    """When catalog has no file manifest: browser scrape (Spectator/windows_lab) or probe."""
    probe_url = _https_url(url)
    label = title or source_id or catalog_connector_id or connector_id or "Discover source"
    # Site roots / OpenAPI portals need Playwright — not a fake file harvest.
    path = ""
    try:
        from urllib.parse import urlparse
        path = (urlparse(probe_url).path or "").rstrip("/")
    except Exception:  # noqa: BLE001
        path = ""
    looks_like_portal = prefer_browser and probe_url.startswith("http") and (
        not path or path in {"", "/"} or path.endswith((".html", ".htm", "/openapi", "/api"))
        or "openapi." in probe_url
        or "mops." in probe_url
    )
    if looks_like_portal:
        return {
            "title": f"Discover scrape · {label}",
            "job_type": "scraper_run",
            "script_key": "generic_url_scrape",
            "url": probe_url,
            "scrape_mode": "page",
            "launchable": True,
            "requires_approval": True,
            "agent_initiated": True,
            "timeout_seconds": 1800,
            "connector_id": connector_id or catalog_connector_id,
            "catalog_connector_id": catalog_connector_id or connector_id,
            "source_id": source_id,
            "candidate_key": candidate_key,
            "collect_resolution": "catalog_browser_scrape_fallback",
            "collect_note": (
                "No bounded HTTP file manifest; queued Spectator generic_url_scrape "
                "on windows_lab (Discover-linked)."
            ),
            "pool_hint": "windows_lab",
        }
    return {
        "title": f"Discover collect · {label}",
        "job_type": "source_probe",
        "url": probe_url,
        "launchable": True,
        "requires_approval": True,
        "connector_id": connector_id or catalog_connector_id,
        "catalog_connector_id": catalog_connector_id or connector_id,
        "source_id": source_id,
        "candidate_key": candidate_key,
        "collect_resolution": "catalog_source_probe_fallback",
        "collect_note": (
            "Catalog connector has no bounded file manifest yet; "
            "queued as source_probe pending approval (Discover-linked)."
        ),
    }


def resolve_discover_collect_plan(
    procurement: Any,
    repo_root: Any,
    *,
    connector_id: str = "",
    source_id: str = "",
    limit: int = 200,
    title: str = "",
    url: str = "",
    candidate_key: str = "",
    doi: str = "",
    external_id: str = "",
    provider: str = "",
    kind: str = "",
    dataset_id: str = "",
) -> dict[str, Any]:
    """Build a plan for an explicit model-selected Discover candidate.

    The resolver never chooses a candidate or substitutes another result. It only
    validates the identity supplied by the model/UI and routes it to an existing
    acquisition mechanism.

    Resolution order:
    1. A concrete Hugging Face dataset URL
    2. A DOI selected from DataCite/Zenodo/OpenAlex, resolved to a repository file
    3. A direct machine-readable URL
    4. Procurement ``src_*`` (or any store id) with a bounded file manifest
    5. Catalog source → matched procurement connector by host/URL
    6. Catalog / payload URL → ``source_probe`` fallback (still Discover-linked)
    """
    cid = str(connector_id or "").strip()
    sid = str(source_id or "").strip()
    limit_n = min(max(int(limit or 200), 1), 2000)
    title_s = str(title or "").strip()
    url_s = _https_url(url)
    ck = str(candidate_key or "").strip()
    doi_s = _doi_from_value(doi) or _doi_from_value(external_id) or _doi_from_value(url_s)
    provider_s = str(provider or "").strip()
    kind_s = str(kind or "").strip().lower()
    canonical_cid = _canonical_live_connector(cid, sid, provider_s)

    hf_dataset_id = _huggingface_dataset_id_from_url(url_s)
    if not hf_dataset_id and canonical_cid == "huggingface" and "/" in str(dataset_id or ""):
        hf_dataset_id = str(dataset_id).strip().strip("/")
    if hf_dataset_id and (
        canonical_cid == "huggingface"
        or cid.lower() in {"", "huggingface"}
        or sid.lower() in {"", "huggingface"}
    ):
        return _huggingface_collect_plan(
            dataset_id=hf_dataset_id,
            title=title_s,
            url=url_s,
            connector_id=cid or "huggingface",
            source_id=sid or "huggingface",
            candidate_key=ck,
            catalog_connector_id=cid or "huggingface",
        )

    # DOI is an explicit identity, not a search instruction. Zenodo and
    # DataCite records share this repository-resolution path.
    if doi_s and (canonical_cid in {"", "datacite", "zenodo", "openalex"} or kind_s == "live_candidate"):
        doi_plan = _selected_doi_plan(
            repo_root=repo_root,
            doi=doi_s,
            title=title_s,
            url=url_s,
            connector_id=canonical_cid or cid,
            source_id=sid,
            candidate_key=ck,
            catalog_connector_id=cid or canonical_cid,
        )
        if doi_plan:
            return doi_plan

    # A concrete URL is already the model's choice. Only classify its fetch
    # shape; never replace it with a provider homepage or catalog root.
    if url_s and (kind_s == "live_candidate" or (not cid and not sid)):
        from scripts.research_data_mcp.scrape_plan import classify_url

        if classify_url(url_s) == "direct_http":
            return _direct_url_manifest_plan(
                url=url_s,
                title=title_s,
                connector_id=cid or canonical_cid,
                source_id=sid,
                candidate_key=ck,
                catalog_connector_id=cid or canonical_cid,
            )

    errors: list[str] = []

    def try_manifest(pid: str) -> dict[str, Any] | None:
        if not pid:
            return None
        try:
            plan = dict(procurement.manifest_plan_from_connector(pid, limit=limit_n))
            plan.setdefault("connector_id", pid)
            plan["collect_resolution"] = "procurement_manifest"
            if title_s:
                plan["title"] = title_s if title_s.lower().startswith("collect") else f"Collect {title_s}"
            if sid:
                plan["source_id"] = sid
            if ck:
                plan["candidate_key"] = ck
            if cid and cid != pid:
                plan["catalog_connector_id"] = cid
            return _stamp_public_collect_plan(plan)
        except KeyError as exc:
            errors.append(f"procurement_missing:{exc}")
            return None
        except ValueError as exc:
            errors.append(f"procurement_unusable:{exc}")
            return None

    # 4) Direct procurement / store id when provided
    if cid:
        plan = try_manifest(cid)
        if plan:
            return _stamp_public_collect_plan(plan)

    catalog = _lookup_catalog_source(repo_root, connector_id=cid, source_id=sid)
    catalog_cid = str(catalog.get("connector_id") or catalog.get("desk_connector_id") or cid).strip()
    catalog_sid = str(catalog.get("source_id") or sid).strip()
    catalog_title = title_s or str(catalog.get("title") or catalog.get("label") or "").strip()
    catalog_endpoint = str(catalog.get("endpoint") or "").strip()
    catalog_url = url_s or _https_url(catalog_endpoint) or _https_url(str(catalog.get("url") or catalog.get("source_url") or ""))
    if not ck:
        ck = str(catalog.get("candidate_key") or "").strip()

    matched = _match_procurement_id(
        getattr(procurement, "store", None),
        host=catalog_endpoint,
        url=catalog_url,
    )
    if matched:
        plan = try_manifest(matched)
        if plan:
            plan["catalog_connector_id"] = catalog_cid or cid
            plan["source_id"] = catalog_sid or sid
            if ck:
                plan["candidate_key"] = ck
            if catalog_title and not plan.get("title"):
                plan["title"] = f"Collect {catalog_title}"
            return _stamp_public_collect_plan(plan)

    # 5) Known public API manifests (TWSE OpenAPI JSON feeds, etc.)
    known = _known_source_manifest_plan(
        source_id=catalog_sid or sid,
        connector_id=matched or cid or catalog_cid,
        catalog=catalog,
        url=catalog_url or url_s,
        limit=min(limit_n, 8),
        title=catalog_title or title_s,
        candidate_key=ck,
    )
    if known:
        return known

    # 6) Probe / scrape fallback — durable History row without inventing harvest files
    if catalog_url:
        return _probe_fallback_plan(
            url=catalog_url,
            title=catalog_title,
            connector_id=matched or cid or catalog_cid,
            source_id=catalog_sid or sid,
            candidate_key=ck,
            catalog_connector_id=catalog_cid or cid,
        )

    if url_s:
        return _probe_fallback_plan(
            url=url_s,
            title=catalog_title or title_s,
            connector_id=cid,
            source_id=sid,
            candidate_key=ck,
            catalog_connector_id=cid,
        )

    detail = "; ".join(errors[:4]) if errors else "no catalog endpoint or procurement manifest"
    raise KeyError(cid or sid or f"unresolvable_collect ({detail})")
