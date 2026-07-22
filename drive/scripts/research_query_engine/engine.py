#!/usr/bin/env python3
from __future__ import annotations

import csv
import glob as globmod
import importlib.util
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

csv.field_size_limit(sys.maxsize)


@dataclass
class QueryResult:
    dataset_id: str
    rows: list[dict[str, Any]]
    meta: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"dataset_id": self.dataset_id, "meta": self.meta, "rows": self.rows}


class ResearchQueryEngine:
    def __init__(self, registry_path: str | Path = "config/research_query_registry.json", repo_root: str | Path | None = None):
        self.repo_root = Path(repo_root or ".").resolve()
        self.registry_path = self._resolve(registry_path)
        self.registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.datasets = {d["dataset_id"]: d for d in self.registry.get("datasets", [])}
        self._reconcile_local_panel_readiness()

    def _resolve(self, value: str | Path) -> Path:
        from scripts.research_data_mcp.data_paths import resolve_data_path

        return resolve_data_path(self.repo_root, value)

    def list_datasets(self) -> list[dict[str, Any]]:
        return list(self.datasets.values())

    def _reconcile_local_panel_readiness(self) -> None:
        """Remove stale query-ready claims when a local panel is not materialized."""
        for dataset in self.datasets.values():
            if dataset.get("backend") != "local_parquet_panel":
                continue
            if dataset.get("analysis_readiness") != "instant":
                continue
            try:
                self._resolve_panel_path(dataset, {})
            except (FileNotFoundError, KeyError, TypeError, ValueError):
                materialization = dict(dataset.get("materialization") or {})
                resolved_path = materialization.pop("resolved_path", None)
                if resolved_path:
                    materialization["expected_path"] = resolved_path
                materialization.update(
                    {
                        "query_ready": False,
                        "skipped": "local_panel_missing_at_runtime",
                    }
                )
                dataset["materialization"] = materialization
                dataset["analysis_readiness"] = "metadata_search"
                dataset["collection_status"] = "metadata_only"
                dataset["field_coverage"] = "metadata-only"
                dataset["runtime_readiness_reason"] = "local_panel_missing"

    def describe(self, dataset_id: str) -> dict[str, Any]:
        if dataset_id not in self.datasets:
            raise KeyError(f"unknown dataset_id: {dataset_id}")
        return self.datasets[dataset_id]

    def search_datasets(self, q: str = "", domain: str = "", readiness: str = "", access_mode: str = "", limit: int = 50) -> list[dict[str, Any]]:
        ql = q.lower().strip()
        tokens = [t for t in re.split(r"\W+", ql) if len(t) > 2]
        scored: list[tuple[int, dict[str, Any]]] = []
        for ds in self.list_datasets():
            text = " ".join(str(ds.get(k, "")) for k in ["dataset_id", "name", "description", "recommended_use", "limitations", "grain", "backend"]).lower()
            if ql:
                if ql in text:
                    score = 100
                elif tokens:
                    score = sum(10 for token in tokens if token in text)
                    if score == 0:
                        continue
                else:
                    continue
            else:
                score = 0
            if domain and domain != ds.get("domain"):
                continue
            if readiness and readiness not in str(ds.get("analysis_readiness", "")):
                continue
            if access_mode and access_mode != ds.get("access_shape"):
                continue
            scored.append((score, ds))
        scored.sort(key=lambda row: (-row[0], row[1].get("dataset_id", "")))
        return [ds for _, ds in scored[:limit]]

    def query(self, dataset_id: str, **params: Any) -> QueryResult:
        if dataset_id == "research_source_plan":
            return self.plan_research_sources(**params)
        ds = self.describe(dataset_id)
        backend = ds.get("backend")
        if backend == "local_gdelt_panel_csv":
            return self._query_gdelt_panel(ds, params)
        if backend == "local_gdelt_high_priority_csv":
            return self._query_gdelt_high_priority(ds, params)
        if backend == "local_jsonl_catalog":
            return self._query_jsonl_catalog(ds, params)
        if backend == "coingecko_simple_price_api":
            return self._query_coingecko_simple_price(ds, params)
        if backend == "local_json_file":
            return self._query_local_json_file(ds, params)
        if backend == "local_json_glob":
            return self._query_local_json_glob(ds, params)
        if backend == "local_csv_file":
            return self._query_local_csv_file(ds, params)
        if backend == "local_file":
            return self._query_local_file_tree(ds, params)
        if backend == "local_jsonl_payment_ledger":
            return self._query_jsonl_payment_ledger(ds, params)
        if backend == "usdt_bigquery_catalogue":
            return self._query_usdt_bigquery_catalogue(ds, params)
        if backend == "local_parquet_panel":
            return self._query_local_parquet_panel(ds, params)
        if backend == "collection_ops_status":
            return self._query_collection_ops_status(ds, params)
        if backend == "datacite_local_harvest_status":
            return self._query_datacite_local_harvest_status(ds, params)
        raise ValueError(f"unsupported backend for {dataset_id}: {backend}")

    def _date_ok(self, row: dict[str, Any], start_date: str, end_date: str) -> bool:
        d = row.get("date") or row.get("published_at") or ""
        if start_date and d < start_date:
            return False
        if end_date and d > end_date:
            return False
        return True

    def _iter_month_dirs(self, root: Path):
        if not root.exists():
            return
        for p in sorted(root.glob("asia_gkg_window_*")):
            if p.is_dir():
                yield p

    def _query_gdelt_panel(self, ds: dict[str, Any], params: dict[str, Any]) -> QueryResult:
        root = self._resolve(ds["local_root"])
        start_date = str(params.get("start_date", ""))
        end_date = str(params.get("end_date", ""))
        countries = {x.strip().upper() for x in str(params.get("countries", params.get("country", ""))).split(",") if x.strip()}
        order_by = str(params.get("order_by", "date"))
        descending = str(params.get("descending", "false")).lower() in {"1", "true", "yes"}
        limit = int(params.get("limit", 100))
        rows: list[dict[str, Any]] = []
        files_seen = 0
        for month_dir in self._iter_month_dirs(root) or []:
            panel = month_dir / "daily_country_shock_panel.csv"
            if not panel.exists():
                continue
            files_seen += 1
            with panel.open(newline="", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if not self._date_ok(row, start_date, end_date):
                        continue
                    if countries and row.get("country_iso3", "").upper() not in countries:
                        continue
                    rows.append(row)
        if order_by:
            rows.sort(key=lambda r: self._sort_key(r.get(order_by, "")), reverse=descending)
        rows = rows[:limit]
        return QueryResult(ds["dataset_id"], rows, {"files_seen": files_seen, "returned": len(rows), "params": params})

    def _query_gdelt_high_priority(self, ds: dict[str, Any], params: dict[str, Any]) -> QueryResult:
        root = self._resolve(ds["local_root"])
        start_date = str(params.get("start_date", ""))
        end_date = str(params.get("end_date", ""))
        countries = {x.strip().upper() for x in str(params.get("countries", params.get("country", ""))).split(",") if x.strip()}
        domain = str(params.get("source_domain", params.get("domain", ""))).lower().strip()
        q = str(params.get("q", "")).lower().strip()
        limit = int(params.get("limit", 100))
        rows: list[dict[str, Any]] = []
        files_seen = 0
        for month_dir in self._iter_month_dirs(root) or []:
            sample = month_dir / "sample_high_priority.csv"
            if not sample.exists():
                continue
            files_seen += 1
            with sample.open(newline="", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if not self._date_ok(row, start_date, end_date):
                        continue
                    if countries and row.get("country_iso3", "").upper() not in countries:
                        continue
                    if domain and domain not in row.get("source_domain", "").lower():
                        continue
                    if q:
                        text = " ".join(str(row.get(k, "")) for k in ["canonical_url", "source_domain", "themes", "shock_hints", "content_signal_flags"]).lower()
                        if q not in text:
                            continue
                    rows.append(row)
                    if len(rows) >= limit:
                        return QueryResult(ds["dataset_id"], rows, {"files_seen": files_seen, "returned": len(rows), "params": params})
        return QueryResult(ds["dataset_id"], rows, {"files_seen": files_seen, "returned": len(rows), "params": params})

    def _query_jsonl_catalog(self, ds: dict[str, Any], params: dict[str, Any]) -> QueryResult:
        path = self._resolve(ds["local_path"])
        q = str(params.get("q", "")).lower().strip()
        source = str(params.get("source", "")).lower().strip()
        domain = str(params.get("domain", "")).lower().strip()
        access_mode = str(params.get("access_mode", "")).lower().strip()
        readiness = str(params.get("analysis_readiness", "")).lower().strip()
        promotion_tier = str(params.get("promotion_tier", "")).lower().strip()
        limit = int(params.get("limit", 100))
        rows: list[dict[str, Any]] = []
        scanned = 0
        if not path.exists():
            return QueryResult(ds["dataset_id"], [], {"error": f"missing catalog path: {path}", "params": params})
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                scanned += 1
                row = json.loads(line)
                if source and source != str(row.get("source", "")).lower():
                    continue
                if domain and domain != str(row.get("domain", "")).lower():
                    continue
                if access_mode and access_mode != str(row.get("access_mode", "")).lower():
                    continue
                if readiness and readiness not in str(row.get("analysis_readiness", "")).lower():
                    continue
                if promotion_tier and promotion_tier != str(row.get("promotion_tier", "")).lower():
                    continue
                if q:
                    text = " ".join(str(row.get(k, "")) for k in ["title", "description", "source", "domain", "recommended_action", "promotion_reasons", "url"]).lower()
                    if q not in text:
                        continue
                rows.append({k: row.get(k) for k in ["source", "dataset_id", "title", "description", "url", "domain", "access_mode", "analysis_readiness", "recommended_action", "promotion_score", "promotion_tier", "promotion_reasons", "license", "tags"]})
                if len(rows) >= limit:
                    break
        return QueryResult(ds["dataset_id"], rows, {"scanned": scanned, "returned": len(rows), "params": params})

    def plan_research_sources(self, **params: Any) -> QueryResult:
        prompt = str(params.get("q", params.get("prompt", ""))).strip()
        limit = int(params.get("limit", 25))
        if not prompt:
            return QueryResult("research_source_plan", [], {"error": "missing q=research question or construct"})

        expanded = self._expand_research_query(prompt)
        candidates: list[dict[str, Any]] = []
        seen = set()

        for ds in self.list_datasets():
            if ds.get("backend") != "local_parquet_panel":
                continue
            if ds.get("analysis_readiness") != "instant":
                continue
            text = " ".join(
                str(ds.get(k, ""))
                for k in ["dataset_id", "name", "description", "recommended_use", "grain"]
            ).lower()
            prompt_tokens = [t for t in re.split(r"\W+", prompt.lower()) if len(t) > 3]
            match_terms = list(dict.fromkeys([*expanded, *prompt_tokens]))
            if not any(term.lower() in text for term in match_terms):
                continue
            row = {
                "source": "local_research_panel",
                "dataset_id": ds["dataset_id"],
                "title": ds.get("name", ds["dataset_id"]),
                "description": ds.get("description", ""),
                "url": "",
                "domain": "local_derived_tables",
                "access_mode": "query_local",
                "analysis_readiness": ds.get("analysis_readiness", "instant"),
                "recommended_action": "query_dataset",
                "promotion_score": 95,
                "promotion_tier": "ready_now",
                "promotion_reasons": "instant local parquet panel; no download required",
                "license": "internal",
                "tags": [ds.get("grain", ""), ds.get("backend", "")],
                "matched_query": prompt,
                "planning_source": "local_parquet_panel",
            }
            key = (row.get("source"), row.get("dataset_id"), row.get("url"))
            if key in seen:
                continue
            seen.add(key)
            row["access_decision"] = self._access_decision(row)
            row["scrape_or_download_needed"] = self._scrape_or_download_needed(row)
            candidates.append(row)

        for query in expanded:
            for dataset_id in ["procurement_source_registry", "external_dataset_catalog_curated"]:
                if dataset_id not in self.datasets:
                    continue
                result = self.query(dataset_id, q=query, limit=max(10, limit))
                for row in result.rows:
                    key = (row.get("source"), row.get("dataset_id"), row.get("url"))
                    if key in seen:
                        continue
                    seen.add(key)
                    row = dict(row)
                    row["matched_query"] = query
                    row["planning_source"] = dataset_id
                    row["access_decision"] = self._access_decision(row)
                    row["scrape_or_download_needed"] = self._scrape_or_download_needed(row)
                    candidates.append(row)
        candidates.sort(key=self._planning_rank_key, reverse=True)
        rows = candidates[:limit]
        plan = {
            "prompt": prompt,
            "expanded_queries": expanded,
            "returned": len(rows),
            "recommended_flow": [
                "query instant local parquet panels when grain matches (country-week or ticker-week)",
                "search curated index for external complements",
                "query_remote/cache_derived sources before download",
                "sample_probe selected repository records",
                "scrape only if no query/download source covers the construct",
            ],
            "interpretation": self._interpret_prompt(prompt),
        }
        return QueryResult("research_source_plan", rows, plan)

    def _expand_research_query(self, prompt: str) -> list[str]:
        p = prompt.lower()
        terms = [prompt]
        expansions = {
            "brand": ["brand awareness", "consumer sentiment", "search interest", "news mentions", "social media", "consumer survey"],
            "awareness": ["search interest", "public attention", "news mentions", "wikipedia pageviews", "social media"],
            "byd": ["BYD electric vehicle", "EV sales", "China auto market", "consumer sentiment electric vehicle"],
            "crypto": ["cryptocurrency", "bitcoin", "ethereum", "blockchain", "financial news sentiment"],
            "ethereum": ["ethereum", "blockchain", "usdt", "stablecoin", "etherscan", "blockscout", "ethereum rpc"],
            "stablecoin": ["stablecoin", "usdt", "tether", "ethereum", "blockchain", "exchange reserves"],
            "usdt": ["usdt", "tether", "stablecoin", "ethereum", "erc20 transfer"],
            "regulation": ["regulation", "enforcement", "sec", "policy", "regulatory event"],
            "nft": ["NFT", "opensea", "marketplace volume", "digital asset"],
            "market": ["financial market", "price", "volatility", "economic", "trading"],
            "labor": ["job posting", "employment", "labor market", "platform work"],
            "baby": ["infant growth", "child development", "NHANES", "diaper", "consumer panel", "pediatric survey"],
            "diaper": ["baby care", "infant product", "consumer panel", "retail scanner", "brand market share"],
            "infant": ["baby growth", "child development", "NHANES", "pediatric health survey"],
        }
        for key, values in expansions.items():
            if key in p:
                terms.extend(values)
        # Always include broad proxy classes.
        terms.extend(["news sentiment", "social web", "economic data", "time series"])
        out = []
        seen = set()
        for t in terms:
            t = t.strip()
            if t and t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
        return out[:12]

    def _planning_rank_key(self, row: dict[str, Any]) -> tuple[int, int]:
        base = int(row.get("promotion_score") or 0)
        source_boost = 25 if row.get("planning_source") == "procurement_source_registry" else 0
        mode = str(row.get("access_mode") or "")
        mode_boost = 12 if mode in {"query_remote", "api_filterable"} else 6 if "api" in mode or "query" in mode else 0
        tier = str(row.get("promotion_tier") or "")
        tier_boost = 10 if "tier_1" in tier else 5 if "tier_2" in tier else 0
        return (source_boost + mode_boost + tier_boost + base, base)

    def _access_decision(self, row: dict[str, Any]) -> str:
        mode = str(row.get("access_mode") or "")
        source = str(row.get("source") or "")
        if mode == "query_remote":
            return "query_or_probe_first_then_cache_derived"
        if mode in {"api_filterable", "download_or_stream", "metadata_and_download", "query_or_cloud_access", "api_and_scrape_pipeline", "api_or_connector_probe", "internal_archive"}:
            return "probe_connector_or_sample_then_cache_derived"
        if mode in {"metadata_index", "discovery_reference", "download_catalogue", "source_family_registry"}:
            return "metadata_or_source_family_first_then_probe"
        if mode == "sample_probe":
            return "inspect_metadata_and_sample_files_before_download"
        if source in {"google_dataset_search", "re3data"}:
            return "discovery_only_find_underlying_repository"
        return "reference_then_decide"

    def _scrape_or_download_needed(self, row: dict[str, Any]) -> str:
        mode = str(row.get("access_mode") or "")
        if mode == "query_remote":
            return "not_initially"
        if mode == "sample_probe":
            return "possibly_after_sample"
        return "not_enough_information"

    def _query_usdt_bigquery_catalogue(self, ds: dict[str, Any], params: dict[str, Any]) -> QueryResult:
        action = str(params.get("action", "status")).lower().strip()
        if action in {"status", "health"}:
            return self._usdt_status(ds, params)
        if action == "sql":
            return self._usdt_sql_template(ds, params)
        if action == "sample":
            return self._usdt_local_sample(ds, params)
        if action in {"dry_run", "dry-run", "run"}:
            return self._usdt_bigquery_job(ds, params, run=action == "run")
        raise ValueError("unsupported USDT action; use status, sql, sample, dry_run, or run")

    def _usdt_status(self, ds: dict[str, Any], params: dict[str, Any]) -> QueryResult:
        project = self._bigquery_project(params)
        adc = self._google_adc_status() if self._has_google_adc_hint() else {
            "available": False,
            "error": "NoLocalCredentialHint",
            "message": "No GOOGLE_APPLICATION_CREDENTIALS and no local gcloud ADC file found.",
        }
        dependency = importlib.util.find_spec("google.cloud.bigquery") is not None
        local_sample = self._latest_usdt_sample(ds)
        ready = bool(dependency and project and adc.get("available"))
        row = {
            "interface": "bigquery_historical_plus_rpc_preview",
            "bigquery_ready": ready,
            "bigquery_project": project,
            "bigquery_dependency": "installed" if dependency else "missing",
            "google_adc": "available" if adc.get("available") else "missing",
            "api_key_note": "GOOGLE_API_KEY is present but BigQuery jobs need OAuth/ADC and a billing or quota project"
            if os.environ.get("GOOGLE_API_KEY")
            else "GOOGLE_API_KEY not set; BigQuery still requires OAuth/ADC",
            "local_rpc_sample": "available" if local_sample else "missing",
            "safe_actions": ["sql", "dry_run", "sample", "run_requires_confirm_execute"],
        }
        meta = {
            "params": params,
            "bigquery_ready": ready,
            "project": project,
            "adc": adc,
            "dependency": dependency,
            "local_sample": local_sample or {"exists": False},
            "known_queries": sorted((ds.get("queries") or {}).keys()),
            "default_max_bytes_billed": ds.get("default_max_bytes_billed"),
        }
        return QueryResult(ds["dataset_id"], [row], meta)

    def _usdt_sql_template(self, ds: dict[str, Any], params: dict[str, Any]) -> QueryResult:
        query_name = str(params.get("query", "daily_recent")).strip()
        query_path = self._usdt_query_path(ds, query_name)
        sql = query_path.read_text(encoding="utf-8")
        row = {
            "query": query_name,
            "path": str(query_path),
            "sql": sql,
            "cost_control": "bounded template; dry-run before execution",
        }
        return QueryResult(ds["dataset_id"], [row], {"query": query_name, "bytes_billed_guard": ds.get("default_max_bytes_billed")})

    def _usdt_local_sample(self, ds: dict[str, Any], params: dict[str, Any]) -> QueryResult:
        latest = self._latest_usdt_sample(ds)
        limit = min(int(params.get("limit", 20)), 500)
        if not latest:
            return QueryResult(ds["dataset_id"], [], {"error": "missing local RPC sample; run scripts/usdt_catalogue/rpc_usdt_transfer_pilot.py first"})
        manifest_path = Path(latest["manifest_path"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        rows = list(manifest.get("sample_rows", []))[:limit]
        return QueryResult(
            ds["dataset_id"],
            rows,
            {
                "source": "local_rpc_pilot_manifest",
                "manifest_path": str(manifest_path),
                "transfer_count": manifest.get("transfer_count"),
                "from_block": manifest.get("from_block"),
                "to_block": manifest.get("to_block"),
                "created_at": manifest.get("created_at"),
                "returned": len(rows),
            },
        )

    def _usdt_bigquery_job(self, ds: dict[str, Any], params: dict[str, Any], run: bool) -> QueryResult:
        try:
            from google.cloud import bigquery
            from google.auth.exceptions import DefaultCredentialsError
        except Exception as exc:
            return QueryResult(ds["dataset_id"], [], {"error": "missing google-cloud-bigquery", "install": "python3 -m pip install --user google-cloud-bigquery", "detail": str(exc)})

        project = self._bigquery_project(params)
        if not project:
            return QueryResult(ds["dataset_id"], [], {"error": "missing BigQuery project", "set": "GOOGLE_CLOUD_PROJECT or ?project=YOUR_PROJECT"})
        if not self._has_google_adc_hint():
            return QueryResult(
                ds["dataset_id"],
                [],
                {
                    "error": "missing Google Application Default Credentials",
                    "fix": "run `gcloud auth application-default login` or set GOOGLE_APPLICATION_CREDENTIALS to a service-account JSON",
                    "detail": "No GOOGLE_APPLICATION_CREDENTIALS and no local gcloud ADC file found.",
                },
            )

        query_name = str(params.get("query", "daily_recent")).strip()
        sql = self._usdt_query_path(ds, query_name).read_text(encoding="utf-8")
        location = str(params.get("location", ds.get("location", "US")))
        max_bytes = int(params.get("max_bytes_billed", ds.get("default_max_bytes_billed", 10 * 1024 * 1024 * 1024)))

        try:
            client = bigquery.Client(project=project, location=location)
        except DefaultCredentialsError as exc:
            return QueryResult(
                ds["dataset_id"],
                [],
                {
                    "error": "missing Google Application Default Credentials",
                    "fix": "run `gcloud auth application-default login` or set GOOGLE_APPLICATION_CREDENTIALS to a service-account JSON",
                    "detail": str(exc),
                },
            )

        dry_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        dry_job = client.query(sql, job_config=dry_config, location=location)
        dry_meta = {
            "mode": "dry_run" if not run else "run",
            "query": query_name,
            "project": project,
            "location": location,
            "total_bytes_processed": dry_job.total_bytes_processed,
            "estimated_tib_processed": self._bytes_to_tib(dry_job.total_bytes_processed),
            "estimated_usd_on_demand_before_free_tier": self._estimated_bigquery_usd(dry_job.total_bytes_processed),
            "free_tier_note": "The first 1 TiB per month is free in aggregate; remaining monthly allowance is account-specific.",
            "maximum_bytes_billed": max_bytes,
            "within_execution_guard": dry_job.total_bytes_processed <= max_bytes,
        }
        if not run:
            return QueryResult(ds["dataset_id"], [], dry_meta)

        if str(params.get("confirm", "")).lower() != "execute":
            dry_meta["error"] = "run action requires confirm=execute"
            return QueryResult(ds["dataset_id"], [], dry_meta)

        max_results = min(int(params.get("max_results", 1000)), 10000)
        run_config = bigquery.QueryJobConfig(use_query_cache=True, maximum_bytes_billed=max_bytes)
        query_job = client.query(sql, job_config=run_config, location=location)
        rows_iter = query_job.result(max_results=max_results)
        rows = [dict(row) for row in rows_iter]
        dry_meta.update({"job_id": query_job.job_id, "returned": len(rows), "actual_bytes_processed": query_job.total_bytes_processed})
        return QueryResult(ds["dataset_id"], rows, dry_meta)

    def _usdt_query_path(self, ds: dict[str, Any], query_name: str) -> Path:
        queries = ds.get("queries") or {}
        if query_name not in queries:
            raise KeyError(f"unknown USDT query template: {query_name}")
        path = self._resolve(queries[query_name])
        if not path.exists():
            raise FileNotFoundError(f"missing SQL template: {path}")
        return path

    def _latest_usdt_sample(self, ds: dict[str, Any]) -> dict[str, Any] | None:
        root = self._resolve(ds.get("sample_root", "data/usdt_catalogue/pilot"))
        if not root.exists():
            return None
        manifests = sorted(root.glob("*.manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not manifests:
            return None
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
        return {
            "exists": True,
            "manifest_path": str(manifests[0]),
            "transfer_count": manifest.get("transfer_count"),
            "from_block": manifest.get("from_block"),
            "to_block": manifest.get("to_block"),
            "created_at": manifest.get("created_at"),
            "parquet_path": manifest.get("parquet_path"),
            "csv_path": manifest.get("csv_path"),
            "endpoint": manifest.get("endpoint"),
        }

    def _bigquery_project(self, params: dict[str, Any]) -> str:
        from scripts.research_data_mcp.bigquery_client import resolve_project

        explicit = str(params.get("project") or "").strip()
        return explicit or resolve_project()

    def _google_adc_status(self) -> dict[str, Any]:
        try:
            import google.auth
            credentials, project = google.auth.default()
            return {"available": True, "project": project, "credentials_type": type(credentials).__name__}
        except Exception as exc:
            return {"available": False, "error": type(exc).__name__, "message": str(exc)[:300]}

    def _has_google_adc_hint(self) -> bool:
        if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            return True
        config = Path(os.environ.get("CLOUDSDK_CONFIG", Path.home() / ".config" / "gcloud"))
        return (config / "application_default_credentials.json").exists()

    def _bytes_to_tib(self, value: int) -> float:
        return value / float(1024**4)

    def _estimated_bigquery_usd(self, bytes_processed: int) -> float:
        return self._bytes_to_tib(bytes_processed) * 6.25

    def _interpret_prompt(self, prompt: str) -> dict[str, Any]:
        p = prompt.lower()
        proxy_types = []
        if any(x in p for x in ["brand", "awareness", "consumer", "marketing"]):
            proxy_types.extend(["search_interest", "news_mentions", "social_discussion", "web_attention", "sales_or_registration_data"])
        if any(x in p for x in ["crypto", "nft", "opensea", "coingecko", "market"]):
            proxy_types.extend(["price_volume_panel", "news_shock_context", "onchain_activity", "social_attention"])
        if any(x in p for x in ["labor", "job", "upwork", "104"]):
            proxy_types.extend(["job_postings", "platform_demand", "skill_mentions", "wage_rates"])
        if not proxy_types:
            proxy_types = ["news_mentions", "search_interest", "public_datasets", "repository_records"]
        return {
            "likely_proxy_types": sorted(set(proxy_types)),
            "survey_replacement_potential": "high_for_observable_attention_or_behavior_low_for_private_motivation",
        }

    def _query_local_json_file(self, ds: dict[str, Any], params: dict[str, Any]) -> QueryResult:
        path = self._resolve(ds["local_path"])
        if not path.exists():
            return QueryResult(ds["dataset_id"], [], {"error": f"missing json path: {path}", "params": params})
        payload = json.loads(path.read_text(encoding="utf-8"))
        fields = [x.strip() for x in str(params.get("fields", "")).split(",") if x.strip()]
        if fields:
            row = {k: self._dig(payload, k) for k in fields}
        else:
            row = payload
        return QueryResult(ds["dataset_id"], [row], {"path": str(path), "returned": 1, "params": params})

    def _query_local_csv_file(self, ds: dict[str, Any], params: dict[str, Any]) -> QueryResult:
        import pandas as pd

        pattern = str(ds.get("local_path") or "").strip()
        limit = min(int(params.get("limit", 100)), 5000)
        if "*" in pattern:
            matches = sorted(Path(p) for p in globmod.glob(str(self._resolve(pattern))))
            path = next((p for p in matches if p.suffix.lower() == ".csv"), matches[0] if matches else None)
        else:
            path = self._resolve(pattern)
        if not path or not Path(path).is_file():
            return QueryResult(ds["dataset_id"], [], {"error": f"missing csv: {pattern}", "params": params})
        path = Path(path)
        df = pd.read_csv(path, nrows=limit)
        rows = json.loads(df.to_json(orient="records"))
        return QueryResult(
            ds["dataset_id"],
            rows,
            {"path": str(path.relative_to(self.repo_root)), "returned": len(rows), "params": params},
        )

    def _query_local_file_tree(self, ds: dict[str, Any], params: dict[str, Any]) -> QueryResult:
        root = self._resolve(ds["local_path"])
        limit = int(params.get("limit", 50))
        if not root.exists():
            return QueryResult(ds["dataset_id"], [], {"error": f"missing path: {root}", "params": params})
        rows: list[dict[str, Any]] = []
        if root.is_file():
            rel = str(root.relative_to(self.repo_root))
            rows.append({"path": rel, "file": root.name, "bytes": root.stat().st_size})
            if root.suffix.lower() == ".csv" and str(params.get("read_csv", "false")).lower() in {"1", "true", "yes"}:
                import pandas as pd

                df = pd.read_csv(root, nrows=min(limit, 200))
                rows = json.loads(df.to_json(orient="records"))
            return QueryResult(ds["dataset_id"], rows[:limit], {"path": rel, "returned": len(rows[:limit]), "params": params})
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            try:
                rel = str(path.relative_to(self.repo_root))
            except ValueError:
                rel = str(path)
            rows.append({"path": rel, "file": path.name, "bytes": path.stat().st_size})
            if len(rows) >= limit:
                break
        return QueryResult(ds["dataset_id"], rows, {"root": str(root), "returned": len(rows), "params": params})

    def _query_local_json_glob(self, ds: dict[str, Any], params: dict[str, Any]) -> QueryResult:
        pattern = str(ds.get("local_path") or ds.get("local_glob") or "").strip()
        if not pattern:
            return QueryResult(ds["dataset_id"], [], {"error": "missing local_path glob pattern", "params": params})
        matches = sorted(Path(p) for p in globmod.glob(str(self._resolve(pattern))))
        ticker = str(params.get("ticker") or params.get("filter_ticker") or "").upper().strip()
        file_name = str(params.get("file") or params.get("filename") or "").strip()
        limit = int(params.get("limit", 50))
        include_payload = str(params.get("include_payload", "false")).lower() in {"1", "true", "yes"}
        metadata_only = str(params.get("metadata_only", "")).lower()
        if not metadata_only:
            metadata_only = "true" if ds.get("analysis_readiness") == "metadata_search" and not include_payload else "false"
        metadata_only = metadata_only in {"1", "true", "yes"}

        rows: list[dict[str, Any]] = []
        for path in matches:
            stem = path.stem.upper()
            if ticker and ticker not in stem and ticker not in path.name.upper():
                continue
            if file_name and file_name not in path.name:
                continue
            try:
                rel = str(path.relative_to(self.repo_root))
            except ValueError:
                rel = str(path)
            row: dict[str, Any] = {"path": rel, "file": path.name, "bytes": path.stat().st_size}
            if path.suffix.lower() == ".json":
                if metadata_only:
                    try:
                        payload = json.loads(path.read_text(encoding="utf-8"))
                        if isinstance(payload, dict):
                            row["keys"] = list(payload.keys())[:30]
                            for key in ("name", "cik", "ticker", "title", "entityType"):
                                if key in payload:
                                    row[key] = payload[key]
                        else:
                            row["json_type"] = type(payload).__name__
                    except Exception as exc:
                        row["parse_error"] = str(exc)
                else:
                    row["payload"] = json.loads(path.read_text(encoding="utf-8"))
            rows.append(row)
            if len(rows) >= limit:
                break
        return QueryResult(
            ds["dataset_id"],
            rows,
            {
                "pattern": pattern,
                "matched": len(matches),
                "returned": len(rows),
                "metadata_only": metadata_only,
                "params": params,
            },
        )

    def _dig(self, obj: Any, dotted: str) -> Any:
        cur = obj
        for part in dotted.split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
        return cur

    def _query_jsonl_payment_ledger(self, ds: dict[str, Any], params: dict[str, Any]) -> QueryResult:
        path = self._resolve(ds["local_path"])
        payment_kind = str(params.get("payment_kind", "")).upper().strip()
        payee = str(params.get("payee", "")).lower().strip()
        payer = str(params.get("payer", "")).lower().strip()
        min_spk = params.get("min_spk")
        order_by = str(params.get("order_by", "payment_id"))
        descending = str(params.get("descending", "false")).lower() in {"1", "true", "yes"}
        limit = int(params.get("limit", 100))
        rows: list[dict[str, Any]] = []
        scanned = 0
        if not path.exists():
            return QueryResult(ds["dataset_id"], [], {"error": f"missing ledger path: {path}", "params": params})
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                scanned += 1
                row = json.loads(line)
                if payment_kind and str(row.get("payment_kind", "")).upper() != payment_kind:
                    continue
                if payee and payee not in str(row.get("payee", "")).lower():
                    continue
                if payer and payer not in str(row.get("payer", "")).lower():
                    continue
                if min_spk is not None and float(row.get("spk", 0)) < float(min_spk):
                    continue
                rows.append(row)
        if order_by:
            rows.sort(key=lambda r: self._sort_key(r.get(order_by, "")), reverse=descending)
        rows = rows[:limit]
        return QueryResult(ds["dataset_id"], rows, {"scanned": scanned, "returned": len(rows), "params": params})

    def _query_coingecko_simple_price(self, ds: dict[str, Any], params: dict[str, Any]) -> QueryResult:
        ids = str(params.get("ids", "bitcoin,ethereum")).strip()
        vs = str(params.get("vs_currencies", "usd")).strip()
        include_market_cap = str(params.get("include_market_cap", "true")).lower()
        include_24hr_vol = str(params.get("include_24hr_vol", "true")).lower()
        query = urllib.parse.urlencode({
            "ids": ids,
            "vs_currencies": vs,
            "include_market_cap": include_market_cap,
            "include_24hr_vol": include_24hr_vol,
            "include_24hr_change": "true",
            "include_last_updated_at": "true",
        })
        url = f"https://api.coingecko.com/api/v3/simple/price?{query}"
        req = urllib.request.Request(url, headers={"User-Agent": "research-query-engine/0.1"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        rows = []
        now = datetime.now(timezone.utc).isoformat()
        for coin_id, payload in data.items():
            row = {"coin_id": coin_id, "queried_at": now}
            row.update(payload)
            rows.append(row)
        return QueryResult(ds["dataset_id"], rows, {"remote_url": url, "returned": len(rows), "params": params})

    def _sort_key(self, value: Any):
        s = str(value)
        try:
            return float(s)
        except Exception:
            return s

    def _resolve_panel_path(self, ds: dict[str, Any], params: dict[str, Any]) -> tuple[Path, str]:
        run_id = str(params.get("run_id") or ds.get("default_run_id") or "").strip()
        root = self._resolve(ds["local_root"])
        if not root.exists():
            raise FileNotFoundError(f"missing panel root: {root}")
        file_name = str(params.get("panel_file") or ds.get("local_file") or f"{ds['dataset_id']}.parquet")
        if run_id and file_name.startswith(f"{run_id}/"):
            file_name = file_name.split("/", 1)[1]

        if not run_id:
            direct = root / file_name
            if direct.exists():
                return direct, root.name
            csv_direct = direct.with_suffix(".csv")
            if csv_direct.exists():
                return csv_direct, root.name
            # Path-style local_file (e.g. processed/foo.parquet) — do not treat sibling dirs as run_id.
            if "/" in file_name or "\\" in file_name:
                raise FileNotFoundError(f"missing panel file: {direct}")
            candidates = [p for p in root.iterdir() if p.is_dir()]
            if not candidates:
                raise FileNotFoundError(f"no run directories under {root}")
            run_dir = sorted(candidates, key=lambda p: p.stat().st_mtime)[-1]
        else:
            run_dir = root / run_id

        path = run_dir / file_name
        if not path.exists():
            csv_path = path.with_suffix(".csv")
            if csv_path.exists():
                path = csv_path
            else:
                raise FileNotFoundError(f"missing panel file: {path}")
        return path, run_dir.name

    def _query_local_parquet_panel(self, ds: dict[str, Any], params: dict[str, Any]) -> QueryResult:
        import pandas as pd

        path, run_id = self._resolve_panel_path(ds, params)
        time_field = str(ds.get("time_field") or "date")
        limit = min(int(params.get("limit", 100)), int(ds.get("max_limit", 5000)))
        order_by = str(params.get("order_by", time_field))
        descending = str(params.get("descending", "false")).lower() in {"1", "true", "yes"}
        start_date = str(params.get("start_date", "")).strip()
        end_date = str(params.get("end_date", "")).strip()
        columns = [c.strip() for c in str(params.get("columns", "")).split(",") if c.strip()]

        if path.suffix.lower() == ".parquet":
            df = pd.read_parquet(path)
        else:
            df = pd.read_csv(path)

        if time_field in df.columns:
            df[time_field] = pd.to_datetime(df[time_field], errors="coerce").dt.strftime("%Y-%m-%d")

        country_field = str(ds.get("country_field") or "country_iso3")
        ticker_field = str(ds.get("ticker_field") or "yahoo_symbol")
        countries = {x.strip().upper() for x in str(params.get("countries", params.get("country", ""))).split(",") if x.strip()}
        tickers = {x.strip().upper() for x in str(params.get("tickers", params.get("ticker", params.get("yahoo_symbol", "")))).split(",") if x.strip()}

        if countries and country_field in df.columns:
            df[country_field] = df[country_field].astype(str).str.upper()
            df = df[df[country_field].isin(countries)]
        if tickers and ticker_field in df.columns:
            df[ticker_field] = df[ticker_field].astype(str).str.upper()
            df = df[df[ticker_field].isin(tickers)]

        entity_fields = [str(f).strip() for f in (ds.get("entity_fields") or []) if str(f).strip()]
        param_aliases = {"ric": ["ric", "constituent_ric"], "ticker": [ticker_field, "ric", "constituent_ric"]}
        seen_fields: set[str] = set()
        for field in entity_fields:
            raw = params.get(field)
            if raw is None and field in param_aliases:
                for alt in param_aliases[field]:
                    if alt in params:
                        raw = params[alt]
                        field = alt
                        break
            if raw is None or field in seen_fields:
                continue
            seen_fields.add(field)
            values = {x.strip() for x in str(raw).split(",") if x.strip()}
            if not values or field not in df.columns:
                continue
            col = df[field]
            if field.startswith("in_"):
                want_one = str(raw).strip().lower() in {"1", "true", "yes"}
                df = df[col.fillna(0).astype(float).astype(int) == (1 if want_one else 0)]
            else:
                upper_vals = {v.upper() for v in values}
                df = df[col.astype(str).str.upper().isin(upper_vals)]

        if start_date and time_field in df.columns:
            df = df[df[time_field].astype(str) >= start_date]
        if end_date and time_field in df.columns:
            df = df[df[time_field].astype(str) <= end_date]

        if order_by in df.columns:
            df = df.sort_values(order_by, ascending=not descending, kind="mergesort")

        if columns:
            keep = [c for c in columns if c in df.columns]
            if keep:
                df = df[keep]

        rows = json.loads(df.head(limit).to_json(orient="records"))
        return QueryResult(
            ds["dataset_id"],
            rows,
            {
                "panel_path": str(path),
                "run_id": run_id,
                "rows_total_after_filter": int(len(df)),
                "returned": len(rows),
                "params": params,
            },
        )

    def _query_collection_ops_status(self, ds: dict[str, Any], params: dict[str, Any]) -> QueryResult:
        from .ops_status import collection_queue_status

        payload = collection_queue_status(self.repo_root)
        return QueryResult(ds["dataset_id"], [payload], {"returned": 1, "params": params})

    def _query_datacite_local_harvest_status(self, ds: dict[str, Any], params: dict[str, Any]) -> QueryResult:
        from .ops_status import datacite_local_harvest_status

        lane = str(params.get("lane", "")).strip()
        payload = datacite_local_harvest_status(self.repo_root, lane=lane)
        return QueryResult(ds["dataset_id"], [payload], {"returned": 1, "lane": lane, "params": params})


def parse_kv_args(items: list[str]) -> dict[str, str]:
    out = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"expected key=value, got: {item}")
        k, v = item.split("=", 1)
        out[k] = v
    return out
