#!/usr/bin/env python3
"""One-screen health report for the Sharpe-Renaissance research platform."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
SR_ROOT = _bmod.bootstrap_repo_paths(__file__)


def _ok(label: str, detail: str = "") -> None:
    suffix = f" — {detail}" if detail else ""
    print(f"  OK   {label}{suffix}")


def _warn(label: str, detail: str = "") -> None:
    suffix = f" — {detail}" if detail else ""
    print(f"  WARN {label}{suffix}")


def _fail(label: str, detail: str = "") -> None:
    suffix = f" — {detail}" if detail else ""
    print(f"  FAIL {label}{suffix}")


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def main() -> int:
    print(f"Sharpe-Renaissance platform status\n  root: {SR_ROOT}\n")

    venv_py = SR_ROOT / ".venv" / "bin" / "python"
    if venv_py.is_file():
        _ok("venv", str(venv_py))
    else:
        _warn("venv", "missing — run scripts/setup_research_platform.sh")

    try:
        import src.research.fingerprint  # noqa: F401

        _ok("import src.research")
    except Exception as exc:
        _fail("import src.research", repr(exc))

    reg_path = SR_ROOT / "config" / "research_query_registry.json"
    if reg_path.exists():
        data = _read_json(reg_path) or {}
        ds = data.get("datasets", [])
        n_ds = len(ds) if isinstance(ds, list) else len(ds)
        _ok("research registry", f"{n_ds} datasets")
    else:
        _warn("research registry", "missing")

    panel = SR_ROOT / "data_lake" / "daily_alpha_panel.csv"
    if panel.exists():
        try:
            import pandas as pd

            df = pd.read_csv(panel, usecols=["Date"])
            latest = str(pd.to_datetime(df["Date"]).max().date())
            _ok("alpha panel", f"latest={latest}")
        except Exception as exc:
            _warn("alpha panel", repr(exc))
    else:
        _warn("alpha panel", "not built yet")

    signal = SR_ROOT / "backtests" / "outputs" / "signals" / "alpha_live_signal.json"
    score = SR_ROOT / "backtests" / "outputs" / "alpha_paper" / "scorecard_latest.json"
    edge = SR_ROOT / "backtests" / "outputs" / "alpha_paper" / "edge_readiness_latest.json"

    if signal.exists():
        sig = _read_json(signal) or {}
        _ok("live signal", f"as_of={sig.get('as_of_month', '?')} strategy={sig.get('strategy', '?')}")
    else:
        _warn("live signal", "missing")

    if score.exists():
        sc = _read_json(score) or {}
        perf = sc.get("performance", {})
        if sc.get("fingerprint_error"):
            _warn("scorecard fingerprint", str(sc["fingerprint_error"])[:80])
        else:
            _ok("scorecard fingerprint")
        sh = perf.get("sharpe_daily_252")
        _ok("paper sharpe", f"{sh:.2f}" if isinstance(sh, (int, float)) else "n/a")
    else:
        _warn("scorecard", "missing")

    if edge.exists():
        er = _read_json(edge) or {}
        status = er.get("status", "?")
        checks = er.get("checks", {})
        if status == "ready":
            _ok("edge readiness", status)
        else:
            _warn("edge readiness", f"{status} checks={checks}")
    else:
        _warn("edge readiness", "missing")

    audit = SR_ROOT / "reports" / "investment_research_engine" / "latest.json"
    if audit.exists():
        _ok("research engine audit", str(audit))
    else:
        _warn("research engine audit", "run scripts/investment_research_engine_audit.py")

    cap_audit = SR_ROOT / "reports" / "investment_capabilities" / "latest.json"
    if cap_audit.exists():
        cap = _read_json(cap_audit) or {}
        summary = cap.get("summary", {})
        statuses = summary.get("status_counts", {})
        priorities = summary.get("priority_counts", {})
        high = priorities.get("high", 0)
        detail = (
            f"strong={statuses.get('strong', 0)} partial={statuses.get('partial', 0)} "
            f"weak={statuses.get('weak', 0)} high_priority={high}"
        )
        if high:
            _warn("investment capabilities", detail)
        else:
            _ok("investment capabilities", detail)
    else:
        _warn("investment capabilities", "run scripts/investment_capability_audit.py")

    repo_inventory = SR_ROOT / "reports" / "repo_inventory" / "latest.json"
    if repo_inventory.exists():
        inv = _read_json(repo_inventory) or {}
        dispositions = inv.get("disposition_counts", {})
        quarantine = dispositions.get("quarantine_candidate", {}).get("count", 0)
        legacy = len(inv.get("legacy_investment_scripts", []) or [])
        _warn("repo inventory", f"files={inv.get('n_files')} legacy_scripts={legacy} quarantine_candidates={quarantine}")
    else:
        _warn("repo inventory", "run scripts/investment_repo_inventory.py")

    decisions = SR_ROOT / "backtests" / "outputs" / "investment_cockpit" / "frozen_decisions.csv"
    if decisions.exists():
        try:
            import pandas as pd

            ddf = pd.read_csv(decisions)
            evaluated = int((ddf.get("evaluated_at", "").astype(str).str.strip() != "").sum()) if not ddf.empty else 0
            _ok("frozen decisions", f"n={len(ddf)} evaluated={evaluated}")
        except Exception as exc:
            _warn("frozen decisions", repr(exc))
    else:
        _warn("frozen decisions", "run scripts/frozen_decision_tracker.py init")

    acct = SR_ROOT / "reports" / "accounting_reconciliation" / "latest.json"
    if acct.exists():
        ar = _read_json(acct) or {}
        if ar.get("passed"):
            _ok("accounting reconciliation")
        else:
            _warn("accounting reconciliation", f"reasons={ar.get('reasons', [])[:4]}")
    else:
        _warn("accounting reconciliation", "run scripts/accounting_reconcile.py")

    bundle = SR_ROOT / "reports" / "accounting_bundle" / "latest.json"
    if bundle.exists():
        ab = _read_json(bundle) or {}
        if ab.get("complete"):
            _ok("accounting bundle", str(ab.get("status")))
        else:
            _warn("accounting bundle", f"status={ab.get('status')} missing={ab.get('missing_artifacts', [])[:5]}")
    else:
        _warn("accounting bundle", "run scripts/accounting_bundle.py")

    thesis_gates = SR_ROOT / "reports" / "thesis_gates" / "latest.json"
    if thesis_gates.exists():
        tg = _read_json(thesis_gates) or {}
        if tg.get("passed"):
            _ok("thesis gates", f"manifests={tg.get('n_manifests')}")
        else:
            _warn("thesis gates", f"failing={tg.get('n_failing')}")
    else:
        _warn("thesis gates", "run scripts/thesis_gates.py")

    manifest_gates = SR_ROOT / "reports" / "manifest_gates" / "latest.json"
    if manifest_gates.exists():
        mg = _read_json(manifest_gates) or {}
        if mg.get("passed"):
            _ok("manifest gates", f"manifests={mg.get('n_manifests')}")
        else:
            _warn("manifest gates", f"failing={mg.get('n_failing')} reasons={mg.get('reasons', [])[:3]}")
    else:
        _warn("manifest gates", "run scripts/manifest_gates.py")

    enforcement = SR_ROOT / "reports" / "investment_enforcement" / "latest.json"
    if enforcement.exists():
        en = _read_json(enforcement) or {}
        status = en.get("status", "?")
        if en.get("passed") and status != "warn":
            _ok("investment enforcement", status)
        elif en.get("passed"):
            _warn("investment enforcement", f"{status} warnings={en.get('warnings', [])[:3]}")
        else:
            _fail("investment enforcement", f"{status} checks={en.get('hard_checks', {})}")
    else:
        _warn("investment enforcement", "run scripts/investment_enforcement_cycle.py")

    operator = SR_ROOT / "reports" / "investment_operator" / "latest.json"
    if operator.exists():
        op = _read_json(operator) or {}
        if op.get("status") == "pass":
            _ok("operator dashboard", "pass")
        else:
            _warn("operator dashboard", f"{op.get('status')} warnings={op.get('warnings', [])[:4]}")
    else:
        _warn("operator dashboard", "run scripts/investment_operator_dashboard.py")

    manifest = SR_ROOT / "backtests" / "outputs" / "platform" / "latest.json"
    if manifest.exists():
        m = _read_json(manifest) or {}
        sleeves = m.get("sleeves", {})
        ga = sleeves.get("global_alpha", {})
        idn = sleeves.get("idn", {})
        _ok(
            "platform cycle",
            f"all_ok={m.get('all_ok')} global={ga.get('as_of_month')} idn={idn.get('as_of_week')}",
        )
        rel = ga.get("market_relevance_overlay") or {}
        if rel:
            _ok(
                "relevance overlay",
                f"level_z={rel.get('level_z', '?'):.2f} gross={rel.get('gross_scalar', '?'):.2f}"
                if isinstance(rel.get("level_z"), (int, float))
                else f"gross={rel.get('gross_scalar', '?')}",
            )
    else:
        _warn("platform cycle", "run scripts/run_unified_platform_cycle.py")

    deep = SR_ROOT / "backtests" / "outputs" / "platform" / "deep_research" / "latest.json"
    if deep.exists():
        d = _read_json(deep) or {}
        best = (d.get("verdict") or {}).get("best_emergent") or {}
        _ok("deep research", f"pairs={d.get('n_pairs')} top={best.get('feature', '?')}")
    else:
        _warn("deep research", "run scripts/run_deep_discovery_lean.py")

    val = SR_ROOT / "backtests" / "outputs" / "platform" / "market_relevance_validation" / "latest.json"
    if val.exists():
        v = _read_json(val) or {}
        verdict = v.get("verdict") or {}
        _ok(
            "market relevance validation",
            f"vol_stable={verdict.get('vol_signal_stable_multi_era')} "
            f"ret_2024={verdict.get('return_signal_strong_2024_oos_only')}",
        )
    else:
        _warn("market relevance validation", "run scripts/run_market_relevance_validation.py")

    print("\nTimers (user systemd):")
    try:
        out = subprocess.check_output(
            ["systemctl", "--user", "list-timers", "--all", "--no-pager"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        for line in out.splitlines():
            if any(k in line for k in ("alpha-live", "alpha-scorecard", "asia-news", "reddit-ingest", "investment-enforcement")):
                print(f"  {line.strip()}")
    except Exception:
        _warn("systemd", "could not list user timers")

    print("\nQuick commands:")
    print(f"  {venv_py if venv_py.is_file() else 'python3'} {SR_ROOT}/scripts/run_unified_platform_cycle.py --skip-fetch")
    print(f"  {SR_ROOT}/scripts/run_research_spine.sh status")
    print(f"  {SR_ROOT}/scripts/run_research_spine.sh capabilities")
    print(f"  {SR_ROOT}/scripts/run_research_spine.sh repo-inventory")
    print(f"  {SR_ROOT}/scripts/run_research_spine.sh ideas report")
    print(f"  {SR_ROOT}/scripts/run_research_spine.sh decisions report")
    print(f"  {SR_ROOT}/scripts/run_research_spine.sh reconcile")
    print(f"  {SR_ROOT}/scripts/run_research_spine.sh accounting-bundle")
    print(f"  {SR_ROOT}/scripts/run_research_spine.sh thesis-gates")
    print(f"  {SR_ROOT}/scripts/run_research_spine.sh manifest-gates")
    print(f"  {SR_ROOT}/scripts/run_research_spine.sh enforce")
    print(f"  {SR_ROOT}/scripts/run_research_spine.sh operator")
    print(f"  {SR_ROOT}/scripts/run_research_query_engine.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
