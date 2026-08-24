#!/usr/bin/env python3
"""Point-in-time social snapshot from registry + public Telegram pages."""
from __future__ import annotations

import csv
import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
ACC = REPO / "stablecoin_skynet/data/community/accounts.csv"
OUT = REPO / "data/datasets/stablecoin_trust_engagement/social_snapshots"
OUT.mkdir(parents=True, exist_ok=True)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 SharpeResearchSnapshot/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="ignore")


def parse_telegram(html: str) -> dict:
    out: dict = {}
    m = re.search(
        r">([\d\s,\.]+)</div>\s*<div[^>]*>\s*(subscribers|members)",
        html,
        re.I,
    )
    if not m:
        m = re.search(r"([\d,\.\s]+)\s+(subscribers|members)", html, re.I)
    if m:
        raw = re.sub(r"[^\d]", "", m.group(1))
        if raw:
            out["telegram_members"] = int(raw)
            out["telegram_label"] = m.group(2).lower()
    title = re.search(r'class="tgme_page_title"[^>]*>\s*<span[^>]*>([^<]+)', html)
    if title:
        out["telegram_title"] = title.group(1).strip()
    return out


def main() -> int:
    df = pd.read_csv(ACC)
    rows = []
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for _, r in df.iterrows():
        row = {
            "entity_id": r["slug"],
            "twitter_handle": r.get("twitter_handle"),
            "telegram_url": "" if pd.isna(r.get("telegram_url")) else str(r.get("telegram_url")),
            "followers_current_skynet_card": r.get("followers_current_skynet_card"),
            "holders_end_skynet": r.get("holder_growth_end_count"),
            "snapshot_at": stamp,
        }
        url = row["telegram_url"]
        if url:
            try:
                if not url.startswith("http"):
                    url = "https://t.me/" + url.lstrip("@")
                html = fetch(url)
                row.update(parse_telegram(html))
                row["telegram_fetch_ok"] = 1
            except Exception as exc:
                row["telegram_fetch_ok"] = 0
                row["telegram_error"] = str(exc)[:200]
            time.sleep(1.0)
        rows.append(row)
    outp = OUT / f"social_snapshot_{stamp[:10].replace('-', '')}.csv"
    fields = sorted({k for row in rows for k in row})
    with outp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    (OUT / "social_snapshot_latest.csv").write_text(outp.read_text(encoding="utf-8"), encoding="utf-8")
    ok = sum(1 for r in rows if r.get("telegram_members"))
    print(json.dumps({"wrote": str(outp), "rows": len(rows), "telegram_parsed": ok}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
