"""End-to-end enforcement cycle for stock investment workflows."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.research.accounting_bundle import build_accounting_bundle, write_accounting_bundle
from src.research.accounting_reconciliation import reconcile_accounting, write_reconciliation_report
from src.research.capability_audit import audit_capabilities, write_report as write_capability_report
from src.research.frozen_decisions import decision_report, evaluate_decisions, freeze_from_candidate_registry
from src.research.manifest_gates import manifest_gate_report, write_manifest_gate_report
from src.research.thesis_gates import thesis_gate_report, write_thesis_gate_report
from src.research.thesis_report import build_thesis_report, write_thesis_report


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _status(passed: bool, *, warn: bool = False) -> str:
    if not passed:
        return "fail"
    return "warn" if warn else "pass"


def run_investment_enforcement_cycle(
    *,
    repo: Path,
    registry_csv: Path,
    decision_log: Path,
    panel_csv: Path,
    thesis_register: Path,
    capability_map: Path,
    equity_ledger: Path,
    scorecard: Path,
    out_dir: Path,
    target_signal: Path | None = None,
    target_weights: Path | None = None,
    safety_config: Path | None = None,
    horizon_days: int = 21,
    as_of: str | None = None,
    include_blocked: bool = True,
) -> dict[str, Any]:
    """Run the hard gates that should precede any promotion or live-adjacent action."""

    repo = Path(repo).resolve()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    include_statuses = {"paper_candidate", "deployable_sleeve"}
    if include_blocked:
        include_statuses.add("blocked")

    freeze_from_candidate_registry(
        decision_log,
        registry_csv=registry_csv,
        horizon_days=horizon_days,
        include_statuses=include_statuses,
    )
    evaluate_decisions(decision_log, panel_csv=panel_csv, as_of=as_of)
    decisions = decision_report(decision_log)

    accounting = reconcile_accounting(equity_ledger_path=equity_ledger, scorecard_path=scorecard)
    accounting_paths = write_reconciliation_report(accounting, repo / "reports" / "accounting_reconciliation")
    accounting_bundle = build_accounting_bundle(
        repo=repo,
        strategy="current_alpha",
        run_id="current_alpha",
        target_weights_path=target_weights,
        target_signal_path=target_signal,
        equity_ledger_path=equity_ledger,
        scorecard_path=scorecard,
        safety_config_path=safety_config,
    )
    accounting_bundle_paths = write_accounting_bundle(accounting_bundle, repo / "reports" / "accounting_bundle")

    thesis = build_thesis_report(thesis_register)
    thesis_paths = write_thesis_report(thesis, repo / "reports" / "thesis_register")

    thesis_gates = thesis_gate_report(registry_csv, thesis_register)
    thesis_gate_paths = write_thesis_gate_report(thesis_gates, repo / "reports" / "thesis_gates")

    manifest_gates = manifest_gate_report(
        registry_csv,
        repo=repo,
        decision_log=decision_log,
    )
    manifest_gate_paths = write_manifest_gate_report(manifest_gates, repo / "reports" / "manifest_gates")

    capabilities = audit_capabilities(repo, capability_map)
    capability_paths = write_capability_report(capabilities, repo / "reports" / "investment_capabilities")

    capability_summary = capabilities.get("summary", {})
    priority_counts = capability_summary.get("priority_counts", {}) if isinstance(capability_summary, Mapping) else {}
    high_priority = int(priority_counts.get("high", 0) or 0)
    decision_warn = bool(decisions.get("n_pending", 0)) or (
        decisions.get("mean_active_return") is not None and float(decisions.get("mean_active_return", 0.0)) < 0.0
    )

    hard_checks = {
        "accounting_reconciliation": bool(accounting.get("passed")),
        "thesis_gates": bool(thesis_gates.get("passed")),
        "manifest_gates": bool(manifest_gates.get("passed")),
    }
    warnings = []
    if high_priority:
        warnings.append(f"high_priority_capability_gaps={high_priority}")
    if decision_warn:
        warnings.append("frozen_decisions_need_attention")
    if not accounting_bundle.get("complete"):
        warnings.append(f"accounting_bundle_status={accounting_bundle.get('status')}")

    report = {
        "generated_at": _utc_now(),
        "repo": str(repo),
        "passed": all(hard_checks.values()),
        "status": _status(all(hard_checks.values()), warn=bool(warnings)),
        "warnings": warnings,
        "hard_checks": hard_checks,
        "artifacts": {
            "frozen_decisions": str(decision_log),
            "accounting_reconciliation": accounting_paths,
            "accounting_bundle": accounting_bundle_paths,
            "thesis_register": thesis_paths,
            "thesis_gates": thesis_gate_paths,
            "manifest_gates": manifest_gate_paths,
            "investment_capabilities": capability_paths,
        },
        "decisions": decisions,
        "accounting": {
            "passed": accounting.get("passed"),
            "reasons": accounting.get("reasons", []),
            "metrics": accounting.get("metrics", {}),
        },
        "accounting_bundle": {
            "status": accounting_bundle.get("status"),
            "complete": accounting_bundle.get("complete"),
            "missing_artifacts": accounting_bundle.get("missing_artifacts", []),
            "checks": accounting_bundle.get("checks", {}),
        },
        "thesis": {
            "n_theses": thesis.get("n_theses"),
            "missing_invalidation_trigger": thesis.get("missing_invalidation_trigger", []),
            "missing_contradiction_checks": thesis.get("missing_contradiction_checks", []),
        },
        "thesis_gates": {
            "passed": thesis_gates.get("passed"),
            "n_manifests": thesis_gates.get("n_manifests"),
            "n_failing": thesis_gates.get("n_failing"),
        },
        "manifest_gates": {
            "passed": manifest_gates.get("passed"),
            "n_manifests": manifest_gates.get("n_manifests"),
            "n_failing": manifest_gates.get("n_failing"),
            "reasons": manifest_gates.get("reasons", []),
        },
        "capabilities": capability_summary,
    }
    write_enforcement_report(report, out_dir)
    return report


def render_enforcement_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Investment Enforcement Cycle",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Hard passed: `{report.get('passed')}`",
        "",
        "## Hard Checks",
        "",
    ]
    hard = report.get("hard_checks", {})
    if isinstance(hard, Mapping):
        for key, value in hard.items():
            lines.append(f"- {key}: `{value}`")
    warnings = report.get("warnings") or []
    lines.extend(["", "## Warnings", ""])
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- none")

    decisions = report.get("decisions", {})
    if isinstance(decisions, Mapping):
        lines.extend(
            [
                "",
                "## Frozen Decisions",
                "",
                f"- Decisions: `{decisions.get('n_decisions')}`",
                f"- Evaluated: `{decisions.get('n_evaluated')}`",
                f"- Pending: `{decisions.get('n_pending')}`",
                f"- Mean active return: `{decisions.get('mean_active_return')}`",
            ]
        )

    manifest = report.get("manifest_gates", {})
    if isinstance(manifest, Mapping):
        lines.extend(
            [
                "",
                "## Manifest Gates",
                "",
                f"- Passed: `{manifest.get('passed')}`",
                f"- Failing: `{manifest.get('n_failing')}`",
            ]
        )
        for reason in manifest.get("reasons", [])[:10]:
            lines.append(f"- {reason}")

    bundle = report.get("accounting_bundle", {})
    if isinstance(bundle, Mapping):
        lines.extend(
            [
                "",
                "## Accounting Bundle",
                "",
                f"- Status: `{bundle.get('status')}`",
                f"- Complete: `{bundle.get('complete')}`",
            ]
        )
        missing = bundle.get("missing_artifacts") or []
        if missing:
            lines.append(f"- Missing: `{', '.join(map(str, missing[:12]))}`")

    return "\n".join(lines) + "\n"


def write_enforcement_report(report: Mapping[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jp = out_dir / "latest.json"
    mp = out_dir / "latest.md"
    jp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    mp.write_text(render_enforcement_markdown(report))
    return {"json": str(jp), "markdown": str(mp)}
