#!/usr/bin/env python3
"""Download public macro/market benchmark datasets.

This is the low-risk first batch while paid lab access is unresolved. It pulls
raw source files only and records a manifest with checksums. No credentials are
required.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "data_lake" / "public_macro_market_baseline"
RUN_DATE = date.today().isoformat()

USER_AGENT = (
    "Sharpe-Renaissance research data collector "
    "(contact: local research use; no credentials)"
)


@dataclass(frozen=True)
class DownloadItem:
    source: str
    name: str
    url: str
    relpath: str
    notes: str = ""


FIXED_DOWNLOADS = [
    DownloadItem(
        "kenneth_french",
        "fama_french_3_factors_daily",
        "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip",
        "raw/kenneth_french/F-F_Research_Data_Factors_daily_CSV.zip",
        "US market, SMB, HML, RF daily factors.",
    ),
    DownloadItem(
        "kenneth_french",
        "fama_french_5_factors_daily",
        "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip",
        "raw/kenneth_french/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip",
        "US 5-factor daily file.",
    ),
    DownloadItem(
        "kenneth_french",
        "fama_french_momentum_daily",
        "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_daily_CSV.zip",
        "raw/kenneth_french/F-F_Momentum_Factor_daily_CSV.zip",
        "US daily momentum factor.",
    ),
    DownloadItem(
        "cboe",
        "vix_history",
        "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
        "raw/cboe/VIX_History.csv",
        "Official CBOE VIX daily history.",
    ),
    DownloadItem(
        "policy_uncertainty",
        "all_country_epu",
        "https://www.policyuncertainty.com/media/All_Country_Data.xlsx",
        "raw/policy_uncertainty/All_Country_Data.xlsx",
        "Baker-Bloom-Davis country EPU workbook.",
    ),
    DownloadItem(
        "geopolitical_risk",
        "gpr_export",
        "https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls",
        "raw/geopolitical_risk/data_gpr_export.xls",
        "Caldara-Iacoviello GPR workbook.",
    ),
]


FRED_SERIES = [
    "DFF",
    "FEDFUNDS",
    "DGS1MO",
    "DGS3MO",
    "DGS2",
    "DGS10",
    "DGS30",
    "T10Y2Y",
    "VIXCLS",
    "DTWEXBGS",
    "DEXUSEU",
    "DEXJPUS",
    "DEXCHUS",
    "DEXUSUK",
    "DEXCAUS",
    "DEXUSAL",
    "DCOILWTICO",
    "DCOILBRENTEU",
    "CPIAUCSL",
    "CPILFESL",
    "UNRATE",
    "INDPRO",
    "PAYEMS",
    "M2SL",
    "WALCL",
]


WORLD_BANK_INDICATORS = [
    "NY.GDP.MKTP.KD.ZG",
    "NE.GDI.FTOT.KD.ZG",
    "FP.CPI.TOTL.ZG",
    "SL.UEM.TOTL.ZS",
    "NE.EXP.GNFS.KD.ZG",
    "BX.KLT.DINV.WD.GD.ZS",
    "NE.TRD.GNFS.ZS",
    "BN.CAB.XOKA.GD.ZS",
    "CM.MKT.LCAP.GD.ZS",
    "RL.EST",
    "GE.EST",
    "RQ.EST",
    "CC.EST",
    "PV.EST",
    "VA.EST",
]


def request_bytes(url: str, timeout: int = 30) -> tuple[bytes, dict[str, str]]:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as response:
        data = response.read()
        headers = {k.lower(): v for k, v in response.headers.items()}
    return data, headers


def curl_download(url: str, dest: Path, timeout: int = 60) -> dict[str, str]:
    """Download with curl's total timeout; urllib can hang on some public endpoints."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    header_path = dest.with_suffix(dest.suffix + ".headers.tmp")
    tmp_path = dest.with_suffix(dest.suffix + ".part")
    cmd = [
        "curl",
        "-L",
        "--fail",
        "--http1.1",
        "--silent",
        "--show-error",
        "--max-time",
        str(timeout),
        "-D",
        str(header_path),
        "-o",
        str(tmp_path),
        url,
    ]
    try:
        subprocess.run(cmd, check=True, cwd=ROOT)
        tmp_path.replace(dest)
        raw_headers = header_path.read_text(errors="ignore") if header_path.exists() else ""
    finally:
        header_path.unlink(missing_ok=True)
        tmp_path.unlink(missing_ok=True)
    headers: dict[str, str] = {}
    for line in raw_headers.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return headers


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_download(item: DownloadItem, run_dir: Path) -> dict[str, str | int]:
    dest = run_dir / item.relpath
    headers = curl_download(item.url, dest)
    data = dest.read_bytes()
    digest = sha256(data)
    return {
        "source": item.source,
        "name": item.name,
        "url": item.url,
        "path": str(dest.relative_to(run_dir)),
        "size_bytes": len(data),
        "sha256": digest,
        "content_type": headers.get("content-type", ""),
        "last_modified": headers.get("last-modified", ""),
        "notes": item.notes,
    }


