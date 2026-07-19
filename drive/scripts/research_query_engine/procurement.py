from __future__ import annotations

import csv
import hashlib
import ipaddress
import json
import re
import socket
import sqlite3
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


MAX_SAMPLE_BYTES = 2 * 1024 * 1024
DATA_EXTENSIONS = {".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".zip", ".gz", ".parquet", ".xlsx", ".xml"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connector_id(url: str) -> str:
    return "src_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]


def assert_public_url(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("only public HTTP/HTTPS URLs are allowed")
    if parsed.username or parsed.password:
        raise ValueError("credentials embedded in URLs are not allowed")
    addresses = {row[4][0] for row in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))}
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise ValueError(f"private or non-routable target is blocked: {address}")
    return parsed


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        assert_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _probe_ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()
class LinkParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.title = ""
        self._in_title = False
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs):
        values = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag in {"a", "link"} and values.get("href"):
            self.links.append({"url": urllib.parse.urljoin(self.base_url, values["href"]), "rel": values.get("rel", ""), "text": ""})

    def handle_endtag(self, tag: str):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str):
        if self._in_title:
            self.title += data.strip()
        if self.links and data.strip():
            self.links[-1]["text"] = (self.links[-1]["text"] + " " + data.strip()).strip()[:240]


class ConnectorStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS connectors (id TEXT PRIMARY KEY, created_at TEXT, updated_at TEXT, status TEXT, name TEXT, source_url TEXT UNIQUE, spec_json TEXT)")

    def save_candidate(self, spec: dict[str, Any]) -> dict[str, Any]:
        cid = spec["connector_id"]
        stamp = now()
        with sqlite3.connect(self.path) as db:
            existing = db.execute("SELECT created_at, status FROM connectors WHERE id=?", (cid,)).fetchone()
            created_at, status = existing if existing else (stamp, "candidate")
            db.execute(
                "INSERT OR REPLACE INTO connectors VALUES (?, ?, ?, ?, ?, ?, ?)",
                (cid, created_at, stamp, status, spec.get("name", cid), spec["source_url"], json.dumps(spec)),
            )
        return self.get(cid)

    def approve(self, cid: str) -> dict[str, Any]:
        with sqlite3.connect(self.path) as db:
            if not db.execute("SELECT 1 FROM connectors WHERE id=?", (cid,)).fetchone():
                raise KeyError(cid)
            db.execute("UPDATE connectors SET status='approved', updated_at=? WHERE id=?", (now(), cid))
        return self.get(cid)

    def get(self, cid: str) -> dict[str, Any]:
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM connectors WHERE id=?", (cid,)).fetchone()
        if not row:
            raise KeyError(cid)
        item = dict(row)
        item["spec"] = json.loads(item.pop("spec_json"))
        return item

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM connectors ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["spec"] = json.loads(item.pop("spec_json"))
            items.append(item)
        return items


