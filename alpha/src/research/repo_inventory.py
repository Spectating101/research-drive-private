"""Repository inventory and pruning audit for the investment platform."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

GENERATED_DIRS = {
    "backtests/outputs",
    "reports",
    "test-results",
    ".tmp-pw",
    ".playwright-mcp",
    ".locks",
    "deliverables",
    "logs",
    "dist",
}

ACTIVE_INVESTMENT_PREFIXES = (
    "src/research/",
    "trading/execution/",
    "scripts/research_query_engine/",
)

ACTIVE_INVESTMENT_FILES = {
    "scripts/accounting_bundle.py",
    "scripts/accounting_reconcile.py",
    "scripts/alpha_idea_queue.py",
    "scripts/alpha_live_cycle.py",
    "scripts/best_practice_equity_runner.py",
    "scripts/equity_academic_runner.py",
    "scripts/frozen_decision_tracker.py",
    "scripts/investment_agent_tools.py",
    "scripts/investment_capability_audit.py",
    "scripts/investment_cockpit.py",
    "scripts/investment_enforcement_cycle.py",
    "scripts/investment_operator_dashboard.py",
    "scripts/live_trade_from_signal.py",
    "scripts/manifest_gates.py",
    "scripts/platform_status.py",
    "scripts/research_query_engine_cli.py",
    "scripts/run_research_spine.sh",
    "scripts/stock_investment_data_status.py",
    "scripts/thesis_gates.py",
    "scripts/thesis_report.py",
    "config/alpha_idea_queue.csv",
    "config/execution_safety.json",
    "config/investment_capability_map.json",
    "config/research_query_registry.json",
    "config/stock_universe_registry.json",
    "config/thesis_register.csv",
    "docs/INVESTMENT_CAPABILITY_TRACKER.md",
    "docs/INVESTMENT_COCKPIT_COMPONENTS.md",
    "docs/INVESTMENT_PLATFORM_BLUEPRINT.md",
    "docs/OSS_AI_INVESTMENT_LANDSCAPE.md",
    "systemd/investment-enforcement.service",
    "systemd/investment-enforcement.timer",
}

INVESTMENT_LEGACY_KEYWORDS = (
    "alpha",
    "asset_screener",
    "best_practice",
    "equity",
    "factor",
    "idn",
    "portfolio",
    "refinitiv",
    "rebound",
    "sec_",
    "single_factor",
    "spy_beater",
    "stock",
)

PROCUREMENT_KEYWORDS = (
    "procurement",
    "research_data_mcp",
    "collection",
    "datacite",
    "dataset",
    "gdrive",
    "sourcing",
    "vault",
    "yzu",
)

CRYPTO_KEYWORDS = (
    "crypto",
    "stablecoin",
    "coingecko",
    "opensea",
    "etherscan",
    "ethereum",
    "usdt",
    "onchain",
    "nft",
)

FRONTEND_HINTS = (
    "package.json",
    "package-lock.json",
    "vite.config.js",
    "playwright.config.js",
    "index.html",
    "src/app/",
    "src/components/",
    "src/main.jsx",
    "src/styles.css",
    "src/index.css",
)

ROOT_GENERATED_SUFFIXES = (".png", ".html")


@dataclass(frozen=True)
class InventoryRow:
    path: str
    category: str
    disposition: str
    reason: str
    bytes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "category": self.category,
            "disposition": self.disposition,
            "reason": self.reason,
            "bytes": self.bytes,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _rel(path: Path, repo: Path) -> str:
    return str(path.relative_to(repo)).replace("\\", "/")


def _under(path: str, prefixes: Iterable[str]) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix.rstrip("/") + "/") for prefix in prefixes)


def iter_repo_files(repo: Path) -> list[Path]:
    repo = Path(repo)
    files: list[Path] = []
    for path in repo.rglob("*"):
        rel_parts = path.relative_to(repo).parts
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        if path.is_file():
            files.append(path)
    return sorted(files)


def classify_path(path: Path, repo: Path) -> InventoryRow:
    rel = _rel(path, repo)
    lower = rel.lower()
    size = int(path.stat().st_size)
    root_level = "/" not in rel
    first_part = rel.split("/", 1)[0]

    if first_part.startswith(".venv") or first_part in {"MagicMock"}:
        return InventoryRow(rel, "local_environment_artifact", "quarantine_candidate", "local virtualenv/mock environment artifact", size)
    if _under(rel, GENERATED_DIRS):
        return InventoryRow(rel, "generated_artifacts", "keep_generated_or_clean_by_policy", "generated report/backtest/test artifact", size)
    if rel in ACTIVE_INVESTMENT_FILES or _under(rel, ACTIVE_INVESTMENT_PREFIXES):
        return InventoryRow(rel, "active_investment_core", "keep", "active investment platform module/config/doc", size)
    if rel.startswith("tests/"):
        return InventoryRow(rel, "tests", "keep_or_update_with_code", "test coverage", size)
    if rel.startswith("systemd/") and any(name in lower for name in ("alpha", "investment", "research-engine", "idn")):
        return InventoryRow(rel, "ops_units", "keep_or_review", "operator/systemd unit", size)
    if any(h == rel or lower.startswith(h) for h in FRONTEND_HINTS):
        return InventoryRow(rel, "frontend_or_ui", "review_scope", "frontend/UI artifact mixed into repo root", size)
    if root_level and (lower.endswith(ROOT_GENERATED_SUFFIXES) or lower.endswith(".zip") or lower.startswith("deep-research-report")):
        return InventoryRow(rel, "root_generated_clutter", "quarantine_candidate", "root-level generated visual/report artifact", size)
    if any(token in lower for token in PROCUREMENT_KEYWORDS):
        return InventoryRow(rel, "research_procurement", "separate_or_archive_outside_investment_path", "procurement/research-drive surface", size)
    if any(token in lower for token in CRYPTO_KEYWORDS):
        return InventoryRow(rel, "crypto_or_stablecoin", "archive_unless_active_cross_asset_input", "crypto/stablecoin side track", size)
    if rel.startswith("scripts/") and any(token in lower for token in INVESTMENT_LEGACY_KEYWORDS):
        return InventoryRow(rel, "legacy_investment_script", "convert_or_archive_after_manifest_backfill", "investment-like script outside current platform contract", size)
    if rel.startswith("docs/"):
        return InventoryRow(rel, "docs_other", "review", "documentation outside active investment docs", size)
    if rel.startswith("config/"):
        return InventoryRow(rel, "config_other", "review", "configuration outside active investment set", size)
    if rel.startswith("data/") or rel.startswith("scrapes/") or rel.startswith("data_lake/"):
        return InventoryRow(rel, "local_data", "keep_data_or_externalize", "local data/cache artifact", size)
    return InventoryRow(rel, "unclassified", "review", "no rule matched", size)


def build_repo_inventory(repo: Path, *, sample_limit: int = 500) -> dict[str, Any]:
    repo = Path(repo).resolve()
    rows = [classify_path(path, repo) for path in iter_repo_files(repo)]
    by_category: dict[str, dict[str, Any]] = {}
    by_disposition: dict[str, dict[str, Any]] = {}
    for row in rows:
        for bucket, key in ((by_category, row.category), (by_disposition, row.disposition)):
            entry = bucket.setdefault(key, {"count": 0, "bytes": 0})
            entry["count"] += 1
            entry["bytes"] += row.bytes

    quarantine_all = [
        row.as_dict()
        for row in rows
        if row.disposition in {"quarantine_candidate", "archive_unless_active_cross_asset_input", "separate_or_archive_outside_investment_path"}
    ]
    legacy_scripts = [row.as_dict() for row in rows if row.category == "legacy_investment_script"]
    active = [row.as_dict() for row in rows if row.category == "active_investment_core"]
    root_quarantine = [row.as_dict() for row in rows if row.category == "root_generated_clutter"]

    top_level_counts: dict[str, dict[str, Any]] = {}
    for row in rows:
        top = row.path.split("/", 1)[0]
        entry = top_level_counts.setdefault(top, {"count": 0, "bytes": 0})
        entry["count"] += 1
        entry["bytes"] += row.bytes

    return {
        "generated_at": _utc_now(),
        "repo": str(repo),
        "n_files": len(rows),
        "total_bytes": int(sum(row.bytes for row in rows)),
        "category_counts": by_category,
        "disposition_counts": by_disposition,
        "top_level_counts": top_level_counts,
        "active_investment_core": active,
        "legacy_investment_scripts": legacy_scripts,
        "root_quarantine_candidates": root_quarantine,
        "quarantine_candidates": quarantine_all[:sample_limit],
        "quarantine_candidates_truncated": max(0, len(quarantine_all) - sample_limit),
        "sample_rows": [row.as_dict() for row in rows[:sample_limit]],
        "sample_rows_truncated": max(0, len(rows) - sample_limit),
    }


def render_inventory_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Repo Inventory And Prune Audit",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Files: `{report.get('n_files')}`",
        f"- Total bytes: `{report.get('total_bytes')}`",
        "",
        "## Category Counts",
        "",
        "| Category | Files | Bytes |",
        "| --- | ---: | ---: |",
    ]
    for category, stats in sorted((report.get("category_counts") or {}).items()):
        lines.append(f"| {category} | {stats.get('count', 0)} | {stats.get('bytes', 0)} |")

    lines.extend(["", "## Disposition Counts", "", "| Disposition | Files | Bytes |", "| --- | ---: | ---: |"])
    for disposition, stats in sorted((report.get("disposition_counts") or {}).items()):
        lines.append(f"| {disposition} | {stats.get('count', 0)} | {stats.get('bytes', 0)} |")

    lines.extend(["", "## Top-Level Footprint", "", "| Path | Files | Bytes |", "| --- | ---: | ---: |"])
    top = report.get("top_level_counts") or {}
    for name, stats in sorted(top.items(), key=lambda kv: kv[1].get("bytes", 0), reverse=True)[:30]:
        lines.append(f"| `{name}` | {stats.get('count', 0)} | {stats.get('bytes', 0)} |")

    lines.extend(["", "## Safest First Quarantine Batch", ""])
    root_candidates = report.get("root_quarantine_candidates") or []
    if root_candidates:
        lines.append("Root-level generated reports/screenshots/HTML/ZIP files. These are the lowest-risk rearrangement candidates.")
        lines.append("")
        for row in root_candidates[:80]:
            lines.append(f"- `{row['path']}`")
    else:
        lines.append("- none")

    lines.extend(["", "## Legacy Investment Scripts", ""])
    legacy = report.get("legacy_investment_scripts") or []
    if legacy:
        for row in legacy[:80]:
            lines.append(f"- `{row['path']}`: {row['reason']}")
        if len(legacy) > 80:
            lines.append(f"- ... +{len(legacy) - 80} more")
    else:
        lines.append("- none")

    lines.extend(["", "## Quarantine Candidate Sample", ""])
    candidates = report.get("quarantine_candidates") or []
    if candidates:
        for row in candidates[:120]:
            lines.append(f"- `{row['path']}` [{row['category']}]: {row['reason']}")
        truncated = int(report.get("quarantine_candidates_truncated", 0) or 0)
        if truncated:
            lines.append(f"- ... +{truncated} more")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Recommended Next Move",
            "",
            "1. Convert or archive `legacy_investment_script` files one group at a time.",
            "2. Move `root_generated_clutter` into an archive/generated-artifacts directory after confirming no docs link to it.",
            "3. Keep procurement and crypto/stablecoin tracks outside the main investment spine unless a specific artifact feeds alpha.",
            "4. Do not delete generated backtests/reports until the active candidate registry no longer references them.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_repo_inventory(report: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jp = out_dir / "latest.json"
    mp = out_dir / "latest.md"
    jp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    mp.write_text(render_inventory_markdown(report))
    return {"json": str(jp), "markdown": str(mp)}
