#!/usr/bin/env python3
"""Single daily entrypoint — global alpha + IDN sleeve + news gates + manifest.

Replaces scattered one-off scripts with one wired cycle driven by
config/platform_integration.json.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
SR_ROOT = _bmod.bootstrap_repo_paths(__file__)

from src.research.platform_bridge import (  # noqa: E402
    file_age_days,
    latest_child_run,
    load_integration_config,
)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _run(cmd: list[str], *, label: str) -> dict[str, Any]:
    print(f"\n==> {label}")
    print("    ", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(SR_ROOT), capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout[-4000:])
    if proc.returncode != 0:
        print(proc.stderr[-2000:], file=sys.stderr)
    return {
        "label": label,
        "cmd": cmd,
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
    }


def _should_refresh(path: Path, max_age_days: float) -> bool:
    age = file_age_days(path)
    if age is None:
        return True
    return age > float(max_age_days)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=SR_ROOT / "config/platform_integration.json")
    ap.add_argument("--skip-global", action="store_true")
    ap.add_argument("--skip-idn", action="store_true")
    ap.add_argument("--skip-news", action="store_true")
    ap.add_argument("--skip-audit", action="store_true")
    ap.add_argument("--force-idn-sheet", action="store_true")
    ap.add_argument("--force-empirical", action="store_true", help="Force sentiment refresh + validation backtests.")
    ap.add_argument("--force-news", action="store_true")
    ap.add_argument("--skip-fetch", action="store_true", help="Pass --skip-fetch to global alpha (panel already fresh).")
    ap.add_argument("--dry-run", action="store_true", help="Print planned steps only.")
    args = ap.parse_args()

    cfg = load_integration_config(SR_ROOT, args.config)
    out_dir = SR_ROOT / cfg.get("outputs_dir", "backtests/outputs/platform")
    out_dir.mkdir(parents=True, exist_ok=True)
    py = SR_ROOT / ".venv/bin/python"
    if not py.is_file():
        py = Path(sys.executable)

    steps: list[dict[str, Any]] = []
    manifest: dict[str, Any] = {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "config": str(args.config),
        "sleeves": {},
    }

    fuel = cfg.get("alpha_fuel", {})
    if fuel.get("enabled", True) and not args.dry_run:
        fuel_cmd = [
            str(py),
            "scripts/run_alpha_research_cycle.py",
            "--manifest",
            str(SR_ROOT / fuel.get("manifest", "alpha/config/alpha_fuel_manifest.json")),
            "--out-dir",
            str(SR_ROOT / fuel.get("out_dir", "backtests/outputs/platform/alpha_fuel")),
            "--no-http",
        ]
        steps.append(_run(fuel_cmd, label="alpha_fuel_inventory"))
        fuel_report = _read_json(SR_ROOT / fuel.get("out_dir", "backtests/outputs/platform/alpha_fuel") / "latest.json")
        if fuel_report:
            manifest["sleeves"]["alpha_fuel"] = {
                "n_ready": fuel_report.get("n_ready"),
                "n_stale": fuel_report.get("n_stale"),
                "n_missing": fuel_report.get("n_missing"),
                "supply_asks": len(fuel_report.get("supply_asks") or []),
                "report": str(SR_ROOT / fuel.get("out_dir", "backtests/outputs/platform/alpha_fuel") / "latest.json"),
            }
    elif fuel.get("enabled", True) and args.dry_run:
        steps.append({
            "label": "alpha_fuel_inventory",
            "cmd": [str(py), "scripts/run_alpha_research_cycle.py", "--no-http"],
            "ok": True,
            "dry_run": True,
        })

    ga = cfg.get("global_alpha", {})
    if ga.get("enabled", True) and not args.skip_global:
        cmd = [str(py), "scripts/alpha_live_cycle.py"]
        if ga.get("auto_params", True):
            cmd.append("--auto-params")
        if ga.get("skip_fetch") or args.skip_fetch:
            cmd.append("--skip-fetch")
        if ga.get("relevance_overlay", True):
            cmd.extend(
                [
                    "--relevance-overlay",
                    "--relevance-floor-gross",
                    str(ga.get("relevance_floor_gross", 0.55)),
                    "--relevance-lookback-weeks",
                    str(int(ga.get("relevance_lookback_weeks", 52))),
                ]
            )
        elif ga.get("news_risk_overlay", False):
            cmd.extend(["--news-risk-overlay", "--news-risk-floor-gross", str(ga.get("news_risk_floor_gross", 0.55))])
        if ga.get("crypto_reg_overlay", False):
            cmd.append("--crypto-reg-overlay")
        gate = str(ga.get("promotion_gate", "warn"))
        if gate != "off":
            cmd.extend(["--promotion-gate", gate])
        on_block = str(ga.get("on_block_fallback", "beta_core") or "beta_core")
        cmd.extend(["--on-block-fallback", on_block])
        profile = ga.get("control_profile")
        if profile:
            cmd.extend(["--control-profile", str(profile)])
        if args.dry_run:
            steps.append({"label": "global_alpha", "cmd": cmd, "ok": True, "dry_run": True})
        else:
            steps.append(_run(cmd, label="global_alpha"))

        sig_path = SR_ROOT / ga.get("signal_out", "backtests/outputs/signals/alpha_live_signal.json")
        sig = _read_json(sig_path) or {}
        manifest["sleeves"]["global_alpha"] = {
            "signal": str(sig_path),
            "as_of_month": sig.get("as_of_month"),
            "strategy": sig.get("strategy"),
            "weights": sig.get("weights"),
            "news_risk_overlay": sig.get("news_risk_overlay"),
            "market_relevance_overlay": sig.get("market_relevance_overlay"),
            "crypto_reg_overlay": sig.get("crypto_reg_overlay"),
            "promotion_gate": sig.get("promotion_gate"),
            "ledger": str(SR_ROOT / ga.get("ledger", "backtests/outputs/alpha_paper/ledger.csv")),
        }

    idn = cfg.get("idn_sleeve", {})
    if idn.get("enabled", True) and not args.skip_idn:
        port = SR_ROOT / idn.get("portfolio", "backtests/outputs/idn_weekly_position_sheet/latest_portfolio.json")
        max_age = float(idn.get("refresh_sheet_if_older_days", 6))
        if args.force_idn_sheet or _should_refresh(port, max_age):
            cmd = [str(py), "scripts/run_idn_weekly_position_sheet.py"]
            if idn.get("max_single_name_weight") is not None:
                cmd.extend(["--max-single-name-weight", str(idn["max_single_name_weight"])])
            gdelt_mode = idn.get("gdelt_retail_filter")
            if gdelt_mode:
                cmd.extend(["--gdelt-retail-filter", str(gdelt_mode)])
            if idn.get("gdelt_lookback_days") is not None:
                cmd.extend(["--gdelt-lookback-days", str(int(idn["gdelt_lookback_days"]))])
            if idn.get("gdelt_min_mention_rows") is not None:
                cmd.extend(["--gdelt-min-mention-rows", str(int(idn["gdelt_min_mention_rows"]))])
            bandar_mode = idn.get("bandar_confirm")
            if bandar_mode:
                cmd.extend(["--bandar-confirm", str(bandar_mode)])
            if idn.get("max_tilt_symbols") is not None:
                cmd.extend(["--max-tilt-symbols", str(int(idn["max_tilt_symbols"]))])
            sig_univ = idn.get("signal_universe")
            if sig_univ:
                cmd.extend(["--signal-universe", str(sig_univ)])
            if args.dry_run:
                steps.append({"label": "idn_weekly_sheet", "cmd": cmd, "ok": True, "dry_run": True})
            else:
                steps.append(_run(cmd, label="idn_weekly_sheet"))
        else:
            steps.append({"label": "idn_weekly_sheet", "ok": True, "skipped": "fresh"})

        op_port = SR_ROOT / idn.get("operator_portfolio", "backtests/outputs/idn_operator/latest_portfolio.json")
        op_rules_port = SR_ROOT / idn.get(
            "operator_rules_portfolio", "backtests/outputs/idn_operator/latest_rules_portfolio.json"
        )
        op_llm_port = SR_ROOT / idn.get(
            "operator_llm_portfolio", "backtests/outputs/idn_operator/latest_llm_portfolio.json"
        )
        op_ledger = SR_ROOT / idn.get("operator_ledger", "backtests/outputs/idn_operator/paper/ledger.csv")
        op_rules_ledger = SR_ROOT / idn.get(
            "operator_rules_ledger", "backtests/outputs/idn_operator/paper/rules_ledger.csv"
        )
        op_llm_ledger = SR_ROOT / idn.get(
            "operator_llm_ledger", "backtests/outputs/idn_operator/paper/llm_ledger.csv"
        )

        if idn.get("operator_brief", False):
            cmd = [str(py), "scripts/run_idn_operator_brief.py"]
            if idn.get("operator_aggressive", False):
                cmd.append("--aggressive")
            cmd.append("--emit-portfolio")
            llm_backend = idn.get("operator_llm", "skip")
            if llm_backend and llm_backend != "skip":
                cmd.extend(["--llm", str(llm_backend)])
                llm_mode = idn.get("operator_llm_mode", "agent")
                cmd.extend(["--llm-mode", str(llm_mode)])
                if idn.get("operator_llm_model"):
                    cmd.extend(["--llm-model", str(idn["operator_llm_model"])])
            if args.dry_run:
                steps.append({"label": "idn_operator_brief", "cmd": cmd, "ok": True, "dry_run": True})
            else:
                steps.append(_run(cmd, label="idn_operator_brief"))

        if idn.get("operator_aggressive", False) and op_port.exists():
            op_ledger.parent.mkdir(parents=True, exist_ok=True)
            for label, port_path, ledger_path in (
                ("idn_operator_paper", op_port, op_ledger),
                ("idn_operator_rules_paper", op_rules_port, op_rules_ledger),
                ("idn_operator_llm_paper", op_llm_port, op_llm_ledger),
            ):
                if not port_path.exists():
                    continue
                moves_name = "recent_moves.json" if ledger_path == op_ledger else f"{ledger_path.stem}_moves.json"
                cmd = [
                    str(py),
                    "scripts/idn_paper_tracker.py",
                    "--portfolio",
                    str(port_path),
                    "--ledger",
                    str(ledger_path),
                    "--moves-out",
                    str(ledger_path.parent / moves_name),
                    "--initial-equity",
                    str(idn.get("initial_equity", 10_000)),
                ]
                if args.dry_run:
                    steps.append({"label": label, "cmd": cmd, "ok": True, "dry_run": True})
                else:
                    steps.append(_run(cmd, label=label))

        if port.exists():
            cmd = [
                str(py),
                "scripts/idn_paper_tracker.py",
                "--portfolio",
                str(port),
                "--ledger",
                str(SR_ROOT / idn.get("ledger", "backtests/outputs/idn_weekly_position_sheet/paper/ledger.csv")),
                "--moves-out",
                str(SR_ROOT / idn.get("moves", "backtests/outputs/idn_weekly_position_sheet/paper/recent_moves.json")),
                "--initial-equity",
                str(idn.get("initial_equity", 10_000)),
            ]
            if args.dry_run:
                steps.append({"label": "idn_paper_tracker", "cmd": cmd, "ok": True, "dry_run": True})
            else:
                steps.append(_run(cmd, label="idn_paper_tracker"))

        portfolio = _read_json(port) or {}
        moves = _read_json(SR_ROOT / idn.get("moves", "backtests/outputs/idn_weekly_position_sheet/paper/recent_moves.json")) or {}
        op_moves = {}
        if idn.get("operator_aggressive", False) and op_port.exists():
            op_moves = _read_json(op_ledger.parent / "recent_moves.json") or {}
            if not op_moves and op_ledger.exists():
                op_moves = _read_json(op_ledger.parent / "ledger_moves.json") or {}
        manifest["sleeves"]["idn"] = {
            "portfolio": str(port),
            "strategy": portfolio.get("strategy"),
            "as_of_week": portfolio.get("as_of_week"),
            "weights": portfolio.get("weights"),
            "latest_move_pct": moves.get("today", {}).get("portfolio_return_pct"),
            "ledger": str(SR_ROOT / idn.get("ledger", "backtests/outputs/idn_weekly_position_sheet/paper/ledger.csv")),
        }
        if idn.get("operator_aggressive", False) and op_port.exists():
            op_pf = _read_json(op_port) or {}
            manifest["sleeves"]["idn_operator"] = {
                "portfolio": str(op_port),
                "rules_portfolio": str(op_rules_port) if op_rules_port.exists() else None,
                "llm_portfolio": str(op_llm_port) if op_llm_port.exists() else None,
                "strategy": op_pf.get("strategy"),
                "as_of_week": op_pf.get("as_of_week"),
                "weights": op_pf.get("weights"),
                "avoid": op_pf.get("avoid"),
                "latest_move_pct": op_moves.get("today", {}).get("portfolio_return_pct"),
                "ledger": str(op_ledger),
                "rules_ledger": str(op_rules_ledger) if op_rules_ledger.exists() else None,
                "llm_ledger": str(op_llm_ledger) if op_llm_ledger.exists() else None,
                "brief": str(SR_ROOT / idn.get("operator_brief_out", "backtests/outputs/idn_operator/latest.md")),
            }

        er_cfg = cfg.get("idn_empirical_research", {})
        if er_cfg.get("enabled", True) and idn.get("enabled", True) and not args.skip_idn:
            er_path = SR_ROOT / er_cfg.get("out", "backtests/outputs/platform/idn_empirical_research/latest.md")
            er_json = er_path.parent / "latest.json"
            val_path = SR_ROOT / er_cfg.get(
                "validation_out", "backtests/outputs/platform/idn_sentiment_validation/latest.json"
            )
            val_max_age = float(er_cfg.get("refresh_validation_days", 7))
            val_fresh = not args.force_empirical and val_path.exists() and not _should_refresh(val_path, val_max_age)
            cmd = [str(py), "scripts/run_idn_empirical_research.py", "--config", str(args.config)]
            if val_fresh:
                cmd.append("--skip-validation")
            elif args.force_empirical:
                cmd.append("--force-validation")
            if args.dry_run:
                steps.append({"label": "idn_empirical_research", "cmd": cmd, "ok": True, "dry_run": True})
            else:
                steps.append(_run(cmd, label="idn_empirical_research"))
            er_summary = _read_json(er_json) or {}
            manifest["idn_empirical_research"] = {
                "brief": str(er_path),
                "json": str(er_json),
                "validation_fresh": val_fresh,
                "live_paper": (er_summary.get("live_paper") or {}),
                "historical_validation": (er_summary.get("historical_validation") or {}),
            }

    news = cfg.get("news_strategies", {})
    if news.get("enabled", True) and not args.skip_news:
        grid = SR_ROOT / news.get("out_grid", "backtests/outputs/news_strategy_grid")
        latest = latest_child_run(grid)
        summary_path = latest / "summary.json" if latest else None
        max_age = float(news.get("refresh_if_older_days", 7))
        need = args.force_news or summary_path is None or _should_refresh(summary_path, max_age)
        if need:
            cmd = [str(py), "scripts/run_news_strategy_promotion_trial.py"]
            if args.dry_run:
                steps.append({"label": "news_strategy_promotion", "cmd": cmd, "ok": True, "dry_run": True})
            else:
                steps.append(_run(cmd, label="news_strategy_promotion"))
            latest = latest_child_run(grid)
            summary_path = latest / "summary.json" if latest else None
        else:
            steps.append({"label": "news_strategy_promotion", "ok": True, "skipped": "fresh"})

        gates_path = latest / "promotion_gates.csv" if latest else None
        summary = _read_json(summary_path) if summary_path and summary_path.exists() else {}
        manifest["sleeves"]["news_strategies"] = {
            "latest_run": str(latest) if latest else None,
            "summary": summary,
            "promotion_gates_csv": str(gates_path) if gates_path and gates_path.exists() else None,
        }

    audit_cfg = cfg.get("research_audit", {})
    if audit_cfg.get("enabled", True) and not args.skip_audit:
        latest_audit = SR_ROOT / audit_cfg.get("out_dir", "reports/investment_research_engine") / "latest.json"
        max_age = float(audit_cfg.get("refresh_if_older_days", 7))
        if _should_refresh(latest_audit, max_age):
            cmd = [str(py), "scripts/investment_research_engine_audit.py"]
            if args.dry_run:
                steps.append({"label": "research_audit", "cmd": cmd, "ok": True, "dry_run": True})
            else:
                steps.append(_run(cmd, label="research_audit"))
        else:
            steps.append({"label": "research_audit", "ok": True, "skipped": "fresh"})
        manifest["research_audit"] = str(latest_audit)

    val_cfg = cfg.get("market_relevance_validation", {})
    if val_cfg.get("enabled", True):
        val_path = SR_ROOT / val_cfg.get("out", "backtests/outputs/platform/market_relevance_validation/latest.json")
        max_age = float(val_cfg.get("refresh_if_older_days", 7))
        if _should_refresh(val_path, max_age):
            cmd = [str(py), "scripts/run_market_relevance_validation.py"]
            if args.dry_run:
                steps.append({"label": "market_relevance_validation", "cmd": cmd, "ok": True, "dry_run": True})
            else:
                steps.append(_run(cmd, label="market_relevance_validation"))
        else:
            steps.append({"label": "market_relevance_validation", "ok": True, "skipped": "fresh"})
        manifest["market_relevance_validation"] = str(val_path)

    manifest["steps"] = steps
    manifest["all_ok"] = all(s.get("ok", False) for s in steps)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_path = out_dir / f"cycle_{stamp}.json"
    latest_path = out_dir / "latest.json"
    latest_md = out_dir / "latest.md"
    run_path.write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    latest_path.write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")

    lines = [
        "# Platform cycle",
        f"- built: {manifest['built_at_utc']}",
        f"- all_ok: {manifest['all_ok']}",
        "",
    ]
    for name, sleeve in manifest.get("sleeves", {}).items():
        lines.append(f"## {name}")
        for k, v in sleeve.items():
            if k == "weights" and isinstance(v, dict):
                lines.append(f"- weights: {', '.join(f'{a} {b:.0%}' for a,b in v.items())}")
            else:
                lines.append(f"- {k}: {v}")
        lines.append("")
    er = manifest.get("idn_empirical_research") or {}
    if er:
        lines.append("## idn_empirical_research")
        lines.append(f"- brief: {er.get('brief')}")
        hv = er.get("historical_validation") or {}
        if hv.get("available"):
            lines.append(
                f"- operator_rules_oos_holdout: {(hv.get('operator_rules_verdict') or {}).get('oos_holdout')}"
            )
            lines.append(f"- bbca_retail: {(hv.get('retail_playbook') or {}).get('bbca_support_rsi', {}).get('verdict')}")
        lp = er.get("live_paper") or {}
        for sleeve, m in lp.items():
            if isinstance(m, dict) and m.get("available"):
                ret = m.get("total_return_pct")
                eq = m.get("terminal_equity")
                lines.append(
                    f"- live_{sleeve}: {ret:+.2f}% (equity ${eq:,.0f})"
                    if ret is not None and eq is not None
                    else f"- live_{sleeve}: available"
                )
        lines.append("")
    latest_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nManifest: {latest_path}")
    print(f"Summary:  {latest_md}")
    return 0 if manifest["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
