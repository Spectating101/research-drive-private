#!/usr/bin/env python3
"""One-time layout migration: drive (procurement) + alpha + kernel under repo root.

Idempotent: skips moves when destination already exists. Creates symlinks at legacy
paths so systemd and existing shell habits keep working.
"""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRIVE = ROOT / "drive"
ALPHA = ROOT / "alpha"
KERNEL = ROOT / "kernel"

# Whole directories → drive
DRIVE_DIR_MOVES = [
    ("scripts/yzu_cluster", "drive/scripts/yzu_cluster"),
    ("scripts/research_data_mcp", "drive/scripts/research_data_mcp"),
    ("scripts/research_query_engine", "drive/scripts/research_query_engine"),
    ("scripts/cluster_agent", "drive/scripts/cluster_agent"),
    ("scripts/data_catalog", "drive/scripts/data_catalog"),
]

# Whole directories → alpha
ALPHA_DIR_MOVES = [
    ("trading", "alpha/trading"),
    ("high_perf", "alpha/high_perf"),
    ("engine", "alpha/engine"),
    ("api", "alpha/api"),
    ("src/strategy", "alpha/src/strategy"),
    ("src/intelligence", "alpha/src/intelligence"),
    ("src/models", "alpha/src/models"),
    ("src/data_sources", "alpha/src/data_sources"),
    ("src/auth", "alpha/src/auth"),
    ("src/billing", "alpha/src/billing"),
    ("src/middleware", "alpha/src/middleware"),
    ("src/integrations", "alpha/src/integrations"),
    ("src/research", "alpha/src/research"),
]

DRIVE_SRC_MOVES = [
    ("src/v2", "drive/src/v2"),
    ("src/app", "drive/src/app"),
    ("src/components", "drive/src/components"),
    ("src/lib", "drive/src/lib"),
]

DRIVE_SCRIPT_PREFIXES = (
    "run_yzu_",
    "run_research_data_mcp",
    "run_research_query_engine",
    "run_data_collection",
    "run_news_shock",
    "run_gdelt",
    "run_after_news",
    "run_public_data_sidecar",
    "run_bulk_unlock",
    "run_dataset_index",
    "run_sourcing",
    "run_coingecko",
    "submit_etherscan",
    "submit_skynet",
    "harvest_stablecoin",
    "hydrate_stablecoin",
    "build_stablecoin",
    "export_professor_stablecoin",
    "probe_stablecoin",
    "sync_news_shock",
    "sync_reddit",
    "procurement_",
    "install_yzu",
    "install_collection",
    "plan_news_shock",
    "guard_gdelt",
    "reclaim_gdelt",
    "monitor_gdelt",
    "remote_gdelt",
    "capture_desk",
    "capture_sourcing",
    "deploy_yzu",
    "build_faculty",
    "download_public_macro",
    "fetch_twse",
    "fetch_taiwan",
    "fetch_accessible",
    "fetch_asia_sourced",
    "build_asia_entity",
    "build_asia_ticker",
    "build_asia_news",
    "analyze_asia_news",
    "sec_fetch_",
    "check_data_collection",
    "run_react_reference_desk",
    "rd_",
    "ui_visual_audit",
    "run_rd_",
)

ALPHA_SCRIPT_PREFIXES = (
    "alpha_",
    "idn_",
    "run_idn",
    "run_unified_platform",
    "run_alpha",
    "run_news_strategy",
    "promote_signal",
    "investment_",
    "live_trade",
    "best_practice",
    "manifest_gates",
    "thesis_",
    "accounting_",
    "frozen_decision",
    "stock_investment",
    "run_coingecko_daily",  # alpha consumer path if present
    "explain_week",
    "build_ticker_research",
    "build_cross_asset",
)

DRIVE_CONFIG_FILES = [
    "yzu_cluster.json",
    "data_collection_queue.json",
    "collection_partitions.json",
    "collection_layout.json",
    "collection_scale.json",
    "collection_semantic.json",
    "partition_sync.json",
    "storage_tiers.json",
    "gdelt_expanded_fleet.json",
    "gdelt_expanded_queue.json",
    "gdelt_crypto_overlay.json",
    "post_gdelt_data_collection_queue_20260526.json",
    "desk_sources.json",
    "desk_demo_catalog.json",
    "procurement_governance.json",
    "procurement_magic.json",
    "procurement_registry_map.json",
    "research_data_mcp.example.json",
    "research_query_registry.json",
]

ALPHA_CONFIG_FILES = [
    "platform_integration.json",
    "investment_capability_map.json",
    "dynamic_regime_protocol.json",
    "dynamic_regime_protocol_v2.json",
    "thesis_register.csv",
    "alpha_idea_queue.csv",
]


