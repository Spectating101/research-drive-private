#!/usr/bin/env python3
"""Harvest sparse historical Twitter follower counts from Wayback Machine.

Resolution target: monthly (or whatever mementos exist). Quarterly rollup optional.
Uses ODU FollowerCountHistory-style CSS selectors + regex fallbacks.
Does NOT claim weekly coverage.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

REPO = Path(__file__).resolve().parents[2]
DEFAULT_ACCOUNTS = REPO / "stablecoin_skynet/data/community/accounts.csv"
DEFAULT_OUT = REPO / "data/datasets/stablecoin_trust_engagement/wayback_followers_monthly"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_kmb(raw: str) -> int | None:
    s = raw.strip().replace(",", "").replace(" ", "")
    if not s:
        return None
    mult = 1
    if s[-1] in "kK":
        mult = 1_000
        s = s[:-1]
    elif s[-1] in "mM":
        mult = 1_000_000
        s = s[:-1]
    elif s[-1] in "bB":
        mult = 1_000_000_000
        s = s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        digits = re.sub(r"\D", "", raw)
        return int(digits) if digits else None


def parse_followers(html: str) -> tuple[int | None, str]:
    """Return (count, method)."""
    # JSON embeds
    for pat, name in [
        (r'"followers_count"\s*:\s*(\d+)', "json_followers_count"),
        (r'followers_count&quot;:(\d+)', "json_escaped"),
        (r'"followersCount"\s*:\s*(\d+)', "json_followersCount"),
    ]:
        m = re.search(pat, html)
        if m:
            return int(m.group(1)), name

    soup = BeautifulSoup(html, "html.parser")

    # FCH case1
    tags = soup.select("li.ProfileNav-item.ProfileNav-item--followers")
    if tags:
        t = tags[0]
        try:
            if t.select("span.ProfileNav-value") and t.select("span.ProfileNav-value")[0].has_attr("data-count"):
                return int(t.select("span.ProfileNav-value")[0]["data-count"]), "ProfileNav_data_count"
            a = t.select("a.ProfileNav-stat")
            if a and a[0].has_attr("title"):
                c = _parse_kmb(re.sub(r"[^\d\.kKmMbB]", "", a[0]["title"]))
                if c is not None:
                    return c, "ProfileNav_title"
            if t.select("span.ProfileNav-value"):
                c = _parse_kmb(t.select("span.ProfileNav-value")[0].get_text())
                if c is not None:
                    return c, "ProfileNav_value"
        except Exception:
            pass

    # FCH case2
    for sel in ["a.user-stats-count.user-stats-followers", "a.user-stats-followers"]:
        el = soup.select(sel)
        if el:
            c = _parse_kmb(el[0].get_text())
            if c is not None:
                return c, "user_stats_followers"

    # mini profile stats
    for sel in ["table.stats.js-mini-profile-stats a.js-nav strong", "ul.stats.js-mini-profile-stats a strong"]:
        els = soup.select(sel)
        if len(els) >= 3:
            el = els[2]
            raw = el.get("title") or el.get_text()
            c = _parse_kmb(raw)
            if c is not None:
                return c, "mini_profile_stats"

    # div.stats
    els = soup.select("div.stats span.stats_count.numeric")
    if len(els) >= 2:
        c = _parse_kmb(els[1].get_text())
        if c is not None:
            return c, "div_stats"

    # title attribute
    m = re.search(r'title="([\d,\.]+)\s+Followers"', html, re.I)
    if m:
        c = _parse_kmb(m.group(1))
        if c is not None:
            return c, "title_attr"

    m = re.search(r'data-count="(\d+)"[^>]*data-nav="followers"', html, re.I)
    if m:
        return int(m.group(1)), "data_nav_followers"

    return None, "unparsed"


def cdx_monthly(handle: str, session: requests.Session, *, limit: int = 200) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen_ym: set[str] = set()
    for hostpath in [f"twitter.com/{handle}", f"x.com/{handle}", f"mobile.twitter.com/{handle}"]:
        q = {
            "url": hostpath,
            "output": "json",
            "fl": "timestamp,original,statuscode,mimetype",
            "filter": "statuscode:200",
            "collapse": "timestamp:6",
            "limit": str(limit),
        }
        url = "https://web.archive.org/cdx/search/cdx?" + urllib.parse.urlencode(q)
        try:
            r = session.get(url, timeout=60)
            r.raise_for_status()
            data = r.json()
        except Exception:
            continue
        if not data or len(data) < 2:
            continue
        for row in data[1:]:
            ts = row[0]
            ym = ts[:6]
            if ym in seen_ym:
                continue
            seen_ym.add(ym)
            out.append({"timestamp": ts, "original": row[1], "hostpath": hostpath})
    out.sort(key=lambda x: x["timestamp"])
    return out


def load_handles(accounts_csv: Path) -> list[dict[str, str]]:
    import pandas as pd

    df = pd.read_csv(accounts_csv)
    # unique by handle; keep all entity_ids mapped
    rows = []
    by_handle: dict[str, list[str]] = {}
    for _, r in df.iterrows():
        h = str(r["twitter_handle"]).strip()
        if not h or h == "nan":
            continue
        by_handle.setdefault(h, []).append(str(r["slug"]))
    for h, slugs in sorted(by_handle.items(), key=lambda x: x[0].lower()):
        rows.append({"twitter_handle": h, "entity_ids": "|".join(slugs), "primary_entity_id": slugs[0]})
    return rows


def cmd_harvest(args: argparse.Namespace) -> int:
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    points_path = out / "wayback_follower_points.csv"
    status_path = out / "harvest_status.jsonl"
    handles = load_handles(args.accounts)
    if args.handles:
        want = {h.strip().lstrip("@") for h in args.handles.split(",") if h.strip()}
        handles = [h for h in handles if h["twitter_handle"] in want]
    if args.shard is not None and args.shards:
        handles = [h for i, h in enumerate(handles) if i % args.shards == args.shard]

    # resume set
    done_keys: set[str] = set()
    if points_path.exists():
        with points_path.open(encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                done_keys.add(f"{row.get('twitter_handle')}|{row.get('memento_ts')}")

    session = requests.Session()
    session.headers["User-Agent"] = "SharpeRenaissance-WaybackFollowerHarvest/1.0 (research; monthly sparse)"

    fieldnames = [
        "primary_entity_id",
        "entity_ids",
        "twitter_handle",
        "memento_ts",
        "date",
        "year_month",
        "year_quarter",
        "followers",
        "parse_method",
        "http_status",
        "bytes",
        "memento_url",
        "hostpath",
        "harvested_at",
    ]
    write_header = not points_path.exists() or points_path.stat().st_size == 0
    pf = points_path.open("a", encoding="utf-8", newline="")
    writer = csv.DictWriter(pf, fieldnames=fieldnames)
    if write_header:
        writer.writeheader()

    n_ok = n_fail = n_skip = 0
    for i, hrow in enumerate(handles, 1):
        handle = hrow["twitter_handle"]
        print(f"[{i}/{len(handles)}] @{handle} entities={hrow['entity_ids']}", flush=True)
        try:
            mems = cdx_monthly(handle, session, limit=args.cdx_limit)
        except Exception as exc:
            status_path.open("a", encoding="utf-8").write(
                json.dumps({"handle": handle, "error": f"cdx:{exc}", "at": _utc()}) + "\n"
            )
            continue
        print(f"  monthly mementos: {len(mems)}", flush=True)
        # optional: downsample to quarterly if too many and --quarterly-only
        if args.quarterly_only:
            keep = {}
            for m in mems:
                q = f"{m['timestamp'][:4]}-Q{(int(m['timestamp'][4:6]) - 1) // 3 + 1}"
                keep[q] = m  # last in quarter
            mems = list(keep.values())
            print(f"  quarterly sample: {len(mems)}", flush=True)

        for m in mems:
            ts = m["timestamp"]
            key = f"{handle}|{ts}"
            if key in done_keys:
                n_skip += 1
                continue
            # prefer twitter.com in replay URL
            mem_url = f"https://web.archive.org/web/{ts}id_/https://twitter.com/{handle}"
            # id_ = raw without toolbar; fallback without id_
            followers = None
            method = "unparsed"
            status = None
            nbytes = None
            used = mem_url
            attempt_urls = [
                mem_url,
                f"https://web.archive.org/web/{ts}/https://twitter.com/{handle}",
            ]
            for attempt_url in attempt_urls:
                try:
                    resp = session.get(attempt_url, timeout=35)
                    status = resp.status_code
                    nbytes = len(resp.content)
                    used = attempt_url
                    if resp.status_code == 200 and nbytes > 2000:
                        followers, method = parse_followers(resp.text)
                        if followers is not None:
                            break
                except Exception as exc:
                    method = f"fetch_error:{exc}"
                # only pause between attempts on failure
                if followers is None:
                    time.sleep(min(0.4, args.pause_sec))
            ym = f"{ts[:4]}-{ts[4:6]}"
            q = f"{ts[:4]}-Q{(int(ts[4:6]) - 1) // 3 + 1}"
            row = {
                "primary_entity_id": hrow["primary_entity_id"],
                "entity_ids": hrow["entity_ids"],
                "twitter_handle": handle,
                "memento_ts": ts,
                "date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}",
                "year_month": ym,
                "year_quarter": q,
                "followers": followers if followers is not None else "",
                "parse_method": method,
                "http_status": status if status is not None else "",
                "bytes": nbytes if nbytes is not None else "",
                "memento_url": used,
                "hostpath": m.get("hostpath", ""),
                "harvested_at": _utc(),
            }
            writer.writerow(row)
            pf.flush()
            done_keys.add(key)
            if followers is not None:
                n_ok += 1
                print(f"  {ym} -> {followers} ({method})", flush=True)
            else:
                n_fail += 1
                print(f"  {ym} -> FAIL ({method}) status={status}", flush=True)
            time.sleep(args.pause_sec)

        status_path.open("a", encoding="utf-8").write(
            json.dumps({"handle": handle, "mementos": len(mems), "at": _utc()}, ensure_ascii=False) + "\n"
        )

    pf.close()
    manifest = {
        "finished_at": _utc(),
        "points_path": str(points_path),
        "handles_requested": len(handles),
        "parsed_ok_this_run": n_ok,
        "parse_fail_this_run": n_fail,
        "skipped_resume": n_skip,
        "resolution": "monthly_mementos_when_available",
        "note": "Sparse archive reconstruction; not weekly. QC required before analysis.",
    }
    (out / "manifest_last_run.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)
    return 0


def cmd_rollup(args: argparse.Namespace) -> int:
    import pandas as pd
    import numpy as np

    out: Path = args.out
    points = pd.read_csv(out / "wayback_follower_points.csv")
    ok = points[points["followers"].notna() & (points["followers"] != "")].copy()
    ok["followers"] = pd.to_numeric(ok["followers"], errors="coerce")
    ok = ok.dropna(subset=["followers"])
    # explode entity_ids
    rows = []
    for _, r in ok.iterrows():
        for eid in str(r["entity_ids"]).split("|"):
            rows.append({**r.to_dict(), "entity_id": eid})
    long = pd.DataFrame(rows)
    # monthly: one point per entity-month (median if dupes)
    monthly = (
        long.groupby(["entity_id", "year_month"], as_index=False)
        .agg(followers=("followers", "median"), n_mementos=("followers", "count"), date=("date", "min"))
    )
    monthly["construct"] = "growth_archive_wayback_monthly_sparse"
    monthly["source"] = "internet_archive_wayback"
    # quarterly
    long["year_quarter"] = long["year_quarter"]
    quarterly = (
        long.groupby(["entity_id", "year_quarter"], as_index=False)
        .agg(followers=("followers", "median"), n_mementos=("followers", "count"), date=("date", "min"))
    )
    quarterly["construct"] = "growth_archive_wayback_quarterly_sparse"
    quarterly["source"] = "internet_archive_wayback"
    # QC: flag huge jumps
    monthly = monthly.sort_values(["entity_id", "year_month"])
    monthly["prev"] = monthly.groupby("entity_id")["followers"].shift(1)
    monthly["mom_ratio"] = monthly["followers"] / monthly["prev"]
    monthly["qc_flag"] = np.where(
        (monthly["mom_ratio"] > 20) | (monthly["mom_ratio"] < 0.05),
        "suspicious_jump",
        "ok",
    )
    monthly.to_csv(out / "wayback_followers_monthly_panel.csv", index=False)
    quarterly.to_csv(out / "wayback_followers_quarterly_panel.csv", index=False)
    # coverage summary
    cov = (
        monthly.groupby("entity_id")
        .agg(n_months=("year_month", "nunique"), first=("year_month", "min"), last=("year_month", "max"), suspicious=("qc_flag", lambda s: int((s == "suspicious_jump").sum())))
        .reset_index()
    )
    cov.to_csv(out / "wayback_coverage_by_entity.csv", index=False)
    summary = {
        "entities_with_any_point": int(monthly.entity_id.nunique()),
        "monthly_rows": int(len(monthly)),
        "quarterly_rows": int(len(quarterly)),
        "raw_parsed_points": int(len(ok)),
        "suspicious_jumps": int((monthly.qc_flag == "suspicious_jump").sum()),
        "median_months_per_entity": float(cov.n_months.median()) if len(cov) else 0,
    }
    (out / "rollup_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("harvest")
    h.add_argument("--accounts", type=Path, default=DEFAULT_ACCOUNTS)
    h.add_argument("--out", type=Path, default=DEFAULT_OUT)
    h.add_argument("--pause-sec", type=float, default=1.2)
    h.add_argument("--cdx-limit", type=int, default=240)
    h.add_argument("--handles", default=None, help="Comma-separated handle filter")
    h.add_argument("--shard", type=int, default=None)
    h.add_argument("--shards", type=int, default=None)
    h.add_argument("--quarterly-only", action="store_true")
    h.set_defaults(func=cmd_harvest)
    r = sub.add_parser("rollup")
    r.add_argument("--out", type=Path, default=DEFAULT_OUT)
    r.set_defaults(func=cmd_rollup)
    args = ap.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
