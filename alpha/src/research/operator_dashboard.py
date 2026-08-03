"""Compact operator dashboard for the investment platform."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(Path(path).read_text())
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def build_operator_dashboard(repo: Path) -> dict[str, Any]:
    repo = Path(repo).resolve()
    signal = _read_json(repo / "backtests/outputs/signals/alpha_live_signal.json")
    scorecard = _read_json(repo / "backtests/outputs/alpha_paper/scorecard_latest.json")
    edge = _read_json(repo / "backtests/outputs/alpha_paper/edge_readiness_latest.json")
    enforcement = _read_json(repo / "reports/investment_enforcement/latest.json")
    manifest_gates = _read_json(repo / "reports/manifest_gates/latest.json")
    accounting_bundle = _read_json(repo / "reports/accounting_bundle/latest.json")
    capabilities = _read_json(repo / "reports/investment_capabilities/latest.json")
    thesis_gates = _read_json(repo / "reports/thesis_gates/latest.json")

    perf = scorecard.get("performance", {}) if isinstance(scorecard.get("performance", {}), Mapping) else {}
    cap_summary = capabilities.get("summary", {}) if isinstance(capabilities.get("summary", {}), Mapping) else {}
    priority_counts = cap_summary.get("priority_counts", {}) if isinstance(cap_summary.get("priority_counts", {}), Mapping) else {}
    status_counts = cap_summary.get("status_counts", {}) if isinstance(cap_summary.get("status_counts", {}), Mapping) else {}

    warnings: list[str] = []
    if edge.get("status") != "ready":
        warnings.append(f"edge_readiness={edge.get('status', 'missing')}")
    if enforcement.get("status") in {"warn", "fail"}:
        warnings.append(f"enforcement={enforcement.get('status')}")
    if priority_counts.get("high", 0):
        warnings.append(f"high_priority_capability_gaps={priority_counts.get('high')}")
    sharpe = perf.get("sharpe_daily_252")
    if isinstance(sharpe, (int, float)) and sharpe < 0:
        warnings.append(f"paper_sharpe={sharpe:.2f}")

    hard_fail = enforcement.get("passed") is False or manifest_gates.get("passed") is False or thesis_gates.get("passed") is False
    status = "fail" if hard_fail else "warn" if warnings else "pass"

    return {
        "generated_at": _utc_now(),
        "repo": str(repo),
        "status": status,
        "warnings": warnings,
        "current_alpha": {
            "strategy": signal.get("strategy"),
            "as_of_month": signal.get("as_of_month") or signal.get("as_of"),
            "latest_equity": perf.get("latest_equity"),
            "paper_sharpe": sharpe,
            "edge_status": edge.get("status"),
            "edge_checks": edge.get("checks", {}),
        },
        "gates": {
            "enforcement_status": enforcement.get("status"),
            "enforcement_passed": enforcement.get("passed"),
            "manifest_gates_passed": manifest_gates.get("passed"),
            "manifest_gate_failures": manifest_gates.get("n_failing"),
            "thesis_gates_passed": thesis_gates.get("passed"),
            "accounting_bundle_status": accounting_bundle.get("status"),
            "accounting_bundle_complete": accounting_bundle.get("complete"),
        },
        "capabilities": {
            "status_counts": status_counts,
            "priority_counts": priority_counts,
            "top_actions": cap_summary.get("top_actions", [])[:10] if isinstance(cap_summary.get("top_actions", []), list) else [],
        },
        "artifacts": {
            "signal": str(repo / "backtests/outputs/signals/alpha_live_signal.json"),
            "scorecard": str(repo / "backtests/outputs/alpha_paper/scorecard_latest.json"),
            "edge_readiness": str(repo / "backtests/outputs/alpha_paper/edge_readiness_latest.json"),
            "enforcement": str(repo / "reports/investment_enforcement/latest.json"),
            "manifest_gates": str(repo / "reports/manifest_gates/latest.json"),
            "accounting_bundle": str(repo / "reports/accounting_bundle/latest.json"),
            "capabilities": str(repo / "reports/investment_capabilities/latest.json"),
        },
    }


def render_operator_dashboard_markdown(report: Mapping[str, Any]) -> str:
    alpha = report.get("current_alpha", {}) if isinstance(report.get("current_alpha", {}), Mapping) else {}
    gates = report.get("gates", {}) if isinstance(report.get("gates", {}), Mapping) else {}
    caps = report.get("capabilities", {}) if isinstance(report.get("capabilities", {}), Mapping) else {}
    lines = [
        "# Investment Operator Dashboard",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Status: `{report.get('status')}`",
        "",
        "## Current Alpha",
        "",
        f"- Strategy: `{alpha.get('strategy')}`",
        f"- Signal as-of: `{alpha.get('as_of_month')}`",
        f"- Paper Sharpe: `{alpha.get('paper_sharpe')}`",
        f"- Latest equity: `{alpha.get('latest_equity')}`",
        f"- Edge readiness: `{alpha.get('edge_status')}`",
        "",
        "## Gates",
        "",
    ]
    for key, value in gates.items():
        lines.append(f"- {key}: `{value}`")
    warnings = report.get("warnings") or []
    lines.extend(["", "## Warnings", ""])
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- none")
    lines.extend(["", "## Capability Counts", ""])
    lines.append(f"- Status counts: `{json.dumps(caps.get('status_counts', {}), sort_keys=True)}`")
    lines.append(f"- Priority counts: `{json.dumps(caps.get('priority_counts', {}), sort_keys=True)}`")
    top_actions = caps.get("top_actions", []) if isinstance(caps.get("top_actions", []), list) else []
    lines.extend(["", "## Top Actions", ""])
    if top_actions:
        for action in top_actions[:10]:
            lines.append(f"- {action.get('capability')}: {action.get('action')}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def write_operator_dashboard(report: Mapping[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jp = out_dir / "latest.json"
    mp = out_dir / "latest.md"
    jp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    mp.write_text(render_operator_dashboard_markdown(report))
    return {"json": str(jp), "markdown": str(mp)}
