#!/usr/bin/env python3
"""Minimal local Research Data Library server.

No external dependencies. This is intentionally boring infrastructure:
dataset registry, live-ish filesystem status, table previews, and a small
metadata-grounded assistant response endpoint.
"""

from __future__ import annotations

import csv
import json
import mimetypes
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
USDT_PACKAGE = ROOT / "data_lake/usdt_catalogue/research_package_pilot_100_blocks"
GDELT_STATUS = ROOT / "data_lake/news_shock_taxonomy/backfill_status/gkg_backfill_2018_2023"
GDELT_ROOT = ROOT / "data_lake/news_shock_taxonomy"


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_error": str(exc)}


def read_csv_preview(path: Path, limit: int = 50) -> dict:
    if not path.exists():
        return {"path": str(path.relative_to(ROOT)), "exists": False, "columns": [], "rows": []}
    rows = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader):
            if index >= limit:
                break
            rows.append(row)
        columns = reader.fieldnames or []
    return {
        "path": str(path.relative_to(ROOT)),
        "exists": True,
        "columns": columns,
        "rows": rows,
        "preview_limit": limit,
    }


def count_dirs(path: Path, pattern: str) -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in path.glob(pattern))


def gdelt_status() -> dict:
    ok = count_dirs(GDELT_STATUS, "*.ok.json")
    processed = count_dirs(GDELT_ROOT / "processed", "asia_gkg_window_*_20260526Tbackfill2018_2023Z")
    normalized = count_dirs(
        GDELT_ROOT / "normalized/gdelt_gkg_asia_bulk",
        "asia_gkg_window_*_20260526Tbackfill2018_2023Z",
    )
    raw = count_dirs(
        GDELT_ROOT / "raw/gdelt_gkg_asia_bulk",
        "asia_gkg_window_*_20260526Tbackfill2018_2023Z",
    )
    return {
        "expected_months": 72,
        "ok_months": ok,
        "processed_months": processed,
        "normalized_months": normalized,
        "raw_months": raw,
        "status_path": str(GDELT_STATUS.relative_to(ROOT)),
    }


def usdt_status() -> dict:
    manifest = load_json(USDT_PACKAGE / "manifest.json")
    return {
        "package_path": str(USDT_PACKAGE.relative_to(ROOT)),
        "package_exists": USDT_PACKAGE.exists(),
        "source_row_count": manifest.get("source_row_count"),
        "min_block": manifest.get("min_block"),
        "max_block": manifest.get("max_block"),
        "min_timestamp": manifest.get("min_timestamp"),
        "max_timestamp": manifest.get("max_timestamp"),
        "duplicate_primary_keys": manifest.get("duplicate_primary_keys"),
        "outputs": manifest.get("outputs", {}),
    }


