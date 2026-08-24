#!/usr/bin/env python3
"""Distributed Wikipedia title probe across windows_lab cluster + local controller."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from stablecoin_skynet.research_dataset import build_entities
from stablecoin_skynet.unified_dataset import (
    DEFAULT_COMMUNITY_DIR,
    DEFAULT_SCRAPES_ROOT,
    DEFAULT_SKYNET_HARVEST,
    build_unified_dataset,
)
from stablecoin_skynet.wikipedia_probe import (
    DEFAULT_CONFIG,
    PROBE_SAMPLE_END,
    PROBE_SAMPLE_START,
    build_probe_plan,
    merge_probe_results,
    merge_verified_config,
    probe_article_title,
)
from stablecoin_skynet.wikipedia_panel import build_pageviews_daily

DERIVED = REPO / "stablecoin_skynet/data/derived/wikipedia"
CLUSTER_CFG = REPO / "config/yzu_cluster.json"

_PS_PROBE = r"""
param([string]$InPath, [string]$OutPath)
$items = Get-Content -Raw -Path $InPath | ConvertFrom-Json
$results = @()
foreach ($item in $items) {
  $art = [string]$item.article
  $eid = [string]$item.entity_id
  $enc = [uri]::EscapeDataString($art).Replace('%2F','/').Replace('%28','(').Replace('%29',')')
  $url = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/$($art -replace '/','%2F' -replace '\(','%28' -replace '\)','%29')/daily/PROBE_START/PROBE_END"
  $status = -1
  $count = 0
  try {
    $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 30 -Headers @{ "User-Agent" = "Sharpe-Renaissance/1.0 (cluster-probe)" }
    $status = [int]$resp.StatusCode
    $payload = $resp.Content | ConvertFrom-Json
    if ($payload.items) { $count = @($payload.items).Count }
  } catch {
    if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
  }
  $ok = ($status -eq 200 -and $count -gt 0)
  $results += [PSCustomObject]@{ entity_id = $eid; article = $art; status = $status; item_count = $count; ok = $ok }
  Start-Sleep -Milliseconds 800
}
$results | ConvertTo-Json -Depth 4 | Set-Content -Path $OutPath -Encoding UTF8
""".replace("PROBE_START", PROBE_SAMPLE_START).replace("PROBE_END", PROBE_SAMPLE_END)


def _load_cluster_workers() -> list[dict[str, str]]:
    cfg = json.loads(CLUSTER_CFG.read_text(encoding="utf-8"))
    pool = cfg.get("worker_pools", {}).get("windows_lab") or {}
    inventory = Path(pool.get("inventory") or "")
    key = str(pool.get("ssh_key") or "")
    if not inventory.is_file():
        return []
    import csv

    workers = []
    with inventory.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("status") == "joined":
                workers.append(
                    {
                        "target": f"{row.get('user') or 'user'}@{row['tailscale_ip']}",
                        "hostname": row.get("hostname") or row["tailscale_ip"],
                        "key": key,
                    }
                )
    return workers


def _shard_plan(plan: list[dict[str, str]], n: int) -> list[list[dict[str, str]]]:
    shards: list[list[dict[str, str]]] = [[] for _ in range(max(1, n))]
    for i, row in enumerate(plan):
        shards[i % len(shards)].append(row)
    return [s for s in shards if s]


def _probe_shard_local(shard: list[dict[str, str]], shard_id: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in shard:
        result = probe_article_title(row["article"])
        result["entity_id"] = row["entity_id"]
        result["ok"] = bool(result.get("ok"))
        result["shard"] = f"local-{shard_id}"
        out.append(result)
        time.sleep(0.35)
    return out


def _probe_shard_windows(
    shard: list[dict[str, str]],
    *,
    worker: dict[str, str],
    shard_id: int,
    work_dir: Path,
) -> list[dict[str, Any]]:
    work_dir.mkdir(parents=True, exist_ok=True)
    in_path = work_dir / f"shard_{shard_id}_in.json"
    out_path = work_dir / f"shard_{shard_id}_out.json"
    remote_in = f"C:/Users/user/wikipedia_probe/shard_{shard_id}_in.json"
    remote_out = f"C:/Users/user/wikipedia_probe/shard_{shard_id}_out.json"
    remote_ps = "C:/Users/user/wikipedia_probe/probe.ps1"

    in_path.write_text(json.dumps(shard, indent=2), encoding="utf-8")
    ps_path = work_dir / "probe.ps1"
    ps_path.write_text(_PS_PROBE, encoding="utf-8")

    target = worker["target"]
    key = worker["key"]
    ssh_base = [
        "ssh",
        "-n",
        "-i",
        key,
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=12",
        target,
    ]

    subprocess.run(
        ["ssh", "-i", key, "-o", "BatchMode=yes", target, "powershell -NoProfile -Command \"New-Item -Force -ItemType Directory C:/Users/user/wikipedia_probe | Out-Null\""],
        check=False,
        capture_output=True,
        timeout=30,
    )
    subprocess.run(["scp", "-q", "-i", key, str(ps_path), f"{target}:{remote_ps}"], check=True, timeout=60)
    subprocess.run(["scp", "-q", "-i", key, str(in_path), f"{target}:{remote_in}"], check=True, timeout=60)

    run = subprocess.run(
        [*ssh_base, f"powershell -NoProfile -ExecutionPolicy Bypass -File {remote_ps} -InPath {remote_in} -OutPath {remote_out}"],
        capture_output=True,
        text=True,
        timeout=max(600, len(shard) * 2),
    )
    if run.returncode != 0:
        raise RuntimeError(f"{worker['hostname']} probe failed: {(run.stderr or run.stdout)[:500]}")

    subprocess.run(["scp", "-q", "-i", key, f"{target}:{remote_out}", str(out_path)], check=True, timeout=120)
    rows = json.loads(out_path.read_text(encoding="utf-8-sig"))
    if isinstance(rows, dict):
        rows = [rows]
    for row in rows:
        row["shard"] = worker["hostname"]
    return rows


def run_cluster_probe(plan: list[dict[str, str]], *, work_dir: Path) -> list[dict[str, Any]]:
    workers = _load_cluster_workers()
    # local controller + each joined windows worker
    n_shards = 1 + len(workers)
    shards = _shard_plan(plan, n_shards)
    results: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=n_shards) as pool:
        futures = []
        if shards:
            futures.append(pool.submit(_probe_shard_local, shards[0], 0))
        for i, worker in enumerate(workers):
            shard_idx = i + 1
            if shard_idx >= len(shards):
                break
            futures.append(
                pool.submit(
                    _probe_shard_windows,
                    shards[shard_idx],
                    worker=worker,
                    shard_id=shard_idx,
                    work_dir=work_dir,
                )
            )
        for fut in as_completed(futures):
            results.extend(fut.result())
    return results


def write_pruned_config(verified: dict[str, str], *, config_path: Path = DEFAULT_CONFIG) -> None:
    payload = {
        "comment": "Verified entity_id -> en.wikipedia article (cluster probe + pageviews API 200).",
        "articles": dict(sorted(verified.items())),
        "generated_by": "scripts/probe_stablecoin_wikipedia_cluster.py",
    }
    config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remap-only", action="store_true", help="Re-merge existing probe audit + cache; skip cluster probe")
    parser.add_argument("--local-only", action="store_true", help="Skip windows_lab; probe from controller only")
    parser.add_argument("--no-harvest", action="store_true", help="Probe + write config only")
    parser.add_argument("--work-dir", type=Path, default=DERIVED / "cluster_probe")
    parser.add_argument("--no-rebuild", action="store_true", help="Skip dataset rebuild")
    args = parser.parse_args()

    audit_path = DERIVED / "wikipedia_probe_audit.json"

    if args.remap_only and audit_path.is_file():
        merged = merge_probe_results(json.loads(audit_path.read_text(encoding="utf-8")).get("probe_rows") or [])
        verified = merge_verified_config(merged["verified_articles"])
        merged["verified_articles"] = verified
        audit_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        write_pruned_config(verified)
        print(json.dumps({"verified_entities": len(verified), "mode": "remap-only"}, indent=2))
        if args.no_harvest:
            return
        entities = [e for e in build_entities(build_unified_dataset(
            skynet_harvest_dir=DEFAULT_SKYNET_HARVEST,
            scrapes_root=DEFAULT_SCRAPES_ROOT,
            community_dir=DEFAULT_COMMUNITY_DIR,
        )[0]) if e.get("in_skynet_leaderboard")]
        daily = build_pageviews_daily(entities, refresh=True, entity_ids={e["entity_id"] for e in entities})
        print(json.dumps({"wikipedia_daily_rows": len(daily)}, indent=2))
        if not args.no_rebuild:
            from datetime import datetime, timezone
            from stablecoin_skynet.research_dataset import publish_research_dataset
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
            out = REPO / "data" / "datasets" / "stablecoin_trust_engagement" / stamp
            manifest = publish_research_dataset(out, include_gdelt=True, include_external=True, refresh_external=False)
            latest = REPO / "data" / "datasets" / "stablecoin_trust_engagement" / "latest"
            if latest.is_symlink() or latest.is_file():
                latest.unlink()
            try:
                latest.symlink_to(out.resolve(), target_is_directory=True)
            except OSError:
                pass
            print(json.dumps({"rebuilt": str(out), "wikipedia_weekly": manifest.get("counts", {}).get("wikipedia_weekly_rows")}, indent=2))
        return

    unified_rows, _ = build_unified_dataset(
        skynet_harvest_dir=DEFAULT_SKYNET_HARVEST,
        scrapes_root=DEFAULT_SCRAPES_ROOT,
        community_dir=DEFAULT_COMMUNITY_DIR,
    )
    entities = [e for e in build_entities(unified_rows) if e.get("in_skynet_leaderboard")]
    plan = build_probe_plan(entities, config_path=DEFAULT_CONFIG)
    print(json.dumps({"entities": len(entities), "probe_candidates": len(plan)}, indent=2))

    if args.local_only:
        results: list[dict[str, Any]] = []
        for row in plan:
            r = probe_article_title(row["article"])
            r["entity_id"] = row["entity_id"]
            r["ok"] = bool(r.get("ok"))
            results.append(r)
            time.sleep(0.35)
    else:
        results = run_cluster_probe(plan, work_dir=args.work_dir)

    merged = merge_probe_results(results)
    verified = merge_verified_config(merged["verified_articles"])
    merged["verified_articles"] = verified
    audit_path = DERIVED / "wikipedia_probe_audit.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    write_pruned_config(verified)

    print(
        json.dumps(
            {
                "verified_entities": len(verified),
                "total_entities": len(entities),
                "probe_rows": len(results),
                "audit_path": str(audit_path),
                "config_path": str(DEFAULT_CONFIG),
            },
            indent=2,
        )
    )

    if args.no_harvest:
        return

    # Re-harvest pageviews for verified titles only (controller; cached per article).
    leaderboard_ids = {e["entity_id"] for e in entities}
    daily = build_pageviews_daily(
        entities,
        refresh=True,
        entity_ids=leaderboard_ids,
        config_articles_only=False,
    )
    print(json.dumps({"wikipedia_daily_rows": len(daily)}, indent=2))

    if not args.no_rebuild:
        from datetime import datetime, timezone

        from stablecoin_skynet.research_dataset import publish_research_dataset

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        out = REPO / "data" / "datasets" / "stablecoin_trust_engagement" / stamp
        manifest = publish_research_dataset(out, include_gdelt=True, include_external=True, refresh_external=False)
        latest = REPO / "data" / "datasets" / "stablecoin_trust_engagement" / "latest"
        if latest.is_symlink() or latest.is_file():
            latest.unlink()
        try:
            latest.symlink_to(out.resolve(), target_is_directory=True)
        except OSError:
            pass
        print(json.dumps({"rebuilt": str(out), "counts": manifest.get("counts")}, indent=2))


if __name__ == "__main__":
    main()