def _ensure(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _move_tree(src_rel: str, dst_rel: str) -> None:
    src = ROOT / src_rel
    dst = ROOT / dst_rel
    if not src.exists():
        return
    if dst.exists():
        return
    _ensure(dst.parent)
    shutil.move(str(src), str(dst))
    print(f"moved {src_rel} -> {dst_rel}")


def _symlink(target_rel: str, link_rel: str) -> None:
    link = ROOT / link_rel
    target = ROOT / target_rel
    if link.exists() or link.is_symlink():
        return
    if not target.exists():
        return
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(os.path.relpath(target, link.parent), link)
    print(f"symlink {link_rel} -> {target_rel}")


def _move_scripts_by_prefix(prefixes: tuple[str, ...], dest: Path) -> None:
    scripts = ROOT / "scripts"
    if not scripts.exists():
        return
    _ensure(dest)
    for path in sorted(scripts.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        if name in {"migrate_repo_split.py", "setup_research_platform.sh"}:
            continue
        if not any(name.startswith(p) for p in prefixes):
            continue
        target = dest / name
        if target.exists():
            continue
        shutil.move(str(path), str(target))
        print(f"moved scripts/{name} -> {dest.relative_to(ROOT)}/{name}")


def _move_config_files(names: list[str], dest_dir: Path, link_dir: Path) -> None:
    _ensure(dest_dir)
    cfg = ROOT / "config"
    for name in names:
        src = cfg / name
        if not src.exists():
            continue
        dst = dest_dir / name
        if not dst.exists():
            shutil.move(str(src), str(dst))
            print(f"moved config/{name} -> {dest_dir.relative_to(ROOT)}/{name}")
        link = link_dir / name
        if not link.exists() and dst.exists():
            os.symlink(os.path.relpath(dst, link_dir), link)
            print(f"symlink config/{name} -> {dst.relative_to(ROOT)}")


def _symlink_all_moved_scripts() -> None:
    """Legacy shims: scripts/foo -> drive/scripts/foo or alpha/scripts/foo."""
    for bucket, sub in (("drive", DRIVE / "scripts"), ("alpha", ALPHA / "scripts")):
        if not sub.is_dir():
            continue
        for path in sorted(sub.iterdir()):
            if not path.is_file():
                continue
            _symlink(str(path.relative_to(ROOT)), f"scripts/{path.name}")


def main() -> int:
    _ensure(DRIVE / "scripts")
    _ensure(DRIVE / "src")
    _ensure(DRIVE / "config")
    _ensure(ALPHA / "scripts")
    _ensure(ALPHA / "src")
    _ensure(ALPHA / "config")
    _ensure(KERNEL / "sharpe_kernel")

    for src, dst in DRIVE_DIR_MOVES + ALPHA_DIR_MOVES + DRIVE_SRC_MOVES:
        _move_tree(src, dst)

    _move_scripts_by_prefix(DRIVE_SCRIPT_PREFIXES, DRIVE / "scripts")
    _move_scripts_by_prefix(ALPHA_SCRIPT_PREFIXES, ALPHA / "scripts")

    # Move selected alpha scripts by exact name
    for name in (
        "run_unified_platform_cycle.py",
        "run_research_spine.sh",
        "platform_status.py",
        "alpha_live_cycle.py",
        "alpha_paper_tracker.py",
        "alpha_daily_scorecard.py",
        "alpha_insights_walkforward_runner.py",
        "investment_research_engine_audit.py",
    ):
        src = ROOT / "scripts" / name
        if src.exists() and not (ALPHA / "scripts" / name).exists():
            shutil.move(str(src), str(ALPHA / "scripts" / name))
            print(f"moved scripts/{name} -> alpha/scripts/{name}")

    _move_config_files(DRIVE_CONFIG_FILES, DRIVE / "config", ROOT / "config")
    _move_config_files(ALPHA_CONFIG_FILES, ALPHA / "config", ROOT / "config")

    # Legacy symlinks for moved script trees
    for _, dst in DRIVE_DIR_MOVES:
        link = dst.replace("drive/", "")
        _symlink(dst, link)

    # Legacy symlinks for key entrypoints
    for name in (
        "run_yzu_cluster.sh",
        "run_research_data_mcp.sh",
        "run_research_query_engine.sh",
        "run_data_collection_queue.py",
        "run_news_shock_gkg_expanded_fleet.sh",
        "alpha_live_cycle.py",
        "run_unified_platform_cycle.py",
        "run_research_spine.sh",
    ):
        src = DRIVE / "scripts" / name
        if not src.exists():
            src = ALPHA / "scripts" / name
        if src.exists():
            _symlink(str(src.relative_to(ROOT)), f"scripts/{name}")

    # src/v2 symlink for vite @ alias
    _symlink("drive/src/v2", "src/v2")

    _symlink_all_moved_scripts()

    print("migration_complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
