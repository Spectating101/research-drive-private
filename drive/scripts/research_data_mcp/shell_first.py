#!/usr/bin/env python3
"""Shell-first procurement — try curl/browser locally, escalate to equipment when needed.

Philosophy:
  1. LLM + shell (curl, probe) handles simple public HTTP first.
  2. Equipment (jobs, cluster scrape, registry, DOI pipeline) only when shell
     cannot complete or when equipment-only capability is required.

Equipment adds what shell cannot:
  - SEC-compliant / governed http_manifest + registry promotion
  - Spectator/Playwright on cluster for blocked portals
  - source_probe → connector routing (BTS ASP forms)
  - Local catalog query_dataset / queue / pipeline shards
  - Long parallel PREZIP / harvest jobs with job ids
  - Datacite DOI resolve + license flow
  - GDrive hydrate, RPC/BigQuery registry fallbacks
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.research_data_mcp.scrape_plan import classify_url


@dataclass
class ShellAttempt:
    ok: bool
    bytes_written: int = 0
    path: str = ""
    method: str = ""
    detail: str = ""
    escalate: bool = False
    escalate_reason: str = ""


# When shell fails or cannot proceed, equipment should take over for these reasons.
ESCALATE_BLOCKED_HTTP = "blocked_http"  # 403, 401, cloudflare
ESCALATE_NOT_DIRECT = "not_direct_http"  # portal / html_catalog
ESCALATE_NEEDS_BROWSER = "needs_browser"
ESCALATE_NEEDS_CLUSTER = "needs_cluster_job"  # long download, pipeline, queue
ESCALATE_NEEDS_REGISTRY = "needs_local_registry"  # query_dataset, already on disk
ESCALATE_NEEDS_DOI = "needs_datacite_pipeline"
ESCALATE_INDEX_MISS = "index_miss_acquire"  # obscure goal, plan+probe chain


def equipment_only_capabilities() -> list[str]:
    return [
        "cluster Playwright scrape (Spectator)",
        "source_probe + site connector routing",
        "YZU job queue with approve/auto-approve",
        "registered pipelines (Skynet, USDT RPC, …)",
        "collection queue tasks + hydrate from GDrive",
        "registry query_dataset / BigQuery / RPC samples",
        "DataCite DOI resolve + http_manifest from repository",
        "procured path + dataset promotion into catalog",
    ]


def shell_try_direct_download(
    repo_root: Path,
    url: str,
    *,
    dest_dir: Path | None = None,
    timeout_s: int = 60,
    user_agent: str = "SharpeRenaissance research@yzu.edu.tw",
) -> ShellAttempt:
    """Try curl for direct_http URLs. Returns escalate=True when equipment should run."""
    url = (url or "").strip()
    if not url.startswith("http"):
        return ShellAttempt(ok=False, escalate=True, escalate_reason=ESCALATE_NOT_DIRECT, detail="not a url")

    mode = classify_url(url)
    if mode != "direct_http":
        return ShellAttempt(
            ok=False,
            escalate=True,
            escalate_reason=ESCALATE_NOT_DIRECT,
            detail=f"classify_url={mode}",
        )

    root = Path(repo_root).resolve()
    out_dir = dest_dir or (root / "data_lake/procurement_audit/shell_first" / _url_slug(url))
    out_dir.mkdir(parents=True, exist_ok=True)
    name = url.rstrip("/").split("/")[-1].split("?")[0] or "download.bin"
    dest = out_dir / name

    try:
        subprocess.run(
            [
                "curl",
                "-fsSL",
                "-A",
                user_agent,
                "--max-time",
                str(timeout_s),
                "-o",
                str(dest),
                url,
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or b"").decode(errors="replace")[:200]
        code_hint = "403" in err or "401" in err
        return ShellAttempt(
            ok=False,
            escalate=True,
            escalate_reason=ESCALATE_BLOCKED_HTTP if code_hint else ESCALATE_NEEDS_CLUSTER,
            detail=err or "curl failed",
            method="curl",
        )

    if dest.is_file() and dest.stat().st_size > 0:
        try:
            rel = str(dest.relative_to(root))
        except ValueError:
            rel = str(dest)
        return ShellAttempt(
            ok=True,
            bytes_written=dest.stat().st_size,
            path=rel,
            method="curl",
            detail="shell_ok",
            escalate=False,
        )

    return ShellAttempt(
        ok=False,
        escalate=True,
        escalate_reason=ESCALATE_NEEDS_CLUSTER,
        detail="empty file",
        method="curl",
    )


def should_escalate_probe(probe_result: dict[str, Any]) -> tuple[bool, str]:
    """After gateway.probe_source, decide if shell is done and equipment must run."""
    rec = probe_result.get("recommendation") or probe_result.get("probe") or probe_result
    if not isinstance(rec, dict):
        return True, ESCALATE_NEEDS_BROWSER
    action = str(rec.get("recommended_action") or rec.get("access_mode") or "").lower()
    feasibility = str(rec.get("feasibility") or rec.get("status") or "").lower()
    links = int(rec.get("downloadable_links") or rec.get("direct_links") or 0)

    if links > 0 and "direct" in action:
        return False, ""
    if "browser" in action or "connector" in action or "scrape" in action:
        return True, ESCALATE_NEEDS_BROWSER
    if feasibility in {"html_catalog", "portal", "blocked"}:
        return True, ESCALATE_NEEDS_BROWSER
    if "manifest" in action and links == 0:
        return True, ESCALATE_NEEDS_BROWSER
    return True, ESCALATE_NEEDS_BROWSER


def trap_query_blocks_doi_collect(query: str) -> bool:
    """Kayak-style traps: do not auto-collect random DOIs."""
    q = (query or "").lower()
    if "kayak" in q and any(t in q for t in ("api dump", "historical", "csv", "2010", "2024")):
        return True
    if "api dump" in q and "flight" in q:
        return True
    return False


def _url_slug(url: str) -> str:
    import hashlib

    return hashlib.sha256(url.encode()).hexdigest()[:12]