class ProcurementWorkbench:
    def __init__(self, root: Path):
        self.root = root
        self.store = ConnectorStore(root / "procurement_connectors.sqlite3")
        self.opener = urllib.request.build_opener(
            SafeRedirectHandler(),
            urllib.request.HTTPSHandler(context=_probe_ssl_context()),
        )

    def probe(self, url: str, name: str = "") -> dict[str, Any]:
        parsed = assert_public_url(url)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "ResearchDrive-Probe/1.0", "Range": f"bytes=0-{MAX_SAMPLE_BYTES - 1}"},
        )
        with self.opener.open(request, timeout=45) as response:
            final_url = response.geturl()
            assert_public_url(final_url)
            body = response.read(MAX_SAMPLE_BYTES + 1)
            truncated = len(body) > MAX_SAMPLE_BYTES
            body = body[:MAX_SAMPLE_BYTES]
            headers = {key.lower(): value for key, value in response.headers.items()}
            status = response.status

        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        access_mode = self._access_mode(final_url, content_type)
        sample = self._inspect_sample(body, content_type, final_url)
        html = sample.pop("html", None)
        discovered_files: list[dict[str, str]] = []
        pagination = self._pagination(headers, final_url, html)
        title = name or sample.get("title") or parsed.hostname or final_url
        if html:
            for link in html.links:
                link_path = urllib.parse.urlparse(link["url"]).path.lower()
                if Path(link_path).suffix in DATA_EXTENSIONS:
                    try:
                        assert_public_url(link["url"])
                    except (ValueError, OSError, socket.gaierror):
                        continue
                    discovered_files.append(link)
                if len(discovered_files) >= 200:
                    break

        robots = self._robots(parsed)
        recommendation = self._recommend(access_mode, discovered_files, pagination)
        spec = {
            "connector_id": connector_id(final_url),
            "name": title[:240],
            "source_url": final_url,
            "host": urllib.parse.urlparse(final_url).hostname,
            "access_mode": access_mode,
            "content_type": content_type or "unknown",
            "content_length": self._integer(headers.get("content-length")),
            "etag": headers.get("etag"),
            "last_modified": headers.get("last-modified"),
            "accept_ranges": headers.get("accept-ranges"),
            "sample_bytes": len(body),
            "sample_truncated": truncated,
            "sample": sample,
            "pagination": pagination,
            "discovered_files": discovered_files,
            "robots": robots,
            "recommended_action": recommendation,
            "probed_at": now(),
            "http_status": status,
        }
        connector = self.store.save_candidate(spec)
        return {"connector": connector, "summary": self._summary(spec)}

    def collection_plan(self, cid: str, limit: int = 200, *, require_approved: bool = True) -> dict[str, Any]:
        connector = self.store.get(cid)
        if require_approved and connector["status"] != "approved":
            raise ValueError("connector must be approved before collection")
        spec = connector["spec"]
        if spec["access_mode"] == "direct_file":
            items = [{"url": spec["source_url"]}]
        else:
            items = [{"url": row["url"]} for row in spec.get("discovered_files", [])[: max(1, min(limit, 2000))]]
        if not items:
            raise ValueError("connector has no bounded file manifest; configure API pagination or a file selector first")
        return {
            "title": f"Collect {connector['name']}",
            "job_type": "http_manifest",
            "items": items,
            "shards": min(4, len(items)),
            "per_node_workers": 2,
            "delay_seconds": 0.35,
            "request_timeout": 90,
            "retries": 3,
            "timeout_seconds": 7200,
            "launchable": True,
            "connector_id": cid,
            "url": spec.get("source_url"),
            "requires_approval": require_approved,
        }

    def manifest_plan_from_connector(self, cid: str, limit: int = 50) -> dict[str, Any]:
        """Magic/campaign path — candidate connectors may collect without manual approve."""
        return self.collection_plan(cid, limit=limit, require_approved=False)

    def _access_mode(self, url: str, content_type: str) -> str:
        suffix = Path(urllib.parse.urlparse(url).path.lower()).suffix
        if suffix in DATA_EXTENSIONS or any(token in content_type for token in ("text/csv", "application/zip", "parquet", "spreadsheet")):
            return "direct_file"
        if "json" in content_type:
            return "json_api"
        if "html" in content_type:
            return "html_catalog"
        if "xml" in content_type:
            return "xml_api"
        return "unknown_http"

    def _inspect_sample(self, body: bytes, content_type: str, url: str) -> dict[str, Any]:
        text = body.decode("utf-8", errors="replace")
        if "json" in content_type or Path(urllib.parse.urlparse(url).path).suffix.lower() in {".json", ".jsonl", ".ndjson"}:
            try:
                payload = json.loads(text)
                rows = payload if isinstance(payload, list) else next((value for value in payload.values() if isinstance(value, list)), []) if isinstance(payload, dict) else []
                first = rows[0] if rows else payload
                return {"format": "json", "top_level": type(payload).__name__, "estimated_sample_rows": len(rows), "fields": self._fields(first), "preview": rows[:3] if rows else first}
            except json.JSONDecodeError:
                lines = [line for line in text.splitlines() if line.strip()][:3]
                parsed = []
                for line in lines:
                    try:
                        parsed.append(json.loads(line))
                    except json.JSONDecodeError:
                        break
                if parsed:
                    return {"format": "jsonl", "estimated_sample_rows": len(parsed), "fields": self._fields(parsed[0]), "preview": parsed}
        if "csv" in content_type or Path(urllib.parse.urlparse(url).path).suffix.lower() in {".csv", ".tsv"}:
            try:
                dialect = csv.Sniffer().sniff(text[:8192], delimiters=",\t;|")
                reader = csv.DictReader(text.splitlines(), dialect=dialect)
                rows = []
                for _, row in zip(range(5), reader):
                    rows.append(dict(row))
                return {"format": "tabular", "delimiter": dialect.delimiter, "fields": list(reader.fieldnames or []), "preview": rows}
            except csv.Error:
                pass
        if "html" in content_type or "<html" in text[:1000].lower():
            parser = LinkParser(url)
            parser.feed(text)
            return {"format": "html", "title": parser.title, "links_seen": len(parser.links), "html": parser}
        return {"format": "binary_or_text", "preview": text[:1000] if text else "", "sha256_sample": hashlib.sha256(body).hexdigest()}

    def _fields(self, row: Any) -> list[str]:
        return sorted(str(key) for key in row.keys())[:200] if isinstance(row, dict) else []

    def _pagination(self, headers: dict[str, str], url: str, html: LinkParser | None) -> dict[str, Any]:
        link = headers.get("link", "")
        if 'rel="next"' in link or "rel=next" in link:
            return {"type": "link_header", "detected": True}
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        keys = [key for key in query if key.lower() in {"page", "offset", "cursor", "limit", "per_page", "pagesize", "page_size"}]
        if keys:
            return {"type": "query_parameters", "detected": True, "keys": keys}
        if html and any("next" in (row.get("rel", "") + " " + row.get("text", "")).lower() for row in html.links):
            return {"type": "html_next_link", "detected": True}
        return {"type": "unknown", "detected": False}

    def _robots(self, parsed: urllib.parse.ParseResult) -> dict[str, Any]:
        url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "ResearchDrive-Probe/1.0"})
            with self.opener.open(request, timeout=10) as response:
                text = response.read(65536).decode("utf-8", errors="replace")
            return {"url": url, "available": True, "disallow_all": bool(re.search(r"User-agent:\s*\*.*?Disallow:\s*/\s*$", text, re.I | re.M | re.S))}
        except (OSError, urllib.error.URLError, ValueError):
            return {"url": url, "available": False, "disallow_all": False}

    def _recommend(self, access_mode: str, files: list[dict[str, str]], pagination: dict[str, Any]) -> str:
        if access_mode == "direct_file":
            return "download_sample_then_archive"
        if access_mode in {"json_api", "xml_api"}:
            return "configure_bounded_api_connector" if pagination["detected"] else "query_sample_then_define_pagination"
        if access_mode == "html_catalog" and files:
            return "review_discovered_file_manifest"
        if access_mode == "html_catalog":
            return "browser_or_site_specific_connector_required"
        return "manual_review_required"

    def _summary(self, spec: dict[str, Any]) -> str:
        return f"{spec['access_mode']} source; {len(spec['discovered_files'])} downloadable links detected; recommendation: {spec['recommended_action']}"

    def _integer(self, value: str | None) -> int | None:
        try:
            return int(value) if value is not None else None
        except ValueError:
            return None
