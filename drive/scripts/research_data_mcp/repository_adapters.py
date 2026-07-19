#!/usr/bin/env python3
"""Repository adapters — resolve landing pages to downloadable file manifests."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any, Callable
from urllib.parse import urlparse

DEFAULT_MAX_FILE_BYTES = 50_000_000
USER_AGENT = "ResearchDrive/1.0"


def _fetch_json(url: str, *, timeout: int = 45) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _file_row(
    *,
    key: str,
    url: str,
    size: int,
    checksum: str = "",
    mime: str = "",
    over_cap: bool = False,
) -> dict[str, Any]:
    return {
        "key": key,
        "url": url,
        "size": size,
        "checksum": checksum,
        "mime": mime,
        "over_cap": over_cap,
    }


def _list_files(raw: list[dict[str, Any]], *, max_file_bytes: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (downloadable_under_cap, all_files_with_over_cap_flags)."""
    all_files: list[dict[str, Any]] = []
    downloadable: list[dict[str, Any]] = []
    for row in raw:
        size = int(row.get("size") or 0)
        item = dict(row)
        if size > max_file_bytes:
            item["over_cap"] = True
            all_files.append(item)
            continue
        item["over_cap"] = False
        all_files.append(item)
        downloadable.append(item)
    downloadable.sort(key=lambda item: int(item.get("size") or 0))
    all_files.sort(key=lambda item: int(item.get("size") or 0))
    return downloadable, all_files


