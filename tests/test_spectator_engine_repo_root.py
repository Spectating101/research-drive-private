#!/usr/bin/env python3
"""SR_REPO_ROOT must match whatever root scripts/yzu_cluster/... actually lives under.

Two "repo_root" conventions legitimately coexist in this monorepo (see
sharpe_kernel.paths): the outer folder with kernel/+drive/ as siblings, and
the drive/ folder itself. Found live: SpectatorEngine constructed with the
outer root exported SR_REPO_ROOT=<outer>, but scripts/yzu_cluster/scrapers/
only exists under <outer>/drive -- scraper_dispatch.sh's own
`$SR_REPO_ROOT/scripts/$SCRIPT` lookup failed with MODULE_NOT_FOUND on a
real submitted job, even though tool call, craft plan, and submit all
worked correctly upstream.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drive"))

from scripts.yzu_cluster.spectator_engine import SpectatorEngine  # noqa: E402


def _make_monorepo_layout(tmp_path: Path) -> Path:
    """<tmp>/kernel, <tmp>/drive/scripts/yzu_cluster/workers/scraper_dispatch.sh"""
    (tmp_path / "kernel").mkdir()
    dispatch = tmp_path / "drive" / "scripts" / "yzu_cluster" / "workers" / "scraper_dispatch.sh"
    dispatch.parent.mkdir(parents=True)
    dispatch.write_text("#!/usr/bin/env bash\n")
    return tmp_path


def test_sr_repo_root_follows_the_dispatch_script_not_the_outer_root(tmp_path):
    outer = _make_monorepo_layout(tmp_path)
    engine = SpectatorEngine(outer, cfg={})
    assert engine.dispatch_script == outer / "drive/scripts/yzu_cluster/workers/scraper_dispatch.sh"
    assert engine.sr_repo_root == outer / "drive"
    assert engine.sr_repo_root != outer


def test_sr_repo_root_stays_at_repo_root_when_dispatch_lives_there_directly(tmp_path):
    dispatch = tmp_path / "scripts" / "yzu_cluster" / "workers" / "scraper_dispatch.sh"
    dispatch.parent.mkdir(parents=True)
    dispatch.write_text("#!/usr/bin/env bash\n")
    engine = SpectatorEngine(tmp_path, cfg={})
    assert engine.dispatch_script == tmp_path / "scripts/yzu_cluster/workers/scraper_dispatch.sh"
    assert engine.sr_repo_root == tmp_path


def test_env_base_exports_the_resolved_sr_repo_root(tmp_path):
    outer = _make_monorepo_layout(tmp_path)
    engine = SpectatorEngine(outer, cfg={})
    env = engine._env_base()
    assert env["SR_REPO_ROOT"] == str(outer / "drive")
