#!/usr/bin/env python3
"""Static inventory + SHA authority gates for desk hardening."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_orchestrator_submit_always_enforces_execution_policy() -> None:
    src = _read("drive/scripts/yzu_cluster/orchestrator.py")
    assert "enforce_execution_submit" in src
    # submit body must call the gate before validate/create
    submit = src.split("def submit(", 1)[1].split("\n    def ", 1)[0]
    assert "enforce_execution_submit" in submit
    assert submit.index("enforce_execution_submit") < submit.index("validate_plan")


def test_remote_collect_uses_pinned_open_not_urlopen() -> None:
    src = _read("drive/scripts/cluster_agent/remote_collect.py")
    assert "open_pinned_public_url" in src
    assert "urlopen(" not in src
    assert "build_opener(" not in src
    assert "Manual redirect loop" in src or "for _hop in range" in src


def test_scraper_has_dns_aware_network_guard() -> None:
    src = _read("drive/scripts/yzu_cluster/scrapers/generic_url_scrape.mjs")
    assert "installNetworkGuard" in src
    assert "isBlockedUrlAsync" in src
    assert "dns.lookup" in src
    assert "100 && b >= 64 && b <= 127" in src  # CGNAT / Tailscale
    assert 'redirect: "manual"' in src
    assert "pinnedFetchRaw" in src or "pickPublicPinnedAddress" in src
    assert "PLAYWRIGHT_PINNED_FULFILL" in src
    assert "route.fulfill" in src


def test_magic_collect_defaults_fail_closed() -> None:
    src = _read("drive/scripts/research_data_mcp/magic_procure.py")
    assert 'auto_collect_chat", False)' in src or "auto_collect_chat\", False)" in src
    assert 'auto_scrape_after_acquire", False)' in src or "auto_scrape_after_acquire\", False)" in src
    assert "approve_collect" in src
    assert 'auto_approve=False' in src


def test_desk_auth_fail_closed_posts() -> None:
    from scripts.research_data_mcp.desk_auth import path_requires_auth

    assert path_requires_auth("/library/craft/collect-plan", "POST") is True
    assert path_requires_auth("/library/advise", "POST") is True
    assert path_requires_auth("/library/desk/session", "POST") is False
    assert path_requires_auth("/healthz", "GET") is False


def test_scheduler_uses_unforgeable_ops_capability() -> None:
    src = _read("drive/scripts/yzu_cluster/scheduler.py")
    assert "internal_ops_request" in src


def test_executor_packages_network_policy_sibling() -> None:
    src = _read("drive/scripts/yzu_cluster/executor.py")
    assert "network_policy.py" in src


def test_backend_sha_matches_build_json_when_required() -> None:
    """Exact-SHA gate: when build.json exists, private_sha must match git HEAD.

    Opt-out only with RESEARCH_DRIVE_SKIP_SHA_GATE=1 (local dirty experiments).
    """
    if os.environ.get("RESEARCH_DRIVE_SKIP_SHA_GATE") == "1":
        pytest.skip("explicit skip")
    build_path = Path.home() / ".cache/research-drive/front-door-ui/current/research-drive-build.json"
    if not build_path.is_file():
        pytest.skip("no deployed build.json on this host")
    build = json.loads(build_path.read_text(encoding="utf-8"))
    stamped = str(build.get("private_sha") or build.get("backend_sha") or "").strip()
    if not stamped:
        pytest.fail("deployed build.json missing private_sha/backend_sha")
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=str(ROOT),
        text=True,
    ).strip()
    assert stamped.startswith(head[:12]) or head.startswith(stamped[:12]), (
        f"deployed sha {stamped!r} does not match git HEAD {head!r} — "
        "restart front-door after deploy or stamp build.json"
    )