def zenodo_files(landing_url: str, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> list[dict[str, Any]]:
    downloadable, _ = _list_files(_zenodo_raw(landing_url), max_file_bytes=max_file_bytes)
    return downloadable


def _zenodo_raw(landing_url: str) -> list[dict[str, Any]]:
    rec_id = landing_url.rstrip("/").split("/")[-1]
    payload = _fetch_json(f"https://zenodo.org/api/records/{rec_id}")
    raw: list[dict[str, Any]] = []
    for row in payload.get("files") or []:
        url = (row.get("links") or {}).get("self")
        if not url:
            continue
        raw.append(
            _file_row(
                key=str(row.get("key") or ""),
                url=url,
                size=int(row.get("size") or 0),
                checksum=str(row.get("checksum") or ""),
                mime=str(row.get("type") or ""),
            )
        )
    return raw


def zenodo_all_files(landing_url: str) -> list[dict[str, Any]]:
    _, all_files = _list_files(_zenodo_raw(landing_url), max_file_bytes=DEFAULT_MAX_FILE_BYTES)
    return all_files


def osf_files(landing_url: str, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> list[dict[str, Any]]:
    downloadable, _ = _list_files(_osf_raw(landing_url), max_file_bytes=max_file_bytes)
    return downloadable


def osf_all_files(landing_url: str) -> list[dict[str, Any]]:
    _, all_files = _list_files(_osf_raw(landing_url), max_file_bytes=DEFAULT_MAX_FILE_BYTES)
    return all_files


def _osf_raw(landing_url: str) -> list[dict[str, Any]]:
    token = _osf_token(landing_url)
    if not token:
        return []
    meta = _fetch_json(f"https://api.osf.io/v2/nodes/{token}/")
    files_link = ((meta.get("relationships") or {}).get("files") or {}).get("links", {}).get("related")
    if not files_link:
        return []
    listing = _fetch_json(files_link)
    raw: list[dict[str, Any]] = []
    for item in listing.get("data") or []:
        attrs = item.get("attributes") or {}
        links = item.get("links") or {}
        url = links.get("download") or links.get("self")
        if not url:
            continue
        raw.append(
            _file_row(
                key=str(attrs.get("name") or ""),
                url=url,
                size=int(attrs.get("size") or 0),
                checksum=str(attrs.get("md5") or ""),
                mime=str(attrs.get("contentType") or ""),
            )
        )
    return raw


def _osf_token(landing_url: str) -> str:
    path = urlparse(landing_url).path.strip("/").split("/")
    for part in path:
        if len(part) == 5 and part.isalnum():
            return part
    return landing_url.rstrip("/").split("/")[-1]


def figshare_files(landing_url: str, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> list[dict[str, Any]]:
    downloadable, _ = _list_files(_figshare_raw(landing_url), max_file_bytes=max_file_bytes)
    return downloadable


def figshare_all_files(landing_url: str) -> list[dict[str, Any]]:
    _, all_files = _list_files(_figshare_raw(landing_url), max_file_bytes=DEFAULT_MAX_FILE_BYTES)
    return all_files


def _figshare_raw(landing_url: str) -> list[dict[str, Any]]:
    article_id = _figshare_article_id(landing_url)
    if not article_id:
        return []
    payload = _fetch_json(f"https://api.figshare.com/v2/articles/{article_id}")
    raw: list[dict[str, Any]] = []
    for row in payload.get("files") or []:
        url = row.get("download_url")
        if not url:
            continue
        raw.append(
            _file_row(
                key=str(row.get("name") or ""),
                url=url,
                size=int(row.get("size") or 0),
                checksum=str(row.get("checksum") or ""),
                mime=str(row.get("mimetype") or ""),
            )
        )
    return raw


def _figshare_article_id(landing_url: str) -> str:
    match = re.search(r"/articles/(?:dataset/)?(\d+)", landing_url)
    if match:
        return match.group(1)
    tail = landing_url.rstrip("/").split("/")[-1]
    return tail if tail.isdigit() else ""


def dryad_files(landing_url: str, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> list[dict[str, Any]]:
    downloadable, _ = _list_files(_dryad_raw(landing_url), max_file_bytes=max_file_bytes)
    return downloadable


def dryad_all_files(landing_url: str) -> list[dict[str, Any]]:
    _, all_files = _list_files(_dryad_raw(landing_url), max_file_bytes=DEFAULT_MAX_FILE_BYTES)
    return all_files


def _dryad_raw(landing_url: str) -> list[dict[str, Any]]:
    doi_match = re.search(r"doi:([^?#]+)", landing_url, re.I) or re.search(r"10\.5061/dryad\.[a-z0-9]+", landing_url, re.I)
    if not doi_match:
        return []
    doi = doi_match.group(1) if doi_match.lastindex else doi_match.group(0)
    if not doi.startswith("10."):
        doi = f"10.5061/{doi}" if "dryad" in doi else doi
    search = _fetch_json(f"https://datadryad.org/api/v2/datasets/{urllib.parse.quote(doi, safe='')}")
    raw: list[dict[str, Any]] = []
    for row in search.get("_embedded", {}).get("stash:files", []):
        links = row.get("_links") or {}
        url = (links.get("stash:download") or {}).get("href")
        if not url:
            continue
        raw.append(
            _file_row(
                key=str(row.get("path") or row.get("originalFilename") or ""),
                url=url,
                size=int(row.get("size") or 0),
                checksum=str(row.get("digest") or ""),
            )
        )
    return raw


def github_release_files(landing_url: str, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> list[dict[str, Any]]:
    downloadable, _ = _list_files(_github_release_raw(landing_url), max_file_bytes=max_file_bytes)
    return downloadable


def github_release_all_files(landing_url: str) -> list[dict[str, Any]]:
    _, all_files = _list_files(_github_release_raw(landing_url), max_file_bytes=DEFAULT_MAX_FILE_BYTES)
    return all_files


def _github_release_raw(landing_url: str) -> list[dict[str, Any]]:
    parsed = urlparse(landing_url)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2 or "github.com" not in parsed.netloc:
        return []
    owner, repo = parts[0], parts[1]
    tag = parts[-1] if "releases" in parts else "latest"
    api = f"https://api.github.com/repos/{owner}/{repo}/releases/{tag}"
    payload = _fetch_json(api)
    raw: list[dict[str, Any]] = []
    for asset in payload.get("assets") or []:
        url = asset.get("browser_download_url")
        if not url:
            continue
        raw.append(
            _file_row(
                key=str(asset.get("name") or ""),
                url=url,
                size=int(asset.get("size") or 0),
            )
        )
    return raw


AdapterFn = Callable[[str, int], list[dict[str, Any]]]

ADAPTERS: list[tuple[str, Callable[[str], bool], AdapterFn]] = [
    ("zenodo", lambda u: "zenodo.org" in u.lower(), zenodo_files),
    ("osf", lambda u: "osf.io" in u.lower(), osf_files),
    ("figshare", lambda u: "figshare.com" in u.lower(), figshare_files),
    ("dryad", lambda u: "datadryad.org" in u.lower(), dryad_files),
    ("github_release", lambda u: "github.com" in u.lower() and "/releases/" in u.lower(), github_release_files),
]


def follow_landing_url(landing_url: str) -> str:
    if not landing_url or "doi.org" not in landing_url:
        return landing_url
    try:
        req = urllib.request.Request(landing_url, method="HEAD", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.geturl()
    except Exception:
        return landing_url


ALL_FILES_ADAPTERS: dict[str, Callable[[str], list[dict[str, Any]]]] = {
    "zenodo": zenodo_all_files,
    "osf": osf_all_files,
    "figshare": figshare_all_files,
    "dryad": dryad_all_files,
    "github_release": github_release_all_files,
}


def resolve_repository(landing_url: str, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> dict[str, Any]:
    landing = follow_landing_url(landing_url or "")
    host = landing.lower()
    for name, matcher, adapter in ADAPTERS:
        if matcher(host):
            files = adapter(landing, max_file_bytes=max_file_bytes)
            all_files_fn = ALL_FILES_ADAPTERS.get(name)
            all_files = all_files_fn(landing) if all_files_fn else files
            return {
                "repository": name,
                "landing_url": landing,
                "files": files,
                "all_files": all_files,
            }
    return {"repository": "unknown", "landing_url": landing, "files": [], "all_files": []}


def repository_slug(repository: str, landing_url: str, doi: str = "") -> str:
    if repository == "zenodo":
        return f"datacite_{landing_url.rstrip('/').split('/')[-1]}"
    if doi:
        return doi.replace("/", "_")
    return hashlib_slug(landing_url)


def hashlib_slug(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()[:12]