def discover_wui_downloads() -> list[DownloadItem]:
    page_url = "https://worlduncertaintyindex.com/data/"
    data, _ = request_bytes(page_url)
    html = data.decode("utf-8", errors="ignore")
    hrefs = sorted(set(re.findall(r'href=["\']([^"\']+\.(?:xlsx|xls|csv))["\']', html, re.I)))
    items = []
    for href in hrefs:
        url = urljoin(page_url, href)
        filename = Path(url.split("?", 1)[0]).name
        if not filename:
            continue
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename)
        items.append(
            DownloadItem(
                "world_uncertainty_index",
                safe_name.rsplit(".", 1)[0],
                url,
                f"raw/world_uncertainty_index/{safe_name}",
                "Discovered from World Uncertainty Index data page.",
            )
        )
    return items


def build_download_list() -> list[DownloadItem]:
    items = list(FIXED_DOWNLOADS)
    for series in FRED_SERIES:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={quote(series)}"
        items.append(
            DownloadItem(
                "fred",
                series,
                url,
                f"raw/fred/{series}.csv",
                "FRED graph CSV endpoint.",
            )
        )
    for indicator in WORLD_BANK_INDICATORS:
        url = f"https://api.worldbank.org/v2/en/indicator/{quote(indicator)}?downloadformat=csv"
        items.append(
            DownloadItem(
                "world_bank",
                indicator,
                url,
                f"raw/world_bank/{indicator}.zip",
                "World Bank indicator CSV zip.",
            )
        )
    try:
        items.extend(discover_wui_downloads())
    except Exception as exc:
        print(f"WARN: WUI discovery failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    return items


def write_manifest(run_dir: Path, records: list[dict[str, str | int]]) -> None:
    manifest_dir = run_dir / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    fields = [
        "source",
        "name",
        "url",
        "path",
        "size_bytes",
        "sha256",
        "content_type",
        "last_modified",
        "status",
        "notes",
        "error",
    ]
    with (manifest_dir / "manifest.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow({k: row.get(k, "") for k in fields})
    with (manifest_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    with (manifest_dir / "SHA256SUMS.txt").open("w", encoding="utf-8") as f:
        for row in records:
            if row.get("status") == "ok":
                f.write(f"{row['sha256']}  {row['path']}\n")


def write_readme(run_dir: Path, records: list[dict[str, str | int]]) -> None:
    ok = [r for r in records if r.get("status") == "ok"]
    failed = [r for r in records if r.get("status") != "ok"]
    by_source: dict[str, int] = {}
    for row in ok:
        by_source[str(row["source"])] = by_source.get(str(row["source"]), 0) + 1
    lines = [
        "# Public Macro Market Baseline",
        "",
        f"Run timestamp UTC: {datetime.now(timezone.utc).isoformat()}",
        "",
        "This folder contains raw public benchmark datasets downloaded without credentials.",
        "It is meant to anchor market, macro, risk, uncertainty, and factor research while paid-data access is unresolved.",
        "",
        f"Successful files: {len(ok)}",
        f"Failed files: {len(failed)}",
        "",
        "## Successful Downloads By Source",
        "",
    ]
    for source, count in sorted(by_source.items()):
        lines.append(f"- `{source}`: {count}")
    if failed:
        lines.extend(["", "## Failed Downloads", ""])
        for row in failed:
            lines.append(f"- `{row.get('source')}/{row.get('name')}`: {row.get('error')}")
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `raw/`: source files exactly as downloaded.",
            "- `manifests/manifest.csv`: download provenance and checksums.",
            "- `manifests/SHA256SUMS.txt`: checksums for successful files.",
        ]
    )
    (run_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    run_dir = OUT_ROOT / RUN_DATE
    run_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, str | int]] = []
    items = build_download_list()
    for idx, item in enumerate(items, start=1):
        print(f"[{idx}/{len(items)}] {item.source}/{item.name}", flush=True)
        try:
            row = write_download(item, run_dir)
            row["status"] = "ok"
            row["error"] = ""
            print(f"  ok {row['size_bytes']} bytes", flush=True)
        except Exception as exc:
            row = {
                "source": item.source,
                "name": item.name,
                "url": item.url,
                "path": item.relpath,
                "size_bytes": 0,
                "sha256": "",
                "content_type": "",
                "last_modified": "",
                "status": "error",
                "notes": item.notes,
                "error": f"{type(exc).__name__}: {exc}",
            }
            print(f"  ERROR {row['error']}", file=sys.stderr, flush=True)
        records.append(row)
    write_manifest(run_dir, records)
    write_readme(run_dir, records)
    print(f"\nWrote {run_dir}")
    print(f"Manifest: {run_dir / 'manifests' / 'manifest.csv'}")
    return 0 if all(r.get("status") == "ok" for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
