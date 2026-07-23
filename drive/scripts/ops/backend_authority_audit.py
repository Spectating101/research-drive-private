#!/usr/bin/env python3
"""Static release audit for Research Drive backend authority and readiness truth.

This does not replace the live Optiplex battery. It produces an exact-SHA,
machine-readable inventory of submit, approval, privilege, and readiness paths,
while failing on repository guarantees that must be structurally true.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DRIVE = ROOT / "drive"

NAMED_QUARANTINED_PIPELINES = (
    "skynet_stablecoin_harvest",
    "coingecko_daily",
    "ethereum_usdt_rpc_pilot",
)

MAGIC_FALSE_PATHS = (
    ("discovery", "auto_collect_chat"),
    ("discovery", "auto_scrape_chat"),
    ("discovery", "auto_collect_datacite"),
    ("flywheel", "auto_follow_scrape_downloads"),
    ("flywheel", "auto_approve_scrape_downloads"),
    ("agent", "auto_scrape_after_acquire"),
    ("agent", "auto_follow_scrape_harvest"),
    ("agent", "auto_approve_probe_collect"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dotted_get(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _source_line(path: Path, line: int) -> str:
    try:
        rows = path.read_text(encoding="utf-8").splitlines()
        return rows[line - 1].strip() if 0 < line <= len(rows) else ""
    except OSError:
        return ""


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts = [func.attr]
        value = func.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
        return ".".join(reversed(parts))
    return ""


def _keyword_value(node: ast.Call, name: str) -> str | None:
    for keyword in node.keywords:
        if keyword.arg != name:
            continue
        try:
            return ast.unparse(keyword.value)
        except Exception:
            return type(keyword.value).__name__
    return None


def _scan_python() -> dict[str, list[dict[str, Any]]]:
    inventory: dict[str, list[dict[str, Any]]] = {
        "submit_calls": [],
        "approval_calls": [],
        "auto_approve_calls": [],
        "ops_privileged_references": [],
        "auto_approve_safe_references": [],
    }
    for path in sorted((DRIVE / "scripts").rglob("*.py")):
        rel = str(path.relative_to(ROOT))
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=rel)
        except (OSError, SyntaxError) as exc:
            inventory.setdefault("parse_errors", []).append({"path": rel, "error": str(exc)})
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _call_name(node)
                row = {
                    "path": rel,
                    "line": getattr(node, "lineno", 0),
                    "call": name,
                    "source": _source_line(path, getattr(node, "lineno", 0)),
                }
                if name.endswith(".submit") or name == "submit":
                    inventory["submit_calls"].append(row)
                if name.endswith(".approve") or name == "approve":
                    inventory["approval_calls"].append(row)
                auto = _keyword_value(node, "auto_approve")
                if auto is not None:
                    inventory["auto_approve_calls"].append({**row, "value": auto})
                safe = _keyword_value(node, "auto_approve_safe")
                if safe is not None:
                    inventory["auto_approve_safe_references"].append({**row, "value": safe})

            if isinstance(node, ast.Constant) and node.value == "ops_privileged":
                inventory["ops_privileged_references"].append(
                    {
                        "path": rel,
                        "line": getattr(node, "lineno", 0),
                        "source": _source_line(path, getattr(node, "lineno", 0)),
                    }
                )
            if isinstance(node, ast.Constant) and node.value == "auto_approve_safe":
                inventory["auto_approve_safe_references"].append(
                    {
                        "path": rel,
                        "line": getattr(node, "lineno", 0),
                        "source": _source_line(path, getattr(node, "lineno", 0)),
                    }
                )
    for rows in inventory.values():
        if isinstance(rows, list):
            rows.sort(key=lambda row: (row.get("path", ""), row.get("line", 0)))
    return inventory


def _hard_guarantees() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    passed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    cluster_path = DRIVE / "config/yzu_cluster.json"
    cluster = _load_json(cluster_path)
    pipelines = cluster.get("pipelines") or {}
    for pipeline_id in NAMED_QUARANTINED_PIPELINES:
        row = pipelines.get(pipeline_id) or {}
        ok = (
            row.get("enabled") is False
            and row.get("procurement_triggered") is False
            and row.get("legacy_quarantine") is True
        )
        target = passed if ok else failed
        target.append(
            {
                "gate": "named_pipeline_quarantined",
                "pipeline_id": pipeline_id,
                "observed": {
                    "enabled": row.get("enabled"),
                    "procurement_triggered": row.get("procurement_triggered"),
                    "legacy_quarantine": row.get("legacy_quarantine"),
                },
            }
        )

    magic_path = DRIVE / "config/procurement_magic.json"
    magic = _load_json(magic_path)
    for dotted in MAGIC_FALSE_PATHS:
        value = _dotted_get(magic, dotted)
        target = passed if value is False else failed
        target.append(
            {
                "gate": "auto_collection_default_false",
                "path": ".".join(dotted),
                "observed": value,
            }
        )

    promotion_path = DRIVE / "scripts/research_data_mcp/registry_promotion.py"
    promotion = promotion_path.read_text(encoding="utf-8")
    forbidden_readiness_patterns = {
        "readiness_assignment_instant": r"\breadiness\s*=\s*[\"']instant[\"']",
        "literal_analysis_readiness_instant": r"[\"']analysis_readiness[\"']\s*:\s*[\"']instant[\"']",
        "materialized_instant_mode": r"[\"']materialized_instant[\"']",
    }
    for gate, pattern in forbidden_readiness_patterns.items():
        matches = [match.group(0) for match in re.finditer(pattern, promotion)]
        target = failed if matches else passed
        target.append({"gate": gate, "matches": matches})

    acquisitions = (DRIVE / "scripts/yzu_cluster/acquisitions.py").read_text(encoding="utf-8")
    required_tokens = (
        "api_error_envelope",
        "empty_collection",
        "metadata_only_backend",
        '"revision_id": revision_id',
    )
    for token in required_tokens:
        target = passed if token in acquisitions else failed
        target.append({"gate": "strict_query_smoke_token", "token": token})

    tests = (DRIVE / "tests/test_hardening_gates.py").read_text(encoding="utf-8")
    weak_phrase = "accept either ok or clear error shape"
    target = failed if weak_phrase in tests else passed
    target.append({"gate": "no_permissive_query_smoke_assertion", "found": weak_phrase in tests})

    return passed, failed


def build_report() -> dict[str, Any]:
    passed, failed = _hard_guarantees()
    inventory = _scan_python()
    warnings: list[dict[str, Any]] = []

    jobs_path = DRIVE / "scripts/research_data_mcp/jobs.py"
    jobs_source = jobs_path.read_text(encoding="utf-8")
    if '(plan or {}).get("ops_privileged")' in jobs_source or 'request.get("ops_privileged")' in jobs_source:
        warnings.append(
            {
                "code": "ops_scope_derived_from_payload",
                "severity": "high",
                "path": str(jobs_path.relative_to(ROOT)),
                "message": "Live audit must prove untrusted faculty/Composer payloads cannot self-assert ops_privileged.",
            }
        )

    gdelt = ((_load_json(DRIVE / "config/yzu_cluster.json").get("pipelines") or {}).get("gdelt_fleet") or {})
    if gdelt.get("enabled") or gdelt.get("procurement_triggered"):
        warnings.append(
            {
                "code": "gdelt_fleet_active",
                "severity": "review",
                "observed": {
                    "enabled": gdelt.get("enabled"),
                    "procurement_triggered": gdelt.get("procurement_triggered"),
                },
                "message": "Classify as ops infrastructure or quarantine as a named product lane.",
            }
        )

    return {
        "generated_at": _now(),
        "repository": "Spectating101/research-drive-private",
        "sha": _git_sha(),
        "hard_guarantees": {
            "passed": passed,
            "failed": failed,
            "ok": not failed,
        },
        "warnings": warnings,
        "inventory": inventory,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/backend_authority_inventory.json")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = build_report()
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "sha": report["sha"],
        "hard_guarantees_ok": report["hard_guarantees"]["ok"],
        "failed": len(report["hard_guarantees"]["failed"]),
        "warnings": len(report["warnings"]),
        "submit_calls": len(report["inventory"]["submit_calls"]),
        "output": str(output.relative_to(ROOT)),
    }, indent=2))
    return 1 if args.strict and not report["hard_guarantees"]["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