def datasets() -> list[dict]:
    usdt = usdt_status()
    gdelt = gdelt_status()
    return [
        {
            "id": "usdt",
            "name": "Ethereum USDT Transfer Catalogue",
            "domain": "On-chain",
            "status": "ready" if usdt["package_exists"] else "missing",
            "type": "live connector + archived research package",
            "grain": "One row per ERC-20 Transfer event",
            "primary_key": "chain_id + tx_hash + log_index",
            "source": "Ethereum RPC pilot; BigQuery historical backend planned",
            "storage": "Parquet package + CSV research tables",
            "refresh": "RPC finalized-block updater planned",
            "coverage": f'{usdt.get("min_timestamp") or "unknown"} to {usdt.get("max_timestamp") or "unknown"}',
            "current_rows": usdt.get("source_row_count") or 0,
            "limitations": [
                "Pilot sample only; not full history.",
                "No exchange/entity labels.",
                "BigQuery access required for historical-scale panels.",
            ],
            "tables": [
                "daily_usdt_flows",
                "monthly_usdt_summary",
                "large_usdt_transfers",
                "address_day_usdt_flows_top",
                "top_addresses_by_volume",
            ],
        },
        {
            "id": "gdelt",
            "name": "GDELT Asia News Shock Backfill",
            "domain": "News",
            "status": "running",
            "type": "backfill pipeline + archived dataset",
            "grain": "Monthly Asia-filtered GKG window",
            "primary_key": "run_id + source-specific article/url keys",
            "source": "GDELT GKG public files",
            "storage": "Local data_lake + GDrive archive pipeline",
            "refresh": "Backfill queue active",
            "coverage": f'{gdelt["ok_months"]}/{gdelt["expected_months"]} months marked OK',
            "current_rows": None,
            "limitations": [
                "Backfill still in progress.",
                "Media-coverage bias applies.",
                "Needs final validation report after completion.",
            ],
            "tables": ["raw_gkg_asia_bulk", "normalized_gkg_asia_bulk", "processed_news_shock_panels"],
        },
        {
            "id": "coingecko",
            "name": "CoinGecko Market Panels",
            "domain": "Market data",
            "status": "registered",
            "type": "scheduled external API dataset",
            "grain": "Asset-day market observation",
            "primary_key": "asset_id + date",
            "source": "CoinGecko",
            "storage": "Existing scheduled outputs; catalogue registration pending",
            "refresh": "Daily scheduled job",
            "coverage": "Needs manifest",
            "current_rows": None,
            "limitations": ["Vendor methodology applies.", "Schema and lineage need registration."],
            "tables": ["asset_day_prices", "market_summary"],
        },
        {
            "id": "crypto_pipeline",
            "name": "Crypto Research Pipeline Exports",
            "domain": "Crypto markets",
            "status": "registered",
            "type": "research dataset package",
            "grain": "Mixed: coin-day, category, exchange, market panel",
            "primary_key": "table-specific",
            "source": "CoinGecko/public crypto source pipeline",
            "storage": "data_lake/crypto_pipeline/exports",
            "refresh": "Existing pipeline outputs; schedule status needs registry",
            "coverage": "Multiple exported tables and professor bundles",
            "current_rows": None,
            "limitations": ["Needs table-level manifest normalization.", "Multiple overlapping export bundles."],
            "tables": ["coin_profiles", "coin_analytics", "price_panel_long", "research_db_full_csv"],
        },
        {
            "id": "opensea",
            "name": "OpenSea / NFT Archive",
            "domain": "NFT / Web3",
            "status": "archive",
            "type": "scraped/enriched archive + deliverables",
            "grain": "Collection/token/event depending package",
            "primary_key": "package-specific",
            "source": "OpenSea/NFT pipeline outputs",
            "storage": "data_lake/opensea + deliverables/opensea_*",
            "refresh": "Not currently managed by this server",
            "coverage": "Existing professor deliverables and metadata packages",
            "current_rows": None,
            "limitations": ["Needs source lineage consolidation.", "Several deliverable packages overlap."],
            "tables": ["collection_metadata", "token_metadata", "graph_viewer_exports"],
        },
        {
            "id": "labor",
            "name": "Labor Market Scraping Archive",
            "domain": "Labor",
            "status": "needs audit",
            "type": "scraping archive",
            "grain": "Job posting / scrape observation",
            "primary_key": "source + scrape_time + job_id where available",
            "source": "Upwork / 104-style scraping engines",
            "storage": "Archive locations need final catalogue registration",
            "refresh": "Not currently managed here",
            "coverage": "Needs audit",
            "current_rows": None,
            "limitations": ["Deduplication and schema audit required before claims."],
            "tables": ["job_postings", "scrape_runs"],
        },
        {
            "id": "markets",
            "name": "Public Market / Entity Mapping Assets",
            "domain": "Public markets",
            "status": "archive",
            "type": "market panels and entity mapping",
            "grain": "Instrument-day / entity / holdings links",
            "primary_key": "table-specific",
            "source": "yfinance, sourced universes, entity mapping jobs",
            "storage": "data_lake/markets + data_lake/entity_mapping",
            "refresh": "Historical/archived runs",
            "coverage": "Asia/universe snapshots and market controls",
            "current_rows": None,
            "limitations": ["Needs manifest normalization.", "Coverage differs by run timestamp."],
            "tables": ["asia_entity_master", "instrument_coverage", "market_controls"],
        },
        {
            "id": "reports",
            "name": "Reports and Deliverables",
            "domain": "Reports",
            "status": "archive",
            "type": "research outputs",
            "grain": "Report/package",
            "primary_key": "path + created_at where available",
            "source": "Local research runs and professor bundles",
            "storage": "reports + deliverables",
            "refresh": "Manual",
            "coverage": "Audit reports, professor zips, research screens",
            "current_rows": None,
            "limitations": ["Not all reports have machine-readable manifests."],
            "tables": ["audit_reports", "professor_bundles", "research_screens"],
        },
    ]


def collections() -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for item in datasets():
        grouped.setdefault(item["domain"], []).append(item)
    return [
        {
            "id": domain.lower().replace(" ", "_").replace("/", "_"),
            "name": domain,
            "asset_count": len(items),
            "running_count": sum(1 for item in items if item["status"] == "running"),
            "blocked_count": sum(1 for item in items if item["status"] in {"blocked", "missing", "needs audit"}),
            "assets": [item["id"] for item in items],
        }
        for domain, items in sorted(grouped.items())
    ]


