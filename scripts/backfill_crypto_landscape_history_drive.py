#!/usr/bin/env python3
"""Drive-first historical crypto landscape backfill.

This backfill is intentionally file-granular and resumable. Each raw response and
normalized CSV is uploaded immediately to Google Drive, then deleted locally.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


DEFAULT_DRIVE_ROOT = "gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/collection/markets/crypto-landscape/historical_backfill"
DEFAULT_STAGE_ROOT = Path("/tmp/sharpe_crypto_landscape_history")
USER_AGENT = "Sharpe-Renaissance crypto-landscape-history/1.0 research-contact=local@example.invalid"
REPO = Path(__file__).resolve().parents[1]
LOCAL_COINGECKO_DB = REPO / "data_lake/coingecko_archive/coingecko_full_active_2009.sqlite3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drive-root", default=DEFAULT_DRIVE_ROOT)
    parser.add_argument("--stage-root", type=Path, default=DEFAULT_STAGE_ROOT)
    parser.add_argument("--state-dir", type=Path, default=REPO / "logs/crypto_landscape_history_backfill")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--sleep", type=float, default=1.25)
    parser.add_argument("--max-protocols", type=int, default=0, help="0 means all discovered protocols.")
    parser.add_argument("--protocol-shards", type=int, default=1, help="Number of disjoint protocol shards to run.")
    parser.add_argument("--protocol-shard-index", type=int, default=0, help="Zero-based protocol shard index for this worker.")
    parser.add_argument("--protocol-min-tvl", type=float, default=0.0)
    parser.add_argument("--no-protocols", action="store_true")
    parser.add_argument("--no-stablecoins", action="store_true")
    parser.add_argument("--no-chains", action="store_true")
    parser.add_argument("--no-overviews", action="store_true")
    parser.add_argument("--upload-local-coingecko-db", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--upload-discovery", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--status-filename", default="backfill_status.jsonl")
    parser.add_argument("--status-upload-every", type=int, default=25)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def safe_name(value: str) -> str:
    value = value.strip().replace("/", "__")
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return value.strip("._-") or "unknown"


def fetch_json(url: str, timeout: int, retries: int) -> tuple[Any, bytes]:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    last_error = ""
    for attempt in range(max(1, retries)):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            return json.loads(raw), raw
        except urllib.error.HTTPError as exc:
            body = exc.read(500).decode("utf-8", errors="replace")
            last_error = f"HTTP {exc.code}: {body}"
            if exc.code == 429 and attempt + 1 < retries:
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 20 + attempt * 20
                time.sleep(delay)
                continue
            if exc.code in {500, 502, 503, 504} and attempt + 1 < retries:
                time.sleep(8 + attempt * 8)
                continue
            raise RuntimeError(last_error) from exc
        except (OSError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            if attempt + 1 < retries:
                time.sleep(6 + attempt * 6)
                continue
            raise RuntimeError(last_error) from exc
    raise RuntimeError(last_error or "unknown fetch error")


def rclone(*args: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["rclone", *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def remote_files(remote_dir: str) -> set[str]:
    proc = rclone("lsf", remote_dir, "--files-only", check=False, capture=True)
    if proc.returncode != 0:
        return set()
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def write_raw_gz(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb", compresslevel=6) as fh:
        fh.write(raw)


def write_csv_gz(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="", encoding="utf-8", compresslevel=6) as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: stringify(row.get(field)) for field in fields})


def stringify(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def sum_number_dict(value: Any) -> float | None:
    if not isinstance(value, dict):
        return None
    total = 0.0
    found = False
    for item in value.values():
        try:
            total += float(item)
            found = True
        except (TypeError, ValueError):
            pass
    return total if found else None


def date_from_unix(value: Any) -> str:
    try:
        return datetime.fromtimestamp(float(value), tz=UTC).date().isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def copyto(local_path: Path, remote_path: str) -> None:
    rclone("copyto", str(local_path), remote_path, "--stats-one-line")


def upload_and_unlink(local_path: Path, remote_path: str) -> int:
    size = local_path.stat().st_size
    copyto(local_path, remote_path)
    local_path.unlink()
    return size


def write_status(args: argparse.Namespace, status_path: Path, record: dict[str, Any]) -> None:
    append_jsonl(status_path, record)
    upload_every = max(0, int(getattr(args, "status_upload_every", 25)))
    should_upload = (
        record.get("status") in {"error", "done"}
        or (upload_every > 0 and record.get("processed_count", 0) % upload_every == 0)
    )
    if should_upload:
        rclone("copyto", str(status_path), f"{args.drive_root}/manifests/{status_path.name}", "--stats-one-line", check=False)


def fetch_upload_item(
    *,
    args: argparse.Namespace,
    stage: Path,
    status_path: Path,
    source: str,
    name: str,
    url: str,
    raw_remote_dir: str,
    norm_remote_dir: str | None,
    normalize: Callable[[Any], tuple[list[dict[str, Any]], list[str]]] | None,
    remote_raw_files: set[str],
    remote_norm_files: set[str] | None,
    processed_count: int,
) -> str:
    raw_file = f"{safe_name(name)}.json.gz"
    norm_file = f"{safe_name(name)}.csv.gz"
    raw_done = raw_file in remote_raw_files
    norm_done = normalize is None or (remote_norm_files is not None and norm_file in remote_norm_files)
    if raw_done and norm_done:
        write_status(
            args,
            status_path,
            {
                "ts": utc_now(),
                "source": source,
                "name": name,
                "url": url,
                "status": "skipped_present",
                "processed_count": processed_count,
            },
        )
        return "skipped_present"

    item_dir = stage / safe_name(source) / safe_name(name)
    if item_dir.exists():
        shutil.rmtree(item_dir)
    item_dir.mkdir(parents=True, exist_ok=True)
    try:
        payload, raw = fetch_json(url, args.timeout, args.retries)
        raw_path = item_dir / raw_file
        write_raw_gz(raw_path, raw)
        raw_gz_bytes = upload_and_unlink(raw_path, f"{raw_remote_dir}/{raw_file}")
        remote_raw_files.add(raw_file)

        norm_rows = 0
        norm_gz_bytes = 0
        if normalize is not None:
            rows, fields = normalize(payload)
            norm_path = item_dir / norm_file
            write_csv_gz(norm_path, rows, fields)
            norm_rows = len(rows)
            norm_gz_bytes = upload_and_unlink(norm_path, f"{norm_remote_dir}/{norm_file}")
            if remote_norm_files is not None:
                remote_norm_files.add(norm_file)

        write_status(
            args,
            status_path,
            {
                "ts": utc_now(),
                "source": source,
                "name": name,
                "url": url,
                "status": "ok",
                "raw_gz_bytes": raw_gz_bytes,
                "normalized_rows": norm_rows,
                "normalized_gz_bytes": norm_gz_bytes,
                "processed_count": processed_count,
            },
        )
        return "ok"
    except Exception as exc:
        write_status(
            args,
            status_path,
            {
                "ts": utc_now(),
                "source": source,
                "name": name,
                "url": url,
                "status": "error",
                "error": str(exc),
                "processed_count": processed_count,
            },
        )
        return "error"
    finally:
        shutil.rmtree(item_dir, ignore_errors=True)


def normalize_chain_tvl(chain: str) -> Callable[[Any], tuple[list[dict[str, Any]], list[str]]]:
    def _normalize(payload: Any) -> tuple[list[dict[str, Any]], list[str]]:
        rows = []
        if isinstance(payload, list):
            for row in payload:
                if isinstance(row, dict):
                    rows.append({"chain": chain, "date": date_from_unix(row.get("date")), "tvl_usd": row.get("tvl")})
        return rows, ["chain", "date", "tvl_usd"]

    return _normalize


def normalize_stablecoin_chart(chain: str) -> Callable[[Any], tuple[list[dict[str, Any]], list[str]]]:
    def _normalize(payload: Any) -> tuple[list[dict[str, Any]], list[str]]:
        rows = []
        if isinstance(payload, list):
            for row in payload:
                if not isinstance(row, dict):
                    continue
                rows.append(
                    {
                        "chain": chain,
                        "date": date_from_unix(row.get("date")),
                        "total_circulating_usd": sum_number_dict(row.get("totalCirculatingUSD")),
                        "total_minted_usd": sum_number_dict(row.get("totalMintedUSD")),
                        "total_unreleased": sum_number_dict(row.get("totalUnreleased")),
                        "total_bridged_to_usd": sum_number_dict(row.get("totalBridgedToUSD")),
                    }
                )
        return rows, [
            "chain",
            "date",
            "total_circulating_usd",
            "total_minted_usd",
            "total_unreleased",
            "total_bridged_to_usd",
        ]

    return _normalize


def normalize_overview(metric: str) -> Callable[[Any], tuple[list[dict[str, Any]], list[str]]]:
    def _normalize(payload: Any) -> tuple[list[dict[str, Any]], list[str]]:
        rows = []
        if isinstance(payload, dict):
            for point in payload.get("totalDataChart", []) or []:
                if isinstance(point, list) and len(point) >= 2:
                    rows.append({"metric": metric, "date": date_from_unix(point[0]), "scope": "total", "name": "total", "value_usd": point[1]})
            for point in payload.get("totalDataChartBreakdown", []) or []:
                if not (isinstance(point, list) and len(point) >= 2 and isinstance(point[1], dict)):
                    continue
                date = date_from_unix(point[0])
                for name, value in point[1].items():
                    rows.append({"metric": metric, "date": date, "scope": "breakdown", "name": name, "value_usd": value})
        return rows, ["metric", "date", "scope", "name", "value_usd"]

    return _normalize


def normalize_protocol(slug: str) -> Callable[[Any], tuple[list[dict[str, Any]], list[str]]]:
    def _normalize(payload: Any) -> tuple[list[dict[str, Any]], list[str]]:
        rows = []
        if not isinstance(payload, dict):
            return rows, ["slug", "name", "category", "scope", "date", "tvl_usd"]
        name = payload.get("name")
        category = payload.get("category")
        for point in payload.get("tvl", []) or []:
            if isinstance(point, dict):
                rows.append(
                    {
                        "slug": slug,
                        "name": name,
                        "category": category,
                        "scope": "total",
                        "date": date_from_unix(point.get("date")),
                        "tvl_usd": point.get("totalLiquidityUSD"),
                    }
                )
        chain_tvls = payload.get("chainTvls") or {}
        if isinstance(chain_tvls, dict):
            for chain_scope, chain_payload in chain_tvls.items():
                if not isinstance(chain_payload, dict):
                    continue
                for point in chain_payload.get("tvl", []) or []:
                    if isinstance(point, dict):
                        rows.append(
                            {
                                "slug": slug,
                                "name": name,
                                "category": category,
                                "scope": chain_scope,
                                "date": date_from_unix(point.get("date")),
                                "tvl_usd": point.get("totalLiquidityUSD"),
                            }
                        )
        return rows, ["slug", "name", "category", "scope", "date", "tvl_usd"]

    return _normalize


def discover(args: argparse.Namespace, stage: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    discovery_dir = stage / "discovery"
    discovery_dir.mkdir(parents=True, exist_ok=True)
    protocols, protocols_raw = fetch_json("https://api.llama.fi/protocols", args.timeout, args.retries)
    chains, chains_raw = fetch_json("https://api.llama.fi/v2/chains", args.timeout, args.retries)
    stablecoinchains, stablecoinchains_raw = fetch_json("https://stablecoins.llama.fi/stablecoinchains", args.timeout, args.retries)

    if args.upload_discovery:
        for name, raw in [
            ("protocols.json.gz", protocols_raw),
            ("chains.json.gz", chains_raw),
            ("stablecoinchains.json.gz", stablecoinchains_raw),
        ]:
            path = discovery_dir / name
            write_raw_gz(path, raw)
            copyto(path, f"{args.drive_root}/discovery/{name}")
            path.unlink()

    protocol_rows = protocols if isinstance(protocols, list) else []
    chain_rows = chains if isinstance(chains, list) else []
    stable_chains = [row.get("name") for row in stablecoinchains if isinstance(row, dict) and row.get("name")] if isinstance(stablecoinchains, list) else []
    return protocol_rows, chain_rows, sorted(set(stable_chains))


def protocol_slug_rows(protocol_rows: list[dict[str, Any]], max_protocols: int, min_tvl: float) -> list[dict[str, Any]]:
    rows = [row for row in protocol_rows if isinstance(row, dict) and row.get("slug")]
    rows = [row for row in rows if float(row.get("tvl") or 0) >= min_tvl]
    rows.sort(key=lambda row: float(row.get("tvl") or 0), reverse=True)
    if max_protocols > 0:
        rows = rows[:max_protocols]
    return rows


def upload_local_coingecko_db(args: argparse.Namespace, stage: Path, status_path: Path) -> None:
    if not LOCAL_COINGECKO_DB.exists():
        write_status(args, status_path, {"ts": utc_now(), "source": "coingecko_local", "name": "full_active_db", "status": "missing", "processed_count": 0})
        return
    remote_dir = f"{args.drive_root}/coingecko_existing_archive"
    existing = remote_files(remote_dir)
    target_name = "coingecko_full_active_2009.sqlite3.gz"
    if target_name in existing:
        write_status(args, status_path, {"ts": utc_now(), "source": "coingecko_local", "name": "full_active_db", "status": "skipped_present", "processed_count": 0})
        return
    tmp = stage / target_name
    print("compress local Coingecko historical SQLite", flush=True)
    with LOCAL_COINGECKO_DB.open("rb") as src, gzip.open(tmp, "wb", compresslevel=4) as dst:
        shutil.copyfileobj(src, dst, length=8 * 1024 * 1024)
    size = upload_and_unlink(tmp, f"{remote_dir}/{target_name}")
    con = sqlite3.connect(LOCAL_COINGECKO_DB)
    try:
        summary = {
            "coins": con.execute("select count(*) from coins").fetchone()[0],
            "coin_history_rows": con.execute("select count(*) from coin_history").fetchone()[0],
            "coin_history_distinct_coins": con.execute("select count(distinct coin_id) from coin_history").fetchone()[0],
            "min_ts_ms": con.execute("select min(ts_ms) from coin_history").fetchone()[0],
            "max_ts_ms": con.execute("select max(ts_ms) from coin_history").fetchone()[0],
        }
    finally:
        con.close()
    summary_path = stage / "coingecko_full_active_2009_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    upload_and_unlink(summary_path, f"{remote_dir}/coingecko_full_active_2009_summary.json")
    write_status(
        args,
        status_path,
        {
            "ts": utc_now(),
            "source": "coingecko_local",
            "name": "full_active_db",
            "status": "ok",
            "raw_gz_bytes": size,
            "normalized_rows": summary["coin_history_rows"],
            "processed_count": 0,
        },
    )


def main() -> int:
    args = parse_args()
    if args.protocol_shards < 1:
        raise SystemExit("--protocol-shards must be >= 1")
    if args.protocol_shard_index < 0 or args.protocol_shard_index >= args.protocol_shards:
        raise SystemExit("--protocol-shard-index must be in [0, --protocol-shards)")

    stage = args.stage_root.resolve()
    stage.mkdir(parents=True, exist_ok=True)
    args.state_dir.mkdir(parents=True, exist_ok=True)
    status_path = args.state_dir / args.status_filename
    print(json.dumps({"drive_root": args.drive_root, "stage": str(stage), "status": str(status_path)}, indent=2), flush=True)

    protocols, chains, stable_chains = discover(args, stage)
    selected_protocols = protocol_slug_rows(protocols, args.max_protocols, args.protocol_min_tvl)
    selected_protocols_before_shard = len(selected_protocols)
    if args.protocol_shards > 1:
        selected_protocols = [
            row
            for idx, row in enumerate(selected_protocols)
            if idx % args.protocol_shards == args.protocol_shard_index
        ]
    print(
        json.dumps(
            {
                "discovered_protocols": len(protocols),
                "selected_protocols_before_shard": selected_protocols_before_shard,
                "selected_protocols": len(selected_protocols),
                "protocol_shards": args.protocol_shards,
                "protocol_shard_index": args.protocol_shard_index,
                "chains": len(chains),
                "stablecoin_chains": len(stable_chains),
            },
            indent=2,
        ),
        flush=True,
    )

    if args.upload_local_coingecko_db:
        upload_local_coingecko_db(args, stage, status_path)

    processed = 0
    status_counts: dict[str, int] = {}

    def run_item(**kwargs: Any) -> None:
        nonlocal processed
        processed += 1
        result = fetch_upload_item(args=args, stage=stage, status_path=status_path, processed_count=processed, **kwargs)
        status_counts[result] = status_counts.get(result, 0) + 1
        print(f"[{processed}] {result} {kwargs['source']}/{kwargs['name']}", flush=True)
        if result != "skipped_present":
            time.sleep(max(0.0, args.sleep))

    if not args.no_overviews:
        overview_tasks = [
            ("fees", "https://api.llama.fi/overview/fees?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=false"),
            ("dexs", "https://api.llama.fi/overview/dexs?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=false"),
            ("open_interest", "https://api.llama.fi/overview/open-interest?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=false"),
        ]
        raw_dir = f"{args.drive_root}/raw/defillama/overviews"
        norm_dir = f"{args.drive_root}/normalized/defillama/overviews"
        raw_files = remote_files(raw_dir)
        norm_files = remote_files(norm_dir)
        for metric, url in overview_tasks:
            run_item(
                source="defillama_overview",
                name=metric,
                url=url,
                raw_remote_dir=raw_dir,
                norm_remote_dir=norm_dir,
                normalize=normalize_overview(metric),
                remote_raw_files=raw_files,
                remote_norm_files=norm_files,
            )

    if not args.no_chains:
        raw_dir = f"{args.drive_root}/raw/defillama/chain_tvl"
        norm_dir = f"{args.drive_root}/normalized/defillama/chain_tvl"
        raw_files = remote_files(raw_dir)
        norm_files = remote_files(norm_dir)
        chain_names = sorted({row.get("name") for row in chains if isinstance(row, dict) and row.get("name")})
        chain_names = ["all"] + chain_names
        for chain in chain_names:
            url_chain = "" if chain == "all" else "/" + urllib.parse.quote(chain, safe="")
            url = "https://api.llama.fi/v2/historicalChainTvl" + url_chain
            run_item(
                source="defillama_chain_tvl",
                name=chain,
                url=url,
                raw_remote_dir=raw_dir,
                norm_remote_dir=norm_dir,
                normalize=normalize_chain_tvl(chain),
                remote_raw_files=raw_files,
                remote_norm_files=norm_files,
            )

    if not args.no_stablecoins:
        raw_dir = f"{args.drive_root}/raw/defillama/stablecoincharts"
        norm_dir = f"{args.drive_root}/normalized/defillama/stablecoincharts"
        raw_files = remote_files(raw_dir)
        norm_files = remote_files(norm_dir)
        for chain in ["all", *stable_chains]:
            url = f"https://stablecoins.llama.fi/stablecoincharts/{urllib.parse.quote(chain, safe='')}"
            run_item(
                source="defillama_stablecoincharts",
                name=chain,
                url=url,
                raw_remote_dir=raw_dir,
                norm_remote_dir=norm_dir,
                normalize=normalize_stablecoin_chart(chain),
                remote_raw_files=raw_files,
                remote_norm_files=norm_files,
            )

    if not args.no_protocols:
        raw_dir = f"{args.drive_root}/raw/defillama/protocols"
        norm_dir = f"{args.drive_root}/normalized/defillama/protocol_tvl"
        raw_files = remote_files(raw_dir)
        norm_files = remote_files(norm_dir)
        for row in selected_protocols:
            slug = row["slug"]
            url = f"https://api.llama.fi/protocol/{urllib.parse.quote(slug, safe='')}"
            run_item(
                source="defillama_protocol",
                name=slug,
                url=url,
                raw_remote_dir=raw_dir,
                norm_remote_dir=norm_dir,
                normalize=normalize_protocol(slug),
                remote_raw_files=raw_files,
                remote_norm_files=norm_files,
            )

    final_summary = {"ts": utc_now(), "status": "done", "processed_count": processed, "status_counts": status_counts}
    write_status(args, status_path, final_summary)
    rclone("copyto", str(status_path), f"{args.drive_root}/manifests/{status_path.name}", "--stats-one-line", check=False)
    print(json.dumps(final_summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
