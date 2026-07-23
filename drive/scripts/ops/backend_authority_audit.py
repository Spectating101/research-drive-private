#!/usr/bin/env python3
"""Exact-SHA static audit for backend execution authority and readiness truth.

This complements, but does not replace, the live Optiplex evidence battery.
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

QUARANTINED_PIPELINES = (
    "skynet_stablecoin_harvest",
    "coingecko_daily",
    "ethereum_usdt_rpc_pilot",
)

AUTO_FALSE_PATHS = (
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
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
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


def _call_name(node: ast.Call) -> str:
    value: ast.expr = node.func
    parts: list[str] = []
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if isinstance(value, ast.Name):
        parts.append(value.id)
    return ".".join(reversed(parts))


def _keyword(node: ast.Call, key: str) -> str | None:
    for item in node.keywords:
        if item.arg == key:
            try:
                return ast.unparse(item.value)
            except Exception:
                return type(item.value).__name__
    return None


def _line(path: Path, number: int) -> str:
    try:
        rows = path.read_text(encoding="utf-8").splitlines()
        return rows[number - 1].strip() if 0 < number <= len(rows) else ""
    except OSError:
        return ""


def _inventory() -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {
        "submit_calls": [],
        "approve_calls": [],
        "auto_approve_calls": [],
        "auto_approve_safe_calls": [],
        "ops_privileged_references": [],
        "parse_errors": [],
    }
    for path in sorted((DRIVE / "scripts").rglob("*.py")):
        rel = str(path.relative_to(ROOT))
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except (OSError, SyntaxError) as exc:
            out["parse_errors"].append({"path": rel, "error": str(exc)})
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _call_name(node)
                row = {
                    "path": rel,
                    "line": getattr(node, "lineno", 0),
                    "call": name,
                    "source": _line(path, getattr(node, "lineno", 0)),
                }
                if name.endswith(".submit") or name == "submit":
                    out["submit_calls"].append(row)
                if name.endswith(".approve") or name == "approve":
                    out["approve_calls"].append(row)
                value = _keyword(node, "auto_approve")
                if value is not None:
                    out["auto_approve_calls"].append({**row, "value": value})
                safe = _keyword(node, "auto_approve_safe")
                if safe is not None:
                    out["auto_approve_safe_calls"].append({**row, "value": safe})
            if isinstance(node, ast.Constant) and node.value == "ops_privileged":
                out["ops_privileged_references"].append(
                    {
                        "path": rel,
                        "line": getattr(node, "lineno", 0),
                        "source": _line(path, getattr(node, "lineno", 0)),
                    }
                )
    for rows in out.values():
        rows.sort(key=lambda row: (row.get("path", ""), row.get("line", 0)))
    return out


def _gate(results: list[dict[str, Any]], failures: list[dict[str, Any]], ok: bool, gate: str, **meta: Any) -> None:
    (results if ok else failures).append({"gate": gate, **meta})


def _hard_guarantees() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    passed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    cluster = _load_json(DRIVE / "config/yzu_cluster.json")
    pipelines = cluster.get("pipelines") or {}
    for pipeline_id in QUARANTINED_PIPELINES:
        row = pipelines.get(pipeline_id) or {}
        _gate(
            passed,
            failed,
            row.get("enabled") is False
            and row.get("procurement_triggered") is False
            and row.get("legacy_quarantine") is True,
            "named_pipeline_quarantined",
            pipeline_id=pipeline_id,
            observed={
                "enabled": row.get("enabled"),
                "procurement_triggered": row.get("procurement_triggered"),
                "legacy_quarantine": row.get("legacy_quarantine"),
            },
        )

    magic = _load_json(DRIVE / "config/procurement_magic.json")
    for dotted in AUTO_FALSE_PATHS:
        value = _dotted_get(magic, dotted)
        # Retired keys are equivalent to disabled only because all current call
        # sites default these controls to False. Record the distinction.
        _gate(
            passed,
            failed,
            value in {False, None},
            "auto_collection_disabled_or_removed",
            path=".".join(dotted),
            observed=value,
            state="removed" if value is None else "disabled",
        )

    policy_path = DRIVE / "scripts/research_data_mcp/execution_policy.py"
    policy = policy_path.read_text(encoding="utf-8") if policy_path.is_file() else ""
    orchestrator = (DRIVE / "scripts/yzu_cluster/orchestrator.py").read_text(encoding="utf-8")
    jobs = (DRIVE / "scripts/research_data_mcp/jobs.py").read_text(encoding="utf-8")
    _gate(passed, failed, bool(policy), "execution_policy_exists")
    _gate(
        passed,
        failed,
        "plan.pop(\"ops_privileged\", None)" in policy
        and "request.pop(\"ops_privileged\", None)" in policy,
        "client_privilege_bits_stripped",
    )
    _gate(
        passed,
        failed,
        "enforce_execution_submit" in orchestrator,
        "orchestrator_uses_lowest_execution_gate",
    )
    _gate(
        passed,
        failed,
        'request.get("ops_privileged")' not in jobs
        and '(plan or {}).get("ops_privileged")' not in jobs,
        "job_service_does_not_trust_client_ops_flag",
    )
    _gate(
        passed,
        failed,
        "if scope == \"faculty\":" in policy and "auto_approve = False" in policy,
        "faculty_auto_approve_forced_false",
    )

    promotion = (DRIVE / "scripts/research_data_mcp/registry_promotion.py").read_text(encoding="utf-8")
    for gate, pattern in {
        "no_readiness_assignment_instant": r"\breadiness\s*=\s*[\"']instant[\"']",
        "no_literal_analysis_readiness_instant": r"[\"']analysis_readiness[\"']\s*:\s*[\"']instant[\"']",
        "no_materialized_instant_mode": r"[\"']materialized_instant[\"']",
    }.items():
        matches = [match.group(0) for match in re.finditer(pattern, promotion)]
        _gate(passed, failed, not matches, gate, matches=matches)
    _gate(
        passed,
        failed,
        'backend = "local_parquet_file"' not in promotion,
        "compatibility_parquet_uses_supported_smoke_backend",
    )

    acquisitions = (DRIVE / "scripts/yzu_cluster/acquisitions.py").read_text(encoding="utf-8")
    for token in (
        "api_error_envelope",
        "empty_collection",
        "metadata_only_backend",
        '"revision_id": revision_id',
    ):
        _gate(passed, failed, token in acquisitions, "strict_query_smoke_token", token=token)

    hardening_tests = (DRIVE / "tests/test_hardening_gates.py").read_text(encoding="utf-8")
    _gate(
        passed,
        failed,
        "accept either ok or clear error shape" not in hardening_tests,
        "no_permissive_query_smoke_assertion",
    )
    return passed, failed


def build_report() -> dict[str, Any]:
    passed, failed = _hard_guarantees()
    inventory = _inventory()
    warnings: list[dict[str, Any]] = []
    cluster = _load_json(DRIVE / "config/yzu_cluster.json")
    gdelt = (cluster.get("pipelines") or {}).get("gdelt_fleet") or {}
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
        "hard_guarantees": {"ok": not failed, "passed": passed, "failed": failed},
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
    print(
        json.dumps(
            {
                "sha": report["sha"],
                "hard_guarantees_ok": report["hard_guarantees"]["ok"],
                "failed": len(report["hard_guarantees"]["failed"]),
                "warnings": len(report["warnings"]),
                "submit_calls": len(report["inventory"]["submit_calls"]),
                "output": str(output.relative_to(ROOT)),
            },
            indent=2,
        )
    )
    return 1 if args.strict and not report["hard_guarantees"]["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