def dataset_by_id(dataset_id: str) -> dict | None:
    for item in datasets():
        if item["id"] == dataset_id:
            return item
    return None


def assistant_answer(question: str) -> dict:
    q = question.lower()
    if "professor" in q or "first" in q:
        answer = (
            "Start with a narrow Research Data Library MVP: USDT dataset page, GDELT dataset page, "
            "CoinGecko placeholder, schema/coverage/limitations, and one query/export surface. "
            "Do not lead with chatbot or visual dashboard."
        )
    elif "bigquery" in q or "gcp" in q:
        answer = (
            "BigQuery is the historical blockchain warehouse path. It is currently blocked by missing GCP "
            "credentials/project access. The library can still run on local RPC/DuckDB pilot data."
        )
    elif "drive" in q or "gdrive" in q:
        answer = (
            "GDrive should be archive and delivery storage: packages, manifests, validation reports, and exports. "
            "It should not be treated as the query engine."
        )
    elif "usdt" in q or "etherscan" in q:
        answer = (
            "USDT is best represented as a maintained data asset: BigQuery for historical scale, RPC eth_getLogs "
            "for live updates, Parquet/DuckDB cache for local research, and Etherscan/Blockscout for validation."
        )
    else:
        answer = (
            "The useful product is a boring research data library: dataset registry, lineage, schema, status, "
            "query/export, and a controlled assistant grounded in metadata."
        )
    return {"answer": answer, "created_at": now_utc(), "source": "local metadata rules"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return

    def send_json(self, data: object, status: int = 200) -> None:
        payload = json.dumps(data, indent=2, sort_keys=True, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_json({"error": "not found"}, 404)
            return
        content = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path in {"/", "/index.html"}:
            self.send_file(ROOT / "research_data_library.html")
            return
        if path == "/api/health":
            self.send_json({"status": "ok", "created_at": now_utc(), "root": str(ROOT)})
            return
        if path == "/api/datasets":
            self.send_json({"datasets": datasets(), "created_at": now_utc()})
            return
        if path == "/api/collections":
            self.send_json({"collections": collections(), "created_at": now_utc()})
            return
        if path.startswith("/api/datasets/"):
            dataset_id = path.rsplit("/", 1)[-1]
            item = dataset_by_id(dataset_id)
            self.send_json(item if item else {"error": "dataset not found"}, 200 if item else 404)
            return
        if path == "/api/status/usdt":
            self.send_json(usdt_status())
            return
        if path == "/api/status/gdelt":
            self.send_json(gdelt_status())
            return
        if path.startswith("/api/tables/usdt/"):
            name = path.rsplit("/", 1)[-1]
            table_map = {
                "daily": USDT_PACKAGE / "tables/daily_usdt_flows.csv",
                "monthly": USDT_PACKAGE / "tables/monthly_usdt_summary.csv",
                "large": USDT_PACKAGE / "tables/large_usdt_transfers.csv",
                "address_day": USDT_PACKAGE / "tables/address_day_usdt_flows_top.csv",
                "top_addresses": USDT_PACKAGE / "tables/top_addresses_by_volume.csv",
            }
            limit = int(query.get("limit", ["50"])[0])
            target = table_map.get(name)
            self.send_json(read_csv_preview(target, limit) if target else {"error": "table not found"}, 200 if target else 404)
            return

        self.send_file(ROOT / path.lstrip("/"))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {}

        if parsed.path == "/api/assistant":
            self.send_json(assistant_answer(str(payload.get("question", ""))))
            return
        if parsed.path == "/api/query/preview":
            sql = str(payload.get("sql", "")).lower()
            if "large" in sql:
                self.send_json(read_csv_preview(USDT_PACKAGE / "tables/large_usdt_transfers.csv", 20))
            elif "address" in sql:
                self.send_json(read_csv_preview(USDT_PACKAGE / "tables/address_day_usdt_flows_top.csv", 20))
            else:
                self.send_json(read_csv_preview(USDT_PACKAGE / "tables/daily_usdt_flows.csv", 20))
            return

        self.send_json({"error": "not found"}, 404)


def main() -> int:
    port = int(os.environ.get("RDL_PORT", "8770"))
    host = os.environ.get("RDL_HOST", "127.0.0.1")
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Research Data Library server: http://{host}:{port}/", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
