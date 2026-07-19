#!/usr/bin/env python3
"""Resumable metadata-only harvest for large external dataset indexes.

This does not download dataset payloads. It writes compressed JSONL metadata records
per source and checkpoint files so the run can be resumed.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

UA = "research-data-hub-full-index/0.1"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)


def request_json(url: str, timeout: int = 90, retries: int = 6) -> Any:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as exc:
            last_error = exc
            if attempt + 1 >= retries:
                break
            time.sleep(min(60, 2 ** attempt))
    raise RuntimeError(f"request failed after {retries} attempts: {last_error!r}")


def clean(v: Any, limit: int = 3000) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        v = " ".join(str(x) for x in v if x is not None)
    return " ".join(str(v).split())[:limit]


def infer_domain(title: str, description: str = "", tags: Iterable[str] = ()) -> str:
    text = " ".join([clean(title), clean(description), " ".join(clean(tag, 500) for tag in tags)]).lower()
    checks = [
        ("crypto_finance", ["crypto", "bitcoin", "ethereum", "nft", "blockchain", "token", "stablecoin"]),
        ("finance_economics", ["finance", "financial", "market", "stock", "economic", "trade", "bank", "monetary", "inflation"]),
        ("news_media", ["news", "media", "journalism", "gdelt"]),
        ("social_web", ["twitter", "reddit", "social", "survey", "consumer", "public opinion"]),
        ("climate_geo", ["climate", "weather", "geospatial", "satellite", "earth", "ocean", "forest"]),
        ("health_bio", ["health", "clinical", "medical", "genome", "biology", "protein"]),
        ("machine_learning", ["machine learning", "benchmark", "nlp", "computer vision", "deep learning"]),
    ]
    for domain, terms in checks:
        if any(t in text for t in terms):
            return domain
    return "general"


def access_for_source(source: str) -> str:
    if source in {"huggingface", "openml", "openaire", "datacite", "openalex", "wikidata"}:
        return "query_remote"
    if source in {"aws_open_data_registry", "google_dataset_search", "re3data"}:
        return "reference_only"
    return "sample_probe"


def record(source: str, source_kind: str, dataset_id: str, title: str, url: str, description: str = "", tags: list[str] | None = None, raw: dict[str, Any] | None = None) -> dict[str, Any]:
    tags = [clean(tag, 500) for tag in (tags or [])]
    tags = [tag for tag in tags if tag]
    dataset_id = clean(dataset_id, 500)
    title = clean(title, 500)
    description = clean(description)
    url = clean(url, 3000)
    access = access_for_source(source)
    return {
        "catalogue_version": "full-index-0.1",
        "harvested_at": now(),
        "source": source,
        "source_kind": source_kind,
        "dataset_id": dataset_id,
        "title": title,
        "description": description,
        "url": url,
        "tags": tags[:100],
        "domain": infer_domain(title, description, tags),
        "access_mode": access,
        "analysis_readiness": "instant_or_minutes" if access == "query_remote" else "metadata_only",
    }


class Writer:
    def __init__(self, out_dir: Path, source: str):
        self.out_dir = out_dir
        self.source = source
        self.path = out_dir / f"{source}.jsonl.gz"
        self.count = 0
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.f = gzip.open(self.path, "at", encoding="utf-8")

    def write(self, rec: dict[str, Any]) -> None:
        self.f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
        self.count += 1

    def close(self) -> None:
        self.f.close()


class ChunkWriter:
    def __init__(self, out_dir: Path, source: str, chunk_size: int, start_index: int = 0):
        self.out_dir = out_dir
        self.source = source
        self.chunk_size = chunk_size
        self.chunk_index = start_index
        self.chunk_count = 0
        self.total_count = 0
        self.f = None
        self.partial_path: Path | None = None
        self.completed: list[dict[str, Any]] = []
        self.out_dir.mkdir(parents=True, exist_ok=True)
        for stale in self.out_dir.glob(f"{self.source}_*.jsonl.gz.partial"):
            stale.unlink(missing_ok=True)

    def _open(self) -> None:
        self.partial_path = self.out_dir / f"{self.source}_{self.chunk_index:06d}.jsonl.gz.partial"
        self.f = gzip.open(self.partial_path, "wt", encoding="utf-8")

    def write(self, rec: dict[str, Any]) -> None:
        if self.f is None:
            self._open()
        self.f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
        self.chunk_count += 1
        self.total_count += 1

    def finalize_chunk(self) -> dict[str, Any] | None:
        if self.f is None or self.partial_path is None or self.chunk_count == 0:
            return None
        self.f.close()
        final_path = self.partial_path.with_suffix("")
        with gzip.open(self.partial_path, "rt", encoding="utf-8") as check:
            validated = sum(1 for _ in check)
        if validated != self.chunk_count:
            raise RuntimeError(f"chunk validation mismatch: expected={self.chunk_count} actual={validated}")
        digest = hashlib.sha256(self.partial_path.read_bytes()).hexdigest()
        self.partial_path.replace(final_path)
        info = {
            "chunk_index": self.chunk_index,
            "path": str(final_path),
            "records": validated,
            "bytes": final_path.stat().st_size,
            "sha256": digest,
        }
        self.completed.append(info)
        self.chunk_index += 1
        self.chunk_count = 0
        self.f = None
        self.partial_path = None
        return info

    def close(self) -> dict[str, Any] | None:
        return self.finalize_chunk()


def save_checkpoint(out_dir: Path, source: str, state: dict[str, Any]) -> None:
    write_json_atomic(out_dir / f"{source}.checkpoint.json", {"updated_at": now(), **state})


def save_heartbeat(out_dir: Path, source: str, state: dict[str, Any]) -> None:
    write_json_atomic(out_dir / f"{source}.heartbeat.json", {"updated_at": now(), **state})


def quarantine_record(out_dir: Path, source: str, cursor: str, item: Any, exc: Exception) -> None:
    payload = {
        "quarantined_at": now(),
        "source": source,
        "cursor": cursor,
        "dataset_id": clean(item.get("id", ""), 500) if isinstance(item, dict) else "",
        "error": repr(exc),
        "raw": item,
    }
    with (out_dir / f"{source}.quarantine.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n")


def load_checkpoint(out_dir: Path, source: str) -> dict[str, Any]:
    p = out_dir / f"{source}.checkpoint.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def should_stop(count: int, max_records: int) -> bool:
    return max_records > 0 and count >= max_records


def harvest_datacite(out_dir: Path, max_records: int, page_size: int, sleep: float, chunk_size: int = 50000, created_years: str = "", datacite_query: str = "") -> int:
    source = "datacite"
    state = load_checkpoint(out_dir, source)
    cursor = state.get("cursor", "1")
    total = 0
    chunk_index = int(state.get("next_chunk_index", 0))
    committed_total = int(state.get("committed_records", 0))
    quarantined_total = int(state.get("quarantined_records", 0))
    started = time.monotonic()
    w = ChunkWriter(out_dir, source, chunk_size, chunk_index)
    try:
        while True:
            params = {"resource-types": "dataset", "page[size]": min(page_size, 1000), "page[cursor]": cursor}
            if created_years:
                params["created"] = created_years
            if datacite_query:
                params["query"] = datacite_query
            data = request_json("https://api.datacite.org/dois?" + urllib.parse.urlencode(params))
            page_items = data.get("data", [])
            for item in page_items:
                try:
                    attrs = item.get("attributes", {}) if isinstance(item, dict) else {}
                    title = ""
                    titles = attrs.get("titles") or []
                    if titles and isinstance(titles[0], dict):
                        title = titles[0].get("title", "")
                    desc = ""
                    descriptions = attrs.get("descriptions") or []
                    if descriptions and isinstance(descriptions[0], dict):
                        desc = descriptions[0].get("description", "")
                    tags = [clean(s.get("subject", ""), 500) for s in attrs.get("subjects") or [] if isinstance(s, dict)]
                    tags = [tag for tag in tags if tag]
                    doi = item.get("id", "") if isinstance(item, dict) else ""
                    w.write(record(source, "doi_metadata", doi, title or doi, attrs.get("url") or f"https://doi.org/{clean(doi)}", desc, tags, item))
                    total += 1
                except Exception as exc:
                    quarantined_total += 1
                    quarantine_record(out_dir, source, cursor, item, exc)
                    continue
                if should_stop(total, max_records):
                    latest = w.close()
                    if latest:
                        committed_total += latest["records"]
                        chunk_index += 1
                    save_checkpoint(out_dir, source, {"cursor": cursor, "committed_records": committed_total, "quarantined_records": quarantined_total, "next_chunk_index": chunk_index, "records_written_this_run": total, "last_chunk": latest, "stopped": "max_records"})
                    return total
            next_url = data.get("links", {}).get("next")
            if not next_url:
                latest = w.close()
                if latest:
                    committed_total += latest["records"]
                    chunk_index += 1
                save_checkpoint(out_dir, source, {"cursor": cursor, "committed_records": committed_total, "quarantined_records": quarantined_total, "next_chunk_index": chunk_index, "records_written_this_run": total, "last_chunk": latest, "stopped": "no_next"})
                write_json_atomic(out_dir / f"{source}.complete.json", {"completed_at": now(), "committed_records": committed_total, "quarantined_records": quarantined_total})
                return total
            parsed = urllib.parse.urlparse(next_url)
            q = urllib.parse.parse_qs(parsed.query)
            next_cursor = (q.get("page[cursor]") or q.get("page%5Bcursor%5D") or [cursor])[0]
            if w.chunk_count >= chunk_size:
                latest = w.finalize_chunk()
                committed_total += latest["records"]
                chunk_index = latest["chunk_index"] + 1
                save_checkpoint(out_dir, source, {
                    "cursor": next_cursor,
                    "committed_records": committed_total,
                    "quarantined_records": quarantined_total,
                    "next_chunk_index": chunk_index,
                    "last_chunk": latest,
                })
            elapsed = max(time.monotonic() - started, 0.001)
            save_heartbeat(out_dir, source, {
                "cursor": cursor,
                "next_cursor": next_cursor,
                "page_records": len(page_items),
                "records_written_this_run": total,
                "committed_records": committed_total,
                "uncommitted_records": w.chunk_count,
                "quarantined_records": quarantined_total,
                "records_per_second": round(total / elapsed, 3),
            })
            cursor = next_cursor
            time.sleep(sleep)
    finally:
        if w.f is not None:
            w.f.close()


def harvest_openaire(out_dir: Path, max_records: int, page_size: int, sleep: float) -> int:
    source = "openaire"
    page = int(load_checkpoint(out_dir, source).get("page", 1))
    total = 0
    w = Writer(out_dir, source)
    try:
        while True:
            params = {"page": page, "size": min(page_size, 100), "format": "json"}
            data = request_json("https://api.openaire.eu/search/datasets?" + urllib.parse.urlencode(params))
            results = data.get("response", {}).get("results", {}).get("result", [])
            if isinstance(results, dict):
                results = [results]
            if not results:
                save_checkpoint(out_dir, source, {"page": page, "records_written_this_run": total, "stopped": "no_results"})
                return total
            for item in results:
                md = item.get("metadata", {}).get("oaf:entity", {}).get("oaf:result", {})
                title = clean(md.get("title", {}).get("$", "") if isinstance(md.get("title"), dict) else md.get("title", ""))
                desc = clean(md.get("description", {}).get("$", "") if isinstance(md.get("description"), dict) else md.get("description", ""))
                pid = clean(md.get("pid", {}).get("$", "") if isinstance(md.get("pid"), dict) else "")
                url = "https://explore.openaire.eu/search/dataset?pid=" + urllib.parse.quote(pid) if pid else "https://explore.openaire.eu/"
                w.write(record(source, "scholarly_dataset_graph", pid or title, title or pid or "OpenAIRE dataset", url, desc, [], item))
                total += 1
                if should_stop(total, max_records):
                    save_checkpoint(out_dir, source, {"page": page, "records_written_this_run": total, "stopped": "max_records"})
                    return total
            page += 1
            save_checkpoint(out_dir, source, {"page": page, "records_written_this_run": total})
            time.sleep(sleep)
    finally:
        w.close()


def harvest_openml(out_dir: Path, max_records: int, page_size: int, sleep: float) -> int:
    source = "openml"
    offset = int(load_checkpoint(out_dir, source).get("offset", 0))
    total = 0
    w = Writer(out_dir, source)
    try:
        while True:
            url = f"https://www.openml.org/api/v1/json/data/list/limit/{min(page_size,10000)}/offset/{offset}"
            data = request_json(url)
            items = data.get("data", {}).get("dataset", [])
            if not items:
                save_checkpoint(out_dir, source, {"offset": offset, "records_written_this_run": total, "stopped": "no_results"})
                return total
            for item in items:
                did = str(item.get("did", ""))
                name = item.get("name", did)
                tags = []
                if item.get("tag"):
                    tags = item.get("tag") if isinstance(item.get("tag"), list) else [str(item.get("tag"))]
                w.write(record(source, "ml_dataset_repository", did, name, f"https://www.openml.org/d/{did}", json.dumps({k: item.get(k) for k in ["NumberOfInstances", "NumberOfFeatures", "format"]}, sort_keys=True), tags, item))
                total += 1
                if should_stop(total, max_records):
                    save_checkpoint(out_dir, source, {"offset": offset, "records_written_this_run": total, "stopped": "max_records"})
                    return total
            offset += len(items)
            save_checkpoint(out_dir, source, {"offset": offset, "records_written_this_run": total})
            time.sleep(sleep)
    finally:
        w.close()


def harvest_huggingface(out_dir: Path, max_records: int, page_size: int, sleep: float) -> int:
    source = "huggingface"
    # HF public API pagination is less stable; use pages by offset-ish cursor where available.
    limit = max_records if max_records > 0 else 10000
    url = "https://huggingface.co/api/datasets?" + urllib.parse.urlencode({"limit": min(limit, 10000), "full": "true"})
    data = request_json(url)
    w = Writer(out_dir, source)
    total = 0
    try:
        for item in data:
            did = item.get("id", "")
            tags = [str(x) for x in item.get("tags", [])]
            desc = item.get("description") or item.get("cardData", {}).get("description", "")
            w.write(record(source, "ml_dataset_repository", did, did, f"https://huggingface.co/datasets/{did}", desc, tags, item))
            total += 1
            if should_stop(total, max_records):
                break
        save_checkpoint(out_dir, source, {"records_written_this_run": total, "stopped": "api_page_complete"})
        return total
    finally:
        w.close()


def harvest_aws(out_dir: Path, max_records: int, page_size: int, sleep: float) -> int:
    source = "aws_open_data_registry"
    data = request_json("https://api.github.com/repos/awslabs/open-data-registry/contents/datasets")
    w = Writer(out_dir, source)
    total = 0
    try:
        for item in data:
            name = item.get("name", "")
            if not name.endswith(".yaml"):
                continue
            did = name[:-5]
            w.write(record(source, "cloud_open_data_registry", did, did.replace("-", " "), item.get("html_url", ""), "AWS Open Data Registry YAML metadata entry", ["aws", "open-data"], item))
            total += 1
            if should_stop(total, max_records):
                break
        save_checkpoint(out_dir, source, {"records_written_this_run": total, "stopped": "complete_or_max"})
        return total
    finally:
        w.close()


HARVESTERS = {
    "datacite": harvest_datacite,
    "openaire": harvest_openaire,
    "openml": harvest_openml,
    "huggingface": harvest_huggingface,
    "aws_open_data_registry": harvest_aws,
}


def write_manifest(out_dir: Path, results: dict[str, Any]) -> None:
    files = []
    for p in sorted(out_dir.glob("*.jsonl.gz")):
        files.append({"source": p.name.replace(".jsonl.gz", ""), "path": str(p), "bytes": p.stat().st_size})
    manifest = {"generated_at": now(), "results": results, "files": files}
    (out_dir / "full_index_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="data_lake/dataset_catalog/full_index")
    ap.add_argument("--sources", default="datacite,openaire,openml,huggingface,aws_open_data_registry")
    ap.add_argument("--max-records-per-source", type=int, default=0, help="0 means unlimited where API supports it")
    ap.add_argument("--page-size", type=int, default=500)
    ap.add_argument("--sleep", type=float, default=0.2)
    ap.add_argument("--datacite-created-years", default="")
    ap.add_argument("--datacite-query", default="")
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {}
    had_error = False
    for source in [s.strip() for s in args.sources.split(",") if s.strip()]:
        fn = HARVESTERS[source]
        print(f"source_start={source} at={now()}", flush=True)
        try:
            if source == "datacite":
                n = fn(out_dir, args.max_records_per_source, args.page_size, args.sleep, created_years=args.datacite_created_years, datacite_query=args.datacite_query)
            else:
                n = fn(out_dir, args.max_records_per_source, args.page_size, args.sleep)
            results[source] = {"records_written_this_run": n, "status": "ok"}
            print(f"source_done={source} records={n} at={now()}", flush=True)
        except Exception as exc:
            had_error = True
            results[source] = {"status": "error", "error": repr(exc)}
            print(f"source_error={source} error={exc!r} at={now()}", flush=True)
        write_manifest(out_dir, results)
    return 1 if had_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
